"""Fake do port `Clock` — instante fixo injetável, NÃO um mock.

`FakeClock` honra a MESMA semântica observável do `SystemClock`: `now()` devolve
um `datetime` timezone-aware em UTC, não-decrescente entre chamadas (aqui, sempre
o mesmo instante). Isso torna determinístico o que depende do tempo, como o
`created_at_utc` write-time de `dim_run` (ADR 4.2.0002). A paridade fake↔real é
provada em `tests/contract/shared/test_clock_contract.py` (`[fake, real]`).

Um instante ingênuo ou fora de UTC é recusado na construção: o fake não pode
aceitar o que o contrato do port proíbe, senão o teste que o usa passa com um
`created_at_utc` que o adapter real nunca produziria.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# Instante default dos testes (o mesmo que os clocks ad hoc anteriores fixavam).
FIXED_NOW = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)


class FakeClock:
    """Clock que devolve sempre o instante injetado (UTC-aware)."""

    def __init__(self, now: datetime = FIXED_NOW) -> None:
        if now.utcoffset() != timedelta(0):
            raise ValueError(f"FakeClock requires a timezone-aware UTC instant, got {now!r}")
        self._now = now

    def now(self) -> datetime:
        """Devolve o instante injetado."""
        return self._now
