"""Serviço de domínio `DmProfiles` — DM por fold, por seed e por τ como perfil (Stage 6.6).

Stdlib-only (concept 6.6 §4, D3, I1, I2, I3, I4, I5; ADR `6_6_0003`). **Só chama** o
`DieboldMariano.compare` da 6.2, com o estimador primário do plano, candidato contra cada
comparador, sobre recortes da série pareada da leitura primária (I2):

- **fold**: as janelas contíguas da amostra comum por rótulo (`HorizonSamples.common_folds`,
  ordem temporal) — `PairedLossSeries.window`; rótulos divergentes entre séries
  (`common_folds is None`) → uma linha `undefined` por comparador (`fold_label_mismatch`,
  `fold` nulo); rótulo em mais de uma janela → uma linha `undefined` por (rótulo,
  comparador) (`fold_not_contiguous`);
- **seed**: a série com **uma** seed do candidato no lugar da média; os comparadores como
  na primária (média das suas seeds);
- **τ**: a série da perda pinball de um nível só (`paired_pinball_losses(level=τ)`).

Perfil descritivo (D3, doc §6.4/§6.8): p bruto e `rejected` ⇔ p ≤ alpha, **sem** Holm nem
outra correção. Uma unidade é (recorte, comparador); pré-condições testadas antes da
chamada (`too_short`: T < 2 ou T ≤ h; `constant_differential`); `ValueError`/
`ArithmeticError` erguido pela chamada ao DM (só ela fica na captura) → `error` com a
mensagem (I4). A fração de seeds que rejeitam a alpha, por comparador, é
n_rejeitando / (n_seeds - n_indefinidas), nula sem seed testada (DM4).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DieboldMariano,
    DieboldMarianoResult,
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.inference_input_validation import (
    validate_alpha,
)
from financial_forecasting.features.evaluation.domain.services.paired_pinball_losses import (
    paired_pinball_losses,
)
from financial_forecasting.features.evaluation.domain.value_objects._paired_inputs import (
    MIN_POINTS,
    is_constant,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    HorizonSamples,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)

TOO_SHORT: Final = "too_short"
CONSTANT_DIFFERENTIAL: Final = "constant_differential"
FOLD_LABEL_MISMATCH: Final = "fold_label_mismatch"
FOLD_NOT_CONTIGUOUS: Final = "fold_not_contiguous"
ERROR: Final = "error"


class DmProfileDimension(StrEnum):
    """O recorte de um DM de perfil."""

    FOLD = "fold"
    SEED = "seed"
    TAU = "tau"


class SubsetStatus(StrEnum):
    """Se a unidade (recorte, comparador) foi calculada."""

    COMPUTED = "computed"
    UNDEFINED = "undefined"


@dataclass(frozen=True)
class DmSubsetRow:
    """Um DM de perfil: o recorte, o comparador e o resultado (ou o motivo de não haver).

    `fold`/`seed`/`level` só preenchido na dimensão correspondente (o rótulo `None` de
    fold é legítimo na dimensão `fold`); `result`, `rejected`, `n_points` e a janela
    ficam vazios quando `status` é `undefined`.
    """

    dimension: DmProfileDimension
    fold: str | None
    seed: int | None
    level: float | None
    comparator: str
    status: SubsetStatus
    undefined_reason: str | None
    detail: str
    n_points: int | None
    first_target_timestamp: str | None
    last_target_timestamp: str | None
    result: DieboldMarianoResult | None
    rejected: bool | None


@dataclass(frozen=True)
class SeedFractionRow:
    """Fração de seeds do candidato cujo DM rejeita a alpha, contra um comparador."""

    comparator: str
    n_seeds: int
    n_rejecting: int
    n_undefined: int
    fraction_rejecting: float | None


@dataclass(frozen=True)
class DmProfilesReport:
    """Os DMs de perfil de um horizonte e as frações de seeds."""

    horizon: int
    candidate: str
    alpha: float
    variance_estimator: DmVarianceEstimator
    rows: tuple[DmSubsetRow, ...]
    seed_fractions: tuple[SeedFractionRow, ...]


@dataclass(frozen=True)
class _Subset:
    dimension: DmProfileDimension
    fold: str | None = None
    seed: int | None = None
    level: float | None = None


class DmProfiles:
    """DM por fold, seed e τ sobre recortes da série pareada primária (ADR 6.6.0003)."""

    @staticmethod
    def evaluate(
        samples: HorizonSamples,
        *,
        candidate: str,
        alpha: float,
        variance_estimator: DmVarianceEstimator,
    ) -> DmProfilesReport:
        """Todas as unidades do horizonte, na ordem fold → seed → τ.

        Raises:
            ValueError: candidato fora de `samples.models`; alpha fora de (0, 1);
                menos de dois modelos (a fábrica da série pareada).
        """
        validate_alpha(alpha)
        if candidate not in samples.models:
            raise ValueError(f"candidate {candidate!r} is not a model of {samples.models}")
        comparators = tuple(model for model in samples.models if model != candidate)
        unit = _Unit(candidate, comparators, alpha, variance_estimator)
        base = paired_pinball_losses({m: samples.common[m] for m in samples.models})
        rows = [
            *_fold_rows(samples, base, unit),
            *_seed_rows(samples, unit),
            *_tau_rows(samples, unit),
        ]
        return DmProfilesReport(
            horizon=samples.horizon,
            candidate=candidate,
            alpha=alpha,
            variance_estimator=variance_estimator,
            rows=tuple(rows),
            seed_fractions=_seed_fractions(rows, comparators),
        )


@dataclass(frozen=True)
class _Unit:
    """Quem compara: candidato, comparadores, alpha e o estimador primário."""

    candidate: str
    comparators: tuple[str, ...]
    alpha: float
    estimator: DmVarianceEstimator

    def undefined(self, subset: _Subset, reason: str, detail: str) -> list[DmSubsetRow]:
        return [
            _row(subset, comparator, SubsetStatus.UNDEFINED, reason, detail)
            for comparator in self.comparators
        ]

    def compare(self, subset: _Subset, series: PairedLossSeries) -> list[DmSubsetRow]:
        return [self._one(subset, series, comparator) for comparator in self.comparators]

    def _one(self, subset: _Subset, series: PairedLossSeries, comparator: str) -> DmSubsetRow:
        if is_constant(series.differential(self.candidate, comparator)):
            return _row(
                subset, comparator, SubsetStatus.UNDEFINED, CONSTANT_DIFFERENTIAL, "", series
            )
        try:
            result = DieboldMariano.compare(
                series,
                candidate=self.candidate,
                comparator=comparator,
                variance_estimator=self.estimator,
            )
        except (ValueError, ArithmeticError) as error:
            detail = f"{type(error).__name__}: {error}"
            return _row(subset, comparator, SubsetStatus.UNDEFINED, ERROR, detail, series)
        return _row(
            subset,
            comparator,
            SubsetStatus.COMPUTED,
            None,
            "",
            series,
            result=result,
            rejected=result.p_value <= self.alpha,
        )


def _row(  # noqa: PLR0913 — o recorte, o comparador e o desfecho da unidade
    subset: _Subset,
    comparator: str,
    status: SubsetStatus,
    reason: str | None,
    detail: str,
    series: PairedLossSeries | None = None,
    *,
    result: DieboldMarianoResult | None = None,
    rejected: bool | None = None,
) -> DmSubsetRow:
    return DmSubsetRow(
        dimension=subset.dimension,
        fold=subset.fold,
        seed=subset.seed,
        level=subset.level,
        comparator=comparator,
        status=status,
        undefined_reason=reason,
        detail=detail,
        n_points=None if series is None else series.n_points,
        first_target_timestamp=None if series is None else series.target_timestamps[0],
        last_target_timestamp=None if series is None else series.target_timestamps[-1],
        result=result,
        rejected=rejected,
    )


def _fold_rows(samples: HorizonSamples, base: PairedLossSeries, unit: _Unit) -> list[DmSubsetRow]:
    folds = samples.common_folds
    if folds is None:
        detail = samples.fold_mismatch_detail or ""
        return unit.undefined(_Subset(DmProfileDimension.FOLD), FOLD_LABEL_MISMATCH, detail)
    windows = _contiguous_windows(folds)
    labels = [label for label, _, _ in windows]
    rows: list[DmSubsetRow] = []
    reported: set[str | None] = set()
    for label, start, stop in windows:
        subset = _Subset(DmProfileDimension.FOLD, fold=label)
        if labels.count(label) > 1:
            if label not in reported:
                reported.add(label)
                detail = f"fold {label!r} appears in {labels.count(label)} separate windows"
                rows += unit.undefined(subset, FOLD_NOT_CONTIGUOUS, detail)
            continue
        n_points = stop - start
        if n_points < MIN_POINTS or n_points <= samples.horizon:
            detail = f"T={n_points} with h={samples.horizon}"
            rows += unit.undefined(subset, TOO_SHORT, detail)
            continue
        rows += unit.compare(subset, base.window(start, stop))
    return rows


def _contiguous_windows(folds: Sequence[str | None]) -> list[tuple[str | None, int, int]]:
    """Janelas `[start, stop)` de rótulo constante, na ordem temporal."""
    windows: list[tuple[str | None, int, int]] = []
    start = 0
    for index in range(1, len(folds) + 1):
        if index == len(folds) or folds[index] != folds[start]:
            windows.append((folds[start], start, index))
            start = index
    return windows


def _series_by_model(
    samples: HorizonSamples, replacement: Mapping[str, tuple[CoverageSeries, ...]]
) -> dict[str, tuple[CoverageSeries, ...]]:
    return {m: replacement.get(m, samples.common[m]) for m in samples.models}


def _seed_rows(samples: HorizonSamples, unit: _Unit) -> list[DmSubsetRow]:
    rows: list[DmSubsetRow] = []
    candidate = unit.candidate
    for index, seed in enumerate(samples.seeds[candidate]):
        one_seed = {candidate: (samples.common[candidate][index],)}
        series = paired_pinball_losses(_series_by_model(samples, one_seed))
        rows += unit.compare(_Subset(DmProfileDimension.SEED, seed=seed), series)
    return rows


def _tau_rows(samples: HorizonSamples, unit: _Unit) -> list[DmSubsetRow]:
    rows: list[DmSubsetRow] = []
    for level in samples.levels:
        series = paired_pinball_losses(_series_by_model(samples, {}), level=level)
        rows += unit.compare(_Subset(DmProfileDimension.TAU, level=level), series)
    return rows


def _seed_fractions(
    rows: Sequence[DmSubsetRow], comparators: Sequence[str]
) -> tuple[SeedFractionRow, ...]:
    fractions: list[SeedFractionRow] = []
    for comparator in comparators:
        seed_rows = [
            row
            for row in rows
            if row.dimension is DmProfileDimension.SEED and row.comparator == comparator
        ]
        undefined = sum(1 for row in seed_rows if row.status is SubsetStatus.UNDEFINED)
        rejecting = sum(1 for row in seed_rows if row.rejected is True)
        tested = len(seed_rows) - undefined
        fractions.append(
            SeedFractionRow(
                comparator=comparator,
                n_seeds=len(seed_rows),
                n_rejecting=rejecting,
                n_undefined=undefined,
                fraction_rejecting=rejecting / tested if tested else None,
            )
        )
    return tuple(fractions)
