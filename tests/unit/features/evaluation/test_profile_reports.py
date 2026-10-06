"""Unit test do `ProfileReports` (Stage 6.6 Task 11; CA5, CA6, I4, I7, I9).

Sobre amostras montadas pelo `SeriesAssembly` (cohort sintético da 6.4) e o
`HorizonReport` do `HorizonReports`: Monte Carlo só em h = 1, sem DGT, igual à chamada
direta e com o status repassado como está (inclusive `not_applicable` de série 100 %
degenerada e o teto de tentativas); pares simétricos copiados do gate e adjacentes de
`adjacent_collapse_rates`; sem `profile_parameters`, só Monte Carlo e diferenciais;
falha injetada em cada tipo de unidade vira `error`, contada, sem afetar as demais.
"""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.evaluation.domain.services import dm_profiles
from financial_forecasting.features.evaluation.domain.services import (
    profile_reports as module,
)
from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    ChristoffersenTest,
    MonteCarloPValues,
    MonteCarloStatus,
)
from financial_forecasting.features.evaluation.domain.services.degeneracy_gate import (
    adjacent_collapse_rates,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.dm_profiles import ERROR
from financial_forecasting.features.evaluation.domain.services.horizon_reports import (
    HorizonReport,
    HorizonReports,
    hit_sequences,
)
from financial_forecasting.features.evaluation.domain.services.paired_pinball_losses import (
    paired_pinball_losses,
)
from financial_forecasting.features.evaluation.domain.services.profile_reports import (
    HorizonProfileReport,
    PairKind,
    ProfileReports,
    ProfileSettings,
    UnitStatus,
)
from financial_forecasting.features.evaluation.domain.services.series_assembly import (
    SeriesAssembly,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    HorizonSamples,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.profile_parameters import (
    PROFILE_RULE_CATALOG,
    ProfileParameters,
    StationarityParameters,
)
from tests.unit.features.evaluation.gold._cohort_factory import (
    Cohort,
    make_cohort,
    replace_records,
)

_CAND = "tft"
_TOLERANCE = 1e-12
_DRAWS = 19
_MC_SEED = 128
_MIN_VIOLATIONS = 2
_RECT = DmVarianceEstimator.RECTANGULAR
_PARAMETERS = ProfileParameters(
    subset_multiplicity=PROFILE_RULE_CATALOG["subset_multiplicity"],
    partial_degeneracy_pairs=PROFILE_RULE_CATALOG["partial_degeneracy_pairs"],
    mcs_block_sensitivity_scheme=PROFILE_RULE_CATALOG["mcs_block_sensitivity_scheme"],
    stationarity=StationarityParameters(
        acf_max_lag=PROFILE_RULE_CATALOG["stationarity.acf_max_lag"],
        break_test=PROFILE_RULE_CATALOG["stationarity.break_test"],
        break_alpha=0.05,
    ),
)


def _settings(parameters: ProfileParameters | None = _PARAMETERS) -> ProfileSettings:
    return ProfileSettings(
        candidate=_CAND,
        alpha=0.05,
        variance_estimator=_RECT,
        min_violations=_MIN_VIOLATIONS,
        tolerance=_TOLERANCE,
        draws=_DRAWS,
        seed=_MC_SEED,
        profile_parameters=parameters,
    )


def _inputs(
    cohort: Cohort | None = None,
) -> list[tuple[HorizonSamples, HorizonReport, PairedLossSeries]]:
    cohort = cohort or make_cohort()
    assembled = SeriesAssembly.assemble(
        cohort.records,
        cohort.runs,
        cohort.realized,
        horizons=(1, 2),
        window_deficits={},
        required_models=frozenset({_CAND}),
    )
    assert assembled.alignment.findings == ()
    out = []
    for samples in assembled.horizons:
        paired = paired_pinball_losses({m: samples.common[m] for m in samples.models})
        report = HorizonReports.evaluate(
            samples,
            paired=paired,
            tolerance=_TOLERANCE,
            band_levels=(0.95,),
            min_violations=_MIN_VIOLATIONS,
            candidate=_CAND,
            dm_alpha=0.05,
            dm_variance_estimators=(_RECT,),
        )
        out.append((samples, report, paired))
    return out


def _evaluate(
    index: int = 0, parameters: ProfileParameters | None = _PARAMETERS, cohort: Cohort | None = None
) -> HorizonProfileReport:
    samples, report, paired = _inputs(cohort)[index]
    return ProfileReports.evaluate(
        samples, horizon_report=report, paired=paired, settings=_settings(parameters)
    )


@pytest.mark.unit
def test_monte_carlo_only_at_h1_and_equal_to_the_direct_call() -> None:
    samples, _, _ = _inputs()[0]
    report = _evaluate(0)
    assert _evaluate(1).monte_carlo == ()
    series = samples.full[_CAND][0]
    expected = [
        ChristoffersenTest.monte_carlo_p_values(
            sequence, min_violations=_MIN_VIOLATIONS, draws=_DRAWS, seed=_MC_SEED
        )
        for sequence, _ in hit_sequences(series, _TOLERANCE)
        if not sequence.is_dgt_subseries
    ]
    rows = [
        r
        for r in report.monte_carlo
        if r.model == _CAND and r.seed == 1 and r.sample.value == "model_full"
    ]
    assert [r.values for r in rows] == expected
    assert all(r.status is UnitStatus.COMPUTED for r in report.monte_carlo)
    n_series = sum(len(seeds) for seeds in samples.seeds.values()) * 2
    assert len(report.monte_carlo) == n_series * len(expected)


@pytest.mark.unit
def test_monte_carlo_status_of_a_fully_degenerate_series_is_kept() -> None:
    cohort = replace_records(
        make_cohort(),
        lambda r: r.model == "gbm",
        lambda r: dataclasses.replace(r, value_raw=0.001, value_guardrail=0.001),
    )
    report = _evaluate(0, cohort=cohort)
    excluded = [r for r in report.monte_carlo if r.model == "gbm" and not r.includes_degenerate]
    assert excluded
    assert all(r.values is not None for r in excluded)
    assert all(r.values.uc_status is MonteCarloStatus.NOT_APPLICABLE for r in excluded)  # type: ignore[union-attr]


@pytest.mark.unit
def test_monte_carlo_cap_status_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    real = ChristoffersenTest.monte_carlo_p_values

    def capped(sequence: object, **kwargs: object) -> MonteCarloPValues:
        found = real(sequence, **kwargs)  # type: ignore[arg-type]
        if found.uc_status is not MonteCarloStatus.APPLICABLE:
            return found
        return dataclasses.replace(
            found,
            ind_status=MonteCarloStatus.MC_CAP_REACHED,
            p_ind=None,
            p_cc=None,
            attempts=100 * found.draws,
        )

    monkeypatch.setattr(module.ChristoffersenTest, "monte_carlo_p_values", staticmethod(capped))
    report = _evaluate(0)
    statuses = {r.values.ind_status for r in report.monte_carlo if r.values is not None}
    assert MonteCarloStatus.MC_CAP_REACHED in statuses


@pytest.mark.unit
def test_without_profile_parameters_only_mc_and_differentials() -> None:
    report = _evaluate(0, parameters=None)
    assert report.monte_carlo
    assert report.differentials
    assert (report.dm_profiles, report.stationarity, report.partial_degeneracy) == (
        None,
        None,
        None,
    )
    assert report.error_units == 0


@pytest.mark.unit
def test_differentials_are_the_primary_pairs() -> None:
    samples, _, paired = _inputs()[0]
    report = _evaluate(0)
    assert [d.pair for d in report.differentials] == list(paired.model_pairs())
    first = report.differentials[0]
    assert first.values == paired.differential(*first.pair)
    assert first.folds == samples.common_folds


@pytest.mark.unit
def test_partial_degeneracy_symmetric_and_adjacent() -> None:
    samples, horizon_report, _ = _inputs()[0]
    report = _evaluate(0)
    assert report.partial_degeneracy is not None
    gate = next(
        s
        for s in horizon_report.series
        if s.model == _CAND and s.seed == 1 and s.sample.value == "common"
    )
    rows = [
        r
        for r in report.partial_degeneracy
        if (r.model, r.seed, r.sample.value) == (_CAND, 1, "common")
    ]
    symmetric = [
        (r.level_low, r.level_high, r.collapse_rate)
        for r in rows
        if r.pair_kind is PairKind.SYMMETRIC
    ]
    adjacent = [
        (r.level_low, r.level_high, r.collapse_rate)
        for r in rows
        if r.pair_kind is PairKind.ADJACENT
    ]
    assert symmetric == list(gate.coverage.degeneracy.pair_collapse_rates)
    assert adjacent == list(adjacent_collapse_rates(samples.common[_CAND][0], tolerance=_TOLERANCE))


@pytest.mark.unit
def test_stationarity_and_dm_profiles_present_with_the_rules() -> None:
    report = _evaluate(0)
    assert report.dm_profiles is not None
    assert report.stationarity is not None
    assert all(r.status is UnitStatus.COMPUTED for r in report.stationarity)
    assert report.error_units == 0


def _raise(*_args: object, **_kwargs: object) -> object:
    raise ValueError("injected")


@pytest.mark.unit
@pytest.mark.parametrize("target", ["monte_carlo", "stationarity", "adjacent", "dm"])
def test_failure_of_each_unit_type_is_isolated(
    monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    samples, horizon_report, paired = _inputs()[0]  # antes da falha: o gate não é perfil

    def evaluate() -> HorizonProfileReport:
        return ProfileReports.evaluate(
            samples, horizon_report=horizon_report, paired=paired, settings=_settings()
        )

    baseline = evaluate()
    if target == "monte_carlo":
        monkeypatch.setattr(module.ChristoffersenTest, "monte_carlo_p_values", staticmethod(_raise))
    elif target == "stationarity":
        monkeypatch.setattr(module.DifferentialStationarity, "evaluate", staticmethod(_raise))
    elif target == "adjacent":
        monkeypatch.setattr(module, "adjacent_collapse_rates", _raise)
    else:
        monkeypatch.setattr(dm_profiles.DieboldMariano, "compare", staticmethod(_raise))
    report = evaluate()
    assert report.error_units > 0
    if target == "monte_carlo":
        assert all(
            r.status is UnitStatus.ERROR and "injected" in r.detail for r in report.monte_carlo
        )
        assert report.error_units == len(report.monte_carlo)
        assert report.stationarity == baseline.stationarity
    elif target == "stationarity":
        assert report.stationarity is not None
        assert all(r.status is UnitStatus.ERROR for r in report.stationarity)
        assert report.monte_carlo == baseline.monte_carlo
    elif target == "adjacent":
        assert report.partial_degeneracy is not None
        errors = [r for r in report.partial_degeneracy if r.status is UnitStatus.ERROR]
        assert errors and all(
            r.pair_kind is PairKind.ADJACENT and r.level_low is None for r in errors
        )
        assert report.error_units == len(errors)
    else:
        assert report.dm_profiles is not None
        errors = [r for r in report.dm_profiles.rows if r.undefined_reason == ERROR]
        assert errors and all("injected" in r.detail for r in errors)
        assert report.error_units == len(errors)
        assert report.monte_carlo == baseline.monte_carlo
    assert report.differentials == baseline.differentials


@pytest.mark.unit
def test_horizon_mismatch_is_a_call_error() -> None:
    first, second = _inputs()
    with pytest.raises(ValueError, match="share the horizon"):
        ProfileReports.evaluate(
            first[0], horizon_report=second[1], paired=first[2], settings=_settings()
        )
