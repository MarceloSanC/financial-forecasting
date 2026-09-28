"""Validador único de entrada dos kernels de contagem real (C3; ADR `6_3_0005` item 1).

Funções puras, stdlib-only, que erguem `ValueError` nomeando o campo. É o **único**
lugar onde o contrato de entrada dos kernels de contagem — `kupiec_pof` (Task 03),
`wilson_interval` (Task 04) e `lr_uc_three_state` (Task 08) — é escrito: contagem
real `0 ≤ count ≤ n`, `n > 0`, ambos finitos e não-`bool` (predicado único do
slice, `is_finite_number`), e taxa em (0, 1). O ADR 6.3.0005 define a regra uma vez
para os três kernels; cada kernel só acrescenta o que é dele (ex.: no 3 estados,
`lower_count + upper_count ≤ n` e `lower_rate + upper_rate < 1`).

Mesmo padrão do `scoring_input_validation` da 6.1 (validador único dos kernels de
scoring): um módulo, nenhuma cópia por kernel.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)


def validate_real_count(count: float, n: float, *, count_field: str, n_field: str) -> None:
    """Contagem real `0 ≤ count ≤ n` sobre `n > 0` (ADR 6.3.0005).

    Ergue também quando `count > 0` e `count / n` sub-flui a 0.0 em float64 (ex.:
    `count = 1e-320`, `n = 1e10`): a verossimilhança em `count / n` pediria `log 0`
    com peso positivo e o kernel ergueria "math domain error" cru.

    Raises:
        ValueError: não-finito ou `bool`; `n <= 0`; `count` fora de [0, n]; razão
            `count / n` sub-fluindo com `count > 0` — a mensagem nomeia o campo.
    """
    for name, value in ((count_field, count), (n_field, n)):
        if not is_finite_number(value):
            raise ValueError(f"{name} must be a finite number, got {value!r}")
    if n <= 0:
        raise ValueError(f"{n_field} must be > 0, got {n!r}")
    if not 0 <= count <= n:
        raise ValueError(f"{count_field} must be in [0, {n_field}={n!r}], got {count!r}")
    if count > 0 and count / n == 0.0:
        raise ValueError(
            f"{count_field}/{n_field} underflows to 0.0 with {count_field} > 0 "
            f"({count_field}={count!r}, {n_field}={n!r})"
        )


def validate_rate(rate: float, *, field: str) -> None:
    """Taxa (ou nível) em (0, 1) aberto, finita e não-`bool`.

    Raises:
        ValueError: não-finito, `bool` ou fora de (0, 1) — a mensagem nomeia o campo.
    """
    if not is_finite_number(rate):
        raise ValueError(f"{field} must be a finite number, got {rate!r}")
    if not 0.0 < rate < 1.0:
        raise ValueError(f"{field} must be in (0, 1), got {rate!r}")
