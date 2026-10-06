"""Port-out `PredictionPersister` do slice `inference` — grava uma decisão de calib (7.1).

Port do CONSUMIDOR (ADR 0.0.0053), mesma forma do homônimo do `modeling`: o
`RunInference` grava cada decisão de `calib` ausente pelo use case dono da linha
LONG e do `target_timestamp` (ADR 4.3.0001) — nunca monta a linha sozinho.
`DuplicateKeyError` (colisão de PK) propaga.

Real: o use case `PersistPredictions` do `analytics_store`, por duck-typing; DTOs
do fornecedor só sob `TYPE_CHECKING`, anotações textualmente as do use case (#93).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
        PersistPredictionsCommand,
        PersistPredictionsResult,
    )


class PredictionPersister(Protocol):
    """Persiste a grade densa de uma decisão (todos os horizontes) no formato LONG."""

    def __call__(self, command: PersistPredictionsCommand) -> PersistPredictionsResult:
        """Grava as linhas LONG resolvíveis e devolve as contagens."""
        ...
