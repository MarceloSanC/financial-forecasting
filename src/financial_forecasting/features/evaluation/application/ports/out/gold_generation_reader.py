"""Port-out `GoldGenerationReader` — leitura da geração viva do gold (Stage 6.5).

Port do **consumidor** (concept 6.5 §4 "Application", D5, I7, C6; ADR `6_5_0005`
itens 1, 4, 5): o scorecard (e, depois, 8.1 e 8.3) lê a geração corrente de uma
partição. Regras de toda implementação:

- o manifesto é lido **antes** de qualquer tabela; partição sem manifesto →
  `GoldManifestNotFoundError`;
- a geração é montada **só** por `GoldGeneration.from_stored` (schema e coerência
  com dono; tabela com zero linhas vem do `rows_by_table`); tabela ausente,
  contagem divergente ou geração incoerente → `GoldGenerationCorruptError`;
- uma geração `BLOCKED` volta normal (a recusa é do use case).

O real é o `ParquetGoldStore.read_generation` (`adapters/out/duckdb/`); o fake é o
`InMemoryGoldGenerationReader` (`tests/fakes/features/evaluation/`). Os dois erros
são definidos em `dtos/refresh_gold.py`, ao lado do `from_stored`, e reexportados
aqui.
"""

from __future__ import annotations

from typing import Protocol

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldGenerationCorruptError,
    GoldManifestNotFoundError,
    GoldPartition,
)

__all__ = [
    "GoldGenerationCorruptError",
    "GoldGenerationReader",
    "GoldManifestNotFoundError",
]


class GoldGenerationReader(Protocol):
    """Lê a geração corrente de uma partição do gold."""

    def read_generation(self, *, partition: GoldPartition) -> GoldGeneration:
        """A geração viva da partição (manifesto primeiro).

        Raises:
            GoldManifestNotFoundError: a partição não tem geração publicada.
            GoldGenerationCorruptError: a geração lida não se sustenta.
        """
        ...
