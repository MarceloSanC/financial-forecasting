"""Port-out `VsnWeightPersister` do `inference` — grava os pesos da VSN de um run (7.3).

Port do CONSUMIDOR (ADR 0.0.0053; ADR 7.3.0002 item 4): o `RunPermutationInference`
grava os pesos do encoder de UM run por chamada, pelo use case dono da tabela
`fact_vsn_weights`. Variável sem família declarada ergue `ValueError`.

Real: o use case `PersistVsnWeights` do `analytics_store`, por duck-typing; DTOs do
fornecedor só sob `TYPE_CHECKING`, anotações textualmente as do use case (#93).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from financial_forecasting.features.analytics_store.application.use_cases.persist_vsn_weights import (  # noqa: E501
        PersistVsnWeightsCommand,
        PersistVsnWeightsResult,
    )


class VsnWeightPersister(Protocol):
    """Persiste os pesos da VSN de um run numa escrita só."""

    def __call__(self, command: PersistVsnWeightsCommand) -> PersistVsnWeightsResult:
        """Grava uma linha por (decisão, variável) e devolve a contagem."""
        ...
