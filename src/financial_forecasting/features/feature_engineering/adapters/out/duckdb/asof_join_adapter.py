"""Adapter `AsofJoinDuckdbAdapter` — DuckDB ASOF JOIN backward de fundamentos.

Traduz o `pandas.merge_asof(direction="backward")` do old
(`build_tft_dataset_use_case.py:513-535`) para um **DuckDB ASOF JOIN backward**
(`ASOF LEFT JOIN f ON d.day >= f.effective_date` — o último fundamento com
`effective_date <= day`), confinando `duckdb` AQUI (concept 3.3 I5/D1, ADR 0.0.0022;
gate `store-no-storage-leak`). Satisfaz o port `AsofJoinAdapter` por duck-typing (NÃO
herda da `application`).

`ASOF LEFT JOIN` (vs `ASOF JOIN` inner) preserva 1 linha por dia de `grid_days`
mesmo sem fundamento elegível (C4 — dia vazio vira `None`), espelhando o
`merge_asof` (left join). A `MATCH_CONDITION`/`ON d.day >= f.effective_date` já
garante o invariante anti-leakage; ainda assim o adapter **re-checa**
`effective_date <= day` por linha materializada (I1, defense-in-depth — paridade com
a policy e o fake).

A materialização da relação DuckDB → `list[dict]` é feita por `description`/`fetchall`
(sem `pandas`/`pyarrow`): a fronteira de saída do port é `Sequence[Mapping]` de
primitivos (`date`/`float`/`None`), `duckdb` não cruza (I7). A coluna interna
`effective_date` sai renomeada como `fundamentals_effective_date` (I8); os 3 ratios
point-in-time são calculados pela `FundamentalsAsofPolicy` (domínio puro, paridade
com o fake).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

import duckdb

from financial_forecasting.features.feature_engineering.domain.services.fundamentals_asof_policy import (  # noqa: E501
    FundamentalsAsofPolicy,
)

Row = Mapping[str, object]

# Campos fundamentais (sem o `effective_date` interno → `fundamentals_effective_date`).
_FUNDAMENTAL_FIELDS = (
    "revenue",
    "net_income",
    "operating_cash_flow",
    "total_shareholder_equity",
    "total_liabilities",
)

# ASOF LEFT JOIN backward: cada dia recebe o último fundamento com
# effective_date <= day (semântica de merge_asof direction="backward"); dia sem
# fundamento elegível → colunas do `rep` em NULL (left join → C4).
_ASOF_SQL = """
SELECT g.day AS day,
       r.effective_date AS fundamentals_effective_date,
       r.revenue AS revenue,
       r.net_income AS net_income,
       r.operating_cash_flow AS operating_cash_flow,
       r.total_shareholder_equity AS total_shareholder_equity,
       r.total_liabilities AS total_liabilities
FROM grid g
ASOF LEFT JOIN rep r ON g.day >= r.effective_date
ORDER BY g.day
"""


class AsofJoinDuckdbAdapter:
    """Adapter DuckDB do contrato `AsofJoinAdapter` (concept 3.3 A5)."""

    def __init__(self, policy: FundamentalsAsofPolicy | None = None) -> None:
        self._policy = policy or FundamentalsAsofPolicy()

    def asof_join_backward(
        self,
        *,
        grid_days: Sequence[date],
        reports: Sequence[Row],
    ) -> Sequence[Row]:
        """As-of backward via DuckDB ASOF JOIN: 1 linha por dia, último `eff <= day` (I3)."""
        connection = duckdb.connect()
        try:
            self._load_grid(connection, grid_days)
            self._load_reports(connection, reports)
            result = connection.execute(_ASOF_SQL)
            columns = [descriptor[0] for descriptor in result.description]
            raw_rows = result.fetchall()
        finally:
            connection.close()
        return [self._build_row(dict(zip(columns, values, strict=True))) for values in raw_rows]

    @staticmethod
    def _load_grid(connection: duckdb.DuckDBPyConnection, grid_days: Sequence[date]) -> None:
        """Materializa a grade de pregão (1 coluna `day DATE`)."""
        connection.execute("CREATE TABLE grid (day DATE)")
        if grid_days:  # executemany exige lista não-vazia (grade vazia → saída vazia)
            connection.executemany("INSERT INTO grid VALUES (?)", [(day,) for day in grid_days])

    @staticmethod
    def _load_reports(connection: duckdb.DuckDBPyConnection, reports: Sequence[Row]) -> None:
        """Materializa os reports (`effective_date` + 5 campos fundamentais)."""
        connection.execute(
            "CREATE TABLE rep ("
            "effective_date DATE, revenue DOUBLE, net_income DOUBLE, "
            "operating_cash_flow DOUBLE, total_shareholder_equity DOUBLE, "
            "total_liabilities DOUBLE)"
        )
        params = [
            (
                _as_date(report.get("effective_date")),
                _as_float(report.get("revenue")),
                _as_float(report.get("net_income")),
                _as_float(report.get("operating_cash_flow")),
                _as_float(report.get("total_shareholder_equity")),
                _as_float(report.get("total_liabilities")),
            )
            for report in reports
        ]
        if params:
            connection.executemany("INSERT INTO rep VALUES (?, ?, ?, ?, ?, ?)", params)

    def _build_row(self, joined: dict[str, object]) -> Row:
        """Monta a `Row` de saída: re-check anti-leakage (I1) + 3 ratios (paridade)."""
        day = _as_date(joined["day"])
        if day is None:  # pragma: no cover - grid sempre traz day não-nulo
            raise ValueError("ASOF join produced a row without `day`")

        effective = _as_date(joined.get("fundamentals_effective_date"))
        row: dict[str, object] = {"day": day, "fundamentals_effective_date": effective}
        for field_name in _FUNDAMENTAL_FIELDS:
            row[field_name] = joined.get(field_name)

        if effective is None:
            # C4 — dia sem fundamento elegível: ratios None.
            row["net_margin"] = None
            row["leverage_ratio"] = None
            row["cashflow_efficiency"] = None
            return row

        # I1 — defense-in-depth: re-checa effective_date <= day (a MATCH_CONDITION já
        # garante, mas o invariante é re-validado pela policy de domínio).
        self._policy.validate_not_future(effective, day)

        revenue = _as_float(joined.get("revenue"))
        net_income = _as_float(joined.get("net_income"))
        operating_cash_flow = _as_float(joined.get("operating_cash_flow"))
        equity = _as_float(joined.get("total_shareholder_equity"))
        liabilities = _as_float(joined.get("total_liabilities"))
        row["net_margin"] = self._policy.net_margin(net_income, revenue)
        row["leverage_ratio"] = self._policy.leverage_ratio(liabilities, equity)
        row["cashflow_efficiency"] = self._policy.cashflow_efficiency(operating_cash_flow, revenue)
        return row


def _as_date(value: object) -> date | None:
    """Coage para `date | None` (preserva `None`; rejeita tipos inesperados)."""
    if value is None:
        return None
    if not isinstance(value, date):
        raise TypeError(f"expected a date, got {type(value).__name__}")
    return value


def _as_float(value: object) -> float | None:
    """Coage para `float | None` (campos fundamentais são numéricos ou `None`)."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
