"""Integração do `PfTftTrainer.predict_from_checkpoint` (Stage 7.1, Task 04; A2, I1/I3/I7, C4/C10).

Um treino real minúsculo por módulo (`_tft_checkpoint_fixture`, geometria do
contract test do trainer) e, sobre o checkpoint gravado:

- a grade de teste re-predita é IGUAL (`==`, mesmas chaves) à que o
  `train_and_predict` devolveu — mesma receita de dataset, mesmo `_emit`;
- independente do RNG global e do processo (subprocesso, grades por `float.hex`);
- decisões de calib emitem uma entrada por decisão x horizonte;
- sha256 errado nunca chama o loader; o loader recebe um objeto de arquivo com os
  bytes que foram hasheados (C10);
- entradas declaradas diferentes → `CheckpointMismatchError` (C4);
- threads e flag de algoritmos determinísticos: o pedido durante, o anterior depois;
- treino e checkpoint passam pela MESMA função de dataset e pelo MESMO `_emit`;
- `settings` registra os parâmetros da inferência.
"""

from __future__ import annotations

import hashlib
import io
import json
import platform
import subprocess
import sys
import textwrap
from collections.abc import Iterator, Mapping
from dataclasses import replace
from importlib import metadata
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
)
from financial_forecasting.features.modeling.application.ports.out.tft_checkpoint_predictor import (
    ArtifactChangedError,
    CheckpointMismatchError,
    TftCheckpointPrediction,
)
from financial_forecasting.features.modeling.domain.exceptions.backend import ModelTrainingError
from tests.contract.features.modeling._tft_checkpoint_fixture import (
    TrainedCheckpoint,
    train_tiny_checkpoint,
)
from tests.contract.features.modeling.test_tft_trainer_contract import (
    _EARLY_STOP,
    _PARAMS,
    _TRAIN,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_Grids = Mapping[int, Mapping[int, tuple[float, ...]]]


@pytest.fixture(scope="module")
def trained(tmp_path_factory: pytest.TempPathFactory) -> TrainedCheckpoint:
    return train_tiny_checkpoint(tmp_path_factory.mktemp("tft-checkpoint"))


def _predict(
    trained: TrainedCheckpoint,
    *,
    decisions: tuple[int, ...] | None = None,
    **overrides: object,
) -> TftCheckpointPrediction:
    arguments: dict[str, object] = {
        "checkpoint_path": trained.path,
        "expected_sha256": trained.sha256,
        "feature_names": trained.feature_names,
        "known_feature_names": trained.known_feature_names,
        "rows": trained.rows,
        "target": trained.target,
        "decision_indices": decisions if decisions is not None else trained.test_decisions,
        "max_horizon": trained.max_horizon,
        "horizons": trained.horizons,
        "quantile_levels": trained.quantile_levels,
        "batch_size": trained.batch_size,
        "num_threads": trained.num_threads,
    }
    arguments.update(overrides)
    return PfTftTrainer().predict_from_checkpoint(**arguments)  # type: ignore[arg-type]


def _plain(grids: _Grids) -> dict[int, dict[int, tuple[float, ...]]]:
    return {d: {h: tuple(v) for h, v in by_h.items()} for d, by_h in grids.items()}


def test_checkpoint_prediction_equals_train_and_predict_test_grid(
    trained: TrainedCheckpoint,
) -> None:
    prediction = _predict(trained)

    assert prediction.grids
    assert _plain(prediction.grids) == _plain(trained.test_grids)
    assert prediction.normalizer_center == trained.normalizer_center
    assert prediction.normalizer_scale == trained.normalizer_scale


def test_prediction_independent_of_global_rng(trained: TrainedCheckpoint) -> None:
    torch.manual_seed(1)
    first = _predict(trained, decisions=trained.calib_decisions)
    torch.manual_seed(2)
    second = _predict(trained, decisions=trained.calib_decisions)

    assert _plain(first.grids) == _plain(second.grids)


@pytest.mark.parametrize("partition", ["calib", "test"])
def test_prediction_in_subprocess_is_identical(trained: TrainedCheckpoint, partition: str) -> None:
    """Outro processo prediz o mesmo; no teste, o que o treino gravou (ADR 7.1.0003 item 7)."""
    decisions = trained.calib_decisions if partition == "calib" else trained.test_decisions
    payload = {
        "checkpoint_path": trained.path,
        "expected_sha256": trained.sha256,
        "feature_names": list(trained.feature_names),
        "known_feature_names": list(trained.known_feature_names),
        "rows": [[v.hex() for v in row] for row in trained.rows],
        "target": [v.hex() for v in trained.target],
        "decision_indices": list(decisions),
        "max_horizon": trained.max_horizon,
        "horizons": list(trained.horizons),
        "quantile_levels": list(trained.quantile_levels),
        "batch_size": trained.batch_size,
        "num_threads": trained.num_threads,
    }
    script = textwrap.dedent(
        f"""
        import importlib, json, sys
        payload = json.loads(sys.stdin.read())
        payload["rows"] = [[float.fromhex(v) for v in row] for row in payload["rows"]]
        payload["target"] = [float.fromhex(v) for v in payload["target"]]
        trainer = importlib.import_module({module.__name__!r}).PfTftTrainer()
        grids = trainer.predict_from_checkpoint(**payload).grids
        out = {{str(d): {{str(h): [v.hex() for v in g] for h, g in by_h.items()}}
                for d, by_h in grids.items()}}
        print("GRIDS=" + json.dumps(out, sort_keys=True))
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )

    [line] = [ln for ln in completed.stdout.splitlines() if ln.startswith("GRIDS=")]
    child = json.loads(line.removeprefix("GRIDS="))
    here = _predict(trained, decisions=decisions).grids
    expected = {
        str(d): {str(h): [v.hex() for v in g] for h, g in by_h.items()} for d, by_h in here.items()
    }
    assert child == expected
    if partition == "test":
        trained_grids = {
            str(d): {str(h): [v.hex() for v in g] for h, g in by_h.items()}
            for d, by_h in trained.test_grids.items()
        }
        assert child == trained_grids


def test_calib_decisions_emit_one_entry_per_decision_and_horizon(
    trained: TrainedCheckpoint,
) -> None:
    prediction = _predict(trained, decisions=trained.calib_decisions)

    assert sorted(prediction.grids) == list(trained.calib_decisions)
    for by_horizon in prediction.grids.values():
        assert sorted(by_horizon) == list(trained.horizons)
        assert all(len(grid) == len(trained.quantile_levels) for grid in by_horizon.values())


def test_wrong_sha_never_calls_the_loader(
    trained: TrainedCheckpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []

    def spy(*args: object, **kwargs: object) -> object:
        calls.append(args)
        raise AssertionError("loader must not be called")

    monkeypatch.setattr(TemporalFusionTransformer, "load_from_checkpoint", spy)

    with pytest.raises(ArtifactChangedError, match="C10"):
        _predict(trained, expected_sha256="0" * 64)

    assert calls == []


def test_loader_receives_the_hashed_bytes_as_file_object(
    trained: TrainedCheckpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = TemporalFusionTransformer.load_from_checkpoint
    received: list[object] = []

    def spy(source: object, *args: object, **kwargs: object) -> object:
        received.append(source)
        return original(source, *args, **kwargs)

    monkeypatch.setattr(TemporalFusionTransformer, "load_from_checkpoint", spy)

    _predict(trained, decisions=trained.calib_decisions)

    [source] = received
    assert not isinstance(source, (str, Path))
    assert isinstance(source, io.BytesIO)
    assert source.getvalue() == Path(trained.path).read_bytes()


@pytest.mark.parametrize(
    "overrides",
    [
        {"quantile_levels": (0.2, 0.5, 0.8)},
        {"known_feature_names": ("day_of_week",)},
        {"max_horizon": 3, "horizons": (1, 2)},
        # SÓ as desconhecidas mudam (conhecidas iguais): uma a menos e uma a mais.
        {"feature_names": ("close_return", "day_of_week", "month")},
        {"feature_names": ("close_return", "rsi_14", "extra_unknown", "day_of_week", "month")},
    ],
    ids=["levels", "known-reals", "decoder-length", "one-unknown-less", "one-unknown-more"],
)
def test_mismatched_levels_or_reals_raise_checkpoint_mismatch(
    trained: TrainedCheckpoint, overrides: dict[str, object]
) -> None:
    with pytest.raises(CheckpointMismatchError, match="C4"):
        _predict(trained, decisions=trained.calib_decisions, **overrides)


@pytest.fixture
def deterministic_on() -> Iterator[int]:
    """Estado "antes" não-default: 3 threads e algoritmos determinísticos ligados."""
    threads, flag = torch.get_num_threads(), torch.are_deterministic_algorithms_enabled()
    torch.set_num_threads(3)
    torch.use_deterministic_algorithms(True)
    try:
        yield 3
    finally:
        torch.set_num_threads(threads)
        torch.use_deterministic_algorithms(flag)


def test_threads_and_deterministic_flag_restored(
    trained: TrainedCheckpoint, monkeypatch: pytest.MonkeyPatch, deterministic_on: int
) -> None:
    original_emit = PfTftTrainer._emit
    during: list[tuple[int, bool]] = []

    def spy(**kwargs: Any) -> Any:  # noqa: ANN401
        during.append((torch.get_num_threads(), torch.are_deterministic_algorithms_enabled()))
        return original_emit(**kwargs)

    monkeypatch.setattr(PfTftTrainer, "_emit", staticmethod(spy))

    _predict(trained, decisions=trained.calib_decisions, num_threads=2)

    assert during == [(2, False)]
    assert torch.get_num_threads() == deterministic_on
    assert torch.are_deterministic_algorithms_enabled() is True


@pytest.mark.parametrize("damage", ["garbage", "truncated", "empty"])
def test_corrupted_checkpoint_with_matching_sha_raises_model_training_error(
    trained: TrainedCheckpoint, tmp_path: Path, damage: str
) -> None:
    """sha256 confere (os bytes são os pedidos), mas não são um checkpoint: falha da pilha
    traduzida em `ModelTrainingError`, com a original em `__cause__` (nunca crua)."""
    original = Path(trained.path).read_bytes()
    data = {
        "garbage": b"not a lightning checkpoint",
        "truncated": original[: len(original) // 2],
        "empty": b"",
    }[damage]
    corrupted = tmp_path / "epoch=0-step=1.ckpt"
    corrupted.write_bytes(data)

    with pytest.raises(ModelTrainingError, match="pytorch-forecasting/lightning failed") as info:
        _predict(
            trained,
            decisions=trained.calib_decisions,
            checkpoint_path=str(corrupted),
            expected_sha256=hashlib.sha256(data).hexdigest(),
        )

    assert info.value.__cause__ is not None


def test_train_and_checkpoint_paths_share_dataset_helper_and_emit(
    trained: TrainedCheckpoint, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_dataset = module._prediction_dataset
    original_emit = PfTftTrainer._emit
    dataset_calls: list[str] = []
    emit_calls: list[str] = []
    phase = ["train"]

    def dataset_spy(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        dataset_calls.append(phase[0])
        return original_dataset(*args, **kwargs)

    def emit_spy(**kwargs: Any) -> Any:  # noqa: ANN401
        emit_calls.append(phase[0])
        return original_emit(**kwargs)

    monkeypatch.setattr(module, "_prediction_dataset", dataset_spy)
    monkeypatch.setattr(PfTftTrainer, "_emit", staticmethod(emit_spy))

    PfTftTrainer().train_and_predict(
        params=replace(_PARAMS, max_epochs=1),
        feature_names=trained.feature_names,
        known_feature_names=trained.known_feature_names,
        rows=trained.rows,
        target=trained.target,
        train_decision_indices=_TRAIN,
        early_stop_decision_indices=_EARLY_STOP,
        test_decision_indices=trained.test_decisions,
        max_horizon=trained.max_horizon,
        horizons=trained.horizons,
        quantile_levels=trained.quantile_levels,
        artifact_dir=str(tmp_path / "ckpt"),
    )
    phase[0] = "checkpoint"
    _predict(trained, decisions=trained.calib_decisions)

    assert dataset_calls == ["train", "checkpoint"]
    assert emit_calls == ["train", "checkpoint"]


def test_settings_record_the_inference_parameters(trained: TrainedCheckpoint) -> None:
    prediction = _predict(trained, decisions=trained.calib_decisions, batch_size=4, num_threads=2)

    assert dict(prediction.settings) == {
        "batch_size": "4",
        "num_workers": "0",
        "accelerator": "cpu",
        "num_threads": "2",
        "deterministic_algorithms": "false",
        "cpu_capability": str(torch.backends.cpu.get_cpu_capability()),
        "platform": platform.platform(),
        "scikit-learn": metadata.version("scikit-learn"),
    }
