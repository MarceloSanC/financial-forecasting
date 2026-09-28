"""Unit test do validador único de entrada dos kernels (C7; ADR `6_1_0001` item 1).

Um teste por ramo de cada função: o mesmo validador é chamado pelos kernels do
domínio, pelo fake e pelos adapters, então um ramo sem teste é um ramo em que
domínio e oráculo poderiam divergir sem ninguém ver.
"""

from __future__ import annotations

import math

import pytest

from financial_forecasting.features.evaluation.domain.services.scoring_input_validation import (
    validate_crps_inputs,
    validate_grid_row,
    validate_interval_bounds,
    validate_interval_inputs,
    validate_level,
    validate_miscoverage,
    validate_pinball_inputs,
)

_OUT_OF_UNIT = [0.0, 1.0, -0.1, 1.5, math.nan]
_OUT_OF_UNIT_IDS = ["zero", "one", "negative", "above-one", "nan"]


@pytest.mark.unit
@pytest.mark.parametrize("level", _OUT_OF_UNIT, ids=_OUT_OF_UNIT_IDS)
def test_validate_level_rejects_outside_open_unit_interval(level: float) -> None:
    with pytest.raises(ValueError, match=r"level must be in \(0, 1\)"):
        validate_level(level)


@pytest.mark.unit
def test_validate_level_accepts_inner_level() -> None:
    validate_level(0.05)


@pytest.mark.unit
@pytest.mark.parametrize("miscoverage", _OUT_OF_UNIT, ids=_OUT_OF_UNIT_IDS)
def test_validate_miscoverage_rejects_outside_open_unit_interval(miscoverage: float) -> None:
    with pytest.raises(ValueError, match=r"miscoverage must be in \(0, 1\)"):
        validate_miscoverage(miscoverage)


@pytest.mark.unit
def test_validate_miscoverage_accepts_inner_value() -> None:
    validate_miscoverage(0.1)


@pytest.mark.unit
def test_validate_grid_row_rejects_misaligned_sizes() -> None:
    with pytest.raises(ValueError, match="must align"):
        validate_grid_row([0.0, 1.0], [0.1, 0.5, 0.9])


@pytest.mark.unit
def test_validate_grid_row_rejects_empty_grid() -> None:
    with pytest.raises(ValueError, match="at least one level"):
        validate_grid_row([], [])


@pytest.mark.unit
def test_validate_grid_row_rejects_level_outside_unit_interval() -> None:
    with pytest.raises(ValueError, match=r"level must be in \(0, 1\)"):
        validate_grid_row([0.0, 1.0], [0.5, 1.0])


@pytest.mark.unit
def test_validate_interval_bounds_rejects_lower_above_upper() -> None:
    with pytest.raises(ValueError, match="must not exceed upper"):
        validate_interval_bounds(0.2, 0.1)


@pytest.mark.unit
def test_validate_interval_bounds_accepts_degenerate_interval() -> None:
    """`lower == upper` é intervalo de largura 0 — válido (caso do Dirac)."""
    validate_interval_bounds(0.1, 0.1)


@pytest.mark.unit
def test_validate_pinball_inputs_rejects_bad_level() -> None:
    with pytest.raises(ValueError, match="level must be"):
        validate_pinball_inputs([1.0], [1.0], 1.5)


@pytest.mark.unit
def test_validate_pinball_inputs_rejects_empty_sequence() -> None:
    with pytest.raises(ValueError, match="empty sequence"):
        validate_pinball_inputs([], [], 0.5)


@pytest.mark.unit
def test_validate_pinball_inputs_rejects_different_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        validate_pinball_inputs([1.0, 2.0], [1.0], 0.5)


@pytest.mark.unit
def test_validate_crps_inputs_rejects_empty_sequence() -> None:
    with pytest.raises(ValueError, match="empty sequence"):
        validate_crps_inputs([], [], [0.25, 0.75])


@pytest.mark.unit
def test_validate_crps_inputs_rejects_different_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        validate_crps_inputs([1.0, 2.0], [[0.0, 1.0]], [0.25, 0.75])


@pytest.mark.unit
def test_validate_crps_inputs_rejects_bad_row() -> None:
    with pytest.raises(ValueError, match="must align"):
        validate_crps_inputs([1.0], [[0.0, 1.0, 2.0]], [0.25, 0.75])


@pytest.mark.unit
def test_validate_crps_inputs_rejects_bad_level() -> None:
    with pytest.raises(ValueError, match="level must be"):
        validate_crps_inputs([1.0], [[0.0, 1.0]], [0.0, 0.75])


@pytest.mark.unit
def test_validate_interval_inputs_rejects_bad_miscoverage() -> None:
    with pytest.raises(ValueError, match="miscoverage must be"):
        validate_interval_inputs([1.0], [0.0], [2.0], 0.0)


@pytest.mark.unit
def test_validate_interval_inputs_rejects_empty_sequence() -> None:
    with pytest.raises(ValueError, match="empty sequence"):
        validate_interval_inputs([], [], [], 0.1)


@pytest.mark.unit
def test_validate_interval_inputs_rejects_different_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        validate_interval_inputs([1.0], [0.0, 0.0], [2.0], 0.1)


@pytest.mark.unit
def test_validate_interval_inputs_rejects_crossed_bounds() -> None:
    with pytest.raises(ValueError, match="must not exceed upper"):
        validate_interval_inputs([1.0, 1.0], [0.0, 3.0], [2.0, 2.0], 0.1)


@pytest.mark.unit
def test_validators_accept_well_formed_series() -> None:
    """Caminho feliz: nenhuma das três validações de série ergue."""
    validate_pinball_inputs([1.0, 2.0], [0.5, 2.5], 0.5)
    validate_crps_inputs([1.0, 2.0], [[0.0, 1.0], [1.0, 3.0]], [0.25, 0.75])
    validate_interval_inputs([1.0, 2.0], [0.0, 1.0], [2.0, 3.0], 0.5)
