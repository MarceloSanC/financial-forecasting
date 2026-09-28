"""Predicado único de "número finito" do domínio de `evaluation` (privado do slice).

Uma só escrita da regra, consumida pelos três lugares que a checam: a
`CoverageSeries` (C2: quantis pós-guardrail e realizados), o validador único dos
kernels (`scoring_input_validation.validate_finite`, C7) e o `DegeneracyGate`
(tolerância, C3). Antes eram três cópias com semânticas diferentes — a do validador
(`math.isfinite` sob `try`) aceitava `Decimal`, `Fraction` e escalares numpy fora da
hierarquia de `float` que a `CoverageSeries` recusava.

Semântica: só `int`/`float` **não-bool** e finitos. `bool` é subclasse de `int` e
`math.isfinite(True)` é `True`, mas não é valor de retorno, quantil nem tolerância.
`numpy.float64` passa (é subclasse de `float`); `Decimal`, `Fraction`,
`numpy.float32`, `None` e `str` não.

Fica em `value_objects/` porque o primeiro dono da regra é a `CoverageSeries` e a
direção interna do domínio já é serviço → VO (nunca o contrário). É cópia
intencional, e não import, do helper privado do `QuantileForecast` (4.3): importá-lo
abriria aresta nova no `bc-independence` (ADR 0.0.0053 item 3).
"""

from __future__ import annotations

import math


def is_finite_number(value: object) -> bool:
    """`True` só para `int`/`float` não-bool finitos (exclui `None`, `nan`, `inf`, `bool`)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return math.isfinite(value)
