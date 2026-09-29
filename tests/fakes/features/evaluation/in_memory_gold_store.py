"""Fake do port `GoldStore` — gerações em memória, substituídas por inteiro (ADR 6.4.0005).

Guarda, por `(asset, parent_sweep_id)`, o `manifest.as_mapping()` e as linhas de cada
tabela publicada (dicts, na ordem recebida). Um `publish` troca a geração inteira da
partição — o mesmo comportamento observável do `ParquetGoldStore`, sem disco. `current`
devolve a geração viva para a suíte de contrato; `publishes` conta as chamadas. A
coerência da geração é a do dono único `check_generation` (a mesma do real).
"""

from __future__ import annotations

from collections.abc import Sequence

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldManifest,
    GoldPartition,
    GoldTable,
    check_generation,
)

Generation = tuple[dict[str, object], dict[str, list[dict[str, object]]]]


class InMemoryGoldStore:
    """Satisfaz `GoldStore` com um dicionário partição → geração."""

    def __init__(self) -> None:
        self._generations: dict[tuple[str, str], Generation] = {}
        self.publishes = 0

    def publish(
        self, *, partition: GoldPartition, tables: Sequence[GoldTable], manifest: GoldManifest
    ) -> None:
        check_generation(partition, tables, manifest)
        self.publishes += 1
        self._generations[partition.asset, partition.parent_sweep_id] = (
            manifest.as_mapping(),
            {table.name: [dict(row) for row in table.rows] for table in tables},
        )

    def current(self, partition: GoldPartition) -> Generation | None:
        """A geração viva da partição, ou `None` se nunca publicada."""
        return self._generations.get((partition.asset, partition.parent_sweep_id))
