"""Port-out `GoldStore` — publica uma geração inteira do gold de um cohort (ADR 6.4.0005).

Protocol estrutural de **um método** (concept 6.4 §4 "Application", D8, C9). O real
é o `ParquetGoldStore` (`adapters/out/duckdb/parquet_gold_store.py`); o fake é o
`InMemoryGoldStore` (`tests/fakes/features/evaluation/in_memory_gold_store.py`).

Contrato de `publish(partition=..., tables=..., manifest=...)`:

- **geração inteira** (ADR `6_4_0005` itens 4-5): depois do `publish`, a geração
  corrente da partição é **exatamente** as `tables` e o `manifest` publicados — uma
  tabela da geração anterior que não está em `tables` deixa de existir; outra partição
  fica intocada; a ordem das linhas (ordenadas pela chave no `GoldTable`) é preservada;
- **layout do real:** `<data_root>/gold/asset=<a>/parent_sweep_id=<p>/current/` com um
  `<table>.parquet` por tabela e `MANIFEST.json` escrito **por último**; a troca é
  `.staging/` → `current/` por dois `rename` de diretório. Falha antes da troca
  propaga e deixa `current/` intacto (C9); sobras de `.staging/`/`.previous/` de uma
  execução interrompida são removidas no `publish` seguinte;
- **leitores (6.5):** leem `MANIFEST.json` primeiro e cada tabela como arquivo único
  **sem** inferência de partição (`partitioning=None` no pyarrow,
  `hive_partitioning = false` no DuckDB): os segmentos `asset=`/`parent_sweep_id=` do
  caminho colidem com as colunas de mesmo nome das linhas. Tabela com zero linhas é
  gravada com schema vazio (sem colunas) — o leitor usa o `rows_by_table` do manifesto;
- **pré-condição de escritor único:** no máximo um `publish` por
  `(asset, parent_sweep_id)` ao mesmo tempo (ADR `6_4_0005` item 6) — sem lock;
- a geração é coerente (`check_generation`, dono único no módulo dos DTOs): manifesto
  da mesma partição, nomes de tabela únicos, `rows_by_table` = tabelas publicadas e
  `asset`/`parent_sweep_id` da partição em toda linha — senão `ValueError` antes de
  gravar;
- a `partition` já foi validada (`validate_path_identifier`, C3); o real valida de novo
  antes de montar qualquer caminho.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldManifest,
    GoldPartition,
    GoldTable,
)


class GoldStore(Protocol):
    """Publica a geração inteira de uma partição do gold."""

    def publish(
        self, *, partition: GoldPartition, tables: Sequence[GoldTable], manifest: GoldManifest
    ) -> None:
        """Substitui a geração corrente da `partition` por `tables` + `manifest`.

        Raises:
            ValueError: geração incoerente (`check_generation`) ou identificador
                inválido (defesa do real na fronteira de I/O).
            OSError: falha de escrita antes da troca (a geração anterior segue viva).
        """
        ...
