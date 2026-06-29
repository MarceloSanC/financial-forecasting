"""Teste de integração do `AlphaVantageFundamentalFetcher` — SEM rede (concept 2.3 I13/A9/A10).

Injeta um cliente `httpx` FALSO (`_FakeClient`) que roteia por `function` para
payloads JSON dos 4 endpoints — NUNCA bate na API ao vivo (free-tier ~25 req/dia,
robustez overnight). Cobre: merge por `(report_type, fiscal_date_end)` →
`FundamentalReport`, EARNINGS → `reported_date` (`None` quando ausente),
`"None"`/`"NaN"` em campos numéricos → `None`, `fiscalDateEnding` ausente → item
pulado, guard `Note`/`Information` → `RuntimeError`, throttle 12.5s. Há um teste live
OPCIONAL com `skipif`.
"""

from __future__ import annotations

import os
import socket
from datetime import date

import httpx
import pytest

from financial_forecasting.features.market_data.adapters.out.alpha_vantage import (
    alpha_vantage_fundamental_fetcher as module,
)
from financial_forecasting.features.market_data.adapters.out.alpha_vantage.alpha_vantage_fundamental_fetcher import (  # noqa: E501
    AlphaVantageFundamentalFetcher,
)
from financial_forecasting.features.market_data.domain.entities.fundamental_report import (
    FundamentalReport,
)

_SYMBOL = "AAPL"


class _FakeResponse:
    """Resposta `httpx`-like mínima: `raise_for_status` + `json`."""

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class _FakeClient:
    """Cliente `httpx`-like que roteia o payload por `params['function']` (sem rede)."""

    def __init__(self, by_function: dict[str, object]) -> None:
        self._by_function = by_function
        self.calls: list[str] = []

    def get(
        self, url: str, *, params: dict[str, str] | None = None, headers: object = None
    ) -> _FakeResponse:
        function = (params or {})["function"]
        self.calls.append(function)
        return _FakeResponse(self._by_function[function])


