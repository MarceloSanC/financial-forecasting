"""Guarda de causalidade / anti-leakage do use case + regressão contra oráculo diário.

A guarda de causalidade é a DoD central desta Stage (anti-leakage, ADR 0.0.0018 —
NÃO-NEGOCIÁVEL). Estes testes (com fakes, SEM torch) provam que o use case
`ScoreAndAggregateSentiment` honra ponta-a-ponta (concept 3.2 I3/C1/C2/C3):

- **C2 — cutoff pós-close:** artigo publicado APÓS o `close_hour` rola para a PRÓXIMA
  sessão de pregão; nunca contamina o dia corrente (look-ahead).
- **C1 — naive:** `published_at` naive levanta `ValueError` (herdado de `NewsArticle`).
- **C3 — janela:** dia de pregão fora da janela materializada -> `ValueError` (sem
  clamp, herdado de `TradingCalendar`).
- **nenhum artigo futuro** é agregado no dia corrente.

E a **regressão end-to-end** contra o oráculo diário real (`daily_sentiment_AAPL`):
alimentando os scores per-article do oráculo `scored_news_AAPL` no fake e rodando o
use case com `close_hour = 21:00 UTC` (fechamento NYSE em EST = 16:00 ET), o
`Result.daily` (mean/pstdev/n por dia de pregão) bate com o oráculo diário do old nos
dias verificáveis. Ver [decision] na §7 do technical: o oráculo diário do old usa dias
CIVIS com fill de dias-zero (n=0), ao passo que o contrato desta Stage é por DIA DE
PREGÃO só com n>=1 — logo a regressão compara só os dias em que civil==pregão e n>=1.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest

from financial_forecasting.features.feature_engineering.application.use_cases.score_and_aggregate_sentiment import (  # noqa: E501
    ScoreAndAggregateSentiment,
    ScoreAndAggregateSentimentRequest,
)
from tests.fakes.features.feature_engineering.in_memory_sentiment_model import (
    InMemorySentimentModel,
)
from tests.fakes.shared.in_memory_exchange_calendar_provider import (
    FakeExchangeCalendarProvider,
)
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

_ASSET = "AAPL"
# Fechamento NYSE em EST (inverno): 16:00 ET = 21:00 UTC. Replica o cutoff do old.
_NYSE_CLOSE_UTC = time(21, 0)
# parents: 0=application 1=feature_engineering 2=features 3=unit 4=tests 5=repo_root.
_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCORED_ORACLE = (
    _REPO_ROOT / "data" / "processed" / "scored_news" / "AAPL" / "scored_news_AAPL.parquet"
)
_DAILY_ORACLE = (
    _REPO_ROOT / "data" / "processed" / "sentiment_daily" / "AAPL" / "daily_sentiment_AAPL.parquet"
)


def _news_row(article_id: str, published_at: datetime) -> dict[str, object]:
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


def _make_use_case(
    store: FakeMedallionStore, scores: dict[str, float]
) -> ScoreAndAggregateSentiment:
    return ScoreAndAggregateSentiment(
        store=store,
        sentiment_model=InMemorySentimentModel(scores),
        calendar_provider=FakeExchangeCalendarProvider(),
    )


def _request(close_hour: time = _NYSE_CLOSE_UTC) -> ScoreAndAggregateSentimentRequest:
    return ScoreAndAggregateSentimentRequest(
        asset=_ASSET,
        start=datetime(2023, 1, 1, tzinfo=UTC),
        end=datetime(2023, 12, 31, tzinfo=UTC),
        close_hour=close_hour,
    )


# -- C2 — cutoff pós-close ---------------------------------------------------


def test_post_close_article_rolls_to_next_session() -> None:
    """Artigo após o `close_hour` cai na PRÓXIMA sessão; o pré-close fica no dia (C2)."""
    # 2023-01-04 (quarta) e 2023-01-05 (quinta) são sessões XNYS consecutivas.
    pre_close = _news_row("pre", datetime(2023, 1, 4, 12, 0, tzinfo=UTC))  # antes de 21:00
    post_close = _news_row("post", datetime(2023, 1, 4, 22, 0, tzinfo=UTC))  # após 21:00
    store = _store_with([pre_close, post_close])
    result = _make_use_case(store, {"pre": 0.5, "post": -0.5}).execute(_request())

    by_day = {d.day: d for d in result.daily}
    # o pré-close fica em 2023-01-04; o pós-close rola para a próxima sessão 2023-01-05.
    assert by_day[date(2023, 1, 4)].n_articles == 1
    assert by_day[date(2023, 1, 4)].sentiment_score == pytest.approx(0.5)
    assert by_day[date(2023, 1, 5)].n_articles == 1
    assert by_day[date(2023, 1, 5)].sentiment_score == pytest.approx(-0.5)


def test_no_future_article_contaminates_current_day() -> None:
    """Nenhum artigo futuro (pós-close) é agregado no dia corrente (anti-leakage)."""
    pre_close = _news_row("pre", datetime(2023, 1, 4, 9, 0, tzinfo=UTC))
    post_close = _news_row("post", datetime(2023, 1, 4, 23, 30, tzinfo=UTC))
    store = _store_with([pre_close, post_close])
    result = _make_use_case(store, {"pre": 0.9, "post": 0.9}).execute(_request())
    current = next(d for d in result.daily if d.day == date(2023, 1, 4))
    # se o pós-close vazasse, n seria 2; a guarda mantém n=1 no dia corrente.
    assert current.n_articles == 1


# -- C1 — naive --------------------------------------------------------------


def test_naive_published_at_raises() -> None:
    """`published_at` naive -> `ValueError` (herdado de NewsArticle, C1)."""
    naive_row = _news_row("naive", datetime(2023, 1, 4, 12, 0))  # naive proposital
    store = _store_with([naive_row])
    with pytest.raises(ValueError, match=r"(?i)timezone|tz-aware|aware"):
        _make_use_case(store, {"naive": 0.1}).execute(_request())


# -- C3 — janela -------------------------------------------------------------


def test_trading_day_beyond_window_raises() -> None:
    """Artigo cujo dia de pregão cairia além da janela materializada -> `ValueError` (C3)."""
    # Janela materializada estreita (só 2023-01-04..05); artigo pós-close no ÚLTIMO dia
    # da janela tenta rolar para uma sessão que não existe na janela -> erro sem clamp.
    narrow_provider = FakeExchangeCalendarProvider(sessions=(date(2023, 1, 4), date(2023, 1, 5)))
    last_post_close = _news_row("late", datetime(2023, 1, 5, 22, 0, tzinfo=UTC))
    store = _store_with([last_post_close])
    use_case = ScoreAndAggregateSentiment(
        store=store,
        sentiment_model=InMemorySentimentModel({"late": 0.1}),
        calendar_provider=narrow_provider,
    )
    request = ScoreAndAggregateSentimentRequest(
        asset=_ASSET,
        start=datetime(2023, 1, 4, tzinfo=UTC),
        end=datetime(2023, 1, 5, tzinfo=UTC),
        close_hour=_NYSE_CLOSE_UTC,
    )
    with pytest.raises(ValueError, match=r"(?i)trading session|window"):
        use_case.execute(request)


# -- regressão end-to-end contra o oráculo diário ----------------------------


def _load_scored_oracle() -> tuple[list[dict[str, object]], dict[str, float]]:
    """Lê o oráculo per-article -> rows da bronze + mapa article_id->score."""
    pq = pytest.importorskip("pyarrow.parquet")
    if not _SCORED_ORACLE.exists():
        pytest.skip(f"scored oracle not present: {_SCORED_ORACLE}")
    table = pq.read_table(_SCORED_ORACLE, columns=["article_id", "published_at", "sentiment_score"])
    data = table.to_pydict()
    rows: list[dict[str, object]] = []
    scores: dict[str, float] = {}
    for aid, pub, score in zip(
        data["article_id"], data["published_at"], data["sentiment_score"], strict=True
    ):
        published_at = pub.to_pydatetime() if hasattr(pub, "to_pydatetime") else pub
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        rows.append(_news_row(str(aid), published_at))
        scores[str(aid)] = float(score)
    return rows, scores


def _load_daily_oracle() -> dict[date, tuple[float, int, float]]:
    """Lê o oráculo diário -> {dia civil: (mean, n, pstdev)}."""
    pq = pytest.importorskip("pyarrow.parquet")
    if not _DAILY_ORACLE.exists():
        pytest.skip(f"daily oracle not present: {_DAILY_ORACLE}")
    table = pq.read_table(
        _DAILY_ORACLE, columns=["day", "sentiment_score", "n_articles", "sentiment_std"]
    )
    data = table.to_pydict()
    out: dict[date, tuple[float, int, float]] = {}
    for day, mean_v, n, std in zip(
        data["day"], data["sentiment_score"], data["n_articles"], data["sentiment_std"], strict=True
    ):
        day_date = day.date() if hasattr(day, "date") else day
        out[day_date] = (float(mean_v), int(n), float(std))
    return out


def test_daily_aggregation_matches_oracle_on_verifiable_days() -> None:
    """Regressão: dias civil==pregão com n>=1 batem com o oráculo diário do old.

    O contrato desta Stage é por dia de PREGÃO só com n>=1; o oráculo do old usa
    dias civis com fill de zero-news. Comparamos só os dias do 1º trimestre/2023 em
    que o agrupamento por dia civil coincide com a sessão de pregão (sem rolagem de
    cutoff) e o oráculo registra n>=1 — esses são os dias verificáveis ([decision]).
    """
    rows, scores = _load_scored_oracle()
    daily_oracle = _load_daily_oracle()

    # Restringe ao 1º trimestre de 2023 (janela coberta pelo FakeExchangeCalendarProvider).
    window_start, window_end = date(2023, 1, 1), date(2023, 3, 31)
    window_rows = [r for r in rows if window_start <= _as_date(r["published_at"]) <= window_end]
    if len(window_rows) < 2:  # noqa: PLR2004 — precisa de ao menos um dia multi-artigo
        pytest.skip("insufficient oracle rows in the 2023-Q1 window")

    store = _store_with(window_rows)
    request = ScoreAndAggregateSentimentRequest(
        asset=_ASSET,
        start=datetime(2023, 1, 1, tzinfo=UTC),
        end=datetime(2023, 3, 31, tzinfo=UTC),
        close_hour=_NYSE_CLOSE_UTC,
    )
    result = _make_use_case(store, scores).execute(request)
    result_by_day = {d.day: d for d in result.daily}

    # Dias em que civil==pregão (sem cutoff cruzando meia-noite UTC): a soma dos
    # scores por dia civil deve coincidir com a do dia de pregão.
    civil_groups: dict[date, list[float]] = defaultdict(list)
    for r in window_rows:
        civil_groups[_as_date(r["published_at"])].append(scores[str(r["article_id"])])

    verifiable = 0
    for day, day_scores in civil_groups.items():
        oracle = daily_oracle.get(day)
        if oracle is None or oracle[1] != len(day_scores) or day not in result_by_day:
            # dia com rolagem de cutoff (n diverge) ou ausente — fora do verificável.
            continue
        dto = result_by_day[day]
        assert dto.n_articles == len(day_scores)
        assert dto.sentiment_score == pytest.approx(statistics.mean(day_scores), abs=1e-6)
        expected_std = statistics.pstdev(day_scores) if len(day_scores) > 1 else 0.0
        assert dto.sentiment_std == pytest.approx(expected_std, abs=1e-6)
        # E bate com o oráculo diário do old nesses dias verificáveis.
        assert dto.sentiment_score == pytest.approx(oracle[0], abs=1e-5)
        assert dto.sentiment_std == pytest.approx(oracle[2], abs=1e-5)
        verifiable += 1

    assert verifiable >= 1, "no verifiable civil==trading-day matches found in the window"


def _as_date(value: object) -> date:
    """Extrai a `date` UTC de um `published_at` (datetime tz-aware)."""
    assert isinstance(value, datetime)
    return value.astimezone(UTC).date() if value.tzinfo else value.date()
