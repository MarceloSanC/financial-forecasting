"""Fake in-memory do port `CheckpointGridPredictor` do `inference` (Stage 7.1).

Configurado com o `PredictTftFromCheckpointsResult` completo de cada seed (todas as
partições); a chamada devolve só as partições pedidas. Como o real: um `run_id`
fora de `allowed` ergue `ApplicationError` antes de "carregar" qualquer run (C6), e
um sha256 esperado diferente do configurado também (C10). Registra os comandos em
`calls` (os testes provam "sem chamar o predictor"). Paridade com o
`PredictTftFromCheckpoints` pelo contrato `[fake, real]`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from financial_forecasting.features.modeling.application.use_cases.predict_tft_from_checkpoints import (  # noqa: E501
    PredictTftFromCheckpointsCommand,
    PredictTftFromCheckpointsResult,
)
from financial_forecasting.shared.application.exceptions import ApplicationError


class InMemoryCheckpointGridPredictor:
    """Grades configuradas por seed, recortadas pelas partições pedidas."""

    def __init__(
        self, results: Mapping[int, PredictTftFromCheckpointsResult] | None = None
    ) -> None:
        self._results = dict(results or {})
        self.calls: list[PredictTftFromCheckpointsCommand] = []

    def set_result(self, seed: int, result: PredictTftFromCheckpointsResult) -> None:
        """Configura (ou troca) o resultado completo de uma seed."""
        self._results[seed] = result

    def __call__(
        self, command: PredictTftFromCheckpointsCommand
    ) -> PredictTftFromCheckpointsResult:
        self.calls.append(command)
        if command.seed not in self._results:
            raise ApplicationError(f"no checkpoint grids configured for seed {command.seed}")
        result = self._results[command.seed]
        unknown = [run.run_id for run in result.runs if run.run_id not in command.allowed]
        if unknown:
            raise ApplicationError(f"runs {unknown} are not in the allowed list (C6)")
        changed = [
            run.run_id
            for run in result.runs
            if command.allowed[run.run_id] != run.checkpoint_sha256
        ]
        if changed:
            raise ApplicationError(f"runs {changed}: sha256 differs from the expected one (C10)")
        runs = tuple(
            replace(run, grids={p: run.grids[p] for p in command.partitions if p in run.grids})
            for run in result.runs
        )
        return replace(result, runs=runs)
