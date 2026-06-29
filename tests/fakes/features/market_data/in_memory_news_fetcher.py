"""Fake in-memory do port `NewsFetcher` — NÃO um mock (concept 2.3 A4).

`FakeNewsFetcher` é um fake COMPORTAMENTAL determinístico (stdlib-only): devolve uma
`list[NewsArticle]` pré-carregada, filtrando por `asset == ticker` e pelo intervalo
`[start_date, end_date]`, e aplicando a MESMA semântica de fronteira do adapter real
(`start_date`/`end_date` tz-aware → `ValueError`). Não asserta chamadas — produz
comportamento real e estável, para passar o MESMO contract test parametrizado do
port que o `ParquetRawNewsFetcher` (paridade fake↔real, concept 2.3 I14).

Vive em `tests/` (fora do gate `import-linter`), mas mantém o contrato agnóstico de
`pandas`/`pyarrow`: só `datetime` + a entity `NewsArticle`.
"""

from __future__ import annotations

from datetime import datetime

from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)
from financial_forecasting.features.market_data.domain.time.utc import require_tz_aware


class FakeNewsFetcher:
    """Implementação in-memory determinística do contrato `NewsFetcher`."""

    def __init__(self, articles: list[NewsArticle] | None = None) -> None:
        # Cópia defensiva: o fake não compartilha estado mutável com o chamador.
        self._articles: list[NewsArticle] = list(articles or [])

    def fetch_company_news(
        self, ticker: str, start_date: datetime, end_date: datetime
    ) -> list[NewsArticle]:
        """Devolve as notícias pré-carregadas de `ticker` em `[start_date, end_date]`.

        Aplica a fronteira do contrato (concept 2.3 C5): `start_date`/`end_date`
        tz-aware e `start_date <= end_date`. Filtra por `asset_id == ticker` e por
        `start_date <= published_at <= end_date`.
        """
        require_tz_aware(start_date, "start_date")
        require_tz_aware(end_date, "end_date")
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")

        return [
            article
            for article in self._articles
            if article.asset_id == ticker and start_date <= article.published_at <= end_date
        ]
