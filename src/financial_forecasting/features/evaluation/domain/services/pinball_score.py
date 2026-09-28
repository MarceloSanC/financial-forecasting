"""Serviço de domínio `PinballScore` — perda pinball por nível e na grade (doc §3.1).

Implementação de **registro** (ADR `6_1_0001`; ADR `0_0_0009`: pinball é a métrica
primária), stdlib-only. Convenções (concept 6.1 I4/I6):

- rho_τ(u) = u·(τ - 1{u < 0}), com u = y - q — escala rho_τ, **sem fator 2** (é a de
  `sklearn.metrics.mean_pinball_loss`, com `alpha` = nível);
- P̄_τ = média de rho_τ sobre os T pontos; P̄_G = média **simples** dos P̄_τ (pesos
  iguais sobre os K níveis);
- L_t = média dos K rho_τ do ponto t (insumo da 6.2) — a média dos L_t é P̄_G;
- empates são irrelevantes (rho_τ(0) = 0 dos dois lados).

Toda série é pontuada sobre `series.scored_values(i)` — o vetor pós-guardrail (I3).
`mean_pinball` é a mesma função de série que o `FakeScoringBackend` delega (ADR
`6_1_0001` item 4); a validação de entrada mora no validador único (C7).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from financial_forecasting.features.evaluation.domain.services.scoring_input_validation import (
    validate_finite,
    validate_level,
    validate_pinball_inputs,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)

_MIN_LEVELS = 2


def pinball_loss(*, realized: float, quantile: float, level: float) -> float:
    """rho_τ(y - q) de um ponto; `level ∉ (0, 1)` ergue `ValueError` (C7)."""
    validate_level(level)
    validate_finite("pinball point", (realized, quantile))
    residual = realized - quantile
    return level * residual if residual >= 0.0 else (level - 1.0) * residual


def mean_pinball(*, realized: Sequence[float], quantiles: Sequence[float], level: float) -> float:
    """P̄_τ — média de rho_τ sobre a série; entrada inválida ergue `ValueError` (C7)."""
    validate_pinball_inputs(realized, quantiles, level)
    losses = (
        pinball_loss(realized=y, quantile=q, level=level)
        for y, q in zip(realized, quantiles, strict=True)
    )
    return math.fsum(losses) / len(realized)


@dataclass(frozen=True)
class PinballReport:
    """Pinball de uma série x horizonte: P̄_τ por nível e P̄_G da grade.

    Campos:
        horizon: horizonte da série de origem.
        n_points: T — todas as linhas (proper score: nenhuma exclusão).
        per_level: `(τ_k, P̄_τk)` na ordem da grade (K ≥ 2).
        grid_mean: P̄_G, média simples dos P̄_τk.
    """

    horizon: int
    n_points: int
    per_level: tuple[tuple[float, float], ...]
    grid_mean: float

    def __post_init__(self) -> None:
        """C4: relatório mal-formado ergue."""
        if len(self.per_level) < _MIN_LEVELS:
            raise ValueError(
                f"a PinballReport needs K >= {_MIN_LEVELS} levels, got {len(self.per_level)}"
            )
        if self.n_points < 1:
            raise ValueError(f"a PinballReport needs n_points >= 1, got {self.n_points}")


class PinballScore:
    """Pinball sobre uma `CoverageSeries` (pesos iguais na grade)."""

    @staticmethod
    def per_point_losses(series: CoverageSeries) -> tuple[float, ...]:
        """L_t = média dos K rho_τ do ponto t, para t = 1..T (insumo da 6.2)."""
        size = len(series.levels)
        return tuple(
            math.fsum(
                pinball_loss(realized=y, quantile=q, level=level)
                for level, q in zip(series.levels, series.scored_values(index), strict=True)
            )
            / size
            for index, y in enumerate(series.realized)
        )

    @staticmethod
    def score(series: CoverageSeries) -> PinballReport:
        """P̄_τ por nível (via `mean_pinball` na coluna do nível) e P̄_G."""
        per_level = tuple(
            (
                level,
                mean_pinball(
                    realized=series.realized,
                    quantiles=[series.scored_values(i)[k] for i in range(series.n_points)],
                    level=level,
                ),
            )
            for k, level in enumerate(series.levels)
        )
        grid_mean = math.fsum(value for _, value in per_level) / len(per_level)
        return PinballReport(
            horizon=series.horizon,
            n_points=series.n_points,
            per_level=per_level,
            grid_mean=grid_mean,
        )
