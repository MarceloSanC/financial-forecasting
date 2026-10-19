"""Schema `pandera` silver — `fact_vsn_weights` (Stage 7.3; ADR 7.3.0002 item 4).

Os pesos da variable selection network do encoder do TFT, por run, decisão de teste e
variável (média nos passos do encoder, como a `pytorch-forecasting` reduz). `family` é a
família da registry da variável, ou `"none"` para o calendário, o alvo passado e o
índice relativo.

PK lógica `(run_id, timestamp_utc, variable)`. Partição `(asset, feature_set_name,
run_id, year)`, a mesma de `fact_permuted_predictions` (leitura por run empurrada ao
storage). `append-only`.
"""

from __future__ import annotations

import pandera.pandas as pa

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.silver_table import (  # noqa: E501
    SilverTable,
)

_SCHEMA_VERSION = 1
VSN_FAMILIES = ("price", "technical", "sentiment", "fundamental", "none")
_PK = ("run_id", "timestamp_utc", "variable")

_SCHEMA = pa.DataFrameSchema(
    {
        "schema_version": pa.Column("int64", nullable=False),
        "run_id": pa.Column(str, nullable=False),
        "model_version": pa.Column(str, nullable=False),
        "asset": pa.Column(str, nullable=False),
        "feature_set_name": pa.Column(str, nullable=False),
        "decision_idx": pa.Column("int64", nullable=False),
        "timestamp_utc": pa.Column(str, nullable=False),
        "variable": pa.Column(str, nullable=False),
        "family": pa.Column(str, nullable=False, checks=pa.Check.isin(list(VSN_FAMILIES))),
        "weight": pa.Column("float64", nullable=False),
        "year": pa.Column("int64", nullable=False),
    },
    strict=True,
    coerce=False,
    unique=list(_PK),
)

FACT_VSN_WEIGHTS = SilverTable(
    name="fact_vsn_weights",
    schema_version=_SCHEMA_VERSION,
    logical_pk=_PK,
    partition_by=("asset", "feature_set_name", "run_id", "year"),
    update_policy="append-only",
    schema=_SCHEMA,
)
