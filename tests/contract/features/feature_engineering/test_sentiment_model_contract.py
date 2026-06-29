"""Contract test do port `SentimentModel` — paridade Fake <-> FinbertSentimentModel.

Um ÚNICO contrato parametrizado prova que as implementações honram a MESMA
semântica observável de FORMA (concept 3.2 A2/A8):

- `score_articles` devolve 1 score por artigo (`len(scores) == len(articles)`).
- **ordem preservada:** `articles[i] -> scores[i]` (permutar a entrada permuta a
  saída na mesma ordem) — I2.
- todo score é finito e está em `[-1, +1]` (I1/C6).
- sequência vazia -> saída vazia.
- expõe `model_name`/`revision` (str) para rastreabilidade (I6).

A FÓRMULA (`P(pos) - P(neg)`) é coberta pela função pura `scores_from_probs`
(Task 03, sem torch). Aqui validamos só a FORMA compartilhada por fake e real.

A partir da Task 06 a fixture parametrizada inclui o `FinbertSentimentModel` real
sob `skipif` (torch/transformers/modelo ausentes) — **SKIPPED no CI** (não baixa
~400 MB). A paridade de forma fake<->real é o que se valida aqui.
"""

from __future__ import annotations

import importlib
import importlib.util
import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

# `SentimentModel` (Protocol, duck-typed) tipa a fixture parametrizada [fake, (real)].
from financial_forecasting.features.feature_engineering.application.ports.out.sentiment_model import (  # noqa: E501
    SentimentModel,
)
from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)
from tests.fakes.features.feature_engineering.in_memory_sentiment_model import (
    InMemorySentimentModel,
)

_ASSET = "AAPL"
_BASE_TS = datetime(2023, 1, 3, 12, 0, tzinfo=UTC)

# Mapa article_id -> score distinto por artigo (prova ordem preservada).
_SCORES = {"a1": 0.6, "a2": -0.4, "a3": 0.1, "a4": -0.9}

_TORCH_MISSING = (
    importlib.util.find_spec("torch") is None or importlib.util.find_spec("transformers") is None
)


def _article(article_id: str, headline: str = "h", summary: str = "s") -> NewsArticle:
    """Constrói um `NewsArticle` válido (tz-aware) com `article_id` distinto."""
    offset = sum(ord(ch) for ch in article_id)
    return NewsArticle(
        asset_id=_ASSET,
        published_at=_BASE_TS + timedelta(minutes=offset),
        headline=headline,
        summary=summary,
        source="unit-test",
        article_id=article_id,
    )


def _make_fake() -> SentimentModel:
    return InMemorySentimentModel(_SCORES)


def _make_finbert() -> SentimentModel:
    # Import LAZY via importlib: o adapter (Task 06) instancia torch/transformers no
    # __init__; importá-lo estaticamente no topo quebraria a coleta no CI sem torch.
    # `import_module` (em vez de `from ... import`) é o idioma de import dinâmico que
    # evita o PLC0415 e mantém a paridade com o skipif do integration test (Task 08).
    module = importlib.import_module(
        "financial_forecasting.features.feature_engineering.adapters.out.finbert."
        "finbert_sentiment_model"
    )
    finbert_cls: type[SentimentModel] = module.FinbertSentimentModel
    return finbert_cls()


_FACTORIES: list[Callable[[], SentimentModel]] = [_make_fake]
_IDS = ["fake"]
if not _TORCH_MISSING:  # pragma: no cover - depende do extra opcional sentiment
    _FACTORIES.append(_make_finbert)
    _IDS.append("real")


@pytest.fixture(params=_FACTORIES, ids=_IDS)
def model(request: pytest.FixtureRequest) -> SentimentModel:
    """Parametriza o contrato sobre o fake e (sob skipif) o adapter real."""
    factory: Callable[[], SentimentModel] = request.param
    return factory()


@pytest.mark.contract
def test_one_score_per_article(model: SentimentModel) -> None:
    """Devolve um score por artigo de entrada."""
    articles = [_article(aid) for aid in _SCORES]
    scores = model.score_articles(articles)
    assert len(scores) == len(articles)


@pytest.mark.contract
def test_order_preserved(model: SentimentModel) -> None:
    """Permutar a entrada permuta a saída na MESMA ordem (I2)."""
    ids = list(_SCORES)
    articles = [_article(aid) for aid in ids]
    reversed_articles = list(reversed(articles))
    scores = list(model.score_articles(articles))
    reversed_scores = list(model.score_articles(reversed_articles))
    assert reversed_scores == list(reversed(scores))


@pytest.mark.contract
def test_scores_in_unit_range_and_finite(model: SentimentModel) -> None:
    """Todo score é finito e está em `[-1, +1]` (I1/C6)."""
    articles = [_article(aid) for aid in _SCORES]
    for score in model.score_articles(articles):
        assert math.isfinite(score)
        assert -1.0 <= score <= 1.0


@pytest.mark.contract
def test_empty_input_yields_empty_output(model: SentimentModel) -> None:
    """Sequência vazia -> saída vazia."""
    assert list(model.score_articles([])) == []


@pytest.mark.contract
def test_exposes_model_name_and_revision(model: SentimentModel) -> None:
    """Expõe `model_name`/`revision` (str) para rastreabilidade (I6)."""
    assert isinstance(model.model_name, str) and model.model_name
    assert isinstance(model.revision, str) and model.revision
