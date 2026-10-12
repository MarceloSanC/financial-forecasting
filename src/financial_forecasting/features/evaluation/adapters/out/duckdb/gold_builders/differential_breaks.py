"""`DifferentialBreaksGoldBuilder` — `GoldBuilder` da tabela `gold_differential_breaks`.

Uma linha por par de modelos de cada horizonte com regras de perfil (Stage 6.6; ADR
6.6.0001): o CUSUM da média de d_t (estatística, p-valor de Kolmogorov, rejeição à alpha
do plano, h usado pela variância, alvo da quebra) ou, sem valor, o motivo
(`constant_differential`) ou o `error` da chamada com a mensagem.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_DIFFERENTIAL_BREAKS,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)

_ERROR = "error"


class DifferentialBreaksGoldBuilder:
    """Teste de quebra (CUSUM) de d_t por par."""

    name = "differential_breaks"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha por par de cada horizonte com regras de perfil."""
        base = partition_columns(inputs, confirmatory=True)
        rules = inputs.parameters.profile_parameters
        alpha = None if rules is None else rules.stationarity.break_alpha
        rows = []
        for profile in inputs.profile_reports:
            for row in profile.stationarity or ():
                report = row.report
                rows.append(
                    {
                        **base,
                        "horizon": profile.horizon,
                        "model_a": row.pair[0],
                        "model_b": row.pair[1],
                        "status": row.status.value if report is None else report.status.value,
                        "undefined_reason": _ERROR if report is None else report.undefined_reason,
                        "detail": row.detail,
                        "statistic": None if report is None else report.statistic,
                        "p_value": None if report is None else report.p_value,
                        "rejected": None if report is None else report.rejected,
                        "alpha": alpha if report is None else report.alpha,
                        "horizon_used": None if report is None else report.horizon_used,
                        "break_target_timestamp": (
                            None if report is None else report.break_target_timestamp
                        ),
                        "n_points": None if report is None else report.n_points,
                        "max_lag": None if report is None else report.max_lag,
                    }
                )
        return GoldTable.sorted_by_key(
            GOLD_DIFFERENTIAL_BREAKS.name, GOLD_DIFFERENTIAL_BREAKS.key, rows
        )
