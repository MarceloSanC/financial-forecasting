"""Adapter `YfinanceCandleFetcher` — origem NÃO-default (concept 2.2 D3).

Porta do old (`financial-time-series-forecasting/src/adapters/yfinance_candle_fetcher.py`)
com julgamento: retry + backoff exponencial, normalização de `MultiIndex`, tz →
`00:00 UTC` (`normalize_to_utc_day`, Task 02), validação das colunas
`Open/High/Low/Close/Volume`. Implementa o port `CandleFetcher` por duck-typing.

NÃO é a origem default — o pipeline reusa o raw existente
(`ParquetRawCandleFetcher`). Este adapter existe para re-ingestão ao vivo
consciente; o teste de integração usa `monkeypatch` de `yf.download` e NUNCA bate
na API ao vivo (robustez overnight, concept 2.2 I13). `yfinance` (sem chave de
API) vive SÓ aqui (concept 2.2 I8).

Diferenças vs old (corrigidas com julgamento):
- injeta `asset` em cada `Candle` (o old não tinha `asset`; o bronze exige
  — concept 2.2 I9/D4), na forma canônica de `AssetId.parse` (issue #69 c); a
  chamada ao `yf.download` usa o símbolo como veio;
- normalização tz via `normalize_to_utc_day` (helper de domínio, Task 02), em vez
  de `datetime.combine` inline;
- esgotados os retries → `ApplicationError` (não `RuntimeError` cru), coerente com
  a hierarquia de exceções do BC (concept 2.2 C6), com a falha da última tentativa
  em `__cause__` (issue #69).

Tradução de exceção (issue #69), por tipos ENUMERADOS — nunca `except Exception`.
Em yfinance 1.5.1, `yf.download` engole a falha por ticker (o `except Exception` de
`multi._download_one`; rede fora vira `DNSError` logado e frame vazio), e a tentativa
sem dados vira o nosso `ValueError`. O que ainda pode escapar da chamada é a raiz
`YFException` (`YFDataException`, `YFRateLimitError`…, subclasses diretas de
`Exception`) e `OSError` (a família de erros do `curl_cffi` descende dele). `TypeError`
fica FORA: neste caminho ele só nasce de bug nosso, e deve propagar.
"""

from __future__ import annotations

import logging
import time as sleep_time
from datetime import datetime

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFException

from financial_forecasting.features.market_data.domain.entities.candle import Candle
from financial_forecasting.features.market_data.domain.time.utc import (
    normalize_to_utc_day,
    require_tz_aware,
    to_utc,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.value_objects.asset_id import AssetId

logger = logging.getLogger(__name__)

_REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
_MULTIINDEX_LEVELS = 1
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY = 1.0
# Falha de UMA tentativa (retentável): o vocabulário da lib (`YFException`, `OSError`,
# e `KeyError` do pandas dentro do `download` — concat/reindex dos frames por ticker,
# fora do `except` por ticker) e o que o nosso mapeamento ergue sobre um frame ruim
# (`ValueError` — vazio, colunas faltando, OHLC que viola a `Candle`, `int(NaN)`). O
# acesso `row["Open"]` do mapeamento não gera `KeyError`: as colunas já foram checadas.
_ATTEMPT_ERRORS: tuple[type[Exception], ...] = (YFException, OSError, ValueError, KeyError)


class YfinanceCandleFetcher:
    """Implementação do `CandleFetcher` sobre `yfinance` (origem não-default)."""

    def __init__(
        self,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_delay: float = _DEFAULT_RETRY_DELAY,
    ) -> None:
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    def fetch_candles(self, symbol: str, start: datetime, end: datetime) -> list[Candle]:
        """Baixa candles diários de `symbol` em `[start, end]` com retry/backoff."""
        require_tz_aware(start, "start")
        require_tz_aware(end, "end")
        start_utc = to_utc(start)
        end_utc = to_utc(end)
        if start_utc > end_utc:
            raise ValueError("start must be <= end")
        # o provedor recebe o símbolo como veio (o sufixo de bolsa importa para ele,
        # ex. `PETR4.SA`); a entidade leva a identidade canônica (#69 c). Fora do
        # laço: símbolo inválido falha já, sem consumir retries.
        asset = AssetId.parse(symbol).value

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return self._download_and_map(symbol, asset, start_utc, end_utc)
            except _ATTEMPT_ERRORS as exc:
                last_error = exc
                logger.warning(
                    "yfinance fetch attempt failed",
                    extra={"symbol": symbol, "attempt": attempt + 1, "error": str(exc)},
                )
                if attempt < self._max_retries:
                    sleep_time.sleep(self._retry_delay * (2**attempt))

        raise ApplicationError(
            f"Failed to fetch {symbol!r} after {self._max_retries} retries: {last_error}"
        ) from last_error

    def _download_and_map(
        self, symbol: str, asset: str, start_utc: datetime, end_utc: datetime
    ) -> list[Candle]:
        """Uma tentativa: baixa, normaliza colunas/tz e mapeia para `list[Candle]`."""
        frame = yf.download(
            symbol,
            start=start_utc.strftime("%Y-%m-%d"),
            end=end_utc.strftime("%Y-%m-%d"),
            interval="1d",
            progress=False,
            auto_adjust=False,
        )
        if frame is None or frame.empty:
            raise ValueError(f"No data returned for {symbol!r}")

        # Normaliza MultiIndex de colunas (yfinance pode devolver níveis).
        if getattr(frame.columns, "nlevels", _MULTIINDEX_LEVELS) > _MULTIINDEX_LEVELS:
            frame = frame.copy()
            frame.columns = frame.columns.get_level_values(0)

        missing = [col for col in _REQUIRED_COLUMNS if col not in frame.columns]
        if missing:
            raise ValueError(f"Missing columns in response for {symbol!r}: {missing}")

        candles: list[Candle] = []
        for index, row in frame.iterrows():
            timestamp = normalize_to_utc_day(_index_to_datetime(index))
            candles.append(
                Candle(
                    asset=asset,
                    timestamp=timestamp,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row["Volume"]),
                )
            )
        candles.sort(key=lambda c: c.timestamp)
        return candles


def _index_to_datetime(index: object) -> datetime:
    """Converte o índice temporal (pd.Timestamp, possivelmente tz-naive) em UTC.

    `pandas` vive no adapter (junto de `yfinance`); naive → assume UTC, para
    `normalize_to_utc_day` (que exige tz-aware) não falhar com índices tz-naive que
    o yfinance às vezes devolve.
    """
    timestamp = pd.Timestamp(index)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    result: datetime = timestamp.to_pydatetime()
    return result
