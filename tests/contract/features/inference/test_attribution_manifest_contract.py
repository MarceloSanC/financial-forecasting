"""Contrato do port `AttributionManifest` do `inference` (Stage 7.3, Tasks 17-18; CA9).

Pernas `fake` (`InMemoryAttributionManifest`) e `real` (`JsonAttributionManifest` sob
`tmp_path`, Task 18). As duas mesclam pela MESMA `apply_run_entry` do manifesto da inferência. A
suíte prova o comportamento observável: sem manifesto → `None`; os campos de primeira
escrita (`checkpoint_sha256`, `first_write_environment`) nunca são sobrescritos; a
entrada guarda a identidade do plano e a partição; `runs` com forma inválida é
ilegível.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from financial_forecasting.features.inference.adapters.out.filesystem.json_attribution_manifest import (  # noqa: E501
    JsonAttributionManifest,
)
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


def _json_leg(root: Path) -> _Leg:
    def malformed() -> AttributionManifest:
        manifest = JsonAttributionManifest(data_root=root / "malformed")
        manifest.path(_COHORT).parent.mkdir(parents=True)
        manifest.path(_COHORT).write_text(json.dumps({"runs": ["x"]}), encoding="utf-8")
        return manifest

    return _Leg(
        open=lambda: JsonAttributionManifest(data_root=root / "data"), with_malformed_runs=malformed
    )


@pytest.fixture(params=["fake", "json"])
def leg(request: pytest.FixtureRequest, tmp_path: Path) -> _Leg:
    return _fake_leg() if request.param == "fake" else _json_leg(tmp_path)


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
    with pytest.raises(ValueError, match=r"malformed|unreadable"):
        leg.with_malformed_runs().record_run(_COHORT, "run-1", _entry())


# -- só a perna real ----------------------------------------------------------------


def test_write_is_atomic_by_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = JsonAttributionManifest(data_root=tmp_path)
    manifest.record_run(_COHORT, "run-1", _entry())
    before = manifest.path(_COHORT).read_bytes()

    def crash(src: object, dst: object) -> None:
        raise OSError("simulated crash before replace")

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(OSError, match="simulated crash"):
        manifest.record_run(_COHORT, "run-2", _entry())
    assert manifest.path(_COHORT).read_bytes() == before
    assert sorted(p.name for p in manifest.path(_COHORT).parent.iterdir()) == [
        "attribution_manifest.json"
    ]


def test_file_path_is_attribution_manifest_json(tmp_path: Path) -> None:
    manifest = JsonAttributionManifest(data_root=tmp_path)
    manifest.record_run(_COHORT, "run-1", _entry())
    expected = tmp_path / "inference" / _COHORT / "attribution_manifest.json"
    assert manifest.path(_COHORT) == expected
    assert expected.exists()
    assert not (tmp_path / "inference" / _COHORT / "manifest.json").exists()
    assert JsonAttributionManifest(data_root=tmp_path).recorded(_COHORT) is not None
