"""Schema `pandera` silver — `fact_permuted_predictions` (Stage 7.3; ADR 7.3.0002 item 4).

As predições da importância por permutação, em formato LONGO como `fact_oos_predictions`
(ADR 4.1.0002): uma linha por (run, família permutada, índice da permutação, horizonte,
decisão, nível). A passagem de identidade também entra, com `permuted_family = "none"` e
`permutation_index = 0` (`none ⇔ 0`), para que toda diferença d_{f,t} use a identidade
da mesma tabela (concept 7.3 I7).

PK lógica `(run_id, permuted_family, permutation_index, horizon, timestamp_utc,
target_timestamp_utc, quantile_level)`. Partição `(asset, feature_set_name, run_id,
year)`: o `run_id` é coluna de partição para que a leitura por run seja empurrada ao
storage (o repositório só empurra colunas de partição). `append-only`.
`permutation_seed`, `permutation_algorithm` e `partition_hash` identificam o plano e a
partição de famílias da linha (o refresh compara com o bloco `[h3]`, I17).
"""

from __future__ import annotations

import pandera.pandas as pa

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.silver_table import (  # noqa: E501
    SilverTable,
)

_SCHEMA_VERSION = 1
IDENTITY_FAMILY = "none"
PERMUTED_FAMILIES = ("price", "technical", "sentiment", "fundamental", IDENTITY_FAMILY)
_PK = (
    "run_id",
    "permuted_family",
    "permutation_index",
    "horizon",
    "timestamp_utc",
    "target_timestamp_utc",
    "quantile_level",
)

_SCHEMA = pa.DataFrameSchema(
    {
        "schema_version": pa.Column("int64", nullable=False),
        "run_id": pa.Column(str, nullable=False),
        "model_version": pa.Column(str, nullable=False),
        "asset": pa.Column(str, nullable=False),
        "feature_set_name": pa.Column(str, nullable=False),
        "permuted_family": pa.Column(
            str, nullable=False, checks=pa.Check.isin(list(PERMUTED_FAMILIES))
        ),
        "permutation_index": pa.Column("int64", nullable=False, checks=pa.Check.ge(0)),
        "permutation_seed": pa.Column("int64", nullable=False),
        "permutation_algorithm": pa.Column(str, nullable=False),
        "partition_hash": pa.Column(str, nullable=False),
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
    checks=pa.Check(
        lambda df: (df["permuted_family"] == IDENTITY_FAMILY) == (df["permutation_index"] == 0),
        element_wise=False,
        error="permuted_family == 'none' iff permutation_index == 0",
    ),
    strict=True,
    coerce=False,
    unique=list(_PK),
)

FACT_PERMUTED_PREDICTIONS = SilverTable(
    name="fact_permuted_predictions",
    schema_version=_SCHEMA_VERSION,
    logical_pk=_PK,
    partition_by=("asset", "feature_set_name", "run_id", "year"),
    update_policy="append-only",
    schema=_SCHEMA,
)
