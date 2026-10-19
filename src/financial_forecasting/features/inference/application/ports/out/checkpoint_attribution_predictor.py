"""Port-out `CheckpointAttributionPredictor` do `inference` — predições de atribuição (7.3).

Port do CONSUMIDOR (ADR 0.0.0053; ADR 7.3.0002 item 1): para uma seed do cohort, a
identidade, as predições permutadas por (família, k) e os pesos da VSN do encoder de
cada fold, só para os `run_id` da lista permitida. A partição de famílias do comando
tem de ser a da registry do fornecedor; os doadores de cada fold são K_p permutações
das decisões de teste com emissão (C1); uma coluna de família que não é real
`unknown` ergue `FamilyFeatureKnownError` (C5); sha256 diferente do esperado ergue
`ArtifactChangedError` (C7).

Real: o use case `PredictTftAttributionFromCheckpoints` do `modeling`, satisfeito por
duck-typing; DTOs do fornecedor só sob `TYPE_CHECKING`, anotações textualmente as do
use case (#93).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from financial_forecasting.features.modeling.application.use_cases.predict_tft_attribution_from_checkpoints import (  # noqa: E501
        PredictTftAttributionCommand,
        PredictTftAttributionResult,
    )


class CheckpointAttributionPredictor(Protocol):
    """Identidade, permutadas e VSN dos checkpoints da lista permitida, por fold."""

    def __call__(self, command: PredictTftAttributionCommand) -> PredictTftAttributionResult:
        """Um item por fold; as guardas erguem antes de qualquer carga (ver módulo)."""
        ...
