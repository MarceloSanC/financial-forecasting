"""Unit do use case `CalibrateConformal` (Stage 7.2, Task 08) — concept §4, I6, I7, §6 C1, C3."""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta
from fractions import Fraction

import pytest

from financial_forecasting.features.inference.application.use_cases.calibrate_conformal import (
    CalibrateConformal,
    CalibrateConformalCommand,
    ConformalPointInput,
    ConformalUnitInput,
    UnitStatus,
    calibration_set_for,
)
from financial_forecasting.features.inference.domain.services.conformal_calibrator import (
    ConformalCalibrator,
    ConformalVariant,
    beta_reference,
)

_SPLIT = ConformalVariant.SPLIT_CQR.value
_NEXCP = ConformalVariant.NEXCP.value
_PAIRS = ((0.1, 0.9), (0.25, 0.75))
_LEVELS = (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98)
_START = datetime(2020, 1, 6, 21, tzinfo=UTC)
_N_CALIB = 40
_N_TEST = 5


def _ts(day: int) -> str:
    return (_START + timedelta(days=day)).isoformat()


def _grid(rng: random.Random) -> dict[float, float]:
    center = rng.uniform(-0.01, 0.01)
    return {level: center + (level - 0.5) * rng.uniform(0.05, 0.1) for level in _LEVELS}


def _unit(
    fold: int = 0, seed: int = 7, horizon: int = 1, *, rng_seed: int = 20261017
) -> ConformalUnitInput:
    rng = random.Random(rng_seed + 1000 * fold + 10 * seed + horizon)
    calib = tuple(
        ConformalPointInput(
            decision_timestamp=_ts(i),
            target_timestamp=_ts(i + horizon),
            grid=_grid(rng),
            realized=rng.gauss(0.0, 0.03),
        )
        for i in range(_N_CALIB)
    )
    first_test = _N_CALIB + horizon + 1
    test = tuple(
        ConformalPointInput(
            decision_timestamp=_ts(first_test + j),
            target_timestamp=_ts(first_test + j + horizon),
            grid=_grid(rng),
            realized=None,
        )
        for j in range(_N_TEST)
    )
    return ConformalUnitInput(fold_index=fold, seed=seed, horizon=horizon, calib=calib, test=test)


def _command(
    units: tuple[ConformalUnitInput, ...],
    *,
    pairs: tuple[tuple[float, float], ...] = _PAIRS,
    variants: tuple[str, ...] = (_SPLIT, _NEXCP),
    rho: float | None = 0.99,
) -> CalibrateConformalCommand:
    return CalibrateConformalCommand(units=units, pairs=pairs, variants=variants, nexcp_rho=rho)


def test_one_calibration_per_unit_pair_tail_variant_in_order() -> None:
    units = (_unit(1, 7, 1), _unit(0, 9, 7), _unit(0, 7, 7), _unit(0, 7, 1))
    result = CalibrateConformal()(_command(units))
    keys = [
        (r.fold_index, r.seed, r.horizon, (r.lower_level, r.upper_level), r.variant)
        for r in result.units
    ]
    expected = [
        (fold, seed, horizon, pair, variant)
        for fold, seed, horizon in sorted((u.fold_index, u.seed, u.horizon) for u in units)
        for pair in _PAIRS
        for variant in (_SPLIT, _NEXCP)
    ]
    assert keys == expected
    assert all(r.status is UnitStatus.OK for r in result.units)
    assert {r.lower.tail for r in result.units if r.lower} == {"lower"}
    assert {r.upper.tail for r in result.units if r.upper} == {"upper"}


def test_tail_corrections_equal_the_calibrator_called_directly() -> None:
    unit = _unit()
    result = CalibrateConformal()(_command((unit,)))
    for row in result.units:
        calib = calibration_set_for(unit, (row.lower_level, row.upper_level))
        assert not isinstance(calib, str)
        rho = 0.99 if row.variant == _NEXCP else None
        direct = ConformalCalibrator.calibrate(
            calib, variant=ConformalVariant(row.variant), rho=rho
        )
        assert row.lower == direct.lower
        assert row.upper == direct.upper
        assert row.rho == rho


