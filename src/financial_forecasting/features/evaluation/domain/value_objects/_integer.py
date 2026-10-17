"""Regra única de "inteiro não-`bool` ≥ mínimo" do slice `evaluation` (privado do slice).

`bool` é subclasse de `int` (`True >= 1`), mas não é horizonte, contagem, semente nem
índice. Antes a regra tinha duas escritas espalhadas pelo slice (`isinstance(x, bool) or
not isinstance(x, int)` e `type(x) is not int`); agora todo ponto do slice consome este
módulo:

- `is_int`: o predicado (`int` não-`bool`), para quem tem mensagem ou regra própria além
  do tipo (`df` em {1, 2}, `max_lag` em 1..T-1, `seed` opcional, célula do gold);
- `validate_int_at_least`: o predicado + o mínimo, com a mensagem única
  `"<field> must be an int >= <minimum>, got <value>"`.

O horizonte (`_horizon.validate_horizon`) e o inteiro positivo
(`_horizon.validate_positive_int`) são `validate_int_at_least` com mínimo 1.
"""

from __future__ import annotations

from typing import TypeGuard


def is_int(value: object) -> TypeGuard[int]:
    """`True` só para `int` não-`bool` (subclasses de `int` como `IntEnum` passam)."""
    return isinstance(value, int) and not isinstance(value, bool)


def validate_int_at_least(value: object, *, minimum: int, field: str) -> None:
    """Ergue `ValueError` se `value` não for `int` não-`bool` ≥ `minimum` (nomeia o campo)."""
    if not is_int(value) or value < minimum:
        raise ValueError(f"{field} must be an int >= {minimum}, got {value!r}")
