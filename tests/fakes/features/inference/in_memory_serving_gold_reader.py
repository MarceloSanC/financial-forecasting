"""Fake in-memory do port `ServingGoldReader` do `inference` (Stage 7.4).

Devolve o `ServingGold` carregado para a partição (`asset`, `cohort_id`). Sem
fallback: partição não carregada ergue `KeyError` — o teste carrega
`ServingGold.unpublished` explicitamente quando quer o gold ausente, e a forma desse
estado é provada contra o real pela suíte de contrato (Checkpoint B, B4). `error`
simula a geração que não se sustenta (o real ergue `ApplicationError`).
"""

from __future__ import annotations

from collections.abc import Mapping

from financial_forecasting.features.inference.application.dtos.serving_gold import (
    ServingGold,
)


class InMemoryServingGoldReader:
    """Satisfaz `ServingGoldReader` com um mapa partição → `ServingGold`."""

    def __init__(
        self,
        golds: Mapping[tuple[str, str], ServingGold],
        *,
        error: Exception | None = None,
    ) -> None:
        self._golds = dict(golds)
        self._error = error
        self.calls: list[tuple[str, str]] = []

    def read(self, *, asset: str, cohort_id: str) -> ServingGold:
        self.calls.append((asset, cohort_id))
        if self._error is not None:
            raise self._error
        return self._golds[(asset, cohort_id)]
