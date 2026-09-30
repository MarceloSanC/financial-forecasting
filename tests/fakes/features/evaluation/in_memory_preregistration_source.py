"""Fake do port `PreregistrationSource` — revisões em memória (Stage 6.5).

`add(name, revision, payload, anchor=None)` registra uma revisão; `read` devolve uma
cópia profunda do payload (o chamador não altera o registrado) e a âncora; revisão
ausente ergue o mesmo `PreregistrationNotFoundError` do real. `reads` conta as
chamadas `(name, revision)` (testes de ordem do use case).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping

from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    PreregistrationAnchor,
    PreregistrationNotFoundError,
    PreregistrationRecord,
)


class InMemoryPreregistrationSource:
    """Satisfaz `PreregistrationSource` com um dicionário `(name, revision)`."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, int], PreregistrationRecord] = {}
        self.reads: list[tuple[str, int]] = []

    def add(
        self,
        name: str,
        revision: int,
        payload: Mapping[str, object],
        anchor: PreregistrationAnchor | None = None,
    ) -> None:
        """Registra (ou substitui) a revisão `revision` do plano `name`."""
        self._records[name, revision] = PreregistrationRecord(
            payload=copy.deepcopy(dict(payload)), anchor=anchor
        )

    def read(self, *, name: str, revision: int) -> PreregistrationRecord:
        """A revisão registrada, com o payload copiado."""
        self.reads.append((name, revision))
        record = self._records.get((name, revision))
        if record is None:
            raise PreregistrationNotFoundError(
                f"preregistration {name!r} revision {revision} not found"
            )
        return PreregistrationRecord(
            payload=copy.deepcopy(dict(record.payload)), anchor=record.anchor
        )
