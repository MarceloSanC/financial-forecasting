"""Contract test do port `GoldStore` — suíte ÚNICA para o fake e o real (ADR 6.4.0005).

Prova (concept 6.4 A8, D8) que toda implementação do port entrega a **geração
inteira**: depois do `publish`, a geração corrente da partição é exatamente as tabelas
e o manifesto publicados; um segundo `publish` com menos tabelas substitui (a tabela que
saiu não aparece); outra partição fica intocada; a ordem das linhas é preservada.

Cada perna é um *harness* (o store + a leitura da geração corrente). Perna `fake`
(`InMemoryGoldStore`); a perna do adapter real entra na Task 08, sem `skipif`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import pytest

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldManifest,
    GoldPartition,
    GoldTable,
    RefreshParameters,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.ports.out.gold_store import (
    GoldStore,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
)
from financial_forecasting.shared.domain.value_objects.dataset_fingerprint import (
    DatasetFingerprint,
)
from tests.fakes.features.evaluation.in_memory_gold_store import InMemoryGoldStore

Generation = tuple[dict[str, object], dict[str, list[dict[str, object]]]]

_PARTITION = GoldPartition("AAPL", "sweep-01")
_OTHER = GoldPartition("AAPL", "sweep-02")
_PARAMETERS = RefreshParameters(
    preregistration_ref="prereg-test-0001",
    degeneracy_tolerance=1e-9,
    band_levels=(0.95, 0.975),
    min_violations=5,
    candidate="tft",
    dm_alpha=0.05,
    dm_variance_estimators=(DmVarianceEstimator.RECTANGULAR,),
    mcs_alpha=0.10,
    mcs_reps=1000,
    mcs_seed=7,
    mcs_schemes=(BootstrapScheme.STATIONARY,),
)
_NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


class Harness(Protocol):
    """Uma perna: o store e a leitura da geração corrente de uma partição."""

    store: GoldStore

    def current(self, partition: GoldPartition) -> Generation | None: ...


class _FakeHarness:
    def __init__(self, _root: Path) -> None:
        self._fake = InMemoryGoldStore()
        self.store: GoldStore = self._fake

    def current(self, partition: GoldPartition) -> Generation | None:
        return self._fake.current(partition)


HARNESSES: dict[str, Callable[[Path], Harness]] = {"fake": _FakeHarness}


@pytest.fixture(params=list(HARNESSES), ids=list(HARNESSES))
def harness(request: pytest.FixtureRequest, tmp_path: Path) -> Harness:
    return HARNESSES[request.param](tmp_path)


def _table(name: str, n_rows: int, *, offset: float = 0.0) -> GoldTable:
    rows = tuple(
        {
            "asset": "AAPL",
            "parent_sweep_id": "sweep-01",
            "horizon": 1 + index // 3,
            "model": ("gbm", "naive", "tft")[index % 3],
            "seed": None if index % 3 != 2 else index,  # noqa: PLR2004 — tft com seed
            "value": offset + index / 8,
            "included": index % 2 == 0,
            "label": None,
        }
        for index in range(n_rows)
    )
    return GoldTable(name, ("horizon", "model"), rows)


def _manifest(
    tables: list[GoldTable], *, status: RefreshStatus = RefreshStatus.COMPLETED
) -> GoldManifest:
    return GoldManifest(
        status=status,
        partition=_PARTITION,
        rows_by_table={table.name: len(table.rows) for table in tables},
        parameters=_PARAMETERS,
        horizons=(1, 2),
        window_deficits={"tft": 2},
        dataset_fingerprint=DatasetFingerprint(value="cd" * 32),
        realized_sessions=40,
        realized_returns_fsum=0.25,
        realized_first_timestamp="2024-01-02T00:00:00+00:00",
        realized_last_timestamp="2024-02-10T00:00:00+00:00",
        n_runs=6,
        build_order=tuple(table.name.removeprefix("gold_") for table in tables),
        started_at=_NOW,
        finished_at=_NOW,
    )


def _publish(
    harness: Harness,
    tables: list[GoldTable],
    *,
    partition: GoldPartition = _PARTITION,
    status: RefreshStatus = RefreshStatus.COMPLETED,
) -> GoldManifest:
    manifest = _manifest(tables, status=status)
    harness.store.publish(partition=partition, tables=tables, manifest=manifest)
    return manifest


def _rows(table: GoldTable) -> list[dict[str, object]]:
    return [dict(row) for row in table.rows]


@pytest.mark.contract
def test_publish_then_current(harness: Harness) -> None:
    tables = [_table("gold_quality_checks", 4), _table("gold_dm_results", 6)]
    manifest = _publish(harness, tables)
    current = harness.current(_PARTITION)
    assert current is not None
    got_manifest, got_tables = current
    assert got_manifest == manifest.as_mapping()
    assert got_tables == {table.name: _rows(table) for table in tables}


@pytest.mark.contract
def test_publish_replaces_generation(harness: Harness) -> None:
    _publish(harness, [_table("gold_quality_checks", 4), _table("gold_dm_results", 6)])
    blocked = [_table("gold_quality_checks", 2, offset=10.0)]
    manifest = _publish(harness, blocked, status=RefreshStatus.BLOCKED)
    current = harness.current(_PARTITION)
    assert current is not None
    got_manifest, got_tables = current
    assert got_manifest == manifest.as_mapping()
    assert got_manifest["status"] == "BLOCKED"
    assert got_tables == {"gold_quality_checks": _rows(blocked[0])}


@pytest.mark.contract
def test_other_partition_untouched(harness: Harness) -> None:
    kept = [_table("gold_mcs_results", 3)]
    _publish(harness, kept, partition=_OTHER)
    before = harness.current(_OTHER)
    _publish(harness, [_table("gold_quality_checks", 4)])
    _publish(harness, [_table("gold_quality_checks", 1)])
    assert harness.current(_OTHER) == before
    assert before is not None
    assert before[1] == {"gold_mcs_results": _rows(kept[0])}
    assert harness.current(GoldPartition("MSFT", "sweep-01")) is None


@pytest.mark.contract
def test_rows_order_preserved(harness: Harness) -> None:
    table = _table("gold_metrics_by_run", 9)
    _publish(harness, [table])
    current = harness.current(_PARTITION)
    assert current is not None
    got = current[1]["gold_metrics_by_run"]
    assert [(r["horizon"], r["model"]) for r in got] == [
        (row["horizon"], row["model"]) for row in table.rows
    ]
    assert got == _rows(table)
