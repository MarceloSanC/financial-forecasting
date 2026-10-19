"""VO `VsnRunWeights` e `reduce_vsn_run` — os pesos da VSN de UM run do candidato (7.3).

Value object de domínio frozen, stdlib-only (concept 7.3 §4; I19). O `RefreshGold` lê um
run por vez de `fact_vsn_weights`, agrupa as linhas por decisão (`reduce_vsn_run`) e
descarta os registros antes do próximo run. Invariantes: decisões não vazias, cada uma
com o MESMO conjunto não vazio de variáveis (a tabela tem decisões x variáveis linhas) e
pesos finitos em [0, 1].
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from financial_forecasting.features.evaluation.domain.value_objects._integer import (
    validate_int_at_least,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    check_non_empty_str,
)
from financial_forecasting.features.evaluation.domain.value_objects.vsn_weight_record import (
    VsnWeightRecord,
)


@dataclass(frozen=True, kw_only=True)
class VsnRunWeights:
    """Os pesos da VSN de um run: decisão (timestamp) → variável → peso."""

    run_id: str
    seed: int
    fold_index: int
    weights: Mapping[str, Mapping[str, float]]

    def __post_init__(self) -> None:
        """Decisões não vazias, o mesmo conjunto de variáveis em todas e pesos em [0, 1]."""
        check_non_empty_str(self.run_id, field="run_id")
        for field in ("seed", "fold_index"):
            validate_int_at_least(getattr(self, field), minimum=0, field=field)
        if not isinstance(self.weights, Mapping) or not self.weights:
            raise ValueError(f"weights must be a non-empty mapping, got {self.weights!r}")
        variables: frozenset[str] | None = None
        canonical: dict[str, MappingProxyType[str, float]] = {}
        for decision in self.weights:
            check_non_empty_str(decision, field="weights decision")
            row = self.weights[decision]
            if not isinstance(row, Mapping) or not row:
                raise ValueError(f"weights[{decision}] must be a non-empty mapping, got {row!r}")
            names = frozenset(row)
            if variables is None:
                variables = names
            elif names != variables:
                raise ValueError(
                    f"weights[{decision}] has variables {sorted(names)}, the other decisions "
                    f"have {sorted(variables)}"
                )
            for variable, weight in row.items():
                check_non_empty_str(variable, field=f"weights[{decision}] variable")
                if not isinstance(weight, float) or not math.isfinite(weight):
                    raise ValueError(f"weights[{decision}][{variable}] must be a finite float")
                if not 0 <= weight <= 1:
                    raise ValueError(f"weights[{decision}][{variable}] must be in [0, 1]")
            canonical[decision] = MappingProxyType({v: row[v] for v in sorted(row)})
        ordered = {decision: canonical[decision] for decision in sorted(canonical)}
        object.__setattr__(self, "weights", MappingProxyType(ordered))

    def __hash__(self) -> int:
        """Hash pela identidade do run (os mapeamentos não são hasháveis)."""
        return hash((self.run_id, self.seed, self.fold_index, tuple(self.weights)))


def reduce_vsn_run(records: Sequence[VsnWeightRecord]) -> VsnRunWeights:
    """Agrupa as linhas de UM run por decisão.

    Raises:
        ValueError: nenhuma linha, linhas de runs (ou seeds, folds) diferentes, ou a mesma
            variável duas vezes numa decisão.
    """
    if not records:
        raise ValueError("reduce_vsn_run needs at least one record")
    first = records[0]
    identity = (first.run_id, first.seed, first.fold_index)
    weights: dict[str, dict[str, float]] = {}
    for record in records:
        if (record.run_id, record.seed, record.fold_index) != identity:
            raise ValueError(
                f"reduce_vsn_run takes one run: {identity} and "
                f"{(record.run_id, record.seed, record.fold_index)}"
            )
        row = weights.setdefault(record.decision_timestamp, {})
        if record.variable in row:
            raise ValueError(
                f"run {first.run_id}: variable {record.variable!r} twice at decision "
                f"{record.decision_timestamp}"
            )
        row[record.variable] = record.weight
    return VsnRunWeights(
        run_id=first.run_id, seed=first.seed, fold_index=first.fold_index, weights=weights
    )
