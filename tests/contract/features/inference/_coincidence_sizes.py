"""Tamanhos de calib em que o posto do MAPIE coincide com o posto exato do domain (Task 06).

O posto do MAPIE 1.5.0 é a cadeia literal, na ordem do código, conferida no
container contra o `mapie` 1.5.0 e o `numpy` 2.5.0 do volume ff72 (2026-10-17):

1. o adapter passa `confidence_level = 1 - 2 * tail_alpha` (float64);
2. `mapie/utils.py` l. 1405-1407 (`_transform_confidence_level_to_alpha`):
   `alpha = float(Decimal("1") - Decimal(str(confidence_level)))`;
3. `mapie/regression/quantile_regression.py` l. 2314 e 2318 (`predict` com
   `symmetry=False`): `alpha = self.alpha / 2` e `q = (1 - (alpha)) * (1 + (1 / n))`;
4. l. 2336-2337: `np.quantile(scores, q, method="higher")`, e em
   `numpy/lib/_function_base_impl.py` l. 152-154 o índice 0-based do `"higher"` é
   `np.ceil((n - 1) * quantiles)` — o posto 1-based é esse índice + 1.

O domain usa k = ceil((n + 1)(1 - alpha)) com alpha exato (`split_conformal_rank`).
Os dois coincidem na maioria dos n; onde diferem, o MAPIE escolhe o escore seguinte
(+1). O piso é 50: com tail_alpha = 0,02 o MAPIE 1.5.0 recusa todo n <= 49 (C5).
"""

from __future__ import annotations

import math
from decimal import Decimal
from functools import cache

from financial_forecasting.features.inference.domain.services.conformal_calibrator import (
    exact_level,
    split_conformal_rank,
)

TAIL_ALPHAS = (0.02, 0.1, 0.25)
MIN_SIZE = 50
MAX_SIZE = 399


def mapie_rank(n: int, tail_alpha: float) -> int:
    """Posto 1-based que o MAPIE 1.5.0 escolhe, pela cadeia literal do docstring."""
    confidence_level = 1 - 2 * tail_alpha
    alpha = float(Decimal("1") - Decimal(str(confidence_level)))
    alpha = alpha / 2
    q = (1 - (alpha)) * (1 + (1 / n))
    return math.ceil((n - 1) * q) + 1


def domain_rank(n: int, tail_alpha: float) -> int:
    """Posto exato do domain para a cauda."""
    return split_conformal_rank(n, exact_level(tail_alpha))


@cache
def coincidence_sizes() -> tuple[int, ...]:
    """n em [50, 399] em que os dois postos coincidem para os três alpha ao mesmo tempo."""
    return tuple(
        n
        for n in range(MIN_SIZE, MAX_SIZE + 1)
        if all(mapie_rank(n, a) == domain_rank(n, a) for a in TAIL_ALPHAS)
    )


@cache
def divergent_sizes() -> tuple[int, ...]:
    """n em [50, 399] em que os postos diferem para algum alpha."""
    return tuple(n for n in range(MIN_SIZE, MAX_SIZE + 1) if n not in set(coincidence_sizes()))
