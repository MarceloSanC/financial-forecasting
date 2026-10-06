"""Serviço de domínio `HorizonReports` — os relatórios 6.1-6.3 de um horizonte (6.4).

Stdlib-only (concept 6.4 §4, D5, I1, I12, C8; ADR `6_4_0007`). **Só chama** os
serviços existentes, sem re-derivar nenhuma métrica, sobre as duas amostras do
`HorizonSamples` (`model_full` e `common`) de cada (modelo, seed):

- `PinballScore.score`, `CrpsScore.score`, `IntervalScore.score`,
  `CoverageMetrics.evaluate(tolerance)` e o `guardrail_applied_rate` da série;
- calibração: para cada par simétrico (`HitSequences.interval`) e cada τ ≠ 0,5 (cauda
  por `var_tail_for`, que dá também o `var_level`), com `include_degenerate` em
  {False, True}, a sequência e — se h > 1 — cada sub-série de `dgt_partition()`, cada
  uma com `ChristoffersenTest.evaluate(min_violations)` e uma `WilsonBand` por nível de
  banda (`count = n_violations`, `n = n_observed`, `nominal = violation_rate`);
- na amostra comum, a `PairedLossSeries` recebida (montada **uma vez** pelo use case
  com a fábrica `paired_pinball_losses` — média de L_t entre seeds, I12 — e a mesma que
  foi ao backend do MCS) e um `HolmCorrection.family` por estimador de variância.

Série 100 % degenerada não é erro: os serviços devolvem os seus relatórios "não
aplicável" (C8). O MCS atravessa o port `McsBackend` e fica no use case.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum

from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    ChristoffersenReport,
    ChristoffersenTest,
)
from financial_forecasting.features.evaluation.domain.services.coverage_metrics import (
    CoverageMetrics,
    CoverageReport,
)
from financial_forecasting.features.evaluation.domain.services.crps_score import (
    CrpsReport,
    CrpsScore,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.hit_sequences import (
    HitSequences,
)
from financial_forecasting.features.evaluation.domain.services.holm_correction import (
    DmHolmFamilyReport,
    HolmCorrection,
)
from financial_forecasting.features.evaluation.domain.services.interval_score import (
    IntervalScore,
    IntervalScoreReport,
)
from financial_forecasting.features.evaluation.domain.services.pinball_score import (
    PinballReport,
    PinballScore,
)
from financial_forecasting.features.evaluation.domain.services.var_descriptive import (
    var_tail_for,
)
from financial_forecasting.features.evaluation.domain.services.wilson_band import (
    WilsonBand,
    WilsonBandReport,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    is_multi_step,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    HorizonSamples,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    MEDIAN_LEVEL,
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitKind,
    HitSequence,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)

_INCLUDE_DEGENERATE = (False, True)


class SampleKind(StrEnum):
    """Amostra de uma série (ADR `6_4_0007`)."""

    MODEL_FULL = "model_full"  # toda a série do (modelo, seed)
    COMMON = "common"  # a interseção comum do horizonte


@dataclass(frozen=True)
class CalibrationRow:
    """Uma sequência de hits testada: Christoffersen, bandas de Wilson e o nível de VaR.

    Campos:
        christoffersen: o relatório (carrega kind, níveis, `include_degenerate` e DGT).
        wilson: uma banda por nível de banda, na ordem pedida.
        var_level: nível de VaR da cauda (`var_tail_for`); `None` num intervalo.
    """

    christoffersen: ChristoffersenReport
    wilson: tuple[WilsonBandReport, ...]
    var_level: float | None


@dataclass(frozen=True)
class SeriesReports:
    """Relatórios de uma série (modelo, seed, amostra) de um horizonte."""

    model: str
    seed: int | None
    sample: SampleKind
    n_points: int
    first_target_timestamp: str
    last_target_timestamp: str
    pinball: PinballReport
    crps: CrpsReport
    interval: IntervalScoreReport
    coverage: CoverageReport
    guardrail_applied_rate: float
    calibration: tuple[CalibrationRow, ...]


@dataclass(frozen=True)
class HorizonReport:
    """Relatórios de um horizonte: por série, a série pareada e as famílias DM + Holm."""

    horizon: int
    n_common: int
    common_first_target_timestamp: str
    common_last_target_timestamp: str
    series: tuple[SeriesReports, ...]
    paired: PairedLossSeries
    dm_families: tuple[DmHolmFamilyReport, ...]


class HorizonReports:
    """Compõe os relatórios 6.1-6.3 de um horizonte chamando os serviços existentes."""

    @staticmethod
    def evaluate(  # noqa: PLR0913 — parâmetros explícitos do refresh (ADR 6.4.0006)
        samples: HorizonSamples,
        *,
        paired: PairedLossSeries,
        tolerance: float,
        band_levels: tuple[float, ...],
        min_violations: int,
        candidate: str,
        dm_alpha: float,
        dm_variance_estimators: tuple[DmVarianceEstimator, ...],
    ) -> HorizonReport:
        """Relatórios das duas amostras e as famílias DM + Holm da amostra comum.

        Raises:
            ValueError: `paired` de outro horizonte, com outros modelos ou fora da
                amostra comum; `band_levels`/`dm_variance_estimators` vazios; e os erros
                de validação dos serviços chamados.
        """
        _check_paired(samples, paired)
        if not band_levels:
            raise ValueError("band_levels must hold at least one band level")
        if not dm_variance_estimators:
            raise ValueError("dm_variance_estimators must hold at least one estimator")
        series_reports = tuple(
            _series_reports(
                series,
                model=model,
                seed=seed,
                sample=sample,
                tolerance=tolerance,
                band_levels=band_levels,
                min_violations=min_violations,
            )
            for model in samples.models
            for index, seed in enumerate(samples.seeds[model])
            for sample, series in (
                (SampleKind.MODEL_FULL, samples.full[model][index]),
                (SampleKind.COMMON, samples.common[model][index]),
            )
        )
        return HorizonReport(
            horizon=samples.horizon,
            n_common=samples.n_common,
            common_first_target_timestamp=samples.common_first_target_timestamp,
            common_last_target_timestamp=samples.common_last_target_timestamp,
            series=series_reports,
            paired=paired,
            dm_families=tuple(
                HolmCorrection.family(
                    paired, candidate=candidate, alpha=dm_alpha, variance_estimator=estimator
                )
                for estimator in dm_variance_estimators
            ),
        )


def _check_paired(samples: HorizonSamples, paired: PairedLossSeries) -> None:
    if paired.horizon != samples.horizon:
        raise ValueError(
            f"paired series is for horizon {paired.horizon}, samples for {samples.horizon}"
        )
    if paired.models != samples.models:
        raise ValueError(f"paired models {paired.models} != samples models {samples.models}")
    common = samples.common[samples.models[0]][0].target_timestamps
    if paired.target_timestamps != common:
        raise ValueError(
            "paired series must be on the common sample of the horizon "
            f"(T={paired.n_points} vs n_common={samples.n_common})"
        )


def _series_reports(  # noqa: PLR0913 — uma série e o seu escopo, keyword-only
    series: CoverageSeries,
    *,
    model: str,
    seed: int | None,
    sample: SampleKind,
    tolerance: float,
    band_levels: tuple[float, ...],
    min_violations: int,
) -> SeriesReports:
    return SeriesReports(
        model=model,
        seed=seed,
        sample=sample,
        n_points=series.n_points,
        first_target_timestamp=series.target_timestamps[0],
        last_target_timestamp=series.target_timestamps[-1],
        pinball=PinballScore.score(series),
        crps=CrpsScore.score(series),
        interval=IntervalScore.score(series),
        coverage=CoverageMetrics.evaluate(series, tolerance=tolerance),
        guardrail_applied_rate=series.guardrail_applied_rate,
        calibration=tuple(
            CalibrationRow(
                christoffersen=ChristoffersenTest.evaluate(sequence, min_violations=min_violations),
                wilson=tuple(
                    WilsonBand.evaluate(
                        horizon=sequence.horizon,
                        count=sequence.n_violations,
                        n=sequence.n_observed,
                        nominal=sequence.violation_rate,
                        band_level=band_level,
                    )
                    for band_level in band_levels
                ),
                var_level=var_level,
            )
            for sequence, var_level in hit_sequences(series, tolerance)
        ),
    )


def hit_sequences(
    series: CoverageSeries, tolerance: float
) -> Iterator[tuple[HitSequence, float | None]]:
    """Sequências de hits na ordem: intervalos, caudas; sem/com degeneradas; + DGT.

    Pública (Stage 6.6): o `ProfileReports` reusa a mesma lista de sequências testadas
    para o Monte Carlo de h = 1 — uma escrita só.
    """
    for include in _INCLUDE_DEGENERATE:
        for pair in series.symmetric_pairs:
            sequence = HitSequences.interval(
                series, pair=pair, tolerance=tolerance, include_degenerate=include
            )
            yield from _with_partition(sequence, None)
        for level in series.levels:
            if level == MEDIAN_LEVEL:
                continue
            kind, var_level = var_tail_for(level)
            build = (
                HitSequences.lower_tail if kind is HitKind.LOWER_TAIL else HitSequences.upper_tail
            )
            sequence = build(series, level=level, tolerance=tolerance, include_degenerate=include)
            yield from _with_partition(sequence, var_level)


def _with_partition(
    sequence: HitSequence, var_level: float | None
) -> Iterator[tuple[HitSequence, float | None]]:
    yield sequence, var_level
    if is_multi_step(sequence.horizon):  # DGT só em h > 1 (regra única do slice)
        for subseries in sequence.dgt_partition():
            yield subseries, var_level