def test_calib_scores_come_from_the_pair_levels_of_the_grid() -> None:
    # oráculo independente de `calibration_set_for`: E_lo = grid[tau_lo] - y e
    # E_hi = y - grid[tau_hi], posto ceil((n+1)(1-alpha)) sobre os escores ordenados
    unit = _unit()
    rows = CalibrateConformal()(_command((unit,), variants=(_SPLIT,), rho=None)).units
    n = len(unit.calib)
    for row in rows:
        assert row.lower is not None
        assert row.upper is not None
        low, high = row.lower_level, row.upper_level
        realized = [p.realized for p in unit.calib]
        assert all(y is not None for y in realized)
        lower_scores = sorted(p.grid[low] - p.realized for p in unit.calib)  # type: ignore[operator]
        upper_scores = sorted(p.realized - p.grid[high] for p in unit.calib)  # type: ignore[operator]
        rank_lo = math.ceil((n + 1) * (1 - Fraction(repr(low))))
        rank_hi = math.ceil((n + 1) * Fraction(repr(high)))
        assert row.lower.correction == lower_scores[rank_lo - 1]
        assert row.upper.correction == upper_scores[rank_hi - 1]


def test_test_limits_aligned_to_the_test_points() -> None:
    unit = _unit()
    result = CalibrateConformal()(_command((unit,)))
    for row in result.units:
        assert row.lower is not None
        assert row.upper is not None
        low, high = row.lower_level, row.upper_level
        assert row.test_lower == tuple(p.grid[low] - row.lower.correction for p in unit.test)
        assert row.test_upper == tuple(p.grid[high] + row.upper.correction for p in unit.test)
        assert len(row.test_lower) == _N_TEST


def test_beta_only_for_the_split_variant_per_tail() -> None:
    result = CalibrateConformal()(_command((_unit(),)))
    for row in result.units:
        assert row.lower is not None
        assert row.upper is not None
        if row.variant == _SPLIT:
            assert row.lower_beta == beta_reference(row.lower.n, row.lower.alpha)
            assert row.upper_beta == beta_reference(row.upper.n, row.upper.alpha)
            assert row.lower_beta is not None
        else:
            assert row.lower_beta is None
            assert row.upper_beta is None


def _with_calib_point(
    unit: ConformalUnitInput, index: int, **changes: object
) -> ConformalUnitInput:
    calib = list(unit.calib)
    point = calib[index]
    calib[index] = ConformalPointInput(
        decision_timestamp=str(changes.get("decision_timestamp", point.decision_timestamp)),
        target_timestamp=str(changes.get("target_timestamp", point.target_timestamp)),
        grid=changes.get("grid", point.grid),  # type: ignore[arg-type]
        realized=changes.get("realized", point.realized),  # type: ignore[arg-type]
    )
    return ConformalUnitInput(unit.fold_index, unit.seed, unit.horizon, tuple(calib), unit.test)


def test_calib_point_without_realized_is_undefined() -> None:
    bad = _with_calib_point(_unit(), 3, realized=None)
    rows = CalibrateConformal()(_command((bad,))).units
    assert {r.status for r in rows} == {UnitStatus.UNDEFINED}
    assert all("realized" in (r.reason or "") for r in rows)


def test_grid_without_a_pair_level_is_undefined_only_for_that_pair() -> None:
    unit = _unit()
    grid = {k: v for k, v in unit.calib[5].grid.items() if k != 0.25}  # noqa: PLR2004
    bad = _with_calib_point(unit, 5, grid=grid)
    rows = CalibrateConformal()(_command((bad,))).units
    by_pair = {(r.lower_level, r.upper_level): r.status for r in rows}
    assert by_pair == {(0.1, 0.9): UnitStatus.OK, (0.25, 0.75): UnitStatus.UNDEFINED}
    undefined = [r for r in rows if r.status is UnitStatus.UNDEFINED]
    assert all("0.25" in (r.reason or "") for r in undefined)


def test_unit_without_test_points_is_undefined() -> None:
    unit = _unit()
    bare = ConformalUnitInput(unit.fold_index, unit.seed, unit.horizon, unit.calib, ())
    rows = CalibrateConformal()(_command((bare,))).units
    assert {r.status for r in rows} == {UnitStatus.UNDEFINED}
    assert all("test" in (r.reason or "") for r in rows)


