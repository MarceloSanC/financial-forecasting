"""Contract test do port `GoldGenerationReader` — suíte ÚNICA para o fake e o real.

Prova (concept 6.5 A9, I7, C6; ADR 6.5.0005 itens 1, 4, 5) que toda implementação
devolve, depois de um `publish` do `GoldStore` da mesma perna, a geração publicada:
manifesto e linhas iguais, tabela de zero linhas vazia, coluna toda `None` como
`None`, geração `BLOCKED` com o status e partição sem geração →
`GoldManifestNotFoundError`.

Pernas (*harness*): `fake` (`InMemoryGoldGenerationReader` sobre `InMemoryGoldStore`)
e `parquet` (`ParquetGoldStore` num `tmp_path`, que publica e lê) — sem `skipif`. Os
testes `real_*` são só do adapter: sem inferência hive, arquivo de tabela apagado,
contagem adulterada no `MANIFEST.json`, manifesto lido antes das tabelas e montagem
única por `GoldGeneration.from_stored`.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import pytest

from financial_forecasting.features.evaluation.adapters.out.duckdb import (
    parquet_gold_store as parquet_gold_store_module,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.parquet_gold_store import (
    MANIFEST_NAME,
    ParquetGoldStore,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_DM_RESULTS,
    GOLD_MCS_RESULTS,
    GOLD_QUALITY_CHECKS,
    GOLD_SCHEMAS,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldManifest,
    GoldPartition,
    GoldTable,
    RefreshParameters,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.ports.out.gold_generation_reader import (
    GoldGenerationCorruptError,
    GoldGenerationReader,
    GoldManifestNotFoundError,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
)
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)
from tests.fakes.features.evaluation.in_memory_gold_generation_reader import (
    InMemoryGoldGenerationReader,
)
from tests.fakes.features.evaluation.in_memory_gold_store import InMemoryGoldStore

_PARTITION = GoldPartition("AAPL", "sweep-01")
_REF = "test_plan-r0-0123456789ab"
_PARAMETERS = RefreshParameters(
    preregistration_ref=_REF,
    degeneracy_tolerance=1e-12,
    band_levels=(0.95, 0.975),
    min_violations=2,
    candidate="tft_quantile",
    dm_alpha=0.05,
    dm_variance_estimators=(DmVarianceEstimator.RECTANGULAR, DmVarianceEstimator.BARTLETT),
    mcs_alpha=0.10,
    mcs_reps=1000,
    mcs_seed=127,
    mcs_schemes=(BootstrapScheme.STATIONARY, BootstrapScheme.MOVING_BLOCK),
    monte_carlo_draws=999,
    monte_carlo_seed=128,
    mcs_block_sensitivities=("h", "sqrt_T"),
    profile_parameters=None,
)
_NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def _base(extra: Mapping[str, object] | None = None) -> dict[str, object]:
    return {"asset": "AAPL", "parent_sweep_id": "sweep-01", **(extra or {})}


def _quality_rows() -> list[dict[str, object]]:
    # horizon/model/seed todos None: a coluna toda `None` do contrato
    return [
        _base(
            {
                "check": f"check_{index}",
                "kind": "k",
                "horizon": None,
                "model": None,
                "seed": None,
                "severity": "ERROR",
                "outcome": "PASS",
                "occurrences": index,
                "detail": "",
            }
        )
        for index in range(3)
    ]


def _dm_rows() -> list[dict[str, object]]:
    return [
        _base(
            {
                "preregistration_ref": _REF,
                "horizon": 1,
                "variance_estimator": "rectangular",
                "candidate": "tft_quantile",
                "comparator": comparator,
                "n_points": 250,
                "mean_differential": -0.01,
                "statistic": -2.5,
                "adjusted_p_value": 0.02,
                "rejected": True,
                "fallback_applied": False,
                "alpha": 0.05,
            }
        )
        for comparator in ("baseline_ar1", "baseline_zero_return")
    ]


def _generation(
    status: RefreshStatus = RefreshStatus.COMPLETED,
) -> tuple[list[GoldTable], GoldManifest]:
    tables = [
        GoldTable.sorted_by_key(GOLD_QUALITY_CHECKS.name, GOLD_QUALITY_CHECKS.key, _quality_rows())
    ]
    if status is RefreshStatus.COMPLETED:
        tables += [
            GoldTable.sorted_by_key(GOLD_DM_RESULTS.name, GOLD_DM_RESULTS.key, _dm_rows()),
            GoldTable(GOLD_MCS_RESULTS.name, GOLD_MCS_RESULTS.key, ()),
        ]
        given = {table.name for table in tables}
        tables += [  # COMPLETED lista toda tabela (Stage 6.6): as demais, vazias
            GoldTable(name, schema.key, ())
            for name, schema in GOLD_SCHEMAS.items()
            if name not in given
        ]
    manifest = GoldManifest(
        status=status,
        partition=_PARTITION,
        rows_by_table={table.name: len(table.rows) for table in tables},
        parameters=_PARAMETERS,
        horizons=(1, 7),
        window_deficits={"tft_quantile": 0},
        dataset_fingerprint=DatasetContentFingerprint("ab" * 32),
        grid_trimmed_prefix=0,
        realized_sessions=250,
        realized_returns_fsum=0.125,
        realized_first_timestamp="2024-01-02T00:00:00+00:00",
        realized_last_timestamp="2024-12-31T00:00:00+00:00",
        n_runs=12,
        build_order=tuple(table.name.removeprefix("gold_") for table in tables),
        started_at=_NOW,
        finished_at=_NOW,
    )
    return tables, manifest


class Harness(Protocol):
    reader: GoldGenerationReader

    def publish(self, tables: Sequence[GoldTable], manifest: GoldManifest) -> None: ...


class _FakeHarness:
    def __init__(self, _: Path) -> None:
        self.store = InMemoryGoldStore()
        self.reader: GoldGenerationReader = InMemoryGoldGenerationReader(self.store)

    def publish(self, tables: Sequence[GoldTable], manifest: GoldManifest) -> None:
        self.store.publish(partition=_PARTITION, tables=tables, manifest=manifest)


class _ParquetHarness:
    def __init__(self, root: Path) -> None:
        self.store = ParquetGoldStore(root)
        self.reader: GoldGenerationReader = self.store

    def publish(self, tables: Sequence[GoldTable], manifest: GoldManifest) -> None:
        self.store.publish(partition=_PARTITION, tables=tables, manifest=manifest)


HARNESSES: dict[str, Callable[[Path], Harness]] = {
    "fake": _FakeHarness,
    "parquet": _ParquetHarness,
}


@pytest.fixture(params=list(HARNESSES), ids=list(HARNESSES))
def harness(request: pytest.FixtureRequest, tmp_path: Path) -> Harness:
    return HARNESSES[request.param](tmp_path)


@pytest.mark.contract
def test_reader_round_trip_equal(harness: Harness) -> None:
    tables, manifest = _generation()
    harness.publish(tables, manifest)

    generation = harness.reader.read_generation(partition=_PARTITION)

    assert generation.manifest == manifest
    assert dict(generation.tables) == {table.name: table for table in tables}


@pytest.mark.contract
def test_reader_zero_row_table(harness: Harness) -> None:
    harness.publish(*_generation())

    generation = harness.reader.read_generation(partition=_PARTITION)

    assert generation.table(GOLD_MCS_RESULTS).rows == ()
    assert generation.table(GOLD_MCS_RESULTS).key == GOLD_MCS_RESULTS.key


@pytest.mark.contract
def test_reader_all_none_column(harness: Harness) -> None:
    harness.publish(*_generation())

    rows = harness.reader.read_generation(partition=_PARTITION).table(GOLD_QUALITY_CHECKS).rows

    assert len(rows) == 3  # noqa: PLR2004
    assert all(row["horizon"] is None and row["seed"] is None for row in rows)


@pytest.mark.contract
def test_reader_blocked_returned(harness: Harness) -> None:
    harness.publish(*_generation(RefreshStatus.BLOCKED))

    generation = harness.reader.read_generation(partition=_PARTITION)

    assert generation.manifest.status is RefreshStatus.BLOCKED
    assert set(generation.tables) == {GOLD_QUALITY_CHECKS.name}


@pytest.mark.contract
def test_reader_missing_manifest_raises(harness: Harness) -> None:
    with pytest.raises(GoldManifestNotFoundError):
        harness.reader.read_generation(partition=_PARTITION)
    harness.publish(*_generation())
    with pytest.raises(GoldManifestNotFoundError):
        harness.reader.read_generation(partition=GoldPartition("AAPL", "sweep-02"))


def _published(tmp_path: Path) -> tuple[ParquetGoldStore, Path]:
    store = ParquetGoldStore(tmp_path)
    tables, manifest = _generation()
    store.publish(partition=_PARTITION, tables=tables, manifest=manifest)
    return store, store.current_dir(_PARTITION)


@pytest.mark.contract
def test_real_no_hive_inference(tmp_path: Path) -> None:
    store, current = _published(tmp_path)

    rows = store.read_generation(partition=_PARTITION).table(GOLD_DM_RESULTS).rows

    assert "asset=AAPL" in current.as_posix()
    assert "parent_sweep_id=sweep-01" in current.as_posix()
    assert all(type(row["asset"]) is str and row["asset"] == "AAPL" for row in rows)
    assert all(row["parent_sweep_id"] == "sweep-01" for row in rows)
    assert set(rows[0]) == set(_dm_rows()[0])


@pytest.mark.contract
def test_real_missing_table_file_corrupt(tmp_path: Path) -> None:
    store, current = _published(tmp_path)
    (current / f"{GOLD_DM_RESULTS.name}.parquet").unlink()

    with pytest.raises(GoldGenerationCorruptError, match="is missing"):
        store.read_generation(partition=_PARTITION)
    (current / f"{GOLD_MCS_RESULTS.name}.parquet").unlink()
    with pytest.raises(GoldGenerationCorruptError, match="is missing"):
        store.read_generation(partition=_PARTITION)


@pytest.mark.contract
def test_real_count_mismatch_corrupt(tmp_path: Path) -> None:
    store, current = _published(tmp_path)
    path = current / MANIFEST_NAME
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["rows_by_table"][GOLD_DM_RESULTS.name] = 5
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(GoldGenerationCorruptError, match="has 2 rows, the manifest says 5"):
        store.read_generation(partition=_PARTITION)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(GoldGenerationCorruptError, match="not valid JSON"):
        store.read_generation(partition=_PARTITION)


@pytest.mark.contract
def test_real_reads_manifest_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store, _ = _published(tmp_path)
    calls: list[str] = []
    read_manifest = parquet_gold_store_module._read_manifest
    read_rows = parquet_gold_store_module._read_rows

    def spy_manifest(path: Path) -> object:
        calls.append(path.name)
        return read_manifest(path)

    def spy_rows(path: Path) -> list[dict[str, object]]:
        calls.append(path.name)
        return read_rows(path)

    monkeypatch.setattr(parquet_gold_store_module, "_read_manifest", spy_manifest)
    monkeypatch.setattr(parquet_gold_store_module, "_read_rows", spy_rows)

    store.read_generation(partition=_PARTITION)

    assert calls[0] == MANIFEST_NAME
    # a tabela de zero linhas não é aberta (vem do rows_by_table)
    assert sorted(calls[1:]) == [
        f"{GOLD_DM_RESULTS.name}.parquet",
        f"{GOLD_QUALITY_CHECKS.name}.parquet",
    ]


@pytest.mark.contract
def test_real_single_assembly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store, _ = _published(tmp_path)
    calls: list[tuple[str, ...]] = []
    original = GoldGeneration.from_stored.__func__  # type: ignore[attr-defined]

    def spy(
        cls: type[GoldGeneration],
        manifest: Mapping[str, object],
        rows_by_table: Mapping[str, Sequence[Mapping[str, object]]],
        *,
        partition: GoldPartition,
    ) -> GoldGeneration:
        calls.append(tuple(sorted(rows_by_table)))
        generation: GoldGeneration = original(cls, manifest, rows_by_table, partition=partition)
        return generation

    monkeypatch.setattr(GoldGeneration, "from_stored", classmethod(spy))

    store.read_generation(partition=_PARTITION)

    assert calls == [tuple(sorted(GOLD_SCHEMAS))]  # uma montagem, com toda tabela listada


@pytest.mark.contract
@pytest.mark.parametrize("name", ["../../evil", "../gold_x", "gold_other"])
def test_real_unknown_table_name_rejected_before_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Checkpoint C bloco 2, F1/R3: nome de tabela fora do schema não vira caminho."""
    store, current = _published(tmp_path)
    path = current / MANIFEST_NAME
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["rows_by_table"] = {name: 1, **manifest["rows_by_table"]}
    path.write_text(json.dumps(manifest), encoding="utf-8")
    opened: list[Path] = []
    monkeypatch.setattr(parquet_gold_store_module, "_read_rows", opened.append)

    with pytest.raises(GoldGenerationCorruptError, match="unknown gold table"):
        store.read_generation(partition=_PARTITION)
    assert opened == []


