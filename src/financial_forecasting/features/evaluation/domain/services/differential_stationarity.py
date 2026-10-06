"""Serviço de domínio `DifferentialStationarity` — diagnóstico de estacionariedade de d_t (6.6).

Implementação de **registro**, stdlib-only (concept 6.6 §4, D2, I1, I4; ADR `6_6_0001`).
É o diagnóstico que a B-FOLDS pré-registra (doc §6.8; Diebold 2015 §2.2: "plot the loss
differential series, examine its sample autocorrelations ... test it for ... structural
breaks"), com as regras congeladas na r1 (`StationarityParameters`):

- **ACF** (`min_floor_10_log10_T_T_minus_1`): rho_k = Σ_{t=k}^{T-1} (d_t - d̄)(d_{t-k} - d̄)
  / Σ_t (d_t - d̄)², k = 1..L, L = min(⌊10·log10 T⌋, T - 1) — o default do `acf` do
  statsmodels 0.15 (`adjusted=False`), o oráculo;
- **CUSUM da média** (`cusum_mean_dm_primary_variance_kolmogorov_v1`): S_k = Σ_{t≤k}
  (d_t - d̄), B = max_k |S_k| / (T·√var̂(d̄)), com var̂(d̄) da `dm_long_run_variance` (a do
  DM primário: estimador do plano até h - 1, fallback h = 1 — uma escrita só, I1); p-valor
  pela distribuição de Kolmogorov (sup |ponte browniana|); rejeita ⇔ p ≤ alpha; a quebra é o
  alvo em argmax |S_k| (o primeiro, em empate). Em h = 1 coincide com o `sup_b`/`pval`
  do `breaks_cusumolsresid(d - d̄, ddof=0)` do statsmodels;
- d_t constante → relatório `undefined` (`constant_differential`): ACF e CUSUM sem valor.

Um relatório por par de `PairedLossSeries.model_pairs()`, d_t = L_a - L_b (a série d_t
vai junto, insumo do plot da 8.3). Perfil: nunca decide o veredito (doc §8.6).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
    dm_long_run_variance,
)
from financial_forecasting.features.evaluation.domain.value_objects._paired_inputs import (
    check_points,
    is_constant,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.profile_parameters import (
    StationarityParameters,
)

CONSTANT_DIFFERENTIAL: Final = "constant_differential"
"""Motivo de indefinição: d_t constante (sem variância, ACF e CUSUM sem valor)."""

_THETA_SWITCH: Final = 1.18  # abaixo, a série teta converge mais rápido que a alternada
_SERIES_EPSILON: Final = 1e-17
_MAX_TERMS: Final = 100


class StationarityStatus(StrEnum):
    """Se o diagnóstico de um par foi calculado."""

    COMPUTED = "computed"
    UNDEFINED = "undefined"


def acf_max_lag(n_points: int) -> int:
    """L = min(⌊10·log10 T⌋, T - 1) — o default de lags do `acf` do statsmodels.

    Raises:
        ValueError: T não-`int`, `bool` ou < 2.
    """
    if isinstance(n_points, bool) or not isinstance(n_points, int) or n_points < 2:  # noqa: PLR2004
        raise ValueError(f"n_points must be an int >= 2, got {n_points!r}")
    return min(int(10 * math.log10(n_points)), n_points - 1)


def sample_acf(values: Sequence[float], max_lag: int) -> tuple[float, ...]:
    """rho_1..rho_L da série (divisor comum, `adjusted=False`).

    Raises:
        ValueError: série constante (sem variância) ou `max_lag` fora de 1..T - 1.
    """
    n_points = len(values)
    if isinstance(max_lag, bool) or not isinstance(max_lag, int) or not 1 <= max_lag < n_points:
        raise ValueError(f"max_lag must be an int in 1..{n_points - 1}, got {max_lag!r}")
    if is_constant(values):
        raise ValueError("the ACF of a constant series is undefined")
    mean = math.fsum(values) / n_points
    deviations = [value - mean for value in values]
    denominator = math.fsum(d * d for d in deviations)
    return tuple(
        math.fsum(deviations[t] * deviations[t - lag] for t in range(lag, n_points)) / denominator
        for lag in range(1, max_lag + 1)
    )


def kolmogorov_sf(x: float) -> float:
    """P(K > x), K = sup |ponte browniana| (distribuição de Kolmogorov), em [0, 1].

    x < 1,18: 1 - (√(2π)/x)·Σ_{j≥1} e^{-(2j-1)²π²/(8x²)} (série teta); senão
    2·Σ_{j≥1} (-1)^{j-1} e^{-2j²x²} (alternada) — somadas até o termo ficar abaixo de 1e-17.
    """
    if x <= 0.0:
        return 1.0
    total = 0.0
    if x < _THETA_SWITCH:
        for j in range(1, _MAX_TERMS):
            term = math.exp(-((2 * j - 1) ** 2) * math.pi**2 / (8 * x * x))
            total += term
            if term < _SERIES_EPSILON:
                break
        value = 1.0 - math.sqrt(2 * math.pi) / x * total
    else:
        for j in range(1, _MAX_TERMS):
            term = math.exp(-2 * j * j * x * x)
            total += term if j % 2 else -term
            if term < _SERIES_EPSILON:
                break
        value = 2.0 * total
    return min(1.0, max(0.0, value))


@dataclass(frozen=True)
class CusumBreak:
    """O CUSUM da média de uma série: estatística, p-valor, índice da quebra, h usado."""

    statistic: float
    p_value: float
    break_index: int
    horizon_used: int


def cusum_mean_break(
    differences: Sequence[float], *, horizon: int, variance_estimator: DmVarianceEstimator
) -> CusumBreak | None:
    """B = max_k |S_k| / (T·√var̂(d̄)) e o p-valor de Kolmogorov; `None` se var̂(d̄) ≤ 0.

    Raises:
        ValueError: os da `dm_long_run_variance` (horizonte, T, estimador).
    """
    variance, horizon_used = dm_long_run_variance(
        differences, horizon=horizon, variance_estimator=variance_estimator
    )
    if variance <= 0.0:
        return None
    n_points = len(differences)
    mean = math.fsum(differences) / n_points
    scale = n_points * math.sqrt(variance)
    best_index, best_value, partial = 0, -1.0, 0.0
    for index, value in enumerate(differences):
        partial += value - mean
        if abs(partial) > best_value:
            best_index, best_value = index, abs(partial)
    statistic = best_value / scale
    return CusumBreak(
        statistic=statistic,
        p_value=kolmogorov_sf(statistic),
        break_index=best_index,
        horizon_used=horizon_used,
    )


@dataclass(frozen=True)
class StationarityReport:
    """O diagnóstico de d_t de um par de modelos num horizonte.

    Campos de valor (`acf`, `statistic`, `p_value`, `rejected`, `horizon_used`,
    `break_target_timestamp`) são vazios/`None` quando `status` é `undefined`.
    """

    pair: tuple[str, str]
    horizon: int
    n_points: int
    status: StationarityStatus
    undefined_reason: str | None
    differential: tuple[float, ...]
    target_timestamps: tuple[str, ...]
    max_lag: int
    acf: tuple[float, ...]
    statistic: float | None
    p_value: float | None
    rejected: bool | None
    alpha: float
    horizon_used: int | None
    break_target_timestamp: str | None


class DifferentialStationarity:
    """ACF + CUSUM de d_t por par de modelos da série pareada primária (ADR 6.6.0001)."""

    @staticmethod
    def evaluate(
        series: PairedLossSeries,
        *,
        parameters: StationarityParameters,
        variance_estimator: DmVarianceEstimator,
    ) -> tuple[StationarityReport, ...]:
        """Um relatório por par de `series.model_pairs()`.

        `parameters` chega já válido (o VO é o dono do catálogo das regras).

        Raises:
            ValueError: `parameters`/`variance_estimator` de tipo errado.
        """
        if not isinstance(parameters, StationarityParameters):
            raise ValueError(f"parameters must be a StationarityParameters, got {parameters!r}")
        check_points(series.n_points, series.horizon)
        max_lag = acf_max_lag(series.n_points)
        return tuple(
            _report(series, pair, max_lag, parameters.break_alpha, variance_estimator)
            for pair in series.model_pairs()
        )


def _report(
    series: PairedLossSeries,
    pair: tuple[str, str],
    max_lag: int,
    alpha: float,
    variance_estimator: DmVarianceEstimator,
) -> StationarityReport:
    differential = series.differential(*pair)
    found = (
        None
        if is_constant(differential)
        else cusum_mean_break(
            differential, horizon=series.horizon, variance_estimator=variance_estimator
        )
    )
    return StationarityReport(
        pair=pair,
        horizon=series.horizon,
        n_points=series.n_points,
        status=StationarityStatus.UNDEFINED if found is None else StationarityStatus.COMPUTED,
        undefined_reason=CONSTANT_DIFFERENTIAL if found is None else None,
        differential=differential,
        target_timestamps=series.target_timestamps,
        max_lag=max_lag,
        acf=() if found is None else sample_acf(differential, max_lag),
        statistic=None if found is None else found.statistic,
        p_value=None if found is None else found.p_value,
        rejected=None if found is None else found.p_value <= alpha,
        alpha=alpha,
        horizon_used=None if found is None else found.horizon_used,
        break_target_timestamp=(
            None if found is None else series.target_timestamps[found.break_index]
        ),
    )