def test_non_ok_results_carry_reason_and_no_values() -> None:
    bad = _with_calib_point(_unit(), 0, realized=math.nan)  # recusa do VO → error
    rows = CalibrateConformal()(_command((bad,))).units
    assert {r.status for r in rows} == {UnitStatus.ERROR}
    for row in rows:
        assert row.reason
        assert "realized" in row.reason
        assert (row.lower, row.upper, row.lower_beta, row.upper_beta) == (None,) * 4
        assert (row.test_lower, row.test_upper) == (None, None)
        assert row.rho == (0.99 if row.variant == _NEXCP else None)


@pytest.mark.parametrize(
    "overrides",
    [
        {"units": "duplicate"},
        {"variants": (_SPLIT, "aci")},
        {"rho": 0.0},
        {"rho": 1.5},
        {"rho": math.nan},
        {"rho": None},
        {"pairs": ((0.1, 0.8),)},
        {"pairs": ((0.0, 1.0),)},
        {"pairs": ((0.5, 0.5),)},
        {"pairs": ((0.1, 0.9), (0.1, 0.9))},
        {"variants": (_SPLIT, _SPLIT)},
    ],
    ids=[
        "duplicate-unit",
        "variant-aci",
        "rho-0",
        "rho-1.5",
        "rho-nan",
        "rho-none",
        "pair-0.1-0.8",
        "tau-lo-0",
        "tau-lo-0.5",
        "duplicate-pair",
        "duplicate-variant",
    ],
)
def test_command_errors_raise_before_any_unit(
    overrides: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []

    def spy(*args: object, **kwargs: object) -> object:
        calls.append(args)
        raise AssertionError("calibrate must not be called")

    monkeypatch.setattr(ConformalCalibrator, "calibrate", staticmethod(spy))
    units: tuple[ConformalUnitInput, ...] = (_unit(0), _unit(1))
    if overrides.get("units") == "duplicate":
        units = (_unit(0), _unit(1), _unit(0))
    command = _command(
        units,
        pairs=overrides.get("pairs", _PAIRS),  # type: ignore[arg-type]
        variants=overrides.get("variants", (_SPLIT, _NEXCP)),  # type: ignore[arg-type]
        rho=overrides.get("rho", 0.99),  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match=r"^(units|variants|nexcp_rho|pairs):"):
        CalibrateConformal()(command)
    assert calls == []


def test_rho_none_accepted_without_nexcp() -> None:
    rows = CalibrateConformal()(_command((_unit(),), variants=(_SPLIT,), rho=None)).units
    assert {r.status for r in rows} == {UnitStatus.OK}
    assert {r.rho for r in rows} == {None}


# --- Checkpoint C do bloco 2 (task-08-fix) --------------------------------------------


def _with_test_point(unit: ConformalUnitInput, index: int, **changes: object) -> ConformalUnitInput:
    test = list(unit.test)
    point = test[index]
    test[index] = ConformalPointInput(
        decision_timestamp=str(changes.get("decision_timestamp", point.decision_timestamp)),
        target_timestamp=str(changes.get("target_timestamp", point.target_timestamp)),
        grid=changes.get("grid", point.grid),  # type: ignore[arg-type]
        realized=None,
    )
    return ConformalUnitInput(unit.fold_index, unit.seed, unit.horizon, unit.calib, tuple(test))


def _statuses(unit: ConformalUnitInput) -> set[UnitStatus]:
    return {r.status for r in CalibrateConformal()(_command((unit,))).units}


def test_test_points_out_of_order_are_undefined() -> None:
    unit = _unit()
    swapped = ConformalUnitInput(
        unit.fold_index, unit.seed, unit.horizon, unit.calib, tuple(reversed(unit.test))
    )
    rows = CalibrateConformal()(_command((swapped,))).units
    assert {r.status for r in rows} == {UnitStatus.UNDEFINED}
    assert all("not strictly after the previous test decision" in (r.reason or "") for r in rows)


def test_test_start_is_the_first_test_decision_against_an_overlapping_calib() -> None:
    # um alvo de calib depois da 1ª decisão de teste, mas antes da última: o embargo
    # vale contra a 1ª (test_start), então a unidade é error
    unit = _unit()
    last_calib = len(unit.calib) - 1
    overlap = _with_calib_point(unit, last_calib, target_timestamp=unit.test[1].decision_timestamp)
    rows = CalibrateConformal()(_command((overlap,))).units
    assert {r.status for r in rows} == {UnitStatus.ERROR}
    assert all("embargo" in (r.reason or "") for r in rows)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, "0.01", True])
