"""Port-out `EvaluationWriterLock` — lock de escritor único do `data_root` (Stage 8.1).

Port do **consumidor** (concept 8.1 §4, D8; ADR 0.0.0053): o subconjunto do
`CohortProgressLedger` do `modeling` que o `RunConfirmatoryEvaluation` usa para ser o
único escritor do gold e da cópia julgada durante a corrida (pré-condição do
`GoldStore` e do `JudgedGenerationStore`). Lock já detido ergue um `ApplicationError` do
dono (`CohortRunLockedError`), que propaga sem ser importado aqui.

Real: `JsonCohortProgressLedger` (adapter do `modeling`), por duck typing — precedente
`CohortLedger` do `inference` (ADR 7.1.0004 item 5). Fake:
`InMemoryEvaluationWriterLock` (`tests/fakes/features/evaluation/`).
"""

from __future__ import annotations

from typing import Protocol


class EvaluationWriterLock(Protocol):
    """Lock de escritor único do `data_root`."""

    def acquire_writer(self, *, break_stale: bool = False) -> None:
        """Adquire o lock; já detido → `ApplicationError`.

        `break_stale=True` remove o lock existente e o adquire (uso explícito).
        """
        ...

    def release_writer(self) -> None:
        """Libera o lock que esta instância adquiriu (idempotente)."""
        ...
