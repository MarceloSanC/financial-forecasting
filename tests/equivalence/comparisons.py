"""Comparações da equivalência: A1, A2, sentido e DM (Stage 8.2; regras puras).

Concept 8.2 D8, D12, D13; doc §5.4-§5.5. As métricas (m_novo e m_A) saem dos serviços de
domínio existentes — `pinball_score.mean_pinball`, `coverage_series.is_inside_closed`,
`wilson_band.wilson_interval`; nenhuma métrica nova (concept §12 item vi).

- **A1** (D13): todo ponto de T∩ com |y_novo - y_ant| ≤ 2⁻⁵³·|y_ant| (y_ant = 0 ⇒ igualdade
  exata); contagem fora e max |Δ|;
- **A2** (D12 e): |m_A - m_ant| ≤ max(1e-9·max(|m_A|, |m_ant|, u_q), 2⁻⁵³·|m_ant|), com u_q
  por grandeza (pinball = a própria pinball; MPIW = média de |largura|; PICP = 1); amostra
  não reconstruível (`n_samples`/`n_obs` ≠ pontos lidos) → `not_realizable`;
- **sentido** (doc §5.5): sinal com zero exato como sinal próprio; lado do nominal do PICP
  80 % contra a banda de Wilson 95 %; DM com d̄ normalizado para candidato - baseline e
  rejeição = p não ajustado ≤ alpha do lado (D8).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from financial_forecasting.features.evaluation.domain.services.pinball_score import (
    mean_pinball,
)
from financial_forecasting.features.evaluation.domain.services.wilson_band import (
    wilson_interval,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    is_inside_closed,
)
from tests.equivalence.comparison_set import (
    A1_HALF_ULP,
    NOMINAL_80,
    R2_RELATIVE,
    STORAGE_HALF_ULP_DOUBLE,
    WILSON_BAND_LEVEL,
)


class RawStatus(StrEnum):
    """A classificação recomputada de uma comparação (antes da explicação da §5.6)."""

    WITHIN_TOLERANCE = "within_tolerance"
    OUT_OF_TOLERANCE = "out_of_tolerance"
    NOT_REALIZABLE = "not_realizable"
    EMPTY_INTERSECTION = "empty_intersection"
    SAME_SENSE = "same_sense"
    DIVERGENT_SENSE = "divergent_sense"


# --- A1 -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class A1Result:
    """A1 de um horizonte: pontos em T∩, fora da tolerância e max |Δ|."""

    n_points: int
    n_out: int
    max_abs_diff: float | None
    status: RawStatus


def a1_within(y_new: float, y_prior: float) -> bool:
    """|y_novo - y_ant| ≤ 2⁻⁵³·|y_ant| (y_ant = 0 ⇒ igualdade exata)."""
    return abs(y_new - y_prior) <= A1_HALF_ULP * abs(y_prior)


def a1_check(pairs: Sequence[tuple[float, float]]) -> A1Result:
    """A1 sobre os pares (y_novo, y_ant) de T∩ de um horizonte."""
    if not pairs:
        return A1Result(0, 0, None, RawStatus.EMPTY_INTERSECTION)
    n_out = sum(not a1_within(new, prior) for new, prior in pairs)
    max_abs_diff = max(abs(new - prior) for new, prior in pairs)
    status = RawStatus.WITHIN_TOLERANCE if n_out == 0 else RawStatus.OUT_OF_TOLERANCE
    return A1Result(len(pairs), n_out, max_abs_diff, status)


# --- A2 -----------------------------------------------------------------------------------


def u_q_pinball(pinball: float) -> float:
    """u_q da pinball por nível: média de |termo| — os termos são ≥ 0, logo a própria pinball."""
    return abs(pinball)


def u_q_mpiw(widths: Sequence[float]) -> float:
    """u_q do MPIW: média de |largura|."""
    return math.fsum(abs(width) for width in widths) / len(widths)


U_Q_PICP: float = 1.0
"""u_q de uma cobertura (adimensional limitada)."""


def a2_tolerance(*, m_a: float, m_ant: float, u_q: float) -> float:
    """max(1e-9·max(|m_A|, |m_ant|, u_q), 2⁻⁵³·|m_ant|) — D12 e."""
    r2 = R2_RELATIVE * max(abs(m_a), abs(m_ant), u_q)
    return max(r2, STORAGE_HALF_ULP_DOUBLE * abs(m_ant))


@dataclass(frozen=True)
class A2Result:
    """A2 de uma grandeza: m_A, m_ant, |Δ|, tolerância e classificação."""

    m_a: float | None
    m_ant: float
    abs_diff: float | None
    tolerance: float | None
    status: RawStatus


def a2_compare(*, m_a: float, m_ant: float, u_q: float, n_recorded: int, n_points: int) -> A2Result:
    """m_A contra m_ant; a amostra do anterior tem de ser a reconstruída (`n_recorded`)."""
    if n_recorded != n_points:
        return A2Result(None, m_ant, None, None, RawStatus.NOT_REALIZABLE)
    tolerance = a2_tolerance(m_a=m_a, m_ant=m_ant, u_q=u_q)
    diff = abs(m_a - m_ant)
    status = RawStatus.WITHIN_TOLERANCE if diff <= tolerance else RawStatus.OUT_OF_TOLERANCE
    return A2Result(m_a, m_ant, diff, tolerance, status)


# --- métricas pelo código novo (m_novo e m_A) --------------------------------------------


def pinball_at(realized: Sequence[float], quantiles: Sequence[float], level: float) -> float:
    """P̄_τ pelo `mean_pinball` do domínio."""
    return mean_pinball(realized=realized, quantiles=quantiles, level=level)


@dataclass(frozen=True)
class PairMeasures:
    """PICP, MPIW e insumos (cobertos, pontos, larguras) de um par numa série."""

    covered: int
    n_points: int
    picp: float
    mpiw: float
    widths: tuple[float, ...]


def pair_measures(
    realized: Sequence[float], lows: Sequence[float], highs: Sequence[float]
) -> PairMeasures:
    """Cobertura pelo intervalo fechado do domínio (`is_inside_closed`) e largura média."""
    if not realized or not (len(realized) == len(lows) == len(highs)):
        raise ValueError("pair measures need aligned, non-empty series")
    covered = sum(
        is_inside_closed(y, low, high) for y, low, high in zip(realized, lows, highs, strict=True)
    )
    widths = tuple(high - low for low, high in zip(lows, highs, strict=True))
    n = len(realized)
    return PairMeasures(covered, n, covered / n, math.fsum(widths) / n, widths)


# --- sentido -----------------------------------------------------------------------------


def sign(value: float) -> int:
    """-1, 0 ou +1 — o zero exato é sinal próprio."""
    return (value > 0) - (value < 0)


def signed_delta(m_new: float, m_a: float) -> float:
    """Delta com sinal m_novo - m_A (EQ-DESC: reportado, sem limiar)."""
    return m_new - m_a


def side_of_nominal(
    *, count: float, n: float, nominal: float = NOMINAL_80, band_level: float = WILSON_BAND_LEVEL
) -> str:
    """Posição do nominal frente à banda de Wilson da cobertura: `below`, `inside`, `above`.

    `count` pode ser real (média de contagens entre seeds). `inside` = o veredito
    `lower ≤ nominal ≤ upper` do `WilsonBandReport`.
    """
    lower, upper = wilson_interval(count=count, n=n, band_level=band_level)
    if nominal < lower:
        return "below"
    if nominal > upper:
        return "above"
    return "inside"


def sense_cell(new: object, prior: object) -> RawStatus:
    """Igual ou divergente — comparação categórica de uma célula de sentido."""
    return RawStatus.SAME_SENSE if new == prior else RawStatus.DIVERGENT_SENSE


# --- DM (D8) -------------------------------------------------------------------------------

_CONVENTIONS = {"candidate_minus_baseline": 1.0, "baseline_minus_candidate": -1.0}


def normalized_mean_diff(value: float, convention: str) -> float:
    """d̄ normalizado para perda(candidato) - perda(baseline), pela convenção do lado.

    Raises:
        ValueError: convenção desconhecida.
    """
    if convention not in _CONVENTIONS:
        raise ValueError(f"unknown DM sign convention {convention!r}")
    return _CONVENTIONS[convention] * value


def dm_rejected(p_value: float, alpha: float) -> bool:
    """Rejeição ao alpha do lado com o p NÃO ajustado (sem Holm — D8)."""
    return p_value <= alpha


def dm_sense(
    *, mean_diff: float, convention: str, p_value: float, alpha: float
) -> tuple[int, bool]:
    """(sinal de d̄ normalizado, rejeição) de um lado."""
    return sign(normalized_mean_diff(mean_diff, convention)), dm_rejected(p_value, alpha)
