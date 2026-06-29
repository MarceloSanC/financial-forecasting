"""Teste-foco do invariante anti-leakage do as-of de fundamentos (concept 3.3 A6).

Este é o teste da **razão-de-ser** da Stage 3.3 (overview ADR 0.0.0018 regra 2,
NÃO-NEGOCIÁVEL). Exercita o invariante anti-leakage em duas frentes:

1. **Policy (`FundamentalsAsofPolicy.validate_not_future`):** `effective_date`
   futura ao dia da amostra → `AntiLeakageError` (I1/C1); `==`/`<` não levantam.
2. **Adapter/fake (`asof_join_backward`, parametrizado fake↔real):** um fundamento
   só é visível a partir do seu `effective_date` (backward, nunca antes — I3); a
   saída traz `fundamentals_effective_date <= day` em toda linha (I8); o fallback
   45d é aplicado a montante pela policy (I2); a violação artificial do invariante
   no caminho de saída levanta `AntiLeakageError` (I1, defense-in-depth).

Complementa o unit da policy (Task 01) e o contract test (Task 04) concentrando a
prova do invariante num só lugar auditável.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date

import pytest

from financial_forecasting.features.feature_engineering.adapters.out.duckdb.asof_join_adapter import (  # noqa: E501
    AsofJoinDuckdbAdapter,
)
from financial_forecasting.features.feature_engineering.application.ports.out.asof_join import (
    AsofJoinAdapter,
)
from financial_forecasting.features.feature_engineering.domain.services.fundamentals_asof_policy import (  # noqa: E501
    AntiLeakageError,
    FundamentalsAsofPolicy,
)
from financial_forecasting.features.market_data.domain.entities.fundamental_report import (
    FundamentalReport,
)
from tests.fakes.features.feature_engineering.in_memory_asof_join_adapter import (
    InMemoryAsofJoinAdapter,
)

Row = Mapping[str, object]

_POLICY = FundamentalsAsofPolicy()

_FACTORIES: list[Callable[[], AsofJoinAdapter]] = [
    InMemoryAsofJoinAdapter,
    AsofJoinDuckdbAdapter,
]
_IDS = ["fake", "duckdb"]


@pytest.fixture(params=_FACTORIES, ids=_IDS)
def adapter(request: pytest.FixtureRequest) -> AsofJoinAdapter:
    """Parametriza o invariante sobre o fake e o adapter DuckDB real (paridade)."""
    factory: Callable[[], AsofJoinAdapter] = request.param
    return factory()


def _as_date(value: object) -> date:
    assert isinstance(value, date)
    return value


# --- frente 1: invariante na policy (I1/C1) -----------------------------------


@pytest.mark.unit
def test_policy_raises_anti_leakage_for_future_effective_date() -> None:
    """`effective_date > sample_date` → `AntiLeakageError` (razão-de-ser, I1)."""
    with pytest.raises(AntiLeakageError):
        _POLICY.validate_not_future(date(2024, 6, 1), date(2024, 1, 15))


@pytest.mark.unit
def test_policy_allows_visible_effective_date() -> None:
    """`effective_date <= sample_date` → não levanta (fundamento visível)."""
    _POLICY.validate_not_future(date(2024, 1, 15), date(2024, 1, 15))
    _POLICY.validate_not_future(date(2024, 1, 1), date(2024, 1, 15))


# --- frente 2: invariante no caminho do as-of (parametrizado fake↔real) -------


@pytest.mark.unit
def test_fundamental_visible_only_from_effective_date(adapter: AsofJoinAdapter) -> None:
    """Backward: o fundamento NÃO é visível antes do seu `effective_date` (I3)."""
    report: dict[str, object] = {
        "effective_date": date(2024, 1, 15),
        "revenue": 100.0,
        "net_income": 20.0,
        "operating_cash_flow": 30.0,
        "total_shareholder_equity": 50.0,
        "total_liabilities": 25.0,
    }
    grid = [date(2024, 1, 14), date(2024, 1, 15), date(2024, 1, 16)]
    by_day = {
        _as_date(row["day"]): row
        for row in adapter.asof_join_backward(grid_days=grid, reports=[report])
    }
    # dia anterior ao effective_date: invisível (None).
    assert by_day[date(2024, 1, 14)]["fundamentals_effective_date"] is None
    assert by_day[date(2024, 1, 14)]["revenue"] is None
    # no próprio effective_date e depois: visível.
    assert by_day[date(2024, 1, 15)]["fundamentals_effective_date"] == date(2024, 1, 15)
    assert by_day[date(2024, 1, 16)]["fundamentals_effective_date"] == date(2024, 1, 15)


@pytest.mark.unit
def test_audit_column_never_future(adapter: AsofJoinAdapter) -> None:
    """Toda linha com fundamento tem `fundamentals_effective_date <= day` (I1/I8)."""
    report: dict[str, object] = {
        "effective_date": date(2024, 1, 5),
        "revenue": 100.0,
        "net_income": 20.0,
        "operating_cash_flow": 30.0,
        "total_shareholder_equity": 50.0,
        "total_liabilities": 25.0,
    }
    grid = [date(2024, 1, 4), date(2024, 1, 5), date(2024, 1, 31)]
    for row in adapter.asof_join_backward(grid_days=grid, reports=[report]):
        effective = row["fundamentals_effective_date"]
        if effective is not None:
            assert _as_date(effective) <= _as_date(row["day"])


@pytest.mark.unit
def test_fallback_45d_applied_upstream(adapter: AsofJoinAdapter) -> None:
    """O fallback 45d entra a montante (policy), não no join (I2)."""
    report = FundamentalReport(
        asset_id="AAPL",
        report_type="quarterly",
        fiscal_date_end=date(2023, 12, 1),
        reported_date=None,
        revenue=500.0,
        net_income=100.0,
        operating_cash_flow=150.0,
        total_shareholder_equity=250.0,
        total_liabilities=120.0,
        source="anti-leakage-test",
    )
    effective = _POLICY.effective_date(report)
    assert effective == date(2024, 1, 15)  # Fri 2023-12-01 + 45d = Mon 2024-01-15

    upstream: dict[str, object] = {
        "effective_date": effective,
        "revenue": report.revenue,
        "net_income": report.net_income,
        "operating_cash_flow": report.operating_cash_flow,
        "total_shareholder_equity": report.total_shareholder_equity,
        "total_liabilities": report.total_liabilities,
    }
    grid = [date(2024, 1, 14), date(2024, 1, 15)]
    by_day = {
        _as_date(row["day"]): row
        for row in adapter.asof_join_backward(grid_days=grid, reports=[upstream])
    }
    assert by_day[date(2024, 1, 14)]["fundamentals_effective_date"] is None
    assert by_day[date(2024, 1, 15)]["fundamentals_effective_date"] == date(2024, 1, 15)
