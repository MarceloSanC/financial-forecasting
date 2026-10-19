"""`ConformalCorrectionsGoldBuilder` — satisfaz o port `GoldBuilder` (`gold_conformal_corrections`).

Uma linha por (fold, seed, horizonte, par, variante, cauda) dos `ConformalUnitRecord`s já
mapeados no `GoldInputs.conformal_reports` (ADR 7.2.0003 item 7; technical 7.2 §1):

- `fold_raw` é o fold cru (nunca nulo, então dois folds não inteiros não colidem) e
  `fold` o inteiro ou nulo;
- correção +inf vai como `correction = null` com `infinite = true` (o `GoldTable`
  recusa float não finito); o leitor reconstrói +inf por `infinite`;
- unidade não-`ok` (da montagem ou do port): as duas linhas com medidas e `infinite`
  nulos, `status` e `reason`.

Mapeamento puro; sem bloco `[conformal]` (ou em BLOCKED, onde nem roda) → zero linhas.
"""

from __future__ import annotations

import math

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CONFORMAL_CORRECTIONS,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)


class ConformalCorrectionsGoldBuilder:
    """Correções conformais por cauda, com posto, flag de infinito e referência Beta."""

    name = "conformal_corrections"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Duas linhas (caudas) por registro de unidade conformal."""
        base = partition_columns(inputs, confirmatory=True)
        rows = []
        for unit in inputs.conformal_reports.units:
            for tail in unit.tails:
                infinite = tail.correction is not None and math.isinf(tail.correction)
                rows.append(
                    {
                        **base,
                        "fold_raw": unit.fold_raw,
                        "fold": unit.fold_index,
                        "seed": unit.seed,
                        "horizon": unit.horizon,
                        "lower_level": unit.lower_level,
                        "upper_level": unit.upper_level,
                        "variant": unit.variant,
                        "tail": tail.tail,
                        "tail_level": tail.level,
                        "rho": unit.rho,
                        "status": unit.status,
                        "reason": unit.reason,
                        "n": tail.n,
                        "rank": tail.rank,
                        "correction": None if infinite else tail.correction,
                        "infinite": tail.infinite,
                        "beta_a": tail.beta_a,
                        "beta_b": tail.beta_b,
                        "beta_mean": tail.beta_mean,
                        "beta_sd": tail.beta_sd,
                    }
                )
        return GoldTable.sorted_by_key(
            GOLD_CONFORMAL_CORRECTIONS.name, GOLD_CONFORMAL_CORRECTIONS.key, rows
        )
