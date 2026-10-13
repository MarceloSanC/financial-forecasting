"""Fake in-memory do port `CheckpointResolver` do `inference` (Stage 7.1).

Devolve o `ResolveTftCheckpointsResult` configurado por seed, ou ergue a exceção
configurada (o real ergue `ApplicationError` nas guardas C1/C2/C3/C14). Seed sem
resultado configurado ergue `ApplicationError` — nunca inventa um checkpoint.
Registra as seeds pedidas em `calls`. Não carrega nada (como o real). Paridade
com o `ResolveTftCheckpoints` pelo contrato `[fake, real]`.
"""

from __future__ import annotations

from collections.abc import Mapping

from financial_forecasting.features.modeling.application.use_cases.resolve_tft_checkpoints import (
    ResolveTftCheckpointsCommand,
    ResolveTftCheckpointsResult,
)
from financial_forecasting.shared.application.exceptions import ApplicationError


class InMemoryCheckpointResolver:
    """Resoluções configuradas por seed (ou uma exceção para toda chamada)."""

    def __init__(
        self,
        results: Mapping[int, ResolveTftCheckpointsResult] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._results = dict(results or {})
        self._error = error
        self.calls: list[int] = []

    def __call__(self, command: ResolveTftCheckpointsCommand) -> ResolveTftCheckpointsResult:
        self.calls.append(command.seed)
        if self._error is not None:
            raise self._error
        if command.seed not in self._results:
            raise ApplicationError(f"no checkpoints resolved for seed {command.seed}")
        return self._results[command.seed]
