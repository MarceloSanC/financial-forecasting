"""Regra única da tolerância de degeneração do slice `evaluation` (privado).

"Tolerância absoluta, finita e ≥ 0" (ADR `6_1_0003`; concept 6.1 C3) — uma escrita,
consumida pelo `DegeneracyGate` (6.1, que a aplica) e pela `HitSequence` (6.3, que a
grava como autodescrição da máscara). Antes eram duas cópias com a mesma mensagem, o
que escondia de qual consumidor vinha o erro; agora cada consumidor passa o nome do
campo (`field`) e a mensagem diz de onde veio.

Fica em `value_objects/` porque a `HitSequence` é consumidora e a direção interna do
domínio é serviço → VO (nunca o contrário), como o `_finite_number`.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)


def validate_tolerance(value: float, *, field: str) -> None:
    """Ergue `ValueError` se `value` não for número finito (não-`bool`) ≥ 0.

    Args:
        value: a tolerância absoluta (unidade de y).
        field: nome do campo na mensagem (ex.: `"tolerance"`, `"HitSequence.tolerance"`).
    """
    if not is_finite_number(value) or value < 0.0:
        raise ValueError(f"{field} must be a finite number >= 0, got {value!r}")
