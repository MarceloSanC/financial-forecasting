"""Port-out `SilverTableReader` do slice `inference` — leitura do silver (Stage 7.1).

Port do CONSUMIDOR (ADR 0.0.0053), mesma forma do homônimo do `evaluation`: o
`RunInference` lê `dim_run` do cohort (C6; identidade herdada pelas linhas de
calib, I4) e `fact_oos_predictions` do ativo e do feature set (teste de
referência da reprodução, calib presente, releitura da contagem — I5/I8). Só
predições: nada do realizado é lido para avaliar (I13).

Real: `ParquetAnalyticsRepository` do `analytics_store`, por duck-typing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol


class SilverTableReader(Protocol):
    """Lê uma tabela silver filtrada por partição."""

    def read(
        self,
        *,
        layer: str,
        table: str,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Mapping[str, object]]:
        """Linhas da tabela nas partições de `filters` (superconjunto permitido)."""
        ...
