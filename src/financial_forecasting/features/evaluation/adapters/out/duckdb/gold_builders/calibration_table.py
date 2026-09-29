"""`CalibrationTableGoldBuilder` — satisfaz o port `GoldBuilder` (`gold_calibration_table`).

Uma linha por (série, sequência de hits, nível de banda): cada `CalibrationRow` do
`HorizonReports` (Christoffersen + Kupiec de uma sequência — intervalo ou cauda, com ou
sem as linhas degeneradas, sub-série DGT em h > 1) vezes cada `WilsonBandReport`. Todo
número sai do `ChristoffersenReport` (e das suas `statistics`) e do `WilsonBandReport`;
`var_label` é o `VAR_DESCRIPTIVE_LABEL` nas caudas (onde há `var_level`).
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
from financial_forecasting.features.evaluation.domain.services.horizon_reports import (
    CalibrationRow,
    SeriesReports,
)
from financial_forecasting.features.evaluation.domain.services.var_descriptive import (
    VAR_DESCRIPTIVE_LABEL,
)
from financial_forecasting.features.evaluation.domain.services.wilson_band import (
    WilsonBandReport,
)

_KEY = (
    "model",
    "seed",
    "horizon",
    "sample",
    "kind",
    "level_low",
    "level_high",
    "includes_degenerate",
    "dgt_offset",
    "dgt_step",
    "band_level",
)
_INTERVAL_LEVELS = 2


def _row(series: SeriesReports, row: CalibrationRow, band: WilsonBandReport) -> dict[str, object]:
    report = row.christoffersen
    stats = report.statistics
    n00, n01, n10, n11 = stats.transitions
    return {
        "model": series.model,
        "seed": series.seed,
        "horizon": report.horizon,
        "sample": series.sample.value,
        "kind": report.kind.value,
        "level_low": report.levels[0],
        "level_high": report.levels[1] if len(report.levels) == _INTERVAL_LEVELS else None,
        "includes_degenerate": report.includes_degenerate,
        "dgt_offset": report.dgt_offset,
        "dgt_step": report.dgt_step,
        "band_level": band.band_level,
        "n_points": series.n_points,
        "first_target_timestamp": series.first_target_timestamp,
        "last_target_timestamp": series.last_target_timestamp,
        "violation_rate": report.violation_rate,
        "tolerance": report.tolerance,
        "degeneracy_rate": report.degeneracy_rate,
        "min_violations": report.min_violations,
        "n_observed": stats.n_observed,
        "n_violations": stats.n_violations,
        "n00": n00,
        "n01": n01,
        "n10": n10,
        "n11": n11,
        "kupiec_pof": stats.kupiec_pof,
        "kupiec_pof_p_value": report.kupiec_pof_p_value,
        "lr_uc": stats.lr_uc,
        "p_uc": report.p_uc,
        "lr_ind": stats.lr_ind,
        "p_ind": report.p_ind,
        "lr_cc": stats.lr_cc,
        "p_cc": report.p_cc,
        "independence_status": stats.independence_status.value,
        "independence_descriptive": report.independence_descriptive,
        "wilson_applicable": band.applicable,
        "wilson_estimate": band.estimate,
        "wilson_lower": band.lower,
        "wilson_upper": band.upper,
        "wilson_contains_nominal": band.contains_nominal,
        "serial_dependence_warning": band.serial_dependence_warning,
        "var_level": row.var_level,
        "var_label": None if row.var_level is None else VAR_DESCRIPTIVE_LABEL,
    }


class CalibrationTableGoldBuilder:
    """Backtests de cobertura (Christoffersen, Kupiec) e bandas de Wilson por série."""

    name = "calibration_table"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha por (série, sequência, nível de banda)."""
        base = partition_columns(inputs, confirmatory=True)
        rows = [
            {**base, **_row(series, row, band)}
            for report in inputs.horizon_reports
            for series in report.series
            for row in series.calibration
            for band in row.wilson
        ]
        return GoldTable.sorted_by_key(f"gold_{self.name}", _KEY, rows)
