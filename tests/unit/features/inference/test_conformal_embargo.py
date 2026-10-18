"""Unit do `CalibrationSet` (Stage 7.2, Task 02) — concept §5 I7 e §6 C1: um caso por recusa."""

from __future__ import annotations

import math
import re
from dataclasses import replace
from fractions import Fraction

import pytest

from financial_forecasting.features.inference.application.use_cases.calibrate_conformal import (
    CalibrateConformal,
    CalibrateConformalCommand,
    ConformalPointInput,
    ConformalUnitInput,
    UnitStatus,
)
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


# --- Task 08: a recusa do VO vira `error` só na sua unidade (I7, independência) ---

_Row = tuple[str, str, float, float, float]  # decisão, alvo, q_lo, q_hi, realizado


def _row(day: int, *, target_day: int | None = None, **values: float) -> _Row:
    target = day + 1 if target_day is None else target_day
    return (
        f"2024-01-{day:02d}T21:00:00+00:00",
        f"2024-01-{target:02d}T21:00:00+00:00",
        values.get("lower", -0.02),
        values.get("upper", 0.02),
        values.get("realized", 0.001),
    )


def _unit_input(fold: int, rows: tuple[_Row, ...]) -> ConformalUnitInput:
    """Unidade do use case com um ponto de teste em `_TEST_START`, depois de todo o calib."""
    calib = tuple(
        ConformalPointInput(
            decision_timestamp=decision,
            target_timestamp=target,
            grid={0.1: lower, 0.5: 0.0, 0.9: upper},
            realized=realized,
        )
        for decision, target, lower, upper, realized in rows
    )
    test = (
        ConformalPointInput(
            decision_timestamp=_TEST_START,
            target_timestamp="2024-01-11T21:00:00+00:00",
            grid={0.1: -0.02, 0.5: 0.0, 0.9: 0.02},
            realized=None,
        ),
    )
    return ConformalUnitInput(fold_index=fold, seed=7, horizon=1, calib=calib, test=test)


def _with(row: _Row, index: int, value: str) -> _Row:
    patched = list(row)
    patched[index] = value
    return tuple(patched)  # type: ignore[return-value]


_GOOD = (_row(2), _row(3), _row(4), _row(5))
_VO_REFUSALS: dict[str, tuple[tuple[_Row, ...], str]] = {
    "empty": ((), r"^lower_level/upper_level|^points: the calibration set is empty"),
    "repeated-target": (
        (_row(2), _row(3, target_day=3)),
        r"^points\[1\]\.target_timestamp: .* not strictly after",
    ),
    "out-of-order-target": (
        (_row(2), _row(4), _row(3)),
        r"^points\[2\]\.target_timestamp: .* not strictly after",
    ),
    "decision-at-test-start": (
        (_row(2), _with(_row(9), 0, _TEST_START)),
        r"^points\[1\]\.decision_timestamp: .* not before test_start",
    ),
    "target-at-test-start": (
        (_row(2), _row(9, target_day=10)),
        r"^points\[1\]\.target_timestamp: .* embargo",
    ),
    "non-finite-lower": ((_row(2), _row(3, lower=math.nan)), r"^lower: nan is not finite"),
    "non-finite-upper": ((_row(2), _row(3, upper=math.inf)), r"^upper: inf is not finite"),
    "non-finite-realized": (
        (_row(2), _row(3, realized=-math.inf)),
        r"^realized: -inf is not finite",
    ),
    "naive-timestamp": (
        (_row(2), _with(_row(3), 1, "2024-01-04T21:00:00")),
        r"^target_timestamp: .* has no time zone",
    ),
    "invalid-timestamp": (
        (_row(2), _with(_row(3), 0, "garbage")),
        r"^decision_timestamp: 'garbage' is not an ISO 8601",
    ),
}


@pytest.mark.parametrize(
    ("bad_rows", "expected"), list(_VO_REFUSALS.values()), ids=list(_VO_REFUSALS)
)
def test_vo_refusal_becomes_error_only_in_its_unit(
    bad_rows: tuple[_Row, ...], expected: str
) -> None:
    good = (_unit_input(0, _GOOD), _unit_input(2, _GOOD[1:]))
    command = CalibrateConformalCommand(
        units=(good[0], _unit_input(1, bad_rows), good[1]),
        pairs=((0.1, 0.9),),
        variants=("split_cqr_asymmetric_unweighted_v1", "nexcp_fixed_geometric_weights_v1"),
        nexcp_rho=0.99,
    )
    rows = CalibrateConformal()(command).units
    bad = [r for r in rows if r.fold_index == 1]
    assert {r.status for r in bad} == {UnitStatus.ERROR}
    assert all(re.search(expected, r.reason or "") for r in bad), [r.reason for r in bad]
    without = CalibrateConformal()(replace(command, units=good)).units
    assert [r for r in rows if r.fold_index != 1] == list(without)
    assert {r.status for r in without} == {UnitStatus.OK}
