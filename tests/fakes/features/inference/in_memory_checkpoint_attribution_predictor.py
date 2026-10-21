"""Fake in-memory do port `CheckpointAttributionPredictor` do `inference` (Stage 7.3).

Configurado com o `PredictTftAttributionResult` completo de cada seed (gravado do real
sobre o mesmo cohort) e com a partição de referência (`registry_partition`). Como o
real, antes de devolver qualquer coisa: partição do comando diferente da de referência
ergue `ApplicationError`; um fold sem doadores, ou doadores que não são permutações das
decisões de teste do run, ergue `ValueError`; `run_id` fora de `allowed` e sha256
diferente do configurado erguem `ApplicationError`. Registra os comandos em `calls`.
Paridade com o `PredictTftAttributionFromCheckpoints` pelo contrato `[fake, real]`.
"""

from __future__ import annotations

from collections.abc import Mapping

from financial_forecasting.features.modeling.application.ports.out.tft_checkpoint_predictor import (
    check_donors,
)
from financial_forecasting.features.modeling.application.use_cases.predict_tft_attribution_from_checkpoints import (  # noqa: E501
    PredictTftAttributionCommand,
    PredictTftAttributionResult,
)
from financial_forecasting.shared.application.exceptions import ApplicationError


class InMemoryCheckpointAttributionPredictor:
    """Resultados de atribuição configurados por seed."""

    def __init__(
        self,
        *,
        registry_partition: Mapping[str, tuple[str, ...]],
        results: Mapping[int, PredictTftAttributionResult] | None = None,
    ) -> None:
        self._registry_partition = {f: tuple(v) for f, v in registry_partition.items()}
        self._results = dict(results or {})
        self.calls: list[PredictTftAttributionCommand] = []

    def set_result(self, seed: int, result: PredictTftAttributionResult) -> None:
        """Configura (ou troca) o resultado completo de uma seed."""
        self._results[seed] = result

    def __call__(self, command: PredictTftAttributionCommand) -> PredictTftAttributionResult:
        self.calls.append(command)
        partition = {f: tuple(v) for f, v in command.family_partition.items()}
        if partition != self._registry_partition:
            raise ApplicationError("the command's family partition differs from the registry's")
        if command.seed not in self._results:
            raise ApplicationError(f"no attribution configured for seed {command.seed}")
        result = self._results[command.seed]
        for run in result.runs:
            donors = command.donors_by_fold.get(run.fold_index)
            if donors is None:
                raise ValueError(f"no donors for fold {run.fold_index} (C1)")
            check_donors(donors, n_decisions=len(run.test_decisions))
        unknown = [run.run_id for run in result.runs if run.run_id not in command.allowed]
        if unknown:
            raise ApplicationError(f"runs {unknown} are not in the allowed list (C6)")
        changed = [
            run.run_id
            for run in result.runs
            if command.allowed[run.run_id] != run.checkpoint_sha256
        ]
        if changed:
            raise ApplicationError(f"runs {changed}: sha256 differs from the expected one (C7)")
        return result
