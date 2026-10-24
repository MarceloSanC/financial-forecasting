"""Colunas lidas pelas figuras no schema do gold (Stage 8.3, Task 03; D3).

As figuras leem as tabelas da cópia julgada por nome, pelo `GoldTableSchema` (nenhuma
coluna é lida por nome fora dele). A 8.3 acrescenta, no fim das tuplas (ordem estável),
o que o reliability diagram, o nativo vs. conformal e o heatmap do DM leem; o conformal
fica intocado — o `_empty_row` do builder de cobertura e o literal do teste das
correções dependem das tuplas atuais.
"""

from __future__ import annotations

import pytest

from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CALIBRATION_TABLE,
    GOLD_CONFORMAL_CORRECTIONS,
    GOLD_CONFORMAL_COVERAGE,
    GOLD_DM_RESULTS,
)


@pytest.mark.unit
def test_calibration_reads_violation_rate_and_wilson_columns() -> None:
    assert GOLD_CALIBRATION_TABLE.read_columns == (
        "n_observed",
        "n_violations",
        "degeneracy_rate",
        "wilson_contains_nominal",
        "p_ind",
        "p_cc",
        "independence_status",
        "violation_rate",
        "wilson_estimate",
        "wilson_lower",
        "wilson_upper",
    )
    assert not set(GOLD_CALIBRATION_TABLE.read_columns) & set(GOLD_CALIBRATION_TABLE.key)


@pytest.mark.unit
def test_dm_results_reads_raw_p_value() -> None:
    assert GOLD_DM_RESULTS.read_columns == (
        "n_points",
        "mean_differential",
        "statistic",
        "adjusted_p_value",
        "rejected",
        "fallback_applied",
        "alpha",
        "p_value",
    )
    assert "p_value" not in GOLD_DM_RESULTS.key


@pytest.mark.unit
def test_conformal_schemas_untouched() -> None:
    assert GOLD_CONFORMAL_CORRECTIONS.read_columns == (
        "fold",
        "tail_level",
        "rho",
        "status",
        "reason",
        "n",
        "rank",
        "correction",
        "infinite",
        "beta_a",
        "beta_b",
        "beta_mean",
        "beta_sd",
    )
    assert GOLD_CONFORMAL_COVERAGE.read_columns == (
        "status",
        "reason",
        "label",
        "n_points",
        "n_evaluated",
        "n_mean",
        "nominal",
        "count",
        "mean_count",
        "coverage",
        "mean_of_seed_coverages",
        "sd_of_seed_coverages",
        "n_seeds_used",
        "seeds_excluded",
        "mpiw",
        "mpiw_infinite",
        "mean_of_seed_mpiws",
        "sd_of_seed_mpiws",
        "crossed_rate",
        "mean_of_seed_crossed_rates",
        "sd_of_seed_crossed_rates",
        "nesting_violation_rate",
        "mean_of_seed_nesting_rates",
        "sd_of_seed_nesting_rates",
        "wilson_lower",
        "wilson_upper",
        "wilson_contains_nominal",
        "serial_dependence_warning",
    )
