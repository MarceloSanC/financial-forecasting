"""Unit test do VO `BootstrapIndices` e dos validadores do `McsBackend` (C6, C9; ADR 6.2.0004).

Um caso por ramo de `validate_bootstrap_request` e de `validate_block_length_request`
(o mínimo de 11 pontos é medido — technical 6.2 §1 item 4 e §7 Task 06) e da construção
do VO. Índices montados à mão; nenhum gerador de biblioteca.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    MIN_BLOCK_LENGTH_OBS,
    BootstrapIndices,
    BootstrapScheme,
    validate_block_length_request,
    validate_bootstrap_request,
)

_STATIONARY = BootstrapScheme.STATIONARY
_MOVING = BootstrapScheme.MOVING_BLOCK
_VALID_REQUEST: dict[str, object] = {
    "n_obs": 5,
    "block_size": 2,
    "reps": 3,
    "seed": 7,
    "scheme": _STATIONARY,
}
_ROWS = ((0, 1, 2, 3, 4), (4, 0, 1, 1, 2), (3, 3, 3, 3, 3))


def _request(**overrides: object) -> None:
    fields = dict(_VALID_REQUEST)
    fields.update(overrides)
    validate_bootstrap_request(**fields)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        pytest.param({"n_obs": 1}, "n_obs must be", id="n-obs-one"),
        pytest.param({"n_obs": True}, "n_obs must be", id="n-obs-bool"),
        pytest.param({"n_obs": 2.0}, "n_obs must be", id="n-obs-float"),
        pytest.param({"block_size": 0}, "block_size must be", id="block-zero"),
        pytest.param({"block_size": True}, "block_size must be", id="block-bool"),
        pytest.param({"reps": 0}, "reps must be", id="reps-zero"),
        pytest.param({"reps": 1.0}, "reps must be", id="reps-float"),
        pytest.param({"seed": True}, "seed must be", id="seed-bool"),
        pytest.param({"seed": 1.0}, "seed must be", id="seed-float"),
        pytest.param({"seed": None}, "seed must be", id="seed-none"),
        pytest.param({"seed": -1}, "seed must be", id="seed-negative"),
        pytest.param({"scheme": "stationary"}, "BootstrapScheme", id="scheme-raw-str"),
        pytest.param({"scheme": _MOVING, "block_size": 5}, "block_size < n_obs", id="mb-equal"),
        pytest.param({"scheme": _MOVING, "block_size": 6}, "block_size < n_obs", id="mb-above"),
    ],
)
def test_bootstrap_request_invalid_raises(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _request(**overrides)


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({}, id="baseline"),
        pytest.param({"scheme": _MOVING, "block_size": 4}, id="mb-n-obs-minus-one"),
        pytest.param({"scheme": _STATIONARY, "block_size": 50}, id="stationary-block-above-n"),
        pytest.param({"n_obs": 2, "block_size": 1, "reps": 1, "seed": 0}, id="minimums"),
    ],
)
def test_bootstrap_request_accepts(overrides: dict[str, object]) -> None:
    _request(**overrides)


def _varying(size: int) -> list[float]:
    return [float(index % 3) for index in range(size)]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("series", "message"),
    [
        pytest.param(_varying(MIN_BLOCK_LENGTH_OBS - 1), "at least 11", id="ten-points"),
        pytest.param([*_varying(12), math.nan], r"series\[12\]", id="nan"),
        pytest.param([*_varying(12), math.inf], r"series\[12\]", id="inf"),
        pytest.param([*_varying(12), None], r"series\[12\]", id="none"),
        pytest.param([*_varying(12), True], r"series\[12\]", id="bool"),
    ],
)
def test_block_length_request_invalid_raises(series: list[object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_block_length_request(series)  # type: ignore[arg-type]


@pytest.mark.unit
def test_block_length_min_length_is_eleven() -> None:
    assert MIN_BLOCK_LENGTH_OBS == 11  # noqa: PLR2004 — o mínimo medido (A14.3)
    validate_block_length_request(_varying(MIN_BLOCK_LENGTH_OBS))
    with pytest.raises(ValueError, match="at least 11"):
        validate_block_length_request(_varying(MIN_BLOCK_LENGTH_OBS - 1))


@pytest.mark.unit
@pytest.mark.parametrize("value", [0.0, 0.3, -2.5])
def test_block_length_constant_series_raises(value: float) -> None:
    with pytest.raises(ValueError, match="non-constant"):
        validate_block_length_request([value] * 20)


def _indices(**overrides: object) -> BootstrapIndices:
    fields: dict[str, object] = {
        "scheme": _STATIONARY,
        "block_size": 2,
        "seed": 7,
        "n_obs": 5,
        "generator": "manual (teste)",
        "indices": _ROWS,
    }
    fields.update(overrides)
    return BootstrapIndices(**fields)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        pytest.param({"indices": ((0, 1, 2, 3),)}, "4 indices for n_obs=5", id="row-short"),
        pytest.param({"indices": ((),)}, "row 0: 0 indices for n_obs=5", id="row-empty"),
        pytest.param({"indices": ((0, 1, 2, 3, 4, 0),)}, "6 indices", id="row-long"),
        pytest.param({"indices": ((0, 1, -1, 3, 4),)}, "outside", id="index-negative"),
        pytest.param({"indices": ((0, 1, 5, 3, 4),)}, "outside", id="index-n-obs"),
        pytest.param({"indices": ((0, True, 2, 3, 4),)}, "not an int", id="index-bool"),
        pytest.param({"indices": ((0, 1.0, 2, 3, 4),)}, "not an int", id="index-float"),
        pytest.param({"generator": ""}, "generator", id="generator-empty"),
        pytest.param({"generator": None}, "generator", id="generator-none"),
        pytest.param({"indices": ()}, "reps must be", id="no-rows"),
        pytest.param({"seed": -3}, "seed must be", id="request-invalid"),
        pytest.param(
            {"scheme": _MOVING, "block_size": 5}, "block_size < n_obs", id="mb-block-n-obs"
        ),
    ],
)
def test_indices_invalid_row_or_request_raises(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _indices(**overrides)


@pytest.mark.unit
def test_indices_valid_reps() -> None:
    indices = _indices()
    assert indices.reps == len(_ROWS)
    assert indices.indices == _ROWS
    assert (indices.scheme, indices.block_size, indices.seed, indices.n_obs) == (
        _STATIONARY,
        2,
        7,
        5,
    )


@pytest.mark.unit
def test_indices_frozen() -> None:
    indices = _indices()
    with pytest.raises(dataclasses.FrozenInstanceError):
        indices.seed = 8  # type: ignore[misc]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("indices", "message"),
    [
        pytest.param(list(_ROWS), "indices must be a tuple", id="outer-list"),
        pytest.param((_ROWS[0], list(_ROWS[1]), _ROWS[2]), "row 1 must be a tuple", id="row-list"),
    ],
)
def test_indices_mutable_container_rejected(indices: object, message: str) -> None:
    """Lista validada poderia ser mutada depois (ex.: índice 99 com n_obs = 5)."""
    with pytest.raises(ValueError, match=message):
        _indices(indices=indices)
