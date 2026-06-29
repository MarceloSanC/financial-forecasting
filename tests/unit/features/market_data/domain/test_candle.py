"""Testes da entity `Candle` — invariantes OHLC fortes (concept 2.2 §5, A1).

Cobre um `Candle` válido + uma violação por invariante (I1 nas três relações
OHLC, I2 não-negatividade, I3 sem nulos, I4 timestamp naive) → cada uma
`ValueError`. Domínio puro: nenhum I/O, só `datetime` stdlib.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from financial_forecasting.features.market_data.domain.entities.candle import Candle

_TS = datetime(2024, 1, 2, tzinfo=UTC)
_VOLUME = 1_000_000


def _valid_kwargs() -> dict[str, Any]:
    return {
        "asset": "AAPL",
        "timestamp": _TS,
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 104.0,
        "volume": _VOLUME,
    }


@pytest.mark.unit
def test_valid_candle_is_constructed() -> None:
    """Candle válido constrói e preserva os campos (identidade `(asset, timestamp)`)."""
    candle = Candle(**_valid_kwargs())

    assert candle.asset == "AAPL"
    assert candle.timestamp == _TS
    assert candle.open == pytest.approx(100.0)
    assert candle.high == pytest.approx(105.0)
    assert candle.low == pytest.approx(99.0)
    assert candle.close == pytest.approx(104.0)
    assert candle.volume == _VOLUME


@pytest.mark.unit
def test_candle_is_frozen() -> None:
    """Candle é imutável (frozen dataclass)."""
    candle = Candle(**_valid_kwargs())
    with pytest.raises(AttributeError):
        candle.close = 1.0  # type: ignore[misc]


@pytest.mark.unit
def test_equality_by_value() -> None:
    """Frozen dataclass tem igualdade por valor (mesma identidade lógica + dados)."""
    assert Candle(**_valid_kwargs()) == Candle(**_valid_kwargs())


# -- I1 — OHLC consistente ---------------------------------------------------


@pytest.mark.unit
def test_high_below_close_raises() -> None:
    """I1: `high < close` (logo < max(open, close)) → ValueError."""
    kwargs = _valid_kwargs()
    kwargs["high"] = 103.0  # < close=104.0
    with pytest.raises(ValueError, match="high"):
        Candle(**kwargs)


@pytest.mark.unit
def test_low_above_open_raises() -> None:
    """I1: `low > open` (logo > min(open, close)) → ValueError."""
    kwargs = _valid_kwargs()
    kwargs["low"] = 101.0  # > open=100.0
    with pytest.raises(ValueError, match="low"):
        Candle(**kwargs)


@pytest.mark.unit
def test_high_below_low_raises() -> None:
    """I1: `high < low` → ValueError."""
    kwargs = _valid_kwargs()
    kwargs["open"] = 100.0
    kwargs["close"] = 100.0
    kwargs["high"] = 98.0
    kwargs["low"] = 99.0
    with pytest.raises(ValueError, match="high"):
        Candle(**kwargs)


# -- I2 — não-negatividade ---------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
def test_negative_value_raises(field: str) -> None:
    """I2: qualquer OHLCV negativo → ValueError."""
    kwargs = _valid_kwargs()
    # Mantém consistência OHLC alterando só o campo testado para negativo.
    kwargs.update(open=0.0, high=0.0, low=0.0, close=0.0, volume=0)
    kwargs[field] = -1 if field == "volume" else -1.0
    with pytest.raises(ValueError, match="non-negative"):
        Candle(**kwargs)


# -- I3 — sem nulos ----------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("field", ["asset", "timestamp", "open", "high", "low", "close", "volume"])
def test_none_field_raises(field: str) -> None:
    """I3: qualquer campo `None` → ValueError."""
    kwargs = _valid_kwargs()
    kwargs[field] = None
    with pytest.raises(ValueError, match="None"):
        Candle(**kwargs)


# -- I4 — timestamp tz-aware -------------------------------------------------


@pytest.mark.unit
def test_naive_timestamp_raises() -> None:
    """I4: `timestamp` naive (sem tz) → ValueError."""
    kwargs = _valid_kwargs()
    kwargs["timestamp"] = datetime(2024, 1, 2)
    with pytest.raises(ValueError, match="timezone-aware"):
        Candle(**kwargs)
