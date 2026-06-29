"""Integration test do `ParquetAnalyticsRepository` — layout Hive real em disco.

Escreve com o adapter real em `tmp_path` e inspeciona o **layout Hive físico**
(caminhos de partição literais por tabela, 1..3 níveis), confere append-only/upsert
reais lendo o disco, o round-trip `parent_sweep_id=None` → `None` e a validação
`pandera` antes do disco (concept 4.2 §11 A10):

- `silver/dim_run/asset=AAPL/parent_sweep_id=<sweep|__none__>/dim_run.parquet` (2 níveis)
- `silver/fact_oos_predictions/asset=AAPL/feature_set_name=<fs>/year=<yyyy>/...` (3 níveis)
- `silver/fact_failures/asset=AAPL/fact_failures.parquet` (1 nível)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from pandera.errors import SchemaError

from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.shared.domain.exceptions.base import DuplicateKeyError

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
    run_id: str = "run-1", *, parent_sweep_id: str | None = "sweep-1"
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "asset": "AAPL",
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
    run_id: str = "run-1", *, quantile_level: float = 0.5, value_raw: float = 0.01
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
        "value_raw": value_raw,
        "value_guardrail": value_raw,
        "guardrail_applied": 0,
        "year": 2024,
    }


def _fact_failures_row(run_id: str = "run-1") -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "asset": "AAPL",
        "failed_at_utc": "2024-01-02T00:00:00+00:00",
        "stage": "train",
        "error_type": "ValueError",
        "error_message": "boom",
        "trace_hash": "abc123",
        "traceback_excerpt": None,
    }


@pytest.mark.integration
def test_hive_layout_three_levels_fact_oos(tmp_path: Path) -> None:
    """A10/I2: `fact_oos_predictions` grava em asset=/feature_set_name=/year= (3 níveis)."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row()])

    expected = (
        tmp_path
        / "silver"
        / "fact_oos_predictions"
        / "asset=AAPL"
        / "feature_set_name=fs_all"
        / "year=2024"
        / "fact_oos_predictions.parquet"
    )
    assert expected.is_file()


@pytest.mark.integration
def test_hive_layout_two_levels_dim_run(tmp_path: Path) -> None:
    """A10/I2: `dim_run` grava em asset=/parent_sweep_id= (2 níveis)."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row()])

    expected = (
        tmp_path
        / "silver"
        / "dim_run"
        / "asset=AAPL"
        / "parent_sweep_id=sweep-1"
        / "dim_run.parquet"
    )
    assert expected.is_file()


@pytest.mark.integration
def test_hive_layout_one_level_fact_failures(tmp_path: Path) -> None:
    """A10/I2: `fact_failures` grava em asset= (1 nível)."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="fact_failures", rows=[_fact_failures_row()])

    expected = tmp_path / "silver" / "fact_failures" / "asset=AAPL" / "fact_failures.parquet"
    assert expected.is_file()


@pytest.mark.integration
def test_hive_layout_sentinel_for_none_parent_sweep(tmp_path: Path) -> None:
    """A10/C6: `parent_sweep_id=None` grava sob `parent_sweep_id=__none__`."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row(parent_sweep_id=None)])

    expected = (
        tmp_path
        / "silver"
        / "dim_run"
        / "asset=AAPL"
        / "parent_sweep_id=__none__"
        / "dim_run.parquet"
    )
    assert expected.is_file()


@pytest.mark.integration
def test_real_append_only_collision_then_upsert(tmp_path: Path) -> None:
    """A10/C1/C5: colisão real sem flag levanta; com flag o disco reflete o upsert."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row()])

    with pytest.raises(DuplicateKeyError):
        repo.write(
            layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row(value_raw=0.99)]
        )

    repo.write(
        layer=_SILVER,
        table="fact_oos_predictions",
        rows=[_fact_oos_row(value_raw=0.42)],
        allow_upsert=True,
    )

    path = (
        tmp_path
        / "silver"
        / "fact_oos_predictions"
        / "asset=AAPL"
        / "feature_set_name=fs_all"
        / "year=2024"
        / "fact_oos_predictions.parquet"
    )
    df = pd.read_parquet(path)
    assert len(df) == 1
    assert df.iloc[0]["value_raw"] == pytest.approx(0.42)


@pytest.mark.integration
def test_real_round_trip_parent_sweep_id_none(tmp_path: Path) -> None:
    """A10/I6/C6: `parent_sweep_id=None` grava sob `__none__` e `read` devolve `None`."""
    repo = _repo(tmp_path)
    repo.write(layer=_SILVER, table="dim_run", rows=[_dim_run_row(parent_sweep_id=None)])

    rows = repo.read(layer=_SILVER, table="dim_run", filters={"asset": "AAPL"})

    assert len(rows) == 1
    assert rows[0]["parent_sweep_id"] is None
    assert rows[0]["created_at_utc"] == _FIXED_NOW.isoformat()


@pytest.mark.integration
def test_real_pandera_rejects_before_disk(tmp_path: Path) -> None:
    """A10/C3/I4: dtype divergente → `SchemaError`, nenhum arquivo escrito."""
    repo = _repo(tmp_path)
    bad = _fact_oos_row()
    bad["value_raw"] = "not-a-float"

    with pytest.raises(SchemaError):
        repo.write(layer=_SILVER, table="fact_oos_predictions", rows=[bad])

    assert not any(tmp_path.rglob("*.parquet"))


@pytest.mark.integration
def test_real_append_only_accumulates_distinct_pks(tmp_path: Path) -> None:
    """A10/I3: dois writes de PKs distintas acumulam no arquivo da partição."""
    repo = _repo(tmp_path)
    repo.write(
        layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row(quantile_level=0.1)]
    )
    repo.write(
        layer=_SILVER, table="fact_oos_predictions", rows=[_fact_oos_row(quantile_level=0.9)]
    )

    rows = repo.read(layer=_SILVER, table="fact_oos_predictions", filters={"asset": "AAPL"})
    assert len(rows) == _TWO_ROWS
