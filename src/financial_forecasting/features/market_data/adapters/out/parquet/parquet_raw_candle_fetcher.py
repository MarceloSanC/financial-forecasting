"""Adapter `ParquetRawCandleFetcher` — origem DEFAULT da ingestão (concept 2.2 D3).

Lê o parquet raw EXISTENTE de candles diários
(`data/raw/market/candles/<symbol>/candles_<symbol>_1d.parquet`, 4024 linhas para
AAPL) e mapeia cada linha para uma entity `Candle`, sem re-baixar nada — o reuso
de `raw/` é decisão do autor (ledger §A) e a origem default do pipeline
(`YfinanceCandleFetcher` existe mas NÃO é default). Implementa o port
`CandleFetcher` por duck-typing.

`pandas`/`pyarrow` vivem SÓ aqui (concept 2.2 I8/D3): o gate `import-linter`
`hexagonal-layers` reprova se a `application`/`domain` do BC importar essas libs.

Mapeamento (concept 2.2 §9):
- o raw NÃO tem coluna `asset`; o adapter injeta `asset=symbol` ao construir cada
  `Candle` (concept 2.2 I9/D4);
- `timestamp` é convertido para tz-aware UTC e normalizado a `00:00 UTC`
  (`normalize_to_utc_day`, Task 02);
- OHLC/volume viram `float`/`int` Python; as invariantes OHLC fortes da `Candle`
  são validadas na construção (concept 2.2 I1).

Erros (concept 2.2 C4/C5):
- `start`/`end` naive ou `start > end` → `ValueError` (fronteira);
- arquivo de origem ausente/ilegível → `ApplicationError` (NÃO silencia em lista
  vazia).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from financial_forecasting.features.market_data.domain.entities.candle import Candle
from financial_forecasting.features.market_data.domain.time.utc import (
    normalize_to_utc_day,
    require_tz_aware,
    to_utc,
)
from financial_forecasting.shared.domain.exceptions.base import ApplicationError

# Raiz default do raw de candles (simples-e-trocável; injetável p/ teste —
# concept 2.2 §13). Layout: <root>/<symbol>/candles_<symbol>_1d.parquet.
DEFAULT_RAW_ROOT = Path("data/raw/market/candles")

_REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume", "timestamp")


class ParquetRawCandleFetcher:
    """Implementação do `CandleFetcher` que lê o raw existente (origem default)."""

    def __init__(self, raw_root: Path | str = DEFAULT_RAW_ROOT) -> None:
        self._raw_root = Path(raw_root)

    def _parquet_path(self, symbol: str) -> Path:
        return self._raw_root / symbol / f"candles_{symbol}_1d.parquet"

    def fetch_candles(self, symbol: str, start: datetime, end: datetime) -> list[Candle]:
        """Lê e mapeia os candles de `symbol` do raw, filtrando `[start, end]`."""
        require_tz_aware(start, "start")
        require_tz_aware(end, "end")
        if start > end:
            raise ValueError("start must be <= end")

        path = self._parquet_path(symbol)
        if not path.exists():
            raise ApplicationError(f"Raw candle source not found for {symbol!r}: {path}")
        try:
            frame = pd.read_parquet(path)
        except (OSError, ValueError, pd.errors.ParserError) as exc:  # pragma: no cover
            raise ApplicationError(
                f"Raw candle source unreadable for {symbol!r}: {path} ({exc})"
            ) from exc

        missing = [col for col in _REQUIRED_COLUMNS if col not in frame.columns]
        if missing:
            raise ApplicationError(
                f"Raw candle source for {symbol!r} missing columns {missing}: {path}"
            )

        start_utc = to_utc(start)
        end_utc = to_utc(end)
        candles: list[Candle] = []
        for record in frame.to_dict(orient="records"):
            timestamp = normalize_to_utc_day(_as_datetime(record["timestamp"]))
            if not (start_utc <= timestamp <= end_utc):
                continue
            candles.append(
                Candle(
                    asset=symbol,
                    timestamp=timestamp,
                    open=float(record["open"]),
                    high=float(record["high"]),
                    low=float(record["low"]),
                    close=float(record["close"]),
                    volume=int(record["volume"]),
                )
            )
        candles.sort(key=lambda c: c.timestamp)
        return candles


def _as_datetime(value: object) -> datetime:
    """Converte um valor de timestamp do parquet (pd.Timestamp/str) em `datetime`."""
    converted: datetime = pd.Timestamp(value).to_pydatetime()
    return converted
