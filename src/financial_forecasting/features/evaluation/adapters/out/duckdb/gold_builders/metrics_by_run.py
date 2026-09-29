"""`MetricsByRunGoldBuilder` — satisfaz o port `GoldBuilder` (tabela `gold_metrics_by_run`).

Formato **longo** (technical 6.4 §1; concept §13): uma linha por (modelo, seed,
horizonte, amostra, métrica, nível baixo, nível alto), com `metric` em
`pinball_grid_mean`, `pinball` (por τ), `crps_q`, `interval_score` e `interval_width`
(por par), `coverage_rate` (ĉ por τ), `picp` e `mpiw` (por par), `degeneracy_rate`,
`guardrail_applied_rate` e `coverage_n_evaluated`. Todo número sai de um campo de
relatório (`PinballReport`, `CrpsReport`, `IntervalScoreReport` — a média do IS pelo
`PairIntervalScore.mean_score` —, `CoverageReport` e o `SeriesReports`); `label` traz o
rótulo descritivo onde o relatório tem (`CRPS_Q_LABEL`, `MPIW_LABEL`).
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
from financial_forecasting.features.evaluation.domain.services.coverage_metrics import (
    MPIW_LABEL,
)
from financial_forecasting.features.evaluation.domain.services.crps_score import CRPS_Q_LABEL
from financial_forecasting.features.evaluation.domain.services.horizon_reports import (
    SeriesReports,
)

_KEY = ("model", "seed", "horizon", "sample", "metric", "level_low", "level_high")

Metric = tuple[str, float | None, float | None, float, str | None]


def _metrics(series: SeriesReports) -> list[Metric]:
    metrics: list[Metric] = [("pinball_grid_mean", None, None, series.pinball.grid_mean, None)]
    metrics += [("pinball", level, None, value, None) for level, value in series.pinball.per_level]
    metrics.append(("crps_q", None, None, series.crps.crps_q, CRPS_Q_LABEL))
    for pair in series.interval.per_pair:
        low, high = pair.lower_level, pair.upper_level
        metrics.append(("interval_score", low, high, pair.mean_score, None))
        metrics.append(("interval_width", low, high, pair.mean_width, None))
    coverage = series.coverage
    metrics += [("coverage_rate", level, None, rate, None) for level, rate in coverage.per_level]
    for pair_coverage in coverage.per_pair:
        low, high = pair_coverage.lower_level, pair_coverage.upper_level
        metrics.append(("picp", low, high, pair_coverage.picp, None))
        metrics.append(("mpiw", low, high, pair_coverage.mpiw, MPIW_LABEL))
    metrics.append(("degeneracy_rate", None, None, coverage.degeneracy.rate, None))
    metrics.append(("guardrail_applied_rate", None, None, series.guardrail_applied_rate, None))
    metrics.append(("coverage_n_evaluated", None, None, float(coverage.n_evaluated), None))
    return metrics


class MetricsByRunGoldBuilder:
    """Métricas 6.1 por série (modelo, seed, horizonte, amostra), em formato longo."""

    name = "metrics_by_run"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha por métrica de cada série de cada horizonte."""
        base = partition_columns(inputs, confirmatory=True)
        tolerance = inputs.parameters.degeneracy_tolerance
        rows = [
            {
                **base,
                "model": series.model,
                "seed": series.seed,
                "horizon": report.horizon,
                "sample": series.sample.value,
                "metric": metric,
                "level_low": level_low,
                "level_high": level_high,
                "value": value,
                "label": label,
                "n_points": series.n_points,
                "first_target_timestamp": series.first_target_timestamp,
                "last_target_timestamp": series.last_target_timestamp,
                "degeneracy_tolerance": tolerance,
            }
            for report in inputs.horizon_reports
            for series in report.series
            for metric, level_low, level_high, value, label in _metrics(series)
        ]
        return GoldTable.sorted_by_key(f"gold_{self.name}", _KEY, rows)
