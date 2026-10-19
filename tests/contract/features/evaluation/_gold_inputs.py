"""`GoldInputs` de teste para a suíte de contrato do `GoldBuilder` (Stage 6.4 Task 09).

Módulo privado (sem `test_`, importado absolutamente). Monta os insumos dos builders
**só com o domínio** + `FakeMcsBackend`, a partir de um cohort sintético pequeno
(`make_cohort` de `gold/_cohort_factory.py`): 2 horizontes, candidato `tft` com 2 seeds, `gbm`
e um baseline pontual `naive` (grade toda igual em todo ponto — 100 % degenerado).

- `completed_inputs()`: montagem sem achado → checks → `HorizonReports` por horizonte →
  b̂_sb por par (`FakeMcsBackend`) → MCS por (horizonte, esquema) → perfis de séries
  novas (`ProfileReports`) e MCS por bloco (`mcs_block_runs`), com as regras de perfil da
  forma da r1 → `COMPLETED`;
- `completed_inputs_r0()`: o mesmo, com `profile_parameters = None` (perfis "não
  congelados": só Monte Carlo e diferenciais, nenhuma rodada por bloco);
- `completed_inputs()` carrega também `conformal_reports` cheios (Stage 7.2): unidades
  `ok`, `undefined` (da montagem) e `error` (do port), cobertura por seed completa com
  um limite infinito, uma cobertura `undefined` e a média entre seeds com uma seed
  excluída; `completed_inputs_without_conformal()` é o mesmo refresh sem bloco
  `[conformal]` (relatórios vazios);
- `blocked_inputs()`: o mesmo cohort com um ponto interno removido (achado
  `interior_gap`) → checks → `BLOCKED`, sem relatórios.

É a mesma sequência que o use case `RefreshGold` (Task 11) orquestra; aqui só para
produzir entradas realistas e coerentes para o mapeamento dos builders.
"""

from __future__ import annotations

