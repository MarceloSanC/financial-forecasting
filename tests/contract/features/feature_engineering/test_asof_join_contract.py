"""Contract test do port `AsofJoinAdapter` — paridade Fake <-> AsofJoinDuckdbAdapter.

Um ÚNICO contrato parametrizado prova que o fake in-memory (Task 03) e o adapter
DuckDB real (Task 04) honram a MESMA semântica observável (concept 3.3 A8, ADR
0.0.0021). As assertivas espelham o oráculo do old
(`merge_asof(direction="backward")`):

- (a) **as-of backward (I3):** 1 linha por dia de pregão; cada dia recebe o último
  fundamento com `effective_date <= day`; um fundamento NÃO é visível antes do seu
  `effective_date`.
- (b) **coluna de auditoria (I8):** toda linha com fundamento traz
  `fundamentals_effective_date <= day`; o nome interno `effective_date` não aparece.
- (c) **fallback 45d a montante (I2):** os reports já chegam com `effective_date`
  calculado pela `FundamentalsAsofPolicy` (fallback aplicado fora do join).
- (d) **dia sem fundamento elegível (C4):** fundamentos + auditoria + ratios `None`.
- (e) **anti-leakage (I1):** o invariante `effective_date <= day` vale para toda
  linha (a violação é provada levantar `AntiLeakageError` no teste-foco da Task 05
  e no unit da policy — Task 01).
- ratios point-in-time corretos e idênticos entre fake e real.

`AsofJoinAdapter` (Protocol, duck-typed) tipa a fixture parametrizada [fake, real];
ambos rodam SEM instalar nada novo (`duckdb` já é dependência do projeto).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date

import pytest

from financial_forecasting.features.feature_engineering.adapters.out.duckdb.asof_join_adapter import (  # noqa: E501
    AsofJoinDuckdbAdapter,
)
from financial_forecasting.features.feature_engineering.application.ports.out.asof_join import (
    AsofJoinAdapter,
)
from financial_forecasting.features.feature_engineering.domain.services.fundamentals_asof_policy import (  # noqa: E501
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

# Reports já com `effective_date` calculado pela policy (fallback a montante — c).
# r1 effective 2024-01-05; r2 effective 2024-01-15.
_R1: dict[str, object] = {
    "effective_date": date(2024, 1, 5),
    "revenue": 100.0,
    "net_income": 20.0,
    "operating_cash_flow": 30.0,
    "total_shareholder_equity": 50.0,
    "total_liabilities": 25.0,
}
_R2: dict[str, object] = {
    "effective_date": date(2024, 1, 15),
    "revenue": 200.0,
    "net_income": 40.0,
    "operating_cash_flow": 60.0,
    "total_shareholder_equity": 100.0,
    "total_liabilities": 80.0,
}
_REPORTS: Sequence[Row] = [_R1, _R2]
# Grade: antes de qualquer report; entre r1 e r2; em r2; depois de r2.
_GRID = [date(2024, 1, 1), date(2024, 1, 10), date(2024, 1, 15), date(2024, 1, 20)]

_FACTORIES: list[Callable[[], AsofJoinAdapter]] = [
    InMemoryAsofJoinAdapter,
    AsofJoinDuckdbAdapter,
]
_IDS = ["fake", "duckdb"]


@pytest.fixture(params=_FACTORIES, ids=_IDS)
def adapter(request: pytest.FixtureRequest) -> AsofJoinAdapter:
    """Parametriza o contrato sobre o fake e o adapter DuckDB real."""
    factory: Callable[[], AsofJoinAdapter] = request.param
    return factory()


def _rows_by_day(adapter: AsofJoinAdapter) -> dict[date, Row]:
    rows = adapter.asof_join_backward(grid_days=_GRID, reports=_REPORTS)
    return {_as_date(row["day"]): row for row in rows}


def _as_date(value: object) -> date:
    assert isinstance(value, date)
    return value


@pytest.mark.contract
def test_one_row_per_grid_day_order_preserved(adapter: AsofJoinAdapter) -> None:
    """1 linha por dia de pregão, na ordem de `grid_days` (I3)."""
    rows = list(adapter.asof_join_backward(grid_days=_GRID, reports=_REPORTS))
    assert [_as_date(row["day"]) for row in rows] == _GRID


@pytest.mark.contract
def test_asof_backward_picks_latest_eligible(adapter: AsofJoinAdapter) -> None:
    """Cada dia recebe o último fundamento com `effective_date <= day` (a/I3)."""
    by_day = _rows_by_day(adapter)
    # 2024-01-01: antes de r1 → vazio (C4).
    assert by_day[date(2024, 1, 1)]["fundamentals_effective_date"] is None
    # 2024-01-10: r1 já visível (eff 01-05), r2 ainda não (eff 01-15) → r1.
    assert by_day[date(2024, 1, 10)]["fundamentals_effective_date"] == date(2024, 1, 5)
    assert by_day[date(2024, 1, 10)]["revenue"] == _R1["revenue"]
    # 2024-01-15: r2 visível no próprio effective_date (<=) → r2.
    assert by_day[date(2024, 1, 15)]["fundamentals_effective_date"] == date(2024, 1, 15)
    assert by_day[date(2024, 1, 15)]["revenue"] == _R2["revenue"]
    # 2024-01-20: último elegível é r2.
    assert by_day[date(2024, 1, 20)]["fundamentals_effective_date"] == date(2024, 1, 15)


@pytest.mark.contract
def test_fundamental_not_visible_before_effective_date(adapter: AsofJoinAdapter) -> None:
    """Um fundamento NÃO é visível antes do seu `effective_date` (a/I3)."""
    by_day = _rows_by_day(adapter)
    # Antes de 01-05 nenhum report; antes de 01-15 r2 invisível.
    assert by_day[date(2024, 1, 1)]["revenue"] is None
    assert by_day[date(2024, 1, 10)]["fundamentals_effective_date"] != date(2024, 1, 15)


@pytest.mark.contract
def test_audit_column_present_and_not_future(adapter: AsofJoinAdapter) -> None:
    """`fundamentals_effective_date` presente e `<= day`; sem `effective_date` cru (b/e)."""
    rows = adapter.asof_join_backward(grid_days=_GRID, reports=_REPORTS)
    for row in rows:
        assert "fundamentals_effective_date" in row
        assert "effective_date" not in row  # nome interno nunca exposto (I8)
        effective = row["fundamentals_effective_date"]
        if effective is not None:
            assert isinstance(effective, date)
            assert effective <= _as_date(row["day"])  # invariante anti-leakage (I1)


@pytest.mark.contract
def test_empty_day_yields_all_none(adapter: AsofJoinAdapter) -> None:
    """Dia sem fundamento elegível → fundamentos/auditoria/ratios `None` (d/C4)."""
    row = _rows_by_day(adapter)[date(2024, 1, 1)]
    for key in (
        "fundamentals_effective_date",
        "revenue",
        "net_income",
        "operating_cash_flow",
        "total_shareholder_equity",
        "total_liabilities",
        "net_margin",
        "leverage_ratio",
        "cashflow_efficiency",
    ):
        assert row[key] is None


@pytest.mark.contract
def test_ratios_point_in_time_correct(adapter: AsofJoinAdapter) -> None:
    """Ratios derivados corretos por linha (DoD: ratios em fixture)."""
    by_day = _rows_by_day(adapter)
    r1_row = by_day[date(2024, 1, 10)]
    assert r1_row["net_margin"] == pytest.approx(0.2)  # 20/100
    assert r1_row["leverage_ratio"] == pytest.approx(0.5)  # 25/50
    assert r1_row["cashflow_efficiency"] == pytest.approx(0.3)  # 30/100
    r2_row = by_day[date(2024, 1, 20)]
    assert r2_row["net_margin"] == pytest.approx(0.2)  # 40/200
    assert r2_row["leverage_ratio"] == pytest.approx(0.8)  # 80/100


@pytest.mark.contract
def test_empty_grid_yields_empty_output(adapter: AsofJoinAdapter) -> None:
    """Grade vazia → saída vazia (sem 1 linha)."""
    assert list(adapter.asof_join_backward(grid_days=[], reports=_REPORTS)) == []


@pytest.mark.contract
def test_no_reports_yields_all_empty_rows(adapter: AsofJoinAdapter) -> None:
    """Sem reports → 1 linha por dia, todas com fundamentos `None` (C4)."""
    rows = list(adapter.asof_join_backward(grid_days=_GRID, reports=[]))
    assert len(rows) == len(_GRID)
    for row in rows:
        assert row["fundamentals_effective_date"] is None
        assert row["revenue"] is None


@pytest.mark.contract
def test_fallback_45d_applied_upstream(adapter: AsofJoinAdapter) -> None:
    """Reports chegam com `effective_date` da policy (fallback a montante — c/I2)."""
    # report sem reported_date → effective_date = fiscal_date_end + 45d (Fri->Mon).
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
        source="contract-test",
    )
    effective = _POLICY.effective_date(report)
    assert effective == date(2024, 1, 15)  # oráculo: fallback 45d calendário

    upstream_row: dict[str, object] = {
        "effective_date": effective,
        "revenue": report.revenue,
        "net_income": report.net_income,
        "operating_cash_flow": report.operating_cash_flow,
        "total_shareholder_equity": report.total_shareholder_equity,
        "total_liabilities": report.total_liabilities,
    }
    by_day = {
        _as_date(row["day"]): row
        for row in adapter.asof_join_backward(grid_days=_GRID, reports=[upstream_row])
    }
    # invisível em 01-10 (antes do effective 01-15); visível em 01-15 e 01-20.
    assert by_day[date(2024, 1, 10)]["fundamentals_effective_date"] is None
    assert by_day[date(2024, 1, 15)]["fundamentals_effective_date"] == date(2024, 1, 15)
