"""Port-out `AnalyticsRepository` — escrita/leitura silver por `(layer, table)`.

Abstrai a gravação/leitura de tabelas silver `(layer, table)` particionadas em
Parquet no BC `analytics_store`. A Stage 4.3 (`MultiHorizonPredictionPersister`)
**grava** predições por este port; os Steps 5-6 **leem** de volta. A camada
`application` depende APENAS deste `Protocol` estrutural, com tipos
`collections.abc`/primitivos — NUNCA `pandas`/`pyarrow`/`duckdb`/`pandera`: o
repositório é trocável, testável por um fake in-memory e validado por contract
test (paridade fake↔real, mesma postura do `MedallionStore` 2.1 / ADR 0.0.0021).
A tradução para `pyarrow` (escrita), `duckdb` (leitura com partition pruning) e
`pandera` (validação de schema) vive só no adapter `ParquetAnalyticsRepository`
(`adapters/out/parquet/`). O gate `import-linter` `store-no-storage-leak` reprova
se uma lib de storage vazar para cá (concept 4.2 I1/A1).

Semântica garantida por qualquer implementação deste contrato:

- **Partição derivada do schema, não do chamador (I2).** As colunas de PK lógica
  e de partição de cada `(layer, table)` vêm do `SILVER_REGISTRY` (4.1) interno
  ao adapter, não dos argumentos — são **colunas literais do payload**
  (`asset`/`parent_sweep_id`/`feature_set_name`/`year`), em 1..3 níveis distintos
  por tabela; sem derivar ano de âncora temporal (divergência chave vs bronze).
  Um par `(layer, table)` fora do registry é erro de aplicação (C2).
- **`write` é append-only nos 4 fatos (I3/C1).** Re-gravar uma linha cuja PK
  lógica já existe na partição alvo levanta `DuplicateKeyError` (`ApplicationError`).
  Upsert (substituir só as linhas colididas) acontece quando o
  `SilverTable.update_policy == "upsert"` (apenas `dim_run`) **ou** quando
  `allow_upsert=True` (reprocessamento consciente, C5).
- **`write` valida o schema `pandera` (I4/C3).** Linhas com colunas/dtypes fora
  do contrato do `(layer, table)` são rejeitadas ANTES de tocar o Parquet.
- **`created_at_utc` de `dim_run` é write-time (I5).** O mapper `RunRecord -> row`
  do adapter preenche `created_at_utc` via `Clock` injetado (o VO `RunRecord` não
  o carrega; o schema exige `nullable=False`).
- **`read` filtra por partição com pruning (I8).** `filters` é um predicado de
  partição (ao menos `{"asset": ...}`, opcionalmente `parent_sweep_id`/
  `feature_set_name`/`year`); a implementação varre só as partições que casam.
- **`read` preserva `parent_sweep_id` no round-trip (I6/C6).** Valor `None` vira
  o sentinel de partição `__none__` no disco e é **re-traduzido para `None`** na
  leitura.
- **`read` de dataset/asset inexistente devolve vazio (C4).** Não é erro.

Ver ADR docs/adr/4_2_0001-analytics-repository-port-shape-and-dedicated-parquet.md
(forma do port + adapter dedicado) e docs/adr/4_2_0002-created-at-utc-via-injected-clock.md
(`created_at_utc` via `Clock`).
"""

from collections.abc import Mapping, Sequence
from typing import Protocol

Row = Mapping[str, object]
"""Uma linha de tabela silver: registro chave→valor (dict-like), sem DataFrame."""


class AnalyticsRepository(Protocol):
    """Contrato de escrita/leitura silver particionada, sem vazar libs de storage."""

    def write(
        self,
        *,
        layer: str,
        table: str,
        rows: Sequence[Row],
        allow_upsert: bool = False,
    ) -> None:
        """Grava `rows` no `(layer, table)`, append-only por padrão.

        As linhas são particionadas pelas colunas literais de
        `SilverTable.partition_by` do registry (I2). Colisão de PK lógica na
        partição alvo, em fato append-only sem `allow_upsert`, levanta
        `DuplicateKeyError` (C1); com `allow_upsert=True` (ou `update_policy ==
        "upsert"`, caso `dim_run`) as linhas colididas são substituídas (C5).
        Dados fora do schema `pandera` são rejeitados antes do disco (C3, I4).
        `(layer, table)` desconhecido é erro de aplicação (C2).
        """
        ...

    def read(
        self,
        *,
        layer: str,
        table: str,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Row]:
        """Lê o `(layer, table)` filtrado por partição (`filters`).

        `filters` (ao menos `{"asset": ...}`, opcional `parent_sweep_id`/
        `feature_set_name`/`year`) é empurrado para as colunas de partição,
        varrendo só as partições casadas (I8) — nunca o dataset inteiro.
        `parent_sweep_id` armazenado como `__none__` retorna como `None` (I6/C6).
        Dataset/asset inexistente devolve sequência vazia (C4).
        `(layer, table)` desconhecido é erro de aplicação (C2).
        """
        ...
