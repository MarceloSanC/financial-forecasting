"""Unit test do perfil do scorecard (Stage 6.5, A7, I8, I10, I12; ADR 6.5.0008 item 2).

Sobre o gold sintético da `_scorecard_factory`: desfecho por nível, IC do efeito do DM
pelo `student_t_quantile`, `fallback_applied` copiado, comparador acima do limiar de
degeneração presente nas leituras, bandas a 95 % e frações entre seeds, gate na amostra
comum, variante "sem lacunas", divergências Bartlett e moving-block, spread por seed,
menor P̄_G, valores copiados sem cálculo e os perfis declarados fora desta Stage.
"""

from __future__ import annotations

import json

import pytest

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    ScorecardProfile,
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CALIBRATION_TABLE,
    GOLD_DM_RESULTS,
    GOLD_MCS_RESULTS,
)
from financial_forecasting.features.evaluation.application.use_cases.scorecard_evidence import (
    evidence_from_generation,
)
from financial_forecasting.features.evaluation.application.use_cases.scorecard_profile import (
    build_profile,
)
from financial_forecasting.features.evaluation.domain.services.confirmatory_scorecard import (
    ConfirmatoryScorecard,
)
from financial_forecasting.features.evaluation.domain.services.student_t import (
    student_t_quantile,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from tests.unit.features.evaluation._preregistration_payload import valid_payload
from tests.unit.features.evaluation._scorecard_factory import (
    REFERENCE,
    T_POINTS,
    StoredGold,
    make_stored,
)

_PLAN = Preregistration.from_mapping(valid_payload())
_COMMAND = refresh_command_from(_PLAN, REFERENCE)
_CAND = _PLAN.candidate
_EFFECT_TOL = 1e-12


def _profile(stored: StoredGold) -> ScorecardProfile:
    generation = stored.generation()
    evidence = evidence_from_generation(prereg=_PLAN, command=_COMMAND, generation=generation)
    verdict = ConfirmatoryScorecard.decide(_PLAN, evidence)
    return build_profile(prereg=_PLAN, evidence=evidence, verdict=verdict, generation=generation)


def _first(stored: StoredGold):  # type: ignore[no-untyped-def]  # noqa: ANN202
    return _profile(stored).horizons[0]


def _is(**values: object):  # type: ignore[no-untyped-def]  # noqa: ANN202
    return lambda row: all(row.get(k) == v for k, v in values.items())


@pytest.mark.unit
def test_profile_tier_outcomes() -> None:
    rejected = [*_PLAN.comparator_tiers.naive, *_PLAN.comparator_tiers.ml, "baseline_ar1"]
    stored = make_stored(_PLAN, dm_rejected=rejected, mcs_included=_PLAN.comparators)

    tiers = {tier.tier: tier for tier in _first(stored).tiers}

    assert tiers["naive"].holm_rejects_all is True
    assert tiers["ml"].holm_rejects_all is True
    assert tiers["strong_statistical"].holm_rejects_all is False
    assert all(t.candidate_in_mcs is False for t in tiers.values())
    assert tiers["strong_statistical"].beats_or_ties is False


@pytest.mark.unit
def test_profile_dm_effect_ci() -> None:
    first = _first(make_stored(_PLAN))

    row = next(
        r
        for r in first.dm
        if r.comparator == "baseline_zero_return" and r.estimator == "rectangular"
    )
    half = student_t_quantile(0.975, T_POINTS - 1.0) * abs(row.mean_differential / row.statistic)
    assert row.effect_interval is not None
    assert row.effect_interval[0] == pytest.approx(row.mean_differential - half, abs=_EFFECT_TOL)
    assert row.effect_interval[1] == pytest.approx(row.mean_differential + half, abs=_EFFECT_TOL)
    stored = make_stored(_PLAN)
    stored.set_cell(
        GOLD_DM_RESULTS.name, _is(horizon=1, comparator="baseline_ar1"), "statistic", 0.0
    )
    zero = next(r for r in _first(stored).dm if r.comparator == "baseline_ar1")
    assert zero.effect_interval is None


@pytest.mark.unit
def test_profile_fallback_applied() -> None:
    stored = make_stored(_PLAN)
    stored.set_cell(
        GOLD_DM_RESULTS.name,
        _is(horizon=1, comparator="gbm_quantile", variance_estimator="bartlett"),
        "fallback_applied",
        True,
    )

    rows = {(r.comparator, r.estimator): r.fallback_applied for r in _first(stored).dm}

    assert rows["gbm_quantile", "bartlett"] is True
    assert rows["gbm_quantile", "rectangular"] is False


@pytest.mark.unit
def test_profile_comparators_threshold() -> None:
    def counts(
        model: str, _s: int | None, _h: int, _sample: str, _kind: str
    ) -> tuple[int, int, float]:
        return (25, 250, 0.02) if model == "baseline_zero_return" else (25, 250, 0.0)

    first = _first(make_stored(_PLAN, counts=counts))

    by_model = {c.model: c for c in first.comparators_calibration}
    assert by_model["baseline_zero_return"].degeneracy_above_threshold is True
    assert by_model["baseline_zero_return"].mean_degeneracy_rate == pytest.approx(0.02)
    assert by_model["baseline_ar1"].degeneracy_above_threshold is False
    assert [c.model for c in first.comparators_calibration] == list(_PLAN.comparators)
    assert "baseline_zero_return" in {r.comparator for r in first.dm}


@pytest.mark.unit
def test_profile_band_95_fractions() -> None:
    stored = make_stored(_PLAN)
    for seed in (1, 2):
        stored.set_cell(
            GOLD_CALIBRATION_TABLE.name,
            _is(model=_CAND, seed=seed, horizon=1, band_level=0.95),
            "wilson_contains_nominal",
            False,
        )
    stored.set_cell(
        GOLD_CALIBRATION_TABLE.name,
        _is(model=_CAND, seed=3, horizon=1, band_level=0.95),
        "p_ind",
        0.01,
    )
    stored.set_cell(
        GOLD_CALIBRATION_TABLE.name,
        _is(model=_CAND, seed=4, horizon=1, band_level=0.95),
        "independence_status",
        "below_min_violations",
    )

    series = [
        s
        for s in _first(stored).calibration_95
        if s.model == _CAND
        and s.sample == "model_full"
        and s.kind == "lower_tail"
        and s.includes_degenerate is False
        and s.dgt_offset is None
    ]

    assert len(series) == 1
    assert series[0].n_seeds == 10  # noqa: PLR2004
    assert series[0].fraction_contains_nominal == pytest.approx(0.8)
    assert series[0].fraction_ind_rejected == pytest.approx(1 / 9)
    assert series[0].n_independence_not_applicable == 1


@pytest.mark.unit
def test_profile_common_sample_gate() -> None:
    def counts(_m: str, _s: int | None, _h: int, sample: str, _kind: str) -> tuple[int, int, float]:
        return (60, 250, 0.0) if sample == "common" else (25, 250, 0.0)

    sensitivities = _first(make_stored(_PLAN, counts=counts)).gate_sensitivities

    assert sensitivities.common_sample_passed is False
    assert "common_sample" in sensitivities.divergences


@pytest.mark.unit
def test_profile_without_gaps_rows() -> None:
    stored = make_stored(_PLAN)
    stored.set_cell(
        GOLD_CALIBRATION_TABLE.name,
        _is(model=_CAND, horizon=1, sample="model_full", includes_degenerate=True, dgt_offset=None),
        "n_violations",
        31,
    )

    without = {s.kind: s for s in _first(stored).without_gaps}

    assert without["lower_tail"].mean_violations == 31.0  # noqa: PLR2004
    assert without["upper_tail"].level == 0.9  # noqa: PLR2004


@pytest.mark.unit
def test_profile_bartlett_divergence() -> None:
    stored = make_stored(_PLAN)
    stored.set_cell(
        GOLD_DM_RESULTS.name,
        _is(horizon=1, comparator="baseline_zero_return", variance_estimator="bartlett"),
        "rejected",
        False,
    )

    assert _first(stored).bartlett_divergences == ("baseline_zero_return",)
    assert _first(make_stored(_PLAN)).bartlett_divergences == ()


@pytest.mark.unit
def test_profile_moving_block_divergence() -> None:
    stored = make_stored(_PLAN)
    stored.set_cell(
        GOLD_MCS_RESULTS.name, _is(horizon=1, scheme="moving_block", model=_CAND), "included", False
    )

    assert _first(stored).mcs_moving_block_divergence is True
    assert _first(make_stored(_PLAN)).mcs_moving_block_divergence is False


@pytest.mark.unit
def test_profile_seed_spread() -> None:
    def pinball(model: str, seed: int | None, _h: int) -> float:
        return 0.10 + 0.001 * (seed or 0) if model == _CAND else 0.12

    first = _first(make_stored(_PLAN, pinball=pinball))

    grid = next(
        d
        for d in first.descriptors
        if d.model == _CAND and d.sample == "common" and d.metric == "pinball_grid_mean"
    )
    assert (grid.minimum, grid.maximum, grid.n_seeds) == (
        pytest.approx(0.101),
        pytest.approx(0.110),
        10,
    )
    assert grid.mean == pytest.approx(0.1055)
    single = next(
        d
        for d in first.descriptors
        if d.model == "baseline_ar1" and d.metric == "pinball_grid_mean"
    )
    assert single.mean == single.minimum == single.maximum


@pytest.mark.unit
def test_profile_lowest_pinball() -> None:
    def pinball(model: str, _seed: int | None, _h: int) -> float:
        return 0.05 if model == "baseline_ar1" else 0.10

    assert _first(make_stored(_PLAN, pinball=pinball)).lowest_mean_pinball is False
    assert _first(make_stored(_PLAN)).lowest_mean_pinball is True


@pytest.mark.unit
def test_profile_copies_gold_values() -> None:
    stored = make_stored(_PLAN)
    stored.set_cell(
        GOLD_DM_RESULTS.name,
        _is(horizon=1, comparator="baseline_ar1"),
        "mean_differential",
        -0.0123456789,
    )
    stored.set_cell(
        GOLD_DM_RESULTS.name,
        _is(horizon=1, comparator="baseline_ar1"),
        "adjusted_p_value",
        0.0314159,
    )

    profile = _profile(stored)
    row = next(r for r in profile.horizons[0].dm if r.comparator == "baseline_ar1")

    assert row.mean_differential == -0.0123456789  # noqa: PLR2004
    assert row.adjusted_p_value == 0.0314159  # noqa: PLR2004
    assert row.n_points == T_POINTS
    json.dumps(profile.as_mapping())


@pytest.mark.unit
def test_profile_declared_not_built() -> None:
    assert _profile(make_stored(_PLAN)).declared_not_built == (
        "mcs_block_h",
        "mcs_block_sqrt_t",
        "christoffersen_monte_carlo_h1",
        "dm_per_fold",
        "dm_per_seed",
        "dm_per_tau",
        "dm_differential_stationarity",
        "partial_degeneracy_per_pair",
        "sharpness_diagram",
    )
