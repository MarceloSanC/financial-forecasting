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
from financial_forecasting.features.evaluation.domain.services.differential_stationarity import (
    DifferentialStationarity,
)
from financial_forecasting.features.evaluation.domain.services.dm_profiles import (
    ERROR,
    DmProfiles,
)
from financial_forecasting.features.evaluation.domain.services.horizon_reports import (
    HorizonReport,
    HorizonReports,
    SampleKind,
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


def _settings(
    parameters: ProfileParameters | None = _PARAMETERS, **changes: object
) -> ProfileSettings:
    fields: dict[str, object] = {
        "candidate": _CAND,
        "alpha": 0.05,
        "variance_estimator": _RECT,
        "min_violations": _MIN_VIOLATIONS,
        "tolerance": _TOLERANCE,
        "draws": _DRAWS,
        "seed": _MC_SEED,
        "profile_parameters": parameters,
    }
    fields.update(changes)
    return ProfileSettings(**fields)  # type: ignore[arg-type]


def _reports_of(
    samples: HorizonSamples, tolerance: float = _TOLERANCE
) -> tuple[HorizonSamples, HorizonReport, PairedLossSeries]:
    paired = paired_pinball_losses({m: samples.common[m] for m in samples.models})
    report = HorizonReports.evaluate(
        samples,
        paired=paired,
        tolerance=tolerance,
        band_levels=(0.95,),
        min_violations=_MIN_VIOLATIONS,
        candidate=_CAND,
        dm_alpha=0.05,
        dm_variance_estimators=(_RECT,),
    )
    return samples, report, paired


def _inputs(
    cohort: Cohort | None = None,
    *,
    prefixes: dict[str, int] | None = None,
    tolerance: float = _TOLERANCE,
) -> list[tuple[HorizonSamples, HorizonReport, PairedLossSeries]]:
    cohort = cohort or make_cohort(prefixes=prefixes)
    assembled = SeriesAssembly.assemble(
        cohort.records,
        cohort.runs,
        cohort.realized,
        horizons=(1, 2),
        window_deficits=dict(prefixes or {}),
        required_models=frozenset({_CAND}),
    )
    assert assembled.alignment.findings == ()
    return [_reports_of(samples, tolerance) for samples in assembled.horizons]


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


# --- Checkpoint C bloco 4 -------------------------------------------------------------


@pytest.mark.unit
def test_settings_reach_every_service() -> None:
    """F4, M-3: estimador, alpha, mínimo de violações e tolerância chegam aos serviços."""
    tolerance = 1e-9
    samples, horizon_report, paired = _inputs(tolerance=tolerance)[0]
    settings = _settings(
        variance_estimator=DmVarianceEstimator.BARTLETT,
        alpha=0.2,
        min_violations=3,
        tolerance=tolerance,
    )
    report = ProfileReports.evaluate(
        samples, horizon_report=horizon_report, paired=paired, settings=settings
    )
    assert report.dm_profiles == DmProfiles.evaluate(
        samples, candidate=_CAND, alpha=0.2, variance_estimator=DmVarianceEstimator.BARTLETT
    )
    assert report.stationarity is not None
    direct = DifferentialStationarity.evaluate(
        paired,
        parameters=_PARAMETERS.stationarity,
        variance_estimator=DmVarianceEstimator.BARTLETT,
    )
    assert tuple(r.report for r in report.stationarity) == direct
    series = samples.full[_CAND][0]
    expected = [
        ChristoffersenTest.monte_carlo_p_values(
            sequence, min_violations=3, draws=_DRAWS, seed=_MC_SEED
        )
        for sequence, _ in hit_sequences(series, tolerance)
    ]
    rows = [
        r.values
        for r in report.monte_carlo
        if (r.model, r.seed, r.sample) == (_CAND, 1, SampleKind.MODEL_FULL)
    ]
    assert rows == expected
    assert report.partial_degeneracy is not None
    adjacent = [
        (r.level_low, r.level_high, r.collapse_rate)
        for r in report.partial_degeneracy
        if (r.model, r.seed, r.sample) == (_CAND, 1, SampleKind.COMMON)
        and r.pair_kind is PairKind.ADJACENT
    ]
    assert adjacent == list(adjacent_collapse_rates(samples.common[_CAND][0], tolerance=tolerance))


@pytest.mark.unit
def test_every_series_and_sample_with_full_different_from_common() -> None:
    """F2: com prefixo (full != common), todas as linhas de toda (modelo, seed, amostra)
    batem com o gate e com a chamada direta do MC sobre a amostra certa."""
    samples, horizon_report, paired = _inputs(prefixes={"gbm": 2})[0]
    assert samples.full[_CAND][0].n_points > samples.n_common
    report = ProfileReports.evaluate(
        samples, horizon_report=horizon_report, paired=paired, settings=_settings()
    )
    assert report.partial_degeneracy is not None
    for series_report in horizon_report.series:
        key = (series_report.model, series_report.seed, series_report.sample)
        symmetric = [
            (r.level_low, r.level_high, r.collapse_rate)
            for r in report.partial_degeneracy
            if (r.model, r.seed, r.sample) == key and r.pair_kind is PairKind.SYMMETRIC
        ]
        assert symmetric == list(series_report.coverage.degeneracy.pair_collapse_rates)
    for model in samples.models:
        for index, seed in enumerate(samples.seeds[model]):
            common = samples.common[model][index]
            expected = [
                ChristoffersenTest.monte_carlo_p_values(
                    sequence, min_violations=_MIN_VIOLATIONS, draws=_DRAWS, seed=_MC_SEED
                )
                for sequence, _ in hit_sequences(common, _TOLERANCE)
            ]
            rows = [
                r.values
                for r in report.monte_carlo
                if (r.model, r.seed, r.sample) == (model, seed, SampleKind.COMMON)
            ]
            assert rows == expected


@pytest.mark.unit
def test_undefined_dm_rows_are_not_errors() -> None:
    """F3: `constant_differential` é indefinido legítimo, não conta em `error_units`."""
    samples, _, _ = _inputs()[0]
    twin = (samples.common[_CAND][0],)
    changed = dataclasses.replace(
        samples,
        full={**samples.full, "gbm": (samples.full[_CAND][0],)},
        common={**samples.common, "gbm": twin},
    )
    samples2, horizon_report, paired = _reports_of(changed)
    report = ProfileReports.evaluate(
        samples2, horizon_report=horizon_report, paired=paired, settings=_settings()
    )
    assert report.dm_profiles is not None
    assert any(r.undefined_reason == "constant_differential" for r in report.dm_profiles.rows)
    assert report.error_units == 0


@pytest.mark.unit
def test_paired_of_another_horizon_or_sample_is_a_call_error() -> None:
    """F7, M-4: `paired` precisa ser a série da amostra comum do horizonte."""
    (first, report, paired), (_, _, other_paired) = _inputs()
    with pytest.raises(ValueError, match="horizon"):
        ProfileReports.evaluate(
            first, horizon_report=report, paired=other_paired, settings=_settings()
        )
    shorter = paired.window(1, paired.n_points)
    with pytest.raises(ValueError, match="common sample"):
        ProfileReports.evaluate(first, horizon_report=report, paired=shorter, settings=_settings())


@pytest.mark.unit
def test_tolerance_must_be_the_gate_tolerance() -> None:
    """L-1: sequências e pares simétricos copiados são os do gate (mesma tolerância)."""
    samples, report, paired = _inputs()[0]
    with pytest.raises(ValueError, match="gate tolerance"):
        ProfileReports.evaluate(
            samples, horizon_report=report, paired=paired, settings=_settings(tolerance=1e-6)
        )


@pytest.mark.unit
def test_smoke_of_the_cost_path_has_no_error_unit() -> None:
    """Smoke do caminho da medição opt-in (Task 20), em escala pequena: 3 folds, h = 1 e 7,
    sem nenhuma unidade `error` e com Monte Carlo só em h = 1."""
    cohort = make_cohort(folds=("f0", "f1", "f2"), horizons=(1, 7), n_sessions=60)
    assembled = SeriesAssembly.assemble(
        cohort.records,
        cohort.runs,
        cohort.realized,
        horizons=(1, 7),
        window_deficits={},
        required_models=frozenset({_CAND}),
    )
    assert assembled.alignment.findings == ()
    reports = [
        ProfileReports.evaluate(samples, horizon_report=report, paired=paired, settings=_settings())
        for samples, report, paired in (_reports_of(s) for s in assembled.horizons)
    ]
    assert [r.error_units for r in reports] == [0, 0]
    assert [bool(r.monte_carlo) for r in reports] == [True, False]
    assert all(r.dm_profiles is not None and r.dm_profiles.rows for r in reports)
