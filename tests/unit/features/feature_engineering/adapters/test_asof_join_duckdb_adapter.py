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
from financial_forecasting.features.feature_engineering.domain.services.fundamentals_asof_policy import (  # noqa: E501
    AntiLeakageError,
    FundamentalsAsofPolicy,
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


class _RaisingPolicy(FundamentalsAsofPolicy):
    """Policy stub que reprova SEMPRE no re-check anti-leakage (defense-in-depth)."""

    def validate_not_future(self, effective_date: date, sample_date: date) -> None:
        raise AntiLeakageError("forced re-check failure (defense-in-depth)")


@pytest.mark.unit
def test_adapter_delegates_anti_leakage_recheck_to_policy() -> None:
    """Defense-in-depth (A5/I1): o adapter chama `validate_not_future` por linha com
    fundamento e PROPAGA o `AntiLeakageError`.

    O ASOF JOIN (`g.day >= r.effective_date`) já impede materializar uma linha com
    `effective_date` futura, então o re-check só pode ser exercitado injetando uma
    policy que reprova — provando que o adapter realmente DELEGA o invariante à policy
    de domínio (e não que a linha confiável passa por sorte).
    """
    report: dict[str, object] = {
        "effective_date": date(2024, 1, 5),
        "revenue": 100.0,
        "net_income": 20.0,
        "operating_cash_flow": 30.0,
        "total_shareholder_equity": 50.0,
        "total_liabilities": 25.0,
    }
    adapter = AsofJoinDuckdbAdapter(policy=_RaisingPolicy())
    with pytest.raises(AntiLeakageError):
        adapter.asof_join_backward(grid_days=_GRID, reports=[report])


@pytest.mark.unit
def test_empty_day_does_not_invoke_policy_recheck() -> None:
    """Dia sem fundamento elegível (C4) NÃO aciona o re-check (sem policy call →
    ratios `None`), mesmo com uma policy que reprovaria se chamada."""
    report: dict[str, object] = {
        "effective_date": date(2024, 1, 15),  # futura a 2024-01-10 → dia vazio
        "revenue": 100.0,
        "net_income": 20.0,
        "operating_cash_flow": 30.0,
        "total_shareholder_equity": 50.0,
        "total_liabilities": 25.0,
    }
    adapter = AsofJoinDuckdbAdapter(policy=_RaisingPolicy())
    rows = list(adapter.asof_join_backward(grid_days=[date(2024, 1, 10)], reports=[report]))
    # linha vazia (C4): não chamou validate_not_future (não levantou) e ratios None.
    assert rows[0]["fundamentals_effective_date"] is None
    assert rows[0]["net_margin"] is None


@pytest.mark.unit
def test_bool_fundamental_coerced_to_none() -> None:
    """`bool` em campo fundamental → `None` (não vira `1.0`/`0.0`; coerção defensiva).

    `bool` é subclasse de `int` em Python; sem o guard explícito `True` viraria `1.0`
    e poluiria os ratios. Mutação que remove o guard falha aqui.
    """
    report: dict[str, object] = {
        "effective_date": date(2024, 1, 5),
        "revenue": True,  # bool, não numérico de verdade
        "net_income": 20.0,
        "operating_cash_flow": 30.0,
        "total_shareholder_equity": 50.0,
        "total_liabilities": 25.0,
    }
    rows = list(AsofJoinDuckdbAdapter().asof_join_backward(grid_days=_GRID, reports=[report]))
    matched = rows[0]
    assert matched["revenue"] is None
    assert matched["net_margin"] is None  # revenue None → denominador inválido
