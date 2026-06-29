"""`SilverTable` — metadata + schema `pandera` de uma tabela silver (Stage 4.1).

Espelha o `BronzeTable` da Stage 2.1 (`shared/adapters/out/parquet/schemas/bronze_schemas.py`):
pareia o `DataFrameSchema` `pandera` de uma tabela com sua metadata de PK lógica,
partição, política de atualização e `schema_version`. Cada módulo de tabela
(`dim_run_schema.py`, …) instancia uma constante `SilverTable`; o `silver_registry.py`
as agrega em `SILVER_REGISTRY[("silver", <table>)]`.

Diferenças vs `BronzeTable`: o silver não deriva âncora de `year`/`asset` (não há
`asset_col`/`year_anchor`) — particiona por colunas já presentes no payload
(`asset`, `parent_sweep_id`, `feature_set_name`, `year`). Carrega `schema_version`
explícito (o bronze fixava no schema da Stage); cada tabela versiona sozinha.

Vive SÓ no adapter: importa `pandera.pandas as pa` (permitido aqui). O gate
`store-no-storage-leak` reprova se `pandera`/`pandas` vazar para domain/application.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandera.pandas as pa


@dataclass(frozen=True)
class SilverTable:
    """Metadata + schema de uma tabela silver (concept 4.1 §4).

    - `name`: nome lógico da tabela (ex.: ``"dim_run"``).
    - `schema_version`: versão do schema desta tabela (bump local ao módulo).
    - `logical_pk`: colunas que formam a PK lógica (dedup/upsert).
    - `partition_by`: colunas de partição em disco (resolvidas pela 4.2).
    - `update_policy`: ``"upsert"`` (só `dim_run`) ou ``"append-only"`` (facts).
    - `schema`: `DataFrameSchema` `pandera` (`strict=True`, `coerce=False`).
    """

    name: str
    schema_version: int
    logical_pk: tuple[str, ...]
    partition_by: tuple[str, ...]
    update_policy: str
    schema: pa.DataFrameSchema
