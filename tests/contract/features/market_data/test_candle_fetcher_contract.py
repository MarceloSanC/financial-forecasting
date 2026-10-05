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
from yfinance.exceptions import YFRateLimitError

from financial_forecasting.features.market_data.adapters.out.parquet.parquet_raw_candle_fetcher import (  # noqa: E501
    ParquetRawCandleFetcher,
)
from financial_forecasting.features.market_data.adapters.out.yfinance import (
    yfinance_candle_fetcher as yfinance_module,
)
from financial_forecasting.features.market_data.adapters.out.yfinance.yfinance_candle_fetcher import (  # noqa: E501
    YfinanceCandleFetcher,
)

# `CandleFetcher` (Protocol, duck-typed) tipa a fixture parametrizada [fake, real].
from financial_forecasting.features.market_data.application.ports.out.candle_fetcher import (
    CandleFetcher,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle
from financial_forecasting.shared.application.exceptions import ApplicationError
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
@pytest.mark.parametrize("spelling", ["aapl", " Aapl ", "AAPL.US"])
def test_other_spellings_resolve_to_the_canonical_asset(
    fetcher: CandleFetcher, spelling: str
) -> None:
    """Grafias do mesmo ativo leem a mesma série e injetam `asset` canônico (#69 c)."""
    candles = fetcher.fetch_candles(spelling, _START, _END)

    assert len(candles) == len(_candles())
    assert {c.asset for c in candles} == {_SYMBOL}


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


# -- origem indisponível: o tipo do contrato (issue #69) -----------------------
# Cada perna falha DE VERDADE onde dá: o parquet sem arquivo; o yfinance com a lib
# erguendo o próprio tipo (a função da lib é dublada, nunca o port). O fake simula o
# tipo do contrato no mesmo ponto em que o real toca a origem.

_UnavailableFactory = Callable[[Path, pytest.MonkeyPatch], CandleFetcher]


def _unavailable_fake(_tmp_path: Path, _monkeypatch: pytest.MonkeyPatch) -> CandleFetcher:
    return FakeCandleFetcher(_candles(), simulate_source_failure="source down")


def _unavailable_parquet(tmp_path: Path, _monkeypatch: pytest.MonkeyPatch) -> CandleFetcher:
    return ParquetRawCandleFetcher(tmp_path)  # sem arquivo: origem ausente


def _unavailable_yfinance(_tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CandleFetcher:
    # sem rede: a lib ergue o próprio tipo de erro (rate limit) em toda tentativa
    def _download(*_args: object, **_kwargs: object) -> pd.DataFrame:
        raise YFRateLimitError

    monkeypatch.setattr(yfinance_module.yf, "download", _download)
    monkeypatch.setattr(yfinance_module.sleep_time, "sleep", lambda _s: None)
    return YfinanceCandleFetcher(max_retries=0, retry_delay=0.0)


_UNAVAILABLE: dict[str, _UnavailableFactory] = {
    "fake": _unavailable_fake,
    "parquet": _unavailable_parquet,
    "yfinance": _unavailable_yfinance,
}


@pytest.fixture(params=list(_UNAVAILABLE))
def unavailable_fetcher(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> CandleFetcher:
    """Cada implementação do port com a origem fora do ar."""
    return _UNAVAILABLE[request.param](tmp_path, monkeypatch)


@pytest.mark.contract
def test_unavailable_source_raises_application_error(
    unavailable_fetcher: CandleFetcher,
) -> None:
    """Origem indisponível → `ApplicationError` em toda implementação (C4/C6)."""
    with pytest.raises(ApplicationError):
        unavailable_fetcher.fetch_candles(_SYMBOL, _START, _END)


@pytest.mark.contract
def test_caller_error_is_value_error_even_with_source_down(
    unavailable_fetcher: CandleFetcher,
) -> None:
    """Entrada inválida segue `ValueError` com a origem fora: é checada antes (C5)."""
    with pytest.raises(ValueError, match="start must be <= end"):
        unavailable_fetcher.fetch_candles(_SYMBOL, _END, _START)
    with pytest.raises(ValueError, match="asset_id"):
        unavailable_fetcher.fetch_candles("AA PL", _START, _END)


# -- linha corrompida no parquet real: origem ilegível (issue #69) ------------


@pytest.mark.contract
@pytest.mark.parametrize(
    ("column", "value"),
    [("high", 1.0), ("volume", float("nan"))],
    ids=["high-below-low", "volume-nan"],
)
def test_real_corrupted_row_raises_application_error(
    tmp_path: Path, column: str, value: float
) -> None:
    """Linha que a `Candle` recusa (high < low, `int(NaN)`) → `ApplicationError` com causa."""
    _write_raw_parquet(tmp_path, _SYMBOL, _candles())
    path = tmp_path / _SYMBOL / f"candles_{_SYMBOL}_1d.parquet"
    frame = pd.read_parquet(path)
    frame[column] = frame[column].astype("float64")
    frame.loc[0, column] = value
    frame.to_parquet(path)

    with pytest.raises(ApplicationError, match="unreadable row") as excinfo:
        ParquetRawCandleFetcher(tmp_path).fetch_candles(_SYMBOL, _START, _END)

    assert isinstance(excinfo.value.__cause__, ValueError)
