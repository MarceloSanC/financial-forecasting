"""Unit do `AsofJoinDuckdbAdapter` — caminhos específicos do adapter DuckDB.

Cobre os ramos de coerção/erro do adapter que o contract test (forma compartilhada)
não exercita, mantendo o adapter ≥90% (concept 3.3 A10):

- campos fundamentais `None`/não-numéricos no report → propagam `None` na saída e
  ratios `None` (divisão segura a jusante);
- `effective_date` não-`date` no report → `TypeError` (coerção defensiva da fronteira).

Não duplica as assertivas de semântica backward (essas vivem no contract test
parametrizado fake↔real, `test_asof_join_contract.py`).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pytest

from financial_forecasting.features.feature_engineering.adapters.out.duckdb.asof_join_adapter import (  # noqa: E501
    AsofJoinDuckdbAdapter,
)

Row = Mapping[str, object]

_GRID = [date(2024, 1, 10), date(2024, 1, 20)]


@pytest.mark.unit
def test_none_fundamentals_propagate_and_ratios_none() -> None:
    """Campos fundamentais `None` no report → `None` na saída e ratios `None`."""
    report: dict[str, object] = {
        "effective_date": date(2024, 1, 5),
        "revenue": None,
        "net_income": None,
        "operating_cash_flow": None,
        "total_shareholder_equity": None,
        "total_liabilities": None,
    }
    rows = list(AsofJoinDuckdbAdapter().asof_join_backward(grid_days=_GRID, reports=[report]))
    matched = rows[0]
    assert matched["fundamentals_effective_date"] == date(2024, 1, 5)
    assert matched["revenue"] is None
    assert matched["net_margin"] is None
    assert matched["leverage_ratio"] is None
    assert matched["cashflow_efficiency"] is None


@pytest.mark.unit
def test_non_numeric_fundamental_coerced_to_none() -> None:
    """Valor não-numérico em campo fundamental → `None` (coerção defensiva)."""
    report: dict[str, object] = {
        "effective_date": date(2024, 1, 5),
        "revenue": "not-a-number",
        "net_income": 20.0,
        "operating_cash_flow": 30.0,
        "total_shareholder_equity": 50.0,
        "total_liabilities": 25.0,
    }
    rows = list(AsofJoinDuckdbAdapter().asof_join_backward(grid_days=_GRID, reports=[report]))
    matched = rows[0]
    # revenue coage para None no INSERT → net_margin/cashflow_efficiency None.
    assert matched["revenue"] is None
    assert matched["net_margin"] is None
    assert matched["cashflow_efficiency"] is None
    # leverage_ratio (liabilities/equity) não depende de revenue.
    assert matched["leverage_ratio"] == pytest.approx(0.5)


@pytest.mark.unit
def test_non_date_effective_date_raises_type_error() -> None:
    """`effective_date` não-`date` no report → `TypeError` (fronteira do adapter)."""
    report: dict[str, object] = {
        "effective_date": "2024-01-05",  # str, não date
        "revenue": 100.0,
        "net_income": 20.0,
        "operating_cash_flow": 30.0,
        "total_shareholder_equity": 50.0,
        "total_liabilities": 25.0,
    }
    with pytest.raises(TypeError):
        AsofJoinDuckdbAdapter().asof_join_backward(grid_days=_GRID, reports=[report])
