"""Fake in-memory do port `CohortProgressLedger` (Stage 5.5).

Mesmo comportamento observável do adapter JSON (o contrato `[fake, real]` prova a
paridade), sem disco. `owner` identifica o dono do lock na mensagem de erro.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from financial_forecasting.features.modeling.application.ports.out.cohort_progress_ledger import (
    CohortRunLockedError,
)


class InMemoryCohortProgressLedger:
    """Ledger em memória: lock, unidades, ambiente, início e resultados de sweep."""

    def __init__(self, *, owner: str = "pid=1 host=fake") -> None:
        self._owner = owner
        self._locked = False
        self._units: dict[str, dict[str, dict[str, int]]] = {}
        self._environment: dict[str, dict[str, str]] = {}
        self._started_at: dict[str, str] = {}
        self._sweeps: dict[str, dict[str, dict[str, object]]] = {}

    def acquire_writer(self, *, break_stale: bool = False) -> None:
        if self._locked and not break_stale:
            raise CohortRunLockedError(f"writer lock already held by {self._owner}")
        self._locked = True

    def release_writer(self) -> None:
        self._locked = False

    @property
    def is_locked(self) -> bool:
        """Só do fake: permite ao teste do use case conferir a liberação em erro."""
        return self._locked

    def completed_units(self, cohort_id: str) -> Mapping[str, Mapping[str, int]]:
        return {unit: dict(rows) for unit, rows in self._units.get(cohort_id, {}).items()}

    def mark_completed(
        self, cohort_id: str, unit_key: str, rows_by_run: Mapping[str, int]
    ) -> None:
        self._units.setdefault(cohort_id, {})[unit_key] = dict(rows_by_run)

    def environment(self, cohort_id: str) -> Mapping[str, str] | None:
        env = self._environment.get(cohort_id)
        return dict(env) if env is not None else None

    def record_environment(
        self, cohort_id: str, env: Mapping[str, str], *, started_at: str
    ) -> None:
        self._environment[cohort_id] = dict(env)
        self._started_at.setdefault(cohort_id, started_at)

    def run_started_at(self, cohort_id: str) -> str | None:
        return self._started_at.get(cohort_id)

    def record_sweep_result(
        self, scope_id: str, model: str, result: Mapping[str, object]
    ) -> None:
        # Mesma ida e volta JSON do adapter real (tuplas viram listas; chaves, texto).
        self._sweeps.setdefault(scope_id, {})[model] = json.loads(json.dumps(dict(result)))

    def sweep_results(self, scope_id: str) -> Mapping[str, Mapping[str, object]]:
        return {model: dict(result) for model, result in self._sweeps.get(scope_id, {}).items()}
