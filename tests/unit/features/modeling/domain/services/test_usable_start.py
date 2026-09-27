"""Unit test de `usable_start` — regra do grid único (Stage 5.5, A1 / D11).

Prova: prefixos com aquecimentos diferentes por coluna cortam até a linha em que
TODAS são finitas; valor ausente depois disso (None, NaN, inf) ergue com a
contagem por coluna, inclusive no `target_return`; tudo finito → 0; nenhuma
linha utilizável → `NoUsableRowsError`.
"""

from __future__ import annotations

import math

import pytest

from financial_forecasting.features.modeling.domain.exceptions.cohort import (
    InteriorMissingValuesError,
    NoUsableRowsError,
)
from financial_forecasting.features.modeling.domain.services.training_grid import usable_start

_NAN = math.nan
_LONGEST_WARM_UP = 3


def test_all_finite_starts_at_zero() -> None:
    assert usable_start({"a": [1.0, 2.0], "target_return": [0.1, 0.2]}) == 0


def test_prefix_is_the_longest_warm_up_across_columns() -> None:
    values = {
        "ema_3": [None, None, 1.0, 2.0, 3.0],
        "yoy": [_NAN, _NAN, _NAN, 4.0, 5.0],
        "target_return": [0.1, 0.2, 0.3, 0.4, 0.5],
    }

    assert usable_start(values) == _LONGEST_WARM_UP


def test_target_return_missing_in_prefix_is_trimmed() -> None:
    values = {"a": [1.0, 2.0, 3.0], "target_return": [_NAN, 0.2, 0.3]}

    assert usable_start(values) == 1


@pytest.mark.parametrize(
    "bad", [None, _NAN, math.inf, -math.inf], ids=["none", "nan", "inf", "-inf"]
)
def test_interior_missing_value_raises_with_counts(bad: float | None) -> None:
    values = {
        "a": [None, 1.0, bad, 3.0, bad],
        "b": [None, 1.0, 2.0, 3.0, 4.0],
        "target_return": [0.0, 0.1, 0.2, bad, 0.4],
    }

    with pytest.raises(InteriorMissingValuesError) as excinfo:
        usable_start(values)

    assert excinfo.value.counts == {"a": 2, "target_return": 1}
    assert excinfo.value.first_usable == 1
    assert "a=2" in str(excinfo.value)
    assert "target_return=1" in str(excinfo.value)


def test_no_usable_row_raises() -> None:
    with pytest.raises(NoUsableRowsError):
        usable_start({"a": [None, 1.0], "b": [2.0, None]})


def test_empty_columns_have_no_usable_row() -> None:
    with pytest.raises(NoUsableRowsError):
        usable_start({"a": [], "target_return": []})


def test_mismatched_lengths_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="same length"):
        usable_start({"a": [1.0], "b": [1.0, 2.0]})


def test_no_columns_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="at least one column"):
        usable_start({})
