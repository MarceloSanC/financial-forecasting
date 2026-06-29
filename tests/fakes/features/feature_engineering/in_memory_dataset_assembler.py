"""Fake in-memory do port `DatasetAssemblerPort` — NÃO um mock (concept 3.5 A2).

`InMemoryDatasetAssembler` é um fake COMPORTAMENTAL determinístico (stdlib-only) que
satisfaz o `Protocol` `DatasetAssemblerPort` por duck-typing, com a MESMA forma
observável do adapter real (`DatasetAssembler`): `assemble` devolve um
`DatasetAssemblyResult` com `n_rows`/`columns`/`feature_columns`/`start`/`end`
coerentes, e `persist` registra o asset persistido. Torna o use case `BuildDataset`
(Task 05) testável SEM pandas.

Modela a convenção do alvo (drop da 1ª linha) e a ordem de colunas do registry
(I7), de modo que o use case receba `n_rows = len(grid_days) - 1` e
`feature_columns` na ordem do `FeatureRegistry`. Não calcula features (isso é do
adapter real, validado pelo contract test); produz comportamento estável.

Vive em `tests/` (fora do gate `import-linter`); importa SÓ stdlib + os DTOs do port
e o `FeatureRegistry` do domínio.
"""

from __future__ import annotations

from financial_forecasting.features.feature_engineering.application.ports.out.dataset_assembler import (  # noqa: E501
    DatasetAssemblyInputs,
    DatasetAssemblyResult,
)
from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    list_feature_specs,
)

_BASE_LEADING = ("timestamp", "asset_id")
_TAIL_COLUMNS = (
    "fundamentals_effective_date",
    "day_of_week",
    "month",
    "target_return",
    "time_idx",
)


class InMemoryDatasetAssembler:
    """Implementação in-memory determinística do contrato `DatasetAssemblerPort`."""

    def __init__(self) -> None:
        self.persisted: list[str] = []
        self.last_inputs: DatasetAssemblyInputs | None = None

    def assemble(self, inputs: DatasetAssemblyInputs) -> DatasetAssemblyResult:
        """Devolve contagens/ordem coerentes; modela o drop da 1ª linha do alvo."""
        self.last_inputs = inputs
        feature_columns = tuple(spec.name for spec in list_feature_specs())
        columns = (*_BASE_LEADING, *feature_columns, *_TAIL_COLUMNS)

        days = list(inputs.grid_days)
        if len(days) < 2:  # noqa: PLR2004 — precisa de >=2 dias para 1 alvo backward
            raise ValueError("not enough rows to compute target_return")
        n_rows = len(days) - 1  # drop da 1ª linha (alvo backward)
        return DatasetAssemblyResult(
            n_rows=n_rows,
            columns=columns,
            feature_columns=feature_columns,
            start=days[1],  # 1ª linha cai → começa no 2º dia
            end=days[-1],
        )

    def persist(self, asset: str) -> None:
        """Registra o asset persistido (sem I/O)."""
        self.persisted.append(asset)
