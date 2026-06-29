"""Testes unitários da entity `FundamentalReport` (concept 2.3 §5 I2, A2).

Cobre um `FundamentalReport` válido (com e SEM `reported_date`) + uma violação por
invariante (`fiscal_date_end` com hora, `report_type` fora do conjunto, numérico
não-float, `reported_date` `datetime`, `asset_id` vazio) → `ValueError`/`TypeError`.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from financial_forecasting.features.market_data.domain.entities.fundamental_report import (
    FundamentalReport,
)

_FISCAL = date(2024, 9, 30)
_REPORTED = date(2024, 11, 1)


def _valid(**overrides: object) -> FundamentalReport:
    """Constrói um `FundamentalReport` válido canônico, com overrides pontuais."""
    kwargs: dict[str, object] = {
        "asset_id": "AAPL",
        "report_type": "annual",
        "fiscal_date_end": _FISCAL,
        "reported_date": _REPORTED,
        "revenue": 391_035_000_000.0,
        "net_income": 93_736_000_000.0,
        "operating_cash_flow": 118_254_000_000.0,
        "total_shareholder_equity": 56_950_000_000.0,
        "total_liabilities": 308_030_000_000.0,
        "source": "alpha_vantage",
    }
    kwargs.update(overrides)
    return FundamentalReport(**kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
def test_valid_with_reported_date() -> None:
    """Um `FundamentalReport` canônico com `reported_date` constrói sem erro."""
    report = _valid()

    assert report.asset_id == "AAPL"
    assert report.report_type == "annual"
    assert report.fiscal_date_end == _FISCAL
    assert report.reported_date == _REPORTED
    assert report.revenue == pytest.approx(391_035_000_000.0)
    assert report.source == "alpha_vantage"


@pytest.mark.unit
def test_valid_without_reported_date() -> None:
    """`reported_date=None` é válido (os 17/81 `NaT` reais do parquet)."""
    report = _valid(reported_date=None)
    assert report.reported_date is None


@pytest.mark.unit
def test_valid_with_none_numeric_fields() -> None:
    """Os cinco numéricos podem ser `None` (endpoint parcial, schema nullable)."""
    report = _valid(
        revenue=None,
        net_income=None,
        operating_cash_flow=None,
        total_shareholder_equity=None,
        total_liabilities=None,
    )
    assert report.revenue is None
    assert report.total_liabilities is None


@pytest.mark.unit
def test_quarterly_report_type_is_valid() -> None:
    """`report_type='quarterly'` é aceito."""
    assert _valid(report_type="quarterly").report_type == "quarterly"


@pytest.mark.unit
def test_int_numeric_is_accepted_as_float() -> None:
    """`int` é aceito nos numéricos (espelha o old `isinstance(v, (int, float))`)."""
    int_revenue = 100
    report = _valid(revenue=int_revenue)
    assert report.revenue == int_revenue


@pytest.mark.unit
def test_is_frozen() -> None:
    """A entity é imutável (frozen)."""
    report = _valid()
    with pytest.raises(AttributeError):
        report.asset_id = "MSFT"  # type: ignore[misc]


@pytest.mark.unit
def test_empty_asset_id_raises() -> None:
    """`asset_id` vazio → `ValueError`."""
    with pytest.raises(ValueError, match="asset_id must be a non-empty string"):
        _valid(asset_id="  ")


@pytest.mark.unit
def test_empty_source_raises() -> None:
    """`source` vazia → `ValueError`."""
    with pytest.raises(ValueError, match="source must be a non-empty string"):
        _valid(source="")


@pytest.mark.unit
def test_fiscal_date_end_with_time_raises() -> None:
    """`fiscal_date_end` como `datetime` (com hora) → `TypeError`."""
    with pytest.raises(TypeError, match="fiscal_date_end must be a date without time"):
        _valid(fiscal_date_end=datetime(2024, 9, 30, 12, 0))


@pytest.mark.unit
def test_fiscal_date_end_non_date_raises() -> None:
    """`fiscal_date_end` que não é `date` → `TypeError`."""
    with pytest.raises(TypeError, match="fiscal_date_end must be a date instance"):
        _valid(fiscal_date_end="2024-09-30")


@pytest.mark.unit
def test_report_type_out_of_set_raises() -> None:
    """`report_type` fora de `{annual, quarterly}` → `ValueError`."""
    with pytest.raises(ValueError, match="report_type must be"):
        _valid(report_type="ttm")


@pytest.mark.unit
def test_non_numeric_field_raises() -> None:
    """Numérico não-float (string) → `TypeError`."""
    with pytest.raises(TypeError, match="revenue must be numeric"):
        _valid(revenue="lots")


@pytest.mark.unit
def test_bool_numeric_field_raises() -> None:
    """`bool` nos numéricos → `TypeError` (endurecimento vs old)."""
    with pytest.raises(TypeError, match="net_income must be numeric"):
        _valid(net_income=True)


@pytest.mark.unit
def test_reported_date_with_time_raises() -> None:
    """`reported_date` como `datetime` → `TypeError`."""
    with pytest.raises(TypeError, match="reported_date must be a date without time"):
        _valid(reported_date=datetime(2024, 11, 1, 9, 30))


@pytest.mark.unit
def test_reported_date_non_date_raises() -> None:
    """`reported_date` que não é `date` → `TypeError`."""
    with pytest.raises(TypeError, match="reported_date must be a date instance"):
        _valid(reported_date="2024-11-01")
