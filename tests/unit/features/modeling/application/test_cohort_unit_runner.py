"""Máquina de unidades compartilhada dos executores de cohort (Stage 7.3, Task 07; CA4, D7).

Sobre os fakes da 5.5 e o spec sintético de `test_run_confirmatory_cohort.py`. Prova a
máquina extraída diretamente, sem passar pelo `RunConfirmatoryCohort`: reconferência
da unidade do ledger, unidade completa no silver verificada e marcada, parcial ergue,
ausente roda e é marcada só depois do sucesso, ambiente gravado e comparado, árvore
suja recusada e lock liberado em erro.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from financial_forecasting.features.modeling.application.use_cases.cohort_unit_runner import (
    RAN,
    SKIPPED_COMPLETED,
    VERIFIED_COMPLETED,
    CompletedUnitCorruptedError,
    EnvironmentMismatchError,
    PartialCohortUnitError,
    RecordedRuns,
    UnitOutputMismatchError,
    UnitPlan,
    check_environment,
    classify_and_run,
    writer_lock,
)
from tests.fakes.features.modeling.in_memory_cohort_progress_ledger import (
    InMemoryCohortProgressLedger,
)
from tests.fakes.features.modeling.in_memory_cohort_run_index import InMemoryCohortRunIndex
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)
from tests.fakes.shared.in_memory_clock import FakeClock
from tests.unit.features.modeling.application.test_run_confirmatory_cohort import (
    _ASSET,
    _FEATURE_SET,
    _GEOMETRY,
    _HORIZONS,
    _LEVELS,
    _spec,
    _targets,
)

pytestmark = pytest.mark.unit

_COHORT = "cohort-x"
_MODEL = ("tft_quantile_loco_full", 7)


class _Unit:
    """Unidade que "persiste" no índice como o use case de treino faria."""

    def __init__(self, index: InMemoryCohortRunIndex, *, folds: range | None = None) -> None:
        self.index = index
        self.calls = 0
        self._folds = folds if folds is not None else range(_GEOMETRY.n_folds)

    def __call__(self) -> Mapping[str, int]:
        self.calls += 1
        return {run_id: rows for run_id, rows in _persist(self.index, self._folds)}


def _persist(index: InMemoryCohortRunIndex, folds: range) -> list[tuple[str, int]]:
    written = []
    for fold in folds:
        rows = _GEOMETRY.expected_prediction_rows(
            fold_index=fold, horizons=_HORIZONS, n_levels=len(_LEVELS)
        )
        run_id = f"run-f{fold}"
        index.record(
            asset_id=_ASSET,
            feature_set_name=_FEATURE_SET,
            cohort_id=_COHORT,
            model_version=_MODEL[0],
            seed=_MODEL[1],
            run_id=run_id,
            fold=str(fold),
            targets_by_horizon=_targets(fold),
            rows=rows,
        )
        written.append((run_id, rows))
    return written


def _recorded(index: InMemoryCohortRunIndex) -> RecordedRuns:
    return index.recorded_runs(asset_id=_ASSET, feature_set_name=_FEATURE_SET, cohort_id=_COHORT)


def _run(
    unit: _Unit, ledger: InMemoryCohortProgressLedger, index: InMemoryCohortRunIndex
) -> object:
    plan = UnitPlan(key="tft:full:seed=7", execute=unit, model_keys=(_MODEL,))
    return classify_and_run(
        plan, spec=_spec(), cohort_id=_COHORT, ledger=ledger, recorded=lambda: _recorded(index)
    )


def test_ledger_unit_is_reconferred() -> None:
    ledger, index = InMemoryCohortProgressLedger(), InMemoryCohortRunIndex()
    unit = _Unit(index)
    _run(unit, ledger, index)

    again = _run(unit, ledger, index)
    assert again.status == SKIPPED_COMPLETED  # type: ignore[attr-defined]
    assert unit.calls == 1

    index._runs[(_COHORT, _ASSET, _FEATURE_SET)][_MODEL].pop("run-f0")
    with pytest.raises(CompletedUnitCorruptedError, match="run-f0"):
        _run(unit, ledger, index)


def test_silver_complete_unit_is_verified_and_marked() -> None:
    ledger, index = InMemoryCohortProgressLedger(), InMemoryCohortRunIndex()
    _persist(index, range(_GEOMETRY.n_folds))
    unit = _Unit(index)

    outcome = _run(unit, ledger, index)

    assert outcome.status == VERIFIED_COMPLETED  # type: ignore[attr-defined]
    assert unit.calls == 0
    assert set(ledger.completed_units(_COHORT)["tft:full:seed=7"]) == {"run-f0", "run-f1"}


def test_partial_unit_raises() -> None:
    ledger, index = InMemoryCohortProgressLedger(), InMemoryCohortRunIndex()
    _persist(index, range(1))
    unit = _Unit(index)

    with pytest.raises(PartialCohortUnitError, match="revision"):
        _run(unit, ledger, index)
    assert unit.calls == 0
    assert ledger.completed_units(_COHORT) == {}


def test_absent_unit_runs_and_is_marked_after_success() -> None:
    ledger, index = InMemoryCohortProgressLedger(), InMemoryCohortRunIndex()
    unit = _Unit(index)

    outcome = _run(unit, ledger, index)

    assert outcome.status == RAN  # type: ignore[attr-defined]
    assert outcome.rows_written > 0  # type: ignore[attr-defined]
    assert unit.calls == 1
    assert "tft:full:seed=7" in ledger.completed_units(_COHORT)


def test_unit_whose_output_is_incomplete_is_not_marked() -> None:
    ledger, index = InMemoryCohortProgressLedger(), InMemoryCohortRunIndex()
    unit = _Unit(index, folds=range(1))

    with pytest.raises(UnitOutputMismatchError):
        _run(unit, ledger, index)
    assert ledger.completed_units(_COHORT) == {}


def test_failing_unit_is_not_marked() -> None:
    ledger, index = InMemoryCohortProgressLedger(), InMemoryCohortRunIndex()

    def boom() -> Mapping[str, int]:
        raise RuntimeError("boom")

    plan = UnitPlan(key="u", execute=boom, model_keys=(_MODEL,))
    with pytest.raises(RuntimeError, match="boom"):
        classify_and_run(
            plan, spec=_spec(), cohort_id=_COHORT, ledger=ledger, recorded=lambda: _recorded(index)
        )
    assert ledger.completed_units(_COHORT) == {}


def test_environment_recorded_first_then_compared() -> None:
    ledger = InMemoryCohortProgressLedger()
    clock = FakeClock()

    check_environment(ledger, InMemoryRuntimeEnvironmentProbe(), _COHORT, clock=clock)
    assert ledger.environment(_COHORT) == InMemoryRuntimeEnvironmentProbe().snapshot()
    assert ledger.run_started_at(_COHORT) == clock.now().isoformat()

    check_environment(ledger, InMemoryRuntimeEnvironmentProbe(), _COHORT, clock=clock)
    with pytest.raises(EnvironmentMismatchError, match="torch"):
        check_environment(
            ledger, InMemoryRuntimeEnvironmentProbe(torch="other"), _COHORT, clock=clock
        )


def test_dirty_tree_refused() -> None:
    ledger = InMemoryCohortProgressLedger()
    probe = InMemoryRuntimeEnvironmentProbe(code_dirty="true")

    with pytest.raises(EnvironmentMismatchError, match="commit first"):
        check_environment(ledger, probe, _COHORT, clock=FakeClock())
    assert ledger.environment(_COHORT) is None


def test_lock_released_on_error() -> None:
    ledger = InMemoryCohortProgressLedger()

    with pytest.raises(RuntimeError, match="inside"), writer_lock(ledger, break_stale=False):
        assert ledger.is_locked
        raise RuntimeError("inside")
    assert not ledger.is_locked