import dataclasses
import math
from functools import cache

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    EMPTY_CONFORMAL_REPORTS,
    EMPTY_H3_REPORTS,
    ConformalReports,
    ConformalTailRecord,
    ConformalUndefinedCoverage,
    ConformalUnitRecord,
    GoldInputs,
    GoldPartition,
    H3Reports,
    RefreshParameters,
    RefreshStatus,
    profile_settings_from,
)
from financial_forecasting.features.evaluation.application.use_cases.refresh_gold import (
    mcs_block_runs,
)
from financial_forecasting.features.evaluation.domain.services.conformal_coverage import (
    ConformalCoverage,
    ConformalCoverageReport,
)
from financial_forecasting.features.evaluation.domain.services.contribution_agreement import (
    ContributionAgreement,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.family_contribution import (
    FamilyContributionReport,
    FamilyShare,
)
from financial_forecasting.features.evaluation.domain.services.horizon_reports import (
    HorizonReports,
)
from financial_forecasting.features.evaluation.domain.services.model_confidence_set import (
    McsReport,
    ModelConfidenceSet,
)
from financial_forecasting.features.evaluation.domain.services.paired_pinball_losses import (
    paired_pinball_losses,
)
from financial_forecasting.features.evaluation.domain.services.profile_reports import (
    ProfileReports,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.alignment_check import (  # noqa: E501
    AlignmentCheck,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.degeneracy_check import (  # noqa: E501
    DegeneracyCheck,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.realized_provenance_check import (  # noqa: E501
    RealizedProvenanceCheck,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.registry import (
    QualityCheckContext,
    QualityCheckRegistry,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.statistical_preconditions_check import (  # noqa: E501
    StatisticalPreconditionsCheck,
    block_request_defect,
)
from financial_forecasting.features.evaluation.domain.services.series_assembly import (
    SeriesAssembly,
)
from financial_forecasting.features.evaluation.domain.services.vsn_summary import (
    VsnEntry,
    VsnSummaryReport,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    AssembledCohort,
    HorizonSamples,
)
from financial_forecasting.features.evaluation.domain.value_objects.block_estimate import (
    BlockEstimate,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
)
from financial_forecasting.features.evaluation.domain.value_objects.conformal_coverage_series import (  # noqa: E501
    ConformalCoverageSeries,
    ConformalPairLimits,
)
from financial_forecasting.features.evaluation.domain.value_objects.conformal_parameters import (
    ConformalParameters,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.family_loss_differentials import (  # noqa: E501
    FamilyLossDifferentials,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)
from tests.fakes.features.evaluation.fake_mcs_backend import FakeMcsBackend
from tests.unit.features.evaluation._conformal_parameters import conformal_block
from tests.unit.features.evaluation._h3_parameters import h3_parameters
from tests.unit.features.evaluation._profile_parameters import profile_parameters
from tests.unit.features.evaluation.gold._cohort_factory import (
    Cohort,
    at_point,
    drop_records,
    make_cohort,
    replace_records,
    targets_of,
)

PREREGISTRATION_REF = "prereg-test-0001"  # literal declarado até a 6.5 fornecer o hash
PARTITION = GoldPartition("AAPL", "sweep-01")
HORIZONS = (1, 2)
SEEDS = {"gbm": (None,), "naive": (None,), "tft": (1, 2)}
PARAMETERS = RefreshParameters(
    preregistration_ref=PREREGISTRATION_REF,
    degeneracy_tolerance=1e-9,
    band_levels=(0.95, 0.975),
    min_violations=5,
    candidate="tft",
    dm_alpha=0.05,
    dm_variance_estimators=(DmVarianceEstimator.RECTANGULAR, DmVarianceEstimator.BARTLETT),
    mcs_alpha=0.10,
    mcs_reps=1000,
    mcs_seed=20260929,
    mcs_schemes=(BootstrapScheme.STATIONARY, BootstrapScheme.MOVING_BLOCK),
    monte_carlo_draws=19,
    monte_carlo_seed=128,
    mcs_block_sensitivities=("h", "sqrt_T"),
    profile_parameters=profile_parameters(),  # forma da r1: todo builder de perfil com linhas
    conformal_parameters=None,
    h3_parameters=None,
)
FINGERPRINT = DatasetContentFingerprint(value="e3" * 32)
GRID_TRIMMED_PREFIX = 3
_BLOCK_LENGTH = 2.5
# Stage 7.2: o bloco do §1 com os pares da grade sintética (sem o 0,02 / 0,98)
CONFORMAL_PARAMETERS = ConformalParameters.from_mapping(
    {**conformal_block(), "pairs": [[0.1, 0.9], [0.25, 0.75]]}
)
CONFORMAL_SPLIT = "split_cqr_asymmetric_unweighted_v1"
CONFORMAL_NEXCP = "nexcp_fixed_geometric_weights_v1"
_CONFORMAL_CORRECTION = 0.001
_POINT_FORECAST = 0.001


def _cohort() -> Cohort:
    cohort = make_cohort(seeds=SEEDS, horizons=HORIZONS)
    return replace_records(
        cohort,
        lambda r: r.model == "naive",
        lambda r: dataclasses.replace(
            r, value_raw=_POINT_FORECAST, value_guardrail=_POINT_FORECAST
        ),
    )


def _assemble(cohort: Cohort) -> AssembledCohort:
    return SeriesAssembly.assemble(
        cohort.records,
        cohort.runs,
        cohort.realized,
        horizons=HORIZONS,
        window_deficits={},
        required_models=frozenset({PARAMETERS.candidate}),
    )


def _registry() -> QualityCheckRegistry:
    return QualityCheckRegistry(
        [
            AlignmentCheck(),
            StatisticalPreconditionsCheck(),
            DegeneracyCheck(),
            RealizedProvenanceCheck(),
        ]
    )


def _estimates(series: PairedLossSeries, backend: FakeMcsBackend) -> tuple[BlockEstimate, ...]:
    estimates = []
    for first, second in series.model_pairs():
        differential = series.differential(first, second)
        reason = block_request_defect(differential)
        if reason is None:
            value = backend.optimal_block_length(series=differential)
            estimates.append(
                BlockEstimate(pair=(first, second), value=value, reason=None, detail="")
            )
        else:
            estimates.append(
                BlockEstimate(pair=(first, second), value=None, reason=reason, detail=reason.value)
            )
    return tuple(estimates)


@cache
def samples_of() -> tuple[HorizonSamples, ...]:
    """As amostras por horizonte do cohort de `completed_inputs()` (para recalcular perfis)."""
    return _assemble(_cohort()).horizons


@cache
def completed_inputs() -> GoldInputs:
    """`GoldInputs` de um refresh `COMPLETED` (sem achado, pré-condições ok), forma da r1.

    Com os blocos `[conformal]` e `[h3]` e os relatórios cheios (Stages 7.2 e 7.3).
    """
    parameters = dataclasses.replace(
        PARAMETERS, conformal_parameters=CONFORMAL_PARAMETERS, h3_parameters=h3_parameters()
    )
    inputs = _completed(parameters)
    return dataclasses.replace(
        inputs, conformal_reports=conformal_reports_of(inputs), h3_reports=h3_reports_sample()
    )


@cache
def completed_inputs_without_h3() -> GoldInputs:
    """O refresh `COMPLETED` com `[conformal]` e sem `[h3]`: relatórios de H3 vazios."""
    parameters = dataclasses.replace(PARAMETERS, conformal_parameters=CONFORMAL_PARAMETERS)
    inputs = _completed(parameters)
    return dataclasses.replace(inputs, conformal_reports=conformal_reports_of(inputs))


@cache
def completed_inputs_without_conformal() -> GoldInputs:
    """O mesmo refresh `COMPLETED` sem bloco `[conformal]`: relatórios conformais vazios."""
    return _completed(PARAMETERS)


@cache
def completed_inputs_r0() -> GoldInputs:
    """O mesmo refresh `COMPLETED` sem regras de perfil (forma do r0)."""
    return _completed(dataclasses.replace(PARAMETERS, profile_parameters=None))


def _completed(parameters: RefreshParameters) -> GoldInputs:
    cohort = _cohort()
    assembled = _assemble(cohort)
    assert assembled.alignment.findings == (), assembled.alignment.findings
    backend = FakeMcsBackend(block_length=_BLOCK_LENGTH)
    paired = {
        samples.horizon: paired_pinball_losses(
            {model: samples.common[model] for model in samples.models}
        )
        for samples in assembled.horizons
    }
    estimates = {h: _estimates(series, backend) for h, series in paired.items()}
    context = QualityCheckContext(
        assembled=assembled,
        paired=paired,
        block_estimates=estimates,
        tolerance=PARAMETERS.degeneracy_tolerance,
        dataset_fingerprint=FINGERPRINT,
        grid_trimmed_prefix=GRID_TRIMMED_PREFIX,
        realized=cohort.realized,
    )
    results = _registry().run(context)
    assert not QualityCheckRegistry.is_blocking(results), results
    reports = tuple(
        HorizonReports.evaluate(
            samples,
            paired=paired[samples.horizon],
            tolerance=PARAMETERS.degeneracy_tolerance,
            band_levels=PARAMETERS.band_levels,
            min_violations=PARAMETERS.min_violations,
            candidate=PARAMETERS.candidate,
            dm_alpha=PARAMETERS.dm_alpha,
            dm_variance_estimators=PARAMETERS.dm_variance_estimators,
        )
        for samples in assembled.horizons
    )
    mcs: list[McsReport] = []
    for horizon, series in paired.items():
        block = ModelConfidenceSet.block_length(
            series,
            block_estimates={e.pair: e.value for e in estimates[horizon] if e.value is not None},
        )
        for scheme in PARAMETERS.mcs_schemes:
            indices = backend.bootstrap_indices(
                n_obs=series.n_points,
                block_size=block,
                reps=PARAMETERS.mcs_reps,
                seed=PARAMETERS.mcs_seed,
                scheme=scheme,
            )
            mcs.append(
                ModelConfidenceSet.evaluate(series, bootstrap=indices, alpha=PARAMETERS.mcs_alpha)
            )
    settings = profile_settings_from(parameters)
    profiles = tuple(
        ProfileReports.evaluate(
            samples, horizon_report=report, paired=paired[samples.horizon], settings=settings
        )
        for samples, report in zip(assembled.horizons, reports, strict=True)
    )
    return GoldInputs(
        partition=PARTITION,
        parameters=parameters,
        status=RefreshStatus.COMPLETED,
        check_results=results,
        horizon_reports=reports,
        mcs_reports=tuple(mcs),
        block_estimates=estimates,
        profile_reports=profiles,
        mcs_block_reports=mcs_block_runs(paired, parameters, backend),
        conformal_reports=EMPTY_CONFORMAL_REPORTS,
        h3_reports=EMPTY_H3_REPORTS,
    )


@cache
def blocked_inputs() -> GoldInputs:
    """`GoldInputs` de um refresh `BLOCKED` (achado de alinhamento, sem relatórios)."""
    cohort = _cohort()
    gap = targets_of(cohort, "tft", 1, 1)[10]
    cohort = drop_records(cohort, at_point("tft", 1, 1, gap))
    assembled = _assemble(cohort)
    context = QualityCheckContext(
        assembled=assembled,
        paired={},
        block_estimates={},
        tolerance=PARAMETERS.degeneracy_tolerance,
        dataset_fingerprint=FINGERPRINT,
        grid_trimmed_prefix=GRID_TRIMMED_PREFIX,
        realized=cohort.realized,
    )
    results = _registry().run(context)
    assert QualityCheckRegistry.is_blocking(results), results
    return GoldInputs(
        partition=PARTITION,
        parameters=PARAMETERS,
        status=RefreshStatus.BLOCKED,
        check_results=results,
        horizon_reports=(),
        mcs_reports=(),
        block_estimates={},
        profile_reports=(),
        mcs_block_reports=(),
        conformal_reports=EMPTY_CONFORMAL_REPORTS,
        h3_reports=EMPTY_H3_REPORTS,
    )


# --- Stage 7.2: relatórios conformais de teste ------------------------------------------


def _tail(
    tail: str, level: float, *, n: int, correction: float, split: bool
) -> ConformalTailRecord:
    infinite = correction == float("inf")
    beta = (n - 1, 2, 0.8, 0.1) if split and not infinite else (None, None, None, None)
    return ConformalTailRecord(
        tail=tail,
        level=level,
        n=n,
        rank=n - 1 if split else None,
        correction=correction,
        infinite=infinite,
        beta_a=beta[0],
        beta_b=beta[1],
        beta_mean=beta[2],
        beta_sd=beta[3],
    )


def _null_tails(pair: tuple[float, float]) -> tuple[ConformalTailRecord, ...]:
    return tuple(
        ConformalTailRecord(
            tail=tail,
            level=level,
            n=None,
            rank=None,
            correction=None,
            infinite=None,
            beta_a=None,
            beta_b=None,
            beta_mean=None,
            beta_sd=None,
        )
        for tail, level in zip(("lower", "upper"), pair, strict=True)
    )


def _lower_correction(seed: int, horizon: int, pair: tuple[float, float], variant: str) -> float:
    """O NexCP da seed 1, h = 1, par (0,1, 0,9) tem Q_lo = +inf (massa insuficiente, C2)."""
    if (seed, horizon, pair, variant) == (1, 1, (0.1, 0.9), CONFORMAL_NEXCP):
        return float("inf")
    return _CONFORMAL_CORRECTION


def _pair_limits(
    native: CoverageSeries,
    pairs: tuple[tuple[float, float], ...],
    *,
    seed: int,
    horizon: int,
    variant: str,
) -> list[ConformalPairLimits]:
    limits = []
    for pair in pairs:
        k_lo = native.levels.index(pair[0])
        k_hi = native.levels.index(pair[1])
        q_lo = _lower_correction(seed, horizon, pair, variant)
        limits.append(
            ConformalPairLimits(
                pair[0],
                pair[1],
                tuple(native.scored_values(i)[k_lo] - q_lo for i in range(native.n_points)),
                tuple(
                    native.scored_values(i)[k_hi] + _CONFORMAL_CORRECTION
                    for i in range(native.n_points)
                ),
            )
        )
    return limits


_CROSS_EVERY = 3
_UNNEST_EVERY = 4


def _varied(limits: list[ConformalPairLimits]) -> list[ConformalPairLimits]:
    """Seed 2, h = 1: cruza o par de fora em i % 3 == 0 e desaninha o de dentro em i % 4 == 1."""
    outer, inner = limits
    outer_lower = tuple(
        up + 0.01 if i % _CROSS_EVERY == 0 else low
        for i, (low, up) in enumerate(zip(outer.lower, outer.upper, strict=True))
    )
    inner_lower = tuple(
        outer.lower[i] - 0.05 if i % _UNNEST_EVERY == 1 else low
        for i, low in enumerate(inner.lower)
    )
    return [
        dataclasses.replace(outer, lower=outer_lower),
        dataclasses.replace(inner, lower=inner_lower),
    ]


def conformal_reports_of(inputs: GoldInputs) -> ConformalReports:
    """Relatórios conformais coerentes com o cohort de `completed_inputs()`.

    Unidades por (fold 0/1, seed 1/2, h) x par x variante. A seed 2 em h = 2 tem uma
    unidade `error` do port (fold 1, variante sem pesos) e uma unidade `undefined` da
    montagem (fold cru `"x"`), então a cobertura dela nos dois variantes é `undefined`
    e a média de h = 2 usa só a seed 1. Limites = quantis nativos corrigidos.

    Em h = 1 as duas seeds entram na média com n, cruzamento e aninhamento DIFERENTES
    (Checkpoint C das Tasks 16-19, C4-1): a série da seed 2 tem o 1º ponto degenerado
    (a grade do `naive`, constante), cruza o par (0,1; 0,9) em todo ponto múltiplo de 3
    e tira o par (0,25; 0,75) de dentro do de fora nos pontos ≡ 1 (mod 4).
    """
    parameters = inputs.parameters.conformal_parameters
    assert parameters is not None
    pairs = parameters.pairs
    variants = (CONFORMAL_SPLIT, CONFORMAL_NEXCP)
    units: list[ConformalUnitRecord] = []
    coverage: list[ConformalCoverageReport] = []
    undefined: list[ConformalUndefinedCoverage] = []
    natives = {
        (seed, samples.horizon): series
        for samples in samples_of()
        for seed, series in zip(samples.seeds["tft"], samples.full["tft"], strict=True)
        if seed is not None
    }
    broken = (2, 2)
    varied = (2, 1)
    naive_first = {
        samples.horizon: samples.full["naive"][0].forecasts[0] for samples in samples_of()
    }
    for (seed, horizon), native in sorted(natives.items()):
        for fold in (0, 1):
            for pair in pairs:
                for variant in variants:
                    rho = parameters.nexcp_rho if variant == CONFORMAL_NEXCP else None
                    if (seed, horizon) == broken and fold == 1 and variant == CONFORMAL_SPLIT:
                        units.append(
                            ConformalUnitRecord(
                                fold_index=1,
                                fold_raw="1",
                                seed=seed,
                                horizon=horizon,
                                lower_level=pair[0],
                                upper_level=pair[1],
                                variant=variant,
                                rho=rho,
                                status="error",
                                reason="points[3].target_timestamp: not before test_start",
                                tails=_null_tails(pair),
                            )
                        )
                        continue
                    split = variant == CONFORMAL_SPLIT
                    units.append(
                        ConformalUnitRecord(
                            fold_index=fold,
                            fold_raw=str(fold),
                            seed=seed,
                            horizon=horizon,
                            lower_level=pair[0],
                            upper_level=pair[1],
                            variant=variant,
                            rho=rho,
                            status="ok",
                            reason=None,
                            tails=(
                                _tail(
                                    "lower",
                                    pair[0],
                                    n=10,
                                    split=split,
                                    correction=_lower_correction(seed, horizon, pair, variant),
                                ),
                                _tail(
                                    "upper",
                                    pair[1],
                                    n=10,
                                    split=split,
                                    correction=_CONFORMAL_CORRECTION,
                                ),
                            ),
                        )
                    )
        if (seed, horizon) == broken:
            for pair in pairs:
                for variant in variants:
                    units.append(
                        ConformalUnitRecord(
                            fold_index=None,
                            fold_raw="x",
                            seed=seed,
                            horizon=horizon,
                            lower_level=pair[0],
                            upper_level=pair[1],
                            variant=variant,
                            rho=parameters.nexcp_rho if variant == CONFORMAL_NEXCP else None,
                            status="undefined",
                            reason="fold 'x' is not an integer",
                            tails=_null_tails(pair),
                        )
                    )
            for variant in variants:
                undefined.append(
                    ConformalUndefinedCoverage(
                        seed=seed,
                        horizon=horizon,
                        variant=variant,
                        reason="fold 'x' is not an integer",
                        n_points=native.n_points,
                    )
                )
            continue
        series = native
        if (seed, horizon) == varied:
            series = dataclasses.replace(
                native, forecasts=(naive_first[horizon], *native.forecasts[1:])
            )
        for variant in variants:
            limits = _pair_limits(series, pairs, seed=seed, horizon=horizon, variant=variant)
            if (seed, horizon) == varied:
                limits = _varied(limits)
            coverage.append(
                ConformalCoverage.evaluate(
                    ConformalCoverageSeries(
                        seed=seed, native=series, variant=variant, pairs=tuple(limits)
                    ),
                    tolerance=inputs.parameters.degeneracy_tolerance,
                    band_levels=inputs.parameters.band_levels,
                )
            )
    seed_means = tuple(
        ConformalCoverage.seed_mean(
            [r for r in coverage if (r.horizon, r.variant) == (horizon, variant)],
            horizon=horizon,
            variant=variant,
            expected_seeds=(1, 2),
            band_levels=inputs.parameters.band_levels,
        )
        for horizon in HORIZONS
        for variant in variants
    )
    return ConformalReports(
        units=tuple(units),
        coverage=tuple(coverage),
        undefined_coverage=tuple(undefined),
        seed_means=seed_means,
    )


# --- Stage 7.3: relatórios de H3 de teste ------------------------------------------------


_H3_ORDER = ("price", "technical", "sentiment", "fundamental")


def h3_reports_sample() -> H3Reports:
    """Relatórios de H3 sintéticos: permutação `ok` (uma família `undefined`, um limite
    infinito), LOCO `undefined`, a leitura `undefined` e um resumo da VSN."""
    shares = (
        FamilyShare("price", 0.4, 0.2, -0.2, -0.3, -0.1, -1, True, "ok", None),
        FamilyShare(
            "technical",
            0.3,
            0.3,
            0.0,
            0.0,
            0.0,
            0,
            None,
            "undefined",
            "a bound of the interval is exactly 0",
        ),
        FamilyShare("sentiment", 0.2, 0.3, 0.1, -math.inf, 0.5, 1, False, "ok", None),
        FamilyShare("fundamental", 0.1, 0.2, 0.1, -0.2, math.inf, 1, False, "ok", None),
    )
    # coerentes com as participações (C7-12): I(1) = 0,04/0,03/0,02/0,01 -> 0,4/0,3/0,2/0,1;
    # I(7) = 0,02/0,03/0,03/0,02 -> 0,2/0,3/0,3/0,2
    importance = {
        **{(f, 1): i for f, i in zip(_H3_ORDER, (0.04, 0.03, 0.02, 0.01), strict=True)},
        **{(f, 7): i for f, i in zip(_H3_ORDER, (0.02, 0.03, 0.03, 0.02), strict=True)},
    }
    permutation = FamilyContributionReport(
        method="permutation",
        importance=importance,
        shares=shares,
        level=0.9875,
        nonpositive_replicas={1: 3, 7: 0},
        status="ok",
        reason=None,
        heterogeneous=True,
    )
    reason = "the point total of importances is <= 0 at h=1 or h=7 (H3-NEG)"
    ablation = FamilyContributionReport(
        method="loco",
        importance={key: -0.01 for key in importance},
        shares=tuple(
            FamilyShare(s.family, None, None, None, None, None, None, None, "undefined", reason)
            for s in shares
        ),
        level=0.9875,
        nonpositive_replicas={1: 0, 7: 0},
        status="undefined",
        reason=reason,
        heterogeneous=None,
    )
    vsn = VsnSummaryReport(
        entries=(
            VsnEntry("variable", "log_return", "price", 0.1, 0.2, 0.3, 40),
            VsnEntry("variable", "relative_time_idx", "none", 0.0, 0.05, 0.1, 40),
            VsnEntry("family", "price", "price", 0.2, 0.3, 0.4, 40),
        ),
        status="ok",
        reason=None,
    )
    families = ("price", "technical", "sentiment", "fundamental")
    differentials = FamilyLossDifferentials(
        method="permutation",
        families=families,
        horizons=(1, 7),
        decision_timestamps=H3_DECISIONS,
        differentials={(f, h): (0.01, 0.02, 0.0) for f in families for h in (1, 7)},
        seed_importances={(f, h, s): 0.01 * s for f in families for h in (1, 7) for s in (1, 2)},
        permutation_importances={
            (f, h, k): 0.001 * k for f in families for h in (1, 7) for k in (1, 2)
        },
    )
    return H3Reports(
        permutation=permutation,
        ablation=ablation,
        permutation_differentials=differentials,
        ablation_differentials=None,
        reading=ContributionAgreement.read(permutation, ablation),
        vsn=vsn,
        block_length=7,
        max_block_estimate=5.25,
        n_points=len(H3_DECISIONS),
    )


H3_DECISIONS = (
    "2024-01-02T00:00:00+00:00",
    "2024-01-03T00:00:00+00:00",
    "2024-01-04T00:00:00+00:00",
)
