"""Serviço de domínio `H1GatePower` — probabilidade exata de reprovar o gate H1 (Stage 6.5).

stdlib-only (concept 6.5 §4 "Domínio", D6; ADR `6_5_0006` item 5 e
`[decision:E] 6.5-POWER`; doc §8.5 "cálculo próprio, binomial e multinomial
exatas"). Sob um cenário de desvio (`TailDeviation`: taxas verdadeiras p_l e p_u
de violação por cauda), os n pontos caem em três células — abaixo de q̂_{τ_l}
(L), acima de q̂_{τ_u} (U) e no meio — com (L, U, meio) ~ Multinomial(n; p_l,
p_u, 1 - p_l - p_u). O gate **passa** quando as duas bandas de Wilson ao nível
do gate contêm as nominais, então

    P(passar) = Σ_{l∈A_l} P(L = l) · Σ_{u∈A_u, u ≤ n-l} P(U = u | L = l),

com U | L = l ~ Binomial(n - l, p_u/(1 - p_l)) (decomposição condicional da
multinomial) e A_l, A_u os conjuntos de contagens aceitas, obtidos varrendo
c = 0..n com o `WilsonBand` (dono da banda; n + 1 chamadas por cauda). As pmfs
são calculadas em escala log por `math.lgamma`; só as contagens aceitas entram
(≈ 50 x 50 termos em n ≈ 1 500), sem a soma dupla O(n²).

As nominais saem de `violation_rate_for` (cauda inferior `(τ_l,)`, superior
`(τ_u,)`), nunca `1 - τ` escrito de novo. **O poder ignora a degeneração** (o
limiar de degeneração do gate não entra: o cenário fala só das taxas de
violação) e assume hits independentes — para h > 1 ele é otimista (doc §4.4); o
`H1Result` declara as duas coisas.
"""

from __future__ import annotations

import math

from financial_forecasting.features.evaluation.domain.services.wilson_band import WilsonBand
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    validate_positive_int,
)
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitKind,
    violation_rate_for,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    H1GateSpec,
    TailDeviation,
)

_BAND_HORIZON = 1
"""Horizonte passado ao `WilsonBand` na varredura: só a aceitação importa (o aviso não)."""


def accepted_counts(*, n: int, nominal: float, band_level: float) -> tuple[int, ...]:
    """Contagens c em 0..n cuja banda de Wilson contém `nominal` (dono: `WilsonBand`)."""
    return tuple(
        count
        for count in range(n + 1)
        if WilsonBand.evaluate(
            horizon=_BAND_HORIZON, count=count, n=n, nominal=nominal, band_level=band_level
        ).contains_nominal
    )


def _log_binomial_pmf(count: int, trials: int, rate: float) -> float:
    return (
        math.lgamma(trials + 1)
        - math.lgamma(count + 1)
        - math.lgamma(trials - count + 1)
        + count * math.log(rate)
        + (trials - count) * math.log1p(-rate)
    )


class H1GatePower:
    """Probabilidade exata de reprovar o gate H1 sob um cenário de desvio."""

    @staticmethod
    def failure_probability(*, n: int, spec: H1GateSpec, deviation: TailDeviation) -> float:
        """1 - P(as duas bandas contêm as nominais) em n pontos (ver docstring do módulo).

        Raises:
            ValueError: `n` não-`int`, `bool` ou < 1.
        """
        validate_positive_int(n, field="n")
        lower_nominal = violation_rate_for(HitKind.LOWER_TAIL, (spec.lower_level,))
        upper_nominal = violation_rate_for(HitKind.UPPER_TAIL, (spec.upper_level,))
        lower_accepted = accepted_counts(
            n=n, nominal=lower_nominal, band_level=spec.gate_band_level
        )
        upper_accepted = accepted_counts(
            n=n, nominal=upper_nominal, band_level=spec.gate_band_level
        )
        p_lower = deviation.lower_rate
        p_upper_given = deviation.upper_rate / (1.0 - p_lower)
        terms: list[float] = []
        for lower in lower_accepted:
            remaining = n - lower
            weight = math.exp(_log_binomial_pmf(lower, n, p_lower))
            inner = math.fsum(
                math.exp(_log_binomial_pmf(upper, remaining, p_upper_given))
                for upper in upper_accepted
                if upper <= remaining
            )
            terms.append(weight * inner)
        passing = math.fsum(terms)
        return min(1.0, max(0.0, 1.0 - passing))
