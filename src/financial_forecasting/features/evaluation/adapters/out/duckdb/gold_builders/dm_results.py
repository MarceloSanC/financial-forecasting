"""`DmResultsGoldBuilder` — satisfaz o port `GoldBuilder` (tabela `gold_dm_results`).

Uma linha por `HolmComparison` de cada `DmHolmFamilyReport` (um por estimador de
variância e horizonte): o `DieboldMarianoResult` do par candidato x comparador, o p
ajustado de Holm, a decisão e o alfa da família, com a janela da amostra comum.
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

_KEY = ("horizon", "variance_estimator", "candidate", "comparator")


class DmResultsGoldBuilder:
    """DM + Holm do candidato contra cada comparador, por horizonte e estimador."""

    name = "dm_results"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha por comparação de cada família."""
        base = partition_columns(inputs, confirmatory=True)
        rows = [
            {
                **base,
                "horizon": family.horizon,
                "variance_estimator": family.variance_estimator.value,
                "candidate": family.candidate,
                "comparator": comparison.comparator,
                "n_points": comparison.dm.n_points,
                "common_first_target_timestamp": report.common_first_target_timestamp,
                "common_last_target_timestamp": report.common_last_target_timestamp,
                "mean_differential": comparison.dm.mean_differential,
                "long_run_variance": comparison.dm.long_run_variance,
                "statistic": comparison.dm.statistic,
                "degrees_of_freedom": comparison.dm.degrees_of_freedom,
                "p_value": comparison.dm.p_value,
                "horizon_used": comparison.dm.horizon_used,
                "fallback_applied": comparison.dm.fallback_applied,
                "adjusted_p_value": comparison.adjusted_p_value,
                "rejected": comparison.rejected,
                "alpha": family.alpha,
            }
            for report in inputs.horizon_reports
            for family in report.dm_families
            for comparison in family.comparisons
        ]
        return GoldTable.sorted_by_key(f"gold_{self.name}", _KEY, rows)
