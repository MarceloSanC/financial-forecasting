"""Use case `IngestCandles` + DTOs frozen (concept 2.2 §4, A5).

Orquestra a ingestão de candles diários para a bronze: lê de uma origem
(`CandleFetcher`, port-out — default = raw existente), mapeia cada `Candle → Row`
INJETANDO `asset` (o raw não tem essa coluna; o bronze a exige — concept 2.2
I9/D4) e grava via `MedallionStore` (port-out 2.1) em `(bronze, candle)`,
append-only. Recebe/devolve DTO frozen — NUNCA vaza `Candle` nem `tuple` para
fora (concept 2.2 I7/D6, contraste com o `tuple[int, int]` do old).

A coerção de dtype para o schema bronze (`open/high/low/close` `float32`,
`volume` `int64`) é responsabilidade do adapter de escrita
(`ParquetMedallionStore._coerce`, 2.1): o use case permanece stdlib-only (sem
`pandas`/`numpy`), produzindo `Row`s com `float`/`int` Python. A rede de
segurança `pandera` (`coerce=False`) no `write` rejeita qualquer drift (C3).

A invariante de coleção "sem duplicados" (I6) é delegada à PK lógica
`(asset, timestamp)` do `MedallionStore`: colisão sem `overwrite` propaga
`DuplicateKeyError` (concept 2.2 C2/D5) — o use case NÃO reimplementa dedup.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from financial_forecasting.features.market_data.application.ports.out.candle_fetcher import (
    CandleFetcher,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle
from financial_forecasting.features.market_data.domain.time.utc import require_tz_aware
from financial_forecasting.shared.application.ports.out.medallion_store import (
    MedallionStore,
    Row,
)

_BRONZE_LAYER = "bronze"
_CANDLE_TABLE = "candle"


@dataclass(frozen=True)
class IngestCandlesRequest:
    """Comando de ingestão: ativo + intervalo tz-aware (concept 2.2 §4)."""

    asset: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class IngestCandlesResult:
    """Resultado da ingestão: contagem gravada + metadados (NUNCA `Candle`)."""

    asset: str
    ingested: int
    start: datetime
    end: datetime


def _candle_to_row(candle: Candle) -> Row:
    """Mapeia `Candle → Row` bronze; o `asset` já está na entity (identidade I5).

    Produz `float`/`int` Python (sem coerção de dtype aqui — I10): o adapter de
    escrita coage para `float32`/`int64` do schema bronze. As chaves casam
    EXATAMENTE as colunas do schema `CANDLE` (2.1): `asset`, `timestamp`,
    `open`, `high`, `low`, `close`, `volume`.
    """
    return {
        "asset": candle.asset,
        "timestamp": candle.timestamp,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    }


class IngestCandles:
    """Use case: ingere candles de um ativo para a bronze via `MedallionStore`."""

    def __init__(self, fetcher: CandleFetcher, store: MedallionStore) -> None:
        self._fetcher = fetcher
        self._store = store

    def execute(self, request: IngestCandlesRequest) -> IngestCandlesResult:
        """Lê candles da origem, injeta `asset` e grava `(bronze, candle)`.

        Valida o intervalo na fronteira (`start`/`end` tz-aware e `start <= end`,
        concept 2.2 C5). A escrita é append-only (`overwrite=False`): re-ingerir
        uma PK lógica já presente propaga `DuplicateKeyError` do store (C2).
        Devolve `IngestCandlesResult` com a contagem ingerida (NUNCA `Candle`).
        """
        require_tz_aware(request.start, "start")
        require_tz_aware(request.end, "end")
        if request.start > request.end:
            raise ValueError("start must be <= end")

        candles = self._fetcher.fetch_candles(
            symbol=request.asset, start=request.start, end=request.end
        )
        rows: list[Mapping[str, object]] = [_candle_to_row(c) for c in candles]
        self._store.write(layer=_BRONZE_LAYER, table=_CANDLE_TABLE, rows=rows, overwrite=False)

        return IngestCandlesResult(
            asset=request.asset,
            ingested=len(rows),
            start=request.start,
            end=request.end,
        )
