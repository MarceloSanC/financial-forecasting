"""Lógica pura de scoring de sentimento — stdlib-only, SEM torch/transformers.

Este módulo isola a FÓRMULA do score e a montagem do texto de entrada, as duas
peças do adapter `FinbertSentimentModel` (Task 06) que NÃO dependem de
`torch`/`transformers`. Separá-las aqui é o que garante a cobertura >=90% do código
vivo do BC SEM instalar torch no CI (concept 3.2 I8/D3): o adapter real só produz os
vetores de probabilidade (tokenização + forward) e DELEGA a fórmula a
`scores_from_probs` e o texto a `build_text` — ambos testáveis com fixtures puras.

Convenção de rótulos (concept 3.2 I1): `scores_from_probs` espera as probabilidades
já na ORDEM CANÔNICA `[neg, neu, pos]` e calcula `p[2] - p[0]` = `P(pos) - P(neg)`.
A responsabilidade de reordenar a saída crua do modelo para essa ordem canônica (o
SHA pinado de `ProsusAI/finbert` expõe `id2label = {0: positive, 1: negative,
2: neutral}` — ordem DIFERENTE do índice fixo do old) é do adapter, que mapeia por
NOME via `model.config.id2label` antes de chamar esta função (ver Task 06 §7
[decision]). Assim a fórmula permanece simples, pura e validável por oráculo.
"""

from __future__ import annotations

from collections.abc import Sequence

from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)

_PROB_COMPONENTS = 3  # [neg, neu, pos] — labels FinBERT na ordem canônica
_NEUTRAL_TEXT = " "  # fallback neutro quando headline+summary são vazios (old)


def scores_from_probs(probs: Sequence[Sequence[float]]) -> list[float]:
    """Converte probabilidades `[neg, neu, pos]` em scores `P(pos) - P(neg)` (I1/C5).

    Cada linha de `probs` deve ter EXATAMENTE 3 componentes na ordem canônica
    `[neg, neu, pos]`; uma linha com número diferente de componentes levanta
    `ValueError` explícito (não devolve score parcial/silencioso). Por construção,
    com `p in [0, 1]`, o resultado fica em `[-1, +1]`.

    Função pura: mesma entrada -> mesma saída; sem estado, sem I/O, sem torch.
    """
    scores: list[float] = []
    for index, row in enumerate(probs):
        row_list = list(row)
        if len(row_list) != _PROB_COMPONENTS:
            raise ValueError(
                f"Probability row {index} must have exactly {_PROB_COMPONENTS} components "
                f"[neg, neu, pos]; got {len(row_list)}"
            )
        scores.append(float(row_list[2]) - float(row_list[0]))
    return scores


def build_text(article: NewsArticle) -> str:
    """Monta o texto de entrada do modelo a partir de `headline` + `summary` (I10).

    Replica a política do old (`finbert_sentiment_model.py:_build_text`):
    `strip()` em ambos, junta com espaço os não-vazios; se ambos forem vazios,
    devolve o token neutro `" "` (evita texto vazio na tokenização). Vive no
    adapter (não cruza o port).
    """
    headline = (article.headline or "").strip()
    summary = (article.summary or "").strip()
    text = " ".join(part for part in (headline, summary) if part)
    return text if text else _NEUTRAL_TEXT
