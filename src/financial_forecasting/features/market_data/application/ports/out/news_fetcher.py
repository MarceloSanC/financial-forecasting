"""Port-out `NewsFetcher` (`Protocol`) — origem de notícias (concept 2.3 §4 D1).

`NewsFetcher` é o port secundário (driven) do bounded context `market_data` para
notícias: abstrai a ORIGEM dos artigos de um ativo (parquet raw existente — origem
default; Alpha Vantage `NEWS_SENTIMENT` ao vivo — não-default). A `application`
(`IngestNews`) depende SÓ deste `Protocol` estrutural; os adapters concretos
(`ParquetRawNewsFetcher`/`AlphaVantageNewsFetcher`) o satisfazem por duck-typing
(NÃO herdam da `application`, ao contrário da ABC do old).

`Protocol` (não ABC) é a postura hexagonal do projeto (`hex-arch-python`, LAYOUT
§3), idêntica a `CandleFetcher` (2.2), `MedallionStore` (2.1) e `ExperimentTracker`
(1.5). Importa a entity `NewsArticle` em runtime — a `application` pode importar o
`domain`. NUNCA importa `adapters`/`httpx`/`pandas`/`pyarrow` (inward-only;
concept 2.3 I3/I4).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)


class NewsFetcher(Protocol):
    """Contrato de leitura de notícias de um ativo, agnóstico de origem.

    Semântica temporal garantida por qualquer implementação:

    - `start_date`/`end_date` são tz-aware (naive → `ValueError` na fronteira do
      adapter/use case).
    - O intervalo `[start_date, end_date]` é filtrado pela implementação; uma origem
      sem dados no intervalo devolve uma lista vazia, mas uma origem
      indisponível/ilegível levanta erro (não silencia em vazio; concept 2.3 C6).
    - Cada `NewsArticle.published_at` devolvido é tz-aware em UTC.
    """

    def fetch_company_news(
        self, ticker: str, start_date: datetime, end_date: datetime
    ) -> list[NewsArticle]:
        """Devolve as notícias de `ticker` no intervalo `[start_date, end_date]`."""
        ...
