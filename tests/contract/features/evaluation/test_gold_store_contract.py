"""Contract test do port `GoldStore` — suíte ÚNICA para o fake e o real (ADR 6.4.0005).

Prova (concept 6.4 A8, D8) que toda implementação do port entrega a **geração
inteira**: depois do `publish`, a geração corrente da partição é exatamente as tabelas
e o manifesto publicados; um segundo `publish` com menos tabelas substitui (a tabela que
saiu não aparece); outra partição fica intocada; a ordem das linhas é preservada.

Cada perna é um *harness* (o store + a leitura da geração corrente): `fake`
(`InMemoryGoldStore`) e `parquet` (`ParquetGoldStore` num `tmp_path`, lido de volta por
`pyarrow` e pelo `MANIFEST.json`) — sem `skipif`. Os testes `real_*` são só do adapter
real: falha antes da troca, sobras, manifesto por último, aviso ao apagar `.previous/`,
leitura por DuckDB e identificador adulterado (A9, C3, C9).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import duckdb
import pyarrow.parquet as pq
import pytest

from financial_forecasting.features.evaluation.adapters.out.duckdb import (
    parquet_gold_store as parquet_gold_store_module,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.parquet_gold_store import (
    MANIFEST_NAME,
    ParquetGoldStore,
)
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


class _ParquetHarness:
    def __init__(self, root: Path) -> None:
        self._parquet = ParquetGoldStore(root)
        self.store: GoldStore = self._parquet

    def current(self, partition: GoldPartition) -> Generation | None:
        directory = self._parquet.current_dir(partition)
        manifest = directory / MANIFEST_NAME
        if not manifest.exists():
            return None
        tables = {
            path.stem: pq.read_table(path, partitioning=None).to_pylist()
            for path in sorted(directory.glob("*.parquet"))
        }
        return json.loads(manifest.read_text(encoding="utf-8")), tables


HARNESSES: dict[str, Callable[[Path], Harness]] = {
    "fake": _FakeHarness,
    "parquet": _ParquetHarness,
}


@pytest.fixture(params=list(HARNESSES), ids=list(HARNESSES))
def harness(request: pytest.FixtureRequest, tmp_path: Path) -> Harness:
    return HARNESSES[request.param](tmp_path)


def _table(
    name: str, n_rows: int, *, offset: float = 0.0, partition: GoldPartition = _PARTITION
) -> GoldTable:
    rows = tuple(
        {
            "asset": partition.asset,
            "parent_sweep_id": partition.parent_sweep_id,
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
    tables: list[GoldTable],
    *,
    status: RefreshStatus = RefreshStatus.COMPLETED,
    partition: GoldPartition = _PARTITION,
) -> GoldManifest:
    return GoldManifest(
        status=status,
        partition=partition,
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
    manifest = _manifest(tables, status=status, partition=partition)
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
    kept = [_table("gold_mcs_results", 3, partition=_OTHER)]
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


@pytest.mark.contract
def test_publish_rejects_incoherent_generation(harness: Harness) -> None:
    """Geração incoerente ergue antes de gravar (dono único `check_generation`)."""
    good = [_table("gold_quality_checks", 4)]
    _publish(harness, good)
    before = harness.current(_PARTITION)
    cases = [
        (good, _manifest(good, partition=_OTHER), "manifest is for partition"),
        (good + good, _manifest(good), "repeated"),
        (good, _manifest([_table("gold_quality_checks", 3)]), "rows_by_table"),
        (
            [_table("gold_quality_checks", 2, partition=_OTHER)],
            _manifest([_table("gold_quality_checks", 2)]),
            "not the partition",
        ),
    ]
    for tables, manifest, message in cases:
        with pytest.raises(ValueError, match=message):
            harness.store.publish(partition=_PARTITION, tables=tables, manifest=manifest)
    assert harness.current(_PARTITION) == before


# --- só do real (ParquetGoldStore) -----------------------------------------------------


def _files(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


@pytest.mark.contract
def test_real_failure_keeps_current(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`OSError` na 2ª tabela: propaga; `current/` e o manifesto byte-iguais (C9)."""
    store = ParquetGoldStore(tmp_path)
    tables = [_table("gold_quality_checks", 4), _table("gold_dm_results", 6)]
    store.publish(partition=_PARTITION, tables=tables, manifest=_manifest(tables))
    current = store.current_dir(_PARTITION)
    before = _files(current)
    original = parquet_gold_store_module._write_table
    calls: list[str] = []

    def _flaky(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
        calls.append(path.name)
        if len(calls) == 2:  # noqa: PLR2004 — a segunda tabela
            raise OSError("disk full (simulated)")
        original(path, rows)

    monkeypatch.setattr(parquet_gold_store_module, "_write_table", _flaky)
    newer = [_table("gold_quality_checks", 2, offset=5.0), _table("gold_dm_results", 3)]
    with pytest.raises(OSError, match="disk full"):
        store.publish(partition=_PARTITION, tables=newer, manifest=_manifest(newer))
    assert _files(current) == before
    assert MANIFEST_NAME in before


@pytest.mark.contract
def test_real_failure_keeps_current_on_swap_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2ª troca (`.staging` → `current`) falha: rollback de `.previous` e o erro propaga."""
    store = ParquetGoldStore(tmp_path)
    first = [_table("gold_quality_checks", 4)]
    store.publish(partition=_PARTITION, tables=first, manifest=_manifest(first))
    current = store.current_dir(_PARTITION)
    before = _files(current)
    real_replace = os.replace

    def _refuse_staging(src: str | Path, dst: str | Path) -> None:
        if Path(src).name == ".staging":
            raise OSError("rename refused (simulated)")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _refuse_staging)
    second = [_table("gold_quality_checks", 2, offset=7.0)]
    with pytest.raises(OSError, match="rename refused"):
        store.publish(partition=_PARTITION, tables=second, manifest=_manifest(second))
    monkeypatch.undo()
    assert _files(current) == before
    assert not (store.partition_root(_PARTITION) / ".previous").exists()


@pytest.mark.contract
def test_real_failure_keeps_current_after_crash_between_swaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Crash entre as trocas (só `.previous/` completo): o `publish` seguinte o restaura."""
    store = ParquetGoldStore(tmp_path)
    first = [_table("gold_quality_checks", 4)]
    store.publish(partition=_PARTITION, tables=first, manifest=_manifest(first))
    root = store.partition_root(_PARTITION)
    before = _files(root / "current")
    os.replace(root / "current", root / ".previous")

    def _broken(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
        raise OSError("disk full (simulated)")

    monkeypatch.setattr(parquet_gold_store_module, "_write_table", _broken)
    second = [_table("gold_quality_checks", 2)]
    with pytest.raises(OSError, match="disk full"):
        store.publish(partition=_PARTITION, tables=second, manifest=_manifest(second))
    assert _files(root / "current") == before
    assert not (root / ".previous").exists()


@pytest.mark.contract
def test_real_leftovers_removed(tmp_path: Path) -> None:
    store = ParquetGoldStore(tmp_path)
    root = store.partition_root(_PARTITION)
    for leftover in (".staging", ".previous"):
        (root / leftover).mkdir(parents=True)
        (root / leftover / "junk.parquet").write_bytes(b"stale")
    tables = [_table("gold_quality_checks", 4)]
    store.publish(partition=_PARTITION, tables=tables, manifest=_manifest(tables))
    assert sorted(path.name for path in root.iterdir()) == ["current"]
    assert sorted(_files(store.current_dir(_PARTITION))) == [
        MANIFEST_NAME,
        "gold_quality_checks.parquet",
    ]


@pytest.mark.contract
def test_real_manifest_written_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    write_table = parquet_gold_store_module._write_table
    write_manifest = parquet_gold_store_module._write_manifest

    def _spy_table(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
        order.append(path.name)
        write_table(path, rows)

    def _spy_manifest(path: Path, manifest: GoldManifest) -> None:
        order.append(path.name)
        write_manifest(path, manifest)

    monkeypatch.setattr(parquet_gold_store_module, "_write_table", _spy_table)
    monkeypatch.setattr(parquet_gold_store_module, "_write_manifest", _spy_manifest)
    tables = [_table("gold_quality_checks", 4), _table("gold_mcs_results", 3)]
    ParquetGoldStore(tmp_path).publish(
        partition=_PARTITION, tables=tables, manifest=_manifest(tables)
    )
    assert order == ["gold_quality_checks.parquet", "gold_mcs_results.parquet", MANIFEST_NAME]


@pytest.mark.contract
def test_real_previous_delete_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Falha ao apagar `.previous/` depois da troca: aviso, sucesso, e o próximo limpa."""
    store = ParquetGoldStore(tmp_path)
    root = store.partition_root(_PARTITION)
    first = [_table("gold_quality_checks", 4)]
    store.publish(partition=_PARTITION, tables=first, manifest=_manifest(first))
    real_rmtree = shutil.rmtree

    def _refuse_previous(path: str | Path, *args: object, **kwargs: object) -> None:
        if Path(path).name == ".previous":
            raise OSError("busy (simulated)")
        real_rmtree(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(shutil, "rmtree", _refuse_previous)
    second = [_table("gold_quality_checks", 2, offset=3.0)]
    with caplog.at_level(logging.WARNING):
        store.publish(partition=_PARTITION, tables=second, manifest=_manifest(second))
    assert "could not delete" in caplog.text
    assert (root / ".previous").exists()
    manifest = json.loads((store.current_dir(_PARTITION) / MANIFEST_NAME).read_text("utf-8"))
    assert manifest["rows_by_table"] == {"gold_quality_checks": 2}
    monkeypatch.undo()
    third = [_table("gold_quality_checks", 1)]
    store.publish(partition=_PARTITION, tables=third, manifest=_manifest(third))
    assert sorted(path.name for path in root.iterdir()) == ["current"]


@pytest.mark.contract
def test_real_duckdb_readable(tmp_path: Path) -> None:
    store = ParquetGoldStore(tmp_path)
    tables = [_table("gold_metrics_by_run", 9), _table("gold_dm_results", 4)]
    store.publish(partition=_PARTITION, tables=tables, manifest=_manifest(tables))
    connection = duckdb.connect()
    for table in tables:
        path = store.current_dir(_PARTITION) / f"{table.name}.parquet"
        cursor = connection.execute("SELECT * FROM read_parquet(?)", [str(path)])
        names = [column[0] for column in cursor.description]
        got = [dict(zip(names, values, strict=True)) for values in cursor.fetchall()]
        assert got == _rows(table)


@pytest.mark.contract
def test_real_rejects_bad_identifier(tmp_path: Path) -> None:
    """`GoldPartition` adulterada: `ValueError` antes de criar qualquer caminho (C3)."""
    partition = GoldPartition("AAPL", "sweep-01")
    object.__setattr__(partition, "asset", "../x")
    tables = [_table("gold_quality_checks", 1, partition=partition)]
    manifest = _manifest(tables, partition=partition)
    with pytest.raises(ValueError, match="asset must match"):
        ParquetGoldStore(tmp_path).publish(partition=partition, tables=tables, manifest=manifest)
    assert not (tmp_path / "gold").exists()
