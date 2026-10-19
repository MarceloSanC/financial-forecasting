"""Contrato do port `TftCheckpointPredictor` (Stage 7.1, C4/C10; concept §4).

A fixture devolve um `_Leg`: o predictor e um checkpoint já gravado — caminho,
sha256 e as entradas com que foi treinado (reais, painel, `max_horizon`, níveis)
mais uma faixa válida de decisões. Perna `fake`: checkpoint registrado no
`InMemoryTftCheckpointPredictor`. Perna `real` (`slow`): `PfTftTrainer` sobre um
checkpoint treinado de verdade uma vez por módulo (`_tft_checkpoint_fixture`),
com a faixa de calib da geometria.

Prova: sha256 esperado errado → `ArtifactChangedError` (C10); uma entrada por
decisão pedida x horizonte; faixa não contígua → `ValueError`; entradas
declaradas diferentes (níveis, reais conhecidas, decodificador) →
`CheckpointMismatchError` (C4).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from financial_forecasting.features.modeling.adapters.out.pytorch_forecasting.pf_tft_trainer import (  # noqa: E501
    PfTftTrainer,
)
from financial_forecasting.features.modeling.application.ports.out.tft_checkpoint_predictor import (
    SETTINGS_KEYS,
    ArtifactChangedError,
    CheckpointMismatchError,
    FamilyFeatureKnownError,
    TftAttributionPrediction,
    TftCheckpointPrediction,
    TftCheckpointPredictor,
)
from tests.contract.features.modeling._tft_checkpoint_fixture import (
    TrainedCheckpoint,
    train_tiny_checkpoint,
)
from tests.fakes.features.modeling.in_memory_tft_checkpoint_predictor import (
    FakeCheckpoint,
    InMemoryTftCheckpointPredictor,
)


@dataclass(frozen=True)
class _Leg:
    predictor: TftCheckpointPredictor
    checkpoint_path: str
    sha256: str
    feature_names: tuple[str, ...]
    known_feature_names: tuple[str, ...]
    rows: tuple[tuple[float, ...], ...]
    target: tuple[float, ...]
    decisions: tuple[int, ...]
    max_horizon: int
    horizons: tuple[int, ...]
    quantile_levels: tuple[float, ...]
    # Faixa que encosta no fim do painel: a penúltima decisão só tem o horizonte 1
    # e a última não tem nenhum (I16 — regra de emissão na cauda).
    tail_decisions: tuple[int, ...]

    def predict(self, **overrides: object) -> TftCheckpointPrediction:
        arguments: dict[str, object] = {
            "checkpoint_path": self.checkpoint_path,
            "expected_sha256": self.sha256,
            "feature_names": self.feature_names,
            "known_feature_names": self.known_feature_names,
            "rows": self.rows,
            "target": self.target,
            "decision_indices": self.decisions,
            "max_horizon": self.max_horizon,
            "horizons": self.horizons,
            "quantile_levels": self.quantile_levels,
            "batch_size": 8,
            "num_threads": 1,
        }
        arguments.update(overrides)
        return self.predictor.predict_from_checkpoint(**arguments)  # type: ignore[arg-type]


def _fake_leg() -> _Leg:
    features = ("f_unknown_a", "f_unknown_b", "day_of_week")
    known = ("day_of_week",)
    levels = (0.1, 0.5, 0.9)
    n_rows = 40
    predictor = InMemoryTftCheckpointPredictor()
    path = "/artifacts/tft/run-0/best.ckpt"
    sha = "a" * 64
    predictor.register(
        path,
        FakeCheckpoint(
            sha256=sha,
            feature_names=features,
            known_feature_names=known,
            max_horizon=2,
            quantile_levels=levels,
        ),
    )
    return _Leg(
        predictor=predictor,
        checkpoint_path=path,
        sha256=sha,
        feature_names=features,
        known_feature_names=known,
        rows=tuple(tuple(float(i + j) for j in range(len(features))) for i in range(n_rows)),
        target=tuple(i / 1000.0 for i in range(n_rows)),
        decisions=(30, 31, 32, 33),
        max_horizon=2,
        horizons=(1, 2),
        quantile_levels=levels,
        tail_decisions=(n_rows - 3, n_rows - 2, n_rows - 1),
    )


def _real_leg(trained: TrainedCheckpoint) -> _Leg:
    return _Leg(
        predictor=PfTftTrainer(),
        checkpoint_path=trained.path,
        sha256=trained.sha256,
        feature_names=trained.feature_names,
        known_feature_names=trained.known_feature_names,
        rows=trained.rows,
        target=trained.target,
        decisions=trained.calib_decisions,
        max_horizon=trained.max_horizon,
        horizons=trained.horizons,
        quantile_levels=trained.quantile_levels,
        tail_decisions=trained.test_decisions,
    )


@pytest.fixture(scope="module")
def trained_checkpoint(tmp_path_factory: pytest.TempPathFactory) -> TrainedCheckpoint:
    return train_tiny_checkpoint(tmp_path_factory.mktemp("tft-checkpoint-contract"))


@pytest.fixture(params=["fake", pytest.param("real", marks=pytest.mark.slow)])
def leg(request: pytest.FixtureRequest) -> _Leg:
    if request.param == "fake":
        return _fake_leg()
    return _real_leg(request.getfixturevalue("trained_checkpoint"))


@pytest.mark.contract
def test_wrong_expected_sha256_raises_artifact_changed(leg: _Leg) -> None:
    with pytest.raises(ArtifactChangedError, match="C10"):
        leg.predict(expected_sha256="0" * 64)


@pytest.mark.contract
def test_emits_one_entry_per_requested_decision_and_horizon(leg: _Leg) -> None:
    prediction = leg.predict()

    assert sorted(prediction.grids) == list(leg.decisions)
    for by_horizon in prediction.grids.values():
        assert sorted(by_horizon) == list(leg.horizons)
        assert all(len(grid) == len(leg.quantile_levels) for grid in by_horizon.values())
    assert prediction.normalizer_scale > 0
    assert prediction.settings["batch_size"] == "8"
    assert prediction.settings["num_threads"] == "1"


@pytest.mark.contract
def test_settings_have_exactly_the_declared_keys(leg: _Leg) -> None:
    settings = leg.predict(batch_size=4, num_threads=2).settings

    assert sorted(settings) == sorted(SETTINGS_KEYS)
    assert settings["batch_size"] == "4"
    assert settings["num_threads"] == "2"
    assert settings["num_workers"] == "0"
    assert settings["accelerator"] == "cpu"
    assert settings["deterministic_algorithms"] == "false"
    assert all(isinstance(value, str) and value for value in settings.values())


@pytest.mark.contract
def test_tail_decisions_omit_horizons_beyond_the_panel(leg: _Leg) -> None:
    """I16 na cauda: horizonte além do fim é omitido; decisão sem horizonte some."""
    last = len(leg.target) - 1
    expected = {
        decision: [h for h in leg.horizons if decision + h <= last]
        for decision in leg.tail_decisions
    }
    assert any(len(hs) == len(leg.horizons) for hs in expected.values())
    assert any(0 < len(hs) < len(leg.horizons) for hs in expected.values())
    assert any(not hs for hs in expected.values())

    prediction = leg.predict(decision_indices=leg.tail_decisions)

    assert sorted(prediction.grids) == sorted(d for d, hs in expected.items() if hs)
    for decision, horizons in expected.items():
        if horizons:
            assert sorted(prediction.grids[decision]) == horizons


@pytest.mark.contract
def test_same_input_gives_the_same_grids(leg: _Leg) -> None:
    assert leg.predict().grids == leg.predict().grids


@pytest.mark.contract
def test_non_contiguous_decisions_raise_value_error(leg: _Leg) -> None:
    first, *_, last = leg.decisions

    with pytest.raises(ValueError, match="contiguous"):
        leg.predict(decision_indices=(first, last))


@pytest.mark.contract
def test_empty_decisions_raise_value_error(leg: _Leg) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        leg.predict(decision_indices=())


@pytest.mark.contract
@pytest.mark.parametrize(
    "mutation",
    ["levels", "known", "max_horizon"],
)
def test_declared_inputs_mismatch_raises_checkpoint_mismatch(leg: _Leg, mutation: str) -> None:
    by_mutation: dict[str, dict[str, object]] = {
        "levels": {"quantile_levels": (0.2, 0.5, 0.8)},
        "known": {"known_feature_names": ()},
        "max_horizon": {"max_horizon": leg.max_horizon + 1},
    }
    overrides = by_mutation[mutation]

    with pytest.raises(CheckpointMismatchError, match="C4"):
        leg.predict(**overrides)


@pytest.mark.contract
def test_leg_fixture_is_consistent(leg: _Leg) -> None:
    """Sanidade da fixture: a faixa pedida cabe no painel com todos os horizontes."""
    assert max(leg.decisions) + max(leg.horizons) <= len(leg.target) - 1
    assert list(leg.decisions) == list(range(leg.decisions[0], leg.decisions[-1] + 1))


# -- Stage 7.3, Task 11: predição de atribuição (identidade, permutadas, VSN) -----------


def _family_column(leg: _Leg) -> str:
    """A primeira real desconhecida do checkpoint: a coluna da família de teste."""
    return next(name for name in leg.feature_names if name not in leg.known_feature_names)


def _attribution(leg: _Leg, **overrides: object) -> TftAttributionPrediction:
    n = len(leg.decisions)
    arguments: dict[str, object] = {
        "checkpoint_path": leg.checkpoint_path,
        "expected_sha256": leg.sha256,
        "feature_names": leg.feature_names,
        "known_feature_names": leg.known_feature_names,
        "rows": leg.rows,
        "target": leg.target,
        "decision_indices": leg.decisions,
        "max_horizon": leg.max_horizon,
        "horizons": leg.horizons,
        "quantile_levels": leg.quantile_levels,
        "batch_size": 8,
        "num_threads": 1,
        "permuted_columns": {"fam": (_family_column(leg),)},
        "donors": (tuple(reversed(range(n))), (*range(1, n), 0)),
    }
    arguments.update(overrides)
    return leg.predictor.predict_attribution_from_checkpoint(**arguments)  # type: ignore[arg-type]


@pytest.mark.contract
def test_attribution_identity_matches_the_grid_method(leg: _Leg) -> None:
    attribution = _attribution(leg)
    assert attribution.identity == leg.predict().grids
    assert set(attribution.settings) == set(SETTINGS_KEYS)


@pytest.mark.contract
@pytest.mark.parametrize(
    "donors",
    [
        pytest.param(((0, 0, 1, 2, 3, 4, 5),), id="repeated"),
        pytest.param(((0, 1),), id="short"),
        pytest.param((), id="empty"),
    ],
)
def test_donors_that_are_not_permutations_refused(leg: _Leg, donors: object) -> None:
    with pytest.raises(ValueError, match="permutation"):
        _attribution(leg, donors=donors)


@pytest.mark.contract
def test_permuted_keys_are_family_and_one_based_k(leg: _Leg) -> None:
    attribution = _attribution(leg)
    assert set(attribution.permuted) == {("fam", 1), ("fam", 2)}
    for grids in attribution.permuted.values():
        assert set(grids) == set(attribution.identity)
    assert set(attribution.encoder_weights) == set(leg.decisions)
    for weights in attribution.encoder_weights.values():
        assert sum(weights.values()) == pytest.approx(1.0)


@pytest.mark.contract
def test_attribution_wrong_sha_raises(leg: _Leg) -> None:
    with pytest.raises(ArtifactChangedError):
        _attribution(leg, expected_sha256="0" * 64)


@pytest.mark.contract
def test_attribution_known_family_column_raises(leg: _Leg) -> None:
    with pytest.raises(FamilyFeatureKnownError):
        _attribution(leg, permuted_columns={"fam": (leg.known_feature_names[0],)})
