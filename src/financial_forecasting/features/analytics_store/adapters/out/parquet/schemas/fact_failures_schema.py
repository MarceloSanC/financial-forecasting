"""Schema `pandera` silver — `fact_failures` (Stage 4.1, task-06).

Fato de falhas: uma linha por `(run_id, failed_at_utc, stage)`. Espelha (com julgamento)
o `FACT_FAILURES_SCHEMA` do old (`analytics_store_schema.py:428-459`), mantendo o núcleo
auditável (tipo/mensagem/hash de trace) e descartando colunas operacionais de captura de
processo (cmdline/stdout/stderr) que não pertencem ao contrato confirmatório dos Steps 1-4.

PK lógica `(run_id, failed_at_utc, stage)`; partição `(asset,)`; `append-only` (I6).
`failed_at_utc` é `string` (ISO UTC) — coerente com timestamps do silver como string.
`strict=True`, `coerce=False`; `unique` composto garante a PK (C5).
"""

from __future__ import annotations

import pandera.pandas as pa

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.silver_table import (  # noqa: E501
    SilverTable,
)

_FACT_FAILURES_SCHEMA_VERSION = 1

_SCHEMA = pa.DataFrameSchema(
    {
        "schema_version": pa.Column("int64", nullable=False),
        "run_id": pa.Column(str, nullable=False),
        "asset": pa.Column(str, nullable=False),
        "failed_at_utc": pa.Column(str, nullable=False),
        "stage": pa.Column(str, nullable=False),
        "error_type": pa.Column(str, nullable=False),
        "error_message": pa.Column(str, nullable=False),
        "trace_hash": pa.Column(str, nullable=False),
        "traceback_excerpt": pa.Column(str, nullable=True),
    },
    strict=True,
    coerce=False,
    unique=["run_id", "failed_at_utc", "stage"],
)

FACT_FAILURES = SilverTable(
    name="fact_failures",
    schema_version=_FACT_FAILURES_SCHEMA_VERSION,
    logical_pk=("run_id", "failed_at_utc", "stage"),
    partition_by=("asset",),
    update_policy="append-only",
    schema=_SCHEMA,
)
