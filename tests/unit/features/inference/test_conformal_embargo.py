"""Unit do `CalibrationSet` (Stage 7.2, Task 02) — concept §5 I7 e §6 C1: um caso por recusa."""

from __future__ import annotations

import math
from dataclasses import replace
from fractions import Fraction

import pytest

from financial_forecasting.features.inference.domain.value_objects.calibration_set import (
    CalibrationPoint,
    CalibrationSet,
    exact_level,
)

_TEST_START = "2024-01-10T21:00:00+00:00"


def _point(day: int, *, target_day: int | None = None, **values: float) -> CalibrationPoint:
    target = day + 1 if target_day is None else target_day
    return CalibrationPoint(
        decision_timestamp=f"2024-01-{day:02d}T21:00:00+00:00",
        target_timestamp=f"2024-01-{target:02d}T21:00:00+00:00",
        lower=values.get("lower", -0.02),
        upper=values.get("upper", 0.02),
        realized=values.get("realized", 0.001),
    )


def _set(points: tuple[CalibrationPoint, ...] | None = None, **fields: object) -> CalibrationSet:
    base: dict[str, object] = {
        "fold_index": 0,
        "seed": 7,
        "horizon": 1,
        "lower_level": 0.1,
        "upper_level": 0.9,
        "points": (_point(2), _point(3), _point(4)) if points is None else points,
        "test_start": _TEST_START,
    }
    base.update(fields)
    return CalibrationSet(**base)  # type: ignore[arg-type]


def test_valid_set_accepted() -> None:
    points = [_point(2), _point(3), _point(8)]
    calib = _set(points=points)  # type: ignore[arg-type]
    assert calib.points == tuple(points)  # lista vira tupla
    # alvo imediatamente antes do teste é aceito (limite do embargo)
    _set(points=(_point(2), _point(8, target_day=9)))


def test_empty_calib_refused() -> None:
    with pytest.raises(ValueError, match="points"):
        _set(points=())


def test_repeated_target_refused() -> None:
    with pytest.raises(ValueError, match=r"points\[1\]\.target_timestamp"):
        _set(points=(_point(2), _point(3, target_day=3)))


def test_out_of_order_target_refused() -> None:
    with pytest.raises(ValueError, match=r"points\[2\]\.target_timestamp"):
        _set(points=(_point(2), _point(4), _point(3)))


def test_calib_decision_at_test_start_refused() -> None:
    point = replace(_point(9), decision_timestamp=_TEST_START, target_timestamp=_TEST_START)
    with pytest.raises(ValueError, match=r"points\[1\]\.decision_timestamp"):
        _set(points=(_point(2), point))


def test_calib_decision_after_test_start_refused() -> None:
    with pytest.raises(ValueError, match=r"points\[1\]\.decision_timestamp"):
        _set(points=(_point(2), _point(11, target_day=12)))


def test_calib_target_at_test_start_refused() -> None:
    with pytest.raises(ValueError, match=r"points\[1\]\.target_timestamp.*embargo"):
        _set(points=(_point(2), _point(9, target_day=10)))


def test_calib_target_after_test_start_refused() -> None:
    with pytest.raises(ValueError, match=r"points\[1\]\.target_timestamp.*embargo"):
        _set(points=(_point(2), _point(9, target_day=15)))


def test_calib_target_one_second_before_test_start_accepted() -> None:
    # mata a mutação `>` no lugar de `>=` pelo lado de dentro do limite
    point = replace(_point(9), target_timestamp="2024-01-10T20:59:59+00:00")
    _set(points=(_point(2), point))


@pytest.mark.parametrize("field", ["lower", "upper", "realized"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_value_refused(field: str, value: float) -> None:
    # o ponto valida os próprios campos: recusa ao construir, antes de qualquer set
    with pytest.raises(ValueError, match=rf"^{field}: .* is not finite"):
        _point(3, **{field: value})


@pytest.mark.parametrize("field", ["lower", "upper", "realized"])
@pytest.mark.parametrize("value", [True, "0.1", None])
def test_non_number_value_refused(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=rf"^{field}: .* is not a number"):
        _point(3, **{field: value})  # type: ignore[arg-type]


def test_non_symmetric_pair_refused() -> None:
    with pytest.raises(ValueError, match="lower_level/upper_level"):
        _set(lower_level=0.1, upper_level=0.8)


def test_lower_level_zero_refused() -> None:
    with pytest.raises(ValueError, match="lower_level"):
        _set(lower_level=0.0, upper_level=1.0)


def test_lower_level_half_refused() -> None:
    with pytest.raises(ValueError, match="lower_level"):
        _set(lower_level=0.5, upper_level=0.5)


def test_lower_level_above_half_refused() -> None:
    with pytest.raises(ValueError, match="lower_level"):
        _set(lower_level=0.9, upper_level=0.1)


def test_symmetric_pairs_of_the_plan_accepted() -> None:
    # 0.02 + 0.98 e 0.25 + 0.75 somam 1 exatamente só pelo decimal mais curto
    for low, high in ((0.02, 0.98), (0.1, 0.9), (0.25, 0.75)):
        _set(lower_level=low, upper_level=high)


@pytest.mark.parametrize(
    ("field", "patch"),
    [
        ("decision_timestamp", {"decision_timestamp": "2024-01-03T21:00:00"}),
        ("target_timestamp", {"target_timestamp": "2024-01-04T21:00:00"}),
        ("decision_timestamp", {"decision_timestamp": "not a timestamp"}),
        ("target_timestamp", {"target_timestamp": "2024-13-45"}),
    ],
)
def test_naive_or_invalid_timestamp_refused(field: str, patch: dict[str, str]) -> None:
    # o ponto recusa o próprio timestamp: o `replace` reconstrói e roda o __post_init__
    with pytest.raises(ValueError, match=rf"^{field}: "):
        replace(_point(3), **patch)


@pytest.mark.parametrize("test_start", ["2024-01-10T21:00:00", "garbage"])
def test_naive_or_invalid_test_start_refused(test_start: str) -> None:
    with pytest.raises(ValueError, match="test_start"):
        _set(test_start=test_start)


def test_exact_level_is_the_shortest_decimal() -> None:
    assert exact_level(0.99) == Fraction(99, 100)
    assert exact_level(0.1) + exact_level(0.9) == 1
    assert exact_level(0.02) + exact_level(0.98) == 1
    assert exact_level(0.1) != Fraction(0.1)  # não é o binário do float
    assert exact_level(1.0) == 1


@pytest.mark.parametrize("bad", [True, False, math.nan, math.inf, -math.inf, "0.1", None])
def test_exact_level_refuses_bool_and_non_finite(bad: object) -> None:
    with pytest.raises(ValueError, match="level"):
        exact_level(bad)  # type: ignore[arg-type]
