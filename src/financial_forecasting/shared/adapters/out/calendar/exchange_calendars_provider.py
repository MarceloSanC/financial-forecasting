"""Adapter `ExchangeCalendarsProvider` — implementação do port `ExchangeCalendarProvider`.

Único lugar que importa `exchange_calendars` (e, transitivamente, `pandas`/
`numpy`); o gate `import-linter` `calendar-no-exchange-calendars-leak` reprova se
a lib vazar para `application`/`domain` (I3/A8). Implementa o contrato sobre o
calendário XNYS (NYSE) — a fonte validada de sessões e feriados reais, em lugar
do roll de fim-de-semana sem feriados do repo antigo (ADR 2.4.0001 §D).

`sessions(start, end)`:

- `start > end` → `ValueError` (C5), antes de tocar a lib.
- consulta `get_calendar("XNYS").sessions_in_range(start, end)` (um
  `DatetimeIndex` de sessões), **converte cada sessão para `date` puro** na
  fronteira do método (sem deixar `pd.Timestamp`/`numpy` escapar) e materializa
  um `TradingSessions` ordenado/sem duplicatas (invariante do VO).
- **janela além dos bounds default da lib** (o calendário default cobre
  ~hoje-20a .. hoje+1a): materializa um calendário com bounds explícitos
  cobrindo a união da janela pedida com os bounds default — a janela pedida
  manda, nunca a conveniência da lib. Necessário para a janela ampla FIXA do
  wiring do `WalkForwardSplitter` (Stage 5.2 Task 09, decisão F-T1 opção A:
  1990-01-01..2035-12-31), que um calendário default não consegue servir.
  `get_calendar` cacheia por (nome, bounds); o custo (~0.7s p/ 46 anos) é pago
  uma vez por processo.

O calendário é instanciado **dentro do método** (não no import do módulo): manter
o adapter barato de importar evita carregar a lib pesada na construção do grafo de
dependências (concept §10 / technical §5). O resultado de `get_calendar` é
cacheado pela própria lib, então chamadas repetidas não recustam.
"""

from __future__ import annotations

from datetime import date

import exchange_calendars as xcals

from financial_forecasting.shared.domain.value_objects.trading_sessions import (
    TradingSessions,
)

_XNYS = "XNYS"  # ISO-10383 MIC do NYSE (New York Stock Exchange)


class ExchangeCalendarsProvider:
    """Materializa sessões XNYS via `exchange-calendars`, devolvendo o VO de domínio."""

    def __init__(self, exchange: str = _XNYS) -> None:
        # MIC do calendário; default XNYS (NYSE). Injetável para multi-asset futuro.
        self._exchange = exchange

    def sessions(self, *, start: date, end: date) -> TradingSessions:
        """Materializa as sessões da janela fechada `[start, end]` (ver port).

        `start > end` → `ValueError` (C5). Janela além dos bounds default da lib
        → calendário com bounds explícitos (união da janela com os bounds default), sem
        perder sessão alguma da janela pedida. Converte cada sessão da lib para
        `date` puro na fronteira; o VO valida ordenação/duplicatas.
        """
        if start > end:
            raise ValueError(f"start ({start.isoformat()}) must be <= end ({end.isoformat()})")
        calendar = xcals.get_calendar(self._exchange)
        if start < calendar.first_session.date() or end > calendar.last_session.date():
            # Janela pedida excede os bounds default (~hoje-20a .. hoje+1a):
            # materializa um calendário com bounds explícitos cobrindo a UNIÃO
            # (janela + default) — assim o ramo nunca produz calendário sem
            # sessões (janela legítima sem sessões segue devolvendo VO vazio).
            calendar = xcals.get_calendar(
                self._exchange,
                start=min(start, calendar.first_session.date()),
                end=max(end, calendar.last_session.date()),
            )
        # `sessions_in_range` exige endpoints dentro de [first_session,
        # last_session]; o clamp descarta apenas dias SEM sessão nas bordas da
        # janela (a primeira/última sessão dentro dela permanece).
        query_start = max(start, calendar.first_session.date())
        query_end = min(end, calendar.last_session.date())
        if query_start > query_end:
            return TradingSessions(sessions=())
        index = calendar.sessions_in_range(query_start, query_end)
        days = tuple(session.date() for session in index)
        return TradingSessions(sessions=days)
