"""Testes do use case `IngestCandles` (concept 2.2 §5/§6, A5).

Usa fakes COMPORTAMENTAIS (não mocks): `FakeCandleFetcher` (novo) +
`FakeMedallionStore` (reusado da 2.1). Cobre: `asset` injetado em toda `Row`;
chamada a `write` com `layer="bronze"`/`table="candle"`/`overwrite=False`
(verificada pelo round-trip no store); `Result.ingested` == nº de candles;
retorno é `IngestCandlesResult` (nunca `Candle`/`tuple`); colisão de PK propaga
`DuplicateKeyError`; `start > end`/naive → `ValueError`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from financial_forecasting.features.market_data.application.use_cases.ingest_candles import (
    IngestCandles,
    IngestCandlesRequest,
    IngestCandlesResult,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle
from financial_forecasting.shared.domain.exceptions.base import DuplicateKeyError
from tests.fakes.features.market_data.in_memory_candle_fetcher import FakeCandleFetcher
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

_START = datetime(2024, 1, 1, tzinfo=UTC)
_END = datetime(2024, 12, 31, tzinfo=UTC)
_EXPECTED_COLUMNS = {"asset", "timestamp", "open", "high", "low", "close", "volume"}
_VOLUME = 1_000_000


def _candle(asset: str, day: int, close: float) -> Candle:
    return Candle(
        asset=asset,
        timestamp=datetime(2024, 1, day, tzinfo=UTC),
        open=close - 1.0,
        high=close + 1.0,
        low=close - 2.0,
        close=close,
        volume=_VOLUME,
    )


def _request(asset: str = "AAPL") -> IngestCandlesRequest:
    return IngestCandlesRequest(asset=asset, start=_START, end=_END)


@pytest.mark.unit
def test_ingests_and_returns_result_dto() -> None:
    """Devolve IngestCandlesResult com a contagem ingerida (nunca Candle/tuple)."""
    fetcher = FakeCandleFetcher([_candle("AAPL", 2, 100.0), _candle("AAPL", 3, 101.0)])
    store = FakeMedallionStore()
    use_case = IngestCandles(fetcher, store)

    result = use_case.execute(_request())

    assert isinstance(result, IngestCandlesResult)
    assert result.asset == "AAPL"
    assert result.ingested == len([_candle("AAPL", 2, 100.0), _candle("AAPL", 3, 101.0)])
    assert result.start == _START
    assert result.end == _END


@pytest.mark.unit
def test_writes_to_bronze_candle_with_asset_injected() -> None:
    """Grava em (bronze, candle); `asset` presente em TODA Row (I9), colunas do schema."""
    fetcher = FakeCandleFetcher([_candle("AAPL", 2, 100.0), _candle("AAPL", 3, 101.0)])
    store = FakeMedallionStore()
    use_case = IngestCandles(fetcher, store)

    use_case.execute(_request())

    rows = store.read(layer="bronze", table="candle", filters={"asset": "AAPL"})
    assert len(rows) == len(["d2", "d3"])
    for row in rows:
        assert set(row) == _EXPECTED_COLUMNS
        assert row["asset"] == "AAPL"


@pytest.mark.unit
def test_row_values_are_plain_python_floats_and_ints() -> None:
    """Mapeamento Candle->Row preserva forma float/int Python (coerção é do adapter, I10)."""
    fetcher = FakeCandleFetcher([_candle("AAPL", 2, 100.0)])
    store = FakeMedallionStore()
    IngestCandles(fetcher, store).execute(_request())

    row = store.read(layer="bronze", table="candle", filters={"asset": "AAPL"})[0]
    assert isinstance(row["close"], float)
    assert isinstance(row["volume"], int)
    assert row["volume"] == _VOLUME


@pytest.mark.unit
def test_empty_fetch_writes_nothing_and_counts_zero() -> None:
    """Sem candles na origem: ingested == 0 e nada gravado (write de [] é no-op)."""
    store = FakeMedallionStore()
    result = IngestCandles(FakeCandleFetcher([]), store).execute(_request())

    assert result.ingested == 0
    assert list(store.read(layer="bronze", table="candle", filters={"asset": "AAPL"})) == []


@pytest.mark.unit
def test_duplicate_pk_propagates_duplicate_key_error() -> None:
    """C2/I6: re-ingerir a MESMA PK lógica sem overwrite propaga DuplicateKeyError."""
    fetcher = FakeCandleFetcher([_candle("AAPL", 2, 100.0)])
    store = FakeMedallionStore()
    use_case = IngestCandles(fetcher, store)

    use_case.execute(_request())
    with pytest.raises(DuplicateKeyError):
        use_case.execute(_request())


@pytest.mark.unit
def test_naive_start_raises() -> None:
    """C5: `start` naive → ValueError, antes de qualquer fetch/write."""
    use_case = IngestCandles(FakeCandleFetcher([]), FakeMedallionStore())
    request = IngestCandlesRequest(
        asset="AAPL",
        start=datetime(2024, 1, 1),  # naive
        end=_END,
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        use_case.execute(request)


@pytest.mark.unit
def test_naive_end_raises() -> None:
    """C5: `end` naive (com `start` aware) → ValueError, antes de qualquer fetch/write.

    Mutação coberta: remover `require_tz_aware(request.end, "end")` deixaria
    passar um `end` naive — só o `start` naive era testado (gap fechado na auditoria).
    """
    use_case = IngestCandles(FakeCandleFetcher([]), FakeMedallionStore())
    request = IngestCandlesRequest(
        asset="AAPL",
        start=_START,
        end=datetime(2024, 12, 31),  # naive
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        use_case.execute(request)


@pytest.mark.unit
def test_start_after_end_raises() -> None:
    """C5: `start > end` → ValueError."""
    use_case = IngestCandles(FakeCandleFetcher([]), FakeMedallionStore())
    request = IngestCandlesRequest(asset="AAPL", start=_END, end=_START)
    with pytest.raises(ValueError, match="start must be <= end"):
        use_case.execute(request)
