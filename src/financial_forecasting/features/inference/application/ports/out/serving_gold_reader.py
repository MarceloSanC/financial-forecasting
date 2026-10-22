"""Port-out `ServingGoldReader` do slice `inference` — o gold que a API serve (Stage 7.4).

Port do CONSUMIDOR (ADR 0.0.0053; concept 7.2 D9; ADR 7.4.0001 item 7): o
`ServeInference` pede, para o cohort servido, as correções conformais e a leitura de
H3 da geração gold viva. Regras de toda implementação:

- partição sem geração publicada → `ServingGold.unpublished` (estado, não erro);
- geração `BLOCKED`, sem bloco `[conformal]`/`[h3]` no pré-registro ou sem leitura
  de H3 → o bloco correspondente `unavailable`, com motivo;
- geração que não se sustenta (corrompida, rótulo gravado divergente da constante de
  dono único) → `ApplicationError`.

Real: o use case `ReadServingGold` do `evaluation`, satisfeito por duck-typing (a
anotação de `read` é textualmente a do use case — o `check_port_coverage.py` compara
texto, #93); o `evaluation` monta os DTOs daqui (aresta evaluation → inference). Fake:
`InMemoryServingGoldReader` (`tests/fakes/features/inference/`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from financial_forecasting.features.inference.application.dtos.serving_gold import (
        ServingGold,
    )


class ServingGoldReader(Protocol):
    """Lê o que a API serve da geração gold viva de um cohort."""

    def read(self, *, asset: str, cohort_id: str) -> ServingGold:
        """O gold servido da partição (`asset`, `cohort_id`).

        Raises:
            ApplicationError: a geração lida não se sustenta.
        """
        ...
