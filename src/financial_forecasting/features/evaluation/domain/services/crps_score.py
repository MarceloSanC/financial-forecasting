"""Serviço de domínio `CrpsScore` — CRPS_Q = 2 x pinball média na grade (doc §3.2).

Implementação de **registro** (ADR `6_1_0001`; ADR `0_0_0009`: CRPS é
complementar), stdlib-only. O CRPS de uma previsão por quantis é aproximado pela
média da perda pinball sobre a grade, com pesos iguais:

    CRPS_Q(y) = (2/K) · Σ_k rho_{τ_k}(y - q̂_{τ_k}) = 2 · (pinball média da grade)

É uma aproximação que depende da grade — por isso todo relatório carrega o rótulo
`CRPS_Q_LABEL` (I4). No Dirac (todos os quantis = x) com grade simétrica,
CRPS_Q = |y - x|, o valor exato do CRPS de uma massa pontual.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from financial_forecasting.features.evaluation.domain.services.pinball_score import (
    pinball_loss,
)
from financial_forecasting.features.evaluation.domain.services.scoring_input_validation import (
    validate_crps_inputs,
    validate_grid_row,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)

CRPS_Q_LABEL: Final = "CRPS_Q = 2 × pinball média na grade (pesos iguais)"  # noqa: RUF001


def crps_quantile(*, realized: float, quantiles: Sequence[float], levels: Sequence[float]) -> float:
    """CRPS_Q de um ponto: (2/K)·Σ_k rho_{τ_k}; grade inválida ergue `ValueError` (C7)."""
    validate_grid_row(quantiles, levels)
    total = math.fsum(
        pinball_loss(realized=realized, quantile=q, level=level)
        for q, level in zip(quantiles, levels, strict=True)
    )
    return 2.0 * total / len(levels)


def mean_crps_quantile(
    *,
    realized: Sequence[float],
    quantile_grid: Sequence[Sequence[float]],
    levels: Sequence[float],
) -> float:
    """Média do CRPS_Q sobre a série; entrada inválida ergue `ValueError` (C7)."""
    validate_crps_inputs(realized, quantile_grid, levels)
    scores = (
        crps_quantile(realized=y, quantiles=row, levels=levels)
        for y, row in zip(realized, quantile_grid, strict=True)
    )
    return math.fsum(scores) / len(realized)


@dataclass(frozen=True)
class CrpsReport:
    """CRPS_Q de uma série x horizonte, sempre com o rótulo da aproximação.

    Campos:
        horizon: horizonte da série de origem.
        n_points: T — todas as linhas (proper score: nenhuma exclusão).
        crps_q: média do CRPS_Q sobre a série.
        label: `CRPS_Q_LABEL` — o nome não pode perder a qualificação "na grade".
    """

    horizon: int
    n_points: int
    crps_q: float
    label: str = CRPS_Q_LABEL


class CrpsScore:
    """CRPS_Q sobre uma `CoverageSeries`, lendo o vetor pós-guardrail (I3)."""

    @staticmethod
    def per_point(series: CoverageSeries) -> tuple[float, ...]:
        """CRPS_Q de cada ponto t = 1..T."""
        return tuple(
            crps_quantile(realized=y, quantiles=series.scored_values(index), levels=series.levels)
            for index, y in enumerate(series.realized)
        )

    @staticmethod
    def score(series: CoverageSeries) -> CrpsReport:
        """Média do CRPS_Q sobre as T linhas, via `mean_crps_quantile`."""
        crps_q = mean_crps_quantile(
            realized=series.realized,
            quantile_grid=[series.scored_values(i) for i in range(series.n_points)],
            levels=series.levels,
        )
        return CrpsReport(horizon=series.horizon, n_points=series.n_points, crps_q=crps_q)
