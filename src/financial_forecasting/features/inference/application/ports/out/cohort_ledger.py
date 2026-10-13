"""Port-out `CohortLedger` do slice `inference` — lock e ambiente do cohort (Stage 7.1).

Port do CONSUMIDOR (ADR 0.0.0053): subconjunto EXATO do `CohortProgressLedger` do
`modeling` — o lock de escritor único do `data_root` (I11; a inferência grava no
mesmo `fact_oos_predictions` que a corrida do cohort) e o ambiente que a primeira
execução do cohort gravou (referência do modo de reprodução, I6; ausente → C11).
O lock já detido ergue `CohortRunLockedError` do `modeling`, que propaga como
`ApplicationError` sem ser importado aqui (C12).

Real: `JsonCohortProgressLedger` (adapter do `modeling`), por duck-typing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class CohortLedger(Protocol):
    """Lock de escritor do `data_root` e ambiente gravado do cohort."""

    def acquire_writer(self, *, break_stale: bool = False) -> None:
        """Adquire o lock de escritor único; já detido → `ApplicationError` (C12).

        `break_stale=True` remove o lock existente e o adquire (uso explícito).
        """
        ...

    def release_writer(self) -> None:
        """Libera o lock que esta instância adquiriu (idempotente)."""
        ...

    def environment(self, cohort_id: str) -> Mapping[str, str] | None:
        """O ambiente gravado na primeira execução do cohort, ou `None`."""
        ...
