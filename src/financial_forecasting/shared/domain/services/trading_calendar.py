"""Serviço de domínio `TradingCalendar` — aritmética de pregão sobre sessões.

Domínio puro (stdlib-only: `datetime`, `bisect`, `dataclasses` via o VO). Opera
**só** sobre um VO `TradingSessions` injetado (ADR 2.4.0001): mapeia um timestamp
ao dia de pregão a que pertence (`trading_day_from_timestamp`), testa se uma data
é sessão (`is_session`), caminha para a próxima/anterior sessão
(`next_session`/`prev_session`) e — na Task 03 — desloca por N pregões
(`shift_trading_days`). Nenhum import de `application`/`adapters` nem de lib
externa: a direção inward-only é satisfeita estruturalmente, não por
`TYPE_CHECKING` (ADR 2.4.0001 §Decision).

Semântica de fronteira (concept §6):

- **`trading_day_from_timestamp` (I5/C1/A3/A4).** `ts` naive → `ValueError`
  (timezone-aware obrigatório); normaliza com `astimezone(UTC)`; a base é
  `ts_utc.date()`. Se `ts_utc.time() > close_hour` **ou** a base não é sessão,
  rola para a **próxima sessão** (não o próximo dia civil — replica a intenção do
  old `trading_day_from_timestamp`, trocando o roll de fim-de-semana por feriados
  reais XNYS).
- **Janela insuficiente (C2/D5).** Um lookup/offset cujo resultado cairia além de
  `[start, end]` da janela materializada levanta `ValueError` — sem clamp. O
  caller deve materializar uma janela larga o bastante.
"""

from __future__ import annotations

import bisect
from datetime import UTC, date, datetime, time
from typing import Literal

from financial_forecasting.shared.domain.value_objects.trading_sessions import (
    TradingSessions,
)

Direction = Literal["forward", "backward"]
"""Sentido do deslocamento de pregões: `"forward"` (futuro) ou `"backward"` (passado)."""


class TradingCalendar:
    """Aritmética de dias de pregão sobre um VO `TradingSessions` injetado."""

    def __init__(self, sessions: TradingSessions) -> None:
        self._sessions = sessions

    def is_session(self, day: date) -> bool:
        """`True` se `day` é uma sessão de pregão (delega o membership ao VO)."""
        return self._sessions.contains(day)

    def next_session(self, day: date) -> date:
        """Menor sessão estritamente maior que `day`.

        `ValueError` (C2/D5) se não houver sessão após `day` dentro da janela
        materializada (estouro de janela — sem clamp).
        """
        days = self._sessions.sessions
        index = bisect.bisect_right(days, day)
        if index >= len(days):
            raise ValueError(
                f"No trading session after {day.isoformat()} within the materialized "
                "window; widen the [start, end] range"
            )
        return days[index]

    def prev_session(self, day: date) -> date:
        """Maior sessão estritamente menor que `day`.

        `ValueError` (C2/D5) se não houver sessão antes de `day` dentro da janela
        materializada (estouro de janela — sem clamp).
        """
        days = self._sessions.sessions
        index = bisect.bisect_left(days, day)
        if index == 0:
            raise ValueError(
                f"No trading session before {day.isoformat()} within the materialized "
                "window; widen the [start, end] range"
            )
        return days[index - 1]

    def trading_day_from_timestamp(self, ts: datetime, close_hour: time) -> date:
        """Mapeia `ts` ao dia de pregão a que o registro pertence.

        `ts` deve ser timezone-aware (naive → `ValueError`, I5/C1). Normaliza para
        UTC; a base é `ts_utc.date()`. Se o horário passou de `close_hour` **ou** a
        base não é sessão, rola para a próxima sessão (A3/A4). Estouro de janela →
        `ValueError` (C2/D5).
        """
        if ts.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware for trading-day normalization")
        ts_utc = ts.astimezone(UTC)
        base = ts_utc.date()
        if ts_utc.time() > close_hour or not self.is_session(base):
            return self.next_session(base)
        return base

    def shift_trading_days(
        self,
        day: date,
        n: int,
        *,
        direction: Direction = "forward",
    ) -> date:
        """Desloca `n` pregões a partir de `day`, no sentido `direction`.

        Usado pelo embargo/purga do walk-forward (Stage 5.1), que precisa de
        deslocamento em **ambas** as direções — por isso o sentido é explícito e
        não herda o roll-forward-only do old (ADR 2.4.0001 §Implementation).

        Regras (concept §6 I6/C2/C3/D5):

        - `n < 0` → `ValueError` (C3): o sinal não expressa direção; use
          `direction`. A magnitude é sempre não-negativa.
        - `n == 0` ancora: retorna `day` se for sessão; caso contrário, a primeira
          sessão no sentido `direction` (próxima se `forward`, anterior se
          `backward`).
        - `n > 0`: avança/recua `n` pregões reusando `next_session`/`prev_session`,
          pulando feriados e fins de semana (I6/A6).
        - Resultado além de `[start, end]` → `ValueError` (C2/D5), propagado dos
          lookups — sem clamp.
        """
        if n < 0:
            raise ValueError(
                f"shift_trading_days magnitude must be non-negative; got n={n}. "
                "Use direction='backward' to go to the past."
            )
        step = self.next_session if direction == "forward" else self.prev_session
        current = day if self.is_session(day) else step(day)
        for _ in range(n):
            current = step(current)
        return current
