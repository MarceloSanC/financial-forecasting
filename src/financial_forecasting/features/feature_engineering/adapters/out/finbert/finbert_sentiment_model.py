"""Adapter `FinbertSentimentModel` — scoring de sentimento via FinBERT (revisão pinada).

Implementa o port `SentimentModel` (Task 01) por duck-typing usando
`ProsusAI/finbert` com uma **revisão HF pinada** (SHA do commit), congelando os
pesos para reprodutibilidade (ADR 0.0.0017). `transformers`/`torch` são importados
de forma **LAZY** (dentro do `__init__`, nunca no topo do módulo): assim a coleta de
testes e o `mypy --strict` do CI — que roda `uv sync --extra dev`, SEM o extra
`sentiment` — não exigem as libs, e o modelo (~400 MB) NÃO é baixado no fluxo
unattended (concept 3.2 I5/I9/D2/D3). Esta é a ÚNICA casa de `torch`/`transformers`
no BC; o gate import-linter `sentiment-no-ml-leak` (Task 07) reprova vazamento.

A FÓRMULA do score (`P(pos) - P(neg)`) é delegada à função pura
`scores_from_probs` (Task 03, stdlib-only, validada por oráculo); este adapter só
produz os vetores de probabilidade.

**Mapeamento de rótulos por NOME (decision Task 06):** o SHA pinado expõe
`config.id2label = {0: positive, 1: negative, 2: neutral}` — ordem DIFERENTE do
índice fixo `[neg, neu, pos]` que o old assumia. Por isso o adapter reordena a saída
crua do modelo para a ordem canônica `[neg, neu, pos]` consultando `id2label` (mapa
por nome), em vez de usar índices fixos. `scores_from_probs` recebe sempre a ordem
canônica e permanece simples/pura.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final

from financial_forecasting.features.feature_engineering.adapters.out.finbert.scoring import (
    build_text,
    scores_from_probs,
)

if TYPE_CHECKING:  # imports só para o type checker — não são dependências de runtime
    from financial_forecasting.features.market_data.domain.entities.news_article import (
        NewsArticle,
    )

# Revisão HF pinada (SHA do commit de ProsusAI/finbert) — congela os pesos (I6).
# Resolvida na execução via metadados HF (sem baixar pesos): config.json deste SHA
# tem id2label = {0: positive, 1: negative, 2: neutral} (ver mapeamento por nome).
_PINNED_REVISION: Final = "4556d13015211d73dccd3fdd39d39232506f3e43"
_MODEL_NAME: Final = "ProsusAI/finbert"
_BATCH_SIZE: Final = 16
_MAX_LENGTH: Final = 512
# Ordem canônica esperada por `scores_from_probs` (labels lowercase de id2label).
_CANONICAL_LABELS: Final = ("negative", "neutral", "positive")

_INSTALL_HINT: Final = (
    "FinbertSentimentModel requires the optional 'sentiment' extra "
    "(torch + transformers). Install it with: uv sync --extra sentiment"
)


class FinbertSentimentModel:
    """Adapter FinBERT que satisfaz o port `SentimentModel` (import lazy de torch)."""

    model_name: str
    revision: str

    def __init__(
        self,
        *,
        revision: str = _PINNED_REVISION,
        batch_size: int = _BATCH_SIZE,
        max_length: int = _MAX_LENGTH,
        device: str | None = None,
    ) -> None:
        self.model_name = _MODEL_NAME
        self.revision = revision
        self._batch_size = int(batch_size)
        self._max_length = int(max_length)

        # Import LAZY: falha com mensagem clara se o extra `sentiment` não estiver
        # instalado (em vez de ImportError opaco no topo do módulo, I5/C4).
        try:
            import torch
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )
        except ImportError as exc:  # pragma: no cover - exige ausência do extra
            raise ImportError(_INSTALL_HINT) from exc

        self._torch = torch
        self._device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name, revision=self.revision)
        self._model = AutoModelForSequenceClassification.from_pretrained(
            self.model_name, revision=self.revision
        ).to(self._device)
        self._model.eval()
        # Posição de cada label canônico na saída do modelo (mapeamento por NOME).
        self._canonical_order = self._resolve_canonical_order(self._model.config.id2label)

    def score_articles(self, articles: Sequence[NewsArticle]) -> Sequence[float]:
        """Pontua cada artigo em `[-1, +1]`, preservando a ordem (I1/I2)."""
        if not articles:
            return []
        texts = [build_text(article) for article in articles]
        probs = self._score_texts(texts)
        return scores_from_probs(probs)

    # -- internos ------------------------------------------------------------

    @staticmethod
    def _resolve_canonical_order(id2label: dict[int, str]) -> tuple[int, int, int]:
        """Mapeia cada label canônico (`negative/neutral/positive`) à sua coluna no logit.

        Consulta `id2label` por NOME (lowercase) e devolve os índices na ordem
        canônica `[neg, neu, pos]`. Levanta `ValueError` se algum label esperado
        faltar — defende contra uma revisão com rótulos inesperados (Q1/risco §5).
        """
        label_to_index = {str(label).lower(): index for index, label in id2label.items()}
        missing = [label for label in _CANONICAL_LABELS if label not in label_to_index]
        if missing:
            raise ValueError(
                f"FinBERT config.id2label missing expected labels {missing}; "
                f"got {sorted(label_to_index)}"
            )
        # A guarda `missing` acima garante que os 3 labels canônicos resolvem,
        # então este é um 3-tuple de tamanho fixo (sem `type: ignore` no boundary).
        return (
            label_to_index[_CANONICAL_LABELS[0]],
            label_to_index[_CANONICAL_LABELS[1]],
            label_to_index[_CANONICAL_LABELS[2]],
        )

    def _score_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Tokeniza + forward em batches; devolve probs na ordem canônica `[neg,neu,pos]`."""
        torch = self._torch
        canonical_probs: list[list[float]] = []
        neg_idx, neu_idx, pos_idx = self._canonical_order
        with torch.no_grad():
            for batch in self._batches(texts):
                inputs = self._tokenizer(
                    list(batch),
                    padding=True,
                    truncation=True,
                    max_length=self._max_length,
                    return_tensors="pt",
                ).to(self._device)
                logits = self._model(**inputs).logits
                raw: list[list[float]] = torch.softmax(logits, dim=1).detach().cpu().tolist()
                for row in raw:
                    canonical_probs.append([row[neg_idx], row[neu_idx], row[pos_idx]])
        return canonical_probs

    def _batches(self, texts: Sequence[str]) -> list[Sequence[str]]:
        """Fatia `texts` em lotes de `batch_size` (do old; controla memória)."""
        step = self._batch_size
        return [texts[i : i + step] for i in range(0, len(texts), step)]