def test_bad_test_grid_value_is_error_of_the_unit(value: object) -> None:
    unit = _unit()
    grid = {**unit.test[2].grid, 0.1: value}
    bad = _with_test_point(unit, 2, grid=grid)
    good = _unit(fold=1)
    rows = CalibrateConformal()(_command((bad, good))).units
    by_fold = {(r.fold_index, r.lower_level): r for r in rows}
    assert by_fold[(0, 0.1)].status is UnitStatus.ERROR
    assert "test[2].grid[0.1]" in (by_fold[(0, 0.1)].reason or "")
    assert by_fold[(0, 0.25)].status is UnitStatus.OK  # o outro par não usa o 0,1
    assert {r.status for r in rows if r.fold_index == 1} == {UnitStatus.OK}


@pytest.mark.parametrize(
    "patch",
    [{"decision_timestamp": "2020-03-01T21:00:00"}, {"target_timestamp": "garbage"}],
)
def test_bad_test_timestamp_is_error_of_the_unit(patch: dict[str, str]) -> None:
    bad = _with_test_point(_unit(), 0, **patch)
    rows = CalibrateConformal()(_command((bad,))).units
    assert {r.status for r in rows} == {UnitStatus.ERROR}
    assert all(r.reason and r.reason.startswith("test[0].") for r in rows)


def test_missing_realized_wins_over_a_vo_error_anywhere() -> None:
    unit = _with_calib_point(_unit(), 0, realized=math.nan)  # error do VO no 1º ponto
    unit = _with_calib_point(unit, 30, realized=None)  # undefined num ponto posterior
    assert _statuses(unit) == {UnitStatus.UNDEFINED}


def test_rho_one_is_accepted() -> None:
    rows = CalibrateConformal()(_command((_unit(),), variants=(_NEXCP,), rho=1.0)).units
    assert {r.status for r in rows} == {UnitStatus.OK}
    assert {r.rho for r in rows} == {1.0}


def test_test_point_without_a_pair_level_is_undefined() -> None:
    unit = _unit()
    grid = {k: v for k, v in unit.test[1].grid.items() if k != 0.25}  # noqa: PLR2004
    rows = CalibrateConformal()(_command((_with_test_point(unit, 1, grid=grid),))).units
    by_pair = {r.lower_level: r for r in rows if r.variant == _SPLIT}
    assert by_pair[0.25].status is UnitStatus.UNDEFINED
    assert "test point" in (by_pair[0.25].reason or "")
    assert by_pair[0.1].status is UnitStatus.OK


def test_other_exceptions_of_the_calibrator_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> object:
        raise TypeError("programming error")

    monkeypatch.setattr(ConformalCalibrator, "calibrate", staticmethod(boom))
    with pytest.raises(TypeError, match="programming error"):
        CalibrateConformal()(_command((_unit(),)))


def test_arithmetic_error_of_the_calibrator_is_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def divide(*args: object, **kwargs: object) -> object:
        raise ZeroDivisionError("division by zero")

    monkeypatch.setattr(ConformalCalibrator, "calibrate", staticmethod(divide))
    rows = CalibrateConformal()(_command((_unit(),))).units
    assert {r.status for r in rows} == {UnitStatus.ERROR}
    assert {r.reason for r in rows} == {"division by zero"}


@pytest.mark.parametrize(
    "nan_at", [0, 4], ids=["nan-before-the-disorder", "nan-after-the-disorder"]
)
def test_test_order_is_checked_before_values(nan_at: int) -> None:
    # os dois defeitos juntos, nas duas ordens: a desordem (undefined) vale antes do NaN
    # (error) (Checkpoint C, C3-6)
    unit = _unit()
    test = list(unit.test)
    test[2], test[3] = test[3], test[2]
    swapped = ConformalUnitInput(unit.fold_index, unit.seed, unit.horizon, unit.calib, tuple(test))
    grid = {**swapped.test[nan_at].grid, 0.1: math.nan}
    bad = _with_test_point(swapped, nan_at, grid=grid)
    rows = CalibrateConformal()(_command((bad,))).units
    assert {r.status for r in rows} == {UnitStatus.UNDEFINED}
    assert all("not strictly after the previous test decision" in (r.reason or "") for r in rows)
