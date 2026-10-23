"""Regras do andaime da equivalência sobre dado sintético (Stage 8.2, Task 10).

Sempre ativo, linhas em memória; nenhum arquivo de `data/analytics/` é lido. Critérios A9,
A10 e A11 (regras), D7, D8, D12, D13.
"""

from __future__ import annotations

import math

import pytest

from financial_forecasting.features.evaluation.domain.services.pinball_score import (
    pinball_loss,
)
from financial_forecasting.features.evaluation.domain.services.wilson_band import (
    wilson_interval,
)
from tests.equivalence import comparison_set as cs
from tests.equivalence.alignment import (
    intersection,
    latest_window_points,
    mean_loss_by_timestamp,
    mean_over_seeds,
    timestamps_by_horizon,
)
from tests.equivalence.comparisons import (
    U_Q_PICP,
    RawStatus,
    a1_check,
    a2_compare,
    a2_tolerance,
    dm_rejected,
    dm_sense,
    normalized_mean_diff,
    pair_measures,
    pinball_at,
    sense_cell,
    side_of_nominal,
    sign,
    u_q_mpiw,
    u_q_pinball,
)

pytestmark = pytest.mark.unit


def _row(
    window: str, ts: str, *, seed: int = 1, horizon: int = 1, value: float = 0.0
) -> dict[str, object]:
    return {
        "config_signature": window,
        "seed": seed,
        "horizon": horizon,
        "target_timestamp_utc": ts,
        "value": value,
    }


def test_prior_point_is_the_latest_test_window() -> None:
    """D7: no timestamp com duas janelas, fica o ponto da janela de início maior."""
    rows = [
        _row("w1", "2023-01-02", value=1.0),
        _row("w1", "2023-06-01", value=2.0),
        _row("w2", "2023-03-01", value=3.0),
        _row("w2", "2023-06-01", value=4.0),  # w2 começa depois de w1: fica este
        _row("w1", "2023-06-01", seed=2, value=5.0),  # outra seed, chave própria
    ]

    chosen = latest_window_points(
        rows,
        point_key=lambda r: (r["seed"], r["horizon"], r["target_timestamp_utc"]),
        window="config_signature",
        horizon="horizon",
        timestamp="target_timestamp_utc",
    )

    by_key = {(r["seed"], r["target_timestamp_utc"]): r["value"] for r in chosen}
    assert by_key == {
        (1, "2023-01-02"): 1.0,
        (1, "2023-06-01"): 4.0,
        (1, "2023-03-01"): 3.0,
        (2, "2023-06-01"): 5.0,
    }
    assert cs.PRIOR_DEDUP_RULE == "operationally_latest_fold"


def test_latest_window_refuses_two_points_in_the_same_window() -> None:
    rows = [_row("w1", "2023-01-02"), _row("w1", "2023-01-02")]
    with pytest.raises(ValueError, match="same test window"):
        latest_window_points(
            rows,
            point_key=lambda r: r["target_timestamp_utc"],
            window="config_signature",
            horizon="horizon",
            timestamp="target_timestamp_utc",
        )


def test_intersection_by_horizon_and_timestamp_ignores_fold() -> None:
    prior = [
        {"horizon": 1, "target_timestamp_utc": "a", "fold": "none"},
        {"horizon": 1, "target_timestamp_utc": "b", "fold": "none"},
        {"horizon": 7, "target_timestamp_utc": "a", "fold": "none"},
    ]
    new = [
        {"horizon": 1, "target_timestamp_utc": "b", "fold": "3"},
        {"horizon": 1, "target_timestamp_utc": "c", "fold": "4"},
        {"horizon": 7, "target_timestamp_utc": "a", "fold": "0"},
    ]

    common = intersection(
        timestamps_by_horizon(prior, horizon="horizon", timestamp="target_timestamp_utc"),
        timestamps_by_horizon(new, horizon="horizon", timestamp="target_timestamp_utc"),
    )

    assert common == {1: ("b",), 7: ("a",)}


def test_empty_intersection_is_recorded_not_compared() -> None:
    common = intersection({1: ["a"], 7: ["x"]}, {1: ["b"]})

    assert common == {1: (), 7: ()}
    assert a1_check([]).status is RawStatus.EMPTY_INTERSECTION
    assert a1_check([]).max_abs_diff is None


