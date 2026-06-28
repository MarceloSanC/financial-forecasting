"""Implementação concreta do port Clock usando o relógio do sistema.

SystemClock satisfaz o Protocol Clock sem herança explícita (duck typing).
Sempre retorna datetime com timezone UTC para evitar ambiguidades entre
ambientes com fusos horários diferentes. Nunca use datetime.now() sem tz
em código de produção — sempre use datetime.UTC ou um Clock injetado.
"""

from datetime import UTC, datetime


class SystemClock:
    """Clock que retorna o timestamp atual do sistema em UTC."""

    def now(self) -> datetime:
        """Retorna datetime.now(UTC) com timezone-aware."""
        return datetime.now(tz=UTC)
