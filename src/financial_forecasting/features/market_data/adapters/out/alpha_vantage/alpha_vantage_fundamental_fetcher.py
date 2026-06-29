"""Adapter `AlphaVantageFundamentalFetcher` — origem NÃO-default (concept 2.3 D3 / I11).

Porta do old (`financial-time-series-forecasting/src/adapters/alpha_vantage_fundamental_fetcher.py`)
com julgamento, trocando `requests` por **`httpx`** (já em deps, sem nova dep —
[decision] §7). Busca fundamentos dos **4 endpoints** (`INCOME_STATEMENT` +
`BALANCE_SHEET` + `CASH_FLOW` + `EARNINGS`), faz merge por
`(report_type, fiscal_date_end)` e converte para entities `FundamentalReport`.
Implementa o port `FundamentalFetcher` por duck-typing.

NÃO é a origem default — o pipeline reusa o parquet existente
(`ParquetFundamentalFetcher`). Existe para re-ingestão ao vivo consciente; o teste
de integração injeta um cliente `httpx` falso e NUNCA bate na API ao vivo (free-tier
~25 req/dia, robustez overnight — concept 2.3 I13). `httpx` vive SÓ aqui (I3).

EARNINGS é a ÚNICA fonte de `reported_date` (nullable; ausente → `None`/`NaT`),
alimentando o fallback as-of H-3 da 3.3 (ADR 2.3.0001 / D3 / I11). Field maps
**verbatim** do old. `_to_float`/`_to_date` defensivos (old `:89-105`):
`"None"`/`"NaN"`/`""`/`"null"` → `None`; `fiscalDateEnding` ausente/ilegível → item
pulado (`_to_date → None → continue`, C8). Throttle `12.5s` (`_MIN_INTERVAL` + lock +
`time.monotonic`) no adapter (I9, old `:30`). Guard `Note`/`Information` →
`RuntimeError` (C7); sem rede em import.
"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime
from typing import Any

import httpx

from financial_forecasting.features.market_data.domain.entities.fundamental_report import (
    FundamentalReport,
)

# Field maps verbatim do old (`:139-150`): chave da API → campo da entity.
_INCOME_MAP = {"totalRevenue": "revenue", "netIncome": "net_income"}
_BALANCE_MAP = {
    "totalShareholderEquity": "total_shareholder_equity",
    "totalLiabilities": "total_liabilities",
}
_CASH_FLOW_MAP = {"operatingCashflow": "operating_cash_flow"}

# (report_type, chave de lista) para statements e earnings.
_STATEMENT_KEYS = (("annual", "annualReports"), ("quarterly", "quarterlyReports"))
_EARNINGS_KEYS = (("annual", "annualEarnings"), ("quarterly", "quarterlyEarnings"))

_NULL_TOKENS = (None, "", "None", "null", "NaN")


class AlphaVantageFundamentalFetcher:
    """Implementação do `FundamentalFetcher` sobre Alpha Vantage (4 endpoints, não-default)."""

    BASE_URL = "https://www.alphavantage.co/query"
    _MIN_INTERVAL = 12.5  # segundos (free-tier Alpha Vantage)

    def __init__(
        self,
        api_key: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
        user_agent: str = "financial-forecasting/1.0",
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._user_agent = user_agent
        self._last_request_ts: float | None = None
        self._lock = threading.Lock()

    def _throttle(self) -> None:
        """Respeita `_MIN_INTERVAL` entre requisições (lock + `time.monotonic`)."""
        with self._lock:
            now = time.monotonic()
            if self._last_request_ts is not None:
                sleep_for = self._MIN_INTERVAL - (now - self._last_request_ts)
                if sleep_for > 0:
                    time.sleep(sleep_for)
            self._last_request_ts = time.monotonic()

    def _get(self, function: str, symbol: str) -> dict[str, Any]:
        """GET throttled de um endpoint; valida resposta (guard de rate-limit, C7)."""
        self._throttle()
        response = self._client.get(
            self.BASE_URL,
            params={"function": function, "symbol": symbol, "apikey": self._api_key},
            headers={"Accept": "application/json", "User-Agent": self._user_agent},
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError(f"Unexpected response format for {function}")
        if "Note" in data:
            raise RuntimeError(f"Alpha Vantage rate limit hit: {data['Note']}")
        if "Information" in data:
            raise RuntimeError(f"Alpha Vantage Information: {data['Information']}")
        return data

    def fetch_fundamentals(self, asset_id: str) -> list[FundamentalReport]:
        """Busca os 4 endpoints, faz merge por `(report_type, fiscal_date_end)`."""
        income = self._get("INCOME_STATEMENT", asset_id)
        balance = self._get("BALANCE_SHEET", asset_id)
        cash_flow = self._get("CASH_FLOW", asset_id)
        earnings = self._get("EARNINGS", asset_id)

        merged: dict[tuple[str, date], dict[str, Any]] = {}
        for report_type, key in _STATEMENT_KEYS:
            _merge_reports(merged, report_type, income.get(key) or [], _INCOME_MAP)
            _merge_reports(merged, report_type, balance.get(key) or [], _BALANCE_MAP)
            _merge_reports(merged, report_type, cash_flow.get(key) or [], _CASH_FLOW_MAP)

        # EARNINGS é a única fonte de reported_date (nullable; ausente → None).
        for report_type, key in _EARNINGS_KEYS:
            for item in earnings.get(key) or []:
                fiscal_end = _to_date(item.get("fiscalDateEnding"))
                if fiscal_end is None:
                    continue
                entry = merged.setdefault(
                    (report_type, fiscal_end),
                    {"fiscal_date_end": fiscal_end, "report_type": report_type},
                )
                reported_date = _to_date(item.get("reportedDate"))
                if reported_date is not None:
                    entry["reported_date"] = reported_date

        reports = [
            FundamentalReport(
                asset_id=asset_id,
                report_type=report_type,
                fiscal_date_end=fiscal_end,
                reported_date=values.get("reported_date"),
                revenue=values.get("revenue"),
                net_income=values.get("net_income"),
                operating_cash_flow=values.get("operating_cash_flow"),
                total_shareholder_equity=values.get("total_shareholder_equity"),
                total_liabilities=values.get("total_liabilities"),
                source="alpha_vantage",
            )
            for (report_type, fiscal_end), values in merged.items()
        ]
        reports.sort(key=lambda r: (r.report_type, r.fiscal_date_end))
        return reports


def _merge_reports(
    base: dict[tuple[str, date], dict[str, Any]],
    report_type: str,
    records: list[dict[str, Any]],
    field_map: dict[str, str],
) -> None:
    """Funde `records` de um endpoint no acumulador por `(report_type, fiscal_end)`."""
    for item in records:
        fiscal_end = _to_date(item.get("fiscalDateEnding"))
        if fiscal_end is None:
            continue  # fiscalDateEnding ausente/ilegível → item pulado (C8)
        entry = base.setdefault(
            (report_type, fiscal_end),
            {"fiscal_date_end": fiscal_end, "report_type": report_type},
        )
        for src_key, dst_key in field_map.items():
            entry[dst_key] = _to_float(item.get(src_key))


def _to_date(value: object) -> date | None:
    """Parseia `YYYY-MM-DD` → `date`; nulo/ilegível → `None` (old `:89-95`)."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def _to_float(value: object) -> float | None:
    """Coage para `float`; `None`/`""`/`"None"`/`"null"`/`"NaN"` → `None` (old `:97-105`)."""
    if value in _NULL_TOKENS:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
