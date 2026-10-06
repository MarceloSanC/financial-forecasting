"""`DifferentialAcfGoldBuilder` — `GoldBuilder` da tabela `gold_differential_acf`.

Uma linha por lag (1..L) da ACF amostral de d_t de cada par calculado do diagnóstico de
estacionariedade (Stage 6.6; ADR 6.6.0001). Par `undefined` (d_t constante) ou `error` não
tem ACF — está na `gold_differential_breaks` com o motivo. Sem regras → nenhuma linha.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_DIFFERENTIAL_ACF,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)


class DifferentialAcfGoldBuilder:
    """ACF de d_t por par e lag."""

    name = "differential_acf"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha por lag de cada par calculado."""
        base = partition_columns(inputs, confirmatory=True)
        rows = [
            {
                **base,
                "horizon": report.horizon,
                "model_a": report.pair[0],
                "model_b": report.pair[1],
                "lag": lag,
                "acf": value,
                "n_points": report.n_points,
                "max_lag": report.max_lag,
            }
            for profile in inputs.profile_reports
            for row in profile.stationarity or ()
            if (report := row.report) is not None
            for lag, value in enumerate(report.acf, start=1)
        ]
        return GoldTable.sorted_by_key(GOLD_DIFFERENTIAL_ACF.name, GOLD_DIFFERENTIAL_ACF.key, rows)
