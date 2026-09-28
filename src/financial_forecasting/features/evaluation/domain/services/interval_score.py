"""Serviço de domínio `IntervalScore` — IS_alpha por par simétrico da grade (doc §3.3).

Implementação de **registro** (ADR `6_1_0001`), stdlib-only. Para o intervalo
central [l, u] de miscobertura alpha (Gneiting & Raftery 2007, Eq. (43)):

    IS_alpha(l, u; y) = (u - l) + (2/alpha)(l - y)·1{y < l} + (2/alpha)(y - u)·1{y > u}

Convenções (concept 6.1 I5/I7): os pares são (τ_k, 1 - τ_k) com τ_k < 0.5, lidos de
`series.symmetric_pairs`; alpha = 2·τ_l e nominal = 1 - 2·τ_l — fórmula única (a forma
`1 - (τ_u - τ_l)` daria 0.10000000000000009 em (0.05, 0.95)). Não escalado e sem WIS
agregado. As médias são sobre **todas** as linhas — proper score, a degeneração não
exclui nada (ADR 0.0.0011); por isso `mean_width` difere do MPIW da cobertura quando
há linha degenerada (D8).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from financial_forecasting.features.evaluation.domain.services.scoring_input_validation import (
    validate_finite,
    validate_interval_bounds,
    validate_interval_inputs,
    validate_miscoverage,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
    pair_miscoverage,
    pair_nominal,
)


def interval_score(*, realized: float, lower: float, upper: float, miscoverage: float) -> float:
    """IS_alpha de um ponto (GR 2007 Eq. (43)); alpha ∉ (0, 1) ou `lower > upper` ergue (C7)."""
    validate_miscoverage(miscoverage)
    validate_interval_bounds(lower, upper)
    validate_finite("realized", (realized,))
    return (
        (upper - lower)
        + _lower_penalty(realized, lower, miscoverage)
        + _upper_penalty(realized, upper, miscoverage)
    )


def mean_interval_score(
    *,
    realized: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float],
    miscoverage: float,
) -> float:
    """Média do IS_alpha sobre a série; entrada inválida ergue `ValueError` (C7)."""
    validate_interval_inputs(realized, lower, upper, miscoverage)
    scores = (
        interval_score(realized=y, lower=low, upper=high, miscoverage=miscoverage)
        for y, low, high in zip(realized, lower, upper, strict=True)
    )
    return math.fsum(scores) / len(realized)


@dataclass(frozen=True)
class PairIntervalScore:
    """IS_alpha de um par simétrico, decomposto nos três termos médios (todas as linhas).

    Campos:
        lower_level / upper_level: o par (τ_l, τ_u) da grade.
        miscoverage: alpha = 2·τ_l.
        nominal: 1 - 2·τ_l.
        mean_width: média de u - l.
        mean_lower_penalty: média de (2/alpha)(l - y)·1{y < l}.
        mean_upper_penalty: média de (2/alpha)(y - u)·1{y > u}.
    """

    lower_level: float
    upper_level: float
    miscoverage: float
    nominal: float
    mean_width: float
    mean_lower_penalty: float
    mean_upper_penalty: float

    def __post_init__(self) -> None:
        """I5/I7: alpha e nominal saem da fórmula única, nunca de `1 - (τ_u - τ_l)`."""
        expected_miscoverage = pair_miscoverage(self.lower_level)
        if self.miscoverage != expected_miscoverage:
            raise ValueError(
                f"miscoverage must be 2 * lower_level = {expected_miscoverage}, "
                f"got {self.miscoverage}"
            )
        expected_nominal = pair_nominal(self.lower_level)
        if self.nominal != expected_nominal:
            raise ValueError(
                f"nominal must be 1 - miscoverage = {expected_nominal}, got {self.nominal}"
            )

    @property
    def mean_score(self) -> float:
        """IS_alpha médio, **definido** como a soma dos três termos médios (I5)."""
        return self.mean_width + self.mean_lower_penalty + self.mean_upper_penalty


@dataclass(frozen=True)
class IntervalScoreReport:
    """IS_alpha de uma série x horizonte, um `PairIntervalScore` por par simétrico."""

    horizon: int
    n_points: int
    per_pair: tuple[PairIntervalScore, ...]

    def __post_init__(self) -> None:
        """C4: relatório mal-formado ergue."""
        if not self.per_pair:
            raise ValueError("an IntervalScoreReport needs at least one symmetric pair")
        if self.n_points < 1:
            raise ValueError(f"an IntervalScoreReport needs n_points >= 1, got {self.n_points}")


class IntervalScore:
    """IS_alpha sobre uma `CoverageSeries`, por par simétrico, lendo o pós-guardrail (I3)."""

    @staticmethod
    def score(series: CoverageSeries) -> IntervalScoreReport:
        """Um `PairIntervalScore` por `series.symmetric_pairs`, médias sobre as T linhas."""
        realized = series.realized
        size = series.n_points
        per_pair: list[PairIntervalScore] = []
        pairs = zip(series.symmetric_pairs, series.symmetric_pair_indices, strict=True)
        for (lower_level, upper_level), (k_low, k_high) in pairs:
            miscoverage = pair_miscoverage(lower_level)
            lower = [series.scored_values(i)[k_low] for i in range(size)]
            upper = [series.scored_values(i)[k_high] for i in range(size)]
            # Mesmo validador único de `mean_interval_score` (C7; ADR 6.1.0001 item 1).
            # A média é decomposta nos três termos (I5) em vez de delegada — o
            # `mean_score` é a soma deles; a ponte com `mean_interval_score` é testada.
            validate_interval_inputs(realized, lower, upper, miscoverage)
            per_pair.append(
                PairIntervalScore(
                    lower_level=lower_level,
                    upper_level=upper_level,
                    miscoverage=miscoverage,
                    nominal=pair_nominal(lower_level),
                    mean_width=math.fsum(high - low for low, high in zip(lower, upper, strict=True))
                    / size,
                    mean_lower_penalty=math.fsum(
                        _lower_penalty(y, low, miscoverage)
                        for y, low in zip(realized, lower, strict=True)
                    )
                    / size,
                    mean_upper_penalty=math.fsum(
                        _upper_penalty(y, high, miscoverage)
                        for y, high in zip(realized, upper, strict=True)
                    )
                    / size,
                )
            )
        return IntervalScoreReport(
            horizon=series.horizon, n_points=series.n_points, per_pair=tuple(per_pair)
        )


def _lower_penalty(realized: float, lower: float, miscoverage: float) -> float:
    return (2.0 / miscoverage) * (lower - realized) if realized < lower else 0.0


def _upper_penalty(realized: float, upper: float, miscoverage: float) -> float:
    return (2.0 / miscoverage) * (realized - upper) if realized > upper else 0.0
