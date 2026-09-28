"""Unit test do VO `CoverageSeries` — invariantes da série alinhada por horizonte.

Prova (concept 6.1 A1, I1/I2/I3, C1/C2; ADR `6_1_0002`):

- um `ValueError` por caso de C1 (série mal-formada) e de C2 (não-finito), na
  construção — nunca linha descartada;
- `symmetric_pairs` e `guardrail_applied_rate` numa grade de 7 níveis;
- a grade (0.02, …, 0.98) é aceita apesar de `1 - 0.98 != 0.02` em float;
- `scored_values` devolve `guardrail_values`, não `raw_values` (I3);
- o VO é frozen.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable

import pytest

from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)

SeriesFactory = Callable[..., CoverageSeries]

_LEVELS = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
_GRID = (-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03)
_CROSSED = (-0.02, -0.03, -0.01, 0.0, 0.01, 0.02, 0.03)  # raw cruzado nos dois primeiros
_TAU_LOW = 0.02
_TAU_HIGH = 0.98
_WIDE_LEVELS = (_TAU_LOW, 0.05, 0.1, 0.5, 0.9, 0.95, _TAU_HIGH)
_HORIZON = 7
_ONE_IN_FOUR = 0.25
# Tolerância de simetria do ADR 6.1.0002 item 2 (espelha a constante do VO).
_SYMMETRY_BOUND = 1e-12


@pytest.mark.unit
def test_well_formed_series_exposes_points_and_scored_values(make_series: SeriesFactory) -> None:
    """Caminho feliz: T, horizonte e o vetor pontuado (pós-guardrail) por ponto."""
    series = make_series([_GRID, _CROSSED], [0.004, -0.001], horizon=_HORIZON)

    assert series.n_points == len(series.realized) == len(series.target_timestamps)
    assert series.horizon == _HORIZON
    assert series.scored_values(0) == _GRID
    # I3: o ponto 1 tem raw cruzado; o pontuado é o rearranjado, nunca o bruto.
    assert series.scored_values(1) == tuple(sorted(_CROSSED))
    assert series.scored_values(1) != series.forecasts[1].raw_values


@pytest.mark.unit
def test_symmetric_pairs_on_seven_level_grid(make_series: SeriesFactory) -> None:
    """A1: 3 pares (τ_l, τ_u) com τ_l < 0.5, do extremo para dentro; 0.5 não forma par."""
    series = make_series([_GRID], [0.0])

    assert series.symmetric_pairs == ((0.05, 0.95), (0.1, 0.9), (0.25, 0.75))


@pytest.mark.unit
def test_guardrail_applied_rate_on_seven_level_grid(make_series: SeriesFactory) -> None:
    """A1: fração de pontos com `guardrail_applied` (1 de 4 cruzado → 0.25)."""
    series = make_series([_GRID, _CROSSED, _GRID, _GRID], [0.0, 0.0, 0.0, 0.0])

    assert series.guardrail_applied_rate == _ONE_IN_FOUR


@pytest.mark.unit
def test_guardrail_applied_rate_is_zero_without_crossing(make_series: SeriesFactory) -> None:
    """Sem cruzamento, a taxa é 0 (não `None` nem `nan`)."""
    series = make_series([_GRID, _GRID], [0.0, 0.0])

    assert series.guardrail_applied_rate == 0.0


@pytest.mark.unit
def test_wide_grid_accepted_despite_float_asymmetry(make_series: SeriesFactory) -> None:
    """A1: (0.02, …, 0.98) é aceita — `1 - 0.98 != 0.02`, mas a soma cabe em 1e-12."""
    assert 1 - _TAU_HIGH != _TAU_LOW  # a premissa do caso, em float64
    series = make_series([_GRID], [0.0], levels=_WIDE_LEVELS)

    assert series.symmetric_pairs[0] == (_TAU_LOW, _TAU_HIGH)


@pytest.mark.unit
def test_is_frozen(make_series: SeriesFactory) -> None:
    """VO imutável: atribuição ergue `FrozenInstanceError`."""
    series = make_series([_GRID], [0.0])

    with pytest.raises(dataclasses.FrozenInstanceError):
        series.horizon = 2  # type: ignore[misc]


# --- C1 — série mal-formada ---------------------------------------------------


@pytest.mark.unit
def test_mismatched_lengths_raise(make_series: SeriesFactory) -> None:
    """C1: forecasts e realized com comprimentos diferentes."""
    with pytest.raises(ValueError, match="align 1:1"):
        make_series([_GRID, _GRID], [0.0])


@pytest.mark.unit
def test_mismatched_timestamps_length_raises(make_series: SeriesFactory) -> None:
    """C1: target_timestamps com comprimento diferente dos pontos."""
    with pytest.raises(ValueError, match="align 1:1"):
        make_series([_GRID], [0.0], timestamps=("2024-01-02T00:00:00+00:00", "2024-01-03"))


@pytest.mark.unit
def test_empty_series_raises(make_series: SeriesFactory) -> None:
    """C1: T = 0."""
    with pytest.raises(ValueError, match="at least one point"):
        make_series([], [])


@pytest.mark.unit
def test_duplicated_timestamp_raises(make_series: SeriesFactory) -> None:
    """C1: timestamp repetido (o mix de horizontes mais comum) ergue."""
    stamp = "2024-01-02T00:00:00+00:00"
    with pytest.raises(ValueError, match="strictly increasing"):
        make_series([_GRID, _GRID], [0.0, 0.0], timestamps=(stamp, stamp))


@pytest.mark.unit
def test_out_of_order_timestamp_raises(make_series: SeriesFactory) -> None:
    """C1: timestamps fora de ordem; a mensagem nomeia o índice do ponto."""
    stamps = ("2024-01-03T00:00:00+00:00", "2024-01-02T00:00:00+00:00")
    with pytest.raises(ValueError, match="point 1"):
        make_series([_GRID, _GRID], [0.0, 0.0], timestamps=stamps)


@pytest.mark.unit
@pytest.mark.parametrize(
    "levels",
    [(0.0, 0.5, 1.0), (-0.1, 0.5, 1.1), (math.nan, 0.5, 0.5)],
    ids=["closed-bounds", "outside", "nan"],
)
def test_level_outside_open_unit_interval_raises(
    make_series: SeriesFactory, levels: tuple[float, ...]
) -> None:
    """C1: nível fora de (0, 1)."""
    with pytest.raises(ValueError, match=r"in \(0, 1\)"):
        make_series([(0.0, 0.0, 0.0)], [0.0], levels=levels, direct=True)


@pytest.mark.unit
def test_levels_not_strictly_increasing_raise(make_series: SeriesFactory) -> None:
    """C1: `levels` fora de ordem ergue."""
    with pytest.raises(ValueError, match="strictly increasing"):
        make_series([(0.0, 0.0, 0.0)], [0.0], levels=(0.9, 0.5, 0.1), direct=True)


@pytest.mark.unit
def test_duplicated_levels_raise(make_series: SeriesFactory) -> None:
    """C1: nível repetido não é estritamente crescente."""
    with pytest.raises(ValueError, match="strictly increasing"):
        make_series([(0.0, 0.0, 0.0)], [0.0], levels=(0.1, 0.1, 0.9), direct=True)


@pytest.mark.unit
def test_forecast_levels_differ_from_series_levels_raise() -> None:
    """C1: `forecast.levels != levels` num ponto; a mensagem nomeia o índice."""
    other = QuantileForecast.from_raw(levels=(0.1, 0.5, 0.9), raw_values=(-0.01, 0.0, 0.01))
    good = QuantileForecast.from_raw(levels=_LEVELS, raw_values=_GRID)
    with pytest.raises(ValueError, match="point 1: forecast levels"):
        CoverageSeries(
            horizon=1,
            levels=_LEVELS,
            target_timestamps=("2024-01-02T00:00:00+00:00", "2024-01-03T00:00:00+00:00"),
            forecasts=(good, other),
            realized=(0.0, 0.0),
        )


@pytest.mark.unit
def test_asymmetric_grid_raises(make_series: SeriesFactory) -> None:
    """C1: grade assimétrica além de 1e-12 (0.1 + 0.8 ≠ 1)."""
    with pytest.raises(ValueError, match="symmetric"):
        make_series([(0.0, 0.0, 0.0)], [0.0], levels=(0.1, 0.5, 0.8))


@pytest.mark.unit
def test_asymmetry_just_above_tolerance_raises(make_series: SeriesFactory) -> None:
    """C1: a tolerância é 1e-12 — um desvio de 1e-9 já é assimetria."""
    with pytest.raises(ValueError, match="symmetric"):
        make_series([(0.0, 0.0, 0.0)], [0.0], levels=(0.1, 0.5, 0.9 + 1e-9))


@pytest.mark.unit
def test_asymmetry_inside_tolerance_is_accepted(make_series: SeriesFactory) -> None:
    """Fronteira de 1e-12 (lado de dentro): resíduo medido ~5.0004e-13 -> aceita.

    As grades usuais fecham a soma em 0.0 exato em float64 e não exercitam a
    tolerância; este caso a exercita de verdade.
    """
    levels = (0.1, 0.5, 0.9 + 5e-13)
    residual = abs(levels[0] + levels[-1] - 1.0)
    assert 0.0 < residual < _SYMMETRY_BOUND  # premissa numérica do caso

    series = make_series([(0.0, 0.0, 0.0)], [0.0], levels=levels)

    assert series.symmetric_pairs == ((0.1, levels[-1]),)


@pytest.mark.unit
def test_asymmetry_just_outside_tolerance_raises(make_series: SeriesFactory) -> None:
    """Fronteira de 1e-12 (lado de fora): resíduo medido ~1.99996e-12 -> ergue."""
    levels = (0.1, 0.5, 0.9 + 2e-12)
    residual = abs(levels[0] + levels[-1] - 1.0)
    assert residual > _SYMMETRY_BOUND  # premissa numérica do caso

    with pytest.raises(ValueError, match="symmetric"):
        make_series([(0.0, 0.0, 0.0)], [0.0], levels=levels)


@pytest.mark.unit
def test_grid_without_symmetric_pair_raises(make_series: SeriesFactory) -> None:
    """C1: K = 1 {0.5} é simétrica mas não tem par — IS/PICP/nominal indefinidos."""
    with pytest.raises(ValueError, match="symmetric pair"):
        make_series([(0.0,)], [0.0], levels=(0.5,))


@pytest.mark.unit
def test_empty_grid_raises(make_series: SeriesFactory) -> None:
    """C1: grade vazia não tem par simétrico."""
    with pytest.raises(ValueError, match="symmetric pair"):
        make_series([()], [0.0], levels=(), direct=True)


@pytest.mark.unit
def test_decreasing_guardrail_values_raise(make_series: SeriesFactory) -> None:
    """C1: `QuantileForecast` construído direto com `guardrail_values` cruzado."""
    with pytest.raises(ValueError, match="point 0: guardrail values must be non-decreasing"):
        make_series([_CROSSED], [0.0], direct=True)


@pytest.mark.unit
def test_guardrail_values_misaligned_with_levels_raise(make_series: SeriesFactory) -> None:
    """C1 (alinhamento valor↔nível): VO direto com menos valores que níveis."""
    with pytest.raises(ValueError, match="6 guardrail values for 7 levels"):
        make_series([_GRID], [0.0], direct=True, guardrail_grids=[_GRID[:-1]])


@pytest.mark.unit
@pytest.mark.parametrize("horizon", [0, -1])
def test_horizon_below_one_raises(make_series: SeriesFactory, horizon: int) -> None:
    """C1: `horizon < 1`."""
    with pytest.raises(ValueError, match="horizon must be >= 1"):
        make_series([_GRID], [0.0], horizon=horizon)


# --- C2 — valor não-finito: ergue, nunca descarta --------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_value", [math.nan, math.inf, -math.inf, None], ids=["nan", "inf", "-inf", "none"]
)
def test_non_finite_guardrail_value_raises(
    make_series: SeriesFactory, bad_value: float | None
) -> None:
    """C2: o 4.3 preserva nan/inf/None com `guardrail_applied=False`; a série ergue."""
    grid = (*_GRID[:3], bad_value, *_GRID[4:])
    with pytest.raises(ValueError, match="point 1: guardrail values must all be finite"):
        make_series([_GRID, grid], [0.0, 0.0])


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_value", [math.nan, math.inf, -math.inf, None], ids=["nan", "inf", "-inf", "none"]
)
def test_non_finite_realized_raises(make_series: SeriesFactory, bad_value: float | None) -> None:
    """C2: `realized` não-finito ergue; a mensagem nomeia o índice do ponto."""
    with pytest.raises(ValueError, match="point 1: realized value must be finite"):
        make_series([_GRID, _GRID], [0.0, bad_value])
