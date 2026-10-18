"""Contrato do port `ConformalCalibration` do `evaluation` (Stage 7.2, Task 15; ADR 7.2.0003).

Duas pernas, tipadas pelo Protocol do evaluation: `fake` (`FakeConformalCalibration`,
correções zero e as regras do fornecedor) e `real` (o use case `CalibrateConformal` do
`inference`, por duck typing — #93). As duas passam pelas mesmas asserções de forma,
status e ordem; os valores das correções só são conferidos na perna fake (zero, por
desenho) e, no real, contra a própria relação limite = q̂ ∓ Q.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from financial_forecasting.features.evaluation.application.ports.out.conformal_calibration import (
    ConformalCalibration,
)
from financial_forecasting.features.inference.application.use_cases.calibrate_conformal import (
    CalibrateConformal,
    CalibrateConformalCommand,
    ConformalPointInput,
    ConformalUnitInput,
    UnitStatus,
)
from tests.fakes.features.evaluation.fake_conformal_calibration import FakeConformalCalibration

pytestmark = pytest.mark.contract

_SPLIT = "split_cqr_asymmetric_unweighted_v1"
_NEXCP = "nexcp_fixed_geometric_weights_v1"
_PAIRS = ((0.1, 0.9), (0.25, 0.75))
_LEVELS = (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98)
_START = datetime(2020, 1, 6, 21, tzinfo=UTC)
_FACTORIES: dict[str, Callable[[], ConformalCalibration]] = {
    "fake": FakeConformalCalibration,
    "real": CalibrateConformal,
}


@pytest.fixture(params=list(_FACTORIES), ids=list(_FACTORIES))
def port(request: pytest.FixtureRequest) -> ConformalCalibration:
    return _FACTORIES[request.param]()


def _ts(day: int) -> str:
    return (_START + timedelta(days=day)).isoformat()


def _unit(fold: int, seed: int = 1, horizon: int = 1, *, n: int = 40) -> ConformalUnitInput:
    rng = random.Random(20261017 + fold)

    def grid() -> dict[float, float]:
        center = rng.uniform(-0.01, 0.01)
        return {level: center + (level - 0.5) * 0.08 for level in _LEVELS}

    calib = tuple(
        ConformalPointInput(_ts(i), _ts(i + horizon), grid(), rng.gauss(0.0, 0.03))
        for i in range(n)
    )
    test = tuple(
        ConformalPointInput(_ts(n + 2 + j), _ts(n + 2 + j + horizon), grid(), None)
        for j in range(5)
    )
    return ConformalUnitInput(fold, seed, horizon, calib, test)


def _command(
    units: tuple[ConformalUnitInput, ...],
    *,
    variants: tuple[str, ...] = (_SPLIT, _NEXCP),
    rho: float | None = 0.99,
) -> CalibrateConformalCommand:
    return CalibrateConformalCommand(units=units, pairs=_PAIRS, variants=variants, nexcp_rho=rho)


def test_ok_unit_returns_one_result_per_pair_tail_variant_in_order(
    port: ConformalCalibration,
) -> None:
    result = port(_command((_unit(1), _unit(0))))
    keys = [(r.fold_index, (r.lower_level, r.upper_level), r.variant) for r in result.units]
    assert keys == [(f, p, v) for f in (0, 1) for p in _PAIRS for v in (_SPLIT, _NEXCP)]
    for row in result.units:
        assert row.status is UnitStatus.OK
        assert row.lower is not None
        assert row.upper is not None
        assert (row.lower.tail, row.upper.tail) == ("lower", "upper")
        assert row.rho == (0.99 if row.variant == _NEXCP else None)


def test_incomplete_input_unit_is_undefined(port: ConformalCalibration) -> None:
    unit = _unit(0)
    calib = list(unit.calib)
    calib[3] = ConformalPointInput(
        calib[3].decision_timestamp, calib[3].target_timestamp, calib[3].grid, None
    )
    bad = ConformalUnitInput(0, 1, 1, tuple(calib), unit.test)
    rows = port(_command((bad,))).units
    assert {r.status for r in rows} == {UnitStatus.UNDEFINED}
    assert all("realized" in (r.reason or "") for r in rows)


def test_embargo_violation_unit_is_error_and_neighbours_ok(port: ConformalCalibration) -> None:
    unit = _unit(1)
    calib = list(unit.calib)
    last = calib[-1]
    calib[-1] = ConformalPointInput(
        last.decision_timestamp, unit.test[0].decision_timestamp, last.grid, last.realized
    )
    bad = ConformalUnitInput(1, 1, 1, tuple(calib), unit.test)
    rows = port(_command((_unit(0), bad, _unit(2)))).units
    by_fold = {r.fold_index: r.status for r in rows}
    assert {r.status for r in rows if r.fold_index == 1} == {UnitStatus.ERROR}
    assert all("embargo" in (r.reason or "") for r in rows if r.fold_index == 1)
    assert by_fold[0] is UnitStatus.OK
    assert by_fold[2] is UnitStatus.OK


@pytest.mark.parametrize(
    ("units", "variants", "rho", "message"),
    [
        ((0, 0), (_SPLIT,), None, "^units:"),
        ((0,), (_SPLIT, "aci"), 0.99, "^variants:"),
        ((0,), (_NEXCP,), None, "^nexcp_rho:"),
    ],
    ids=["duplicate-unit", "unknown-variant", "rho-missing-for-nexcp"],
)
def test_command_errors_raise(
    port: ConformalCalibration,
    units: tuple[int, ...],
    variants: tuple[str, ...],
    rho: float | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        port(_command(tuple(_unit(f) for f in units), variants=variants, rho=rho))


def test_non_ok_fields_are_none(port: ConformalCalibration) -> None:
    unit = _unit(0)
    bare = ConformalUnitInput(0, 1, 1, unit.calib, ())
    for row in port(_command((bare,))).units:
        assert row.status is UnitStatus.UNDEFINED
        assert row.reason
        assert (row.lower, row.upper, row.lower_beta, row.upper_beta) == (None,) * 4
        assert (row.test_lower, row.test_upper) == (None, None)


def test_test_limits_aligned_to_test_points(port: ConformalCalibration) -> None:
    unit = _unit(0)
    for row in port(_command((unit,))).units:
        assert row.lower is not None
        assert row.upper is not None
        assert row.test_lower == tuple(
            p.grid[row.lower_level] - row.lower.correction for p in unit.test
        )
        assert row.test_upper == tuple(
            p.grid[row.upper_level] + row.upper.correction for p in unit.test
        )


# --- só a perna fake ------------------------------------------------------------------


def test_fake_zero_corrections_give_the_native_quantiles() -> None:
    unit = _unit(0)
    for row in FakeConformalCalibration()(_command((unit,))).units:
        assert row.lower is not None
        assert row.upper is not None
        assert (row.lower.correction, row.upper.correction) == (0.0, 0.0)
        assert not (math.isinf(row.lower.correction) or row.lower.infinite)
        assert row.test_lower == tuple(p.grid[row.lower_level] for p in unit.test)
        assert row.test_upper == tuple(p.grid[row.upper_level] for p in unit.test)


def test_fake_forced_status() -> None:
    fake = FakeConformalCalibration(force_status={(1, 1, 1): ("error", "forced")})
    rows = fake(_command((_unit(0), _unit(1)))).units
    assert {(r.fold_index, r.status, r.reason) for r in rows if r.fold_index == 1} == {
        (1, UnitStatus.ERROR, "forced")
    }
    assert {r.status for r in rows if r.fold_index == 0} == {UnitStatus.OK}
    assert len(fake.calls) == 1


def test_fake_raises_when_configured() -> None:
    fake = FakeConformalCalibration(raises=RuntimeError("port down"))
    with pytest.raises(RuntimeError, match="port down"):
        fake(_command((_unit(0),)))
    assert len(fake.calls) == 1