def test_a1_passes_at_half_ulp_and_fails_one_ulp_beyond() -> None:
    """D13: 2⁻⁵³·|y_ant|; y_ant = 0 ⇒ igualdade exata."""
    half = math.nextafter(1.0, 0.0)  # 1 - 2⁻⁵³: |Δ| = 2⁻⁵³·|1.0|, no limite
    beyond = math.nextafter(half, 0.0)  # 1 - 2⁻⁵²: um ulp além

    assert a1_check([(half, 1.0)]).status is RawStatus.WITHIN_TOLERANCE
    assert a1_check([(beyond, 1.0)]).status is RawStatus.OUT_OF_TOLERANCE
    assert a1_check([(0.0, 0.0)]).status is RawStatus.WITHIN_TOLERANCE
    assert a1_check([(5e-324, 0.0)]).status is RawStatus.OUT_OF_TOLERANCE
    assert a1_check([(-0.0, 0.0)]).status is RawStatus.WITHIN_TOLERANCE  # |Δ| = 0
    assert cs.A1_HALF_ULP == 2.0**-53


def test_a1_reports_count_out_and_max() -> None:
    result = a1_check([(1.0, 1.0), (2.0, 2.5), (-1.0, -1.25), (3.0, 3.0)])

    assert (result.n_points, result.n_out, result.max_abs_diff) == (4, 2, 0.5)
    assert result.status is RawStatus.OUT_OF_TOLERANCE


def test_a2_tolerance_is_max_of_r2_and_storage_precision() -> None:
    """D12 e: u_q por grandeza; precisão de armazenamento 2⁻⁵³·|m_ant| (`double`)."""
    assert u_q_pinball(0.02) == 0.02  # noqa: PLR2004
    assert u_q_mpiw([-0.5, 0.25, 0.25]) == pytest.approx(1.0 / 3.0)
    assert U_Q_PICP == 1.0
    # R2 domina: 1e-9·max(|m_A|, |m_ant|, u_q)
    assert a2_tolerance(m_a=0.02, m_ant=0.021, u_q=0.02) == 1e-9 * 0.021
    assert a2_tolerance(m_a=0.8, m_ant=0.79, u_q=U_Q_PICP) == 1e-9  # noqa: PLR2004
    # u_q dá a escala perto de zero
    assert a2_tolerance(m_a=1e-12, m_ant=0.0, u_q=0.5) == 0.5e-9  # noqa: PLR2004
    # a precisão de armazenamento é o piso quando a escala R2 é menor que meio ulp
    assert a2_tolerance(m_a=0.0, m_ant=1e10, u_q=0.0) == max(1e-9 * 1e10, 2.0**-53 * 1e10)
    within = a2_compare(m_a=0.8, m_ant=0.8 + 5e-10, u_q=1.0, n_recorded=10, n_points=10)
    outside = a2_compare(m_a=0.8, m_ant=0.8 + 2e-9, u_q=1.0, n_recorded=10, n_points=10)
    assert within.status is RawStatus.WITHIN_TOLERANCE
    assert outside.status is RawStatus.OUT_OF_TOLERANCE
    assert outside.abs_diff == pytest.approx(2e-9)


def test_a2_not_realizable_when_sample_size_cannot_be_rebuilt() -> None:
    result = a2_compare(m_a=0.1, m_ant=0.1, u_q=0.1, n_recorded=436, n_points=435)

    assert result.status is RawStatus.NOT_REALIZABLE
    assert (result.m_a, result.abs_diff, result.tolerance) == (None, None, None)


def test_seed_aggregation_mean_of_losses_and_mean_of_coverages() -> None:
    """D12 d (B-SEEDS): perda média por timestamp entre seeds; cobertura média por seed."""
    realized = {"a": 0.01, "b": -0.02}
    q10 = {1: {"a": -0.03, "b": -0.01}, 2: {"a": 0.02, "b": -0.05}}
    losses: dict[object, dict[str, float]] = {
        seed: {
            ts: pinball_loss(realized=realized[ts], quantile=q, level=0.1) for ts, q in qs.items()
        }
        for seed, qs in q10.items()
    }

    by_ts = mean_loss_by_timestamp(losses, ["a", "b"])
    pinball = math.fsum(by_ts.values()) / len(by_ts)

    per_seed = [pinball_at([0.01, -0.02], [q10[s]["a"], q10[s]["b"]], 0.1) for s in (1, 2)]
    assert pinball == pytest.approx(math.fsum(per_seed) / 2)
    assert by_ts["a"] == pytest.approx((losses[1]["a"] + losses[2]["a"]) / 2)
    assert mean_over_seeds({1: 0.75, 2: 0.85}) == pytest.approx(0.8)
    with pytest.raises(ValueError, match="no point at b"):
        mean_loss_by_timestamp({1: {"a": 0.1}}, ["a", "b"])
    with pytest.raises(ValueError, match="no seed"):
        mean_over_seeds({})


