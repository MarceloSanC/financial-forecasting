"""Contrato do port `CohortProgressLedger` (Stage 5.5, A4).

A fixture devolve `open_ledger()`: cada chamada "reabre" o ledger — o fake devolve
a mesma instância; o adapter real (perna `real`, Task 19) devolve uma instância
nova sobre o mesmo diretório. A mesma suíte prova, nas duas pernas: lock
exclusivo com dono identificado e quebra explícita de lock órfão; unidades
marcadas persistem entre aberturas; ambiente gravado e relido, com o instante de
início gravado uma única vez; resultados de sweep persistem por scope id.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from financial_forecasting.features.modeling.application.ports.out.cohort_progress_ledger import (
    CohortProgressLedger,
    CohortRunLockedError,
)
from tests.fakes.features.modeling.in_memory_cohort_progress_ledger import (
    InMemoryCohortProgressLedger,
)

_COHORT = "aapl_confirmatory-r0-abcdef123456"
_OpenLedger = Callable[[], CohortProgressLedger]


@pytest.fixture(params=["fake"])
def open_ledger(request: pytest.FixtureRequest) -> _OpenLedger:
    if request.param == "fake":
        ledger = InMemoryCohortProgressLedger()
        return lambda: ledger
    raise AssertionError(request.param)  # pragma: no cover


@pytest.mark.contract
def test_second_acquire_is_refused_naming_the_owner(open_ledger: _OpenLedger) -> None:
    first = open_ledger()
    first.acquire_writer()

    with pytest.raises(CohortRunLockedError, match="pid="):
        open_ledger().acquire_writer()


@pytest.mark.contract
def test_release_frees_the_lock(open_ledger: _OpenLedger) -> None:
    ledger = open_ledger()
    ledger.acquire_writer()
    ledger.release_writer()

    open_ledger().acquire_writer()


@pytest.mark.contract
def test_release_without_lock_is_a_no_op(open_ledger: _OpenLedger) -> None:
    open_ledger().release_writer()


@pytest.mark.contract
def test_break_stale_takes_over_an_existing_lock(open_ledger: _OpenLedger) -> None:
    open_ledger().acquire_writer()

    open_ledger().acquire_writer(break_stale=True)

    with pytest.raises(CohortRunLockedError):
        open_ledger().acquire_writer()


@pytest.mark.contract
def test_completed_units_persist_across_openings(open_ledger: _OpenLedger) -> None:
    open_ledger().mark_completed(_COHORT, "baselines", {"run-a": 3528, "run-b": 3472})
    open_ledger().mark_completed(_COHORT, "gbm", {"run-c": 3528})

    units = open_ledger().completed_units(_COHORT)

    assert units == {"baselines": {"run-a": 3528, "run-b": 3472}, "gbm": {"run-c": 3528}}
    assert open_ledger().completed_units("other-cohort") == {}


@pytest.mark.contract
def test_environment_and_start_are_recorded_once(open_ledger: _OpenLedger) -> None:
    assert open_ledger().environment(_COHORT) is None
    assert open_ledger().run_started_at(_COHORT) is None

    open_ledger().record_environment(
        _COHORT, {"torch": "2.4", "device": "cpu"}, started_at="2026-09-27T10:00:00+00:00"
    )
    open_ledger().record_environment(
        _COHORT, {"torch": "2.4", "device": "cpu"}, started_at="2026-09-28T10:00:00+00:00"
    )

    assert open_ledger().environment(_COHORT) == {"torch": "2.4", "device": "cpu"}
    assert open_ledger().run_started_at(_COHORT) == "2026-09-27T10:00:00+00:00"


@pytest.mark.contract
def test_sweep_results_persist_by_scope(open_ledger: _OpenLedger) -> None:
    open_ledger().record_sweep_result(
        "scope-1", "tft", {"study_id": "s-tft", "best_trial": 4, "best_objective": 0.012}
    )
    open_ledger().record_sweep_result(
        "scope-1", "gbm", {"study_id": "s-gbm", "best_trial": 2, "best_objective": 0.011}
    )

    results = open_ledger().sweep_results("scope-1")

    assert results["tft"]["study_id"] == "s-tft"
    assert results["gbm"]["best_trial"] == 2  # noqa: PLR2004
    assert open_ledger().sweep_results("scope-2") == {}
