"""Unit test do use case `RunGbmSweep` com fakes (Stage 5.5, A5 / D13).

Prova: isolamento estrutural (nenhuma porta de persistência no construtor; zero
escritas no store); fit-only (nenhuma decisão de teste chega ao port); objetivo =
média entre horizontes da perda de early_stop do port; `phase='exploratory'` no
tracker; C9 quando todos os trials falham; C11 contra `GbmTrainingParams`; o
resultado traz a impressão digital do grid; grid único (prefixo sem valor cortado,
como nos treinadores).
"""

from __future__ import annotations

import inspect
import math
from datetime import UTC, date, datetime, timedelta
from statistics import fmean
from typing import Any

import pytest

from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    SearchDimension,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
    QuantileTrainingResult,
)
from financial_forecasting.features.modeling.application.use_cases.run_gbm_sweep import (
    RunGbmSweep,
    RunGbmSweepCommand,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    modeling_columns,
)
from financial_forecasting.features.modeling.domain.exceptions.backend import ModelTrainingError
from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
    WalkForwardSplitter,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import ScopeSpec
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.services.trading_calendar import TradingCalendar
from financial_forecasting.shared.domain.value_objects.trading_sessions import TradingSessions
from tests.fakes.features.modeling.in_memory_hyperparameter_search import (
    InMemoryHyperparameterSearch,
)
from tests.fakes.features.modeling.in_memory_quantile_model_trainer import (
    FakeQuantileModelTrainer,
)
from tests.fakes.shared.in_memory_experiment_tracker import FakeExperimentTracker
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

_FRIDAY = 4
_N_SESSIONS = 120
_LEVELS = (0.1, 0.5, 0.9)
_HORIZONS = (1, 2)
_N_TRIALS = 3
_SCOPE = ScopeSpec(asset_id="TEST", feature_set_name="fs_test", max_horizon=2, cohort_id="c")
_SPACE = (
    SearchDimension(name="num_leaves", low=4, high=32, kind="int"),
    SearchDimension(name="learning_rate", low=0.01, high=0.3, kind="float"),
)
_FORBIDDEN_PORTS = ("persist_predictions", "persist_run_record", "analytics_repository")


class _CountingStore(FakeMedallionStore):
    def __init__(self) -> None:
        super().__init__()
        self.write_calls = 0
        self.read_calls = 0

    def write(self, **kwargs: Any) -> Any:  # noqa: ANN401
        self.write_calls += 1
        return super().write(**kwargs)

    def read(self, **kwargs: Any) -> Any:  # noqa: ANN401
        self.read_calls += 1
        return super().read(**kwargs)


class _CapturingTrainer(FakeQuantileModelTrainer):
    def __init__(self, *, fail_always: bool = False) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []
        self.results: list[QuantileTrainingResult] = []
        self._fail_always = fail_always

    def train_and_predict(self, **kwargs: Any) -> QuantileTrainingResult:  # type: ignore[override]  # noqa: ANN401
        self.calls.append(kwargs)
        if self._fail_always:
            raise ModelTrainingError("boom")
        result = super().train_and_predict(**kwargs)
        self.results.append(result)
        return result


def _sessions() -> tuple[date, ...]:
    days: list[date] = []
    current = date(2021, 1, 4)
    while len(days) < _N_SESSIONS:
        if current.weekday() <= _FRIDAY:
            days.append(current)
        current += timedelta(days=1)
    return tuple(days)


_SESSIONS = _sessions()


def _rows(*, missing_prefix: int = 0) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx, day in enumerate(_SESSIONS):
        row: dict[str, object] = {
            "timestamp": datetime(day.year, day.month, day.day, tzinfo=UTC),
            "asset_id": _SCOPE.asset_id,
            "target_return": math.sin(idx / 5.0) / 100.0,
        }
        for position, name in enumerate(modeling_columns()[:-1]):
            row[name] = float(idx) + (position + 1) / 100.0
        if idx < missing_prefix:
            row[modeling_columns()[0]] = None
        rows.append(row)
    return rows


def _build(
    *, trainer: _CapturingTrainer | None = None, missing_prefix: int = 0
) -> tuple[RunGbmSweep, _CountingStore, _CapturingTrainer, FakeExperimentTracker]:
    store = _CountingStore()
    store.seed_read_only(
        layer="processed",
        table="dataset_tft",
        asset=_SCOPE.asset_id,
        rows=_rows(missing_prefix=missing_prefix),
    )
    resolved = trainer if trainer is not None else _CapturingTrainer()
    tracker = FakeExperimentTracker()
    use_case = RunGbmSweep(
        store=store,
        splitter=WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=_SESSIONS))),
        trainer=resolved,
        search=InMemoryHyperparameterSearch(),
        tracker=tracker,
        hasher=CanonicalJsonHasher(),
    )
    return use_case, store, resolved, tracker


