"""Integration test LIVE do `FinbertSentimentModel` — SKIPPED no CI (concept 3.2 A10).

`@pytest.mark.skipif`: pulado quando `torch`/`transformers` estão ausentes — exatamente
o caso do CI, que roda `uv sync --extra dev` (sem o extra `sentiment`). Assim o modelo
(~400 MB) NÃO é baixado no fluxo unattended (I9/I8). Quando rodado MANUALMENTE com
`uv sync --extra sentiment`, baixa o modelo pinado e valida a FUMAÇA de integração:
`score_articles` devolve scores finitos em `[-1, +1]` (ordem preservada) e o sinal é
coerente para uma notícia claramente positiva vs negativa.

A FÓRMULA (`P(pos)-P(neg)`) já é coberta sem torch pela função pura `scores_from_probs`
(Task 03) e a FORMA pelo contract test (Task 02/06); aqui o objetivo é só confirmar que
o adapter real carrega o modelo pinado e produz scores no contrato.
"""

from __future__ import annotations

import importlib
import importlib.util
import math
from datetime import UTC, datetime

import pytest

from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)

_MIN_SHA_LEN = 7  # uma revisão HF pinada tem pelo menos um short-SHA
_TORCH_MISSING = (
    importlib.util.find_spec("torch") is None or importlib.util.find_spec("transformers") is None
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        _TORCH_MISSING,
        reason="optional 'sentiment' extra (torch/transformers) not installed; "
        "run `uv sync --extra sentiment` to exercise the live FinBERT adapter",
    ),
]


def _article(article_id: str, headline: str, summary: str) -> NewsArticle:
    return NewsArticle(
        asset_id="AAPL",
        published_at=datetime(2023, 1, 3, 12, 0, tzinfo=UTC),
        headline=headline,
        summary=summary,
        source="integration-test",
        article_id=article_id,
    )


def _build_model() -> object:
    # Import dinâmico via importlib: o adapter só carrega quando o extra `sentiment`
    # está instalado; evita PLC0415 e mantém a paridade com o skipif.
    module = importlib.import_module(
        "financial_forecasting.features.feature_engineering.adapters.out.finbert."
        "finbert_sentiment_model"
    )
    return module.FinbertSentimentModel(device="cpu")


def test_score_articles_returns_unit_range_and_preserves_order() -> None:
    """Live: scores finitos em `[-1, +1]`, 1 por artigo, ordem preservada (I1/I2)."""
    model = _build_model()
    articles = [
        _article("pos", "Apple beats estimates", "record revenue and strong guidance"),
        _article("neg", "Apple shares plunge", "weak demand triggers a sharp selloff"),
    ]
    scores = list(model.score_articles(articles))  # type: ignore[attr-defined]

    assert len(scores) == len(articles)
    for score in scores:
        assert math.isfinite(score)
        assert -1.0 <= score <= 1.0


def test_positive_news_scores_above_negative_news() -> None:
    """Live: notícia claramente positiva pontua acima da claramente negativa (sinal coerente)."""
    model = _build_model()
    positive = _article("pos", "Apple beats estimates", "record revenue and strong guidance")
    negative = _article("neg", "Apple shares plunge", "weak demand triggers a sharp selloff")
    pos_score, neg_score = model.score_articles([positive, negative])  # type: ignore[attr-defined]
    assert pos_score > neg_score


def test_exposes_pinned_revision() -> None:
    """Live: o adapter expõe a revisão pinada usada para carregar os pesos (I6)."""
    model = _build_model()
    assert model.model_name == "ProsusAI/finbert"  # type: ignore[attr-defined]
    revision = model.revision  # type: ignore[attr-defined]
    assert isinstance(revision, str) and len(revision) >= _MIN_SHA_LEN
