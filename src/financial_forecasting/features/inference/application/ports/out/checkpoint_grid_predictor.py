"""Port-out `CheckpointGridPredictor` do slice `inference` — a grade crua dos checkpoints.

Port do CONSUMIDOR (ADR 0.0.0053; ADR 7.1.0001 item 1): para uma seed do cohort, a
grade crua de `test` e/ou `calib` (partição → decisão → horizonte → tupla alinhada a
`spec.quantile_levels`) de cada fold, só para os `run_id` da lista permitida
(`allowed: run_id → sha256 esperado`). Um run fora da lista ergue antes de qualquer
carga (C6); o sha256 dos bytes carregados é conferido contra o esperado (C10).

Real: o use case `PredictTftFromCheckpoints` do `modeling`, satisfeito por
duck-typing; DTOs do fornecedor só sob `TYPE_CHECKING`, anotações textualmente as
do use case (#93).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from financial_forecasting.features.modeling.application.use_cases.predict_tft_from_checkpoints import (  # noqa: E501
        PredictTftFromCheckpointsCommand,
        PredictTftFromCheckpointsResult,
    )


class CheckpointGridPredictor(Protocol):
    """Grade crua das partições pedidas, a partir dos checkpoints da lista permitida."""

    def __call__(
        self, command: PredictTftFromCheckpointsCommand
    ) -> PredictTftFromCheckpointsResult:
        """Um item por fold; run fora de `allowed` ergue `ApplicationError` sem carregar."""
        ...
