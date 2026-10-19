"""`ConformalCalibrator` — split-CQR assimétrico e NexCP de registro (concept 7.2 §4; ADR 7.2.0002).

Implementação de registro (I1): o MAPIE e o código dos autores são oráculos, nunca
chamados daqui. Por cauda, sobre o calib dedicado de uma unidade (I6, I7):

- escores (I2): E^lo = q̂_lo - y e E^hi = y - q̂_hi, com q̂ do vetor rearranjado;
- alpha exato (I3): alpha_lo = τ_lo e alpha_hi = 1 - τ_hi em `Fraction`, a partir do decimal
  mais curto de cada nível (`exact_level`);
- posto (I3): k = ⌈(n+1)(1-alpha)⌉ inteiro exato; Q̂ = k-ésimo menor escore, empates
  com multiplicidade; k > n ⇒ Q̂ = +∞ (`infinite = True`), nunca cortado em n (C2);
- NexCP (I4): w_i = rho^(n+1-i), i crescente no `target_timestamp` (1 = mais antigo;
  o mais recente pesa rho), com rho exato (`exact_level`); w̃_i = w_i/(Σ_j w_j + 1);
  Q̂ = menor escore R com Σ_{R_j ≤ R} w̃_j ≥ 1 - alpha (empates juntos); massa finita
  < 1 - alpha ⇒ +∞. Com rho = 1 reproduz o posto sem pesos;
- saída (I5): L = q̂_lo - Q̂_lo e U = q̂_hi + Q̂_hi, sem rearranjo, ±∞ permitido.

A referência Beta(n+1-l, l), l = ⌊(n+1)alpha⌋, é só por cauda e só na variante sem
pesos; sem quantis (D7). `exact_level` mora no `CalibrationSet` (o VO confere o
par com ela) e é reexportada aqui.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Literal

from financial_forecasting.features.inference.domain.value_objects.calibration_set import (
    CalibrationSet,
    exact_level,
)

__all__ = [
    "BetaReference",
    "ConformalCalibrator",
    "ConformalVariant",
    "PairCorrection",
    "TailCorrection",
    "beta_reference",
    "exact_level",
    "exact_rho",
    "split_conformal_rank",
    "weighted_conformal_threshold",
]


class ConformalVariant(StrEnum):
    """Variantes do pré-registro; os ids são os do catálogo `[conformal]` (I16, I17)."""

    SPLIT_CQR = "split_cqr_asymmetric_unweighted_v1"
    NEXCP = "nexcp_fixed_geometric_weights_v1"


@dataclass(frozen=True)
class TailCorrection:
    """Correção conformal de uma cauda: Q̂, o posto (sem pesos) e a flag de infinito."""

    tail: Literal["lower", "upper"]
    level: float  # τ da cauda
    alpha: Fraction  # alpha_lo = τ_lo; alpha_hi = 1 - τ_hi (exatos)
    n: int
    rank: int | None  # k = ⌈(n+1)(1-alpha)⌉ na variante sem pesos
    correction: float  # Q̂; +inf quando infinito
    infinite: bool


@dataclass(frozen=True)
class PairCorrection:
    """As duas correções de um par numa variante."""

    variant: ConformalVariant
    rho: float | None  # só NEXCP
    lower: TailCorrection
    upper: TailCorrection

    def limits(self, *, lower: float, upper: float) -> tuple[float, float]:
        """(q̂_lo - Q̂_lo, q̂_hi + Q̂_hi): sem rearranjo, ±inf permitido (I5)."""
        return (lower - self.lower.correction, upper + self.upper.correction)


@dataclass(frozen=True)
class BetaReference:
    """Beta(a, b) = Beta(n+1-l, l) da cobertura condicional da cauda: média e dp."""

    a: int
    b: int
    mean: float
    sd: float


def _check_alpha(alpha: Fraction) -> None:
    if not isinstance(alpha, Fraction) or not 0 < alpha < 1:
        raise ValueError(f"alpha must be a Fraction in (0, 1), got {alpha!r}")


def _check_n(n: int) -> None:
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be an integer >= 1, got {n!r}")


def split_conformal_rank(n: int, alpha: Fraction) -> int:
    """k = ⌈(n+1)(1-alpha)⌉, inteiro exato (I3); pode passar de n (Q̂ = +∞)."""
    _check_n(n)
    _check_alpha(alpha)
    return math.ceil((n + 1) * (1 - alpha))


def beta_reference(n: int, alpha: Fraction) -> BetaReference | None:
    """Beta(n+1-l, l), l = ⌊(n+1)alpha⌋, em forma fechada; `None` quando l = 0 (D7)."""
    _check_n(n)
    _check_alpha(alpha)
    b = math.floor((n + 1) * alpha)
    if b == 0:
        return None
    a = n + 1 - b
    total = a + b
    return BetaReference(
        a=a,
        b=b,
        mean=float(Fraction(a, total)),
        sd=math.sqrt(Fraction(a * b, total * total * (total + 1))),
    )


def weighted_conformal_threshold(
    scores: Sequence[float], weights: Sequence[Fraction], alpha: Fraction
) -> float:
    """Menor escore R com Σ_{R_j ≤ R} w_j / (Σ w + 1) ≥ 1 - alpha; senão +∞ (I4, C2).

    O +1 é o peso do ponto de teste (o átomo em +∞ do `splitCP_LS`); escores
    iguais entram juntos. A comparação é exata: Σ_{R_j ≤ R} w_j ≥ (1 - alpha)(Σ w + 1).
    """
    _check_alpha(alpha)
    if not scores:
        raise ValueError("scores: empty")
    if len(weights) != len(scores):
        raise ValueError(f"weights: {len(weights)} weights for {len(scores)} scores")
    if any(not isinstance(w, Fraction) or w <= 0 for w in weights):
        raise ValueError("weights: every weight must be a positive Fraction")
    if any(not math.isfinite(score) for score in scores):
        raise ValueError("scores: every score must be finite")
    target = (1 - alpha) * (sum(weights, Fraction(0)) + 1)
    order = sorted(range(len(scores)), key=scores.__getitem__)
    cumulative = Fraction(0)
    position = 0
    while position < len(order):
        value = scores[order[position]]
        while position < len(order) and scores[order[position]] == value:
            cumulative += weights[order[position]]
            position += 1
        if cumulative >= target:
            return value
    return math.inf


def exact_rho(rho: float) -> Fraction:
    """rho ∈ (0, 1] tomado exato pelo decimal mais curto: a regra única do rho no `inference`.

    O calibrador e o `validate_command` a chamam e só prefixam a mensagem com o campo.
    """
    try:
        exact = exact_level(rho)
    except ValueError:
        raise ValueError(f"{rho!r} is not a finite number in (0, 1]") from None
    if not 0 < exact <= 1:
        raise ValueError(f"{rho!r} is not in (0, 1]")
    return exact


def _kth_smallest(scores: list[float], rank: int) -> float:
    """k-ésimo menor com multiplicidade; k > n ⇒ +∞ (I3, nunca cortado)."""
    if rank > len(scores):
        return math.inf
    return sorted(scores)[rank - 1]


def _split_tail(
    tail: Literal["lower", "upper"], level: float, alpha: Fraction, scores: list[float]
) -> TailCorrection:
    n = len(scores)
    rank = split_conformal_rank(n, alpha)
    correction = _kth_smallest(scores, rank)
    return TailCorrection(
        tail=tail,
        level=level,
        alpha=alpha,
        n=n,
        rank=rank,
        correction=correction,
        infinite=math.isinf(correction),
    )


def _nexcp_tail(
    tail: Literal["lower", "upper"],
    level: float,
    alpha: Fraction,
    scores: list[float],
    weights: list[Fraction],
) -> TailCorrection:
    correction = weighted_conformal_threshold(scores, weights, alpha)
    return TailCorrection(
        tail=tail,
        level=level,
        alpha=alpha,
        n=len(scores),
        rank=None,
        correction=correction,
        infinite=math.isinf(correction),
    )


class ConformalCalibrator:
    """Calibra as duas caudas de um `CalibrationSet` numa variante."""

    @staticmethod
    def calibrate(
        calib: CalibrationSet, *, variant: ConformalVariant, rho: float | None = None
    ) -> PairCorrection:
        """Correções (Q̂_lo, Q̂_hi) da unidade; só o calib entra (I7)."""
        if not isinstance(variant, ConformalVariant):
            raise ValueError(f"variant: unknown conformal variant {variant!r}")
        if variant is ConformalVariant.SPLIT_CQR and rho is not None:
            raise ValueError(f"rho: the {variant.value} variant takes no rho, got {rho!r}")
        alpha_lo = exact_level(calib.lower_level)
        alpha_hi = 1 - exact_level(calib.upper_level)
        lower_scores = [point.lower - point.realized for point in calib.points]
        upper_scores = [point.realized - point.upper for point in calib.points]
        if variant is ConformalVariant.NEXCP:
            if rho is None:
                raise ValueError("rho: the nexcp variant needs rho in (0, 1]")
            try:
                exact = exact_rho(rho)
            except ValueError as exc:
                raise ValueError(f"rho: {exc}") from None
            n = len(calib.points)
            # i = 1..n em ordem crescente de alvo (garantida pelo VO): o mais recente pesa rho
            weights = [exact ** (n + 1 - i) for i in range(1, n + 1)]
            return PairCorrection(
                variant=variant,
                rho=rho,
                lower=_nexcp_tail("lower", calib.lower_level, alpha_lo, lower_scores, weights),
                upper=_nexcp_tail("upper", calib.upper_level, alpha_hi, upper_scores, weights),
            )
        return PairCorrection(
            variant=variant,
            rho=None,
            lower=_split_tail("lower", calib.lower_level, alpha_lo, lower_scores),
            upper=_split_tail("upper", calib.upper_level, alpha_hi, upper_scores),
        )
