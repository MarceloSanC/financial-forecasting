"""Schema `pandera` silver — `fact_oos_predictions` em formato LONGO (H-1, Stage 4.1, task-07).

Fato de predições out-of-sample em **formato LONGO/agnóstico à grade** (decisão humana H-1,
fechada/imutável; ADR 4.1.0002): uma linha por nível de quantil. `quantile_level` entra na PK
com `value_raw`, `value_guardrail`, `guardrail_applied`. É **PROIBIDO** portar as colunas
`quantile_p10/p50/p90` (e variantes `_post_guardrail`) do old
(`analytics_store_schema.py:393-399`) — a grade densa ~7-9 fica decidida no Step 5 sem
migração de schema (mais linhas, nunca DDL).

PK lógica `(run_id, split, horizon, timestamp_utc, target_timestamp_utc, quantile_level)`;
partição `(asset, feature_set_name, year)`; `append-only` (I6).

`decision_idx`, `timestamp_utc`, `target_timestamp_utc` são contrato de schema (âncora
ADR-0003 do old, *mechanical > procedural*); a lógica de off-by-one que os preenche é da
Stage 4.3, não aqui (I11). `quantile_level` é `float64` (nível numérico, query-ável;
concept §13), `coerce=False`. `strict=True`; `unique` composto garante a PK longa (C5).
"""

from __future__ import annotations

import pandera.pandas as pa

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.silver_table import (  # noqa: E501
    SilverTable,
)

_FACT_OOS_PREDICTIONS_SCHEMA_VERSION = 1

_SCHEMA = pa.DataFrameSchema(
    {
        "schema_version": pa.Column("int64", nullable=False),
        "run_id": pa.Column(str, nullable=False),
        "model_version": pa.Column(str, nullable=False),
        "asset": pa.Column(str, nullable=False),
        "feature_set_name": pa.Column(str, nullable=False),
        "split": pa.Column(str, nullable=False),
        "horizon": pa.Column("int64", nullable=False),
        "decision_idx": pa.Column("int64", nullable=False),
        "timestamp_utc": pa.Column(str, nullable=False),
        "target_timestamp_utc": pa.Column(str, nullable=False),
        "quantile_level": pa.Column("float64", nullable=False),
        "value_raw": pa.Column("float64", nullable=False),
        "value_guardrail": pa.Column("float64", nullable=False),
        "guardrail_applied": pa.Column("int64", nullable=False),
        "year": pa.Column("int64", nullable=False),
    },
    strict=True,
    coerce=False,
    unique=[
        "run_id",
        "split",
        "horizon",
        "timestamp_utc",
        "target_timestamp_utc",
        "quantile_level",
    ],
)

FACT_OOS_PREDICTIONS = SilverTable(
    name="fact_oos_predictions",
    schema_version=_FACT_OOS_PREDICTIONS_SCHEMA_VERSION,
    logical_pk=(
        "run_id",
        "split",
        "horizon",
        "timestamp_utc",
        "target_timestamp_utc",
        "quantile_level",
    ),
    partition_by=("asset", "feature_set_name", "year"),
    update_policy="append-only",
    schema=_SCHEMA,
)
