"""Testes unitários das regras puras das análises pós-veredito (D1 e D3, #243; D4, #272)."""

from __future__ import annotations

import math

import pytest

from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from tests.tcc.post_verdict import (
    median_is_identically_zero,
    medians,
    pair_widths,
    point_profile,
    quantile_type7,
    seed_ensemble,
    seed_mean,
    spearman,
    tail_rates,
    values_at_decision,
)
from tests.tcc.post_verdict_report import (
    BEGIN_MARKER,
    END_MARKER,
    PostVerdictSanityError,
    SanityCheck,
    block_of,
    check_sanity,
)

LEVELS = (0.1, 0.5, 0.9)
STAMPS = ("2020-01-01T00:00:00+00:00", "2020-01-02T00:00:00+00:00", "2020-01-03T00:00:00+00:00")


def _series(
    grids: list[tuple[float, ...]],
    realized: tuple[float, ...],
    *,
    levels: tuple[float, ...] = LEVELS,
) -> CoverageSeries:
    return CoverageSeries(
        horizon=1,
        levels=levels,
        target_timestamps=STAMPS[: len(grids)],
        forecasts=tuple(
            QuantileForecast(
                levels=levels, raw_values=g, guardrail_values=g, guardrail_applied=False
            )
            for g in grids
        ),
        realized=realized,
    )


def test_point_profile_rmse_mae_hits_and_ties() -> None:
    series = _series(
        [(-1.0, 0.5, 1.0), (-1.0, -0.5, 1.0), (-1.0, 0.0, 1.0)],
        (1.0, 0.5, 0.2),
    )
    profile = point_profile(series)
    # erros: 0.5, 1.0, 0.2
    assert profile.rmse == pytest.approx(math.sqrt((0.25 + 1.0 + 0.04) / 3))
    assert profile.mae == pytest.approx(1.7 / 3)
    assert profile.hits == 1  # só o 1º: 0.5·1.0 > 0; o 2º erra o sinal; o 3º empata
    assert profile.ties == 1
    assert profile.n_points == len(series.realized)


def test_realized_zero_is_a_tie_not_a_hit() -> None:
    profile = point_profile(_series([(-1.0, 0.3, 1.0)], (0.0,)))
    assert (profile.hits, profile.ties) == (0, 1)


def test_medians_read_the_scored_vector_and_need_the_median_level() -> None:
    assert medians(_series([(-1.0, 0.25, 1.0)], (0.0,))) == (0.25,)
    no_median = _series([(-1.0, 1.0)], (0.0,), levels=(0.1, 0.9))
    with pytest.raises(ValueError, match="no median level"):
        medians(no_median)


def test_identically_zero_median_needs_every_point_of_every_seed() -> None:
    zero = _series([(-1.0, 0.0, 1.0), (-2.0, 0.0, 2.0)], (0.1, 0.2))
    almost = _series([(-1.0, 0.0, 1.0), (-2.0, 1e-300, 2.0)], (0.1, 0.2))
    assert median_is_identically_zero([zero, zero])
    assert not median_is_identically_zero([zero, almost])


def test_seed_mean() -> None:
    assert seed_mean([1.0, 2.0, 4.0]) == pytest.approx(7.0 / 3)
    with pytest.raises(ValueError, match="at least one seed"):
        seed_mean([])


def test_seed_ensemble_averages_quantiles_level_by_level() -> None:
    a = _series([(-1.0, 0.0, 1.0), (-2.0, 0.2, 2.0)], (0.1, 0.2))
    b = _series([(-3.0, 1.0, 3.0), (-4.0, 0.4, 2.0)], (0.1, 0.2))
    ensemble = seed_ensemble([a, b])
    assert ensemble.scored_values(0) == (-2.0, 0.5, 2.0)
    assert ensemble.scored_values(1) == pytest.approx((-3.0, 0.3, 2.0))
    assert ensemble.forecasts[0].raw_values == ensemble.forecasts[0].guardrail_values
    assert not ensemble.forecasts[0].guardrail_applied
    assert ensemble.realized == a.realized
    assert ensemble.target_timestamps == a.target_timestamps


def test_seed_ensemble_of_one_seed_is_the_seed() -> None:
    a = _series([(-1.0, 0.0, 1.0)], (0.1,))
    assert seed_ensemble([a]).scored_values(0) == a.scored_values(0)


