"""Serviços de domínio: emissão da grade densa de quantis dos baselines.

Domínio puro (stdlib-only — ADR 5.2.0001). Três funções puras que materializam as
convenções de emissão pré-registradas do doc de domínio
`quantile-model-training.md` §3 (ADR 0.0.0052) — as fórmulas são o contrato, a
implementação não re-deriva nada:

- `degenerate_grid` (§3.4): preditor pontual como distribuição degenerada
  (Dirac) — o mesmo valor repetido em todo nível da grade (Gneiting & Raftery
  2007 §4.2). Usada por `zero_return` (§3.2) e `historical_mean` (§3.3).
- `gaussian_grid` (§3.5/§3.6): conversão locação-escala
  ``q_tau = mean + std * z_tau`` com ``z_tau = NormalDist().inv_cdf(tau)``
  (QRM Eq. (2.19); stdlib AS241 — sem numpy/scipy). Usada por `ar1` e
  `ewma_vol`.
- `sample_quantiles_type7` (§3.7): quantil amostral tipo 7 de Hyndman & Fan
  (1996), parametrização ``h = (n-1)p + 1`` com interpolação linear entre
  estatísticas de ordem — o default de R (`type=7`) e NumPy
  (`method='linear'`). Usada por `historical_quantiles`.

Validações defensivas erguem `ValueError` (alimentam C5 do concept §6: um
baseline determinístico nunca emite valor não-finito). A saída é sempre
`tuple[float, ...]` alinhada 1:1 a `levels`.
"""

from __future__ import annotations

import math
from itertools import pairwise
from statistics import NormalDist
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_STANDARD_NORMAL = NormalDist()


def degenerate_grid(*, value: float, levels: Sequence[float]) -> tuple[float, ...]:
    """Grade degenerada: `value` repetido em todo nível (doc §3.4 — Dirac).

    Args:
        value: valor pontual do preditor (finito).
        levels: níveis de quantil — não-vazios, estritamente crescentes, em (0, 1).

    Returns:
        Tupla alinhada 1:1 a `levels`, com `value` em toda posição.

    Raises:
        ValueError: `levels` inválidos ou `value` não-finito (C5).
    """
    _validate_levels(levels)
    if not math.isfinite(value):
        raise ValueError(f"degenerate_grid value must be finite; got {value}")
    return tuple(float(value) for _ in levels)


def gaussian_grid(*, mean: float, std: float, levels: Sequence[float]) -> tuple[float, ...]:
    """Grade gaussiana locação-escala: ``mean + std * inv_cdf(tau)`` (doc §3.5/§3.6).

    Forma VaR_alpha = mu + sigma * Phi^-1(alpha) (QRM Eq. (2.19)); ``z_tau`` vem de
    `statistics.NormalDist().inv_cdf` (stdlib, algoritmo AS241).

    Args:
        mean: locação (finita).
        std: escala (> 0 e finita).
        levels: níveis de quantil — não-vazios, estritamente crescentes, em (0, 1).

    Returns:
        Tupla alinhada 1:1 a `levels`.

    Raises:
        ValueError: `levels` inválidos, `mean` não-finito ou `std` não-positivo/
            não-finito (C5).
    """
    _validate_levels(levels)
    if not math.isfinite(mean):
        raise ValueError(f"gaussian_grid mean must be finite; got {mean}")
    if not math.isfinite(std) or std <= 0.0:
        raise ValueError(f"gaussian_grid std must be finite and > 0; got {std}")
    return tuple(mean + std * _STANDARD_NORMAL.inv_cdf(tau) for tau in levels)


def sample_quantiles_type7(
    *, values: Sequence[float], levels: Sequence[float]
) -> tuple[float, ...]:
    """Quantil amostral tipo 7 (Hyndman & Fan 1996) por nível da grade (doc §3.7).

    Parametrização ``h = (n - 1) * p + 1`` (1-indexada) com interpolação linear
    entre as estatísticas de ordem adjacentes — idêntica ao default de R
    (`type=7`) e NumPy (`method='linear'`).

    Args:
        values: amostra (não-vazia, todos finitos); a ordenação é interna.
        levels: níveis de quantil — não-vazios, estritamente crescentes, em (0, 1).

    Returns:
        Tupla alinhada 1:1 a `levels`.

    Raises:
        ValueError: `levels` inválidos, `values` vazio ou com valor não-finito (C5).
    """
    _validate_levels(levels)
    if not values:
        raise ValueError("sample_quantiles_type7 values must be non-empty")
    if any(not math.isfinite(v) for v in values):
        raise ValueError("sample_quantiles_type7 values must all be finite")

    ordered = sorted(float(v) for v in values)
    n = len(ordered)
    grid: list[float] = []
    for tau in levels:
        # h = (n-1)p + 1 em base 1 => índice 0-based h0 = (n-1)p; com
        # tau em (0,1), h0 < n-1, logo lower+1 <= n-1 sempre é válido.
        h0 = (n - 1) * tau
        lower = math.floor(h0)
        fraction = h0 - lower
        if n == 1 or fraction == 0.0:
            grid.append(ordered[lower])
            continue
        grid.append(ordered[lower] + fraction * (ordered[lower + 1] - ordered[lower]))
    return tuple(grid)


def _validate_levels(levels: Sequence[float]) -> None:
    """Valida a grade de níveis: não-vazia, estritamente crescente, em (0, 1).

    Estritamente crescente implica unicidade; NaN reprova o teste de faixa
    (comparações com NaN são falsas), então nível não-finito também ergue.
    """
    if not levels:
        raise ValueError("quantile levels must be non-empty")
    if any(not 0.0 < tau < 1.0 for tau in levels):
        raise ValueError(f"quantile levels must all be in (0, 1); got {tuple(levels)}")
    if any(b <= a for a, b in pairwise(levels)):
        raise ValueError(
            f"quantile levels must be strictly increasing and unique; got {tuple(levels)}"
        )
