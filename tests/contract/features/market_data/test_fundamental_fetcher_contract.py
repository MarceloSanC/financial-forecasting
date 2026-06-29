"""Contract test do port `FundamentalFetcher` — paridade Fake ↔ ParquetFundamentalFetcher.

Um ÚNICO contrato parametrizado prova que ambas as implementações honram a MESMA
semântica observável (concept 2.3 I14/A4): `fetch_fundamentals` devolve
`list[FundamentalReport]` com invariantes I2 respeitadas, `reported_date`
`date|None` (alguns `None` reais — `NaT`), `fiscal_date_end` é `date` sem hora, e
TODOS os reports do ativo (sem filtrar `report_type`/intervalo — isso é do use case).

O `real` (`ParquetFundamentalFetcher`) lê um parquet sintético escrito em `tmp_path`
com o MESMO layout/dtypes do processado
(`<root>/<symbol>/fundamentals_<symbol>.parquet`, 10 colunas, datas `UTC`, floats
`float64`, `reported_date` com `NaT`) — hermético e rápido. A validação contra o
parquet real completo (81 linhas, 17 `NaT`) é da Task 10 / integração.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from financial_forecasting.features.market_data.adapters.out.parquet.parquet_fundamental_fetcher import (  # noqa: E501
    ParquetFundamentalFetcher,
)

# `FundamentalFetcher` (Protocol, duck-typed) tipa a fixture parametrizada.
from financial_forecasting.features.market_data.application.ports.out.fundamental_fetcher import (
    FundamentalFetcher,
)
from financial_forecasting.features.market_data.domain.entities.fundamental_report import (
    FundamentalReport,
)
from financial_forecasting.shared.domain.exceptions.base import ApplicationError
from tests.fakes.features.market_data.in_memory_fundamental_fetcher import (
    FakeFundamentalFetcher,
)

_SYMBOL = "AAPL"
_THREE = 3


def _reports() -> list[FundamentalReport]:
    """Conjunto canônico de reports (com 1 SEM `reported_date` — `NaT` real)."""
    return [
        FundamentalReport(
            asset_id=_SYMBOL,
            report_type="annual",
            fiscal_date_end=date(2021, 9, 30),
            reported_date=None,  # NaT real
            revenue=365_817_000_000.0,
            net_income=94_680_000_000.0,
            operating_cash_flow=104_038_000_000.0,
            total_shareholder_equity=63_090_000_000.0,
            total_liabilities=287_912_000_000.0,
            source="alpha_vantage",
        ),
        FundamentalReport(
            asset_id=_SYMBOL,
            report_type="annual",
            fiscal_date_end=date(2022, 9, 30),
            reported_date=date(2022, 10, 27),
            revenue=394_328_000_000.0,
            net_income=99_803_000_000.0,
            operating_cash_flow=122_151_000_000.0,
            total_shareholder_equity=50_672_000_000.0,
            total_liabilities=302_083_000_000.0,
            source="alpha_vantage",
        ),
        FundamentalReport(
            asset_id=_SYMBOL,
            report_type="quarterly",
            fiscal_date_end=date(2022, 12, 31),
            reported_date=date(2023, 2, 2),
            revenue=117_154_000_000.0,
            net_income=29_998_000_000.0,
            operating_cash_flow=None,  # NaN real
            total_shareholder_equity=56_727_000_000.0,
            total_liabilities=290_437_000_000.0,
            source="alpha_vantage",
        ),
    ]


def _write_parquet(root: Path, symbol: str, reports: list[FundamentalReport]) -> None:
    """Escreve o parquet sintético no layout/dtypes esperados pelo adapter (10 colunas)."""
    path = root / symbol / f"fundamentals_{symbol}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "asset_id": pd.array([r.asset_id for r in reports], dtype="string"),
            "report_type": pd.array([r.report_type for r in reports], dtype="string"),
            "fiscal_date_end": pd.to_datetime([r.fiscal_date_end for r in reports], utc=True),
            "reported_date": pd.to_datetime([r.reported_date for r in reports], utc=True),
            "revenue": [r.revenue for r in reports],
            "net_income": [r.net_income for r in reports],
            "operating_cash_flow": [r.operating_cash_flow for r in reports],
            "total_shareholder_equity": [r.total_shareholder_equity for r in reports],
            "total_liabilities": [r.total_liabilities for r in reports],
            "source": pd.array([r.source for r in reports], dtype="string"),
        }
    )
    frame.to_parquet(path)


def _build_fake(_tmp_path: Path) -> FundamentalFetcher:
    return FakeFundamentalFetcher(_reports())


def _build_real(tmp_path: Path) -> FundamentalFetcher:
    _write_parquet(tmp_path, _SYMBOL, _reports())
    return ParquetFundamentalFetcher(tmp_path)


_FACTORIES: list[Callable[[Path], FundamentalFetcher]] = [_build_fake, _build_real]
_IDS = ["fake", "real"]


@pytest.fixture(params=_FACTORIES, ids=_IDS)
def fetcher(request: pytest.FixtureRequest, tmp_path: Path) -> FundamentalFetcher:
    """Parametriza o contrato sobre o fake e o adapter real (paridade fake↔real)."""
    factory: Callable[[Path], FundamentalFetcher] = request.param
    return factory(tmp_path)


@pytest.mark.contract
def test_fetch_returns_list_of_reports(fetcher: FundamentalFetcher) -> None:
    """Devolve `list[FundamentalReport]` com TODOS os reports do ativo (sem filtro)."""
    reports = fetcher.fetch_fundamentals(_SYMBOL)

    assert reports
    assert all(isinstance(r, FundamentalReport) for r in reports)
    assert len(reports) == _THREE


@pytest.mark.contract
def test_fiscal_date_end_is_date_without_time(fetcher: FundamentalFetcher) -> None:
    """`fiscal_date_end` é `date` sem hora (nunca `datetime`) — I2."""
    for report in fetcher.fetch_fundamentals(_SYMBOL):
        assert isinstance(report.fiscal_date_end, date)
        assert not isinstance(report.fiscal_date_end, datetime)


@pytest.mark.contract
def test_reported_date_is_date_or_none(fetcher: FundamentalFetcher) -> None:
    """`reported_date` é `date|None`; ao menos um `None` real (`NaT`)."""
    reported = [r.reported_date for r in fetcher.fetch_fundamentals(_SYMBOL)]
    assert any(rd is None for rd in reported)
    for rd in reported:
        assert rd is None or (isinstance(rd, date) and not isinstance(rd, datetime))


@pytest.mark.contract
def test_none_numeric_preserved(fetcher: FundamentalFetcher) -> None:
    """Numérico `NaN`/nulo → `None` (schema nullable)."""
    by_key = {(r.report_type, r.fiscal_date_end): r for r in fetcher.fetch_fundamentals(_SYMBOL)}
    quarterly = by_key[("quarterly", date(2022, 12, 31))]
    assert quarterly.operating_cash_flow is None


@pytest.mark.contract
def test_asset_id_matches_requested(fetcher: FundamentalFetcher) -> None:
    """`asset_id` dos reports é o ativo pedido (normalizado)."""
    for report in fetcher.fetch_fundamentals(_SYMBOL):
        assert report.asset_id == _SYMBOL


# -- testes específicos do adapter real (origem default; concept 2.3 C6) -------


@pytest.mark.contract
def test_real_missing_file_raises_application_error(tmp_path: Path) -> None:
    """Arquivo de origem ausente → `ApplicationError` (não lista vazia, C6)."""
    real = ParquetFundamentalFetcher(tmp_path)
    with pytest.raises(ApplicationError, match="not found"):
        real.fetch_fundamentals(_SYMBOL)


@pytest.mark.contract
def test_real_missing_column_raises_application_error(tmp_path: Path) -> None:
    """Coluna obrigatória ausente no parquet → `ApplicationError` (C6)."""
    path = tmp_path / _SYMBOL / f"fundamentals_{_SYMBOL}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    # parquet sem a coluna `total_liabilities`
    pd.DataFrame(
        {
            "asset_id": ["AAPL"],
            "report_type": ["annual"],
            "fiscal_date_end": pd.to_datetime(["2022-09-30"], utc=True),
            "reported_date": pd.to_datetime(["2022-10-27"], utc=True),
            "revenue": [1.0],
            "net_income": [1.0],
            "operating_cash_flow": [1.0],
            "total_shareholder_equity": [1.0],
            "source": ["alpha_vantage"],
        }
    ).to_parquet(path)

    with pytest.raises(ApplicationError, match="missing columns"):
        ParquetFundamentalFetcher(tmp_path).fetch_fundamentals(_SYMBOL)


@pytest.mark.contract
def test_real_normalizes_asset_id_with_exchange_suffix(tmp_path: Path) -> None:
    """`asset_id` com sufixo de bolsa é normalizado (`AAPL.US` → `AAPL`)."""
    _write_parquet(tmp_path, _SYMBOL, _reports())
    reports = ParquetFundamentalFetcher(tmp_path).fetch_fundamentals("AAPL.US")
    assert reports
    assert all(r.asset_id == _SYMBOL for r in reports)
