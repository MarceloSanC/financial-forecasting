"""Perfil do scorecard confirmatório — o que é informação, nunca veredito (Stage 6.5).

Módulo auxiliar do use case `BuildConfirmatoryScorecard` (concept 6.5 §4, D8, I8, I10,
I12; ADRs `6_5_0006` itens 4, 6, 7, `6_5_0007` itens 4-5, `6_5_0008` item 2).
`build_profile` **só copia** colunas do gold (lidas pelo schema, `col`) e chama os
donos: `H1Result` (sensibilidades e poder, já calculados pelo `H1Gate`),
`ConfirmatoryScorecard.tier_readings`, `H1Gate.tail_bands` (bandas dos comparadores
com S = 1), `dm_effect_interval` (IC do efeito a 95 %) e `SeedSpread` (descritores
entre seeds). Nada é recomputado (I8); os comparadores mal calibrados ficam nas
leituras (I10, doc §6.4); o veredito é construído antes e sem o perfil (I12).

Perfis de séries novas (Stage 6.6; ADR 6.6.0002): DM por fold/seed/τ e fração de seeds,
MCS por bloco, Monte Carlo de Christoffersen, degeneração parcial por par e o
diagnóstico de d_t (CUSUM + ACF) são **copiados** linha a linha das suas tabelas gold,
por horizonte (`gold_loss_differentials` não: é insumo de plot da 8.3). O veredito
nunca as lê (I12). `profile_states`: cada perfil declarado é `built`, ou
`not_frozen_in_revision` (um dos sete do I9 numa revisão sem `[profile_parameters]` —
estado tirado **do plano**, nunca de tabela vazia), ou `not_built_here` (o diagrama de
nitidez, 8.3); `declared_not_built` = os `not_built_here`.

As células são lidas pelos acessores tipados de `refresh_gold` (`col_int`,
`col_float`, `col_str`, ...; F6): tipo divergente do schema é corrupção nomeada
(`GoldGenerationCorruptError`).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Final

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    CalibrationSeriesProfile,
    ComparatorCalibrationProfile,
    DescriptorProfile,
    DmProfileRow,
    DmSubsetProfileRow,
    GateSensitivitiesProfile,
    HorizonProfile,
    McsBlockProfileRow,
    MonteCarloProfileRow,
    PartialDegeneracyProfileRow,
    PowerProfile,
    ProfileState,
    ScorecardProfile,
    SeedFractionProfileRow,
    StationarityProfileRow,
    TailSummaryProfile,
    TierProfile,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CALIBRATION_TABLE,
    GOLD_CHRISTOFFERSEN_MONTE_CARLO,
    GOLD_DIFFERENTIAL_ACF,
    GOLD_DIFFERENTIAL_BREAKS,
    GOLD_DM_PROFILES,
    GOLD_DM_SEED_FRACTION,
    GOLD_MCS_BLOCK_SENSITIVITY,
    GOLD_METRICS_BY_RUN,
    GOLD_PARTIAL_DEGENERACY,
    GoldTableSchema,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    Row,
    col_bool,
    col_bool_or_none,
    col_float,
    col_float_or_none,
    col_int,
    col_int_or_none,
    col_str,
    col_str_or_none,
)
from financial_forecasting.features.evaluation.application.use_cases.scorecard_evidence import (
    LOWER_TAIL,
    UPPER_TAIL,
)
from financial_forecasting.features.evaluation.domain.services.confirmatory_scorecard import (
    ConfirmatoryScorecard,
    HorizonVerdict,
    ScorecardVerdict,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
    dm_effect_interval,
)
from financial_forecasting.features.evaluation.domain.services.h1_gate import H1Gate
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.features.evaluation.domain.value_objects.scorecard_evidence import (
    GATE_SAMPLE,
    HorizonEvidence,
    SeedSpread,
)

EFFECT_LEVEL: Final = 0.95
"""Nível do IC do efeito do DM (doc §6.8: "efeito + IC", t_{T-1, 0,975})."""

NOT_BUILT_HERE: Final = frozenset({"sharpness_diagram"})
"""Perfis declaráveis construídos fora do scorecard (o diagrama de nitidez: Stage 8.3)."""

FROZEN_RULE_PROFILES: Final = frozenset(
    {
        "dm_per_fold",
        "dm_per_seed",
        "dm_per_tau",
        "mcs_block_h",
        "mcs_block_sqrt_t",
        "partial_degeneracy_per_pair",
        "dm_differential_stationarity",
    }
)
"""Os sete perfis que só rodam com `[profile_parameters]` na revisão (concept 6.6 I9)."""

_INDEPENDENCE_APPLICABLE = "applicable"


def _gate_sensitivities(verdict: HorizonVerdict) -> GateSensitivitiesProfile:
    h1 = verdict.h1
    return GateSensitivitiesProfile(
        lr_uc_statistic=None if h1.lr_uc is None else h1.lr_uc.statistic,
        lr_uc_p_value=None if h1.lr_uc is None else h1.lr_uc.p_value,
        lr_uc_rejected=None if h1.lr_uc is None else h1.lr_uc.rejected,
        dgt_band_level=None if h1.dgt is None else h1.dgt.band_level,
        dgt_passed=None if h1.dgt is None else h1.dgt.passed,
        common_sample_passed=h1.common_sample_passed,
        mean_of_seed_rates=h1.mean_of_seed_rates,
        divergences=h1.divergences,
    )


def _dm_rows(evidence: HorizonEvidence) -> tuple[DmProfileRow, ...]:
    return tuple(
        DmProfileRow(
            comparator=row.comparator,
            estimator=row.estimator.value,
            n_points=row.n_points,
            mean_differential=row.mean_differential,
            statistic=row.statistic,
            adjusted_p_value=row.adjusted_p_value,
            rejected=row.rejected,
            fallback_applied=row.fallback_applied,
            effect_interval=dm_effect_interval(
                mean_differential=row.mean_differential,
                statistic=row.statistic,
                n_points=row.n_points,
                level=EFFECT_LEVEL,
            ),
        )
        for row in evidence.dm
    )


def _bartlett_divergences(prereg: Preregistration, evidence: HorizonEvidence) -> tuple[str, ...]:
    rejected = {(row.comparator, row.estimator): row.rejected for row in evidence.dm}
    primary = prereg.dm.primary_estimator
    return tuple(
        comparator
        for comparator in prereg.comparators
        if (comparator, DmVarianceEstimator.BARTLETT) in rejected
        and rejected[comparator, DmVarianceEstimator.BARTLETT] != rejected[comparator, primary]
    )


def _moving_block_divergence(prereg: Preregistration, evidence: HorizonEvidence) -> bool:
    included = {(row.scheme, row.model): row.included for row in evidence.mcs}
    key = (BootstrapScheme.MOVING_BLOCK, prereg.candidate)
    if key not in included:
        return False
    return included[key] != included[prereg.mcs.primary_scheme, prereg.candidate]


def _comparators(
    prereg: Preregistration, evidence: HorizonEvidence
) -> tuple[ComparatorCalibrationProfile, ...]:
    gate = prereg.h1_gate
    profiles: list[ComparatorCalibrationProfile] = []
    for calibration in evidence.comparators_calibration:
        lower, upper = H1Gate.tail_bands(
            gate,
            horizon=evidence.horizon,
            lower=calibration.lower,
            upper=calibration.upper,
            band_level=gate.gate_band_level,
        )
        degeneracy = calibration.lower.mean_degeneracy
        profiles.append(
            ComparatorCalibrationProfile(
                model=calibration.model,
                lower_contains_nominal=lower.contains_nominal,
                upper_contains_nominal=upper.contains_nominal,
                mean_degeneracy_rate=degeneracy,
                degeneracy_above_threshold=degeneracy > gate.degeneracy_threshold,
            )
        )
    return tuple(profiles)


def _mean(values: Sequence[float]) -> float:
    return SeedSpread.of(values).mean


def _fraction(flags: Sequence[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


_CalibrationKey = tuple[str, str, str, float, float | None, bool, int | None, int | None]


def _calibration_key(row: Row) -> _CalibrationKey:
    schema = GOLD_CALIBRATION_TABLE
    return (
        col_str(row, schema, "model"),
        col_str(row, schema, "sample"),
        col_str(row, schema, "kind"),
        col_float(row, schema, "level_low"),
        col_float_or_none(row, schema, "level_high"),
        col_bool(row, schema, "includes_degenerate"),
        col_int_or_none(row, schema, "dgt_offset"),
        col_int_or_none(row, schema, "dgt_step"),
    )


def _calibration_series(
    prereg: Preregistration, rows: Sequence[Row], horizon: int
) -> tuple[CalibrationSeriesProfile, ...]:
    schema = GOLD_CALIBRATION_TABLE
    groups: dict[_CalibrationKey, list[Row]] = defaultdict(list)
    for row in rows:
        if col_int(row, schema, "horizon") != horizon:
            continue
        if col_float(row, schema, "band_level") != prereg.h1_gate.profile_band_level:
            continue
        groups[_calibration_key(row)].append(row)
    alpha = prereg.h1_gate.sensitivity_alpha
    series: list[CalibrationSeriesProfile] = []
    for key, members in groups.items():
        contains = [col_bool_or_none(r, schema, "wilson_contains_nominal") for r in members]
        applicable = [
            r
            for r in members
            if col_str(r, schema, "independence_status") == _INDEPENDENCE_APPLICABLE
        ]
        series.append(
            CalibrationSeriesProfile(
                model=key[0],
                sample=key[1],
                kind=key[2],
                level_low=key[3],
                level_high=key[4],
                includes_degenerate=key[5],
                dgt_offset=key[6],
                dgt_step=key[7],
                n_seeds=len(members),
                mean_violations=_mean([col_int(r, schema, "n_violations") for r in members]),
                mean_observed=_mean([col_int(r, schema, "n_observed") for r in members]),
                fraction_contains_nominal=_fraction([c is True for c in contains if c is not None]),
                fraction_ind_rejected=_fraction(
                    [col_float(r, schema, "p_ind") < alpha for r in applicable]
                ),
                fraction_cc_rejected=_fraction(
                    [col_float(r, schema, "p_cc") < alpha for r in applicable]
                ),
                n_independence_not_applicable=len(members) - len(applicable),
            )
        )
    return tuple(series)


def _without_gaps(
    prereg: Preregistration, rows: Sequence[Row], horizon: int
) -> tuple[TailSummaryProfile, ...]:
    schema = GOLD_CALIBRATION_TABLE
    gate = prereg.h1_gate
    summaries: list[TailSummaryProfile] = []
    for kind, level in ((LOWER_TAIL, gate.lower_level), (UPPER_TAIL, gate.upper_level)):
        members = [
            r
            for r in rows
            if col_str(r, schema, "model") == prereg.candidate
            and col_int(r, schema, "horizon") == horizon
            and col_str(r, schema, "sample") == GATE_SAMPLE
            and col_str(r, schema, "kind") == kind
            and col_float(r, schema, "level_low") == level
            and col_bool(r, schema, "includes_degenerate")
            and col_int_or_none(r, schema, "dgt_offset") is None
            and col_float(r, schema, "band_level") == gate.gate_band_level
        ]
        if members:
            summaries.append(
                TailSummaryProfile(
                    kind=kind,
                    level=level,
                    mean_violations=_mean([col_int(r, schema, "n_violations") for r in members]),
                    mean_observed=_mean([col_int(r, schema, "n_observed") for r in members]),
                )
            )
    return tuple(summaries)


def _descriptors(rows: Sequence[Row], horizon: int) -> tuple[DescriptorProfile, ...]:
    schema = GOLD_METRICS_BY_RUN
    groups: dict[tuple[str, str, str, float | None, float | None], list[float]] = defaultdict(list)
    for row in rows:
        if col_int(row, schema, "horizon") != horizon:
            continue
        key = (
            col_str(row, schema, "model"),
            col_str(row, schema, "sample"),
            col_str(row, schema, "metric"),
            col_float_or_none(row, schema, "level_low"),
            col_float_or_none(row, schema, "level_high"),
        )
        groups[key].append(col_float(row, schema, "value"))
    descriptors: list[DescriptorProfile] = []
    for key, values in groups.items():
        spread = SeedSpread.of(values)
        descriptors.append(
            DescriptorProfile(
                model=key[0],
                sample=key[1],
                metric=key[2],
                level_low=key[3],
                level_high=key[4],
                mean=spread.mean,
                minimum=spread.minimum,
                maximum=spread.maximum,
                n_seeds=spread.n_seeds,
            )
        )
    return tuple(descriptors)


def _at(rows: Sequence[Row], schema: GoldTableSchema, horizon: int) -> list[Row]:
    return [row for row in rows if col_int(row, schema, "horizon") == horizon]


def _dm_subsets(rows: Sequence[Row], horizon: int) -> tuple[DmSubsetProfileRow, ...]:
    s = GOLD_DM_PROFILES
    return tuple(
        DmSubsetProfileRow(
            dimension=col_str(r, s, "dimension"),
            fold=col_str_or_none(r, s, "fold"),
            seed=col_int_or_none(r, s, "seed"),
            level=col_float_or_none(r, s, "level"),
            comparator=col_str(r, s, "comparator"),
            status=col_str(r, s, "status"),
            undefined_reason=col_str_or_none(r, s, "undefined_reason"),
            detail=col_str(r, s, "detail"),
            n_points=col_int_or_none(r, s, "n_points"),
            first_target_timestamp=col_str_or_none(r, s, "first_target_timestamp"),
            last_target_timestamp=col_str_or_none(r, s, "last_target_timestamp"),
            variance_estimator=col_str(r, s, "variance_estimator"),
            mean_differential=col_float_or_none(r, s, "mean_differential"),
            statistic=col_float_or_none(r, s, "statistic"),
            p_value=col_float_or_none(r, s, "p_value"),
            rejected=col_bool_or_none(r, s, "rejected"),
            fallback_applied=col_bool_or_none(r, s, "fallback_applied"),
            horizon_used=col_int_or_none(r, s, "horizon_used"),
            alpha=col_float(r, s, "alpha"),
        )
        for r in _at(rows, s, horizon)
    )


def _seed_fractions(rows: Sequence[Row], horizon: int) -> tuple[SeedFractionProfileRow, ...]:
    s = GOLD_DM_SEED_FRACTION
    return tuple(
        SeedFractionProfileRow(
            comparator=col_str(r, s, "comparator"),
            n_seeds=col_int(r, s, "n_seeds"),
            n_rejecting=col_int(r, s, "n_rejecting"),
            n_undefined=col_int(r, s, "n_undefined"),
            fraction_rejecting=col_float_or_none(r, s, "fraction_rejecting"),
            alpha=col_float(r, s, "alpha"),
        )
        for r in _at(rows, s, horizon)
    )


def _mcs_blocks(rows: Sequence[Row], horizon: int) -> tuple[McsBlockProfileRow, ...]:
    s = GOLD_MCS_BLOCK_SENSITIVITY
    return tuple(
        McsBlockProfileRow(
            block_rule=col_str(r, s, "block_rule"),
            model=col_str_or_none(r, s, "model"),
            status=col_str(r, s, "status"),
            undefined_reason=col_str_or_none(r, s, "undefined_reason"),
            detail=col_str(r, s, "detail"),
            scheme=col_str(r, s, "scheme"),
            block_size=col_int(r, s, "block_size"),
            elimination_rank=col_int_or_none(r, s, "elimination_rank"),
            step_p_value=col_float_or_none(r, s, "step_p_value"),
            mcs_p_value=col_float_or_none(r, s, "mcs_p_value"),
            included=col_bool_or_none(r, s, "included"),
            alpha=col_float_or_none(r, s, "alpha"),
            reps=col_int_or_none(r, s, "reps"),
            seed=col_int_or_none(r, s, "seed"),
            n_points=col_int_or_none(r, s, "n_points"),
        )
        for r in _at(rows, s, horizon)
    )


def _monte_carlo(rows: Sequence[Row], horizon: int) -> tuple[MonteCarloProfileRow, ...]:
    s = GOLD_CHRISTOFFERSEN_MONTE_CARLO
    return tuple(
        MonteCarloProfileRow(
            model=col_str(r, s, "model"),
            seed=col_int_or_none(r, s, "seed"),
            sample=col_str(r, s, "sample"),
            kind=col_str(r, s, "kind"),
            level_low=col_float(r, s, "level_low"),
            level_high=col_float_or_none(r, s, "level_high"),
            includes_degenerate=col_bool(r, s, "includes_degenerate"),
            status=col_str(r, s, "status"),
            detail=col_str(r, s, "detail"),
            uc_status=col_str_or_none(r, s, "uc_status"),
            ind_status=col_str_or_none(r, s, "ind_status"),
            mc_p_uc=col_float_or_none(r, s, "mc_p_uc"),
            mc_p_ind=col_float_or_none(r, s, "mc_p_ind"),
            mc_p_cc=col_float_or_none(r, s, "mc_p_cc"),
            draws=col_int(r, s, "draws"),
            mc_seed=col_int(r, s, "mc_seed"),
            attempts=col_int_or_none(r, s, "attempts"),
        )
        for r in _at(rows, s, horizon)
    )


def _partial_degeneracy(
    rows: Sequence[Row], horizon: int
) -> tuple[PartialDegeneracyProfileRow, ...]:
    s = GOLD_PARTIAL_DEGENERACY
    return tuple(
        PartialDegeneracyProfileRow(
            model=col_str(r, s, "model"),
            seed=col_int_or_none(r, s, "seed"),
            sample=col_str(r, s, "sample"),
            pair_kind=col_str(r, s, "pair_kind"),
            level_low=col_float_or_none(r, s, "level_low"),
            level_high=col_float_or_none(r, s, "level_high"),
            status=col_str(r, s, "status"),
            detail=col_str(r, s, "detail"),
            collapse_rate=col_float_or_none(r, s, "collapse_rate"),
            tolerance=col_float(r, s, "tolerance"),
        )
        for r in _at(rows, s, horizon)
    )


def _stationarity(
    breaks: Sequence[Row], acf_rows: Sequence[Row], horizon: int
) -> tuple[StationarityProfileRow, ...]:
    s, a = GOLD_DIFFERENTIAL_BREAKS, GOLD_DIFFERENTIAL_ACF
    # o `GoldTable` está em ordem estrita da chave (horizon, model_a, model_b, lag): a ACF
    # de cada par sai em ordem de lag sem reordenar
    acf: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in _at(acf_rows, a, horizon):
        pair = (col_str(r, a, "model_a"), col_str(r, a, "model_b"))
        acf[pair].append(col_float(r, a, "acf"))
    profile: list[StationarityProfileRow] = []
    for r in _at(breaks, s, horizon):
        pair = (col_str(r, s, "model_a"), col_str(r, s, "model_b"))
        profile.append(
            StationarityProfileRow(
                model_a=pair[0],
                model_b=pair[1],
                status=col_str(r, s, "status"),
                undefined_reason=col_str_or_none(r, s, "undefined_reason"),
                detail=col_str(r, s, "detail"),
                statistic=col_float_or_none(r, s, "statistic"),
                p_value=col_float_or_none(r, s, "p_value"),
                rejected=col_bool_or_none(r, s, "rejected"),
                alpha=col_float(r, s, "alpha"),
                horizon_used=col_int_or_none(r, s, "horizon_used"),
                break_target_timestamp=col_str_or_none(r, s, "break_target_timestamp"),
                n_points=col_int_or_none(r, s, "n_points"),
                max_lag=col_int_or_none(r, s, "max_lag"),
                acf=tuple(acf[pair]),
            )
        )
    return tuple(profile)


def _profile_states(prereg: Preregistration) -> tuple[tuple[str, ProfileState], ...]:
    def state(profile: str) -> ProfileState:
        if profile in NOT_BUILT_HERE:
            return ProfileState.NOT_BUILT_HERE
        if prereg.profile_parameters is None and profile in FROZEN_RULE_PROFILES:
            return ProfileState.NOT_FROZEN_IN_REVISION
        return ProfileState.BUILT

    return tuple((profile, state(profile)) for profile in prereg.profiles.declared)


def build_profile(
    *,
    prereg: Preregistration,
    evidence: Sequence[HorizonEvidence],
    verdict: ScorecardVerdict,
    generation: GoldGeneration,
) -> ScorecardProfile:
    """O perfil por horizonte (ver docstring do módulo); nunca lido por `decide`."""
    calibration_rows = generation.table(GOLD_CALIBRATION_TABLE).rows
    metric_rows = generation.table(GOLD_METRICS_BY_RUN).rows
    dm_rows = generation.table(GOLD_DM_PROFILES).rows
    fraction_rows = generation.table(GOLD_DM_SEED_FRACTION).rows
    block_rows = generation.table(GOLD_MCS_BLOCK_SENSITIVITY).rows
    monte_carlo_rows = generation.table(GOLD_CHRISTOFFERSEN_MONTE_CARLO).rows
    partial_rows = generation.table(GOLD_PARTIAL_DEGENERACY).rows
    break_rows = generation.table(GOLD_DIFFERENTIAL_BREAKS).rows
    acf_rows = generation.table(GOLD_DIFFERENTIAL_ACF).rows
    tiers = ConfirmatoryScorecard.tier_readings(prereg, evidence)
    by_horizon = {item.horizon: item for item in evidence}
    horizons: list[HorizonProfile] = []
    for horizon_verdict in verdict.horizons:
        h = horizon_verdict.horizon
        item = by_horizon[h]
        h1 = horizon_verdict.h1
        horizons.append(
            HorizonProfile(
                horizon=h,
                gate_sensitivities=_gate_sensitivities(horizon_verdict),
                power=tuple(
                    PowerProfile(
                        label=power.label,
                        role=power.role.value,
                        n=power.n,
                        failure_probability=power.failure_probability,
                        assumes_independence=h1.power_assumes_independence,
                    )
                    for power in h1.power
                ),
                tiers=tuple(
                    TierProfile(
                        tier=reading.tier,
                        members=reading.members,
                        holm_rejects_all=reading.holm_rejects_all,
                        candidate_in_mcs=reading.candidate_in_mcs,
                        beats_or_ties=reading.beats_or_ties,
                        ties_in_mcs=reading.ties_in_mcs,
                    )
                    for reading in tiers
                    if reading.horizon == h
                ),
                dm=_dm_rows(item),
                bartlett_divergences=_bartlett_divergences(prereg, item),
                mcs_moving_block_divergence=_moving_block_divergence(prereg, item),
                comparators_calibration=_comparators(prereg, item),
                calibration_95=_calibration_series(prereg, calibration_rows, h),
                without_gaps=_without_gaps(prereg, calibration_rows, h),
                descriptors=_descriptors(metric_rows, h),
                lowest_mean_pinball=horizon_verdict.candidate_has_lowest_mean_pinball,
                dm_subsets=_dm_subsets(dm_rows, h),
                dm_seed_fractions=_seed_fractions(fraction_rows, h),
                mcs_block_sensitivity=_mcs_blocks(block_rows, h),
                monte_carlo=_monte_carlo(monte_carlo_rows, h),
                partial_degeneracy=_partial_degeneracy(partial_rows, h),
                stationarity=_stationarity(break_rows, acf_rows, h),
            )
        )
    states = _profile_states(prereg)
    return ScorecardProfile(
        horizons=tuple(horizons),
        declared_not_built=tuple(p for p, s in states if s is ProfileState.NOT_BUILT_HERE),
        profile_states=states,
    )
