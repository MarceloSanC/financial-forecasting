"""Port-out `SilverTableReader` — leitura das tabelas silver pelo refresh do gold (ADR 6.4.0004).

Port do **consumidor** (concept 6.4 §4 "Application", D3; ADR `6_4_0004` item 1;
ADR `0_0_0053`): o `evaluation` não importa o `AnalyticsRepository` do
`analytics_store`; declara aqui só a leitura de que precisa. O real é o
`ParquetAnalyticsRepository` (`analytics_store/adapters/out/parquet/`), por duck
typing; o fake é o `FakeSilverTableReader`
(`tests/fakes/features/evaluation/fake_silver_table_reader.py`).

Contrato de `read(layer=..., table=..., filters=...)`:

- `filters` são **predicados de partição apenas** (ex.: `dim_run` por `asset` e
  `parent_sweep_id`; `fact_oos_predictions` por `asset` e `feature_set_name`); chave de
  filtro fora da partição é ignorada — o resultado pode ser um **superconjunto** e o
  consumidor pós-filtra o que precisa (ex.: `run_id` do cohort);
- partição sem dados → sequência vazia; `(layer, table)` desconhecido → `ApplicationError`;
- os tipos do schema silver são preservados (`guardrail_applied` `int` 0/1, `seed`
  `int` ou `None`, timestamps ISO `str`).
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
