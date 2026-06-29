"""Schema `pandera` silver — `dim_run` (Stage 4.1, task-06).

Dimensão de execução: uma linha por `run_id`. Espelha (com julgamento) o
`DIM_RUN_SCHEMA` do old (`analytics_store_schema.py:154-202`), reduzido ao conjunto
de colunas do contrato (concept 4.1 §4) e alinhado aos campos do VO `RunRecord`.

PK lógica `(run_id,)`; partição `(asset, parent_sweep_id)`; **única tabela `upsert`**
(I6 — facts são `append-only`). Identificadores/hashes/timestamps como `string`
(`run_id`, `config_signature`, `split_fingerprint` guardam o hash hex da 1.4 — I10);
contagens/`schema_version` como `int64`. `strict=True`, `coerce=False` (espelha bronze).

Colunas opcionais (`parent_sweep_id`, `fold`, `seed`) são `nullable=True` —
execução avulsa pode não ter sweep/fold/seed. As colunas de PK são `nullable=False`
e `unique` (composto) garante a unicidade da PK (C5).
"""

from __future__ import annotations

import pandera.pandas as pa

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.silver_table import (  # noqa: E501
    SilverTable,
)

_DIM_RUN_SCHEMA_VERSION = 1

_SCHEMA = pa.DataFrameSchema(
    {
        "schema_version": pa.Column("int64", nullable=False),
        "run_id": pa.Column(str, nullable=False),
        "asset": pa.Column(str, nullable=False),
        "parent_sweep_id": pa.Column(str, nullable=True),
        "feature_set_name": pa.Column(str, nullable=False),
        "config_signature": pa.Column(str, nullable=False),
        "split_fingerprint": pa.Column(str, nullable=False),
        "fold": pa.Column(str, nullable=True),
        "seed": pa.Column("int64", nullable=True),
        "model_version": pa.Column(str, nullable=False),
        "created_at_utc": pa.Column(str, nullable=False),
    },
    strict=True,
    coerce=False,
    unique=["run_id"],
)

DIM_RUN = SilverTable(
    name="dim_run",
    schema_version=_DIM_RUN_SCHEMA_VERSION,
    logical_pk=("run_id",),
    partition_by=("asset", "parent_sweep_id"),
    update_policy="upsert",
    schema=_SCHEMA,
)
