"""Integração do `ParquetFundamentalFetcher` contra o parquet REAL (concept 2.3 A7, Task 10).

Ponto de verdade dos riscos do concept §10 para fundamentos: conversão
`datetime64 UTC → date`, perda dos 17 `NaT` reais. Lê as 81 linhas reais de AAPL via
o adapter default e prova que TODAS produzem `FundamentalReport`s válidos (I2),
`fiscal_date_end` é `date` sem hora, e os 17 `NaT` viram `reported_date=None` (não
erro). Se nenhuma linha legítima reprova, o risco está fechado. `skipif` se o parquet
não estiver presente (robustez overnight).

`[deviation]` vs technical §2 Task 10: teste de integração `read-all` dedicado em vez
de só estabilizar o contract test — espelha a 2.2 e isola a leitura completa.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from financial_forecasting.features.market_data.adapters.out.parquet.parquet_fundamental_fetcher import (  # noqa: E501
    DEFAULT_FUNDAMENTALS_ROOT,
    ParquetFundamentalFetcher,
)
from financial_forecasting.features.market_data.domain.entities.fundamental_report import (
    FundamentalReport,
)

_SYMBOL = "AAPL"
_EXPECTED_ROWS = 81
_EXPECTED_NAT = 17
_REAL_PATH = DEFAULT_FUNDAMENTALS_ROOT / _SYMBOL / f"fundamentals_{_SYMBOL}.parquet"

pytestmark = pytest.mark.skipif(
    not _REAL_PATH.exists(),
    reason=f"parquet real de fundamentos ausente: {_REAL_PATH}",
)


@pytest.fixture
def reports() -> list[FundamentalReport]:
    return ParquetFundamentalFetcher().fetch_fundamentals(_SYMBOL)


@pytest.mark.integration
def test_reads_all_real_rows(reports: list[FundamentalReport]) -> None:
    """Lê as 81 linhas reais sem rejeitar nenhuma (invariantes I2 passam)."""
    assert len(reports) == _EXPECTED_ROWS
    assert all(isinstance(r, FundamentalReport) for r in reports)


@pytest.mark.integration
def test_fiscal_date_end_is_date_without_time(reports: list[FundamentalReport]) -> None:
    """`fiscal_date_end` real é `date` sem hora (nunca `datetime`)."""
    for report in reports:
        assert isinstance(report.fiscal_date_end, date)
        assert not isinstance(report.fiscal_date_end, datetime)
        assert report.asset_id == _SYMBOL


@pytest.mark.integration
def test_seventeen_nat_become_none(reports: list[FundamentalReport]) -> None:
    """Os 17 `NaT` reais em `reported_date` viram `None` (não erro, I7)."""
    none_count = sum(1 for r in reports if r.reported_date is None)
    assert none_count == _EXPECTED_NAT
    for report in reports:
        if report.reported_date is not None:
            assert isinstance(report.reported_date, date)
            assert not isinstance(report.reported_date, datetime)


@pytest.mark.integration
def test_report_types_are_valid(reports: list[FundamentalReport]) -> None:
    """Todo `report_type` real ∈ {annual, quarterly} (I2)."""
    assert {r.report_type for r in reports} <= {"annual", "quarterly"}
