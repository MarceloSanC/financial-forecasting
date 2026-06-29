"""Domain service `FundamentalsAsofPolicy` — política temporal pura do as-of.

`FundamentalsAsofPolicy` encapsula a política temporal do as-of de fundamentos do
bounded context `feature_engineering`, decomposta da lógica monolítica do old
(`build_tft_dataset_use_case.py`) nas peças hexagonais corretas (concept 3.3 §3):

- **`effective_date(report)`** — o ponto-no-tempo a partir do qual o fundamento fica
  **visível**: `report.reported_date` se presente; senão `report.fiscal_date_end +
  timedelta(days=45)` (fallback **calendário**, ledger H-3). Porta de
  `_fundamentals_to_df` (`:116-143`).
- **`validate_not_future(effective_date, sample_date)`** — o invariante
  **razão-de-ser** da Stage (anti-leakage, overview ADR 0.0.0018 regra 2): levanta
  `AntiLeakageError` se `effective_date > sample_date`. Replica o `ValueError` do old
  (`:518-535`) como erro **nomeável** de domínio (D4).
- **3 ratios point-in-time** (`net_margin`/`leverage_ratio`/`cashflow_efficiency`) com
  **divisão segura** (porta verbatim de `_safe_ratio` `:256-263`): numerador `None`
  **ou** denominador `None`/`0`/`NaN` → `None` (I4). O YoY é deferido a 3.4/3.5 (D2/ADR
  3.3.0002) por depender da grade densa.

Domínio **puro stdlib-only**: importa SÓ `datetime`/`math` (stdlib), a entity
`FundamentalReport` (cross-BC `domain` — LAYOUT §3/§7) e `DomainError`. SEM
`pandas`/`pyarrow`/`duckdb`/`torch`/`pydantic` — os gates `import-linter`
`domain-purity` + `store-no-storage-leak` reprovam qualquer vazamento (concept 3.3 I5).
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from financial_forecasting.features.market_data.domain.entities.fundamental_report import (
    FundamentalReport,
)
from financial_forecasting.shared.domain.exceptions.base import DomainError

# H-3 (ledger, FECHADA com humano, pré-registrada): fallback CALENDÁRIO (não dias
# úteis) — conservador entre os prazos SEC (10-Q 40d / 10-K 60-90d). Confirmado por
# teste-oráculo do old: `Fri 2023-12-01 + 45d = Mon 2024-01-15` (sem roll).
FUNDAMENTALS_FALLBACK_DAYS = 45


class AntiLeakageError(DomainError):
    """`effective_date` futura ao dia da amostra (overview ADR 0.0.0018 regra 2).

    Erro de domínio **nomeável** (subclasse de `DomainError`, padrão
    `NotFoundError`/`DuplicateKeyError`) para o invariante anti-leakage razão-de-ser
    da Stage (D4) — substitui o `ValueError` cru do old (`:530-535`).
    """


class FundamentalsAsofPolicy:
    """Política temporal pura do as-of de fundamentos (stdlib-only, concept 3.3 §4).

    Sem estado: pode ser instanciada uma vez e reusada. `effective_date` e
    `validate_not_future` são de instância (a policy é o objeto de domínio); os 3
    ratios são `@staticmethod` (funções puras sobre primitivos).
    """

    def effective_date(self, report: FundamentalReport) -> date:
        """`reported_date` se presente; senão `fiscal_date_end + 45d` calendário (I2).

        É o ponto-no-tempo a partir do qual o fundamento fica visível na grade. Porta
        de `_fundamentals_to_df` (`build_tft_dataset_use_case.py:116-143`).
        """
        if report.reported_date is not None:
            return report.reported_date
        return report.fiscal_date_end + timedelta(days=FUNDAMENTALS_FALLBACK_DAYS)

    def validate_not_future(self, effective_date: date, sample_date: date) -> None:
        """Levanta `AntiLeakageError` se `effective_date > sample_date` (I1/C1).

        Invariante anti-leakage NÃO-NEGOCIÁVEL (overview ADR 0.0.0018 regra 2): um
        fundamento só pode ser visível num dia se a sua `effective_date` já passou.
        `==` e `<` não levantam (visível). Sem fallback silencioso.
        """
        if effective_date > sample_date:
            raise AntiLeakageError(
                f"Anti-leakage violation: fundamentals effective_date "
                f"{effective_date.isoformat()} is posterior to sample date "
                f"{sample_date.isoformat()} (overview ADR 0.0.0018 regra 2)."
            )

    @staticmethod
    def net_margin(net_income: float | None, revenue: float | None) -> float | None:
        """`net_income / revenue` com divisão segura (I4/C3)."""
        return FundamentalsAsofPolicy._safe_ratio(net_income, revenue)

    @staticmethod
    def leverage_ratio(
        total_liabilities: float | None,
        total_shareholder_equity: float | None,
    ) -> float | None:
        """`total_liabilities / total_shareholder_equity` com divisão segura (I4/C3)."""
        return FundamentalsAsofPolicy._safe_ratio(total_liabilities, total_shareholder_equity)

    @staticmethod
    def cashflow_efficiency(
        operating_cash_flow: float | None,
        revenue: float | None,
    ) -> float | None:
        """`operating_cash_flow / revenue` com divisão segura (I4/C3)."""
        return FundamentalsAsofPolicy._safe_ratio(operating_cash_flow, revenue)

    @staticmethod
    def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
        """Divisão segura (porta verbatim de `_safe_ratio` `:256-263`).

        Numerador `None`/`NaN` **ou** denominador `None`/`0`/`NaN` → `None` (nunca
        `ZeroDivisionError`, nunca `inf`/`NaN` propagado como número válido — I4/C3).
        """
        if numerator is None or denominator is None:
            return None
        if math.isnan(numerator) or math.isnan(denominator):
            return None
        if denominator == 0:
            return None
        return numerator / denominator