@pytest.mark.contract
def test_reader_single_assembly_every_leg(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Checkpoint C bloco 2, F4: as duas pernas montam só por `GoldGeneration.from_stored`."""
    harness.publish(*_generation())
    calls: list[int] = []
    original = GoldGeneration.from_stored.__func__  # type: ignore[attr-defined]

    def spy(cls: type[GoldGeneration], *args: object, **kwargs: object) -> GoldGeneration:
        calls.append(1)
        generation: GoldGeneration = original(cls, *args, **kwargs)
        return generation

    monkeypatch.setattr(GoldGeneration, "from_stored", classmethod(spy))

    harness.reader.read_generation(partition=_PARTITION)

    assert calls == [1]


@pytest.mark.contract
def test_real_manifest_of_other_partition_corrupt(tmp_path: Path) -> None:
    """Checkpoint C bloco 2, F2: pasta `current/` copiada de outra partição é recusada."""
    store, current = _published(tmp_path)
    other = GoldPartition("AAPL", "sweep-02")
    target = store.current_dir(other)
    target.parent.mkdir(parents=True)
    shutil.copytree(current, target)

    with pytest.raises(GoldGenerationCorruptError, match="read as"):
        store.read_generation(partition=other)


@pytest.mark.contract
def test_real_unreadable_files_corrupt(tmp_path: Path) -> None:
    """Checkpoint C bloco 2, F3: Parquet truncado e manifesto não-UTF-8 viram corrupção."""
    store, current = _published(tmp_path)
    table = current / f"{GOLD_DM_RESULTS.name}.parquet"
    table.write_bytes(table.read_bytes()[:20])

    with pytest.raises(GoldGenerationCorruptError, match="not a readable Parquet file"):
        store.read_generation(partition=_PARTITION)
    (current / MANIFEST_NAME).write_bytes(bytes([0xFF, 0xFE]) + b"{")
    with pytest.raises(GoldGenerationCorruptError, match="not valid JSON"):
        store.read_generation(partition=_PARTITION)


# --- extras da auditoria de testes (rodada 1) -----------------------------------------


@pytest.mark.contract
@pytest.mark.parametrize(
    ("content", "message"),
    [
        pytest.param("[1, 2]", "is not a JSON object", id="not-object"),
        pytest.param('{"status": "COMPLETED"}', "has no rows_by_table", id="no-rows-by-table"),
    ],
)
def test_real_manifest_shape_corrupt(tmp_path: Path, content: str, message: str) -> None:
    """Auditoria (cobertura): manifesto que não é objeto ou sem `rows_by_table` é corrupção."""
    store, current = _published(tmp_path)
    (current / MANIFEST_NAME).write_text(content, encoding="utf-8")

    with pytest.raises(GoldGenerationCorruptError, match=message):
        store.read_generation(partition=_PARTITION)
