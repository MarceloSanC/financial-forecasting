"""Unit test do validador único de Holm/MCS (C4; ADR 6.2.0003 item 3)."""

from __future__ import annotations

import math

import pytest

from financial_forecasting.features.evaluation.domain.services.inference_input_validation import (
    validate_alpha,
    validate_p_values,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("p_values", "message"),
    [
        pytest.param([], "at least one", id="empty"),
        pytest.param([0.1, -0.1], r"p_values\[1\]", id="negative"),
        pytest.param([1.1], r"p_values\[0\]", id="above-one"),
        pytest.param([0.2, math.nan], r"p_values\[1\]", id="nan"),
        pytest.param([0.2, math.inf], r"p_values\[1\]", id="inf"),
        pytest.param([None], r"p_values\[0\]", id="none"),
        pytest.param([True], r"p_values\[0\]", id="bool"),
    ],
)
def test_p_values_invalid_raise(p_values: list[object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_p_values(p_values)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize("alpha", [0.0, 1.0, -0.1, 1.5, math.nan, math.inf, True, None], ids=repr)
def test_alpha_invalid_raise(alpha: object) -> None:
    with pytest.raises(ValueError, match="alpha must be"):
        validate_alpha(alpha)  # type: ignore[arg-type]


@pytest.mark.unit
def test_valid_inputs_accepted() -> None:
    validate_p_values([0.0, 0.5, 1.0])
    validate_p_values((0.03,))
    for alpha in (0.01, 0.05, 0.5, 0.99):
        validate_alpha(alpha)