def test_pair_measures_use_the_closed_interval() -> None:
    measures = pair_measures([0.0, 1.0, 2.0, 5.0], [0.0, 0.5, 2.5, 4.0], [1.0, 1.0, 3.0, 5.0])

    assert (measures.covered, measures.n_points) == (3, 4)  # bordas contam como dentro
    assert measures.picp == 0.75  # noqa: PLR2004
    assert measures.mpiw == pytest.approx((1.0 + 0.5 + 0.5 + 1.0) / 4)
    assert cs.NEW_INTERVAL_IS_CLOSED is True


def test_dm_sign_normalized_to_candidate_minus_baseline() -> None:
    """As duas convenções do D8 levam ao mesmo d̄ = perda(candidato) - perda(baseline)."""
    assert normalized_mean_diff(-0.3, "candidate_minus_baseline") == -0.3  # noqa: PLR2004
    assert normalized_mean_diff(0.3, "baseline_minus_candidate") == -0.3  # noqa: PLR2004
    assert cs.PRIOR_DM_SIGN_CONVENTION == cs.NEW_DM_SIGN_CONVENTION == "candidate_minus_baseline"
    with pytest.raises(ValueError, match="unknown DM sign convention"):
        normalized_mean_diff(0.1, "tft_minus_whatever")


def test_dm_rejection_uses_unadjusted_p_and_side_alpha() -> None:
    assert dm_rejected(0.05, 0.05) is True
    assert dm_rejected(0.0501, 0.05) is False
    assert dm_sense(
        mean_diff=-0.1, convention="candidate_minus_baseline", p_value=0.03, alpha=0.05
    ) == (-1, True)
    assert dm_sense(
        mean_diff=0.1, convention="baseline_minus_candidate", p_value=0.03, alpha=0.01
    ) == (-1, False)
    assert cs.PRIOR_DM_P_VALUE == "pvalue_one_sided_less"
    assert cs.NEW_DM_P_VALUE == "p_value"  # nunca o adjusted_p_value (Holm)
    assert cs.PRIOR_DM_ALPHA == 0.05  # noqa: PLR2004


def test_side_of_nominal_below_inside_above_wilson_band() -> None:
    n = 250
    lower, upper = wilson_interval(count=200, n=n, band_level=0.95)
    assert lower <= 0.8 <= upper  # noqa: PLR2004

    assert side_of_nominal(count=200, n=n) == "inside"
    assert side_of_nominal(count=240, n=n) == "below"  # cobertura alta: nominal sob a banda
    assert side_of_nominal(count=150, n=n) == "above"
    assert side_of_nominal(count=200.5, n=n) == "inside"  # contagem média entre seeds


def test_sense_cell_equal_or_divergent() -> None:
    """Sinal ± e zero exato como sinal próprio."""
    assert (sign(-0.1), sign(0.0), sign(-0.0), sign(2.0)) == (-1, 0, 0, 1)
    assert sense_cell(sign(-0.1), sign(-3.0)) is RawStatus.SAME_SENSE
    assert sense_cell(sign(-0.1), sign(0.0)) is RawStatus.DIVERGENT_SENSE
    assert sense_cell(sign(0.0), sign(0.0)) is RawStatus.SAME_SENSE
    assert sense_cell("inside", "below") is RawStatus.DIVERGENT_SENSE
    assert sense_cell((-1, True), (-1, True)) is RawStatus.SAME_SENSE
    assert sense_cell((-1, True), (-1, False)) is RawStatus.DIVERGENT_SENSE


def test_comparison_set_is_fixed_before_values() -> None:
    assert cs.COMMON_LEVELS == (0.1, 0.5, 0.9)
    assert cs.PAIR_80 == (0.1, 0.9)
    assert cs.PRIOR_FILES == tuple(cs.FILTER_COLUMNS) == tuple(cs.VALUE_COLUMNS)
    assert cs.COMMON_BASELINES == ()  # preenchido só na E1
    assert cs.MODEL_LABEL_COLUMN is None
    assert cs.variant_of_column("picp_post_guardrail") == "post_guardrail"
    assert cs.variant_of_column("mpiw_raw") == "raw"
    assert cs.variant_of_column("picp_q10_q90") == cs.MARGINAL_COVERAGE_VARIANT
    assert cs.NEW_SCORED_VARIANT == cs.PRIOR_LOSS_VARIANT == "post_guardrail"
