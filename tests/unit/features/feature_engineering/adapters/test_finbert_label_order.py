"""Unit tests do mapeamento de rótulos por NOME do adapter FinBERT — SEM torch.

`FinbertSentimentModel._resolve_canonical_order` é lógica PURA stdlib-only (recebe um
`id2label: dict[int, str]` e devolve os índices na ordem canônica `[neg, neu, pos]`)
e carrega a [decision] da Task 06 (§7 do technical): o SHA pinado de `ProsusAI/finbert`
expõe `id2label = {0: positive, 1: negative, 2: neutral}` — ordem DIFERENTE do índice
fixo `[neg, neu, pos]` que o old assumia; usar índice fixo produziria o score com sinal
TROCADO (`P(neg)-P(pos)`). Este método é a correção do bug latente.

O integration live (Task 08) que exercita o forward completo é SKIPPED no CI (torch
ausente), logo o reordenamento por nome ficava SEM cobertura torch-free: uma mutação
(inverter a ordem canônica, dropar a guarda de label faltante, trocar índices) NÃO
reprovava nenhum teste do CI. Estes testes fecham esse gap — o método é estático,
torch-free e o módulo do adapter importa torch só LAZY dentro do `__init__`, então
chamá-lo direto não exige o extra `sentiment`.
"""

from __future__ import annotations

import pytest

from financial_forecasting.features.feature_engineering.adapters.out.finbert.finbert_sentiment_model import (  # noqa: E501
    FinbertSentimentModel,
)

_resolve = FinbertSentimentModel._resolve_canonical_order


def test_pinned_sha_label_order_is_remapped_by_name() -> None:
    """`{0:positive,1:negative,2:neutral}` (SHA pinado) -> índices canônicos `(neg,neu,pos)`.

    Os índices canônicos `[neg, neu, pos]` apontam para as colunas
    `negative=1`, `neutral=2`, `positive=0` da saída crua — a correção do sinal
    invertido da [decision] Task 06.
    """
    assert _resolve({0: "positive", 1: "negative", 2: "neutral"}) == (1, 2, 0)


def test_already_canonical_order_is_identity() -> None:
    """`{0:negative,1:neutral,2:positive}` (a ordem que o old assumia) -> `(0, 1, 2)`."""
    assert _resolve({0: "negative", 1: "neutral", 2: "positive"}) == (0, 1, 2)


def test_label_matching_is_case_insensitive() -> None:
    """Rótulos em maiúsculas/mistos são casados por nome lowercase."""
    assert _resolve({0: "POSITIVE", 1: "Negative", 2: "NEUTRAL"}) == (1, 2, 0)


def test_arbitrary_permutation_is_resolved_by_name() -> None:
    """Qualquer permutação dos 3 rótulos é resolvida por NOME, não por posição."""
    assert _resolve({0: "neutral", 1: "positive", 2: "negative"}) == (2, 0, 1)


@pytest.mark.parametrize(
    "id2label",
    [
        {0: "positive", 1: "negative"},  # falta neutral
        {0: "positive", 1: "neutral"},  # falta negative
        {0: "negative", 1: "neutral"},  # falta positive
        {0: "bullish", 1: "bearish", 2: "flat"},  # rótulos totalmente inesperados
        {},  # vazio
    ],
)
def test_missing_expected_label_raises(id2label: dict[int, str]) -> None:
    """Revisão sem algum rótulo canônico (`neg`/`neu`/`pos`) -> `ValueError` (defesa Q1/§5)."""
    with pytest.raises(ValueError, match="missing expected labels"):
        _resolve(id2label)
