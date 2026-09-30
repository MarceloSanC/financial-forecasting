"""Fake do port `GoldGenerationReader` — lê a geração viva de um `InMemoryGoldStore`.

`read_generation` pega `store.current(partition)` (ausente →
`GoldManifestNotFoundError`, como o real) e monta a geração pelo mesmo dono do real,
`GoldGeneration.from_stored` — nenhuma montagem própria (ADR 6.5.0005 item 5).
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldManifestNotFoundError,
    GoldPartition,
)
from tests.fakes.features.evaluation.in_memory_gold_store import InMemoryGoldStore


class InMemoryGoldGenerationReader:
    """Satisfaz `GoldGenerationReader` sobre um `InMemoryGoldStore`."""

    def __init__(self, store: InMemoryGoldStore) -> None:
        self._store = store
        self.reads: list[GoldPartition] = []

    def read_generation(self, *, partition: GoldPartition) -> GoldGeneration:
        """A geração viva da partição, montada por `GoldGeneration.from_stored`."""
        self.reads.append(partition)
        generation = self._store.current(partition)
        if generation is None:
            raise GoldManifestNotFoundError(f"no gold generation for {partition}")
        manifest, rows_by_table = generation
        return GoldGeneration.from_stored(manifest, rows_by_table)