def _payloads() -> dict[str, object]:
    """Payloads dos 4 endpoints: 1 período annual completo + 1 quarterly parcial."""
    return {
        "INCOME_STATEMENT": {
            "annualReports": [
                {
                    "fiscalDateEnding": "2022-09-30",
                    "totalRevenue": "394328000000",
                    "netIncome": "99803000000",
                },
                {
                    # fiscalDateEnding ausente → item pulado (C8)
                    "totalRevenue": "1",
                    "netIncome": "1",
                },
            ],
            "quarterlyReports": [
                {
                    "fiscalDateEnding": "2022-12-31",
                    "totalRevenue": "117154000000",
                    "netIncome": "NaN",  # → None
                }
            ],
        },
        "BALANCE_SHEET": {
            "annualReports": [
                {
                    "fiscalDateEnding": "2022-09-30",
                    "totalShareholderEquity": "50672000000",
                    "totalLiabilities": "302083000000",
                }
            ],
            "quarterlyReports": [
                {
                    "fiscalDateEnding": "2022-12-31",
                    "totalShareholderEquity": "None",  # → None
                    "totalLiabilities": "290437000000",
                }
            ],
        },
        "CASH_FLOW": {
            "annualReports": [
                {"fiscalDateEnding": "2022-09-30", "operatingCashflow": "122151000000"}
            ],
            "quarterlyReports": [
                {"fiscalDateEnding": "2022-12-31", "operatingCashflow": "34005000000"}
            ],
        },
        "EARNINGS": {
            "annualEarnings": [{"fiscalDateEnding": "2022-09-30", "reportedDate": "2022-10-27"}],
            # quarterly SEM reportedDate → reported_date None (NaT)
            "quarterlyEarnings": [{"fiscalDateEnding": "2022-12-31"}],
        },
    }


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutraliza `time.sleep` no throttle (não dorme de verdade no teste)."""
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)


def _fetcher(by_function: dict[str, object]) -> tuple[AlphaVantageFundamentalFetcher, _FakeClient]:
    client = _FakeClient(by_function)
    return AlphaVantageFundamentalFetcher(api_key="demo", client=client), client


@pytest.mark.integration
def test_merges_four_endpoints_into_reports() -> None:
    """Merge dos 4 endpoints → `FundamentalReport` por `(report_type, fiscal_date_end)`."""
    fetcher, client = _fetcher(_payloads())

    reports = fetcher.fetch_fundamentals(_SYMBOL)

    assert all(isinstance(r, FundamentalReport) for r in reports)
    by_key = {(r.report_type, r.fiscal_date_end): r for r in reports}
    # annual 2022-09-30: completo (income + balance + cash_flow + earnings)
    annual = by_key[("annual", date(2022, 9, 30))]
    assert annual.revenue == pytest.approx(394_328_000_000.0)
    assert annual.net_income == pytest.approx(99_803_000_000.0)
    assert annual.operating_cash_flow == pytest.approx(122_151_000_000.0)
    assert annual.total_shareholder_equity == pytest.approx(50_672_000_000.0)
    assert annual.total_liabilities == pytest.approx(302_083_000_000.0)
    # os 4 endpoints foram consultados
    assert client.calls == ["INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW", "EARNINGS"]


@pytest.mark.integration
def test_reported_date_from_earnings() -> None:
    """`reported_date` vem do endpoint EARNINGS (I11)."""
    fetcher, _ = _fetcher(_payloads())
    by_key = {(r.report_type, r.fiscal_date_end): r for r in fetcher.fetch_fundamentals(_SYMBOL)}
    assert by_key[("annual", date(2022, 9, 30))].reported_date == date(2022, 10, 27)


@pytest.mark.integration
def test_reported_date_none_when_earnings_absent() -> None:
    """EARNINGS sem `reportedDate` → `reported_date=None` (NaT, I11)."""
    fetcher, _ = _fetcher(_payloads())
    by_key = {(r.report_type, r.fiscal_date_end): r for r in fetcher.fetch_fundamentals(_SYMBOL)}
    assert by_key[("quarterly", date(2022, 12, 31))].reported_date is None


@pytest.mark.integration
def test_none_and_nan_numeric_become_none() -> None:
    """`"NaN"`/`"None"` em campos numéricos → `None` (`_to_float` defensivo)."""
    fetcher, _ = _fetcher(_payloads())
    by_key = {(r.report_type, r.fiscal_date_end): r for r in fetcher.fetch_fundamentals(_SYMBOL)}
    quarterly = by_key[("quarterly", date(2022, 12, 31))]
    assert quarterly.net_income is None  # "NaN"
    assert quarterly.total_shareholder_equity is None  # "None"
    assert quarterly.total_liabilities == pytest.approx(290_437_000_000.0)


@pytest.mark.integration
def test_item_without_fiscal_date_is_skipped() -> None:
    """Item sem `fiscalDateEnding` é pulado (C8): só 2 reports no total (annual+quarterly)."""
    fetcher, _ = _fetcher(_payloads())
    reports = fetcher.fetch_fundamentals(_SYMBOL)
    keys = {(r.report_type, r.fiscal_date_end) for r in reports}
    assert keys == {("annual", date(2022, 9, 30)), ("quarterly", date(2022, 12, 31))}


@pytest.mark.integration
def test_rate_limit_note_raises_runtime_error() -> None:
    """Resposta com chave `Note` no primeiro endpoint → `RuntimeError` (C7)."""
    payloads = _payloads()
    payloads["INCOME_STATEMENT"] = {"Note": "rate limit hit"}
    fetcher, _ = _fetcher(payloads)
    with pytest.raises(RuntimeError, match="rate limit"):
        fetcher.fetch_fundamentals(_SYMBOL)


@pytest.mark.integration
def test_information_key_raises_runtime_error() -> None:
    """Resposta com chave `Information` → `RuntimeError` (C7)."""
    payloads = _payloads()
    payloads["INCOME_STATEMENT"] = {"Information": "25 requests/day"}
    fetcher, _ = _fetcher(payloads)
    with pytest.raises(RuntimeError, match="Information"):
        fetcher.fetch_fundamentals(_SYMBOL)


@pytest.mark.integration
def test_non_dict_response_raises() -> None:
    """Resposta JSON não-dict → `ValueError` (C7)."""
    payloads = _payloads()
    payloads["INCOME_STATEMENT"] = ["not", "a", "dict"]
    fetcher, _ = _fetcher(payloads)
    with pytest.raises(ValueError, match="Unexpected response format"):
        fetcher.fetch_fundamentals(_SYMBOL)


@pytest.mark.integration
def test_invalid_fiscal_date_string_skips_item() -> None:
    """`fiscalDateEnding` ilegível (não `YYYY-MM-DD`) → item pulado (`_to_date` → None)."""
    payloads = _payloads()
    payloads["INCOME_STATEMENT"] = {
        "annualReports": [{"fiscalDateEnding": "30/09/2022", "totalRevenue": "1"}],
        "quarterlyReports": [],
    }
    # zera os demais endpoints para isolar
    payloads["BALANCE_SHEET"] = {"annualReports": [], "quarterlyReports": []}
    payloads["CASH_FLOW"] = {"annualReports": [], "quarterlyReports": []}
    payloads["EARNINGS"] = {"annualEarnings": [], "quarterlyEarnings": []}
    fetcher, _ = _fetcher(payloads)
    assert fetcher.fetch_fundamentals(_SYMBOL) == []


@pytest.mark.integration
def test_earnings_item_without_fiscal_date_is_skipped() -> None:
    """Item de EARNINGS sem `fiscalDateEnding` é pulado (ramo `continue`, C8)."""
    payloads = _payloads()
    payloads["EARNINGS"] = {
        "annualEarnings": [{"reportedDate": "2022-10-27"}],  # sem fiscalDateEnding
        "quarterlyEarnings": [],
    }
    fetcher, _ = _fetcher(payloads)
    by_key = {(r.report_type, r.fiscal_date_end): r for r in fetcher.fetch_fundamentals(_SYMBOL)}
    # nenhum reported_date atribuído (o item de earnings foi pulado)
    assert by_key[("annual", date(2022, 9, 30))].reported_date is None


@pytest.mark.integration
def test_throttle_sleeps_between_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    """As 4 chamadas em sequência exercitam o `sleep` do throttle 12.5s (I9)."""
    slept: list[float] = []
    monkeypatch.setattr(module.time, "sleep", slept.append)
    monkeypatch.setattr(module.time, "monotonic", lambda: 100.0)

    fetcher, _ = _fetcher(_payloads())
    fetcher.fetch_fundamentals(_SYMBOL)

    assert slept  # dormiu entre endpoints (mesma instância, intervalo zero)


@pytest.mark.integration
def test_to_float_handles_non_numeric_string() -> None:
    """`_to_float` de string não-numérica → `None` (ramo except)."""
    assert module._to_float("abc") is None
    assert module._to_float([1, 2]) is None


@pytest.mark.integration
def test_default_client_is_httpx_without_network() -> None:
    """Sem `client` injetado, cria um `httpx.Client` na construção — sem rede."""
    fetcher = AlphaVantageFundamentalFetcher(api_key="demo")
    assert isinstance(fetcher._client, httpx.Client)


def _has_network() -> bool:
    try:
        socket.create_connection(("www.alphavantage.co", 443), timeout=2).close()
    except OSError:
        return False
    return True


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("FF_LIVE_ALPHAVANTAGE") != "1"
    or not os.environ.get("ALPHAVANTAGE_API_KEY")
    or not _has_network(),
    reason="teste live opcional: requer FF_LIVE_ALPHAVANTAGE=1, chave e rede (não roda no CI)",
)
def test_live_fetch_optional() -> None:  # pragma: no cover - live, opt-in
    """Teste LIVE opt-in (não roda no CI): bate na API real só se habilitado."""
    key = os.environ["ALPHAVANTAGE_API_KEY"]
    fetcher = AlphaVantageFundamentalFetcher(api_key=key)
    reports = fetcher.fetch_fundamentals(_SYMBOL)
    assert all(r.asset_id == _SYMBOL for r in reports)
