"""Contrato do port `AttributionManifest` do `inference` (Stage 7.3, Tasks 17-18; CA9).

Perna `fake` (`InMemoryAttributionManifest`); a perna real (o adapter JSON) entra na
Task 18. As duas mesclam pela MESMA `apply_run_entry` do manifesto da inferência. A
suíte prova o comportamento observável: sem manifesto → `None`; os campos de primeira
escrita (`checkpoint_sha256`, `first_write_environment`) nunca são sobrescritos; a
entrada guarda a identidade do plano e a partição; `runs` com forma inválida é
ilegível.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from financial_forecasting.features.inference.application.ports.out.attribution_manifest import (
    ATTRIBUTION_ENTRY_FIELDS,
    AttributionManifest,
)
from tests.fakes.features.inference.in_memory_attribution_manifest import (
    InMemoryAttributionManifest,
)

pytestmark = pytest.mark.contract

_COHORT = "aapl_confirmatory-r0-abcdef123456"


@dataclass(frozen=True)
class _Leg:
    open: Callable[[], AttributionManifest]
    with_malformed_runs: Callable[[], AttributionManifest]


def _fake_leg() -> _Leg:
    shared = InMemoryAttributionManifest()
    return _Leg(
        open=lambda: shared,
        with_malformed_runs=lambda: InMemoryAttributionManifest({_COHORT: {"runs": ["x"]}}),
    )


@pytest.fixture(params=["fake"])
def leg(request: pytest.FixtureRequest) -> _Leg:
    return _fake_leg()


def _entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "status": "started",
        "checkpoint_sha256": "a" * 64,
        "first_write_environment": {"torch": "2.13.0+cpu"},
        "settings": {"batch_size": "64"},
        "mode": "strict",
        "max_abs_diff": 0.0,
        "permutation_seed": 130,
        "k_p": 10,
        "permutation_algorithm": "fisher_yates_random_random_v1",
        "fold_index": 2,
        "n_decisions": 252,
        "family_partition": {"price": ["close"], "technical": ["rsi_14"]},
        "partition_hash": "b" * 64,
        "permuted_rows": 0,
        "vsn_rows": 0,
    }
    entry.update(overrides)
    return entry


def test_absent_cohort_is_none(leg: _Leg) -> None:
    assert leg.open().recorded(_COHORT) is None


def test_started_then_completed_merges_first_write_fields(leg: _Leg) -> None:
    manifest = leg.open()
    manifest.record_run(_COHORT, "run-1", _entry())
    manifest.record_run(
        _COHORT,
        "run-1",
        _entry(
            status="completed",
            checkpoint_sha256="c" * 64,
            first_write_environment={"torch": "OTHER"},
            permuted_rows=1230,
            vsn_rows=59,
        ),
    )
    document = manifest.recorded(_COHORT)
    assert document is not None
    run = document["runs"]["run-1"]  # type: ignore[index]
    assert run["status"] == "completed"
    assert run["permuted_rows"] == 1230  # noqa: PLR2004
    assert run["checkpoint_sha256"] == "a" * 64
    assert run["first_write_environment"] == {"torch": "2.13.0+cpu"}


def test_entry_has_the_plan_identity_and_partition(leg: _Leg) -> None:
    manifest = leg.open()
    manifest.record_run(_COHORT, "run-2", _entry())
    document = manifest.recorded(_COHORT)
    assert document is not None
    run = document["runs"]["run-2"]  # type: ignore[index]
    assert set(ATTRIBUTION_ENTRY_FIELDS) <= set(run)
    assert run["permutation_seed"] == 130  # noqa: PLR2004
    assert run["permutation_algorithm"] == "fisher_yates_random_random_v1"
    assert run["family_partition"] == {"price": ["close"], "technical": ["rsi_14"]}
    assert run["partition_hash"] == "b" * 64
    assert document["cohort_id"] == _COHORT


def test_runs_shape_problem_is_unreadable(leg: _Leg) -> None:
    with pytest.raises(ValueError, match="malformed"):
        leg.with_malformed_runs().record_run(_COHORT, "run-1", _entry())
