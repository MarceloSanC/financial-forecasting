"""Unit test dos acessores tipados das células do gold (Stage 6.6 Task 01, F6, D9).

Política de tipo (concept 6.6 D9): `col_int` aceita `int` não-`bool`; `col_float` aceita
`int` não-`bool` ou `float` e devolve `float`; `col_bool` só `bool`; `col_str` só `str`;
`*_or_none` aceitam também `None`. Tipo fora da política → `GoldGenerationCorruptError`
nomeando tabela e coluna; coluna fora do schema → `KeyError` (regra do `col`).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GoldTableSchema,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGenerationCorruptError,
    Row,
    col,
    col_bool,
    col_float,
    col_float_or_none,
    col_int,
    col_int_or_none,
    col_str,
    col_str_or_none,
)

_SCHEMA = GoldTableSchema(name="gold_example", key=("k",), read_columns=("v",))


def _row(value: object) -> Row:
    return {"k": "key", "v": value, "outside": 1}


def test_col_reads_key_and_read_columns_only() -> None:
    row = _row("value")
    assert col(row, _SCHEMA, "k") == "key"
    assert col(row, _SCHEMA, "v") == "value"
    with pytest.raises(KeyError, match="'outside' is not a column of the gold_example schema"):
        col(row, _SCHEMA, "outside")


@pytest.mark.parametrize(
    ("accessor", "value", "expected"),
    [
        (col_int, 3, 3),
        (col_int, 0, 0),
        (col_float, 0.25, 0.25),
        (col_float, 2, 2.0),
        (col_bool, True, True),
        (col_bool, False, False),
        (col_str, "x", "x"),
        (col_int_or_none, None, None),
        (col_int_or_none, 4, 4),
        (col_float_or_none, None, None),
        (col_float_or_none, 1, 1.0),
        (col_str_or_none, None, None),
        (col_str_or_none, "y", "y"),
    ],
)
def test_accepted_values(
    accessor: Callable[[Row, GoldTableSchema, str], object], value: object, expected: object
) -> None:
    got = accessor(_row(value), _SCHEMA, "v")
    assert got == expected
    assert type(got) is type(expected)


def test_col_float_returns_a_float_for_an_int_cell() -> None:
    assert isinstance(col_float(_row(7), _SCHEMA, "v"), float)


@pytest.mark.parametrize(
    ("accessor", "value", "expected_name"),
    [
        (col_int, True, "int"),
        (col_int, 1.0, "int"),
        (col_int, "1", "int"),
        (col_int, None, "int"),
        (col_float, False, "float"),
        (col_float, "0.5", "float"),
        (col_float, None, "float"),
        (col_bool, 1, "bool"),
        (col_bool, "true", "bool"),
        (col_bool, None, "bool"),
        (col_str, 1, "str"),
        (col_str, None, "str"),
        (col_int_or_none, True, "int"),
        (col_float_or_none, "x", "float"),
        (col_str_or_none, 2, "str"),
    ],
)
def test_refused_values_name_table_and_column(
    accessor: Callable[[Row, GoldTableSchema, str], object], value: object, expected_name: str
) -> None:
    with pytest.raises(
        GoldGenerationCorruptError, match=rf"gold_example\.v: expected {expected_name}"
    ):
        accessor(_row(value), _SCHEMA, "v")


@pytest.mark.parametrize("accessor", [col_int, col_float, col_bool, col_str, col_int_or_none])
def test_typed_accessors_keep_the_schema_rule(
    accessor: Callable[[Row, GoldTableSchema, str], object],
) -> None:
    with pytest.raises(KeyError):
        accessor(_row(1), _SCHEMA, "outside")
