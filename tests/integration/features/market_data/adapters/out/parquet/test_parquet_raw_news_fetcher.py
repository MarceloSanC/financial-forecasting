"""Integração do `ParquetRawNewsFetcher` contra o raw REAL (concept 2.3 A7, Task 10).

Ponto de verdade dos riscos do concept §10 para news: campo opcional chegando vazio,
ID estável, tz-aware UTC. Lê as 6921 linhas reais de AAPL via o adapter default e
prova que TODAS produzem `NewsArticle`s válidos (invariantes I1 aplicadas na
construção), `asset_id == AAPL`, `published_at` tz-aware UTC, e contagem == 6921. Se
nenhuma linha legítima reprova, o risco está fechado. `skipif` se o raw não estiver
presente (robustez overnight).

`[deviation]` vs technical §2 Task 10: o plano original previa estabilizar os
contract tests; optou-se por um teste de integração `read-all` dedicado (espelhando
`test_parquet_raw_candle_fetcher.py` da 2.2) — mantém os contract tests herméticos e
isola a leitura completa do parquet real. Registrado na §7.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from financial_forecasting.features.market_data.adapters.out.parquet.parquet_raw_news_fetcher import (  # noqa: E501
    DEFAULT_RAW_ROOT,
    ParquetRawNewsFetcher,
)
from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)

_SYMBOL = "AAPL"
_EXPECTED_ROWS = 6921
_WIDE_START = datetime(1990, 1, 1, tzinfo=UTC)
_WIDE_END = datetime(2100, 1, 1, tzinfo=UTC)
_RAW_PATH = DEFAULT_RAW_ROOT / _SYMBOL / f"news_{_SYMBOL}.parquet"

pytestmark = pytest.mark.skipif(
    not _RAW_PATH.exists(),
    reason=f"raw real de news ausente: {_RAW_PATH}",
)


@pytest.fixture
def articles() -> list[NewsArticle]:
    return ParquetRawNewsFetcher().fetch_company_news(_SYMBOL, _WIDE_START, _WIDE_END)


@pytest.mark.integration
def test_reads_all_real_rows(articles: list[NewsArticle]) -> None:
    """Lê as 6921 linhas reais sem rejeitar nenhuma (invariantes I1 passam)."""
    assert len(articles) == _EXPECTED_ROWS
    assert all(isinstance(a, NewsArticle) for a in articles)


@pytest.mark.integration
def test_all_real_articles_are_valid_aapl_utc(articles: list[NewsArticle]) -> None:
    """Todo artigo real: asset_id=AAPL, published_at tz-aware UTC, article_id non-null."""
    for article in articles:
        assert article.asset_id == _SYMBOL
        assert article.published_at.tzinfo is not None
        assert article.published_at.utcoffset() == UTC.utcoffset(None)
        assert article.article_id is not None


@pytest.mark.integration
def test_real_articles_sorted_by_published_at(articles: list[NewsArticle]) -> None:
    """Os artigos voltam ordenados por `published_at` ascendente."""
    published = [a.published_at for a in articles]
    assert published == sorted(published)
