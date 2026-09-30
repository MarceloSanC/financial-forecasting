"""Perfil do scorecard confirmatório — o que é informação, nunca veredito (Stage 6.5).

Módulo auxiliar do use case `BuildConfirmatoryScorecard` (concept 6.5 §4, D8, I8, I10,
I12; ADRs `6_5_0006` itens 4, 6, 7, `6_5_0007` itens 4-5, `6_5_0008` item 2).
`build_profile` **só copia** colunas do gold (lidas pelo schema, `col`) e chama os
donos: `H1Result` (sensibilidades e poder, já calculados pelo `H1Gate`),
`ConfirmatoryScorecard.tier_readings`, `H1Gate.tail_bands` (bandas dos comparadores
com S = 1), `dm_effect_interval` (IC do efeito a 95 %) e `SeedSpread` (descritores
entre seeds). Nada é recomputado (I8); os comparadores mal calibrados ficam nas
leituras (I10, doc §6.4); o veredito é construído antes e sem o perfil (I12).

`declared_not_built`: os perfis que o plano declara e esta Stage não constrói — os de
séries novas (issue #129: DM por fold/seed/τ, estacionariedade de d_t, degeneração
parcial por par, sensibilidades de bloco do MCS, p-valor Monte Carlo) e o diagrama de
nitidez (8.3).

Os `# type: ignore[arg-type]` deste módulo vêm das células do gold, tipadas `object`
(`col`): o tipo é o do schema dono (`gold_schema`) e os valores são revalidados na
construção dos VOs/DTOs de destino (evidência, perfil, `FailedCheck`).
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
    GateSensitivitiesProfile,
    HorizonProfile,
    PowerProfile,
    ScorecardProfile,
    TailSummaryProfile,
    TierProfile,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CALIBRATION_TABLE,
    GOLD_METRICS_BY_RUN,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    Row,
)
from financial_forecasting.features.evaluation.application.use_cases.scorecard_evidence import (
    LOWER_TAIL,
    UPPER_TAIL,
    col,
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

NOT_BUILT_HERE: Final = frozenset(
    {
        "mcs_block_h",
        "mcs_block_sqrt_t",
        "christoffersen_monte_carlo_h1",
        "dm_per_fold",
        "dm_per_seed",
        "dm_per_tau",
        "dm_differential_stationarity",
        "partial_degeneracy_per_pair",
        "sharpness_diagram",
    }
)
"""Perfis declaráveis fora da 6.5 (ADR 6.5.0008 itens 3-4: issue #129 e Stage 8.3)."""

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


def _calibration_series(
    prereg: Preregistration, rows: Sequence[Row], horizon: int
) -> tuple[CalibrationSeriesProfile, ...]:
    schema = GOLD_CALIBRATION_TABLE
    groups: dict[tuple[object, ...], list[Row]] = defaultdict(list)
    for row in rows:
        if col(row, schema, "horizon") != horizon:
            continue
        if col(row, schema, "band_level") != prereg.h1_gate.profile_band_level:
            continue
        key = tuple(
            col(row, schema, c)
            for c in (
                "model",
                "sample",
                "kind",
                "level_low",
                "level_high",
                "includes_degenerate",
                "dgt_offset",
                "dgt_step",
            )
        )
        groups[key].append(row)
    alpha = prereg.h1_gate.sensitivity_alpha
    series: list[CalibrationSeriesProfile] = []
    for key, members in groups.items():
        contains = [col(r, schema, "wilson_contains_nominal") for r in members]
        applicable = [
            r for r in members if col(r, schema, "independence_status") == _INDEPENDENCE_APPLICABLE
        ]
        series.append(
            CalibrationSeriesProfile(
                model=key[0],  # type: ignore[arg-type]
                sample=key[1],  # type: ignore[arg-type]
                kind=key[2],  # type: ignore[arg-type]
                level_low=key[3],  # type: ignore[arg-type]
                level_high=key[4],  # type: ignore[arg-type]
                includes_degenerate=key[5],  # type: ignore[arg-type]
                dgt_offset=key[6],  # type: ignore[arg-type]
                dgt_step=key[7],  # type: ignore[arg-type]
                n_seeds=len(members),
                mean_violations=_mean([col(r, schema, "n_violations") for r in members]),  # type: ignore[misc]
                mean_observed=_mean([col(r, schema, "n_observed") for r in members]),  # type: ignore[misc]
                fraction_contains_nominal=_fraction([c is True for c in contains if c is not None]),
                fraction_ind_rejected=_fraction(
                    [col(r, schema, "p_ind") < alpha for r in applicable]  # type: ignore[operator]
                ),
                fraction_cc_rejected=_fraction(
                    [col(r, schema, "p_cc") < alpha for r in applicable]  # type: ignore[operator]
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
            if col(r, schema, "model") == prereg.candidate
            and col(r, schema, "horizon") == horizon
            and col(r, schema, "sample") == GATE_SAMPLE
            and col(r, schema, "kind") == kind
            and col(r, schema, "level_low") == level
            and col(r, schema, "includes_degenerate") is True
            and col(r, schema, "dgt_offset") is None
            and col(r, schema, "band_level") == gate.gate_band_level
        ]
        if members:
            summaries.append(
                TailSummaryProfile(
                    kind=kind,
                    level=level,
                    mean_violations=_mean([col(r, schema, "n_violations") for r in members]),  # type: ignore[misc]
                    mean_observed=_mean([col(r, schema, "n_observed") for r in members]),  # type: ignore[misc]
                )
            )
    return tuple(summaries)


def _descriptors(rows: Sequence[Row], horizon: int) -> tuple[DescriptorProfile, ...]:
    schema = GOLD_METRICS_BY_RUN
    groups: dict[tuple[object, ...], list[float]] = defaultdict(list)
    for row in rows:
        if col(row, schema, "horizon") != horizon:
            continue
        key = tuple(
            col(row, schema, c) for c in ("model", "sample", "metric", "level_low", "level_high")
        )
        groups[key].append(col(row, schema, "value"))  # type: ignore[arg-type]
    descriptors: list[DescriptorProfile] = []
    for key, values in groups.items():
        spread = SeedSpread.of(values)
        descriptors.append(
            DescriptorProfile(
                model=key[0],  # type: ignore[arg-type]
                sample=key[1],  # type: ignore[arg-type]
                metric=key[2],  # type: ignore[arg-type]
                level_low=key[3],  # type: ignore[arg-type]
                level_high=key[4],  # type: ignore[arg-type]
                mean=spread.mean,
                minimum=spread.minimum,
                maximum=spread.maximum,
                n_seeds=spread.n_seeds,
            )
        )
    return tuple(descriptors)


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
            )
        )
    return ScorecardProfile(
        horizons=tuple(horizons),
        declared_not_built=tuple(p for p in prereg.profiles.declared if p in NOT_BUILT_HERE),
    )
