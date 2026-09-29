"""`QualityChecksGoldBuilder` — satisfaz o port `GoldBuilder` (tabela `gold_quality_checks`).

Uma linha por `QualityCheckResult` (ADR 6.4.0002 item 2), no grão (check, kind,
horizon, model, seed). Roda também com o refresh `BLOCKED` (`runs_when_blocked`) e
**não** carrega `preregistration_ref` (não é tabela confirmatória — ADR 6.4.0006
item 4).
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)

_KEY = ("check", "kind", "horizon", "model", "seed")


class QualityChecksGoldBuilder:
    """Resultados dos quality checks, publicados mesmo com o refresh bloqueado."""

    name = QUALITY_CHECKS
    depends_on: frozenset[str] = frozenset()
    runs_when_blocked = True

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha por resultado de check."""
        base = partition_columns(inputs, confirmatory=False)
        rows = [
            {
                **base,
                "check": result.check,
                "kind": result.kind,
                "horizon": result.horizon,
                "model": result.model,
                "seed": result.seed,
                "severity": result.severity.value,
                "outcome": result.outcome.value,
                "occurrences": result.occurrences,
                "value": result.value,
                "detail": result.detail,
            }
            for result in inputs.check_results
        ]
        return GoldTable.sorted_by_key(f"gold_{self.name}", _KEY, rows)
