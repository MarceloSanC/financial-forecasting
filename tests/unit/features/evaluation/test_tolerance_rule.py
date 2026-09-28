"""Unit test da regra única de tolerância (`_tolerance.validate_tolerance`).

Prova (ADR 6.1.0003; concept 6.1 C3 e 6.3 C1): "finita, não-`bool` e ≥ 0" tem uma
escrita, consumida pelo `DegeneracyGate` e pela `HitSequence`; a mensagem nomeia o
campo passado pelo consumidor, para o erro dizer de onde veio.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.services import (
    degeneracy_gate as degeneracy_gate_module,
)
from financial_forecasting.features.evaluation.domain.services.degeneracy_gate import (
    DegeneracyGate,
)
from financial_forecasting.features.evaluation.domain.value_objects import (
    hit_sequence as hit_sequence_module,
)
from financial_forecasting.features.evaluation.domain.value_objects._tolerance import (
    validate_tolerance,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitSequence,
)

SeriesFactory = Callable[..., CoverageSeries]
HitSequenceFactory = Callable[..., HitSequence]


@pytest.mark.unit
@pytest.mark.parametrize("value", [0, 0.0, 1e-9, 0.25], ids=["int-zero", "zero", "tiny", "dyadic"])
def test_tolerance_rule_accepts_finite_non_negative(value: float) -> None:
    validate_tolerance(value, field="tolerance")


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [-1e-12, math.nan, math.inf, True, 10**400],
    ids=["negative", "nan", "inf", "bool", "int-beyond-float"],
)
def test_tolerance_rule_rejects_with_the_field_name(value: float) -> None:
    with pytest.raises(ValueError, match=r"^my_field must be a finite number >= 0"):
        validate_tolerance(value, field="my_field")


def _reject(*_: object, **__: object) -> None:
    raise ValueError("single tolerance rule called")


@pytest.mark.unit
def test_tolerance_rule_is_consumed_by_the_gate(
    make_series: SeriesFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O gate valida pela regra única (trocar o nome no módulo muda o erro)."""
    monkeypatch.setattr(degeneracy_gate_module, "validate_tolerance", _reject)
    series = make_series([(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6)], [0.0])

    with pytest.raises(ValueError, match="single tolerance rule called"):
        DegeneracyGate.evaluate(series, tolerance=0.0)


@pytest.mark.unit
def test_tolerance_rule_is_consumed_by_the_hit_sequence(
    make_hit_sequence: HitSequenceFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `HitSequence` valida pela regra única (trocar o nome no módulo muda o erro)."""
    monkeypatch.setattr(hit_sequence_module, "validate_tolerance", _reject)

    with pytest.raises(ValueError, match="single tolerance rule called"):
        make_hit_sequence((True, False))
