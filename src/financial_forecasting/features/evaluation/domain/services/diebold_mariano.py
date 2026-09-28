"""Serviço de domínio `DieboldMariano` — teste DM unilateral com a correção HLN (doc §6.1, §6.3).

Implementação **de registro**, stdlib-only (concept 6.2 §4, I4/I5, C2/C3/C8; ADR
`6_2_0003` itens 1 e 3; ADR `0_0_0056`). Semântica = a do oráculo R `forecast::dm.test`
com `alternative = "less"`, `power = 1` sobre as perdas já calculadas (doc §11.3,
convenções #14/#14b):

- d_t = L_cand,t - L_comp,t; d̄ = Σd_t/T (`math.fsum`); d̄ < 0 favorece o candidato;
- gamma_k = Σ_{t=k}^{T-1} (d_t - d̄)(d_{t-k} - d̄) / T (divisor T);
- var̂(d̄) = (gamma_0 + 2·Σ_{k=1}^{h-1} w_k·gamma_k) / T, com w_k = 1 (retangular, o "acf" do R —
  registro) ou w_k = 1 - k/h (Bartlett — sensibilidade);
- var̂ ≤ 0 com h > 1 → recalcula **tudo** com h = 1 (variância e fator HLN) e marca
  `fallback_applied` — o fallback do `dm.test`; var̂ ≤ 0 com h = 1 → `ValueError`
  ("Variance of DM statistic is zero", a mensagem do R);
- S1* = HLN(T, h)·d̄/√var̂, HLN = ((T + 1 - 2h + h(h - 1)/T)/T)^{1/2} (HLN 1997, Eq. 9);
- p = P(t_{T-1} ≤ S1*) por `student_t_cdf` (ADR `6_2_0002`) — H1: E[d] < 0.

Duas divergências deliberadas do R: **T > h** é exigido (com h = T a variância
retangular e o fator HLN são identicamente 0 — ADR `6_2_0001`) e **perda negativa** é
recusada (o R pontuaria |L|). A validação de entrada mora num validador único,
`validate_dm_request`, chamado pelo primitivo, pelo fake e pelo adapter do port
`InferenceBackend` (padrão `scoring_input_validation` da 6.1). Ele fica neste módulo, ao
lado do enum que confere, para não criar ciclo de import (technical 6.2 §1).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from financial_forecasting.features.evaluation.domain.services.student_t import student_t_cdf
from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._paired_inputs import (
    check_horizon,
    check_loss,
    check_points,
    differential,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)


class DmVarianceEstimator(StrEnum):
    """Estimador da variância de longo prazo de d̄ (doc §6.1; convenção #14)."""

    RECTANGULAR = "rectangular"  # "acf" do R — registro
    BARTLETT = "bartlett"  # sensibilidade


def validate_dm_request(
    *,
    candidate_losses: Sequence[float],
    comparator_losses: Sequence[float],
    horizon: int,
    variance_estimator: DmVarianceEstimator,
) -> None:
    """Validador único do DM (primitivo, fake e adapter) — C3.

    As regras de horizonte, T e perda são as do VO (`_paired_inputs`, dono único).

    Raises:
        ValueError: tamanhos diferentes; `horizon` não-int, `bool` ou < 1; T < 2 ou
            T ≤ h; perda não-finita, não-número, `bool` ou negativa; estimador fora de
            `DmVarianceEstimator` (string crua inclusive).
    """
    n_points = len(candidate_losses)
    if len(comparator_losses) != n_points:
        raise ValueError(
            "candidate and comparator losses must have the same length, got "
            f"{n_points} and {len(comparator_losses)}"
        )
    check_horizon(horizon)
    check_points(n_points, horizon)
    for name, losses in (("candidate", candidate_losses), ("comparator", comparator_losses)):
        for index, loss in enumerate(losses):
            check_loss(loss, where=f"{name}, point {index}")
    if not isinstance(variance_estimator, DmVarianceEstimator):
        raise ValueError(
            f"variance_estimator must be a DmVarianceEstimator, got {variance_estimator!r}"
        )


@dataclass(frozen=True)
class DieboldMarianoResult:
    """Resultado do DM unilateral (H1: o candidato tem perda esperada menor).

    Campos:
        horizon: h pedido.
        horizon_used: h efetivo (1 se houve fallback).
        fallback_applied: `True` ⇔ `horizon_used != horizon`.
        variance_estimator: estimador de var̂(d̄).
        n_points: T.
        mean_differential: d̄ (< 0 favorece o candidato).
        long_run_variance: var̂(d̄) > 0.
        statistic: S1*.
        degrees_of_freedom: T - 1.
        p_value: P(t_{T-1} ≤ S1*), em [0, 1].

    Raises:
        ValueError: combinação incoerente (I5; C8), na construção.
    """

    horizon: int
    horizon_used: int
    fallback_applied: bool
    variance_estimator: DmVarianceEstimator
    n_points: int
    mean_differential: float
    long_run_variance: float
    statistic: float
    degrees_of_freedom: int
    p_value: float

    def __post_init__(self) -> None:
        """I5: horizonte efetivo, graus de liberdade, variância, estatística e p-valor."""
        check_horizon(self.horizon)
        check_points(self.n_points, self.horizon)
        if self.horizon_used not in (self.horizon, 1):
            raise ValueError(
                f"horizon_used must be the horizon ({self.horizon}) or 1, got {self.horizon_used}"
            )
        if not isinstance(self.fallback_applied, bool):
            raise ValueError(f"fallback_applied must be a bool, got {self.fallback_applied!r}")
        if self.fallback_applied != (self.horizon_used != self.horizon):
            raise ValueError(
                "fallback_applied must hold exactly when horizon_used != horizon, got "
                f"fallback_applied={self.fallback_applied}, horizon={self.horizon}, "
                f"horizon_used={self.horizon_used}"
            )
        if not isinstance(self.variance_estimator, DmVarianceEstimator):
            raise ValueError(
                f"variance_estimator must be a DmVarianceEstimator, got {self.variance_estimator!r}"
            )
        if self.degrees_of_freedom != self.n_points - 1:
            raise ValueError(
                f"degrees_of_freedom must be n_points - 1 = {self.n_points - 1}, got "
                f"{self.degrees_of_freedom}"
            )
        if not is_finite_number(self.long_run_variance) or self.long_run_variance <= 0.0:
            raise ValueError(
                f"long_run_variance must be finite and > 0, got {self.long_run_variance!r}"
            )
        if not is_finite_number(self.mean_differential):
            raise ValueError(f"mean_differential must be finite, got {self.mean_differential!r}")
        if not is_finite_number(self.statistic):
            raise ValueError(f"statistic must be finite, got {self.statistic!r}")
        if not is_finite_number(self.p_value) or not 0.0 <= self.p_value <= 1.0:
            raise ValueError(f"p_value must be in [0, 1], got {self.p_value!r}")


def diebold_mariano(
    *,
    candidate_losses: Sequence[float],
    comparator_losses: Sequence[float],
    horizon: int,
    variance_estimator: DmVarianceEstimator = DmVarianceEstimator.RECTANGULAR,
) -> DieboldMarianoResult:
    """DM/HLN unilateral sobre duas séries de perdas pareadas (primitivo do serviço e do fake).

    Raises:
        ValueError: entrada inválida (C3, via `validate_dm_request`) ou variância de
            longo prazo ≤ 0 com h = 1 (depois do fallback, se h > 1).
    """
    validate_dm_request(
        candidate_losses=candidate_losses,
        comparator_losses=comparator_losses,
        horizon=horizon,
        variance_estimator=variance_estimator,
    )
    differences = differential(candidate_losses, comparator_losses)
    n_points = len(differences)
    mean = math.fsum(differences) / n_points
    deviations = [value - mean for value in differences]
    horizon_used = horizon
    variance = _long_run_variance(deviations, horizon, variance_estimator)
    if variance <= 0.0 and horizon > 1:
        horizon_used = 1
        variance = _long_run_variance(deviations, horizon_used, variance_estimator)
    if variance <= 0.0:
        raise ValueError("Variance of DM statistic is zero")
    statistic = _hln_factor(n_points, horizon_used) * mean / math.sqrt(variance)
    return DieboldMarianoResult(
        horizon=horizon,
        horizon_used=horizon_used,
        fallback_applied=horizon_used != horizon,
        variance_estimator=variance_estimator,
        n_points=n_points,
        mean_differential=mean,
        long_run_variance=variance,
        statistic=statistic,
        degrees_of_freedom=n_points - 1,
        p_value=student_t_cdf(statistic, float(n_points - 1)),
    )


class DieboldMariano:
    """DM do candidato contra um comparador sobre uma `PairedLossSeries` (um horizonte)."""

    @staticmethod
    def compare(
        series: PairedLossSeries,
        *,
        candidate: str,
        comparator: str,
        variance_estimator: DmVarianceEstimator = DmVarianceEstimator.RECTANGULAR,
    ) -> DieboldMarianoResult:
        """DM(candidato, comparador) no horizonte da série.

        Raises:
            ValueError: nome fora de `series.models` ou candidato = comparador (C2); e os
                erros do primitivo (C3).
        """
        if candidate == comparator:
            raise ValueError(f"candidate and comparator must differ, got {candidate!r} twice")
        return diebold_mariano(
            candidate_losses=series.losses_of(candidate),
            comparator_losses=series.losses_of(comparator),
            horizon=series.horizon,
            variance_estimator=variance_estimator,
        )


def _long_run_variance(
    deviations: Sequence[float], horizon: int, variance_estimator: DmVarianceEstimator
) -> float:
    """var̂(d̄) = (gamma_0 + 2·Σ_{k=1}^{h-1} w_k·gamma_k)/T sobre os desvios d_t - d̄."""
    n_points = len(deviations)
    terms = [_autocovariance(deviations, 0)]
    for lag in range(1, horizon):
        weight = (
            1.0 if variance_estimator is DmVarianceEstimator.RECTANGULAR else 1.0 - lag / horizon
        )
        terms.append(2.0 * weight * _autocovariance(deviations, lag))
    return math.fsum(terms) / n_points


def _autocovariance(deviations: Sequence[float], lag: int) -> float:
    """gamma_lag = Σ_{t=lag}^{T-1} (d_t - d̄)(d_{t-lag} - d̄) / T (divisor T, como o R `acf`)."""
    n_points = len(deviations)
    return math.fsum(deviations[t] * deviations[t - lag] for t in range(lag, n_points)) / n_points


def _hln_factor(n_points: int, horizon: int) -> float:
    """Correção HLN: ((T + 1 - 2h + h(h - 1)/T)/T)^{1/2} (HLN 1997, Eq. 9)."""
    return math.sqrt((n_points + 1 - 2 * horizon + horizon * (horizon - 1) / n_points) / n_points)
