"""Schema `pandera` silver — `fact_config` (Stage 4.1, task-06).

Fato de configuração: uma linha por `run_id` com a configuração de treino serializada.
Espelha (com julgamento) o `FACT_CONFIG_SCHEMA` do old
(`analytics_store_schema.py:254-306`), reduzido ao essencial do contrato (concept §4):
o JSON canônico da config + os campos de modo/loss/horizontes que os Steps 5-6 leem.

PK lógica `(run_id,)`; partição `(asset, parent_sweep_id)`; `append-only` (I6).
`training_config_json`/`quantile_levels_json`/`evaluation_horizons_json` guardam JSON
como `string` (a grade de quantis vive aqui como dado, não como colunas — coerente
com H-1). `strict=True`, `coerce=False`.
"""

from __future__ import annotations

import pandera.pandas as pa

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.silver_table import (  # noqa: E501
    SilverTable,
)

_FACT_CONFIG_SCHEMA_VERSION = 1

_SCHEMA = pa.DataFrameSchema(
    {
        "schema_version": pa.Column("int64", nullable=False),
        "run_id": pa.Column(str, nullable=False),
        "asset": pa.Column(str, nullable=False),
        "parent_sweep_id": pa.Column(str, nullable=True),
        "prediction_mode": pa.Column(str, nullable=False),
        "loss_name": pa.Column(str, nullable=False),
        "quantile_levels_json": pa.Column(str, nullable=False),
        "evaluation_horizons_json": pa.Column(str, nullable=False),
        "training_config_json": pa.Column(str, nullable=False),
        "dataset_parameters_json": pa.Column(str, nullable=True),
    },
    strict=True,
    coerce=False,
    unique=["run_id"],
)

FACT_CONFIG = SilverTable(
    name="fact_config",
    schema_version=_FACT_CONFIG_SCHEMA_VERSION,
    logical_pk=("run_id",),
    partition_by=("asset", "parent_sweep_id"),
    update_policy="append-only",
    schema=_SCHEMA,
)
