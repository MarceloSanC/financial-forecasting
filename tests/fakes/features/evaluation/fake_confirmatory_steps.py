"""Fakes dos Protocols locais do `RunConfirmatoryEvaluation` (Stage 8.1 Task 13).

- `FakeGoldRefresh` — satisfaz `GoldRefresh`: publica no `InMemoryGoldStore` a próxima
  geração da fila (`generations`; a última se repete) e devolve o `RefreshGoldResult`
  com o manifesto publicado, como o `RefreshGold`; `error` ergue antes de publicar
  (falha no E1 com `current/` intacto); `calls` registra os comandos.
- `FakeScorecardBuilder` — satisfaz `ScorecardBuilder`: delega ao scorecard real
  (`delegate`, montado pelo teste sobre os fakes) e pode trocar o `manifest_read`
  (`manifest_read`, A6b) ou erguer (`error`, ex. `GoldGenerationCorruptError`);
  `calls` registra os comandos.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    BuildConfirmatoryScorecardCommand,
    ScorecardResult,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    FailedCheck,
    GoldGeneration,
    GoldManifest,
    RefreshGoldCommand,
    RefreshGoldResult,
)
from tests.fakes.features.evaluation.in_memory_gold_store import InMemoryGoldStore


class FakeGoldRefresh:
    """Publica gerações prontas no `InMemoryGoldStore`, uma por chamada."""

    def __init__(
        self,
        store: InMemoryGoldStore,
        generations: Sequence[GoldGeneration],
        *,
        failed_checks: tuple[FailedCheck, ...] = (),
        error: Exception | None = None,
    ) -> None:
        if not generations:
            raise ValueError("FakeGoldRefresh needs at least one generation")
        self._store = store
        self.generations = list(generations)
        self.failed_checks = failed_checks
        self.error = error
        self.calls: list[RefreshGoldCommand] = []

    def __call__(self, command: RefreshGoldCommand) -> RefreshGoldResult:
        self.calls.append(command)
        if self.error is not None:
            raise self.error
        index = min(len(self.calls), len(self.generations)) - 1
        generation = self.generations[index]
        manifest = generation.manifest
        self._store.publish(
            partition=manifest.partition, tables=list(generation.tables.values()), manifest=manifest
        )
        return RefreshGoldResult(
            status=manifest.status,
            rows_by_table=dict(manifest.rows_by_table),
            failed_checks=self.failed_checks,
            profile_error_units=0,
            conformal_error_units=0,
            manifest=manifest,
        )


class FakeScorecardBuilder:
    """Delega ao scorecard real; troca o `manifest_read` ou ergue quando pedido."""

    def __init__(
        self,
        delegate: Callable[[BuildConfirmatoryScorecardCommand], ScorecardResult],
        *,
        manifest_read: GoldManifest | None = None,
        error: Exception | None = None,
    ) -> None:
        self._delegate = delegate
        self.manifest_read = manifest_read
        self.error = error
        self.calls: list[BuildConfirmatoryScorecardCommand] = []

    def __call__(self, command: BuildConfirmatoryScorecardCommand) -> ScorecardResult:
        self.calls.append(command)
        if self.error is not None:
            raise self.error
        result = self._delegate(command)
        if self.manifest_read is not None:
            result = dataclasses.replace(result, manifest_read=self.manifest_read)
        return result
