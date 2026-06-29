"""Port compartilhado: `MedallionStore`.

Abstrai a gravação/leitura de datasets `(layer, table)` particionados em Parquet
na arquitetura medalhão (bronze/silver/gold). As Stages 2.2 (`IngestCandles`) e
2.3 (news/fundamentals) **gravam** bronze por este port; 3.x/4.x **leem** de
volta. A camada `application` depende APENAS deste `Protocol` estrutural, com
tipos `collections.abc`/primitivos — NUNCA `pandas`/`pyarrow`/`duckdb`/`pandera`:
o store é trocável, testável por um fake in-memory e validado por contract test
(paridade fake↔real, mesma postura da Stage 1.5 / ADR 0.0.0021). A tradução para
`pyarrow` (escrita), `duckdb` (leitura com partition pruning) e `pandera`
(validação de schema) vive só no adapter `ParquetMedallionStore`
(`shared/adapters/out/parquet/`). O gate `import-linter` `store-no-storage-leak`
reprova se uma lib de storage vazar para cá (concept 2.1 I3/I4).

Semântica garantida por qualquer implementação deste contrato:

- **Partição derivada do schema, não do chamador (I1).** As colunas de PK lógica
  e de partição de cada `(layer, table)` vêm de um registry de schema interno ao
  adapter, não dos argumentos. O par válido nesta Stage é `bronze` cruzado com
  {`candle`, `news`, `fundamental`}; um par fora do registry é erro de aplicação
  (C2).
- **`write` é append-only com dedup por PK lógica (I2/C1).** Re-gravar uma linha
  cuja PK lógica já existe na partição alvo, com `overwrite=False`, levanta
  `DuplicateKeyError` (`ApplicationError`). Com `overwrite=True`, as linhas
  colididas são substituídas. A escrita é em batch-por-partição (nunca
  linha-a-linha).
- **`write` valida o schema bronze (C3).** Linhas com colunas/dtypes fora do
  contrato do `(layer, table)` são rejeitadas antes de tocar o Parquet.
- **`read` filtra por partição com pruning (I7).** `filters` é um predicado de
  partição (ao menos `{"asset": ...}`, opcionalmente `year`); a implementação
  varre só as partições que casam, nunca o dataset inteiro.
- **`read` de dataset/asset inexistente devolve vazio (C4).** Ler um
  `(layer, table)` ainda não gravado — ou filtrar por um `asset` sem dados —
  devolve uma sequência vazia, não um erro.

Ver ADR docs/adr/2_1_0002-medallion-store-port-shape.md (forma do port) e
docs/adr/2_1_0001-medallion-partition-and-bronze-schemas.md (partição/schemas).
"""

from collections.abc import Mapping, Sequence
from typing import Protocol

Row = Mapping[str, object]
"""Uma linha de dataset: registro chave→valor (dict-like), sem vazar DataFrame."""


class MedallionStore(Protocol):
    """Contrato de storage medalhão particionado, sem vazar libs de storage."""

    def write(
        self,
        *,
        layer: str,
        table: str,
        rows: Sequence[Row],
        overwrite: bool = False,
    ) -> None:
        """Grava `rows` no dataset `(layer, table)`, append-only por padrão.

        As linhas são particionadas por `asset`/`year` derivados do schema do
        `(layer, table)` (I1). Colisão de PK lógica na partição alvo sem
        `overwrite` levanta `DuplicateKeyError` (C1); com `overwrite=True`, as
        linhas colididas são substituídas. Dados fora do schema bronze são
        rejeitados (C3). `(layer, table)` desconhecido é erro de aplicação (C2).
        """
        ...

    def read(
        self,
        *,
        layer: str,
        table: str,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Row]:
        """Lê o dataset `(layer, table)` filtrado por partição (`filters`).

        `filters` (ao menos `{"asset": ...}`, opcionalmente `year`) é empurrado
        para a engine, varrendo só as partições casadas (I7) — nunca carrega o
        dataset inteiro. Dataset/asset inexistente devolve sequência vazia (C4).
        `(layer, table)` desconhecido é erro de aplicação (C2).
        """
        ...
