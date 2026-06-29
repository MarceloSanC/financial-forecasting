"""Testes do use case `IngestNews` com fakes (concept 2.3 §5 I5/I6/I8, A5).

Usa `FakeNewsFetcher` + `FakeMedallionStore` (reusado da 2.1) — fakes
comportamentais, NÃO mocks. Cobre: 8 chaves non-null em toda Row (fallback para
`url`/`summary`/`language` vazios), `article_id` non-null garantido (fallback
`article_id > url > time+title`), gravação `(bronze, news)` `overwrite=False`,
`Result.ingested` == nº de artigos, retorno é `IngestNewsResult` (nunca entity),
colisão de PK → `DuplicateKeyError`, `start > end`/naive → `ValueError`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from financial_forecasting.features.market_data.application.use_cases.ingest_news import (
    IngestNews,
    IngestNewsRequest,
    IngestNewsResult,
)
from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)
from financial_forecasting.shared.application.ports.out.medallion_store import Row
from financial_forecasting.shared.domain.exceptions.base import DuplicateKeyError
from tests.fakes.features.market_data.in_memory_news_fetcher import FakeNewsFetcher
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

_SYMBOL = "AAPL"
_START = datetime(2024, 1, 1, tzinfo=UTC)
_END = datetime(2024, 12, 31, tzinfo=UTC)
_NEWS_COLUMNS = (
    "asset_id",
    "article_id",
    "published_at",
    "headline",
    "summary",
    "source",
    "url",
    "language",
)


def _article(**overrides: object) -> NewsArticle:
    kwargs: dict[str, object] = {
        "asset_id": _SYMBOL,
        "published_at": datetime(2024, 3, 1, 9, 30, tzinfo=UTC),
        "headline": "Apple beats estimates",
        "summary": "Strong quarter.",
        "source": "Reuters",
        "url": "https://example.com/aapl-1",
        "article_id": "https://example.com/aapl-1",
        "language": "en",
    }
    kwargs.update(overrides)
    return NewsArticle(**kwargs)  # type: ignore[arg-type]


def _stored_news(store: FakeMedallionStore) -> Sequence[Row]:
    return store.read(layer="bronze", table="news", filters={"asset": _SYMBOL})


@pytest.mark.unit
def test_ingests_and_returns_count() -> None:
    """Grava as notícias e devolve `IngestNewsResult` com a contagem (nunca entity)."""
    fetcher = FakeNewsFetcher(
        [
            _article(),
            _article(article_id="https://example.com/aapl-2", url="https://example.com/aapl-2"),
        ]
    )
    store = FakeMedallionStore()

    result = IngestNews(fetcher, store).execute(IngestNewsRequest(_SYMBOL, _START, _END))

    assert isinstance(result, IngestNewsResult)
    assert result.ingested == len(["a1", "a2"])
    assert result.asset == _SYMBOL
    assert len(_stored_news(store)) == len(["a1", "a2"])


@pytest.mark.unit
def test_rows_have_eight_non_null_columns() -> None:
    """Toda Row gravada tem as 8 colunas non-null (fallback aplicado, I6)."""
    fetcher = FakeNewsFetcher([_article(url=None, summary="", language=None)])
    store = FakeMedallionStore()

    IngestNews(fetcher, store).execute(IngestNewsRequest(_SYMBOL, _START, _END))

    row = _stored_news(store)[0]
    assert set(row.keys()) == set(_NEWS_COLUMNS)
    for col in _NEWS_COLUMNS:
        assert row[col] is not None, f"column {col} must be non-null"
    # url/summary/language vazios viram string non-null
    assert row["url"] == ""
    assert row["summary"] == ""
    assert row["language"] == ""


@pytest.mark.unit
def test_article_id_fallback_to_url_then_time_title() -> None:
    """`article_id` non-null: fallback `url`, depois `time:title` (I6/D5)."""
    store = FakeMedallionStore()
    # sem article_id, mas com url → usa url
    IngestNews(
        FakeNewsFetcher([_article(article_id=None, url="https://u/abc")]),
        store,
    ).execute(IngestNewsRequest(_SYMBOL, _START, _END))
    assert _stored_news(store)[0]["article_id"] == "https://u/abc"

    # sem article_id E sem url → usa f"{published_at_iso}:{headline[:80]}"
    store2 = FakeMedallionStore()
    published = datetime(2024, 3, 1, 9, 30, tzinfo=UTC)
    IngestNews(
        FakeNewsFetcher(
            [_article(article_id=None, url=None, published_at=published, headline="HL")]
        ),
        store2,
    ).execute(IngestNewsRequest(_SYMBOL, _START, _END))
    assert _stored_news(store2)[0]["article_id"] == f"{published.isoformat()}:HL"


@pytest.mark.unit
def test_writes_to_bronze_news_append_only() -> None:
    """Grava em `(bronze, news)`; segundo write da MESMA PK → `DuplicateKeyError` (C3/I8)."""
    fetcher = FakeNewsFetcher([_article()])
    store = FakeMedallionStore()
    uc = IngestNews(fetcher, store)

    uc.execute(IngestNewsRequest(_SYMBOL, _START, _END))
    with pytest.raises(DuplicateKeyError):
        uc.execute(IngestNewsRequest(_SYMBOL, _START, _END))


@pytest.mark.unit
def test_empty_source_produces_no_rows() -> None:
    """Sem artigos no intervalo → grava lista vazia, `ingested == 0`."""
    store = FakeMedallionStore()
    result = IngestNews(FakeNewsFetcher([]), store).execute(
        IngestNewsRequest(_SYMBOL, _START, _END)
    )
    assert result.ingested == 0
    assert _stored_news(store) == []


@pytest.mark.unit
def test_naive_bounds_raise() -> None:
    """`start`/`end` naive → `ValueError` (C5)."""
    uc = IngestNews(FakeNewsFetcher([]), FakeMedallionStore())
    with pytest.raises(ValueError, match="timezone-aware"):
        uc.execute(IngestNewsRequest(_SYMBOL, datetime(2024, 1, 1), _END))


@pytest.mark.unit
def test_start_after_end_raises() -> None:
    """`start > end` → `ValueError` (C5)."""
    uc = IngestNews(FakeNewsFetcher([]), FakeMedallionStore())
    with pytest.raises(ValueError, match="start must be <= end"):
        uc.execute(IngestNewsRequest(_SYMBOL, _END, _START))
