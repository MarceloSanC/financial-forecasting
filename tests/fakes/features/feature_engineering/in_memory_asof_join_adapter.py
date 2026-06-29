"""Fake in-memory do port `AsofJoinAdapter` — NÃO um mock (concept 3.3 A7).

`InMemoryAsofJoinAdapter` é um fake COMPORTAMENTAL determinístico (stdlib-only) que
satisfaz o `Protocol` `AsofJoinAdapter` por duck-typing, com a MESMA semântica
backward do adapter real (`AsofJoinDuckdbAdapter`, Task 04) — base do contract test
de paridade fake↔real (ADR 0.0.0021). Torna o contrato testável SEM instalar/rodar
DuckDB.

Algoritmo (espelha `merge_asof(direction="backward")` do old `:513-535`):

- Ordena os `reports` por `effective_date`.
- Para cada `day` de `grid_days` (ordem preservada), escolhe o report com o **maior**
  `effective_date <= day` (I3 — visibilidade backward, último elegível).
- Re-checa o invariante anti-leakage via `FundamentalsAsofPolicy.validate_not_future`
  (I1, defense-in-depth) — mesma semântica observável que o real.
- Monta a `Row` de saída: `day` + os campos fundamentais do report escolhido + a
  coluna de auditoria `fundamentals_effective_date` (rename de `effective_date` na
  fronteira — I8) + os 3 ratios point-in-time via a policy (paridade com o real).
- Dia sem fundamento elegível → campos fundamentais + `fundamentals_effective_date`
  + ratios todos `None` (C4); a linha existe (1 por dia).

Vive em `tests/` (fora do gate `import-linter`), mas mantém o contrato agnóstico de
`duckdb`/`pandas`: importa SÓ stdlib + a policy de domínio.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from financial_forecasting.features.feature_engineering.domain.services.fundamentals_asof_policy import (  # noqa: E501
    FundamentalsAsofPolicy,
)

Row = Mapping[str, object]

# Campos fundamentais carregados do report para a saída (sem o `effective_date`
# interno, que vira `fundamentals_effective_date` na fronteira — I8).
_FUNDAMENTAL_FIELDS = (
    "revenue",
    "net_income",
    "operating_cash_flow",
    "total_shareholder_equity",
    "total_liabilities",
)


class InMemoryAsofJoinAdapter:
    """Implementação in-memory determinística do contrato `AsofJoinAdapter` (A7)."""

    def __init__(self, policy: FundamentalsAsofPolicy | None = None) -> None:
        self._policy = policy or FundamentalsAsofPolicy()

    def asof_join_backward(
        self,
        *,
        grid_days: Sequence[date],
        reports: Sequence[Row],
    ) -> Sequence[Row]:
        """As-of backward stdlib: 1 linha por dia, último `effective_date <= day` (I3)."""
        ordered = sorted(reports, key=_effective_date)
        rows: list[Row] = []
        for day in grid_days:
            match = self._latest_eligible(ordered, day)
            rows.append(self._build_row(day, match))
        return rows

    def _latest_eligible(self, ordered_reports: Sequence[Row], day: date) -> Row | None:
        """Último report com `effective_date <= day` (backward); re-checa invariante (I1)."""
        chosen: Row | None = None
        for report in ordered_reports:  # ordenado asc por effective_date
            eff = _effective_date(report)
            if eff <= day:
                chosen = report
            else:
                break
        if chosen is not None:
            # Defense-in-depth (I1): levanta AntiLeakageError se a escolha for futura.
            self._policy.validate_not_future(_effective_date(chosen), day)
        return chosen

    def _build_row(self, day: date, match: Row | None) -> Row:
        """Monta a `Row` de saída (campos + auditoria + 3 ratios; `None` se vazio, C4)."""
        row: dict[str, object] = {"day": day}
        if match is None:
            row["fundamentals_effective_date"] = None
            for field_name in _FUNDAMENTAL_FIELDS:
                row[field_name] = None
            row["net_margin"] = None
            row["leverage_ratio"] = None
            row["cashflow_efficiency"] = None
            return row

        row["fundamentals_effective_date"] = _effective_date(match)
        for field_name in _FUNDAMENTAL_FIELDS:
            row[field_name] = match.get(field_name)
        revenue = _as_float(match.get("revenue"))
        net_income = _as_float(match.get("net_income"))
        operating_cash_flow = _as_float(match.get("operating_cash_flow"))
        equity = _as_float(match.get("total_shareholder_equity"))
        liabilities = _as_float(match.get("total_liabilities"))
        row["net_margin"] = self._policy.net_margin(net_income, revenue)
        row["leverage_ratio"] = self._policy.leverage_ratio(liabilities, equity)
        row["cashflow_efficiency"] = self._policy.cashflow_efficiency(operating_cash_flow, revenue)
        return row


def _effective_date(report: Row) -> date:
    """Extrai o `effective_date` (uma `date`) de um report de entrada."""
    value = report["effective_date"]
    if not isinstance(value, date):
        raise TypeError("report['effective_date'] must be a date")
    return value


def _as_float(value: object) -> float | None:
    """Coage para `float | None` (campos fundamentais são numéricos ou `None`)."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
