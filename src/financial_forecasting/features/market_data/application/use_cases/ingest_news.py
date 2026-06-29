"""Use case `IngestNews` + DTOs frozen (concept 2.3 §4, A5).

Orquestra a ingestão de notícias para a bronze: lê de uma origem (`NewsFetcher`,
port-out — default = parquet raw existente), mapeia cada `NewsArticle → Row`
aplicando FALLBACK NON-NULL nos campos opcionais (o schema bronze `NEWS` exige as 8
colunas `nullable=False`, mas a entity os declara opcionais — concept 2.3 I6/D5) e
grava via `MedallionStore` (port-out 2.1) em `(bronze, news)`, append-only. Recebe/
devolve DTO frozen — NUNCA vaza `NewsArticle` nem `list` para fora (concept 2.3
I5/D6, recorte do `Result`-com-`fetched` do old).

O use case é stdlib-only (não usa `pandas`): a coerção de dtype final para o schema
bronze é do `ParquetMedallionStore` (2.1, I7). A rede de segurança `pandera`
(`coerce=False`/`strict=True`) no `write` rejeita qualquer drift ou coluna nula (C4).

A invariante de coleção "sem duplicados" (dedup por `article_id`) é delegada à PK
lógica `(asset_id, article_id)` do `MedallionStore`: colisão sem `overwrite` propaga
`DuplicateKeyError` (concept 2.3 C3/I8/D5) — o use case NÃO reimplementa dedup nem
porta o cursor-walking do old `FetchNewsUseCase` (D4 — non-goal).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from financial_forecasting.features.market_data.application.ports.out.news_fetcher import (
    NewsFetcher,
)
from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)
from financial_forecasting.features.market_data.domain.time.utc import require_tz_aware
from financial_forecasting.shared.application.ports.out.medallion_store import (
    MedallionStore,
    Row,
)

_BRONZE_LAYER = "bronze"
_NEWS_TABLE = "news"
_HEADLINE_ID_LEN = 80


@dataclass(frozen=True)
class IngestNewsRequest:
    """Comando de ingestão de news: ativo + intervalo tz-aware (concept 2.3 §4)."""

    asset: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class IngestNewsResult:
    """Resultado da ingestão: contagem gravada + metadados (NUNCA `NewsArticle`)."""

    asset: str
    ingested: int
    start: datetime
    end: datetime


def _stable_article_id(article: NewsArticle) -> str:
    """ID estável non-null: `article_id` > `url` > `f"{published_at_iso}:{headline[:80]}"`.

    Mesma regra do adapter de news do old (`alpha_vantage_news_fetcher.py:169-170`):
    garante a PK lógica `(asset_id, article_id)` válida mesmo quando a entity traz
    `article_id`/`url` ausentes (concept 2.3 I6/D5).
    """
    if article.article_id and article.article_id.strip():
        return article.article_id
    if article.url and article.url.strip():
        return article.url
    published_iso = article.published_at.isoformat()
    return f"{published_iso}:{article.headline[:_HEADLINE_ID_LEN]}"


def _news_to_row(article: NewsArticle) -> Row:
    """Mapeia `NewsArticle → Row` bronze com FALLBACK NON-NULL nas 8 colunas (I6/D5).

    As chaves casam EXATAMENTE as colunas do schema `NEWS` (2.1): `asset_id`,
    `article_id`, `published_at`, `headline`, `summary`, `source`, `url`, `language`.
    Campos opcionais `None`/vazio viram string non-null (`""` para `url`/`summary`;
    `"en"` default para `language` já vem da entity; `article_id` via ID estável).
    """
    return {
        "asset_id": article.asset_id,
        "article_id": _stable_article_id(article),
        "published_at": article.published_at,
        "headline": article.headline,
        "summary": article.summary,
        "source": article.source,
        "url": article.url if article.url is not None else "",
        "language": article.language if article.language is not None else "",
    }


class IngestNews:
    """Use case: ingere notícias de um ativo para a bronze via `MedallionStore`."""

    def __init__(self, fetcher: NewsFetcher, store: MedallionStore) -> None:
        self._fetcher = fetcher
        self._store = store

    def execute(self, request: IngestNewsRequest) -> IngestNewsResult:
        """Lê notícias da origem, mapeia (fallback non-null) e grava `(bronze, news)`.

        Valida o intervalo na fronteira (`start`/`end` tz-aware e `start <= end`,
        concept 2.3 C5). A escrita é append-only (`overwrite=False`): re-ingerir uma
        PK lógica `(asset_id, article_id)` já presente propaga `DuplicateKeyError`
        do store (C3/I8 — dedup de news). Devolve `IngestNewsResult` com a contagem
        ingerida (NUNCA `NewsArticle`).
        """
        require_tz_aware(request.start, "start")
        require_tz_aware(request.end, "end")
        if request.start > request.end:
            raise ValueError("start must be <= end")

        articles = self._fetcher.fetch_company_news(
            ticker=request.asset, start_date=request.start, end_date=request.end
        )
        rows: list[Mapping[str, object]] = [_news_to_row(a) for a in articles]
        self._store.write(layer=_BRONZE_LAYER, table=_NEWS_TABLE, rows=rows, overwrite=False)

        return IngestNewsResult(
            asset=request.asset,
            ingested=len(rows),
            start=request.start,
            end=request.end,
        )
