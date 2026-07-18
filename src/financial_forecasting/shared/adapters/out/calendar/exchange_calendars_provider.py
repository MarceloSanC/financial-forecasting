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
- **bounds explícitos SEMPRE** (a janela pedida manda, nunca a conveniência da
  lib): o calendário default tem bounds MÓVEIS (~hoje-20a .. hoje+1a) e não
  serve a janela ampla FIXA do wiring do `WalkForwardSplitter` (Stage 5.2
  Task 09, decisão F-T1 opção A: 1990-01-01..2035-12-31). O adapter deriva os
  bounds da própria janela, **ano-quantizados** com folga de 1 ano por ponta —
  sem sondar o calendário default: o cache da lib é single-slot por bolsa, e a
  sonda o derrubaria a cada chamada (~1.1s de rebuild por chamada). Com bounds
  quantizados, chamadas repetidas com janelas nos MESMOS anos reusam o
  calendário cacheado (a 2ª chamada custa < 50ms).

O calendário é instanciado **dentro do método** (não no import do módulo): manter
o adapter barato de importar evita carregar a lib pesada na construção do grafo de
dependências (concept §10 / technical §5).
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

        `start > end` → `ValueError` (C5). O calendário é obtido SEMPRE com
        bounds explícitos derivados da janela pedida (ano-quantizados, folga de
        1 ano por ponta) — sem sondar o calendário default da lib. Converte
        cada sessão da lib para `date` puro na fronteira; o VO valida
        ordenação/duplicatas.
        """
        if start > end:
            raise ValueError(f"start ({start.isoformat()}) must be <= end ({end.isoformat()})")
        # Bounds ano-quantizados derivados da janela (NUNCA o calendário default,
        # cujos bounds são móveis e cuja sonda derrubaria o cache single-slot da
        # lib): janelas nos mesmos anos compartilham o mesmo calendário cacheado;
        # a folga de 1 ano por ponta garante calendário nunca-vazio (janela
        # legítima sem sessões devolve VO vazio pelo clamp abaixo, não erro).
        calendar = xcals.get_calendar(
            self._exchange,
            start=date(start.year - 1, 1, 1),
            end=date(end.year + 1, 12, 31),
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
