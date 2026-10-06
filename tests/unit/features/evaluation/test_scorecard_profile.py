"""Unit test do perfil do scorecard (Stage 6.5, A7, I8, I10, I12; ADR 6.5.0008 item 2).

Sobre o gold sintético da `_scorecard_factory`: desfecho por nível, IC do efeito do DM
pelo `student_t_quantile`, `fallback_applied` copiado, comparador acima do limiar de
degeneração presente nas leituras, bandas a 95 % e frações entre seeds, gate na amostra
comum, variante "sem lacunas", divergências Bartlett e moving-block, spread por seed,
menor P̄_G, valores copiados sem cálculo e os perfis declarados fora desta Stage.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    ProfileState,
    ScorecardProfile,
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CALIBRATION_TABLE,
    GOLD_CHRISTOFFERSEN_MONTE_CARLO,
    GOLD_DIFFERENTIAL_ACF,
    GOLD_DIFFERENTIAL_BREAKS,
    GOLD_DM_PROFILES,
    GOLD_DM_RESULTS,
    GOLD_DM_SEED_FRACTION,
    GOLD_MCS_BLOCK_SENSITIVITY,
    GOLD_MCS_RESULTS,
    GOLD_PARTIAL_DEGENERACY,
    GoldTableSchema,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGenerationCorruptError,
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
from tests.unit.features.evaluation._preregistration_payload import r1_payload, valid_payload
from tests.unit.features.evaluation._scorecard_factory import (
    PROFILE_PAIR_ACF,
    REFERENCE,
    T_POINTS,
    StoredGold,
    make_stored,
)

_PLAN = Preregistration.from_mapping(valid_payload())
_R1 = Preregistration.from_mapping(r1_payload())
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
    assert stored.set_cell(
        GOLD_DM_RESULTS.name, _is(horizon=1, comparator="baseline_ar1"), "statistic", 0.0
    )
    zero = next(r for r in _first(stored).dm if r.comparator == "baseline_ar1")
    assert zero.effect_interval is None


@pytest.mark.unit
def test_profile_fallback_applied() -> None:
    stored = make_stored(_PLAN)
    assert stored.set_cell(
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
        assert stored.set_cell(
            GOLD_CALIBRATION_TABLE.name,
            _is(model=_CAND, seed=seed, horizon=1, band_level=0.95),
            "wilson_contains_nominal",
            False,
        )
    assert stored.set_cell(
        GOLD_CALIBRATION_TABLE.name,
        _is(model=_CAND, seed=3, horizon=1, band_level=0.95),
        "p_ind",
        0.01,
    )
    assert stored.set_cell(
        GOLD_CALIBRATION_TABLE.name,
        _is(model=_CAND, seed=4, horizon=1, band_level=0.95),
        "independence_status",
        "below_min_violations",
    )
    for seed in (5, 6):  # p_cc distinto do p_ind (Checkpoint C bloco 3, L3)
        assert stored.set_cell(
            GOLD_CALIBRATION_TABLE.name,
            _is(model=_CAND, seed=seed, horizon=1, band_level=0.95),
            "p_cc",
            0.02,
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
    assert series[0].fraction_cc_rejected == pytest.approx(2 / 9)
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
    assert stored.set_cell(
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
    assert stored.set_cell(
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
    assert stored.set_cell(
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
    assert stored.set_cell(
        GOLD_DM_RESULTS.name,
        _is(horizon=1, comparator="baseline_ar1"),
        "mean_differential",
        -0.0123456789,
    )
    assert stored.set_cell(
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
    """Stage 6.6: só o diagrama de nitidez (8.3) fica fora do scorecard."""
    assert _profile(make_stored(_PLAN)).declared_not_built == ("sharpness_diagram",)


_SEVEN = (
    "mcs_block_h",
    "mcs_block_sqrt_t",
    "dm_per_fold",
    "dm_per_seed",
    "dm_per_tau",
    "dm_differential_stationarity",
    "partial_degeneracy_per_pair",
)


@pytest.mark.unit
def test_r0_states_seven_not_frozen_and_monte_carlo_built() -> None:
    """CA12 / I9: sem `[profile_parameters]`, os sete perfis ficam `not_frozen_in_revision`."""
    profile = _profile(make_stored(_PLAN))
    states = dict(profile.profile_states)
    assert [p for p, _ in profile.profile_states] == list(_PLAN.profiles.declared)
    assert {p for p, s in states.items() if s is ProfileState.NOT_FROZEN_IN_REVISION} == set(_SEVEN)
    assert states["christoffersen_monte_carlo_h1"] is ProfileState.BUILT
    assert states["sharpness_diagram"] is ProfileState.NOT_BUILT_HERE
    assert profile.horizons[0].monte_carlo  # o MC roda no r0
    assert all(not h.dm_subsets and not h.stationarity for h in profile.horizons)


@pytest.mark.unit
def test_r1_states_built_even_with_an_empty_table() -> None:
    """CA12: com as regras congeladas, tudo `built` — inclusive com tabela vazia legítima."""
    stored = make_stored(_R1)
    stored.drop_rows(GOLD_DM_PROFILES.name, lambda _row: True)
    profile = _profile_for(_R1, stored)
    states = dict(profile.profile_states)
    assert {p for p, s in states.items() if s is not ProfileState.BUILT} == {"sharpness_diagram"}
    assert profile.declared_not_built == ("sharpness_diagram",)
    assert all(not h.dm_subsets for h in profile.horizons)


@pytest.mark.unit
def test_r1_profile_rows_are_copied_from_the_gold() -> None:
    """Cada tabela de perfil copiada por horizonte, coluna a coluna (nada recalculado)."""
    stored = make_stored(_R1)
    profile = _profile_for(_R1, stored)
    for horizon in profile.horizons:
        h = horizon.horizon
        for table, copied in (
            (GOLD_DM_PROFILES, horizon.dm_subsets),
            (GOLD_DM_SEED_FRACTION, horizon.dm_seed_fractions),
            (GOLD_MCS_BLOCK_SENSITIVITY, horizon.mcs_block_sensitivity),
            (GOLD_CHRISTOFFERSEN_MONTE_CARLO, horizon.monte_carlo),
            (GOLD_PARTIAL_DEGENERACY, horizon.partial_degeneracy),
        ):
            gold = sorted(
                (_without(r, table) for r in stored.rows[table.name] if r["horizon"] == h),
                key=repr,
            )
            assert sorted((dataclasses.asdict(row) for row in copied), key=repr) == gold, table
        (stationarity,) = horizon.stationarity
        (gold_break,) = [r for r in stored.rows[GOLD_DIFFERENTIAL_BREAKS.name] if r["horizon"] == h]
        assert {k: v for k, v in dataclasses.asdict(stationarity).items() if k != "acf"} == (
            _without(gold_break, GOLD_DIFFERENTIAL_BREAKS)
        )
        assert stationarity.acf == PROFILE_PAIR_ACF  # em ordem de lag
    json.dumps(profile.as_mapping())


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "column", "value"),
    [
        (GOLD_DM_PROFILES, "p_value", "0.01"),
        (GOLD_MCS_BLOCK_SENSITIVITY, "block_size", 2.5),
        (GOLD_CHRISTOFFERSEN_MONTE_CARLO, "mc_p_cc", "x"),
        (GOLD_DIFFERENTIAL_ACF, "acf", None),
    ],
)
def test_profile_cell_of_wrong_type_is_named_corruption(
    table: GoldTableSchema, column: str, value: object
) -> None:
    """D9: tipo divergente numa tabela de perfil é corrupção nomeada (nunca coerção)."""
    stored = make_stored(_R1)
    assert stored.set_cell(table.name, lambda _row: True, column, value)
    with pytest.raises(GoldGenerationCorruptError, match=column):
        _profile_for(_R1, stored)


def _without(row: dict[str, object], table: GoldTableSchema) -> dict[str, object]:
    """A linha gold sem partição, horizonte e as colunas constantes que o DTO não copia."""
    dropped = {"asset", "parent_sweep_id", "preregistration_ref", "horizon", "candidate"}
    return {k: v for k, v in row.items() if k not in dropped}


def _profile_for(plan: Preregistration, stored: StoredGold) -> ScorecardProfile:
    generation = stored.generation()
    command = refresh_command_from(plan, REFERENCE)
    evidence = evidence_from_generation(prereg=plan, command=command, generation=generation)
    verdict = ConfirmatoryScorecard.decide(plan, evidence)
    return build_profile(prereg=plan, evidence=evidence, verdict=verdict, generation=generation)


@pytest.mark.unit
def test_profile_comparators_threshold_gate_band_rows() -> None:
    """Checkpoint C bloco 3, L3: a banda do comparador vem das linhas do nível do gate.

    A degeneração do comparador é a da série: igual nas duas caudas por invariante do
    `ComparatorCalibration` (Checkpoint C bloco 1, B3), por isso lida de uma cauda só.
    """
    stored = make_stored(_PLAN)
    assert stored.set_cell(
        GOLD_CALIBRATION_TABLE.name,
        _is(model="baseline_ar1", horizon=1, band_level=0.95),
        "n_violations",
        100,
    )

    first = _first(stored)

    ar1 = next(c for c in first.comparators_calibration if c.model == "baseline_ar1")
    assert (ar1.lower_contains_nominal, ar1.upper_contains_nominal) == (True, True)
    evidence = next(
        c
        for c in evidence_from_generation(
            prereg=_PLAN, command=_COMMAND, generation=stored.generation()
        )[0].comparators_calibration
        if c.model == "baseline_ar1"
    )
    assert evidence.lower.mean_degeneracy == evidence.upper.mean_degeneracy


@pytest.mark.unit
def test_profile_without_gaps_rows_gate_band() -> None:
    """Checkpoint C bloco 3, L3/R3: sem lacunas lê o nível do gate; sem as linhas → ()."""
    stored = make_stored(_PLAN)
    base = {"model": _CAND, "horizon": 1, "sample": "model_full", "includes_degenerate": True}
    assert stored.set_cell(
        GOLD_CALIBRATION_TABLE.name, _is(**base, band_level=0.95), "n_violations", 77
    )
    assert stored.set_cell(
        GOLD_CALIBRATION_TABLE.name, _is(**base, band_level=0.975), "n_violations", 31
    )

    without = {s.kind: s for s in _first(stored).without_gaps}

    assert without["lower_tail"].mean_violations == 31.0  # noqa: PLR2004
    empty = make_stored(_PLAN)
    assert empty.drop_rows(GOLD_CALIBRATION_TABLE.name, _is(includes_degenerate=True))
    assert _first(empty).without_gaps == ()


@pytest.mark.unit
def test_profile_moving_block_divergence_without_scheme() -> None:
    """Checkpoint C bloco 3, R3: plano sem moving-block → sem divergência."""
    payload = valid_payload()
    payload["mcs"]["sensitivity_schemes"] = []  # type: ignore[index]
    plan = Preregistration.from_mapping(payload)

    profile = _profile_for(plan, make_stored(plan))

    assert profile.horizons[0].mcs_moving_block_divergence is False


@pytest.mark.unit
def test_profile_p_ind_of_wrong_type_is_named_corruption() -> None:
    """Checkpoint C bloco 1 (T2, F6): célula `p_ind` nula numa linha "applicable" é
    corrupção nomeada (antes: `TypeError` cru na comparação com alpha)."""
    stored = make_stored(_PLAN)
    hits = stored.set_cell(
        GOLD_CALIBRATION_TABLE.name,
        _is(independence_status="applicable", band_level=_PLAN.h1_gate.profile_band_level),
        "p_ind",
        None,
    )
    assert hits
    with pytest.raises(
        GoldGenerationCorruptError, match=r"gold_calibration_table\.p_ind: expected float"
    ):
        _profile(stored)


@pytest.mark.unit
@pytest.mark.parametrize("declared", [(), ("b", "a"), ("a", "b", "c")])
def test_declared_not_built_must_be_the_not_built_here_states(declared: tuple[str, ...]) -> None:
    """Checkpoint C bloco 6, H-3: `declared_not_built` = os `not_built_here`, na ordem."""
    states = (
        ("a", ProfileState.NOT_BUILT_HERE),
        ("x", ProfileState.BUILT),
        ("b", ProfileState.NOT_BUILT_HERE),
    )
    with pytest.raises(ValueError, match="not_built_here"):
        ScorecardProfile(horizons=(), declared_not_built=declared, profile_states=states)
    ScorecardProfile(horizons=(), declared_not_built=("a", "b"), profile_states=states)
