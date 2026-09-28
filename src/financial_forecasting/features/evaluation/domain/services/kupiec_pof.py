"""Kernel `kupiec_pof` — o POF de Kupiec (1995), que é o LR_uc de Christoffersen.

stdlib-only (concept 6.3 §4, I10, I13, C3; ADR `6_3_0001` item 3; ADR `6_3_0005`).
Kupiec (1995), expressão (6), com x violações em n observações e taxa nominal p:

    LR_POF = -2 log[(1-p)^{n-x} p^x] + 2 log[(1-x/n)^{n-x} (x/n)^x]

É a mesma estatística que o LR_uc de Christoffersen (doc de domínio §7.3): um só
kernel serve às duas leituras. Calcula-se por **log-somas** — `-2·(l(p) - l(x/n))`
com `l(q) = (n-x)·log(1-q) + x·log q` —, nunca pelo produto de verossimilhanças,
que sub-flui em n grande. A convenção `0·log 0 = 0` tem uma única escrita,
`xlogy`, consumida também por LR_ind e pelo LR_uc de 3 estados.

As contagens podem ser **reais** (0 ≤ x ≤ n, n > 0): a 6.5 alimenta o kernel com
contagens médias entre seeds e o número médio de pontos não-degenerados (ADR
`6_3_0005`). O resultado passa pelo piso numérico I13 (`floor_lr_statistic`).
"""

from __future__ import annotations

import math

from financial_forecasting.features.evaluation.domain.services.chi_square import (
    floor_lr_statistic,
)
from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)


def xlogy(x: float, y: float) -> float:
    """`x · log y` com a convenção `0 · log 0 = 0` (x = 0 → 0.0, qualquer y).

    Única escrita da convenção no slice (technical 6.3 §1, decisão de detalhe).
    """
    if x == 0.0:
        return 0.0
    return x * math.log(y)


def kupiec_pof(*, violations: float, observations: float, violation_rate: float) -> float:
    """LR_POF de Kupiec 1995 expr. (6) ≡ LR_uc de Christoffersen (doc §7.3).

    Args:
        violations: x — violações observadas; real em [0, observations].
        observations: n — posições observadas; real > 0.
        violation_rate: p — taxa nominal de violação, em (0, 1).

    Returns:
        A estatística, ≥ 0, após o piso I13 (distribuição χ²(1) sob a nula).

    Raises:
        ValueError: argumento não-finito ou `bool`, `observations <= 0`, `violations`
            fora de [0, observations] ou `violation_rate` fora de (0, 1) (C3); LR bruto
            negativo além do piso (I13).
    """
    for name, value in (
        ("violations", violations),
        ("observations", observations),
        ("violation_rate", violation_rate),
    ):
        if not is_finite_number(value):
            raise ValueError(f"{name} must be a finite number, got {value!r}")
    if observations <= 0:
        raise ValueError(f"observations must be > 0, got {observations!r}")
    if not 0 <= violations <= observations:
        raise ValueError(
            f"violations must be in [0, observations={observations!r}], got {violations!r}"
        )
    if not 0.0 < violation_rate < 1.0:
        raise ValueError(f"violation_rate must be in (0, 1), got {violation_rate!r}")
    observed_rate = violations / observations
    raw = -2.0 * (
        _binomial_log_likelihood(violations, observations, violation_rate)
        - _binomial_log_likelihood(violations, observations, observed_rate)
    )
    return floor_lr_statistic(raw)


def _binomial_log_likelihood(violations: float, observations: float, rate: float) -> float:
    """l(x, n, q) = (n - x)·log(1 - q) + x·log q, com `0·log 0 = 0`."""
    return xlogy(observations - violations, 1.0 - rate) + xlogy(violations, rate)
