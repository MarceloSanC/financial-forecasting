"""Contract test do port `CandleFetcher` — paridade Fake ↔ ParquetRawCandleFetcher.

Um ÚNICO contrato parametrizado prova que ambas as implementações honram a MESMA
semântica observável (concept 2.2 I14/A4): `fetch_candles` devolve `list[Candle]`
com todos os `timestamp` tz-aware UTC normalizados a `00:00`, invariantes OHLC
respeitadas (garantidas pela construção da `Candle`), filtro por `[start, end]`,
`asset` injetado (= `symbol` pedido), e `start > end`/naive → `ValueError`.

O `real` (`ParquetRawCandleFetcher`) lê um parquet sintético escrito em `tmp_path`
com o MESMO layout/dtypes do raw (`<root>/<symbol>/candles_<symbol>_1d.parquet`,
OHLC `float32`, `volume` `int64`, `timestamp` UTC) — hermético e rápido. A
validação contra o raw real completo (4024 linhas) é da Task 08 / integração.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from financial_forecasting.features.market_data.adapters.out.parquet.parquet_raw_candle_fetcher import (  # noqa: E501
    ParquetRawCandleFetcher,
)

# `CandleFetcher` (Protocol, duck-typed) tipa a fixture parametrizada [fake, real].
from financial_forecasting.features.market_data.application.ports.out.candle_fetcher import (
    CandleFetcher,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle
from tests.fakes.features.market_data.in_memory_candle_fetcher import FakeCandleFetcher

_SYMBOL = "AAPL"
_START = datetime(2024, 1, 1, tzinfo=UTC)
_END = datetime(2024, 12, 31, tzinfo=UTC)
_VOLUME = 1_000_000
_TWO = 2


def _candles() -> list[Candle]:
    """Conjunto canônico de candles válidos (mesma fonte p/ fake e real)."""
    return [
        Candle(
            asset=_SYMBOL,
            timestamp=datetime(2024, 1, day, tzinfo=UTC),
            open=100.0 + day,
            high=105.0 + day,
            low=99.0 + day,
            close=104.0 + day,
            volume=_VOLUME + day,
        )
        for day in (2, 3, 4)
    ]


def _write_raw_parquet(root: Path, symbol: str, candles: list[Candle]) -> None:
    """Escreve o raw sintético no layout/dtypes esperados pelo adapter (sem `asset`)."""
    path = root / symbol / f"candles_{symbol}_1d.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "open": np.array([c.open for c in candles], dtype="float32"),
            "high": np.array([c.high for c in candles], dtype="float32"),
            "low": np.array([c.low for c in candles], dtype="float32"),
            "close": np.array([c.close for c in candles], dtype="float32"),
            "volume": np.array([c.volume for c in candles], dtype="int64"),
            "timestamp": pd.to_datetime([c.timestamp for c in candles], utc=True),
        }
    )
    frame.to_parquet(path)


def _build_fake(_tmp_path: Path) -> CandleFetcher:
    return FakeCandleFetcher(_candles())


def _build_real(tmp_path: Path) -> CandleFetcher:
    _write_raw_parquet(tmp_path, _SYMBOL, _candles())
    return ParquetRawCandleFetcher(tmp_path)


_FACTORIES: list[Callable[[Path], CandleFetcher]] = [_build_fake, _build_real]
_IDS = ["fake", "real"]


@pytest.fixture(params=_FACTORIES, ids=_IDS)
def fetcher(request: pytest.FixtureRequest, tmp_path: Path) -> CandleFetcher:
    """Parametriza o contrato sobre o fake e o adapter real (paridade fake↔real)."""
    factory: Callable[[Path], CandleFetcher] = request.param
    return factory(tmp_path)


@pytest.mark.contract
def test_fetch_returns_list_of_candles(fetcher: CandleFetcher) -> None:
    """Devolve uma `list[Candle]` não-vazia para o símbolo com dados."""
    candles = fetcher.fetch_candles(_SYMBOL, _START, _END)

    assert candles
    assert all(isinstance(c, Candle) for c in candles)
    assert len(candles) == len(_candles())


@pytest.mark.contract
def test_all_timestamps_are_utc_midnight(fetcher: CandleFetcher) -> None:
    """Todos os timestamps são tz-aware UTC normalizados a 00:00."""
    for candle in fetcher.fetch_candles(_SYMBOL, _START, _END):
        assert candle.timestamp.tzinfo == UTC
        assert candle.timestamp.hour == 0
        assert candle.timestamp.minute == 0


@pytest.mark.contract
def test_asset_is_the_requested_symbol(fetcher: CandleFetcher) -> None:
    """`asset` injetado é o símbolo pedido (I9/I5)."""
    for candle in fetcher.fetch_candles(_SYMBOL, _START, _END):
        assert candle.asset == _SYMBOL


@pytest.mark.contract
def test_filters_by_interval(fetcher: CandleFetcher) -> None:
    """Filtra por `[start, end]`: janela menor devolve menos candles."""
    narrow = fetcher.fetch_candles(
        _SYMBOL, datetime(2024, 1, 2, tzinfo=UTC), datetime(2024, 1, 3, tzinfo=UTC)
    )
    assert len(narrow) == _TWO
    assert all(c.timestamp <= datetime(2024, 1, 3, tzinfo=UTC) for c in narrow)


@pytest.mark.contract
def test_start_after_end_raises(fetcher: CandleFetcher) -> None:
    """`start > end` → ValueError (fronteira do contrato, C5)."""
    with pytest.raises(ValueError, match="start must be <= end"):
        fetcher.fetch_candles(_SYMBOL, _END, _START)


@pytest.mark.contract
def test_naive_bounds_raise(fetcher: CandleFetcher) -> None:
    """`start`/`end` naive → ValueError (C5)."""
    with pytest.raises(ValueError, match="timezone-aware"):
        fetcher.fetch_candles(_SYMBOL, datetime(2024, 1, 1), _END)  # naive start
