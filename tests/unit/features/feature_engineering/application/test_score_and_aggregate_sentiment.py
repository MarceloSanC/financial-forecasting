"""Unit tests do use case `ScoreAndAggregateSentiment` — agregação + DTO na fronteira.

Cobre o happy path (concept 3.2 A5), SEM torch: o use case é exercitado com o fake
`InMemorySentimentModel` (mapa `article_id -> score`), o `FakeExchangeCalendarProvider`
(sessões XNYS 2023, reuso 2.4) e o `FakeMedallionStore` (reuso 2.1):

- lê a bronze `news`, scora e devolve DTOs frozen (nunca a entity `NewsArticle`);
- agrega `mean`/`pstdev(n>1)/0.0(n==1)`/`n` por dia de pregão;
- `Result.daily` ordenado por `day` e só com `n>=1` (D7);
- `Result` expõe `(model_name, revision)` do modelo injetado (I6).

A guarda de causalidade (cutoff/naive/janela) ganha teste dedicado na Task 05.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from statistics import mean, pstdev

import pytest

from financial_forecasting.features.feature_engineering.application.use_cases.score_and_aggregate_sentiment import (  # noqa: E501
    DailySentimentDTO,
    ScoreAndAggregateSentiment,
    ScoreAndAggregateSentimentRequest,
    ScoredNewsDTO,
)
from tests.fakes.features.feature_engineering.in_memory_sentiment_model import (
    InMemorySentimentModel,
)
from tests.fakes.shared.in_memory_exchange_calendar_provider import (
    FakeExchangeCalendarProvider,
)
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

_ASSET = "AAPL"
# close_hour bem tardio para que os timestamps de teste (manhã/meio-dia) caiam no
# próprio dia de pregão — a guarda pós-close é exercitada na Task 05.
_CLOSE_HOUR = time(23, 59)


def _news_row(article_id: str, published_at: datetime) -> dict[str, object]:
    """Linha da bronze `news` (mesmas colunas do schema 2.1)."""
    return {
        "asset_id": _ASSET,
        "article_id": article_id,
        "published_at": published_at,
        "headline": f"headline {article_id}",
        "summary": f"summary {article_id}",
        "source": "unit-test",
        "url": f"https://example.com/{article_id}",
        "language": "en",
    }


def _store_with(rows: list[dict[str, object]]) -> FakeMedallionStore:
    store = FakeMedallionStore()
    store.write(layer="bronze", table="news", rows=rows)
    return store


def _request() -> ScoreAndAggregateSentimentRequest:
    return ScoreAndAggregateSentimentRequest(
        asset=_ASSET,
        start=datetime(2023, 1, 1, tzinfo=UTC),
        end=datetime(2023, 12, 31, tzinfo=UTC),
        close_hour=_CLOSE_HOUR,
    )


def _use_case(store: FakeMedallionStore, scores: dict[str, float]) -> ScoreAndAggregateSentiment:
    return ScoreAndAggregateSentiment(
        store=store,
        sentiment_model=InMemorySentimentModel(scores, model_name="m", revision="rev-1"),
        calendar_provider=FakeExchangeCalendarProvider(),
    )


def test_returns_only_dtos_never_entity() -> None:
    """Use case devolve DTOs frozen, nunca a entity `NewsArticle` (I7)."""
    rows = [_news_row("a1", datetime(2023, 1, 3, 12, 0, tzinfo=UTC))]
    result = _use_case(_store_with(rows), {"a1": 0.5}).execute(_request())
    assert all(isinstance(s, ScoredNewsDTO) for s in result.scored)
    assert all(isinstance(d, DailySentimentDTO) for d in result.daily)


def test_single_article_day_has_zero_std() -> None:
    """Dia com 1 artigo: mean = score, pstdev = 0.0, n = 1 (I4)."""
    rows = [_news_row("a1", datetime(2023, 1, 3, 12, 0, tzinfo=UTC))]
    result = _use_case(_store_with(rows), {"a1": 0.42}).execute(_request())
    (day,) = result.daily
    assert day.day == date(2023, 1, 3)
    assert day.sentiment_score == pytest.approx(0.42)
    assert day.sentiment_std == pytest.approx(0.0)
    assert day.n_articles == 1


def test_multi_article_day_aggregates_mean_and_pstdev() -> None:
    """Dia com >1 artigo: mean dos scores, pstdev populacional, n = len (I4)."""
    rows = [
        _news_row("a1", datetime(2023, 1, 3, 9, 0, tzinfo=UTC)),
        _news_row("a2", datetime(2023, 1, 3, 12, 0, tzinfo=UTC)),
        _news_row("a3", datetime(2023, 1, 3, 15, 0, tzinfo=UTC)),
    ]
    scores = {"a1": 0.2, "a2": 0.8, "a3": -0.4}
    result = _use_case(_store_with(rows), scores).execute(_request())
    (day,) = result.daily
    expected_vals = [0.2, 0.8, -0.4]
    assert day.n_articles == len(expected_vals)
    assert day.sentiment_score == pytest.approx(mean(expected_vals))
    assert day.sentiment_std == pytest.approx(pstdev(expected_vals))


def test_daily_is_sorted_by_day_and_only_nonempty() -> None:
    """`Result.daily` ordenado por `day`; só dias com n>=1 (D7) — sem dias vazios."""
    rows = [
        _news_row("a3", datetime(2023, 3, 1, 12, 0, tzinfo=UTC)),
        _news_row("a1", datetime(2023, 1, 4, 12, 0, tzinfo=UTC)),
        _news_row("a2", datetime(2023, 2, 1, 12, 0, tzinfo=UTC)),
    ]
    scores = {"a1": 0.1, "a2": 0.2, "a3": 0.3}
    result = _use_case(_store_with(rows), scores).execute(_request())
    days = [d.day for d in result.daily]
    assert days == sorted(days)
    assert days == [date(2023, 1, 4), date(2023, 2, 1), date(2023, 3, 1)]
    assert all(d.n_articles >= 1 for d in result.daily)


def test_result_carries_model_name_and_revision() -> None:
    """`Result` expõe `(model_name, revision)` do modelo injetado (I6)."""
    rows = [_news_row("a1", datetime(2023, 1, 3, 12, 0, tzinfo=UTC))]
    result = _use_case(_store_with(rows), {"a1": 0.5}).execute(_request())
    assert result.model_name == "m"
    assert result.revision == "rev-1"


def test_scored_aligns_score_to_article() -> None:
    """Cada `ScoredNewsDTO` carrega o score do seu artigo (I2) e o dia de pregão."""
    rows = [
        _news_row("a1", datetime(2023, 1, 4, 12, 0, tzinfo=UTC)),
        _news_row("a2", datetime(2023, 1, 5, 12, 0, tzinfo=UTC)),
    ]
    scores = {"a1": 0.7, "a2": -0.3}
    result = _use_case(_store_with(rows), scores).execute(_request())
    by_id = {s.article_id: s for s in result.scored}
    assert by_id["a1"].score == pytest.approx(0.7)
    assert by_id["a1"].trading_day == date(2023, 1, 4)
    assert by_id["a2"].score == pytest.approx(-0.3)
    assert by_id["a2"].trading_day == date(2023, 1, 5)


def test_empty_news_yields_empty_result() -> None:
    """Sem notícias para o ativo, `scored` e `daily` são vazios."""
    result = _use_case(FakeMedallionStore(), {}).execute(_request())
    assert list(result.scored) == []
    assert list(result.daily) == []


def test_score_count_mismatch_raises() -> None:
    """Modelo que devolve nº de scores != nº de artigos -> ValueError (I2)."""

    class _BadModel:
        model_name = "bad"
        revision = "bad"

        def score_articles(self, articles: object) -> list[float]:
            del articles  # sempre 1 score, independente da entrada
            return [0.1]

    rows = [
        _news_row("a1", datetime(2023, 1, 4, 12, 0, tzinfo=UTC)),
        _news_row("a2", datetime(2023, 1, 5, 12, 0, tzinfo=UTC)),
    ]
    use_case = ScoreAndAggregateSentiment(
        store=_store_with(rows),
        sentiment_model=_BadModel(),
        calendar_provider=FakeExchangeCalendarProvider(),
    )
    with pytest.raises(ValueError, match="one score per article"):
        use_case.execute(_request())
