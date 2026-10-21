"""Port-out `PermutedPredictionPersister` do `inference` — grava um run da atribuição (7.3).

Port do CONSUMIDOR (ADR 0.0.0053; ADR 7.3.0002 item 4): o `RunPermutationInference`
grava a identidade e as passagens permutadas de UM run por chamada, pelo use case dono
da tabela `fact_permuted_predictions` e do `target_timestamp` (ADR 4.3.0001) — nunca
monta a linha sozinho. Entrada com `permuted_family = "none"` fora do índice 0 (ou o
contrário) ergue `ValueError` antes de escrever; `DuplicateKeyError` propaga.

Real: o use case `PersistPermutedPredictions` do `analytics_store`, por duck-typing;
DTOs do fornecedor só sob `TYPE_CHECKING`, anotações textualmente as do use case (#93).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from financial_forecasting.features.analytics_store.application.use_cases.persist_permuted_predictions import (  # noqa: E501
        PersistPermutedPredictionsCommand,
        PersistPermutedPredictionsResult,
    )


class PermutedPredictionPersister(Protocol):
    """Persiste as predições de atribuição de um run numa escrita só."""

    def __call__(
        self, command: PersistPermutedPredictionsCommand
    ) -> PersistPermutedPredictionsResult:
        """Grava as linhas LONG resolvíveis do run e devolve as contagens."""
        ...
