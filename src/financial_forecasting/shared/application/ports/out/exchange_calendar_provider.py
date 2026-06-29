"""Port compartilhado: `ExchangeCalendarProvider`.

Abstrai a materialização das sessões de pregão de uma bolsa (XNYS, no piloto)
para uma janela fechada `[start, end]`, devolvendo o VO de domínio
`TradingSessions`. A aplicação carrega as sessões por este port e **injeta** o VO
no serviço de domínio `TradingCalendar` (ADR 2.4.0001): o domínio nunca importa
este port nem a lib de calendário — a direção inward-only fica intacta.

A camada `application` depende APENAS deste `Protocol` estrutural; ela importa o
VO de `shared/domain/value_objects` (direção para dentro é permitida), mas
**nunca** `exchange-calendars`/`pandas`/`numpy` (I3/A7). A tradução para a lib
concreta (`exchange_calendars.get_calendar("XNYS")`) e a conversão de cada sessão
para `date` puro vivem só no adapter `ExchangeCalendarsProvider`
(`shared/adapters/out/calendar/`). O contrato `import-linter`
`calendar-no-exchange-calendars-leak` reprova se a lib vazar para cá.

Semântica garantida por qualquer implementação deste contrato:

- **`sessions(start, end)` materializa a janela fechada (I8/A9).** Devolve um
  `TradingSessions` com as sessões `start <= s <= end`, ordenado e sem
  duplicatas (invariante do VO). Feriados XNYS conhecidos (ex.: `2023-07-04`,
  `2023-11-23`, `2023-12-25`) e fins de semana **não** aparecem.
- **`start > end` é erro de chamada (C5).** Levanta `ValueError` — uma janela
  invertida não tem sessões e é defeito do chamador, não janela vazia legítima.
- **Janela sem sessões (ex.: só um feriado) devolve VO vazio**, não erro.

Espelha a forma de `medallion_store.py`/`experiment_tracker.py` (Protocol
estrutural, sem ABC, sem vazar lib). Ver ADR
docs/adr/2_4_0001-trading-calendar-domain-over-materialized-sessions-vo.md.
"""

from datetime import date
from typing import Protocol

from financial_forecasting.shared.domain.value_objects.trading_sessions import (
    TradingSessions,
)


class ExchangeCalendarProvider(Protocol):
    """Contrato de materialização de sessões de pregão, sem vazar a lib de calendário."""

    def sessions(self, *, start: date, end: date) -> TradingSessions:
        """Materializa as sessões de pregão da janela fechada `[start, end]`.

        Devolve um `TradingSessions` ordenado/sem duplicatas com as sessões da
        janela (feriados/fins de semana ausentes, I8/A9). `start > end` levanta
        `ValueError` (C5); uma janela legítima sem sessões devolve VO vazio.
        """
        ...
