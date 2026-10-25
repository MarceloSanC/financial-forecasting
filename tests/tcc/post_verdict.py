"""Regras puras das análises pós-veredito do TCC: perfil pontual (D1) e média das sementes (D3).

Plano de fechamento (#237, `docs/tcc/PLANO-FECHAMENTO.md` §7); issue #243. Calculado depois
do veredito; não altera o veredito. As métricas saem dos serviços de domínio do gold
(`PinballScore`, `paired_pinball_losses`, `DieboldMariano`, `wilson_interval` e os
predicados de cobertura de `coverage_series`); aqui só moram as regras que eles não têm:

- **D1** — `point_profile`: RMSE e MAE da mediana (τ = 0,5, vetor pós-guardrail) contra o
  realizado e a contagem de acertos de sinal (acerto ⇔ mediana·realizado > 0; ponto com
  mediana ou realizado exatamente 0 não é acerto e é contado como empate);
  `median_is_identically_zero`: o critério de exclusão da acurácia direcional;
  `seed_mean`: a média simples entre sementes de uma medida por semente (B-SEEDS: média de
  métricas, não de previsões);
- **D3** — `seed_ensemble`: em cada ponto e nível, a média aritmética (`math.fsum` / S) dos
  quantis pós-guardrail das S sementes, sem rearranjo (a média de grades monotônicas é
  monotônica; grade não monotônica ergue, nunca é corrigida); `tail_rates`: violação da
  cauda inferior (y ≤ q_τl), da superior (y > q_τu) e PICP do par (intervalo fechado),
  pelos predicados únicos do gold.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    MEDIAN_LEVEL,
    CoverageSeries,
    is_at_or_below,
    is_inside_closed,
)


@dataclass(frozen=True)
class PointProfile:
    """Perfil pontual da mediana de uma série (uma semente).

    Campos:
        n_points: T.
        rmse: raiz da média de (y - m)².
        mae: média de |y - m|.
        hits: pontos com m·y > 0.
        ties: pontos com m = 0 ou y = 0 (nem acerto nem erro de sinal; contam como não
            acerto no denominador T).
    """

    n_points: int
    rmse: float
    mae: float
    hits: int
    ties: int


def medians(series: CoverageSeries) -> tuple[float, ...]:
    """A coluna τ = 0,5 do vetor pontuado (pós-guardrail) de cada ponto.

    Raises:
        ValueError: a grade da série não tem o nível 0,5.
    """
    if MEDIAN_LEVEL not in series.levels:
        raise ValueError(f"the grid {series.levels} has no median level {MEDIAN_LEVEL}")
    k = series.levels.index(MEDIAN_LEVEL)
    return tuple(series.scored_values(i)[k] for i in range(series.n_points))


def point_profile(series: CoverageSeries) -> PointProfile:
    """RMSE, MAE e acertos de sinal da mediana de uma série."""
    errors = [y - m for y, m in zip(series.realized, medians(series), strict=True)]
    products = [y * m for y, m in zip(series.realized, medians(series), strict=True)]
    n_points = series.n_points
    return PointProfile(
        n_points=n_points,
        rmse=math.sqrt(math.fsum(e * e for e in errors) / n_points),
        mae=math.fsum(abs(e) for e in errors) / n_points,
        hits=sum(1 for p in products if p > 0.0),
        ties=sum(
            1 for y, m in zip(series.realized, medians(series), strict=True) if y == 0.0 or m == 0.0
        ),
    )


def median_is_identically_zero(seeds: Sequence[CoverageSeries]) -> bool:
    """Verdadeiro se a mediana é exatamente 0 em todo ponto de toda semente."""
    return all(m == 0.0 for series in seeds for m in medians(series))


def seed_mean(values: Sequence[float]) -> float:
    """Média simples de uma medida entre sementes (`math.fsum` / S).

    Raises:
        ValueError: sequência vazia.
    """
    if not values:
        raise ValueError("seed_mean needs at least one seed")
    return math.fsum(values) / len(values)


def _check_same_axes(reference: CoverageSeries, series: CoverageSeries, index: int) -> None:
    for name in ("horizon", "levels", "target_timestamps", "realized"):
        if getattr(series, name) != getattr(reference, name):
            raise ValueError(f"seed index {index}: {name} differs from the first seed")


def seed_ensemble(seeds: Sequence[CoverageSeries]) -> CoverageSeries:
    """D3: a série cujo quantil em (ponto, nível) é a média dos quantis das S sementes.

    Lê o vetor pontuado (pós-guardrail, `value_guardrail`) de cada semente; o resultado tem
    `raw_values = guardrail_values` = a média e `guardrail_applied = False` (não há
    rearranjo).

    Raises:
        ValueError: nenhuma semente; sementes com horizonte, grade, alvos ou realizados
            diferentes; grade média não monotônica (não deveria acontecer: é erro de dado).
    """
    if not seeds:
        raise ValueError("seed_ensemble needs at least one seed")
    reference = seeds[0]
    for index, series in enumerate(seeds):
        _check_same_axes(reference, series, index)
    count = len(seeds)
    forecasts: list[QuantileForecast] = []
    for i in range(reference.n_points):
        values = tuple(
            math.fsum(column) / count
            for column in zip(*(series.scored_values(i) for series in seeds), strict=True)
        )
        if any(b < a for a, b in pairwise(values)):
            raise ValueError(
                f"point {reference.target_timestamps[i]}: the seed-mean grid is not monotone"
            )
        forecasts.append(
            QuantileForecast(
                levels=reference.levels,
                raw_values=values,
                guardrail_values=values,
                guardrail_applied=False,
            )
        )
    return CoverageSeries(
        horizon=reference.horizon,
        levels=reference.levels,
        target_timestamps=reference.target_timestamps,
        forecasts=tuple(forecasts),
        realized=reference.realized,
    )


@dataclass(frozen=True)
class TailRates:
    """Taxas de violação das duas caudas de um par e o PICP, sobre os T pontos."""

    lower: float
    upper: float
    picp: float


def tail_rates(series: CoverageSeries, *, pair: tuple[float, float]) -> TailRates:
    """Violação inferior (y ≤ q_τl), superior (y > q_τu) e PICP ([q_τl, q_τu] fechado).

    Raises:
        ValueError: nível do par fora da grade da série.
    """
    low_level, high_level = pair
    for level in pair:
        if level not in series.levels:
            raise ValueError(f"level {level} is not in the grid {series.levels}")
    k_low, k_high = series.levels.index(low_level), series.levels.index(high_level)
    lower = upper = inside = 0
    for i, y in enumerate(series.realized):
        values = series.scored_values(i)
        lower += is_at_or_below(y, values[k_low])
        upper += not is_at_or_below(y, values[k_high])
        inside += is_inside_closed(y, values[k_low], values[k_high])
    n_points = series.n_points
    return TailRates(lower=lower / n_points, upper=upper / n_points, picp=inside / n_points)
