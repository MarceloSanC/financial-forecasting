"""Fake in-memory do port `VsnWeightPersister` do `inference` (Stage 7.3).

Não guarda linhas: registra cada comando em `commands` e as chaves que seriam gravadas
em `keys` — `(run_id, decisão, variável, família)`. Como o real, variável sem família
declarada no comando ergue `ValueError` antes de registrar.
"""

from __future__ import annotations

from financial_forecasting.features.analytics_store.application.use_cases.persist_vsn_weights import (  # noqa: E501
    PersistVsnWeightsCommand,
    PersistVsnWeightsResult,
)

Key = tuple[str, int, str, str]


class InMemoryVsnWeightPersister:
    """Conta e registra as chaves dos pesos da VSN de cada run."""

    def __init__(self) -> None:
        self.commands: list[PersistVsnWeightsCommand] = []
        self.keys: list[Key] = []

    def __call__(self, command: PersistVsnWeightsCommand) -> PersistVsnWeightsResult:
        missing = sorted(
            {v for entry in command.decisions for v in entry.weights}
            - set(command.variable_families)
        )
        if missing:
            raise ValueError(f"variables {missing} have no declared family")
        self.commands.append(command)
        before = len(self.keys)
        for entry in command.decisions:
            self.keys.extend(
                (command.run_id, entry.decision_idx, variable, command.variable_families[variable])
                for variable in entry.weights
            )
        return PersistVsnWeightsResult(rows_written=len(self.keys) - before)