def test_seed_ensemble_refuses_misaligned_seeds_and_no_seed() -> None:
    a = _series([(-1.0, 0.0, 1.0)], (0.1,))
    other_realized = _series([(-1.0, 0.0, 1.0)], (0.2,))
    with pytest.raises(ValueError, match="realized differs"):
        seed_ensemble([a, other_realized])
    with pytest.raises(ValueError, match="at least one seed"):
        seed_ensemble([])


def test_tail_rates_use_the_gold_tie_rules() -> None:
    # y = q_0.1 é violação inferior (y ≤ q); y = q_0.9 não é violação superior; PICP fechado
    series = _series(
        [(-1.0, 0.0, 1.0)] * 3,
        (-1.0, 1.0, 2.0),
    )
    rates = tail_rates(series, pair=(0.1, 0.9))
    assert rates.lower == pytest.approx(1 / 3)
    assert rates.upper == pytest.approx(1 / 3)
    assert rates.picp == pytest.approx(2 / 3)
    with pytest.raises(ValueError, match="not in the grid"):
        tail_rates(series, pair=(0.25, 0.75))


def test_check_sanity_passes_within_tolerance_and_stops_otherwise() -> None:
    check_sanity([SanityCheck("ok", 4.05e-3, 4.05e-3 * (1 + 1e-12))])
    with pytest.raises(PostVerdictSanityError, match="1 of 2 checks differ: bad"):
        check_sanity([SanityCheck("ok", 1.0, 1.0), SanityCheck("bad", 1.0, 1.001)])


def test_block_of_returns_the_marked_block() -> None:
    text = f"intro\n{BEGIN_MARKER}\nx\n{END_MARKER}\nfim\n"
    assert block_of(text) == f"{BEGIN_MARKER}\nx\n{END_MARKER}\n"
    with pytest.raises(ValueError, match="markers"):
        block_of("sem marcadores")


def test_pair_widths_read_the_scored_vector() -> None:
    series = _series([(-1.0, 0.0, 1.0), (-0.5, 0.0, 2.0)], (0.1, 0.2))
    assert pair_widths(series, pair=(0.1, 0.9)) == (2.0, 2.5)
    with pytest.raises(ValueError, match="not in the grid"):
        pair_widths(series, pair=(0.25, 0.75))


def test_values_at_decision_step_back_h_sessions_on_the_grid() -> None:
    grid = ("2019-12-30T00:00:00+00:00", "2019-12-31T00:00:00+00:00", *STAMPS)
    column = (10.0, 20.0, 30.0, 40.0, 50.0)
    series = _series([(-1.0, 0.0, 1.0)] * 2, (0.1, 0.2))  # alvos STAMPS[0:2], h = 1
    assert values_at_decision(series, timestamps=grid, column=column) == (20.0, 30.0)
    with pytest.raises(ValueError, match="before the session grid"):
        values_at_decision(series, timestamps=STAMPS, column=column)
    with pytest.raises(ValueError, match="not in the session grid"):
        values_at_decision(series, timestamps=grid[:2], column=column)


def test_spearman_matches_the_textbook_cases() -> None:
    assert spearman([1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 40.0, 80.0]) == pytest.approx(1.0)
    assert spearman([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]) == pytest.approx(-1.0)
    # empates com postos médios: x = (1, 2, 2, 3) -> postos (1, 2.5, 2.5, 4)
    assert spearman([1.0, 2.0, 2.0, 3.0], [1.0, 3.0, 2.0, 4.0]) == pytest.approx(
        4.5 / math.sqrt(4.5 * 5.0)
    )
    with pytest.raises(ValueError, match="constant"):
        spearman([1.0, 1.0], [1.0, 2.0])
    with pytest.raises(ValueError, match="same length"):
        spearman([1.0], [1.0])


def test_quantile_type7_interpolates_like_r_and_numpy() -> None:
    values = [4.0, 1.0, 3.0, 2.0]
    assert quantile_type7(values, 0.0) == min(values)
    assert quantile_type7(values, 1.0) == max(values)
    assert quantile_type7(values, 0.5) == pytest.approx(2.5)
    assert quantile_type7(values, 0.05) == pytest.approx(1.15)  # numpy.quantile(..., 0.05)
    with pytest.raises(ValueError, match="probability"):
        quantile_type7(values, 1.5)
