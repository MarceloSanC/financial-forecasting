"""Integração do `ParquetRawCandleFetcher` contra o raw REAL (concept 2.2 A6, Task 08).

Ponto de verdade do risco "invariantes OHLC fortes rejeitam linhas legítimas do
raw" (concept 2.2 §10): lê as 4024 linhas reais de AAPL via o adapter default e
prova que TODAS produzem `Candle`s válidos (invariantes OHLC fortes da entity
aplicadas na construção), `asset` injetado, timestamps tz-aware UTC a `00:00`, e
contagem == 4024. Se nenhuma linha reprova, o risco está fechado (e a Task 08 é a
confirmação dele). `skipif` se o raw não estiver presente (robustez).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from financial_forecasting.features.market_data.adapters.out.parquet.parquet_raw_candle_fetcher import (  # noqa: E501
    DEFAULT_RAW_ROOT,
    ParquetRawCandleFetcher,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle
from financial_forecasting.shared.domain.exceptions.base import ApplicationError

_SYMBOL = "AAPL"
_EXPECTED_ROWS = 4024
_WIDE_START = datetime(1990, 1, 1, tzinfo=UTC)
_WIDE_END = datetime(2100, 1, 1, tzinfo=UTC)
_RAW_PATH = DEFAULT_RAW_ROOT / _SYMBOL / f"candles_{_SYMBOL}_1d.parquet"

pytestmark = pytest.mark.skipif(
    not _RAW_PATH.exists(),
    reason=f"raw real ausente: {_RAW_PATH}",
)


@pytest.fixture
def candles() -> list[Candle]:
    return ParquetRawCandleFetcher().fetch_candles(_SYMBOL, _WIDE_START, _WIDE_END)


@pytest.mark.integration
def test_reads_all_real_rows(candles: list[Candle]) -> None:
    """Lê as 4024 linhas reais sem perder/rejeitar nenhuma (invariantes OHLC passam)."""
    assert len(candles) == _EXPECTED_ROWS
    assert all(isinstance(c, Candle) for c in candles)


@pytest.mark.integration
def test_all_real_candles_are_valid_aapl_utc(candles: list[Candle]) -> None:
    """Todo Candle real: asset=AAPL injetado, timestamp tz-aware UTC a 00:00."""
    for candle in candles:
        assert candle.asset == _SYMBOL
        assert candle.timestamp.tzinfo == UTC
        assert candle.timestamp.hour == 0
        assert candle.timestamp.minute == 0


@pytest.mark.integration
def test_real_candles_sorted_by_timestamp(candles: list[Candle]) -> None:
    """Os candles voltam ordenados por timestamp ascendente."""
    timestamps = [c.timestamp for c in candles]
    assert timestamps == sorted(timestamps)


@pytest.mark.integration
def test_missing_symbol_raises_application_error() -> None:
    """Símbolo sem raw → ApplicationError (não lista vazia, C4)."""
    fetcher = ParquetRawCandleFetcher(Path("data/raw/market/candles"))
    with pytest.raises(ApplicationError, match="not found"):
        fetcher.fetch_candles("NO_SUCH_SYMBOL", _WIDE_START, _WIDE_END)


@pytest.mark.integration
def test_raw_missing_columns_raises_application_error(tmp_path: Path) -> None:
    """Raw presente mas sem colunas OHLCV → ApplicationError (C4, não lista vazia)."""
    symbol = "BADCOLS"
    path = tmp_path / symbol / f"candles_{symbol}_1d.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Falta `volume` (e demais OHLC) — só `timestamp`.
    pd.DataFrame({"timestamp": pd.to_datetime(["2024-01-02"], utc=True)}).to_parquet(path)

    with pytest.raises(ApplicationError, match="missing columns"):
        ParquetRawCandleFetcher(tmp_path).fetch_candles(symbol, _WIDE_START, _WIDE_END)
