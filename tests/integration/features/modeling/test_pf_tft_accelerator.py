"""Device por instância do `PfTftTrainer` (Stage 7.3, Task 03; CA5, I1, I5; ADR 7.3.0004).

O `accelerator` da instância tem de chegar aos três pontos em que o Lightning escolhe o
hardware: o `Trainer` do `fit`, o `Trainer` interno do `predict` no `_emit` (pelo
`trainer_kwargs`) e a chave `accelerator` dos `settings` da predição a partir do
checkpoint. Os kwargs são capturados por `monkeypatch`, sem GPU: o `Trainer` capturado
ergue um sentinela antes de alocar, e o `predict` capturado grava o `trainer_kwargs` e
roda em CPU. Só o smoke de GPU treina de verdade fora da CPU, e é pulado sem GPU.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
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
from tests.contract.features.modeling._tft_checkpoint_fixture import (
    TrainedCheckpoint,
    train_tiny_checkpoint,
)
from tests.contract.features.modeling.test_tft_trainer_contract import (
    _EARLY_STOP,
    _FEATURES,
    _HORIZONS,
    _KNOWN,
    _LEVELS,
    _MAX_HORIZON,
    _PARAMS,
    _TEST,
    _TRAIN,
    _panel,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]


class _TrainerBuilt(Exception):  # sentinela, não erro de domínio
    """O `Trainer` capturado ergue isto antes de alocar qualquer coisa."""


@pytest.fixture(scope="module")
def trained(tmp_path_factory: pytest.TempPathFactory) -> TrainedCheckpoint:
    return train_tiny_checkpoint(tmp_path_factory.mktemp("tft-accelerator"))


def _train_kwargs(tmp_path: Path) -> dict[str, Any]:
    rows, target = _panel()
    return {
        "params": _PARAMS,
        "feature_names": _FEATURES,
        "known_feature_names": _KNOWN,
        "rows": rows,
        "target": target,
        "train_decision_indices": _TRAIN,
        "early_stop_decision_indices": _EARLY_STOP,
        "test_decision_indices": _TEST,
        "max_horizon": _MAX_HORIZON,
        "horizons": _HORIZONS,
        "quantile_levels": _LEVELS,
        "artifact_dir": str(tmp_path / "ckpt"),
    }


def _fit_accelerator(trainer: PfTftTrainer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """O `accelerator` com que o `fit` constrói o `Trainer` do Lightning."""
    captured: list[dict[str, Any]] = []

    def trainer_spy(**kwargs: Any) -> Any:  # noqa: ANN401
        captured.append(kwargs)
        raise _TrainerBuilt

    monkeypatch.setattr(module.pl, "Trainer", trainer_spy)
    with pytest.raises(_TrainerBuilt):
        trainer.train_and_predict(**_train_kwargs(tmp_path))
    assert len(captured) == 1
    return str(captured[0]["accelerator"])


def _train_emit_accelerator(
    trainer: PfTftTrainer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> str:
    """O `accelerator` que o `train_and_predict` passa ao `_emit` (sem treinar)."""
    seen: list[str] = []

    def fit_stub(**_: Any) -> Any:  # noqa: ANN401
        return SimpleNamespace(
            model=object(),
            val_loss_by_epoch=(0.5,),
            best_epoch=0,
            best_val_loss=0.5,
            artifact_path="",
        )

    def emit_spy(**kwargs: Any) -> Any:  # noqa: ANN401
        seen.append(kwargs["accelerator"])
        return {}

    monkeypatch.setattr(trainer, "fit", fit_stub)
    monkeypatch.setattr(PfTftTrainer, "_emit", staticmethod(emit_spy))
    trainer.train_and_predict(**_train_kwargs(tmp_path))
    assert len(seen) == 1
    return seen[0]


def _checkpoint_prediction(
    trainer: PfTftTrainer, trained: TrainedCheckpoint, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """`trainer_kwargs` do `predict` interno e os `settings`; o `predict` roda em CPU."""
    original = TemporalFusionTransformer.predict
    seen: list[dict[str, Any]] = []

    def predict_spy(self: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        seen.append(dict(kwargs["trainer_kwargs"]))
        kwargs["trainer_kwargs"] = {**kwargs["trainer_kwargs"], "accelerator": "cpu"}
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TemporalFusionTransformer, "predict", predict_spy)
    prediction = trainer.predict_from_checkpoint(
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
        batch_size=trained.batch_size,
        num_threads=trained.num_threads,
    )
    return seen, dict(prediction.settings)


def test_default_instance_uses_cpu_in_fit_emit_and_checkpoint_prediction(
    trained: TrainedCheckpoint, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trainer = PfTftTrainer()
    assert trainer.accelerator == "cpu"
    with monkeypatch.context() as patch:
        assert _fit_accelerator(trainer, tmp_path / "fit", patch) == "cpu"
    with monkeypatch.context() as patch:
        assert _train_emit_accelerator(trainer, tmp_path / "emit", patch) == "cpu"
    seen, _ = _checkpoint_prediction(trainer, trained, monkeypatch)
    assert [kwargs["accelerator"] for kwargs in seen] == ["cpu"]


def test_gpu_instance_passes_gpu_everywhere(
    trained: TrainedCheckpoint, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trainer = PfTftTrainer(accelerator="gpu")
    with monkeypatch.context() as patch:
        assert _fit_accelerator(trainer, tmp_path / "fit", patch) == "gpu"
    with monkeypatch.context() as patch:
        assert _train_emit_accelerator(trainer, tmp_path / "emit", patch) == "gpu"
    seen, _ = _checkpoint_prediction(trainer, trained, monkeypatch)
    assert [kwargs["accelerator"] for kwargs in seen] == ["gpu"]


@pytest.mark.parametrize("accelerator", ["cpu", "gpu"])
def test_settings_report_the_instance_accelerator(
    trained: TrainedCheckpoint, monkeypatch: pytest.MonkeyPatch, accelerator: str
) -> None:
    _, settings = _checkpoint_prediction(
        PfTftTrainer(accelerator=accelerator), trained, monkeypatch
    )
    assert settings["accelerator"] == accelerator


@pytest.mark.parametrize("accelerator", ["", "auto", "cuda", "rocm", "mps"])
def test_accelerator_outside_cpu_and_gpu_refused(accelerator: str) -> None:
    with pytest.raises(ValueError, match="accelerator must be one of"):
        PfTftTrainer(accelerator=accelerator)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="sem GPU visível ao torch")
def test_gpu_fit_smoke(tmp_path: Path) -> None:
    kwargs = _train_kwargs(tmp_path)
    kwargs["params"] = replace(_PARAMS, max_epochs=1)
    result = PfTftTrainer(accelerator="gpu").train_and_predict(**kwargs)
    assert result.grids
