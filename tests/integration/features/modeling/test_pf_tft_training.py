"""Integração — treino do TFT: parada antecipada, histórico e checkpoint.

Treina de verdade em CPU (sem `skipif` — ADR 5.4.0003), com modelo mínimo e
poucas épocas. Prova:

- **A5 (parte):** `best_epoch == argmin(val_loss_by_epoch)`,
  `len(val_loss_by_epoch)` == épocas executadas (sem a passagem de sanidade —
  D11), e `artifact_path` existente em disco;
- **A4(a):** mutar o alvo em `calib` e em `test` deixa `best_epoch` e o
  histórico IDÊNTICOS. A invariância é estrutural: o quadro do monitor termina
  antes de `calib` (Task 07), então essas sessões nem chegam ao ajuste;
- **A9 (parte real):** duas chamadas idênticas no mesmo processo devolvem o
  mesmo histórico;
- **C10:** histórico sem valor finito e caminho de checkpoint vazio erguem —
  via os helpers puros, que dão gatilho determinístico sem depender de um treino
  divergir de fato;
- **fit-only:** nenhum checkpoint é escrito (a varredura roda dezenas de
  treinos e não pode deixar arquivos órfãos).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from financial_forecasting.features.modeling.adapters.out.pytorch_forecasting.pf_tft_trainer import (  # noqa: E501
    PfTftTrainer,
    _require_checkpoint,
    _select_best_epoch,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)

pytestmark = pytest.mark.integration

_PANEL = 54
_ENCODER_LENGTH = 12
_MAX_HORIZON = 2
_HORIZONS = (1, 2)
_TRAIN = tuple(range(30))
_EARLY_STOP = tuple(range(33, 38))
_TEST = tuple(range(49, 54))
_FEATURES = ("close_return", "rsi_14", "day_of_week", "month")
_KNOWN = ("day_of_week", "month")
_LEVELS = (0.1, 0.5, 0.9)
_CALIB = tuple(range(41, 46))
_MAX_EPOCHS = 2

_PARAMS = TftTrainingParams(
    seed=7,
    max_encoder_length=_ENCODER_LENGTH,
    hidden_size=4,
    attention_head_size=1,
    hidden_continuous_size=2,
    max_epochs=_MAX_EPOCHS,
    patience=2,
    batch_size=8,
    learning_rate=0.01,
)


def _panel(mutated: tuple[int, ...] = ()) -> tuple[list[list[float]], list[float]]:
    rows = [
        [0.01 * index, 50.0 + index, float(index % 5), float(index % 12 + 1)]
        for index in range(_PANEL)
    ]
    target = [
        (100.0 if index in mutated else 0.0) + 0.001 * index for index in range(_PANEL)
    ]
    return rows, target


def _datasets(trainer: PfTftTrainer, mutated: tuple[int, ...] = ()) -> object:
    rows, target = _panel(mutated)
    return trainer.build_datasets(
        params=_PARAMS,
        feature_names=_FEATURES,
        known_feature_names=_KNOWN,
        rows=rows,
        target=target,
        train_decision_indices=_TRAIN,
        early_stop_decision_indices=_EARLY_STOP,
        test_decision_indices=_TEST,
        max_horizon=_MAX_HORIZON,
        horizons=_HORIZONS,
    )


def _fit(tmp_path: Path, *, mutated: tuple[int, ...] = (), write: bool = True) -> object:
    trainer = PfTftTrainer()
    return trainer.fit(
        datasets=_datasets(trainer, mutated),
        params=_PARAMS,
        quantile_levels=_LEVELS,
        artifact_dir=str(tmp_path / "ckpt"),
        write_checkpoint=write,
    )


class TestStoppingMechanism:
    def test_best_epoch_is_the_argmin_of_the_history(self, tmp_path: Path) -> None:
        result = _fit(tmp_path)

        assert result.val_loss_by_epoch
        assert result.best_epoch == result.val_loss_by_epoch.index(
            min(result.val_loss_by_epoch)
        )
        assert result.best_val_loss == min(result.val_loss_by_epoch)

    def test_history_has_one_entry_per_executed_epoch(self, tmp_path: Path) -> None:
        """Sem a guarda de sanidade o histórico ganharia uma entrada extra (D11)."""
        result = _fit(tmp_path)

        assert len(result.val_loss_by_epoch) == _MAX_EPOCHS

    def test_checkpoint_exists_on_disk(self, tmp_path: Path) -> None:
        result = _fit(tmp_path)

        assert result.artifact_path
        assert Path(result.artifact_path).is_file()


class TestAntiLeakage:
    """A4(a) — `calib` e `test` não alcançam o ajuste nem o monitor."""

    def test_mutating_calibration_and_test_targets_changes_nothing(
        self, tmp_path: Path
    ) -> None:
        baseline = _fit(tmp_path / "a")
        mutated = _fit(tmp_path / "b", mutated=(*_CALIB, *_TEST))

        assert mutated.val_loss_by_epoch == baseline.val_loss_by_epoch
        assert mutated.best_epoch == baseline.best_epoch


class TestDeterminism:
    """A9 (perna real) — a semente é reaplicada a CADA chamada."""

    def test_two_identical_fits_agree(self, tmp_path: Path) -> None:
        first = _fit(tmp_path / "a")
        second = _fit(tmp_path / "b")

        assert first.val_loss_by_epoch == second.val_loss_by_epoch
        assert first.best_epoch == second.best_epoch


class TestFitOnly:
    def test_no_checkpoint_is_written(self, tmp_path: Path) -> None:
        result = _fit(tmp_path, write=False)

        assert result.artifact_path == ""
        assert not (tmp_path / "ckpt").exists()
        assert result.val_loss_by_epoch  # a perda de validação continua reportada


class TestC10:
    """Gatilho determinístico via helpers puros — sem depender de divergir."""

    def test_history_without_any_finite_loss_raises(self) -> None:
        with pytest.raises(ValueError, match="C10"):
            _select_best_epoch([math.nan, math.inf * 0])

    def test_empty_checkpoint_path_raises(self) -> None:
        with pytest.raises(ValueError, match="C10"):
            _require_checkpoint("")

    def test_earliest_epoch_wins_ties(self) -> None:
        assert _select_best_epoch([0.5, 0.5, 0.9]) == 0

    def test_non_finite_entries_are_skipped(self) -> None:
        assert _select_best_epoch([math.nan, 0.3, 0.7]) == 1
