"""Unit tests da lógica pura de scoring (`scores_from_probs` + `build_text`) — sem torch.

Cobre (concept 3.2 A3/A4):

- `scores_from_probs`: scores hand-computed exatos (`[0.1,0.2,0.7] -> 0.6`, etc.),
  `ValueError` para linha com != 3 componentes, resultado em `[-1, +1]` (I1/C5).
- `build_text`: 4 casos (ambos / só headline / só summary / vazios -> fallback `" "`)
  (I10).
- **Regressão de invariante contra o oráculo** `scored_news_AAPL.parquet`: o parquet
  guarda o score FINAL (`P(pos)-P(neg)`) e `confidence`, NÃO os vetores de
  probabilidade — então o oráculo entra como rede de invariante (todo
  `sentiment_score in [-1,+1]`; `confidence == abs(sentiment_score)`), não como fonte
  de probs (premissa §1 do technical). A leitura usa `pytest.importorskip("pyarrow")`
  para resiliência (o teste vive em `tests/`, fora do gate import-linter).

Tudo roda SEM torch/transformers (I8).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path

import pytest

from financial_forecasting.features.feature_engineering.adapters.out.finbert.scoring import (
    build_text,
    scores_from_probs,
)
from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)

# Raiz do repo: .../tests/unit/features/feature_engineering/adapters/<file>
# parents: 0=adapters 1=feature_engineering 2=features 3=unit 4=tests 5=repo_root.
_REPO_ROOT = Path(__file__).resolve().parents[5]
_ORACLE = _REPO_ROOT / "data" / "processed" / "scored_news" / "AAPL" / "scored_news_AAPL.parquet"


@pytest.mark.parametrize(
    ("probs_row", "expected"),
    [
        ([0.1, 0.2, 0.7], 0.6),  # P(pos)-P(neg) = 0.7-0.1
        ([0.7, 0.2, 0.1], -0.6),  # 0.1-0.7
        ([0.0, 1.0, 0.0], 0.0),  # neutro puro
        ([1.0, 0.0, 0.0], -1.0),  # negativo extremo
        ([0.0, 0.0, 1.0], 1.0),  # positivo extremo
    ],
)
def test_scores_from_probs_hand_computed(probs_row: list[float], expected: float) -> None:
    """Scores hand-computed exatos a partir de `[neg, neu, pos]` (I1)."""
    (score,) = scores_from_probs([probs_row])
    assert score == pytest.approx(expected)


def test_scores_from_probs_preserves_order_and_count() -> None:
    """1 score por linha, na mesma ordem das probs (I2 na camada pura)."""
    probs = [[0.1, 0.2, 0.7], [0.7, 0.2, 0.1], [0.0, 1.0, 0.0]]
    scores = scores_from_probs(probs)
    assert scores == pytest.approx([0.6, -0.6, 0.0])


def test_scores_from_probs_result_in_unit_range() -> None:
    """Por construção (`p in [0,1]`), o resultado fica em `[-1, +1]`."""
    probs = [[0.33, 0.33, 0.34], [0.8, 0.1, 0.1], [0.05, 0.05, 0.9]]
    for score in scores_from_probs(probs):
        assert -1.0 <= score <= 1.0


def test_scores_from_probs_empty_input() -> None:
    """Sequência vazia -> saída vazia."""
    assert scores_from_probs([]) == []


@pytest.mark.parametrize("bad_row", [[0.5, 0.5], [0.2, 0.2, 0.2, 0.4], [1.0], []])
def test_scores_from_probs_rejects_wrong_component_count(bad_row: list[float]) -> None:
    """Linha com != 3 componentes -> `ValueError` explícito (C5)."""
    with pytest.raises(ValueError, match="exactly 3 components"):
        scores_from_probs([bad_row])


def _article(headline: str, summary: str) -> NewsArticle:
    return NewsArticle(
        asset_id="AAPL",
        published_at=datetime(2023, 1, 3, 12, 0, tzinfo=UTC),
        headline=headline,
        summary=summary,
        source="unit-test",
        article_id="a1",
    )


def test_build_text_both_present() -> None:
    """`headline` + `summary` juntados por espaço."""
    text = build_text(_article("  Apple beats  ", " on strong iPhone "))
    assert text == "Apple beats on strong iPhone"


def test_build_text_headline_only() -> None:
    """Só `headline` (summary vazio)."""
    assert build_text(_article("Apple up", "   ")) == "Apple up"


def test_build_text_summary_only() -> None:
    """Só `summary` (headline vazio)."""
    assert build_text(_article("", "Strong guidance")) == "Strong guidance"


def test_build_text_both_empty_fallback() -> None:
    """Ambos vazios -> fallback neutro `" "` (não texto vazio)."""
    assert build_text(_article("   ", "")) == " "


def test_oracle_invariants_range_and_confidence() -> None:
    """Regressão de invariante: oráculo respeita `score in [-1,+1]` e `confidence == |score|`."""
    pq = pytest.importorskip("pyarrow.parquet")
    if not _ORACLE.exists():
        pytest.skip(f"oracle parquet not present: {_ORACLE}")
    table = pq.read_table(_ORACLE, columns=["sentiment_score", "confidence"])
    data = table.to_pydict()
    scores = data["sentiment_score"]
    confidences = data["confidence"]
    assert len(scores) > 0
    for score, confidence in zip(scores, confidences, strict=True):
        assert -1.0 <= score <= 1.0
        assert confidence == pytest.approx(abs(score), abs=1e-6)
        assert math.isfinite(score)
