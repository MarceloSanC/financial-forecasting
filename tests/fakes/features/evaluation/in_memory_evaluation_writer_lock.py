"""Fake do port `EvaluationWriterLock` — lock em memória que registra e pode recusar (8.1).

`acquired` e `released` contam as chamadas efetivas; `events` guarda a ordem
(`"acquire"`/`"release"`) para os testes do use case (lock antes de qualquer efeito e
liberado no fim, também na falha). O lock já detido — por esta instância ou por um dono
simulado (`hold_by_other()`) — ergue `ApplicationError`, como o
`CohortRunLockedError` do real; `break_stale=True` o toma. `refuse=True` recusa sempre.
"""

from __future__ import annotations

from financial_forecasting.shared.application.exceptions import ApplicationError


class InMemoryEvaluationWriterLock:
    """Satisfaz `EvaluationWriterLock` em memória."""

    def __init__(self, *, refuse: bool = False) -> None:
        self._refuse = refuse
        self._held_by_me = False
        self._held_by_other = False
        self.acquired = 0
        self.released = 0
        self.events: list[str] = []

    @property
    def held(self) -> bool:
        return self._held_by_me or self._held_by_other

    def hold_by_other(self) -> None:
        """Simula um lock deixado por outro processo (órfão ou vivo)."""
        self._held_by_other = True

    def acquire_writer(self, *, break_stale: bool = False) -> None:
        if self._refuse:
            raise ApplicationError("the data_root writer lock is held by another run")
        if break_stale:
            self._held_by_other = False
            self._held_by_me = False
        if self.held:
            raise ApplicationError("the data_root writer lock is already held")
        self._held_by_me = True
        self.acquired += 1
        self.events.append("acquire")

    def release_writer(self) -> None:
        if not self._held_by_me:
            return
        self._held_by_me = False
        self.released += 1
        self.events.append("release")
