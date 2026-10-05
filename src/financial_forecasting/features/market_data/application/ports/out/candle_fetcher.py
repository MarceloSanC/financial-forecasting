"""Port-out `CandleFetcher` (`Protocol`) — origem de candles (concept 2.2 §4 D2).

`CandleFetcher` é o port secundário (driven) do bounded context `market_data`:
abstrai a ORIGEM dos candles de um ativo (parquet raw existente — origem default;
yfinance ao vivo — não-default). A `application` (`IngestCandles`) depende SÓ
deste `Protocol` estrutural; os adapters concretos
(`ParquetRawCandleFetcher`/`YfinanceCandleFetcher`) o satisfazem por duck-typing
(NÃO herdam da `application`, ao contrário da ABC do old).

`Protocol` (não ABC) é a postura hexagonal do projeto (`hex-arch-python`, LAYOUT
§3), idêntica a `MedallionStore` (2.1) e `ExperimentTracker` (1.5). Importa a
entity `Candle` em runtime — a `application` pode importar o `domain`. NUNCA
importa `adapters`/`pandas`/`pyarrow` (inward-only; concept 2.2 I8/I11).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from financial_forecasting.features.market_data.domain.entities.candle import Candle


class CandleFetcher(Protocol):
    """Contrato de leitura de candles de um ativo, agnóstico de origem.

    Semântica temporal garantida por qualquer implementação:

    - `start`/`end` são tz-aware (naive → `ValueError` na fronteira do adapter);
      `start <= end` (concept 2.2 C5).
    - Cada `Candle.timestamp` devolvido é tz-aware em UTC; no diário (`1d`),
      normalizado a `00:00 UTC` (concept 2.2 I4) — para alinhar com a coluna
      `datetime64[ns, UTC]` a `00:00` do bronze.
    - O intervalo `[start, end]` é filtrado pela implementação; uma origem sem
      dados no intervalo devolve uma lista vazia, mas uma origem
      indisponível/ilegível levanta erro (não silencia em vazio; concept 2.2 C4).

    Tipos de erro do contrato (issue #69): exceções de biblioteca (`yfinance`,
    `pandas`, I/O) nunca atravessam o port — o adapter as traduz para o tipo abaixo,
    com a original em `__cause__` (`operational-evolution-policy.md` §4, invariante 2).
    """

    def fetch_candles(self, symbol: str, start: datetime, end: datetime) -> list[Candle]:
        """Devolve os candles diários de `symbol` no intervalo `[start, end]`.

        Raises:
            ValueError: entrada inválida do chamador, checada ANTES de tocar a origem —
                `start`/`end` naive, `start > end` (concept 2.2 C5) ou `symbol` que
                não vira `AssetId`.
            ApplicationError: origem indisponível ou ilegível — arquivo ausente ou
                corrompido, falha do provedor, resposta vazia ou sem as colunas
                esperadas (concept 2.2 C4/C6).
        """
        ...
