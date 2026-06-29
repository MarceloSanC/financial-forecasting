"""Teste de integração do `YfinanceCandleFetcher` — SEM rede (concept 2.2 I13/A7).

Usa `monkeypatch` de `yf.download` devolvendo um `DataFrame` fixture (com
`MultiIndex` de colunas e índice tz-naive, para exercitar a normalização) — NUNCA
bate na API ao vivo (robustez overnight). Cobre: mapeamento + normalização tz →
`00:00 UTC`, injeção de `asset`, colunas faltando → `ApplicationError` após
retries, `start > end`/naive → `ValueError`. Há um teste live OPCIONAL com
`skipif` (não roda no CI overnight).
"""

from __future__ import annotations

import os
import socket
from datetime import UTC, datetime

import pandas as pd
import pytest

from financial_forecasting.features.market_data.adapters.out.yfinance import (
    yfinance_candle_fetcher as module,
)
from financial_forecasting.features.market_data.adapters.out.yfinance.yfinance_candle_fetcher import (  # noqa: E501
    YfinanceCandleFetcher,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle
from financial_forecasting.shared.domain.exceptions.base import ApplicationError

_START = datetime(2024, 1, 1, tzinfo=UTC)
_END = datetime(2024, 1, 5, tzinfo=UTC)
_THREE = 3


def _multiindex_naive_frame() -> pd.DataFrame:
    """DataFrame estilo yfinance: colunas MultiIndex (níveis OHLCV x ticker), índice naive."""
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])  # tz-naive
    columns = pd.MultiIndex.from_product([["Open", "High", "Low", "Close", "Volume"], ["AAPL"]])
    data = {
        ("Open", "AAPL"): [100.0, 101.0, 102.0],
        ("High", "AAPL"): [105.0, 106.0, 107.0],
        ("Low", "AAPL"): [99.0, 100.0, 101.0],
        ("Close", "AAPL"): [104.0, 105.0, 106.0],
        ("Volume", "AAPL"): [1_000_000, 1_100_000, 1_200_000],
    }
    return pd.DataFrame(data, index=index, columns=columns)


def _single_level_aware_frame() -> pd.DataFrame:
    """DataFrame yfinance single-ticker: colunas planas (1 nível) + índice JÁ tz-aware UTC.

    Exercita o caminho COMPLEMENTAR ao MultiIndex/naive: `nlevels == 1` (sem
    achatar colunas) e índice já tz-aware (`_index_to_datetime` NÃO relocaliza —
    branch `135->137` do adapter).
    """
    index = pd.to_datetime(["2024-01-02", "2024-01-03"], utc=True)  # já tz-aware
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [105.0, 106.0],
            "Low": [99.0, 100.0],
            "Close": [104.0, 105.0],
            "Volume": [1_000_000, 1_100_000],
        },
        index=index,
    )


@pytest.mark.integration
def test_maps_and_normalizes_multiindex_naive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Normaliza MultiIndex + índice naive → Candles UTC 00:00 com asset injetado."""
    monkeypatch.setattr(module.yf, "download", lambda *a, **k: _multiindex_naive_frame())

    candles = YfinanceCandleFetcher().fetch_candles("AAPL", _START, _END)

    assert len(candles) == _THREE
    assert all(isinstance(c, Candle) for c in candles)
    for candle in candles:
        assert candle.asset == "AAPL"
        assert candle.timestamp.tzinfo == UTC
        assert candle.timestamp.hour == 0
    assert candles[0].timestamp == datetime(2024, 1, 2, tzinfo=UTC)
    assert candles[0].close == pytest.approx(104.0)


@pytest.mark.integration
def test_maps_single_level_columns_with_aware_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """Colunas planas (nlevels==1) + índice já tz-aware → Candles UTC 00:00 corretos.

    Complemento do teste MultiIndex/naive: cobre o branch-false de
    `nlevels > 1` (não achata) e o branch-false de `_index_to_datetime`
    (índice já aware, sem relocalizar — `135->137`). Gaps fechados na auditoria.
    """
    monkeypatch.setattr(module.yf, "download", lambda *a, **k: _single_level_aware_frame())

    candles = YfinanceCandleFetcher().fetch_candles("AAPL", _START, _END)

    assert len(candles) == len(["d2", "d3"])
    for candle in candles:
        assert candle.asset == "AAPL"
        assert candle.timestamp.tzinfo == UTC
        assert candle.timestamp.hour == 0
    assert candles[0].timestamp == datetime(2024, 1, 2, tzinfo=UTC)
    assert candles[1].timestamp == datetime(2024, 1, 3, tzinfo=UTC)
    assert candles[0].close == pytest.approx(104.0)


@pytest.mark.integration
def test_empty_response_raises_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """`df` vazio após esgotar retries → ApplicationError (C6)."""
    monkeypatch.setattr(module.yf, "download", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(module.sleep_time, "sleep", lambda _s: None)

    with pytest.raises(ApplicationError, match="after"):
        YfinanceCandleFetcher(max_retries=1, retry_delay=0.0).fetch_candles("AAPL", _START, _END)


@pytest.mark.integration
def test_missing_columns_raises_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Colunas OHLCV faltando após retries → ApplicationError (C6)."""
    bad = pd.DataFrame({"Open": [1.0]}, index=pd.to_datetime(["2024-01-02"]))
    monkeypatch.setattr(module.yf, "download", lambda *a, **k: bad)
    monkeypatch.setattr(module.sleep_time, "sleep", lambda _s: None)

    with pytest.raises(ApplicationError):
        YfinanceCandleFetcher(max_retries=1, retry_delay=0.0).fetch_candles("AAPL", _START, _END)


@pytest.mark.integration
def test_start_after_end_raises() -> None:
    """`start > end` → ValueError (sem nem chamar yf.download)."""
    with pytest.raises(ValueError, match="start must be <= end"):
        YfinanceCandleFetcher().fetch_candles("AAPL", _END, _START)


@pytest.mark.integration
def test_naive_bounds_raise() -> None:
    """`start`/`end` naive → ValueError (C5)."""
    with pytest.raises(ValueError, match="timezone-aware"):
        YfinanceCandleFetcher().fetch_candles("AAPL", datetime(2024, 1, 1), _END)


def _has_network() -> bool:
    try:
        socket.create_connection(("query1.finance.yahoo.com", 443), timeout=2).close()
    except OSError:
        return False
    return True


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("FF_LIVE_YFINANCE") != "1" or not _has_network(),
    reason="teste live opcional: requer FF_LIVE_YFINANCE=1 e rede (não roda no CI overnight)",
)
def test_live_fetch_optional() -> None:  # pragma: no cover - live, opt-in
    """Teste LIVE opt-in (não roda no CI): bate na API real só se habilitado + rede."""
    candles = YfinanceCandleFetcher().fetch_candles(
        "AAPL", datetime(2024, 1, 2, tzinfo=UTC), datetime(2024, 1, 10, tzinfo=UTC)
    )
    assert candles
    assert all(c.asset == "AAPL" for c in candles)
