"""Validador único de entrada dos kernels de scoring (C7; ADR `6_1_0001` item 1).

Funções puras, stdlib-only, que erguem `ValueError`. É o **único** lugar onde o
contrato de entrada de pinball, CRPS_Q e interval score é escrito: chamado pelos
kernels por ponto e pelas funções de série do domínio, pelo `FakeScoringBackend`
(via as funções de série) e pelos dois adapters do port `ScoringBackend` — nenhuma
cópia, então domínio e adapters recusam exatamente as mesmas entradas (provado na
suíte de contrato).

- **Por ponto:** `validate_level`, `validate_miscoverage`, `validate_finite`,
  `validate_grid_row`, `validate_interval_bounds`.
- **Por série** (compostas das anteriores): `validate_pinball_inputs`,
  `validate_crps_inputs`, `validate_interval_inputs` — tamanhos iguais, sequência
  não-vazia (a média sobre zero pontos é indefinida; technical 6.1 §1) e todo valor
  (realizado, quantil, extremo do intervalo) finito: sem isso as pernas divergiriam
  (o sklearn ergue em `nan`/`inf`, o domínio e a scoringrules devolveriam `nan`/`inf`).
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def validate_level(level: float) -> None:
    """Nível de quantil τ em (0, 1) aberto (`nan` também ergue)."""
    if not 0.0 < level < 1.0:
        raise ValueError(f"level must be in (0, 1), got {level}")


def validate_miscoverage(miscoverage: float) -> None:
    """Miscobertura alpha do intervalo central em (0, 1) aberto (`nan` também ergue)."""
    if not 0.0 < miscoverage < 1.0:
        raise ValueError(f"miscoverage must be in (0, 1), got {miscoverage}")


def validate_finite(name: str, values: Sequence[float]) -> None:
    """Todo valor de `values` é número finito (`nan`, `inf` e não-número erguem)."""
    for index, value in enumerate(values):
        if not _is_finite(value):
            raise ValueError(f"{name} values must all be finite, got {value!r} at index {index}")


def validate_grid_row(quantiles: Sequence[float], levels: Sequence[float]) -> None:
    """Uma grade de quantis: não-vazia, alinhada aos níveis, cada nível em (0, 1), finita."""
    if len(quantiles) != len(levels):
        raise ValueError(
            f"quantiles and levels must align: {len(quantiles)} quantiles for {len(levels)} levels"
        )
    # Grade vazia: a média (2/K)·Σ rho_τ é indefinida — mesma pré-condição das séries.
    if not levels:
        raise ValueError("a quantile grid needs at least one level")
    for level in levels:
        validate_level(level)
    validate_finite("quantile", quantiles)


def validate_interval_bounds(lower: float, upper: float) -> None:
    """Extremos finitos e `lower ≤ upper` — fora disso o IS sai do seu domínio."""
    validate_finite("interval bound", (lower, upper))
    if not lower <= upper:
        raise ValueError(f"interval lower bound must not exceed upper: {lower} > {upper}")


def validate_pinball_inputs(
    realized: Sequence[float], quantiles: Sequence[float], level: float
) -> None:
    """Série do pinball: nível válido, não-vazia, `realized` alinhado a `quantiles`."""
    validate_level(level)
    _check_non_empty(realized)
    _check_same_length(realized=realized, quantiles=quantiles)
    validate_finite("realized", realized)
    validate_finite("quantile", quantiles)


def validate_crps_inputs(
    realized: Sequence[float],
    quantile_grid: Sequence[Sequence[float]],
    levels: Sequence[float],
) -> None:
    """Série do CRPS_Q: não-vazia, uma grade por ponto, cada grade válida contra `levels`."""
    _check_non_empty(realized)
    _check_same_length(realized=realized, quantile_grid=quantile_grid)
    validate_finite("realized", realized)
    for row in quantile_grid:
        validate_grid_row(row, levels)


def validate_interval_inputs(
    realized: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float],
    miscoverage: float,
) -> None:
    """Série do IS: alpha válido, não-vazia, alinhada, `lower ≤ upper` em todo ponto."""
    validate_miscoverage(miscoverage)
    _check_non_empty(realized)
    _check_same_length(realized=realized, lower=lower, upper=upper)
    validate_finite("realized", realized)
    for low, high in zip(lower, upper, strict=True):
        validate_interval_bounds(low, high)


def _check_non_empty(realized: Sequence[float]) -> None:
    if not realized:
        raise ValueError("scoring needs at least one point (empty sequence)")


def _check_same_length(**sequences: Sequence[object]) -> None:
    lengths = {name: len(values) for name, values in sequences.items()}
    if len(set(lengths.values())) != 1:
        raise ValueError(f"sequences must have the same length, got {lengths}")


def _is_finite(value: object) -> bool:
    try:
        return math.isfinite(value)  # type: ignore[arg-type]
    except TypeError:
        return False
