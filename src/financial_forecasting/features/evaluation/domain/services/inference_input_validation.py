"""Validador único de entrada de Holm e do nível do MCS (C4; ADR `6_2_0003` item 3).

Funções puras, stdlib-only, que erguem `ValueError`. É o **único** lugar onde o
contrato de entrada dos p-valores e do nível alpha é escrito: chamado pelas funções de
`holm_correction` e pelo `HolmCorrection.family`, pelo fake e pelo adapter do port
`InferenceBackend` e — `validate_alpha` — pelo `ModelConfidenceSet` (6.2 Task 07).
Nenhuma cópia, então domínio e adapter recusam exatamente as mesmas entradas (padrão
`scoring_input_validation` da 6.1).

Não importa serviço nenhum (só o predicado `is_finite_number` do slice): o validador do
DM mora em `diebold_mariano.py`, ao lado do enum que confere (technical 6.2 §1).
"""

from __future__ import annotations

from collections.abc import Sequence

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)


def validate_p_values(p_values: Sequence[float]) -> None:
    """Lista não-vazia de p-valores finitos em [0, 1] (`bool`/`None` também erguem)."""
    if len(p_values) == 0:
        raise ValueError("p_values must hold at least one p-value, got an empty sequence")
    for index, p_value in enumerate(p_values):
        if not is_finite_number(p_value) or not 0.0 <= p_value <= 1.0:
            raise ValueError(
                f"p_values[{index}] must be a finite number in [0, 1], got {p_value!r}"
            )


def validate_alpha(alpha: float) -> None:
    """Nível alpha finito em (0, 1) aberto (`bool`/`None`/`nan` também erguem)."""
    if not is_finite_number(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be a finite number in (0, 1), got {alpha!r}")
