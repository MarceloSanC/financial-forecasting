"""Unit test de `adjacent_collapse_rates` (Stage 6.6 Task 06; CA6; ADR 6.6.0002 T2).

Fixtures analíticas com valores diádicos (exatos em float64), grade de 3 ou 5 níveis:

- q_0,25 = q_0,5 < q_0,75: colapso adjacente sem nenhum colapso simétrico;
- gaps internos 0,125 cada com tolerância 0,125: os adjacentes colapsam, o par simétrico
  (amplitude 0,25 > tol) não — as taxas simétricas não determinam as adjacentes;
- série 100 % degenerada: todas as taxas `None` (o denominador são as linhas não
  degeneradas, a mesma máscara do gate);
- o relatório do gate (caminho do veredito) não muda.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.services.degeneracy_gate import (
    DegeneracyGate,
    adjacent_collapse_rates,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)

SeriesFactory = Callable[..., CoverageSeries]

_THREE = (0.25, 0.5, 0.75)
_FIVE = (0.1, 0.25, 0.5, 0.75, 0.9)
_EIGHTH = 0.125
_HALF = 0.5


def _series(
    make_series: SeriesFactory, grids: list[tuple[float, ...]], levels: tuple[float, ...]
) -> CoverageSeries:
    return make_series(grids, [0.0] * len(grids), levels=levels, direct=True)


@pytest.mark.unit
def test_adjacent_tie_without_symmetric_collapse(make_series: SeriesFactory) -> None:
    series = _series(make_series, [(0.0, 0.0, 0.5), (0.0, 0.25, 0.5)], _THREE)
    rates = adjacent_collapse_rates(series, tolerance=0.0)
    assert rates == ((0.25, 0.5, _HALF), (0.5, 0.75, 0.0))
    symmetric = DegeneracyGate.evaluate(series, tolerance=0.0).pair_collapse_rates
    assert symmetric == ((0.25, 0.75, 0.0),)


@pytest.mark.unit
def test_inner_gaps_within_tolerance_add_up_beyond_it(make_series: SeriesFactory) -> None:
    grid = (0.0, 0.125, 0.25, 0.375, 0.5)
    series = _series(make_series, [grid], _FIVE)
    rates = adjacent_collapse_rates(series, tolerance=_EIGHTH)
    assert [rate for _, _, rate in rates] == [1.0, 1.0, 1.0, 1.0]
    symmetric = dict(
        ((low, high), rate)
        for low, high, rate in DegeneracyGate.evaluate(
            series, tolerance=_EIGHTH
        ).pair_collapse_rates
    )
    assert symmetric[0.25, 0.75] == 0.0
    assert symmetric[0.1, 0.9] == 0.0


@pytest.mark.unit
def test_fully_degenerate_series_has_no_rate(make_series: SeriesFactory) -> None:
    series = _series(make_series, [(0.1, 0.1, 0.1), (0.2, 0.2, 0.2)], _THREE)
    assert adjacent_collapse_rates(series, tolerance=0.0) == ((0.25, 0.5, None), (0.5, 0.75, None))


@pytest.mark.unit
def test_degenerate_rows_are_left_out_of_the_denominator(make_series: SeriesFactory) -> None:
    series = _series(make_series, [(0.1, 0.1, 0.1), (0.0, 0.0, 0.5), (0.0, 0.25, 0.5)], _THREE)
    assert adjacent_collapse_rates(series, tolerance=0.0)[0] == (0.25, 0.5, _HALF)


@pytest.mark.unit
@pytest.mark.parametrize("tolerance", [-0.1, float("nan")])
def test_invalid_tolerance(make_series: SeriesFactory, tolerance: float) -> None:
    series = _series(make_series, [(0.0, 0.25, 0.5)], _THREE)
    with pytest.raises(ValueError, match="tolerance"):
        adjacent_collapse_rates(series, tolerance=tolerance)
