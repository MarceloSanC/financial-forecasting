"""Unit test da regra única de "inteiro não-`bool` ≥ mínimo" (`_integer`, issue #118).

`is_int` é o predicado; `validate_int_at_least` é o predicado + mínimo com a mensagem
única. O horizonte e o inteiro positivo (`_horizon`) e o horizonte da amostra pareada
(`_paired_inputs.check_horizon`) delegam a ela — trocar o dono muda o erro deles.
"""

from __future__ import annotations

from enum import IntEnum

import pytest

from financial_forecasting.features.evaluation.domain.value_objects import (
    _horizon as horizon_module,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    validate_horizon,
    validate_positive_int,
)
from financial_forecasting.features.evaluation.domain.value_objects._integer import (
    is_int,
    validate_int_at_least,
)
from financial_forecasting.features.evaluation.domain.value_objects._paired_inputs import (
    check_horizon,
)


class _Level(IntEnum):
    TWO = 2


@pytest.mark.unit
@pytest.mark.parametrize("value", [0, -3, 10**400, _Level.TWO], ids=["zero", "neg", "big", "enum"])
def test_is_int_accepts_non_bool_ints(value: object) -> None:
    assert is_int(value) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [True, False, 1.0, "1", None, b"1"],
    ids=["true", "false", "float", "str", "none", "bytes"],
)
def test_is_int_rejects_bool_and_non_ints(value: object) -> None:
    assert is_int(value) is False


@pytest.mark.unit
@pytest.mark.parametrize("minimum", [-1, 0, 1, 2])
def test_validate_int_at_least_accepts_the_minimum_itself(minimum: int) -> None:
    validate_int_at_least(minimum, minimum=minimum, field="x")
    validate_int_at_least(minimum + 1, minimum=minimum, field="x")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "minimum"),
    [(1, 2), (-1, 0), (True, 0), (False, 0), (2.0, 1), ("3", 1), (None, 0)],
    ids=["below", "negative", "true", "false", "float", "str", "none"],
)
def test_validate_int_at_least_rejects_with_the_single_message(value: object, minimum: int) -> None:
    expected = rf"^my_field must be an int >= {minimum}, got {value!r}$"
    with pytest.raises(ValueError, match=expected):
        validate_int_at_least(value, minimum=minimum, field="my_field")


def _reject(*_: object, **__: object) -> None:
    raise ValueError("single int rule called")


@pytest.mark.unit
def test_horizon_helpers_delegate_to_the_single_int_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    """`validate_positive_int`, `validate_horizon` e `check_horizon` passam pelo dono."""
    monkeypatch.setattr(horizon_module, "validate_int_at_least", _reject)

    for call in (
        lambda: validate_positive_int(1, field="n"),
        lambda: validate_horizon(1, field="horizon"),
        lambda: check_horizon(1),
    ):
        with pytest.raises(ValueError, match="single int rule called"):
            call()


@pytest.mark.unit
@pytest.mark.parametrize("value", [0, True, 1.0], ids=["zero", "bool", "float"])
def test_paired_check_horizon_keeps_its_message(value: object) -> None:
    with pytest.raises(ValueError, match=r"^horizon must be an int >= 1, got "):
        check_horizon(value)
