"""Fixtures compartilhadas dos testes dos escritores silver da Stage 7.3 (achado C4-8).

`CountingRepository` conta as escritas (prova "uma escrita por run"); `TIMESTAMPS` é a
grade de pregão sintética que cruza a virada de ano, e `LEVELS` a grade de quantis.
"""

from __future__ import annotations

from typing import Any

from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
    FakeAnalyticsRepository,
)
from tests.fakes.shared.in_memory_clock import FakeClock

LEVELS = (0.1, 0.5, 0.9)
# Grade de pregão sintética (ISO UTC). Os índices 3/4 cruzam a virada de ano.
TIMESTAMPS = (
    "2024-12-26T00:00:00+00:00",
    "2024-12-27T00:00:00+00:00",
    "2024-12-30T00:00:00+00:00",
    "2024-12-31T00:00:00+00:00",
    "2025-01-02T00:00:00+00:00",
    "2025-01-03T00:00:00+00:00",
    "2025-01-06T00:00:00+00:00",
    "2025-01-07T00:00:00+00:00",
)


class CountingRepository(FakeAnalyticsRepository):
    """O `FakeAnalyticsRepository` que registra `(tabela, linhas)` de cada `write`."""

    def __init__(self) -> None:
        super().__init__(clock=FakeClock())
        self.writes: list[tuple[str, int]] = []

    def write(self, *, layer: str, table: str, rows: Any, allow_upsert: bool = False) -> Any:  # noqa: ANN401
        self.writes.append((table, len(rows)))
        return super().write(layer=layer, table=table, rows=rows, allow_upsert=allow_upsert)
