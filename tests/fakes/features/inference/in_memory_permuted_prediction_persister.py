"""Fake in-memory do port `PermutedPredictionPersister` do `inference` (Stage 7.3).

Não guarda linhas: registra cada comando em `commands` e as chaves que seriam gravadas
em `keys` — `(run_id, família, k, decisão, horizonte, nível)` — para os pares resolvíveis
(o alvo `decisão + h` dentro da grade do dataset; senão conta em `rows_skipped`, como o
real). Como o real, `permuted_family == "none"` fora do índice 0 (ou o contrário), ou
índice negativo, ergue `ValueError` antes de registrar qualquer coisa.
"""

from __future__ import annotations

from financial_forecasting.features.analytics_store.application.use_cases.persist_permuted_predictions import (  # noqa: E501
    PersistPermutedPredictionsCommand,
    PersistPermutedPredictionsResult,
)

Key = tuple[str, str, int, int, int, float]


class InMemoryPermutedPredictionPersister:
    """Conta e registra as chaves das linhas de atribuição de cada run."""

    def __init__(self) -> None:
        self.commands: list[PersistPermutedPredictionsCommand] = []
        self.keys: list[Key] = []

    def __call__(
        self, command: PersistPermutedPredictionsCommand
    ) -> PersistPermutedPredictionsResult:
        for entry in command.entries:
            index = entry.permutation_index
            if isinstance(index, bool) or index < 0:
                raise ValueError(f"permutation_index must be an int >= 0, got {index!r}")
            if (entry.permuted_family == "none") != (index == 0):
                raise ValueError(
                    f"permuted_family {entry.permuted_family!r} with index {index}: the "
                    "identity pass is 'none' with permutation_index 0"
                )
        self.commands.append(command)
        last = len(command.dataset_timestamps) - 1
        written, skipped = 0, 0
        for entry in command.entries:
            for horizon, forecast in entry.forecasts.items():
                levels = tuple(forecast.levels)
                if entry.decision_idx + horizon > last:
                    skipped += len(levels)
                    continue
                for level in levels:
                    self.keys.append(
                        (
                            command.run_id,
                            entry.permuted_family,
                            entry.permutation_index,
                            entry.decision_idx,
                            horizon,
                            level,
                        )
                    )
                    written += 1
        return PersistPermutedPredictionsResult(rows_written=written, rows_skipped=skipped)
