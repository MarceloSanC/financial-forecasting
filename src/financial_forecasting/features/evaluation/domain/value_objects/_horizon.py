"""Regra única do rótulo de horizonte dos VOs e serviços da 6.3 (privado do slice).

"Horizonte é `int` não-`bool` ≥ 1" (concept 6.3 I1, C1, C9) — uma escrita, consumida
pela `HitSequence`, pelo `WilsonBand`/`WilsonBandReport` e, nas Tasks 07-09, pelos
relatórios de Christoffersen, Monte Carlo e VaR descritivo. `bool` é subclasse de
`int` (`True >= 1`), mas não é horizonte. A `CoverageSeries` (6.1), a
`PairedLossSeries` (6.2, via `_paired_inputs.check_horizon`) e os VOs do gold (6.4) também
consomem esta regra; o predicado de tipo é o do dono do inteiro (`_integer`).
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.domain.value_objects._integer import (
    validate_int_at_least,
)


def validate_positive_int(value: object, *, field: str) -> None:
    """Ergue `ValueError` se `value` não for `int` não-`bool` ≥ 1 (mensagem nomeia o campo).

    Inteiro positivo do slice (horizonte, `draws` do Monte Carlo): `validate_int_at_least`
    com mínimo 1.
    """
    validate_int_at_least(value, minimum=1, field=field)


def validate_horizon(value: object, *, field: str) -> None:
    """Horizonte é inteiro positivo (`validate_positive_int`) - nome do conceito no slice."""
    validate_positive_int(value, field=field)


def is_multi_step(horizon: int) -> bool:
    """`horizon > 1` - o limiar único do slice para multi-passo (B-H7, doc §7.4).

    A partir dele: hits podem ser (h-1)-dependentes sob a nula, a banda de Wilson ganha
    o aviso de dependência serial, LR_ind/LR_cc viram descritivos (fora de sub-série DGT),
    o p-valor Monte Carlo não é definido e a `HitSequence` tem partição DGT (passo ≥ 2).
    """
    return horizon > 1
