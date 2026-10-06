"""Serviço de domínio `ProfileReports` — os perfis de séries novas de um horizonte (Stage 6.6).

Stdlib-only (concept 6.6 §4, I1, I2, I4, I7, I9, I13; ADRs `6_6_0001`-`6_6_0003`). Compõe,
por horizonte, só chamando os donos — nenhuma fórmula própria:

- `differentials` — d_t = L_a - L_b por par de `paired.model_pairs()` (a série pareada
  primária), com o fold de cada ponto quando a montagem o tem; sempre (sem regra);
- `monte_carlo` — em h = 1 só (`monte_carlo_defined_for`), para cada (modelo, seed,
  amostra) e cada sequência de hits que o gold testa pelo χ² (`hit_sequences`, a mesma
  ordem do `HorizonReports`), o `ChristoffersenTest.monte_carlo_p_values` com `draws`/
  `seed` do plano;
- com `profile_parameters` (a revisão congela as regras — I9): `dm_profiles`
  (`DmProfiles`), `stationarity` (`DifferentialStationarity`, um relatório por par) e
  `partial_degeneracy` — pares simétricos copiados do `DegeneracyReport` que o
  `HorizonReports` já calculou e adjacentes por `adjacent_collapse_rates`; sem as regras,
  os três são `None` (perfis "não congelados nesta revisão").

Isolamento (I4): só a **chamada** a cada serviço fica na captura (`_guarded`); um
`ValueError`/`ArithmeticError` vira unidade `error` com a mensagem e entra em
`error_units` (o `DmProfiles` isola as suas unidades do mesmo jeito). A montagem dos
relatórios fica fora — bug de contrato ergue. Unidade da estacionariedade = a chamada do
horizonte (falha → linha `error` para cada par).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import partial

from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    ChristoffersenTest,
    MonteCarloPValues,
    monte_carlo_defined_for,
)
from financial_forecasting.features.evaluation.domain.services.degeneracy_gate import (
    adjacent_collapse_rates,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.differential_stationarity import (
    DifferentialStationarity,
    StationarityReport,
)
from financial_forecasting.features.evaluation.domain.services.dm_profiles import (
    ERROR,
    DmProfiles,
    DmProfilesReport,
)
from financial_forecasting.features.evaluation.domain.services.horizon_reports import (
    HorizonReport,
    SampleKind,
    check_paired,
    hit_sequences,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    HorizonSamples,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import HitKind
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.profile_parameters import (
    ProfileParameters,
)


class UnitStatus(StrEnum):
    """Desfecho de uma unidade de perfil isolada."""

    COMPUTED = "computed"
    ERROR = "error"


class PairKind(StrEnum):
    """Que par da grade a degeneração parcial descreve (ADR 6.6.0002 T2)."""

    SYMMETRIC = "symmetric"
    ADJACENT = "adjacent"


@dataclass(frozen=True)
class DifferentialSeries:
    """d_t de um par na amostra comum (insumo do plot da 8.3)."""

    pair: tuple[str, str]
    target_timestamps: tuple[str, ...]
    folds: tuple[str | None, ...] | None
    values: tuple[float, ...]


@dataclass(frozen=True)
class MonteCarloRow:
    """O Monte Carlo de uma sequência de hits (ou o erro da chamada)."""

    model: str
    seed: int | None
    sample: SampleKind
    kind: HitKind
    levels: tuple[float, ...]
    includes_degenerate: bool
    status: UnitStatus
    detail: str
    values: MonteCarloPValues | None


@dataclass(frozen=True)
class StationarityRow:
    """O diagnóstico de d_t de um par (ou o erro da chamada do horizonte)."""

    pair: tuple[str, str]
    status: UnitStatus
    detail: str
    report: StationarityReport | None


@dataclass(frozen=True)
class PartialDegeneracyRow:
    """Taxa de colapso parcial de um par (simétrico ou adjacente) de uma série.

    Linha `error` (falha da taxa adjacente da série): níveis e taxa nulos.
    """

    model: str
    seed: int | None
    sample: SampleKind
    pair_kind: PairKind
    level_low: float | None
    level_high: float | None
    collapse_rate: float | None
    status: UnitStatus
    detail: str


@dataclass(frozen=True)
class HorizonProfileReport:
    """Os perfis de séries novas de um horizonte (ver docstring do módulo)."""

    horizon: int
    differentials: tuple[DifferentialSeries, ...]
    monte_carlo: tuple[MonteCarloRow, ...]
    dm_profiles: DmProfilesReport | None
    stationarity: tuple[StationarityRow, ...] | None
    partial_degeneracy: tuple[PartialDegeneracyRow, ...] | None
    error_units: int


def _guarded[T](call: Callable[[], T]) -> tuple[T | None, str]:
    """A chamada a um serviço; `ValueError`/`ArithmeticError` → `(None, mensagem)` (I4)."""
    try:
        return call(), ""
    except (ValueError, ArithmeticError) as error:
        return None, f"{type(error).__name__}: {error}"


@dataclass(frozen=True, kw_only=True)
class ProfileSettings:
    """Os parâmetros do plano que os perfis usam (vindos do `RefreshParameters`)."""

    candidate: str
    alpha: float
    variance_estimator: DmVarianceEstimator
    min_violations: int
    tolerance: float
    draws: int
    seed: int
    profile_parameters: ProfileParameters | None


class ProfileReports:
    """Compõe os perfis de séries novas de um horizonte (ver docstring do módulo)."""

    @staticmethod
    def evaluate(
        samples: HorizonSamples,
        *,
        horizon_report: HorizonReport,
        paired: PairedLossSeries,
        settings: ProfileSettings,
    ) -> HorizonProfileReport:
        """Os perfis do horizonte; falha de unidade vira `error`, nunca exceção (I4).

        Raises:
            ValueError: `horizon_report` de outro horizonte; `paired` fora da amostra comum
                (`check_paired`, I2); tolerância diferente da que o gate usou (as
                sequências e os pares simétricos copiados são os do gold).
        """
        if horizon_report.horizon != samples.horizon:
            raise ValueError(
                f"samples and horizon_report must share the horizon, got "
                f"{samples.horizon} and {horizon_report.horizon}"
            )
        check_paired(samples, paired)
        tolerances = {s.coverage.degeneracy.tolerance for s in horizon_report.series}
        if tolerances != {settings.tolerance}:
            raise ValueError(
                f"settings.tolerance {settings.tolerance!r} must be the gate tolerance "
                f"{sorted(tolerances)}"
            )
        monte_carlo = _monte_carlo(samples, settings)
        parameters = settings.profile_parameters
        dm = None
        stationarity = None
        degeneracy = None
        if parameters is not None:
            dm = DmProfiles.evaluate(
                samples,
                candidate=settings.candidate,
                alpha=settings.alpha,
                variance_estimator=settings.variance_estimator,
            )
            stationarity = _stationarity(paired, parameters, settings.variance_estimator)
            degeneracy = _partial_degeneracy(samples, horizon_report, settings.tolerance)
        errors = sum(1 for row in monte_carlo if row.status is UnitStatus.ERROR)
        errors += 0 if dm is None else sum(1 for r in dm.rows if r.undefined_reason == ERROR)
        errors += sum(1 for r in stationarity or () if r.status is UnitStatus.ERROR)
        errors += sum(1 for r in degeneracy or () if r.status is UnitStatus.ERROR)
        return HorizonProfileReport(
            horizon=samples.horizon,
            differentials=tuple(
                DifferentialSeries(
                    pair=pair,
                    target_timestamps=paired.target_timestamps,
                    folds=samples.common_folds,
                    values=paired.differential(*pair),
                )
                for pair in paired.model_pairs()
            ),
            monte_carlo=monte_carlo,
            dm_profiles=dm,
            stationarity=stationarity,
            partial_degeneracy=degeneracy,
            error_units=errors,
        )


def _series_of(samples: HorizonSamples) -> list[tuple[str, int | None, SampleKind, CoverageSeries]]:
    """(modelo, seed, amostra, série) na ordem do `HorizonReports`."""
    return [
        (model, seed, sample, series)
        for model in samples.models
        for index, seed in enumerate(samples.seeds[model])
        for sample, series in (
            (SampleKind.MODEL_FULL, samples.full[model][index]),
            (SampleKind.COMMON, samples.common[model][index]),
        )
    ]


def _monte_carlo(samples: HorizonSamples, settings: ProfileSettings) -> tuple[MonteCarloRow, ...]:
    if not monte_carlo_defined_for(samples.horizon):
        return ()
    rows: list[MonteCarloRow] = []
    for model, seed, sample, series in _series_of(samples):
        for sequence, _ in hit_sequences(series, settings.tolerance):
            if sequence.is_dgt_subseries:  # redundante em h = 1 (DGT só em h > 1): defesa
                continue
            values, detail = _guarded(
                partial(
                    ChristoffersenTest.monte_carlo_p_values,
                    sequence,
                    min_violations=settings.min_violations,
                    draws=settings.draws,
                    seed=settings.seed,
                )
            )
            rows.append(
                MonteCarloRow(
                    model=model,
                    seed=seed,
                    sample=sample,
                    kind=sequence.kind,
                    levels=sequence.levels,
                    includes_degenerate=sequence.includes_degenerate,
                    status=UnitStatus.ERROR if values is None else UnitStatus.COMPUTED,
                    detail=detail,
                    values=values,
                )
            )
    return tuple(rows)


def _stationarity(
    paired: PairedLossSeries,
    parameters: ProfileParameters,
    variance_estimator: DmVarianceEstimator,
) -> tuple[StationarityRow, ...]:
    reports, detail = _guarded(
        lambda: DifferentialStationarity.evaluate(
            paired, parameters=parameters.stationarity, variance_estimator=variance_estimator
        )
    )
    if reports is None:
        return tuple(
            StationarityRow(pair=pair, status=UnitStatus.ERROR, detail=detail, report=None)
            for pair in paired.model_pairs()
        )
    return tuple(
        StationarityRow(pair=report.pair, status=UnitStatus.COMPUTED, detail="", report=report)
        for report in reports
    )


def _partial_degeneracy(
    samples: HorizonSamples, horizon_report: HorizonReport, tolerance: float
) -> tuple[PartialDegeneracyRow, ...]:
    symmetric = {
        (report.model, report.seed, report.sample): report.coverage.degeneracy.pair_collapse_rates
        for report in horizon_report.series
    }
    rows: list[PartialDegeneracyRow] = []
    for model, seed, sample, series in _series_of(samples):
        for low, high, rate in symmetric[model, seed, sample]:
            rows.append(
                PartialDegeneracyRow(
                    model=model,
                    seed=seed,
                    sample=sample,
                    pair_kind=PairKind.SYMMETRIC,
                    level_low=low,
                    level_high=high,
                    collapse_rate=rate,
                    status=UnitStatus.COMPUTED,
                    detail="",
                )
            )
        adjacent, detail = _guarded(partial(adjacent_collapse_rates, series, tolerance=tolerance))
        if adjacent is None:
            rows.append(
                PartialDegeneracyRow(
                    model=model,
                    seed=seed,
                    sample=sample,
                    pair_kind=PairKind.ADJACENT,
                    level_low=None,
                    level_high=None,
                    collapse_rate=None,
                    status=UnitStatus.ERROR,
                    detail=detail,
                )
            )
            continue
        rows += [
            PartialDegeneracyRow(
                model=model,
                seed=seed,
                sample=sample,
                pair_kind=PairKind.ADJACENT,
                level_low=low,
                level_high=high,
                collapse_rate=rate,
                status=UnitStatus.COMPUTED,
                detail="",
            )
            for low, high, rate in adjacent
        ]
    return tuple(rows)
