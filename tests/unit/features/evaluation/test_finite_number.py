"""Unit test do predicado único de "número finito" do slice `evaluation`.

`is_finite_number` é a única escrita da regra, consumida pela `CoverageSeries` (C2),
pelo validador único dos kernels (`validate_finite`, C7) e pelo `DegeneracyGate`
(tolerância, C3). Antes eram três cópias: a do validador aceitava `Decimal` e
`Fraction` (e escalares numpy fora da hierarquia de `float`), que a `CoverageSeries`
recusava. Os testes de consistência abaixo provam que os três consumidores decidem
igual justamente nessas entradas.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from decimal import Decimal
from fractions import Fraction

import pytest

from financial_forecasting.features.evaluation.domain.services.degeneracy_gate import (
    DegeneracyGate,
)
from financial_forecasting.features.evaluation.domain.services.scoring_input_validation import (
    validate_finite,
)
from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)

SeriesFactory = Callable[..., CoverageSeries]

_GRID = (-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03)


class _FloatSubclass(float):
    """Stand-in stdlib de `numpy.float64` (subclasse de `float`) — o domínio não importa numpy."""


# Entradas em que as três cópias antigas divergiam: o validador aceitava, a série recusava.
_FORMERLY_DIVERGENT = [Decimal("0.01"), Fraction(1, 100)]
_FORMERLY_DIVERGENT_IDS = ["decimal", "fraction"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [0, -3, 0.0, -1.5, 1e300, _FloatSubclass(0.25)],
    ids=["zero-int", "negative-int", "zero-float", "negative-float", "large", "float-subclass"],
)
def test_accepts_finite_int_and_float(value: object) -> None:
    assert is_finite_number(value) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [math.nan, math.inf, -math.inf, None, "0.1", True, False, *_FORMERLY_DIVERGENT],
    ids=["nan", "inf", "-inf", "none", "str", "true", "false", *_FORMERLY_DIVERGENT_IDS],
)
def test_rejects_non_finite_bool_and_non_float_numbers(value: object) -> None:
    assert is_finite_number(value) is False


@pytest.mark.unit
@pytest.mark.parametrize("value", _FORMERLY_DIVERGENT, ids=_FORMERLY_DIVERGENT_IDS)
def test_all_three_consumers_reject_formerly_divergent_input(
    make_series: SeriesFactory, value: object
) -> None:
    """`Decimal`/`Fraction`: validador, série e gate recusam (antes o validador aceitava)."""
    with pytest.raises(ValueError, match="realized values must all be finite"):
        validate_finite("realized", [0.0, value])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="point 1: realized value must be finite"):
        make_series([_GRID, _GRID], [0.0, value])
    series = make_series([_GRID], [0.0])
    with pytest.raises(ValueError, match="tolerance must be a finite number >= 0"):
        DegeneracyGate.evaluate(series, tolerance=value)  # type: ignore[arg-type]


@pytest.mark.unit
def test_all_three_consumers_accept_float_subclass(make_series: SeriesFactory) -> None:
    """Subclasse de `float` (como `numpy.float64`) passa nos três consumidores."""
    value = _FloatSubclass(0.01)

    validate_finite("realized", [0.0, value])
    series = make_series([_GRID, _GRID], [0.0, value])
    report = DegeneracyGate.evaluate(series, tolerance=value)

    assert series.realized == (0.0, value)
    assert report.levels == series.levels
    assert report.tolerance == value
