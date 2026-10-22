"""Fake do port `PreregistrationSource` — revisões em memória (Stage 6.5).

`add(name, revision, payload, anchor=None)` registra uma revisão; `read` devolve uma
cópia profunda do payload (o chamador não altera o registrado) e a âncora; revisão
ausente ergue o mesmo `PreregistrationNotFoundError` do real. `reads` conta as
chamadas `(name, revision)` (testes de ordem do use case).

Stage 8.1: `add_judged(name, record)` registra um `.judged.toml`; `judged_records`
devolve os do plano ordenados pela revisão (sem registro → tupla vazia).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping

from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    JudgedRecord,
    PreregistrationAnchor,
    PreregistrationNotFoundError,
    PreregistrationRecord,
)


class InMemoryPreregistrationSource:
    """Satisfaz `PreregistrationSource` com um dicionário `(name, revision)`."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, int], PreregistrationRecord] = {}
        self.reads: list[tuple[str, int]] = []
        self._judged: dict[tuple[str, int], JudgedRecord] = {}

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

    def add_judged(self, name: str, record: JudgedRecord) -> None:
        """Registra (ou substitui) o `.judged.toml` da revisão `record.revision` de `name`."""
        self._judged[name, record.revision] = record

    def judged_records(self, *, name: str) -> tuple[JudgedRecord, ...]:
        """Os registros de `name`, ordenados pela revisão."""
        return tuple(
            record
            for (owner, _), record in sorted(self._judged.items(), key=lambda item: item[0][1])
            if owner == name
        )
