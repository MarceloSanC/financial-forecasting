"""Testes unitários do value object `SilverContentHash` (Stage 8.1, A1 / I6 / I7).

Contra o `CanonicalJsonHasher` real (puro, sem I/O; precedente
`test_preregistration_hash.py`): o hasher sozinho arredonda floats a 10 casas, o VO
codifica cada float exatamente e canoniza cada valor pelo tipo declarado da coluna.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping
from typing import cast

import numpy as np
import pytest

from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.silver_content_hash import (
    KIND_BOOL,
    KIND_FLOAT,
    KIND_INT,
    KIND_STR,
    SilverContentHash,
)

_COLUMNS: dict[str, tuple[str, bool]] = {
    "run_id": (KIND_STR, False),
    "year": (KIND_INT, False),
    "seed": (KIND_INT, True),
    "quantile": (KIND_FLOAT, False),
    "flag": (KIND_BOOL, False),
}
_ROW_A: dict[str, object] = {
    "run_id": "r1",
    "year": 2020,
    "seed": 7,
    "quantile": 0.125,
    "flag": True,
}
_ROW_B: dict[str, object] = {
    "run_id": "r2",
    "year": 2021,
    "seed": None,
    "quantile": -0.5,
    "flag": False,
}
_SMALL = 1e-4  # A1: |x| < 1e-4, faixa em que o arredondamento a 10 casas colide float32
_GOLDEN = "7038a8934168c0501ce8fa1b6e1925dbfff60161b27ea85ad95597f896f4c9ac"


def _unit(
    rows: list[Mapping[str, object]],
    *,
    columns: Mapping[str, tuple[str, bool]] = _COLUMNS,
    table: str = "fact_oos_predictions",
) -> SilverContentHash:
    return SilverContentHash.of_unit(
        hasher=CanonicalJsonHasher(), table=table, columns=columns, rows=rows
    )


def _float32_neighbours() -> tuple[float, float]:
    bits = struct.unpack("<I", struct.pack("<f", 5e-5))[0]
    low = struct.unpack("<f", struct.pack("<I", bits))[0]
    high = struct.unpack("<f", struct.pack("<I", bits + 1))[0]
    return low, high


@pytest.mark.unit
def test_golden_value_for_small_payload() -> None:
    assert _unit([_ROW_A, _ROW_B]).value == _GOLDEN


@pytest.mark.unit
def test_invariant_to_row_order() -> None:
    assert _unit([_ROW_A, _ROW_B]) == _unit([_ROW_B, _ROW_A])


@pytest.mark.unit
def test_invariant_to_column_order() -> None:
    reversed_row = dict(reversed(list(_ROW_A.items())))
    reversed_columns = dict(reversed(list(_COLUMNS.items())))

    assert _unit([_ROW_A]) == _unit([reversed_row], columns=reversed_columns)


@pytest.mark.unit
def test_neighbour_float32_values_hash_differently() -> None:
    low, high = _float32_neighbours()
    assert low != high
    assert abs(low) < _SMALL
    assert abs(high) < _SMALL
    # O arredondamento do hasher sozinho os colide: prova de que o teste discrimina.
    assert round(low, 10) == round(high, 10)

    assert _unit([{**_ROW_A, "quantile": low}]) != _unit([{**_ROW_A, "quantile": high}])


@pytest.mark.unit
def test_int_column_accepts_integral_float() -> None:
    assert _unit([{**_ROW_A, "seed": 3}]) == _unit([{**_ROW_A, "seed": 3.0}])


@pytest.mark.unit
def test_int_column_rejects_fractional_float() -> None:
    with pytest.raises(ValueError, match=r"fact_oos_predictions\.seed"):
        _unit([{**_ROW_A, "seed": 3.5}])


@pytest.mark.unit
def test_none_in_non_nullable_column_raises() -> None:
    with pytest.raises(ValueError, match=r"fact_oos_predictions\.quantile: None"):
        _unit([{**_ROW_A, "quantile": None}])


@pytest.mark.unit
def test_none_in_nullable_column_accepted() -> None:
    assert _unit([{**_ROW_A, "seed": None}]) != _unit([_ROW_A])


@pytest.mark.unit
def test_undeclared_column_raises() -> None:
    with pytest.raises(ValueError, match=r"fact_oos_predictions\.extra: column not declared"):
        _unit([{**_ROW_A, "extra": 1}])


@pytest.mark.unit
def test_absent_column_and_null_hash_differently() -> None:
    without_seed = {key: value for key, value in _ROW_A.items() if key != "seed"}

    assert _unit([without_seed]) != _unit([{**_ROW_A, "seed": None}])


@pytest.mark.unit
def test_str_preserved() -> None:
    as_str: dict[str, tuple[str, bool]] = {"label": (KIND_STR, False)}
    as_int: dict[str, tuple[str, bool]] = {"label": (KIND_INT, False)}

    # Mesma tabela, mesma coluna: só o tipo declarado difere, e "1" nunca vira 1.
    assert _unit([{"label": "1"}], columns=as_str) != _unit([{"label": 1}], columns=as_int)
    assert _unit([{"label": "1"}], columns=as_str) != _unit([{"label": "01"}], columns=as_str)
    with pytest.raises(ValueError, match=r"int in a str column"):
        _unit([{"label": 1}], columns=as_str)
    with pytest.raises(ValueError, match=r"str in a int column"):
        _unit([{"label": "1"}], columns=as_int)


@pytest.mark.unit
def test_float_column_accepts_integral_int() -> None:
    assert _unit([{**_ROW_A, "quantile": 1}]) == _unit([{**_ROW_A, "quantile": 1.0}])


@pytest.mark.unit
def test_created_at_utc_does_not_change_hash() -> None:
    early = {**_ROW_A, "created_at_utc": "2026-01-01T00:00:00+00:00"}
    late = {**_ROW_A, "created_at_utc": "2026-10-22T12:00:00+00:00"}

    # Não declarada nas colunas: sai antes da checagem de coluna declarada.
    assert _unit([early]) == _unit([late]) == _unit([_ROW_A])
    # Declarada (como no schema real e no fake do `dim_run`): continua fora do hash.
    declared = {**_COLUMNS, "created_at_utc": (KIND_STR, False)}
    assert _unit([early], columns=declared) == _unit([late], columns=declared)
    assert _unit([early], columns=declared) == _unit([_ROW_A])


@pytest.mark.unit
def test_non_finite_floats_encoded_as_distinct_tokens() -> None:
    values = [float("inf"), float("-inf"), float("nan"), 0.0, 1.0, -1.0, 1e308]

    digests = {_unit([{**_ROW_A, "quantile": value}]) for value in values}

    assert len(digests) == len(values)


@pytest.mark.unit
def test_numpy_scalars_normalized() -> None:
    native = _unit([_ROW_A])
    numpy_row = {
        **_ROW_A,
        "year": np.int64(2020),
        "seed": np.float64(7.0),
        "quantile": np.float64(0.125),
    }

    assert _unit([numpy_row]) == native
    assert _unit([{**_ROW_A, "quantile": np.float32(0.125)}]) == native


@pytest.mark.unit
def test_combine_depends_on_keys_and_digests() -> None:
    hasher = CanonicalJsonHasher()
    first = _unit([_ROW_A])
    second = _unit([_ROW_B])

    base = SilverContentHash.combine(hasher=hasher, digests={"a": first, "b": second})

    assert base == SilverContentHash.combine(hasher=hasher, digests={"b": second, "a": first})
    assert base != SilverContentHash.combine(hasher=hasher, digests={"a": first, "c": second})
    assert base != SilverContentHash.combine(hasher=hasher, digests={"a": second, "b": first})


@pytest.mark.unit
@pytest.mark.parametrize("value", ["abc", "A" * 64, "0" * 63, 123])
def test_raw_constructor_validates_sha256_hex(value: object) -> None:
    with pytest.raises(ValueError, match=r"SilverContentHash\.value"):
        SilverContentHash(value=cast("str", value))  # entrada inválida de propósito
    assert SilverContentHash(value="0" * 64).value == "0" * 64
