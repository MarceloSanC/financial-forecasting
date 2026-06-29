"""Fake in-memory do port `SentimentModel` — NÃO um mock (concept 3.2 A2).

`InMemorySentimentModel` é um fake COMPORTAMENTAL determinístico (stdlib-only):
para cada `NewsArticle` devolve um score finito em `[-1, +1]`, resolvido por um
**mapa `article_id -> score`** injetado (default) ou por uma **função** `NewsArticle
-> float`; artigos sem entrada caem num `default_score` finito. Aplica a MESMA
semântica observável que o adapter real (`FinbertSentimentModel`): 1 score por
artigo, **ordem preservada** (`articles[i] -> scores[i]`), score em `[-1, +1]`,
sequência vazia -> saída vazia. Não asserta chamadas — produz comportamento real e
estável (skill `pytest-with-fakes`).

Expõe `model_name`/`revision` (defaults fake) para satisfazer o `Protocol`
`SentimentModel` por duck-typing e permitir que o use case (Tasks 04/05) e o
contract test rodem **sem torch**. Vive em `tests/` (fora do gate `import-linter`),
mas mantém o contrato agnóstico de ML: importa SÓ stdlib + a entity `NewsArticle`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)

_DEFAULT_MODEL_NAME = "fake/sentiment"
_DEFAULT_REVISION = "fake-revision"


def _clamp(value: float) -> float:
    """Garante o invariante de fronteira do port (score em `[-1, +1]`, I1)."""
    return max(-1.0, min(1.0, float(value)))


class InMemorySentimentModel:
    """Implementação in-memory determinística do contrato `SentimentModel`.

    `scores_by_article_id` mapeia `article_id -> score`; `score_fn` (alternativa)
    resolve o score a partir do próprio `NewsArticle`. Sem mapa nem função, todo
    artigo recebe `default_score`. Os scores são sempre clampeados em `[-1, +1]`
    (I1), de modo que o fake nunca viole o contrato observável do port.
    """

    def __init__(
        self,
        scores_by_article_id: Mapping[str, float] | None = None,
        *,
        score_fn: Callable[[NewsArticle], float] | None = None,
        default_score: float = 0.0,
        model_name: str = _DEFAULT_MODEL_NAME,
        revision: str = _DEFAULT_REVISION,
    ) -> None:
        self._scores_by_article_id: dict[str, float] = dict(scores_by_article_id or {})
        self._score_fn = score_fn
        self._default_score = _clamp(default_score)
        self.model_name = model_name
        self.revision = revision

    def score_articles(self, articles: Sequence[NewsArticle]) -> Sequence[float]:
        """Pontua cada artigo em `[-1, +1]`, preservando a ordem da entrada (I1/I2)."""
        return [self._score_one(article) for article in articles]

    def _score_one(self, article: NewsArticle) -> float:
        if self._score_fn is not None:
            return _clamp(self._score_fn(article))
        if article.article_id is not None and article.article_id in self._scores_by_article_id:
            return _clamp(self._scores_by_article_id[article.article_id])
        return self._default_score
