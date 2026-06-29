"""Integration test do `ParquetMedallionStore` particionado real (Stage 2.1, task-08).

Grava/lê datasets bronze de verdade em `tmp_path` (sem mock) e asserta a tarefa
de fundação (A6): layout Hive em disco (`asset=<asset>/year=<year>/<table>.parquet`),
round-trip de dtype EXATO (UTC preservado, `float32` não vira `float64`, `volume`
`int64`, fundamentals `float64`, `reported_date` `NaT` preservado), append-only
entre dois `write`, e que `read({"asset": A})` num dataset com dois assets retorna
SÓ as linhas de `A` (partition pruning, I7).

Cobre candle (float32/int64/UTC) e fundamental (float64/NaT) — as duas tabelas
com os dtypes mais sensíveis ao round-trip.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from financial_forecasting.shared.adapters.out.parquet.parquet_medallion_store import (
    ParquetMedallionStore,
)

_F32 = np.float32
_VOLUME = 1_234_567
_TWO_ROWS = 2


def _candle_row(asset: str, ts: datetime, close: float) -> dict[str, object]:
    return {
        "asset": asset,
        "timestamp": ts,
        "open": _F32(close - 1.0),
        "high": _F32(close + 1.0),
        "low": _F32(close - 2.0),
        "close": _F32(close),
        "volume": _VOLUME,
    }


def _fundamental_row(reported: datetime | None) -> dict[str, object]:
    return {
        "asset_id": "AAPL",
        "report_type": "10-K",
        "fiscal_date_end": datetime(2024, 3, 31, tzinfo=UTC),
        "reported_date": reported,
        "revenue": 1.0e9,
        "net_income": 1.0e8,
        "operating_cash_flow": 2.0e8,
        "total_shareholder_equity": 3.0e8,
        "total_liabilities": 4.0e8,
        "source": "sec",
    }


@pytest.mark.integration
def test_candle_partition_layout_on_disk(tmp_path: Path) -> None:
    """A6/I1: o write cria o layout Hive `asset=…/year=…/candle.parquet`."""
    store = ParquetMedallionStore(tmp_path)
    store.write(
        layer="bronze",
        table="candle",
        rows=[_candle_row("AAPL", datetime(2024, 1, 2, tzinfo=UTC), 100.0)],
    )

    expected = tmp_path / "bronze" / "candle" / "asset=AAPL" / "year=2024" / "candle.parquet"
    assert expected.is_file()


@pytest.mark.integration
def test_candle_dtype_round_trip(tmp_path: Path) -> None:
    """A6/I5: UTC + float32 + int64 preservados no round-trip.

    A fidelidade de dtype que importa para 2.2/2.3 está NO PARQUET em disco (lido
    de volta como DataFrame), não no scalar Python do `Row` (que `to_dict`
    converte para nativo). Asserta os dois níveis: (1) `read` devolve o instante
    UTC correto; (2) o arquivo Parquet preserva `float32`/`int64`/UTC exatos.
    """
    store = ParquetMedallionStore(tmp_path)
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    store.write(layer="bronze", table="candle", rows=[_candle_row("AAPL", ts, 100.0)])

    rows = store.read(layer="bronze", table="candle", filters={"asset": "AAPL"})
    assert len(rows) == 1
    got_ts = pd.Timestamp(rows[0]["timestamp"])  # type: ignore[arg-type]
    assert got_ts.tzinfo is not None
    assert got_ts.tz_convert("UTC") == pd.Timestamp(ts)
    assert int(rows[0]["volume"]) == _VOLUME  # type: ignore[call-overload]

    # Dtype exato no Parquet em disco (o que 2.2/2.3 releem como DataFrame).
    parquet = tmp_path / "bronze" / "candle" / "asset=AAPL" / "year=2024" / "candle.parquet"
    on_disk = pd.read_parquet(parquet)
    assert on_disk["open"].dtype == np.float32
    assert on_disk["close"].dtype == np.float32
    assert on_disk["volume"].dtype == np.int64
    assert str(on_disk["timestamp"].dtype) == "datetime64[ns, UTC]"


@pytest.mark.integration
def test_candle_append_only_across_writes(tmp_path: Path) -> None:
    """A6/I2: dois writes de PKs distintas acumulam (append-only) na mesma partição."""
    store = ParquetMedallionStore(tmp_path)
    store.write(
        layer="bronze",
        table="candle",
        rows=[_candle_row("AAPL", datetime(2024, 1, 2, tzinfo=UTC), 100.0)],
    )
    store.write(
        layer="bronze",
        table="candle",
        rows=[_candle_row("AAPL", datetime(2024, 1, 3, tzinfo=UTC), 101.0)],
    )

    rows = store.read(layer="bronze", table="candle", filters={"asset": "AAPL"})

    assert len(rows) == _TWO_ROWS


@pytest.mark.integration
def test_read_prunes_by_asset(tmp_path: Path) -> None:
    """A6/I7: `read({"asset": A})` com dois assets em disco devolve só A."""
    store = ParquetMedallionStore(tmp_path)
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    store.write(layer="bronze", table="candle", rows=[_candle_row("AAPL", ts, 100.0)])
    store.write(layer="bronze", table="candle", rows=[_candle_row("MSFT", ts, 300.0)])

    aapl = store.read(layer="bronze", table="candle", filters={"asset": "AAPL"})

    assert len(aapl) == 1
    assert all(r["asset"] == "AAPL" for r in aapl)
    # As partições de ambos os assets existem em disco (write real).
    assert (tmp_path / "bronze" / "candle" / "asset=MSFT" / "year=2024").is_dir()


@pytest.mark.integration
def test_fundamental_nat_reported_date_round_trip(tmp_path: Path) -> None:
    """A6/I5/C3: `reported_date` `NaT` é gravado e relido como nulo; float64 preservado."""
    store = ParquetMedallionStore(tmp_path)
    store.write(
        layer="bronze",
        table="fundamental",
        rows=[
            _fundamental_row(reported=None),  # vira NaT na coerção
            _fundamental_row_with_pk(reported=datetime(2024, 5, 1, tzinfo=UTC)),
        ],
    )

    rows = store.read(layer="bronze", table="fundamental", filters={"asset": "AAPL"})

    assert len(rows) == _TWO_ROWS
    nat_row = next(r for r in rows if r["report_type"] == "10-K")
    assert nat_row["reported_date"] is None
    assert isinstance(nat_row["revenue"], float)


def _fundamental_row_with_pk(reported: datetime | None) -> dict[str, object]:
    """Segunda linha de fundamental com PK distinta (report_type diferente)."""
    row = _fundamental_row(reported)
    row["report_type"] = "10-Q"
    return row
