"""Use case `ScoreAndAggregateSentiment` — scoring + agregação diária de sentimento.

Orquestra o eixo de sentimento do BC `feature_engineering` (concept 3.2 §4):

1. lê a bronze `news` de um `asset` via `MedallionStore` (port 2.1);
2. mapeia cada linha para a entity `NewsArticle` (2.3);
3. pontua os artigos pelo port `SentimentModel` (Task 01), preservando a ordem;
4. materializa as sessões de pregão da janela via `ExchangeCalendarProvider` (2.4)
   e injeta o VO no serviço de domínio `TradingCalendar` (2.4);
5. mapeia `published_at -> dia de pregão` com `trading_day_from_timestamp`
   (guarda de causalidade: artigo pós-`close_hour` rola para a próxima sessão — I3,
   testada na Task 05);
6. agrega por dia de pregão (`mean`/`pstdev`/`n`, replica `SentimentAggregator` do
   old) e devolve **DTOs frozen** — a entity `NewsArticle` NUNCA cruza para fora (I7).

Depende SÓ de `Protocol`s/domain (LAYOUT §3): nenhum import de `adapters`/`torch`/
`transformers`/`pandas`. Os colaboradores são injetados no construtor (composition
root / testes com fakes). Recebe/devolve `dataclass` frozen.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from statistics import mean, pstdev

from financial_forecasting.features.feature_engineering.application.ports.out.sentiment_model import (  # noqa: E501
    SentimentModel,
)
from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)
from financial_forecasting.shared.application.ports.out.exchange_calendar_provider import (
    ExchangeCalendarProvider,
)
from financial_forecasting.shared.application.ports.out.medallion_store import (
    MedallionStore,
)
from financial_forecasting.shared.domain.services.trading_calendar import TradingCalendar

_BRONZE = "bronze"
_NEWS_TABLE = "news"


@dataclass(frozen=True)
class ScoreAndAggregateSentimentRequest:
    """Entrada do use case: ativo, janela `[start, end]` e horário de corte (cutoff)."""

    asset: str
    start: datetime
    end: datetime
    close_hour: time


@dataclass(frozen=True)
class ScoredNewsDTO:
    """Score por artigo, já mapeado ao dia de pregão (nunca a entity)."""

    asset: str
    article_id: str | None
    published_at: datetime
    trading_day: date
    score: float


@dataclass(frozen=True)
class DailySentimentDTO:
    """Sentimento agregado por dia de pregão (mean/pstdev/n)."""

    asset: str
    day: date
    sentiment_score: float
    sentiment_std: float
    n_articles: int


@dataclass(frozen=True)
class ScoreAndAggregateSentimentResult:
    """Saída do use case: scores por artigo + agregação diária + rastreabilidade."""

    scored: Sequence[ScoredNewsDTO]
    daily: Sequence[DailySentimentDTO]
    model_name: str
    revision: str


class ScoreAndAggregateSentiment:
    """Scoring + agregação diária de sentimento por dia de pregão (concept 3.2 §4)."""

    def __init__(
        self,
        *,
        store: MedallionStore,
        sentiment_model: SentimentModel,
        calendar_provider: ExchangeCalendarProvider,
    ) -> None:
        self._store = store
        self._sentiment_model = sentiment_model
        self._calendar_provider = calendar_provider

    def execute(
        self, request: ScoreAndAggregateSentimentRequest
    ) -> ScoreAndAggregateSentimentResult:
        """Lê, scora, mapeia para dia de pregão e agrega; devolve só DTOs (I7)."""
        articles = self._load_articles(request.asset)
        scores = self._sentiment_model.score_articles(articles)
        calendar = self._build_calendar(request)

        scored = self._build_scored(articles, scores, request.close_hour, calendar)
        daily = self._aggregate_daily(request.asset, scored)
        return ScoreAndAggregateSentimentResult(
            scored=scored,
            daily=daily,
            model_name=self._sentiment_model.model_name,
            revision=self._sentiment_model.revision,
        )

    # -- leitura/mapeamento --------------------------------------------------

    def _load_articles(self, asset: str) -> list[NewsArticle]:
        """Lê a bronze `news` filtrada por `asset` e mapeia cada linha para a entity."""
        rows = self._store.read(layer=_BRONZE, table=_NEWS_TABLE, filters={"asset": asset})
        return [self._row_to_article(row) for row in rows]

    @staticmethod
    def _row_to_article(row: Mapping[str, object]) -> NewsArticle:
        """Mapeia uma linha da bronze `news` para a entity `NewsArticle` (2.3)."""
        published_at = row["published_at"]
        if not isinstance(published_at, datetime):
            raise ValueError("bronze news row 'published_at' must be a datetime")
        return NewsArticle(
            asset_id=str(row["asset_id"]),
            published_at=published_at,
            headline=str(row.get("headline", "")),
            summary=str(row.get("summary", "")),
            source=str(row.get("source", "")),
            url=_optional_str(row.get("url")),
            article_id=_optional_str(row.get("article_id")),
            language=_optional_str(row.get("language")),
        )

    def _build_calendar(self, request: ScoreAndAggregateSentimentRequest) -> TradingCalendar:
        """Materializa as sessões da janela e injeta o VO no `TradingCalendar`."""
        sessions = self._calendar_provider.sessions(
            start=request.start.date(), end=request.end.date()
        )
        return TradingCalendar(sessions)

    # -- scoring + dia de pregão ---------------------------------------------

    @staticmethod
    def _build_scored(
        articles: Sequence[NewsArticle],
        scores: Sequence[float],
        close_hour: time,
        calendar: TradingCalendar,
    ) -> list[ScoredNewsDTO]:
        """Alinha artigo<->score (I2) e resolve o dia de pregão de cada um (I3)."""
        if len(scores) != len(articles):
            raise ValueError(
                f"SentimentModel returned {len(scores)} scores for {len(articles)} articles; "
                "the contract requires one score per article (order preserved)"
            )
        scored: list[ScoredNewsDTO] = []
        for article, score in zip(articles, scores, strict=True):
            trading_day = calendar.trading_day_from_timestamp(article.published_at, close_hour)
            scored.append(
                ScoredNewsDTO(
                    asset=article.asset_id,
                    article_id=article.article_id,
                    published_at=article.published_at,
                    trading_day=trading_day,
                    score=float(score),
                )
            )
        return scored

    # -- agregação diária ----------------------------------------------------

    @staticmethod
    def _aggregate_daily(asset: str, scored: Sequence[ScoredNewsDTO]) -> list[DailySentimentDTO]:
        """Agrega por dia de pregão (mean/pstdev/n), ordenado por `day`, só com n>=1 (I4/D7)."""
        grouped: dict[date, list[float]] = {}
        for item in scored:
            grouped.setdefault(item.trading_day, []).append(item.score)

        daily: list[DailySentimentDTO] = []
        for day in sorted(grouped):
            day_scores = grouped[day]
            std = pstdev(day_scores) if len(day_scores) > 1 else 0.0
            daily.append(
                DailySentimentDTO(
                    asset=asset,
                    day=day,
                    sentiment_score=mean(day_scores),
                    sentiment_std=std,
                    n_articles=len(day_scores),
                )
            )
        return daily


def _optional_str(value: object) -> str | None:
    """Normaliza um campo opcional da bronze: `None`/`""` -> `None`, senão `str`."""
    if value is None:
        return None
    text = str(value)
    return text if text else None
