"""Schema `pandera` silver — `fact_split_metrics` (Stage 4.1, task-06).

Fato de métricas por split: uma linha por `(run_id, split)` com métricas pontuais.
Espelha (com julgamento) o `FACT_SPLIT_METRICS_SCHEMA` do old
(`analytics_store_schema.py:339-367`). As métricas confirmatórias probabilísticas
(pinball/CRPS/calibração) são do Step 6 (tabelas gold) — aqui ficam só as métricas
pontuais descritivas que o old já registrava por split.

PK lógica `(run_id, split)`; partição `(asset, parent_sweep_id)`; `append-only` (I6).
Métricas como `float64` (`mape`/`smape` opcionais — nem todo modelo as reporta).
`strict=True`, `coerce=False`; `unique` composto garante a PK (C5).
"""

from __future__ import annotations

import pandera.pandas as pa

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.silver_table import (  # noqa: E501
    SilverTable,
)

_FACT_SPLIT_METRICS_SCHEMA_VERSION = 1

_SCHEMA = pa.DataFrameSchema(
    {
        "schema_version": pa.Column("int64", nullable=False),
        "run_id": pa.Column(str, nullable=False),
        "asset": pa.Column(str, nullable=False),
        "parent_sweep_id": pa.Column(str, nullable=True),
        "split": pa.Column(str, nullable=False),
        "rmse": pa.Column("float64", nullable=False),
        "mae": pa.Column("float64", nullable=False),
        "mape": pa.Column("float64", nullable=True),
        "smape": pa.Column("float64", nullable=True),
        "directional_accuracy": pa.Column("float64", nullable=False),
        "n_samples": pa.Column("int64", nullable=False),
    },
    strict=True,
    coerce=False,
    unique=["run_id", "split"],
)

FACT_SPLIT_METRICS = SilverTable(
    name="fact_split_metrics",
    schema_version=_FACT_SPLIT_METRICS_SCHEMA_VERSION,
    logical_pk=("run_id", "split"),
    partition_by=("asset", "parent_sweep_id"),
    update_policy="append-only",
    schema=_SCHEMA,
)
