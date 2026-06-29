"""Value object `TradingSessions` — conjunto materializado de dias de pregão.

Frozen, domínio puro (stdlib-only: `dataclasses`, `datetime`, `bisect`). Materializa
a sequência ordenada, imutável e sem duplicatas das datas de sessão de uma bolsa
(XNYS, no piloto) para uma janela fechada `[start, end]`. É o **objeto de
fronteira** do ADR 2.4.0001 (e da postura "boundary = value object" do ADR
0.0.0020): a aplicação carrega as sessões via `ExchangeCalendarProvider` e injeta
este VO no serviço de domínio `TradingCalendar`, que opera só sobre ele — nenhum
tipo de `exchange-calendars`/`pandas` cruza para o domínio.

Invariantes (concept §6 I7/A1, C4):

- **Ordenado estritamente crescente, sem duplicatas.** Construir com sessões
  desordenadas ou repetidas é `ValueError` (C4) — a invariante é verificada na
  construção, não assumida.
- **Imutável (frozen).** `sessions` é uma `tuple[date, ...]`; o VO não pode ser
  mutado após criado.
- **Membership O(log n).** `contains` usa `bisect` sobre a tupla ordenada.

A `close_hour` (política intraday) **não** vive aqui — é passada por chamada a
`trading_day_from_timestamp`. Este VO é o *conjunto de sessões*, não a política de
pregão (ADR 2.4.0001 §Neutral).
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class TradingSessions:
    """Conjunto ordenado e imutável de dias de pregão de uma janela `[start, end]`.

    Attributes:
        sessions: tupla de `date` estritamente crescente, sem duplicatas.
    """

    sessions: tuple[date, ...]

    def __post_init__(self) -> None:
        """Valida ordenação estritamente crescente e ausência de duplicatas (C4)."""
        previous: date | None = None
        for current in self.sessions:
            if previous is not None and current <= previous:
                raise ValueError(
                    "TradingSessions must be strictly increasing without duplicates; "
                    f"got {previous.isoformat()} followed by {current.isoformat()}"
                )
            previous = current

    @property
    def start(self) -> date:
        """Primeira sessão da janela. `ValueError` se o VO for vazio."""
        if not self.sessions:
            raise ValueError("TradingSessions is empty; no start session")
        return self.sessions[0]

    @property
    def end(self) -> date:
        """Última sessão da janela. `ValueError` se o VO for vazio."""
        if not self.sessions:
            raise ValueError("TradingSessions is empty; no end session")
        return self.sessions[-1]

    def contains(self, day: date) -> bool:
        """`True` se `day` é uma sessão de pregão (membership O(log n) via `bisect`)."""
        index = bisect.bisect_left(self.sessions, day)
        return index < len(self.sessions) and self.sessions[index] == day

    def in_window(self, day: date) -> bool:
        """`True` se `day` está dentro de `[start, end]` (independe de ser sessão)."""
        if not self.sessions:
            return False
        return self.start <= day <= self.end
