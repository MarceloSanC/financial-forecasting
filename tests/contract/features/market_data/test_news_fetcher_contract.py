"""Contract test do port `NewsFetcher` — paridade Fake ↔ ParquetRawNewsFetcher.

Um ÚNICO contrato parametrizado prova que ambas as implementações honram a MESMA
semântica observável (concept 2.3 I14/A4): `fetch_company_news` devolve
`list[NewsArticle]` com todos os `published_at` tz-aware UTC, invariantes I1
respeitadas (garantidas pela construção da `NewsArticle`), filtro por
`[start_date, end_date]`, `asset_id` == ticker pedido, e `start_date >
end_date`/naive → `ValueError`.

O `real` (`ParquetRawNewsFetcher`) lê um parquet sintético escrito em `tmp_path` com
o MESMO layout/dtypes do raw (`<root>/<symbol>/news_<symbol>.parquet`, 8 colunas
string + `published_at` UTC) — hermético e rápido. A validação contra o raw real
completo (6921 linhas) é da Task 10 / integração.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from financial_forecasting.features.market_data.adapters.out.parquet.parquet_raw_news_fetcher import (  # noqa: E501
    ParquetRawNewsFetcher,
)

# `NewsFetcher` (Protocol, duck-typed) tipa a fixture parametrizada [fake, real].
from financial_forecasting.features.market_data.application.ports.out.news_fetcher import (
    NewsFetcher,
)
from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)
from financial_forecasting.shared.domain.exceptions.base import ApplicationError
from tests.fakes.features.market_data.in_memory_news_fetcher import FakeNewsFetcher

_SYMBOL = "AAPL"
_START = datetime(2024, 1, 1, tzinfo=UTC)
_END = datetime(2024, 12, 31, tzinfo=UTC)
_TWO = 2


def _articles() -> list[NewsArticle]:
    """Conjunto canônico de notícias válidas (mesma fonte p/ fake e real)."""
    return [
        NewsArticle(
            asset_id=_SYMBOL,
            published_at=datetime(2024, 1, day, 10, 0, tzinfo=UTC),
            headline=f"Headline {day}",
            summary=f"Summary {day}",
            source="Reuters",
            url=f"https://example.com/aapl-{day}",
            article_id=f"https://example.com/aapl-{day}",
            language="en",
        )
        for day in (2, 3, 4)
    ]


def _write_raw_parquet(root: Path, symbol: str, articles: list[NewsArticle]) -> None:
    """Escreve o raw sintético no layout/dtypes esperados pelo adapter (8 colunas)."""
    path = root / symbol / f"news_{symbol}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "article_id": pd.array([a.article_id for a in articles], dtype="string"),
            "headline": pd.array([a.headline for a in articles], dtype="string"),
            "published_at": pd.to_datetime([a.published_at for a in articles], utc=True),
            "asset_id": pd.array([a.asset_id for a in articles], dtype="string"),
            "url": pd.array([a.url for a in articles], dtype="string"),
            "source": pd.array([a.source for a in articles], dtype="string"),
            "language": pd.array([a.language for a in articles], dtype="string"),
            "summary": pd.array([a.summary for a in articles], dtype="string"),
        }
    )
    frame.to_parquet(path)


def _build_fake(_tmp_path: Path) -> NewsFetcher:
    return FakeNewsFetcher(_articles())


def _build_real(tmp_path: Path) -> NewsFetcher:
    _write_raw_parquet(tmp_path, _SYMBOL, _articles())
    return ParquetRawNewsFetcher(tmp_path)


_FACTORIES: list[Callable[[Path], NewsFetcher]] = [_build_fake, _build_real]
_IDS = ["fake", "real"]


@pytest.fixture(params=_FACTORIES, ids=_IDS)
def fetcher(request: pytest.FixtureRequest, tmp_path: Path) -> NewsFetcher:
    """Parametriza o contrato sobre o fake e o adapter real (paridade fake↔real)."""
    factory: Callable[[Path], NewsFetcher] = request.param
    return factory(tmp_path)


@pytest.mark.contract
def test_fetch_returns_list_of_news_articles(fetcher: NewsFetcher) -> None:
    """Devolve uma `list[NewsArticle]` não-vazia para o ticker com dados."""
    articles = fetcher.fetch_company_news(_SYMBOL, _START, _END)

    assert articles
    assert all(isinstance(a, NewsArticle) for a in articles)
    assert len(articles) == len(_articles())


@pytest.mark.contract
def test_all_published_at_are_utc(fetcher: NewsFetcher) -> None:
    """Todos os `published_at` são tz-aware UTC (I1)."""
    for article in fetcher.fetch_company_news(_SYMBOL, _START, _END):
        assert article.published_at.tzinfo is not None
        assert article.published_at.utcoffset() == _START.utcoffset()


@pytest.mark.contract
def test_asset_id_is_the_requested_ticker(fetcher: NewsFetcher) -> None:
    """`asset_id` é o ticker pedido."""
    for article in fetcher.fetch_company_news(_SYMBOL, _START, _END):
        assert article.asset_id == _SYMBOL


@pytest.mark.contract
def test_filters_by_interval(fetcher: NewsFetcher) -> None:
    """Filtra por `[start, end]`: janela menor devolve menos notícias."""
    narrow = fetcher.fetch_company_news(
        _SYMBOL,
        datetime(2024, 1, 2, tzinfo=UTC),
        datetime(2024, 1, 3, 23, 59, tzinfo=UTC),
    )
    assert len(narrow) == _TWO
    assert all(a.published_at <= datetime(2024, 1, 4, tzinfo=UTC) for a in narrow)


@pytest.mark.contract
def test_no_data_in_interval_returns_empty(fetcher: NewsFetcher) -> None:
    """Sem notícias no intervalo → `[]` (não erro)."""
    empty = fetcher.fetch_company_news(
        _SYMBOL,
        datetime(2030, 1, 1, tzinfo=UTC),
        datetime(2030, 12, 31, tzinfo=UTC),
    )
    assert empty == []


@pytest.mark.contract
def test_start_after_end_raises(fetcher: NewsFetcher) -> None:
    """`start > end` → ValueError (fronteira do contrato, C5)."""
    with pytest.raises(ValueError, match="must be <="):
        fetcher.fetch_company_news(_SYMBOL, _END, _START)


@pytest.mark.contract
def test_naive_bounds_raise(fetcher: NewsFetcher) -> None:
    """`start`/`end` naive → ValueError (C5)."""
    with pytest.raises(ValueError, match="timezone-aware"):
        fetcher.fetch_company_news(_SYMBOL, datetime(2024, 1, 1), _END)


# -- testes específicos do adapter real (origem default; concept 2.3 C6) -------


@pytest.mark.contract
def test_real_missing_file_raises_application_error(tmp_path: Path) -> None:
    """Arquivo de origem ausente → `ApplicationError` (não lista vazia, C6)."""
    real = ParquetRawNewsFetcher(tmp_path)
    with pytest.raises(ApplicationError, match="not found"):
        real.fetch_company_news(_SYMBOL, _START, _END)


@pytest.mark.contract
def test_real_missing_column_raises_application_error(tmp_path: Path) -> None:
    """Coluna obrigatória ausente no parquet → `ApplicationError` (C6)."""
    path = tmp_path / _SYMBOL / f"news_{_SYMBOL}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    # parquet sem a coluna `summary`
    pd.DataFrame(
        {
            "article_id": ["x"],
            "headline": ["h"],
            "published_at": pd.to_datetime(["2024-01-02"], utc=True),
            "asset_id": [_SYMBOL],
            "url": ["https://x"],
            "source": ["s"],
            "language": ["en"],
        }
    ).to_parquet(path)

    with pytest.raises(ApplicationError, match="missing columns"):
        ParquetRawNewsFetcher(tmp_path).fetch_company_news(_SYMBOL, _START, _END)


@pytest.mark.contract
def test_real_optional_fields_null_and_naive_timestamp(tmp_path: Path) -> None:
    """`url`/`language` nulos → `None`; `published_at` naive é localizado a UTC."""
    path = tmp_path / _SYMBOL / f"news_{_SYMBOL}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "article_id": pd.array(["aid-1"], dtype="string"),
            "headline": pd.array(["h"], dtype="string"),
            # timestamp tz-NAIVE → exercita o ramo `tz_localize("UTC")`
            "published_at": pd.to_datetime(["2024-01-02 10:00:00"]),
            "asset_id": pd.array([_SYMBOL], dtype="string"),
            "url": pd.array([None], dtype="string"),  # nulo → None
            "source": pd.array(["s"], dtype="string"),
            "language": pd.array([None], dtype="string"),  # nulo → None
            "summary": pd.array(["sm"], dtype="string"),
        }
    ).to_parquet(path)

    articles = ParquetRawNewsFetcher(tmp_path).fetch_company_news(_SYMBOL, _START, _END)

    assert len(articles) == 1
    article = articles[0]
    assert article.url is None
    assert article.language is None
    assert article.published_at == datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
