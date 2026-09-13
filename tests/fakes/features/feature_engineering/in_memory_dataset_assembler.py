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

**Geometria de missing (issues #72/#83):** `feature_rows` reproduz a forma que o
adapter real entrega ao gate — `None` (NaN normalizado) nas primeiras `warmup` linhas
de cada feature e finito (`0.0`) depois. Por default o warmup é o **nominal** do
registry; `effective_warmup={name: k}` sobrescreve por feature para modelar o caso
real em que o warmup EFETIVO excede o nominal (o débito que a #83 reconciliou:
`trend_regime` nominal 63 vs efetivo 112 — hoje acusado pela checagem absoluta (d) do
gate); `missing_rows={name: {i, j}}` emite `None` em índices INTERIORES (pós-drop),
modelando missing real pós-warmup — o que a checagem de NaN-ratio (a) mede. Antes da
#72 o fake emitia `0.0` em toda linha, e o ramo "gate reprova por NaN-ratio" era
inalcançável pelo caminho wireado.

Vive em `tests/` (fora do gate `import-linter`); importa SÓ stdlib + os DTOs do port
e o `FeatureRegistry` do domínio.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

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
    """Implementação in-memory determinística do contrato `DatasetAssemblerPort`.

    `effective_warmup`: nº de linhas iniciais emitidas como `None` por feature; ausente
    → warmup nominal do registry (geometria default do adapter real).
    `missing_rows`: índices (pós-drop) emitidos como `None` por feature, além do warmup
    — missing interior, o que a checagem de NaN-ratio do gate mede.
    """

    def __init__(
        self,
        *,
        effective_warmup: Mapping[str, int] | None = None,
        missing_rows: Mapping[str, Collection[int]] | None = None,
    ) -> None:
        self.persisted: list[str] = []
        self.last_inputs: DatasetAssemblyInputs | None = None
        self._effective_warmup: dict[str, int] = dict(effective_warmup or {})
        self._missing_rows: dict[str, frozenset[int]] = {
            name: frozenset(rows) for name, rows in (missing_rows or {}).items()
        }

    def assemble(self, inputs: DatasetAssemblyInputs) -> DatasetAssemblyResult:
        """Devolve contagens/ordem coerentes; modela o drop da 1ª linha do alvo."""
        self.last_inputs = inputs
        specs = list_feature_specs()
        feature_columns = tuple(spec.name for spec in specs)
        columns = (*_BASE_LEADING, *feature_columns, *_TAIL_COLUMNS)

        days = list(inputs.grid_days)
        if len(days) < 2:  # noqa: PLR2004 — precisa de >=2 dias para 1 alvo backward
            raise ValueError("not enough rows to compute target_return")
        retained = days[1:]  # drop da 1ª linha (alvo backward)
        n_rows = len(retained)
        # Forma do gate (#72/#83): `None` nas primeiras `warmup` linhas (nominal do
        # registry ou o efetivo injetado) e nos `missing_rows` interiores; `0.0` finito
        # no resto — o fake não calcula features.
        warmup_by_feature = {
            spec.name: self._effective_warmup.get(spec.name, spec.warmup_count) for spec in specs
        }
        feature_rows = tuple(
            {
                name: (
                    None
                    if index < warmup_by_feature[name]
                    or index in self._missing_rows.get(name, frozenset())
                    else 0.0
                )
                for name in feature_columns
            }
            for index in range(n_rows)
        )
        return DatasetAssemblyResult(
            n_rows=n_rows,
            columns=columns,
            feature_columns=feature_columns,
            start=retained[0],  # começa no 2º dia
            end=retained[-1],
            timestamps=tuple(retained),
            feature_rows=feature_rows,
        )

    def persist(self, asset: str) -> None:
        """Registra o asset persistido (sem I/O)."""
        self.persisted.append(asset)