def _command(**overrides: object) -> RunGbmSweepCommand:
    base: dict[str, object] = {
        "scope": _SCOPE,
        "base_params": GbmTrainingParams(seed=7, num_boost_round_max=20, min_data_in_leaf=3),
        "space": _SPACE,
        "n_trials": _N_TRIALS,
        "seed": 11,
        "horizons": _HORIZONS,
        "quantile_levels": _LEVELS,
        "n_folds": 1,
        "test_size": 20,
        "val_size": 10,
        "calib_size": 10,
        "embargo": 1,
    }
    base.update(overrides)
    return RunGbmSweepCommand(**base)  # type: ignore[arg-type]


class TestStructuralIsolation:
    @pytest.mark.parametrize("port", _FORBIDDEN_PORTS)
    def test_no_result_persistence_port_in_the_constructor(self, port: str) -> None:
        assert port not in inspect.signature(RunGbmSweep.__init__).parameters

    def test_the_store_receives_no_writes(self) -> None:
        use_case, store, _, _ = _build()

        use_case(_command())

        assert store.write_calls == 0


class TestFitOnlyAndObjective:
    def test_trainer_is_called_fit_only_once_per_trial(self) -> None:
        use_case, _, trainer, _ = _build()

        use_case(_command())

        assert len(trainer.calls) == _N_TRIALS
        assert all(call["test_rows"] == () for call in trainer.calls)
        assert all(call["test_decision_indices"] == () for call in trainer.calls)

    def test_objective_is_the_mean_early_stop_loss_over_horizons(self) -> None:
        use_case, _, trainer, _ = _build()

        result = use_case(_command())

        for summary, training in zip(result.trials, trainer.results, strict=True):
            expected = fmean(training.early_stop_loss_by_horizon[h] for h in _HORIZONS)
            assert summary.objective_value == pytest.approx(expected)

    def test_best_params_come_from_the_best_trial(self) -> None:
        use_case, _, _, _ = _build()

        result = use_case(_command())

        best = next(t for t in result.trials if t.trial_number == result.best_trial_number)
        assert result.best_params.num_leaves == round(best.values["num_leaves"])
        assert result.best_params.seed == 7  # noqa: PLR2004 — base congelada preservada

    def test_every_trial_is_tagged_exploratory(self) -> None:
        use_case, _, _, tracker = _build()

        use_case(_command())

        runs = list(tracker._runs.values())
        assert len(runs) == _N_TRIALS
        assert all(run.tags["phase"] == "exploratory" for run in runs)


class TestDataset:
    def test_result_reports_the_fingerprint_of_the_swept_grid(self) -> None:
        first = _build()[0](_command())
        second = _build()[0](_command())

        assert len(first.dataset_fingerprint) == 64  # noqa: PLR2004 — sha256 hex
        assert first.dataset_fingerprint == second.dataset_fingerprint

    def test_warm_up_prefix_is_trimmed_like_the_trainers(self) -> None:
        use_case, _, trainer, _ = _build(missing_prefix=5)
        full_use_case, _, full_trainer, _ = _build()

        use_case(_command(n_trials=1))
        full_use_case(_command(n_trials=1))

        trimmed_first = trainer.calls[0]["train_rows"][0]
        full_rows = full_trainer.calls[0]["train_rows"]
        assert trimmed_first == full_rows[5]


class TestErrors:
    def test_all_trials_failing_raises_c9(self) -> None:
        use_case, _, _, _ = _build(trainer=_CapturingTrainer(fail_always=True))

        with pytest.raises(ValueError, match="C9"):
            use_case(_command())

    def test_dimension_outside_gbm_params_raises_before_any_io(self) -> None:
        use_case, store, _, _ = _build()
        tft_only = (SearchDimension(name="hidden_size", low=4, high=32, kind="int"),)

        with pytest.raises(ValueError, match="não é campo de GbmTrainingParams"):
            use_case(_command(space=tft_only))
        assert store.read_calls == 0

    @pytest.mark.parametrize(
        "overrides",
        [
            {"n_trials": 0},
            {"space": ()},
            {"quantile_levels": ()},
            {"quantile_levels": (0.5, 0.1)},
            {"quantile_levels": (0.0, 0.5)},
            {"horizons": ()},
            {"horizons": (1, 3)},
            {"horizons": (0,)},
            {"horizons": (1, 1)},
        ],
    )
    def test_invalid_command_raises_before_any_io(self, overrides: dict[str, object]) -> None:
        use_case, store, _, _ = _build()

        with pytest.raises(ValueError):
            use_case(_command(**overrides))
        assert store.read_calls == 0

    def test_empty_dataset_raises_c1(self) -> None:
        store = _CountingStore()
        store.seed_read_only(layer="processed", table="dataset_tft", asset="OTHER", rows=[])
        use_case = RunGbmSweep(
            store=store,
            splitter=WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=_SESSIONS))),
            trainer=_CapturingTrainer(),
            search=InMemoryHyperparameterSearch(),
            tracker=FakeExperimentTracker(),
            hasher=CanonicalJsonHasher(),
        )

        with pytest.raises(ValueError, match="C1"):
            use_case(_command())
