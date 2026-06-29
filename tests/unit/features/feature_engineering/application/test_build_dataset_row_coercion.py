"""Testes das coerções de fronteira do `BuildDataset` (bronze row → entidade).

Cobre os validadores defensivos do boundary do use case (concept 3.5 §6 DQ): mapeiam
linhas da bronze (`Mapping[str, object]`) para `Candle`/`FundamentalReport`, rejeitando
tipos inesperados. São branches de erro que uma mutação ("retornar default", "pular o
raise") silenciaria — por isso exercitados em isolamento (mutation guard, audit Q3).

Adicionados na AUDITORIA DE TESTES da Stage 3.5 (gaps de cobertura dos branches de
coerção 227/259-261/267/270-272/278/285).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from financial_forecasting.features.feature_engineering.application.use_cases import (
    build_dataset as bd,
)


def test_row_to_candle_rejects_non_datetime_timestamp() -> None:
    """`timestamp` não-datetime na bronze candle levanta `ValueError` (linha 227)."""
    row = {
        "asset": "AAPL",
        "timestamp": "2024-01-01",  # str, não datetime
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": 1.5,
        "volume": 1000.0,
    }
    with pytest.raises(ValueError, match="'timestamp' must be a datetime"):
        bd._row_to_candle(row)


def test_as_date_accepts_datetime_and_date_and_rejects_other() -> None:
    """`_as_date`: datetime→date, date→date, outro→`ValueError` (259-261)."""
    assert bd._as_date(datetime(2024, 1, 2, 9, tzinfo=UTC)) == date(2024, 1, 2)
    assert bd._as_date(date(2024, 1, 3)) == date(2024, 1, 3)
    with pytest.raises(ValueError, match="expected a date, got str"):
        bd._as_date("2024-01-01")


def test_as_optional_date_branches() -> None:
    """`_as_optional_date`: None→None, datetime→date, date→date, outro→None (267/270-272)."""
    assert bd._as_optional_date(None) is None
    assert bd._as_optional_date(datetime(2024, 1, 2, tzinfo=UTC)) == date(2024, 1, 2)
    assert bd._as_optional_date(date(2024, 1, 4)) == date(2024, 1, 4)
    assert bd._as_optional_date(123) is None  # tipo inesperado → None (fallback)


def test_as_float_rejects_bool_and_non_numeric() -> None:
    """`_as_float`: bool e tipos não-numéricos levantam `ValueError` (linha 278)."""
    assert bd._as_float(3) == 3.0  # noqa: PLR2004
    assert bd._as_float("2.5") == 2.5  # noqa: PLR2004
    with pytest.raises(ValueError, match="expected a numeric value, got bool"):
        bd._as_float(True)
    with pytest.raises(ValueError, match="expected a numeric value, got list"):
        bd._as_float([1.0])


def test_as_optional_float_returns_none_for_bool_and_non_numeric() -> None:
    """`_as_optional_float`: None/bool/não-numérico → None; numérico → float (linha 285)."""
    assert bd._as_optional_float(None) is None
    assert bd._as_optional_float(True) is None  # bool tratado como ausente
    assert bd._as_optional_float("x") is None
    assert bd._as_optional_float(4) == 4.0  # noqa: PLR2004
