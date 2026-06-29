"""Testes do serviço de domínio `TradingCalendar` (Tasks 02 e 03).

Fixtures de sessões NYSE 2023 conhecidas (com feriados reais ausentes), sobre as
quais o serviço é validado deterministicamente (I4/A5). Os feriados-âncora usados:

- 2023-07-04 (Independence Day) — NÃO é sessão; 2023-07-03 e 2023-07-05 são.
- 2023-11-23 (Thanksgiving) — NÃO é sessão; 2023-11-22 e 2023-11-24 são.
- 2023-12-25 (Christmas) — NÃO é sessão; 2023-12-22 e 2023-12-26 são.
- fins de semana (sábado/domingo) ausentes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from financial_forecasting.shared.domain.services.trading_calendar import (
    TradingCalendar,
)
from financial_forecasting.shared.domain.value_objects.trading_sessions import (
    TradingSessions,
)

# Sessões NYSE reais ao redor do feriado de Thanksgiving 2023 (qui 23/11 ausente):
#   seg 20, ter 21, qua 22, [qui 23 feriado], sex 24, seg 27, ter 28
_THANKSGIVING_WEEK = (
    date(2023, 11, 20),
    date(2023, 11, 21),
    date(2023, 11, 22),
    date(2023, 11, 24),
    date(2023, 11, 27),
    date(2023, 11, 28),
)

# Sessões reais ao redor do 4 de julho 2023 (ter 04/07 ausente):
#   sex 30/06, seg 03/07, [ter 04 feriado], qua 05, qui 06, sex 07
_JULY_FOURTH_WEEK = (
    date(2023, 6, 30),
    date(2023, 7, 3),
    date(2023, 7, 5),
    date(2023, 7, 6),
    date(2023, 7, 7),
)

# Sessões reais ao redor do Natal 2023 (seg 25/12 ausente):
#   sex 22/12, [seg 25 feriado], ter 26, qua 27, qui 28, sex 29
_CHRISTMAS_WEEK = (
    date(2023, 12, 22),
    date(2023, 12, 26),
    date(2023, 12, 27),
    date(2023, 12, 28),
    date(2023, 12, 29),
)

_ALL_SESSIONS = TradingSessions(
    sessions=tuple(sorted(set(_JULY_FOURTH_WEEK + _THANKSGIVING_WEEK + _CHRISTMAS_WEEK)))
)

_MARKET_CLOSE = time(21, 0)  # ~16:00 ET ≈ 21:00 UTC; usada como close_hour de teste


def _calendar() -> TradingCalendar:
    return TradingCalendar(_ALL_SESSIONS)


# --- is_session ------------------------------------------------------------


def test_is_session_true_on_trading_day() -> None:
    assert _calendar().is_session(date(2023, 11, 24)) is True


def test_is_session_false_on_holiday() -> None:
    # Thanksgiving (feriado), 4 de julho, Natal: nenhum é sessão.
    cal = _calendar()
    assert cal.is_session(date(2023, 11, 23)) is False
    assert cal.is_session(date(2023, 7, 4)) is False
    assert cal.is_session(date(2023, 12, 25)) is False


def test_is_session_false_on_weekend() -> None:
    # sábado 2023-11-25 e domingo 2023-11-26 não são sessões.
    cal = _calendar()
    assert cal.is_session(date(2023, 11, 25)) is False
    assert cal.is_session(date(2023, 11, 26)) is False


# --- next_session / prev_session -------------------------------------------


def test_next_session_skips_holiday() -> None:
    # Quarta 22/11 -> próxima sessão pula o feriado de quinta (23) e o fato de
    # sexta (24) ser a próxima sessão real.
    assert _calendar().next_session(date(2023, 11, 22)) == date(2023, 11, 24)


def test_next_session_skips_weekend() -> None:
    # Sexta 24/11 -> próxima sessão pula sáb/dom para segunda 27.
    assert _calendar().next_session(date(2023, 11, 24)) == date(2023, 11, 27)


def test_next_session_from_holiday_itself() -> None:
    # A partir do próprio 4 de julho (não-sessão) -> 5 de julho.
    assert _calendar().next_session(date(2023, 7, 4)) == date(2023, 7, 5)


def test_prev_session_skips_holiday() -> None:
    # Sexta 24/11 -> sessão anterior pula o feriado de quinta (23) para quarta 22.
    assert _calendar().prev_session(date(2023, 11, 24)) == date(2023, 11, 22)


def test_prev_session_skips_weekend() -> None:
    # Segunda 27/11 -> sessão anterior pula sáb/dom para sexta 24.
    assert _calendar().prev_session(date(2023, 11, 27)) == date(2023, 11, 24)


def test_next_session_overflow_raises() -> None:
    # Última sessão da janela: não há próxima -> ValueError (sem clamp, C2/D5).
    with pytest.raises(ValueError, match="No trading session after"):
        _calendar().next_session(date(2023, 12, 29))


def test_prev_session_overflow_raises() -> None:
    # Primeira sessão da janela: não há anterior -> ValueError (C2/D5).
    with pytest.raises(ValueError, match="No trading session before"):
        _calendar().prev_session(date(2023, 6, 30))


# --- trading_day_from_timestamp --------------------------------------------


def test_trading_day_naive_timestamp_raises() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _calendar().trading_day_from_timestamp(datetime(2023, 11, 24, 10, 0), _MARKET_CLOSE)


def test_trading_day_before_close_is_same_session() -> None:
    # Sexta 24/11 às 15:00 UTC (antes do close 21:00) e é sessão -> mesmo dia.
    ts = datetime(2023, 11, 24, 15, 0, tzinfo=UTC)
    assert _calendar().trading_day_from_timestamp(ts, _MARKET_CLOSE) == date(2023, 11, 24)


def test_trading_day_after_close_rolls_to_next_session() -> None:
    # Sexta 24/11 às 22:00 UTC (após close) -> próxima sessão = segunda 27.
    ts = datetime(2023, 11, 24, 22, 0, tzinfo=UTC)
    assert _calendar().trading_day_from_timestamp(ts, _MARKET_CLOSE) == date(2023, 11, 27)


def test_trading_day_on_non_session_rolls_to_next() -> None:
    # Sábado 25/11 às 10:00 (não-sessão, antes do close) -> próxima sessão = 27.
    ts = datetime(2023, 11, 25, 10, 0, tzinfo=UTC)
    assert _calendar().trading_day_from_timestamp(ts, _MARKET_CLOSE) == date(2023, 11, 27)


def test_trading_day_on_holiday_rolls_to_next() -> None:
    # 4 de julho (feriado) às 10:00 -> próxima sessão = 5 de julho.
    ts = datetime(2023, 7, 4, 10, 0, tzinfo=UTC)
    assert _calendar().trading_day_from_timestamp(ts, _MARKET_CLOSE) == date(2023, 7, 5)


def test_trading_day_friday_after_close_into_holiday_monday() -> None:
    # Fixture do old (A4): sexta após o close -> próxima sessão. Aqui a "segunda"
    # seguinte é feriado de Natal (25/12), então rola para terça 26/12.
    ts = datetime(2023, 12, 22, 22, 0, tzinfo=UTC)
    assert _calendar().trading_day_from_timestamp(ts, _MARKET_CLOSE) == date(2023, 12, 26)


def test_trading_day_after_close_overflow_raises() -> None:
    # Última sessão (29/12) após o close: não há próxima sessão -> ValueError.
    ts = datetime(2023, 12, 29, 22, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="No trading session after"):
        _calendar().trading_day_from_timestamp(ts, _MARKET_CLOSE)
