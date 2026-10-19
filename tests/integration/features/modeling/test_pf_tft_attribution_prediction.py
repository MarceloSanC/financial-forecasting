"""Predição de atribuição do `PfTftTrainer` (Stage 7.3, Task 11; CA7, I6-I8, C5, C7).

Um TFT minúsculo real por módulo (`_tft_checkpoint_fixture`), com `batch_size` menor que
o número de decisões, para que o doador de algumas decisões fique noutro lote. A
referência do bloco doador é INDEPENDENTE da tabela do adapter: um espião grava os
dataloaders que o adapter passa ao `_emit`; o teste percorre o da identidade e o
permutado, e compara o encoder trocado com o da decisão doadora na passagem de
identidade.
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import torch
from pytorch_forecasting import TemporalFusionTransformer

from financial_forecasting.features.modeling.adapters.out.pytorch_forecasting import (
    pf_tft_trainer as module,
)
from financial_forecasting.features.modeling.adapters.out.pytorch_forecasting.pf_tft_trainer import (  # noqa: E501
    PfTftTrainer,
    donor_blocks,
)
from financial_forecasting.features.modeling.application.ports.out.tft_checkpoint_predictor import (
    ArtifactChangedError,
    FamilyFeatureKnownError,
    TftAttributionPrediction,
)
from tests.contract.features.modeling._tft_checkpoint_fixture import (
    KNOWN_FAMILY_COLUMN,
    TrainedCheckpoint,
    train_tiny_checkpoint,
    train_tiny_checkpoint_with_known_family_column,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_BATCH = 2  # < 7 decisões de calib: o doador de algumas decisões está noutro lote
_INFORMATIVE = "close_return"
_OTHER = "rsi_14"


@pytest.fixture(scope="module")
def trained(tmp_path_factory: pytest.TempPathFactory) -> TrainedCheckpoint:
    return train_tiny_checkpoint(tmp_path_factory.mktemp("tft-attribution"))


def _donors(n: int) -> tuple[tuple[int, ...], ...]:
    return (tuple(reversed(range(n))), (*range(1, n), 0))


def _attribute(
    trained: TrainedCheckpoint,
    *,
    columns: Mapping[str, tuple[str, ...]] | None = None,
    donors: tuple[tuple[int, ...], ...] | None = None,
    rows: tuple[tuple[float, ...], ...] | None = None,
    trainer: PfTftTrainer | None = None,
    **overrides: Any,  # noqa: ANN401
) -> TftAttributionPrediction:
    decisions = trained.calib_decisions
    arguments: dict[str, Any] = {
        "checkpoint_path": trained.path,
        "expected_sha256": trained.sha256,
        "feature_names": trained.feature_names,
        "known_feature_names": trained.known_feature_names,
        "rows": rows if rows is not None else trained.rows,
        "target": trained.target,
        "decision_indices": decisions,
        "max_horizon": trained.max_horizon,
        "horizons": trained.horizons,
        "quantile_levels": trained.quantile_levels,
        "batch_size": _BATCH,
        "num_threads": trained.num_threads,
        "permuted_columns": columns if columns is not None else {"price": (_INFORMATIVE,)},
        "donors": donors if donors is not None else _donors(len(decisions)),
    }
    arguments.update(overrides)
    return (trainer or PfTftTrainer()).predict_attribution_from_checkpoint(**arguments)


def _grid_prediction(trained: TrainedCheckpoint) -> Any:  # noqa: ANN401
    return PfTftTrainer().predict_from_checkpoint(
        checkpoint_path=trained.path,
        expected_sha256=trained.sha256,
        feature_names=trained.feature_names,
        known_feature_names=trained.known_feature_names,
        rows=trained.rows,
        target=trained.target,
        decision_indices=trained.calib_decisions,
        max_horizon=trained.max_horizon,
        horizons=trained.horizons,
        quantile_levels=trained.quantile_levels,
        batch_size=_BATCH,
        num_threads=trained.num_threads,
    )


def test_identity_equals_predict_from_checkpoint_value_by_value(
    trained: TrainedCheckpoint,
) -> None:
    attribution = _attribute(trained)
    reference = _grid_prediction(trained)
    assert attribution.identity == reference.grids
    assert attribution.normalizer_center == reference.normalizer_center
    assert attribution.normalizer_scale == reference.normalizer_scale


def test_identity_permutation_reproduces_the_identity(trained: TrainedCheckpoint) -> None:
    n = len(trained.calib_decisions)
    attribution = _attribute(trained, donors=(tuple(range(n)),))
    assert attribution.permuted[("price", 1)] == attribution.identity


def _captured_loaders(
    trained: TrainedCheckpoint, monkeypatch: pytest.MonkeyPatch, donors: tuple[tuple[int, ...], ...]
) -> list[Any]:
    original = PfTftTrainer._emit
    loaders: list[Any] = []

    def spy(**kwargs: Any) -> Any:  # noqa: ANN401
        loaders.append(kwargs["prediction_dataset"])
        return original(**kwargs)

    monkeypatch.setattr(PfTftTrainer, "_emit", staticmethod(spy))
    _attribute(trained, donors=donors)
    return loaders


def _batches(loader: Any) -> list[dict[str, torch.Tensor]]:  # noqa: ANN401
    return [x for x, _ in loader]


def _sample_by_decision(batches: list[dict[str, torch.Tensor]]) -> dict[int, tuple[int, int]]:
    """Decisão → (lote, posição) da amostra de decodificador mais longo."""
    best: dict[int, tuple[int, int, int]] = {}
    for b, x in enumerate(batches):
        for i, (time_idx, length) in enumerate(
            zip(x["decoder_time_idx"][:, 0].tolist(), x["decoder_lengths"].tolist(), strict=True)
        ):
            decision = int(time_idx) - 1
            if decision not in best or length > best[decision][2]:
                best[decision] = (b, i, length)
    return {d: (b, i) for d, (b, i, _) in best.items()}


def test_donor_in_another_batch_gets_the_donor_block(
    trained: TrainedCheckpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    decisions = trained.calib_decisions
    permutation = tuple(reversed(range(len(decisions))))
    identity_loader, permuted_loader = _captured_loaders(trained, monkeypatch, (permutation,))
    identity, permuted = _batches(identity_loader), _batches(permuted_loader)
    column = list(identity_loader.dataset.reals).index(_INFORMATIVE)
    where = _sample_by_decision(identity)

    swapped_elsewhere = False
    for b, x in enumerate(permuted):
        for i, time_idx in enumerate(x["decoder_time_idx"][:, 0].tolist()):
            decision = int(time_idx) - 1
            if decision not in decisions:
                continue
            donor = decisions[permutation[decisions.index(decision)]]
            db, di = where[donor]
            length = int(x["encoder_lengths"][i])
            expected = identity[db]["encoder_cont"][di, :length, column]
            assert torch.equal(x["encoder_cont"][i, :length, column], expected)
            swapped_elsewhere |= donor != decision and db != b
    assert swapped_elsewhere


def test_non_permuted_columns_and_decoder_bit_identical(
    trained: TrainedCheckpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    decisions = trained.calib_decisions
    identity_loader, permuted_loader = _captured_loaders(
        trained, monkeypatch, (tuple(reversed(range(len(decisions)))),)
    )
    reals = list(identity_loader.dataset.reals)
    others = [j for j, name in enumerate(reals) if name != _INFORMATIVE]
    for ident, perm in zip(_batches(identity_loader), _batches(permuted_loader), strict=True):
        assert torch.equal(ident["encoder_cont"][:, :, others], perm["encoder_cont"][:, :, others])
        assert torch.equal(ident["decoder_cont"], perm["decoder_cont"])
        assert torch.equal(ident["decoder_time_idx"], perm["decoder_time_idx"])


def test_constant_family_swap_changes_nothing(trained: TrainedCheckpoint) -> None:
    j = trained.feature_names.index(_OTHER)
    constant = tuple(tuple(50.0 if k == j else v for k, v in enumerate(r)) for r in trained.rows)
    attribution = _attribute(trained, columns={"technical": (_OTHER,)}, rows=constant)
    for k in (1, 2):
        assert attribution.permuted[("technical", k)] == attribution.identity


def test_informative_family_swap_changes_the_grid(trained: TrainedCheckpoint) -> None:
    attribution = _attribute(trained)
    assert attribution.permuted[("price", 1)] != attribution.identity


def test_vsn_weights_sum_to_one_per_decision_over_encoder_variables(
    trained: TrainedCheckpoint,
) -> None:
    attribution = _attribute(trained)
    model = TemporalFusionTransformer.load_from_checkpoint(
        io.BytesIO(Path(trained.path).read_bytes())
    )
    assert set(attribution.encoder_weights) == set(trained.calib_decisions)
    for weights in attribution.encoder_weights.values():
        assert list(weights) == list(model.encoder_variables)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)
        assert all(value >= 0 for value in weights.values())


def test_known_family_column_raises_family_feature_known(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    known = train_tiny_checkpoint_with_known_family_column(tmp_path_factory.mktemp("known"))
    emitted: list[object] = []
    monkeypatch.setattr(
        PfTftTrainer, "_emit", staticmethod(lambda **kwargs: emitted.append(kwargs) or {})
    )
    with pytest.raises(FamilyFeatureKnownError, match=KNOWN_FAMILY_COLUMN):
        _attribute(known, columns={"technical": (KNOWN_FAMILY_COLUMN,)})
    assert emitted == []


def test_family_column_absent_from_unknown_reals_raises(trained: TrainedCheckpoint) -> None:
    with pytest.raises(FamilyFeatureKnownError, match="not_a_column"):
        _attribute(trained, columns={"price": ("not_a_column",)})


def test_encoder_length_mismatch_refused() -> None:
    encoder_cont = torch.zeros((3, 12, 4))
    lengths = torch.tensor([12, 11, 12])
    with pytest.raises(ValueError, match="encoder lengths differ"):
        donor_blocks(encoder_cont, lengths, {40: 0, 41: 1, 42: 2}, (40, 41, 42), {"f": (2,)})
    with pytest.raises(ValueError, match="without a prediction sample"):
        donor_blocks(encoder_cont, lengths, {40: 0, 41: 1}, (40, 41, 42), {"f": (2,)})


def test_wrong_sha_raises_before_load(
    trained: TrainedCheckpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    def never(*_: object, **__: object) -> None:
        raise AssertionError("the loader must not run")

    monkeypatch.setattr(module.TemporalFusionTransformer, "load_from_checkpoint", never)
    with pytest.raises(ArtifactChangedError):
        _attribute(trained, expected_sha256="0" * 64)


def test_settings_report_the_accelerator(trained: TrainedCheckpoint) -> None:
    attribution = _attribute(trained)
    assert attribution.settings["accelerator"] == "cpu"
    assert attribution.settings["batch_size"] == str(_BATCH)
