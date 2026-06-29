"""Unit da `FundamentalsAsofPolicy` — effective_date + invariante + 3 ratios.

Cobre os critérios de aceite A1/A2/A3 (concept 3.3 §11):

- A1: `effective_date` usa `reported_date` quando presente; senão `fiscal_date_end +
  45d` calendário (teste-oráculo `Fri 2023-12-01 → Mon 2024-01-15`, sem roll — I2).
- A2: `validate_not_future` levanta `AntiLeakageError` (subclasse de `DomainError`)
  para `>`; `==` e `<` não levantam; mensagem cita dia, effective_date e o ADR (I1).
- A3: os 3 ratios point-in-time com divisão segura (numerador `None`/`NaN` ou
  denominador `None`/`0`/`NaN` → `None`); sem YoY (I4/I9).

Stdlib-only: o teste e o módulo sob teste não importam `pandas`/`duckdb`.
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from financial_forecasting.features.feature_engineering.domain.services.fundamentals_asof_policy import (  # noqa: E501
    FUNDAMENTALS_FALLBACK_DAYS,
    AntiLeakageError,
    FundamentalsAsofPolicy,
)
from financial_forecasting.features.market_data.domain.entities.fundamental_report import (
    FundamentalReport,
)
from financial_forecasting.shared.domain.exceptions.base import DomainError


def _report(**overrides: object) -> FundamentalReport:
    """Constrói um `FundamentalReport` válido; `overrides` sobrescreve campos."""
    kwargs: dict[str, object] = {
        "asset_id": "AAPL",
        "report_type": "quarterly",
        "fiscal_date_end": date(2023, 9, 30),
        "reported_date": date(2023, 11, 2),
        "revenue": 1_000.0,
        "net_income": 200.0,
        "operating_cash_flow": 300.0,
        "total_shareholder_equity": 500.0,
        "total_liabilities": 250.0,
        "source": "unit-test",
    }
    kwargs.update(overrides)
    return FundamentalReport(**kwargs)  # type: ignore[arg-type]


# --- A1: effective_date -------------------------------------------------------


@pytest.mark.unit
def test_effective_date_uses_reported_date_when_present() -> None:
    """`reported_date` presente → usado diretamente (sem fallback)."""
    policy = FundamentalsAsofPolicy()
    report = _report(reported_date=date(2023, 11, 2))
    assert policy.effective_date(report) == date(2023, 11, 2)


@pytest.mark.unit
def test_effective_date_fallback_45_calendar_days_oracle() -> None:
    """Oráculo do old: `Fri 2023-12-01 + 45d = Mon 2024-01-15` (calendário, sem roll)."""
    policy = FundamentalsAsofPolicy()
    report = _report(fiscal_date_end=date(2023, 12, 1), reported_date=None)
    assert policy.effective_date(report) == date(2024, 1, 15)


@pytest.mark.unit
def test_fallback_constant_is_45_calendar_days() -> None:
    """A constante do fallback é 45 dias calendário (ledger H-3, pré-registrada)."""
    assert FUNDAMENTALS_FALLBACK_DAYS == 45  # noqa: PLR2004 — H-3 pré-registrada (45d calendário)


# --- A2: validate_not_future (invariante anti-leakage I1) ---------------------


@pytest.mark.unit
def test_validate_not_future_raises_for_future_effective_date() -> None:
    """`effective_date > sample_date` → `AntiLeakageError` (I1/C1)."""
    policy = FundamentalsAsofPolicy()
    with pytest.raises(AntiLeakageError):
        policy.validate_not_future(date(2024, 1, 16), date(2024, 1, 15))


@pytest.mark.unit
def test_anti_leakage_error_is_domain_error() -> None:
    """`AntiLeakageError` é subclasse de `DomainError` (erro nomeável, D4)."""
    assert issubclass(AntiLeakageError, DomainError)
    policy = FundamentalsAsofPolicy()
    with pytest.raises(DomainError):
        policy.validate_not_future(date(2024, 1, 16), date(2024, 1, 15))


@pytest.mark.unit
def test_validate_not_future_allows_equal_and_past() -> None:
    """`effective_date == sample_date` e `< sample_date` → não levantam (visível)."""
    policy = FundamentalsAsofPolicy()
    # nenhuma exceção
    policy.validate_not_future(date(2024, 1, 15), date(2024, 1, 15))
    policy.validate_not_future(date(2024, 1, 10), date(2024, 1, 15))


@pytest.mark.unit
def test_validate_not_future_message_cites_dates_and_adr() -> None:
    """A mensagem cita o dia, a effective_date e o ADR 0.0.0018 (A2)."""
    policy = FundamentalsAsofPolicy()
    with pytest.raises(AntiLeakageError) as exc:
        policy.validate_not_future(date(2024, 2, 1), date(2024, 1, 15))
    message = str(exc.value)
    assert "2024-02-01" in message
    assert "2024-01-15" in message
    assert "0.0.0018" in message


# --- A3: ratios point-in-time com divisão segura (I4/C3) ----------------------


@pytest.mark.unit
def test_ratios_compute_correctly() -> None:
    """Os 3 ratios em fixture: margin/leverage/cashflow corretos (A3)."""
    policy = FundamentalsAsofPolicy()
    assert policy.net_margin(200.0, 1_000.0) == pytest.approx(0.2)
    assert policy.leverage_ratio(250.0, 500.0) == pytest.approx(0.5)
    assert policy.cashflow_efficiency(300.0, 1_000.0) == pytest.approx(0.3)


@pytest.mark.unit
def test_net_margin_none_when_revenue_zero_or_none() -> None:
    """`revenue=0`/`None` → `net_margin None` (denominador inválido, I4/C3)."""
    policy = FundamentalsAsofPolicy()
    assert policy.net_margin(200.0, 0.0) is None
    assert policy.net_margin(200.0, None) is None


@pytest.mark.unit
def test_leverage_ratio_none_when_equity_zero() -> None:
    """`equity=0` → `leverage_ratio None` (sem `ZeroDivisionError`, I4/C3)."""
    policy = FundamentalsAsofPolicy()
    assert policy.leverage_ratio(250.0, 0.0) is None


@pytest.mark.unit
def test_ratio_none_when_numerator_none() -> None:
    """Numerador `None` → `None` (I4/C3)."""
    policy = FundamentalsAsofPolicy()
    assert policy.net_margin(None, 1_000.0) is None
    assert policy.cashflow_efficiency(None, 1_000.0) is None


@pytest.mark.unit
def test_ratio_none_when_nan_in_operand() -> None:
    """`NaN` no numerador OU denominador → `None` (não propaga `NaN`, I4/C3)."""
    policy = FundamentalsAsofPolicy()
    assert policy.net_margin(math.nan, 1_000.0) is None
    assert policy.net_margin(200.0, math.nan) is None


@pytest.mark.unit
def test_policy_exposes_no_yoy_methods() -> None:
    """3.3 só tem ratios point-in-time; YoY é deferido a 3.4/3.5 (I9/D2)."""
    assert not hasattr(FundamentalsAsofPolicy, "revenue_yoy_growth")
    assert not hasattr(FundamentalsAsofPolicy, "net_income_yoy_growth")
