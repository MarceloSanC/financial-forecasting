"""Unit do VO `ConformalCoverageSeries` (Stage 7.2, Task 09) — concept §4, ADR 7.2.0004 item 1."""

from __future__ import annotations

import math
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.value_objects.conformal_coverage_series import (  # noqa: E501
    ConformalCoverageSeries,
    ConformalPairLimits,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)

SeriesFactory = Callable[..., CoverageSeries]

pytestmark = pytest.mark.unit

_GRID = (-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03)


def _native(make_series: SeriesFactory, n: int = 3) -> CoverageSeries:
    return make_series([_GRID] * n, [0.001 * i for i in range(n)])


def _limits(pair: tuple[float, float] = (0.1, 0.9), n: int = 3) -> ConformalPairLimits:
    return ConformalPairLimits(pair[0], pair[1], (-0.02,) * n, (0.02,) * n)


def test_valid_series_accepted(make_series: SeriesFactory) -> None:
    series = ConformalCoverageSeries(
        seed=7,
        native=_native(make_series),
        variant="v",
        pairs=[_limits()],  # type: ignore[arg-type]
    )
    assert isinstance(series.pairs, tuple)


def test_limits_length_must_match_the_native_series(make_series: SeriesFactory) -> None:
    with pytest.raises(ValueError, match=r"pairs\[0\] has 2 limits for 3 native points"):
        ConformalCoverageSeries(
            seed=7, native=_native(make_series), variant="v", pairs=(_limits(n=2),)
        )
    with pytest.raises(ValueError, match="lower and upper must align"):
        ConformalPairLimits(0.1, 0.9, (0.0, 0.0), (0.0,))


@pytest.mark.parametrize("side", ["lower", "upper"])
def test_nan_limit_refused_infinite_accepted(side: str) -> None:
    values = {"lower": (-0.02, -0.02), "upper": (0.02, 0.02)}
    values[side] = (math.nan, 0.0)
    with pytest.raises(ValueError, match=rf"{side}\[0\] must be a number \(not NaN\)"):
        ConformalPairLimits(0.1, 0.9, values["lower"], values["upper"])
    infinite = ConformalPairLimits(0.1, 0.9, (-math.inf, 0.0), (math.inf, 0.0))
    assert infinite.lower[0] == -math.inf


def test_pair_must_be_symmetric_and_in_the_native_grid(make_series: SeriesFactory) -> None:
    with pytest.raises(ValueError, match="not a symmetric pair"):
        ConformalPairLimits(0.1, 0.8, (0.0,), (0.0,))
    with pytest.raises(ValueError, match="not a symmetric pair"):
        ConformalPairLimits(0.6, 0.4, (0.0,), (0.0,))
    with pytest.raises(ValueError, match="not a symmetric pair of the native grid"):
        ConformalCoverageSeries(
            seed=7, native=_native(make_series), variant="v", pairs=(_limits((0.2, 0.8)),)
        )


def test_duplicate_pair_refused(make_series: SeriesFactory) -> None:
    with pytest.raises(ValueError, match=r"pairs\[1\] \(0.1, 0.9\) is duplicated"):
        ConformalCoverageSeries(
            seed=7, native=_native(make_series), variant="v", pairs=(_limits(), _limits())
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("seed", True, "seed must be an int"),
        ("variant", "", "variant must be a non-empty string"),
        ("pairs", (), "at least one"),
    ],
)
def test_bad_fields_refused(
    make_series: SeriesFactory, field: str, value: object, message: str
) -> None:
    fields: dict[str, object] = {
        "seed": 7,
        "native": _native(make_series),
        "variant": "v",
        "pairs": (_limits(),),
    }
    fields[field] = value
    with pytest.raises(ValueError, match=message):
        ConformalCoverageSeries(**fields)  # type: ignore[arg-type]
