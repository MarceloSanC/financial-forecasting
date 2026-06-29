"""Unit test do `ParquetAnalyticsRepository.read` (pruning + projeção + round-trip).

Cobre (concept 4.2 A7/A8, C4/C6, I6/I8, D5): pruning por `asset` (e opcional por
`parent_sweep_id`/`year`), projeção do conjunto/ordem do schema (não `SELECT *`),
round-trip `parent_sweep_id=None` → `None` (sentinel `__none__` no disco) e vazio
para `(layer, table)`/asset inexistente. Usa o `write` do adapter para popular o
disco (round-trip real do adapter).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.fact_oos_predictions_schema import (  # noqa: E501
    FACT_OOS_PREDICTIONS,
)

_SILVER = "silver"
_FIXED_NOW = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)
_TWO_ROWS = 2


class FakeClock:
    """Clock determinístico (timestamp fixo)."""

    def now(self) -> datetime:
        return _FIXED_NOW


def _repo(tmp_path: Path) -> ParquetAnalyticsRepository:
    return ParquetAnalyticsRepository(data_root=tmp_path, clock=FakeClock())


def _dim_run_row(
    run_id: str = "run-1",
    *,
    asset: str = "AAPL",
    parent_sweep_id: str | None = "sweep-1",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "asset": asset,
        "parent_sweep_id": parent_sweep_id,
        "feature_set_name": "fs_all",
        "config_signature": "cfg-hash",
        "split_fingerprint": "split-hash",
        "fold": "fold-0",
        "seed": 42,
        "model_version": "tft_v1",
        "created_at_utc": _FIXED_NOW.isoformat(),
    }


def _fact_oos_row(
    run_id: str = "run-1", *, quantile_level: float = 0.5, year: int = 2024
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "model_version": "tft_v1",
        "asset": "AAPL",
        "feature_set_name": "fs_all",
        "split": "test",
        "horizon": 1,
        "decision_idx": 0,
        "timestamp_utc": "2024-01-02T00:00:00+00:00",
        "target_timestamp_utc": "2024-01-03T00:00:00+00:00",
        "quantile_level": quantile_level,
        "value_raw": 0.01,
        "value_guardrail": 0.01,
        "guardrail_applied": 0,
        "year": year,
    }


def test_read_missing_dataset_returns_empty(tmp_path: Path) -> None:
    """C4: `read` de `(layer, table)` não gravado → vazio."""
    repo = _repo(tmp_path)
    assert list(repo.read(layer=_SILVER, table="dim_run", filters={"asset": "AAPL"})) == []


def test_read_missing_asset_returns_empty(tmp_path: Path) -> None:
    """C4: filtro por `asset` sem dados → vazio (não erro)."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row()])
    assert list(repo.read(layer=_SILVER, table="dim_run", filters={"asset": "NVDA"})) == []


def test_read_projects_exact_schema_columns(tmp_path: Path) -> None:
    """A7/A9: o `read` projeta exatamente o conjunto de colunas do schema."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row()])

    rows = repo.read(layer=_SILVER, table="fact_oos_predictions", filters={"asset": "AAPL"})

    assert len(rows) == 1
    assert set(rows[0]) == set(FACT_OOS_PREDICTIONS.schema.columns)


def test_read_prunes_by_asset(tmp_path: Path) -> None:
    """I8: `read({"asset": A})` num dataset com dois assets devolve só A."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row("r-aapl", asset="AAPL")])
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row("r-msft", asset="MSFT")])

    aapl = repo.read(layer=_SILVER, table="dim_run", filters={"asset": "AAPL"})

    assert len(aapl) == 1
    assert all(r["asset"] == "AAPL" for r in aapl)


def test_read_prunes_by_year(tmp_path: Path) -> None:
    """I8: pruning por `year` (coluna de partição literal de fact_oos_predictions)."""
    repo = _repo(tmp_path)
    repo.write(
        layer=_SILVER,
        table="fact_oos_predictions",
        rows=[_fact_oos_row("r-2023", quantile_level=0.5, year=2023)],
    )
    repo.write(
        layer=_SILVER,
        table="fact_oos_predictions",
        rows=[_fact_oos_row("r-2024", quantile_level=0.5, year=2024)],
    )

    rows = repo.read(
        layer=_SILVER,
        table="fact_oos_predictions",
        filters={"asset": "AAPL", "year": 2024},
    )

    assert len(rows) == 1
    assert int(rows[0]["year"]) == 2024  # noqa: PLR2004


def test_read_prunes_by_parent_sweep_id(tmp_path: Path) -> None:
    """I8: pruning por `parent_sweep_id` (2º nível de partição de dim_run)."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row("r-a", parent_sweep_id="sw-a")])
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row("r-b", parent_sweep_id="sw-b")])

    rows = repo.read(
        layer=_SILVER,
        table="dim_run",
        filters={"asset": "AAPL", "parent_sweep_id": "sw-a"},
    )

    assert len(rows) == 1
    assert rows[0]["run_id"] == "r-a"


def test_read_round_trips_parent_sweep_id_none(tmp_path: Path) -> None:
    """A8/C6/I6: `parent_sweep_id=None` armazenado como `__none__` volta como `None`."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row(parent_sweep_id=None)])

    rows = repo.read(layer=_SILVER, table="dim_run", filters={"asset": "AAPL"})

    assert len(rows) == 1
    assert rows[0]["parent_sweep_id"] is None


def test_read_round_trip_filter_by_none_parent_sweep_id(tmp_path: Path) -> None:
    """I6/I8: filtrar por `parent_sweep_id=None` casa as linhas gravadas como `__none__`."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row("r-none", parent_sweep_id=None)])
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row("r-sw", parent_sweep_id="sw-1")])

    rows = repo.read(
        layer=_SILVER,
        table="dim_run",
        filters={"asset": "AAPL", "parent_sweep_id": None},
    )

    assert len(rows) == 1
    assert rows[0]["run_id"] == "r-none"
    assert rows[0]["parent_sweep_id"] is None


def test_read_accumulated_rows(tmp_path: Path) -> None:
    """Round-trip de várias linhas append-only na mesma partição."""
    repo = _repo(tmp_path)
    repo.write(
        layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row(quantile_level=0.1)]
    )
    repo.write(
        layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row(quantile_level=0.9)]
    )

    rows = repo.read(layer=_SILVER, table="fact_oos_predictions", filters={"asset": "AAPL"})

    assert len(rows) == _TWO_ROWS
    assert {float(r["quantile_level"]) for r in rows} == {0.1, 0.9}
