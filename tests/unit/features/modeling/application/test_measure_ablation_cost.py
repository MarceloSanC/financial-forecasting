"""`MeasureAblationCost` com fakes (Stage 7.3, Task 09; CA6, I9 parte; concept D8).

O treinador fake devolve um histórico de validação programável; o relógio fake avança
um intervalo fixo por leitura. O dataset é o de `test_train_tft.py`.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
    TftTrainingResult,
)
from financial_forecasting.features.modeling.application.use_cases.measure_ablation_cost import (
    MeasureAblationCost,
    MeasureAblationCostCommand,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    load_tft_panel,
)
from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
    WalkForwardSplitter,
)
from financial_forecasting.features.modeling.domain.value_objects.cohort_geometry import (
    CohortGeometry,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.services.trading_calendar import TradingCalendar
from financial_forecasting.shared.domain.value_objects.trading_sessions import TradingSessions
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)
from tests.fakes.features.modeling.in_memory_tft_trainer import InMemoryTftTrainer
from tests.unit.features.modeling.application.test_ablation_cohort_spec import (
    _spec as _ablation_spec,
)
from tests.unit.features.modeling.application.test_cohort_spec import _spec as _cohort_spec
from tests.unit.features.modeling.application.test_train_tft import (
    _SCOPE,
    _SESSIONS,
    _seeded_store,
)

pytestmark = pytest.mark.unit

_GEOMETRY = CohortGeometry(n_folds=2, test_size=3, val_size=5, calib_size=5, embargo=1)
_MAX_EPOCHS = 20
_WALL = 12.0
_HISTORY = (0.9, 0.7, 0.8, 0.75)
_TORCH = "2.13.0+rocm6.4"


class _StepClock:
    """Cada `now()` avança `_WALL` segundos: início e fim do treino distam `_WALL`."""

    def __init__(self) -> None:
        self._now = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        current = self._now
        self._now += timedelta(seconds=_WALL)
        return current


class _HistoryTrainer(InMemoryTftTrainer):
    """Fake com `val_loss_by_epoch` programado (o `best_epoch` é o argmin)."""

    def train_and_predict(self, **kwargs: Any) -> TftTrainingResult:  # noqa: ANN401
        result = super().train_and_predict(**kwargs)
        best = min(range(len(_HISTORY)), key=_HISTORY.__getitem__)
        return replace(
            result,
            val_loss_by_epoch=_HISTORY,
            best_epoch=best,
            best_val_loss=_HISTORY[best],
        )


class _ForbiddenStore:
    """Store que só aceita leitura do dataset; qualquer escrita reprova."""

    def __init__(self) -> None:
        self._inner = _seeded_store()
        self.reads: list[tuple[str, str]] = []

    def read(self, *, layer: str, table: str, filters: Any = None) -> Any:  # noqa: ANN401
        self.reads.append((layer, table))
        return self._inner.read(layer=layer, table=table, filters=filters)

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        raise AssertionError(f"pilot touched store.{name}")


def _base() -> Any:  # noqa: ANN401
    return _cohort_spec(
        asset_id=_SCOPE.asset_id,
        horizons=(1, 2),
        quantile_levels=(0.1, 0.5, 0.9),
        geometry=_GEOMETRY,
        tft_params=TftTrainingParams(seed=0, max_encoder_length=12, max_epochs=_MAX_EPOCHS),
    )


def _measure(tmp_path: Path) -> tuple[Any, _HistoryTrainer, _ForbiddenStore]:
    trainer = _HistoryTrainer()
    store = _ForbiddenStore()
    use_case = MeasureAblationCost(
        store=store,  # type: ignore[arg-type]
        splitter=WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=_SESSIONS))),
        trainer=trainer,
        probe=InMemoryRuntimeEnvironmentProbe.with_gpu(torch=_TORCH),
        clock=_StepClock(),  # type: ignore[arg-type]
        hasher=CanonicalJsonHasher(),
    )
    report = use_case(
        MeasureAblationCostCommand(
            spec=_ablation_spec(), base=_base(), pilot_dir=str(tmp_path / "pilot")
        )
    )
    return report, trainer, store


def test_pilot_uses_full_configuration_last_fold_seed_1(tmp_path: Path) -> None:
    report, trainer, _ = _measure(tmp_path)
    assert (report.configuration, report.seed, report.fold_index) == ("full", 1, 1)
    assert trainer.call_count == 1
    call = trainer.last_call
    assert call["params"].seed == 1
    assert call["params"].max_epochs == _MAX_EPOCHS
    # configuração full: o painel inteiro, sem família fora
    full = load_tft_panel(store=_seeded_store(), asset_id=_SCOPE.asset_id)
    assert call["feature_names"] == full.feature_names
    assert call["artifact_dir"] == str(tmp_path / "pilot")


@pytest.mark.parametrize("seeds", range(1, 11))
def test_ceiling_is_5_folds_s_max_epochs_seconds_per_epoch(tmp_path: Path, seeds: int) -> None:
    report, _, _ = _measure(tmp_path)
    per_epoch = _WALL / len(_HISTORY)
    assert report.seconds_per_epoch == pytest.approx(per_epoch)
    assert report.ceiling_seconds[seeds] == pytest.approx(
        5 * _GEOMETRY.n_folds * seeds * _MAX_EPOCHS * per_epoch
    )


def test_estimate_is_5_folds_s_wall_seconds_and_labelled_estimate(tmp_path: Path) -> None:
    report, _, _ = _measure(tmp_path)
    assert set(report.estimate_seconds) == set(range(1, 11))
    for seeds, value in report.estimate_seconds.items():
        assert value == pytest.approx(5 * _GEOMETRY.n_folds * seeds * _WALL)
    assert "estimate" in report.label
    assert "not a bound" in report.label
    assert report.estimate_seconds[10] < report.ceiling_seconds[10]


def test_report_fields(tmp_path: Path) -> None:
    report, _, _ = _measure(tmp_path)
    assert report.wall_seconds == pytest.approx(_WALL)
    assert report.epochs_run == len(_HISTORY)
    assert report.best_epoch == 1
    assert report.max_epochs == _MAX_EPOCHS
    assert report.device == "rocm"
    assert report.torch_build == _TORCH


def test_nothing_is_persisted(tmp_path: Path) -> None:
    _, _, store = _measure(tmp_path)
    assert store.reads == [("processed", "dataset_tft")]
    assert not (tmp_path / "silver").exists()
