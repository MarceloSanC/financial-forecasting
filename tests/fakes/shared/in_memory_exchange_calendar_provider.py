"""Fake in-memory do port `ExchangeCalendarProvider` — NÃO um mock.

`FakeExchangeCalendarProvider` aplica a MESMA semântica observável do adapter real
(`ExchangeCalendarsProvider`): materializa as sessões XNYS de uma janela fechada
`[start, end]` como um `TradingSessions` ordenado/sem duplicatas, omitindo feriados
e fins de semana; `start > end` levanta `ValueError` (C5). Mantém um conjunto de
sessões pré-construído em memória (não asserts de chamada).

O conjunto de sessões é derivado deterministicamente dos dias úteis de 2023 MENOS
os feriados de fechamento total do NYSE em 2023 — exatamente o que o
`exchange_calendars` retorna para `XNYS` nesse ano. Isso garante paridade
fake↔real no MESMO contract test
(`tests/contract/shared/test_exchange_calendar_provider_contract.py`),
parametrizado sobre `[fake, real]` a partir da Task 07. O fake é stdlib-only
(vive em `tests/`, fora do gate, mas mantém o contrato agnóstico de
`exchange-calendars`/`pandas`).
"""

from __future__ import annotations

from datetime import date, timedelta

from financial_forecasting.shared.domain.value_objects.trading_sessions import (
    TradingSessions,
)

# Feriados de fechamento TOTAL do NYSE/XNYS em 2023 (não são sessões). Não inclui
# early closes (3 jul, 24 nov, 22 dez): nesses dias o pregão abre, então são
# sessões. Fonte: calendário oficial NYSE 2023 (replicado pelo exchange_calendars).
_NYSE_2023_HOLIDAYS: frozenset[date] = frozenset(
    {
        date(2023, 1, 2),  # New Year's Day (observed)
        date(2023, 1, 16),  # Martin Luther King Jr. Day
        date(2023, 2, 20),  # Washington's Birthday
        date(2023, 4, 7),  # Good Friday
        date(2023, 5, 29),  # Memorial Day
        date(2023, 6, 19),  # Juneteenth
        date(2023, 7, 4),  # Independence Day
        date(2023, 9, 4),  # Labor Day
        date(2023, 11, 23),  # Thanksgiving Day
        date(2023, 12, 25),  # Christmas Day
    }
)

_SATURDAY = 5  # date.weekday(): 0=segunda ... 5=sábado, 6=domingo


def _nyse_2023_sessions() -> tuple[date, ...]:
    """Dias úteis de 2023 (seg-sex) menos os feriados de fechamento total do NYSE."""
    sessions: list[date] = []
    cursor = date(2023, 1, 1)
    end = date(2023, 12, 31)
    one_day = timedelta(days=1)
    while cursor <= end:
        is_weekday = cursor.weekday() < _SATURDAY
        if is_weekday and cursor not in _NYSE_2023_HOLIDAYS:
            sessions.append(cursor)
        cursor += one_day
    return tuple(sessions)


class FakeExchangeCalendarProvider:
    """Implementação in-memory determinística do contrato `ExchangeCalendarProvider`."""

    def __init__(self, sessions: tuple[date, ...] | None = None) -> None:
        # Conjunto-base de sessões; default = ano XNYS 2023 completo (paridade real).
        self._all_sessions: tuple[date, ...] = (
            sessions if sessions is not None else _nyse_2023_sessions()
        )

    def sessions(self, *, start: date, end: date) -> TradingSessions:
        """Recorta a janela fechada `[start, end]` (ver port). `start>end` → erro."""
        if start > end:
            raise ValueError(f"start ({start.isoformat()}) must be <= end ({end.isoformat()})")
        window = tuple(s for s in self._all_sessions if start <= s <= end)
        return TradingSessions(sessions=window)
