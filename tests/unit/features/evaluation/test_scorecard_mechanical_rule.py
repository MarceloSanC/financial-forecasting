"""Unit test do `ConfirmatoryScorecard.decide` (Stage 6.5, A6, I4, I9, I10, I12, C9, C11).

Um teste por desfecho de H2 e pelo vencedor primário (ADR 6.5.0007; P4 do ADR
6.5.0010: o nível ML conta como forte), H1 reprovado com DM todo rejeitado →
`NOT_APPLICABLE` sem vencedor, menor P̄_G só como informação, comparador mal
calibrado segue na família, horizontes independentes, sucesso = H1 em ≥ 1
horizonte, veredito sem campo do perfil, leitura por nível e as defesas de
entrada (horizontes e identificadores de regra).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable

import pytest

from financial_forecasting.features.evaluation.domain.services.confirmatory_scorecard import (
    ConfirmatoryScorecard,
    H2Outcome,
    HorizonVerdict,
    ScorecardVerdict,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.features.evaluation.domain.value_objects.scorecard_evidence import (
    CalibrationEvidence,
    ComparatorCalibration,
    DgtTailEvidence,
    DmEvidence,
    HorizonEvidence,
    McsEvidence,
    SeedTailCounts,
    TailEvidence,
)
from tests.unit.features.evaluation._preregistration_payload import valid_payload

_PLAN = Preregistration.from_mapping(valid_payload())
_CANDIDATE = _PLAN.candidate
_NAIVE = _PLAN.comparator_tiers.naive
_STRONG_STAT = _PLAN.comparator_tiers.strong_statistical
_ML = _PLAN.comparator_tiers.ml
_T = 250


def _tail(level: float, violations: int, observed: int, degeneracy: float = 0.0) -> TailEvidence:
    return TailEvidence(
        level=level,
        seeds=tuple(SeedTailCounts(seed, violations, observed, degeneracy) for seed in (1, 2)),
    )


def _calibration(sample: str, horizon: int, violations: int) -> CalibrationEvidence:
    lower, upper = _tail(0.1, violations, 1000), _tail(0.9, violations, 1000)
    dgt: tuple[DgtTailEvidence, ...] = ()
    if horizon > 1 and sample == "model_full":
        dgt = tuple(
            DgtTailEvidence(
                k, horizon, _tail(0.1, violations // 10, 100), _tail(0.9, violations // 10, 100)
            )
            for k in range(horizon)
        )
    return CalibrationEvidence(sample=sample, lower=lower, upper=upper, dgt=dgt)


def _evidence(  # noqa: PLR0913 — um parâmetro por eixo da evidência (keyword-only)
    horizon: int,
    *,
    gate_passes: bool = True,
    rejected: Iterable[str] = (),
    included: Iterable[str] = (),
    pinball: dict[str, float] | None = None,
    comparators_calibration: tuple[ComparatorCalibration, ...] = (),
) -> HorizonEvidence:
    rejected, included = set(rejected), set(included)
    violations = 100 if gate_passes else 200
    dm = tuple(
        DmEvidence(
            comparator=model,
            estimator=estimator,
            n_points=_T,
            mean_differential=-0.01 if model in rejected else 0.0,
            statistic=-3.0 if model in rejected else 0.5,
            adjusted_p_value=0.001 if model in rejected else 0.6,
            rejected=model in rejected,
            fallback_applied=False,
        )
        for model in _PLAN.comparators
        for estimator in (DmVarianceEstimator.RECTANGULAR, DmVarianceEstimator.BARTLETT)
    )
    mcs = tuple(
        McsEvidence(scheme, model, included=model in included)
        for scheme in (BootstrapScheme.STATIONARY, BootstrapScheme.MOVING_BLOCK)
        for model in _PLAN.models
    )
    return HorizonEvidence(
        horizon=horizon,
        common_points=_T,
        gate=_calibration("model_full", horizon, violations),
        common=_calibration("common", horizon, violations),
        comparators_calibration=comparators_calibration,
        mean_pinball=pinball
        or {model: (0.1 if model == _CANDIDATE else 0.2) for model in _PLAN.models},
        dm=dm,
        mcs=mcs,
    )


def _decide(*evidence: HorizonEvidence) -> ScorecardVerdict:
    if len(evidence) == 1:
        evidence = (evidence[0], _evidence(7 if evidence[0].horizon == 1 else 1))
    return ConfirmatoryScorecard.decide(_PLAN, evidence)


def _h1(**kwargs: object) -> HorizonVerdict:
    return _decide(_evidence(1, **kwargs)).horizons[0]  # type: ignore[arg-type]


_ALL = _PLAN.comparators


@pytest.mark.unit
def test_outcome_not_applicable() -> None:
    verdict = _h1(gate_passes=False, rejected=_NAIVE, included={_CANDIDATE})

    assert verdict.h1.passed is False
    assert verdict.h2 is H2Outcome.NOT_APPLICABLE


@pytest.mark.unit
def test_outcome_no_skill_over_naive() -> None:
    verdict = _h1(rejected=_NAIVE[:1] + _PLAN.strong, included={_CANDIDATE})

    assert verdict.beats_naive is False
    assert verdict.h2 is H2Outcome.NO_SKILL_OVER_NAIVE
    assert verdict.primary_winner is None


@pytest.mark.unit
def test_outcome_beats_naive_only() -> None:
    verdict = _h1(rejected=_NAIVE + _STRONG_STAT[:1])

    assert (verdict.beats_naive, verdict.in_mcs, verdict.beats_or_ties_strong) == (
        True,
        False,
        False,
    )
    assert verdict.h2 is H2Outcome.BEATS_NAIVE_ONLY
    assert verdict.primary_winner is None


@pytest.mark.unit
def test_outcome_beats_naive_ties_strong() -> None:
    verdict = _h1(rejected=_NAIVE, included={_CANDIDATE, *_PLAN.strong})

    assert verdict.in_mcs is True
    assert verdict.h2 is H2Outcome.BEATS_NAIVE_TIES_STRONG
    assert verdict.primary_winner == _CANDIDATE


@pytest.mark.unit
def test_outcome_beats_naive_and_strong() -> None:
    verdict = _h1(rejected=_ALL, included={_CANDIDATE})

    assert verdict.h2 is H2Outcome.BEATS_NAIVE_AND_STRONG
    assert verdict.primary_winner == _CANDIDATE


@pytest.mark.unit
@pytest.mark.parametrize(
    ("gate_passes", "rejected", "included", "winner"),
    [
        pytest.param(True, _NAIVE, {_CANDIDATE}, True, id="h1-i-ii"),
        pytest.param(False, _NAIVE, {_CANDIDATE}, False, id="no-h1"),
        pytest.param(True, _NAIVE[:1], {_CANDIDATE}, False, id="no-i"),
        pytest.param(True, _NAIVE, set(), False, id="no-ii"),
    ],
)
def test_winner_requires_gate_and_both(
    gate_passes: bool, rejected: tuple[str, ...], included: set[str], winner: bool
) -> None:
    verdict = _h1(gate_passes=gate_passes, rejected=rejected, included=included)

    assert verdict.primary_winner == (_CANDIDATE if winner else None)


@pytest.mark.unit
def test_h1_fail_all_rejected_no_winner() -> None:
    verdict = _h1(gate_passes=False, rejected=_ALL, included={_CANDIDATE})

    assert verdict.h2 is H2Outcome.NOT_APPLICABLE
    assert verdict.primary_winner is None
    # os fatos do gold vêm preenchidos mesmo com H1 reprovado
    assert (verdict.beats_naive, verdict.beats_or_ties_strong, verdict.in_mcs) == (
        True,
        True,
        True,
    )


@pytest.mark.unit
def test_outside_mcs_beats_strong_wins() -> None:
    verdict = _h1(rejected=_ALL, included=set(_PLAN.comparators))

    assert verdict.in_mcs is False
    assert verdict.beats_or_ties_strong is True
    assert verdict.h2 is H2Outcome.BEATS_NAIVE_AND_STRONG
    assert verdict.primary_winner == _CANDIDATE


@pytest.mark.unit
def test_ml_tier_counts_as_strong() -> None:
    verdict = _h1(rejected=_NAIVE + _STRONG_STAT, included=set(_PLAN.comparators))

    assert _ML == ("gbm_quantile",)
    assert verdict.in_mcs is False
    assert verdict.h2 is H2Outcome.BEATS_NAIVE_ONLY
    assert verdict.primary_winner is None


@pytest.mark.unit
def test_lowest_pinball_only_information() -> None:
    pinball = {model: 0.2 for model in _PLAN.models} | {"baseline_ar1": 0.05}

    verdict = _h1(rejected=_ALL, included={_CANDIDATE}, pinball=pinball)

    assert verdict.candidate_has_lowest_mean_pinball is False
    assert verdict.primary_winner == _CANDIDATE
    assert _h1(rejected=_ALL, included={_CANDIDATE}).candidate_has_lowest_mean_pinball is True


@pytest.mark.unit
def test_comparator_miscalibrated_stays_in_family() -> None:
    bad = ComparatorCalibration(
        model="baseline_zero_return",
        lower=_tail(0.1, 400, 1000, degeneracy=0.5),
        upper=_tail(0.9, 400, 1000, degeneracy=0.5),
    )
    with_bad = _h1(rejected=_NAIVE, included={_CANDIDATE}, comparators_calibration=(bad,))
    without = _h1(rejected=_NAIVE, included={_CANDIDATE})

    assert with_bad == without
    assert with_bad.beats_naive is True
    assert with_bad.primary_winner == _CANDIDATE


@pytest.mark.unit
def test_horizons_independent() -> None:
    first = ConfirmatoryScorecard.decide(
        _PLAN, [_evidence(1, rejected=_ALL, included={_CANDIDATE}), _evidence(7)]
    )
    second = ConfirmatoryScorecard.decide(
        _PLAN, [_evidence(7, gate_passes=False), _evidence(1, rejected=_ALL, included={_CANDIDATE})]
    )

    assert first.horizons[0] == second.horizons[0]
    assert first.horizons[1] != second.horizons[1]
    assert [v.horizon for v in second.horizons] == [1, 7]


@pytest.mark.unit
def test_study_success_one_horizon() -> None:
    one = ConfirmatoryScorecard.decide(_PLAN, [_evidence(1), _evidence(7, gate_passes=False)])
    none = ConfirmatoryScorecard.decide(
        _PLAN, [_evidence(1, gate_passes=False), _evidence(7, gate_passes=False)]
    )

    assert one.study_success_h1 is True
    assert none.study_success_h1 is False


@pytest.mark.unit
def test_verdict_without_profile_fields() -> None:
    horizon_fields = {field.name for field in dataclasses.fields(HorizonVerdict)}
    verdict_fields = {field.name for field in dataclasses.fields(ScorecardVerdict)}

    assert horizon_fields == {
        "horizon",
        "h1",
        "beats_naive",
        "beats_or_ties_strong",
        "in_mcs",
        "h2",
        "primary_winner",
        "candidate_has_lowest_mean_pinball",
    }
    assert verdict_fields == {"horizons", "study_success_h1"}
    types = [
        str(f.type)
        for f in (*dataclasses.fields(HorizonVerdict), *dataclasses.fields(ScorecardVerdict))
    ]
    assert not any("Profile" in t for t in types)


@pytest.mark.unit
def test_tier_reading_per_tier() -> None:
    evidence = [
        _evidence(1, rejected=_NAIVE + _ML, included={_CANDIDATE, *_STRONG_STAT}),
        _evidence(7),
    ]

    readings = ConfirmatoryScorecard.tier_readings(_PLAN, evidence)

    assert [(r.horizon, r.tier) for r in readings] == [
        (1, "naive"),
        (1, "strong_statistical"),
        (1, "ml"),
        (7, "naive"),
        (7, "strong_statistical"),
        (7, "ml"),
    ]
    first = {r.tier: r for r in readings if r.horizon == 1}
    assert (first["naive"].holm_rejects_all, first["naive"].ties_in_mcs) == (True, False)
    assert (
        first["strong_statistical"].holm_rejects_all,
        first["strong_statistical"].ties_in_mcs,
    ) == (
        False,
        True,
    )
    assert (first["ml"].holm_rejects_all, first["ml"].ties_in_mcs) == (True, False)
    assert all(r.candidate_in_mcs for r in first.values())
    assert [first[t].beats_or_ties for t in ("naive", "strong_statistical", "ml")] == [True] * 3
    out = _evidence(1, rejected=_NAIVE, included=set(_STRONG_STAT))
    outside = {
        r.tier: r
        for r in ConfirmatoryScorecard.tier_readings(_PLAN, [out, _evidence(7)])
        if r.horizon == 1
    }
    assert [outside[t].candidate_in_mcs for t in outside] == [False] * 3
    assert [outside[t].beats_or_ties for t in ("naive", "strong_statistical", "ml")] == [
        True,
        False,
        False,
    ]
    assert outside["strong_statistical"].ties_in_mcs is False
    assert first["ml"].members == _ML


@pytest.mark.unit
@pytest.mark.parametrize(
    "horizons", [pytest.param((1,), id="missing"), pytest.param((1, 7, 7), id="repeated")]
)
def test_decide_horizon_set_mismatch_raises(horizons: tuple[int, ...]) -> None:
    with pytest.raises(ValueError, match="must be the preregistered horizons"):
        ConfirmatoryScorecard.decide(_PLAN, [_evidence(h) for h in horizons])


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "key"),
    [
        ("h1_gate_form", "h1_gate.form"),
        ("verdict_form", "verdict.form"),
        ("success_criterion", "success_criterion"),
    ],
)
def test_services_check_rule_identifiers(field: str, key: str) -> None:
    plan = Preregistration.from_mapping(valid_payload())
    object.__setattr__(plan.rules, field, "tampered_v9")

    with pytest.raises(ValueError, match=f"rules.{key} must be"):
        ConfirmatoryScorecard.decide(plan, [_evidence(1), _evidence(7)])


def _flip_sensitivities(evidence: HorizonEvidence) -> HorizonEvidence:
    """Bartlett e moving-block discordando das linhas primárias em toda linha."""
    dm = tuple(
        dataclasses.replace(row, rejected=not row.rejected)
        if row.estimator is DmVarianceEstimator.BARTLETT
        else row
        for row in evidence.dm
    )
    mcs = tuple(
        dataclasses.replace(row, included=not row.included)
        if row.scheme is BootstrapScheme.MOVING_BLOCK
        else row
        for row in evidence.mcs
    )
    return dataclasses.replace(evidence, dm=dm, mcs=mcs)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rejected", "included", "outcome"),
    [
        pytest.param(_NAIVE, {_CANDIDATE}, H2Outcome.BEATS_NAIVE_TIES_STRONG, id="ties"),
        pytest.param(_ALL, set(), H2Outcome.BEATS_NAIVE_AND_STRONG, id="beats-all"),
        pytest.param((), {_CANDIDATE}, H2Outcome.NO_SKILL_OVER_NAIVE, id="no-skill"),
    ],
)
def test_outcome_follows_primary_variants(
    rejected: tuple[str, ...], included: set[str], outcome: H2Outcome
) -> None:
    """M1 (ADR 6.5.0006 item 6): o veredito lê só o DM retangular e o MCS estacionário."""
    primary = _evidence(1, rejected=rejected, included=included)
    flipped = _flip_sensitivities(primary)

    verdict = _decide(flipped).horizons[0]

    assert verdict.h2 is outcome
    assert verdict == _decide(primary).horizons[0]
    assert verdict.in_mcs is (_CANDIDATE in included)


# --- extras da auditoria de testes (rodada 1) -----------------------------------------


def _without_primary(evidence: HorizonEvidence, part: str) -> HorizonEvidence:
    if part == "dm":
        dm = tuple(
            r
            for r in evidence.dm
            if not (
                r.comparator == "baseline_ar1" and r.estimator is DmVarianceEstimator.RECTANGULAR
            )
        )
        return dataclasses.replace(evidence, dm=dm)
    if part == "mcs":
        mcs = tuple(
            r
            for r in evidence.mcs
            if not (r.model == "gbm_quantile" and r.scheme is BootstrapScheme.STATIONARY)
        )
        return dataclasses.replace(evidence, mcs=mcs)
    pinball = {m: v for m, v in evidence.mean_pinball.items() if m != "baseline_ewma_vol"}
    return dataclasses.replace(evidence, mean_pinball=pinball)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("part", "message"),
    [
        ("dm", "no primary DM row for the comparators"),
        ("mcs", "no primary MCS row for the models"),
        ("pinball", "no mean pinball for the models"),
    ],
)
def test_decide_missing_primary_rows_raises(part: str, message: str) -> None:
    """Auditoria D8: linha primária do DM/MCS ou P̄_G faltando é erro de programação (C11)."""
    evidence = _without_primary(_evidence(1, rejected=_ALL, included={_CANDIDATE}), part)

    with pytest.raises(ValueError, match=message):
        ConfirmatoryScorecard.decide(_PLAN, [evidence, _evidence(7)])


@pytest.mark.unit
def test_tier_ties_partial_membership() -> None:
    """Auditoria D10: candidato no MCS e um naive fora → sem empate com o nível naive."""
    included = {_CANDIDATE, _NAIVE[0], *_STRONG_STAT, *_ML}
    evidence = [_evidence(1, rejected=_NAIVE, included=included), _evidence(7)]

    naive = next(
        r
        for r in ConfirmatoryScorecard.tier_readings(_PLAN, evidence)
        if r.horizon == 1 and r.tier == "naive"
    )

    assert naive.candidate_in_mcs is True
    assert naive.ties_in_mcs is False
    assert naive.beats_or_ties is True
