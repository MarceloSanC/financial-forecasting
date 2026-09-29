"""Regra única do rótulo de horizonte dos VOs e serviços da 6.3 (privado do slice).

"Horizonte é `int` não-`bool` ≥ 1" (concept 6.3 I1, C1, C9) — uma escrita, consumida
pela `HitSequence`, pelo `WilsonBand`/`WilsonBandReport` e, nas Tasks 07-09, pelos
relatórios de Christoffersen, Monte Carlo e VaR descritivo. `bool` é subclasse de
`int` (`True >= 1`), mas não é horizonte.

A `CoverageSeries` (6.1) ainda tem a forma mais fraca (`horizon < 1`); adotar este
helper lá — junto com o `_timestamps` que a 6.2 cria em paralelo — fica para depois do
merge das Stages 6.2 e 6.3 (`[finding]` no technical 6.3 §7).
"""

from __future__ import annotations


def validate_positive_int(value: int, *, field: str) -> None:
    """Ergue `ValueError` se `value` não for `int` não-`bool` ≥ 1 (mensagem nomeia o campo).

    Regra única de "inteiro positivo" do slice: horizonte e o N (`draws`) do Monte Carlo.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be an int >= 1, got {value!r}")


def validate_horizon(value: int, *, field: str) -> None:
    """Horizonte é inteiro positivo (`validate_positive_int`) - nome do conceito no slice."""
    validate_positive_int(value, field=field)
