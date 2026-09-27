"""Unit test de `build_training_grid` — grid único de treino (Stage 5.5, A1 / D11).

Prova: em dataset sem valor ausente, reproduz o que as 4 leituras antigas
entregavam (ordem cronológica, timestamps ISO, sessões, `target_return`, matriz
na ordem pedida — caracterização da Task 04); com aquecimento, corta o prefixo
comum a todas as colunas; erros de coluna ausente (C6), tipo inválido, timestamp
sem fuso, timestamp repetido e dataset vazio.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime

import pytest

from financial_forecasting.features.modeling.domain.exceptions.cohort import (
    InteriorMissingValuesError,
    NoUsableRowsError,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    build_training_grid,
)

_COLUMNS = ("f_a", "f_b", "target_return")


def _row(day: int, target: float | None, f_a: float | None, f_b: float | None) -> dict[str, object]:
    return {
        "timestamp": datetime(2024, 1, day, tzinfo=UTC),
        "asset_id": "AAPL",
        "target_return": target,
        "f_a": f_a,
        "f_b": f_b,
        "unused_column": "ignored",
    }


def test_without_missing_values_matches_the_old_readers() -> None:
    rows = [_row(4, 0.03, 3.0, 30.0), _row(2, 0.01, 1.0, 10.0), _row(3, 0.02, 2.0, 20.0)]

    grid = build_training_grid(rows, columns=_COLUMNS)

    assert grid.trimmed_prefix == 0
    assert grid.timestamps_iso() == (
        "2024-01-02T00:00:00+00:00",
        "2024-01-03T00:00:00+00:00",
        "2024-01-04T00:00:00+00:00",
    )
    assert grid.sessions() == (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))
    assert grid.column("target_return") == (0.01, 0.02, 0.03)
    assert grid.matrix(("f_b", "f_a")) == ((10.0, 1.0), (20.0, 2.0), (30.0, 3.0))


def test_warm_up_prefix_is_trimmed_for_every_column() -> None:
    rows = [
        _row(2, 0.01, None, math.nan),
        _row(3, 0.02, 2.0, math.nan),
        _row(4, 0.03, 3.0, 30.0),
        _row(5, 0.04, 4.0, 40.0),
    ]

    grid = build_training_grid(rows, columns=_COLUMNS)

    expected_prefix = 2
    assert grid.trimmed_prefix == expected_prefix
    assert grid.sessions() == (date(2024, 1, 4), date(2024, 1, 5))
    assert grid.column("target_return") == (0.03, 0.04)
    assert grid.matrix(("f_a", "f_b")) == ((3.0, 30.0), (4.0, 40.0))


def test_missing_target_in_prefix_is_trimmed() -> None:
    rows = [_row(2, None, 1.0, 10.0), _row(3, 0.02, 2.0, 20.0)]

    grid = build_training_grid(rows, columns=_COLUMNS)

    assert grid.column("target_return") == (0.02,)


def test_interior_missing_value_raises() -> None:
    rows = [_row(2, 0.01, 1.0, 10.0), _row(3, 0.02, None, 20.0), _row(4, 0.03, 3.0, 30.0)]

    with pytest.raises(InteriorMissingValuesError) as excinfo:
        build_training_grid(rows, columns=_COLUMNS)

    assert excinfo.value.counts == {"f_a": 1}


def test_missing_column_raises_c6_naming_it() -> None:
    with pytest.raises(ValueError, match="C6") as excinfo:
        build_training_grid([_row(2, 0.01, 1.0, 10.0)], columns=("f_a", "f_missing"))

    assert "f_missing" in str(excinfo.value)


def test_non_numeric_value_raises() -> None:
    rows = [{**_row(2, 0.01, 1.0, 10.0), "f_a": "1.0"}]

    with pytest.raises(ValueError, match="'f_a' must be numeric"):
        build_training_grid(rows, columns=_COLUMNS)


def test_naive_timestamp_raises() -> None:
    rows = [{**_row(2, 0.01, 1.0, 10.0), "timestamp": datetime(2024, 1, 2)}]

    with pytest.raises(ValueError, match="tz-aware"):
        build_training_grid(rows, columns=_COLUMNS)


def test_repeated_timestamp_raises() -> None:
    rows = [_row(2, 0.01, 1.0, 10.0), _row(2, 0.02, 2.0, 20.0)]

    with pytest.raises(ValueError, match="repeated timestamps"):
        build_training_grid(rows, columns=_COLUMNS)


def test_empty_dataset_raises() -> None:
    with pytest.raises(NoUsableRowsError):
        build_training_grid([], columns=_COLUMNS)


def test_matrix_without_columns_keeps_one_empty_row_per_timestamp() -> None:
    grid = build_training_grid([_row(2, 0.01, 1.0, 10.0)], columns=("target_return",))

    assert grid.matrix(()) == ((),)
