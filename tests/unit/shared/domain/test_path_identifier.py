"""Testes da regra única de identificador de caminho (Stage 6.4 Task 02; C3).

`validate_path_identifier` é o dono do padrão `^[A-Za-z0-9._-]+$` consumido pelo
`ParquetMedallionStore`, pelo `FakeMedallionStore` e pelo `GoldPartition` (6.4).
"""

from __future__ import annotations

import re

import pytest

from financial_forecasting.shared.domain.services.path_identifier import (
    PATH_IDENTIFIER_PATTERN,
    validate_path_identifier,
)


@pytest.mark.unit
@pytest.mark.parametrize("value", ["AAPL", "sweep-01.a_b", "a", "2024.Q1-x_y"])
def test_identifier_accepts(value: str) -> None:
    assert validate_path_identifier(value, field="asset") is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [
        pytest.param("", id="empty"),
        pytest.param("a/b", id="slash"),
        pytest.param("a\\b", id="backslash"),
        pytest.param("a b", id="space"),
        pytest.param("AAPL\n", id="trailing-newline-asset"),
        pytest.param("a\n", id="trailing-newline"),
        pytest.param("\nAAPL", id="leading-newline"),
        pytest.param("ç", id="non-ascii"),
        pytest.param("a*b", id="glob-star"),
        pytest.param(None, id="none"),
        pytest.param(3, id="int"),
        pytest.param(b"AAPL", id="bytes"),
    ],
)
def test_identifier_rejects(value: object) -> None:
    with pytest.raises(ValueError, match="must match"):
        validate_path_identifier(value, field="asset")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "field"),
    [
        pytest.param("a/b", "parent_sweep_id", id="str"),
        pytest.param(None, "read-only pair ('processed', 'dataset_tft') asset filter", id="none"),
    ],
)
def test_identifier_message_names_field(value: object, field: str) -> None:
    expected = f"{field} must match {PATH_IDENTIFIER_PATTERN.pattern!r}; got {value!r}"
    with pytest.raises(ValueError, match=re.escape(expected)):
        validate_path_identifier(value, field=field)
