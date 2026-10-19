"""Schema silver `fact_vsn_weights` (Stage 7.3, Task 14; CA10, I19; ADR 7.3.0002)."""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
import pytest

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.fact_vsn_weights_schema import (  # noqa: E501
    FACT_VSN_WEIGHTS,
)

pytestmark = pytest.mark.unit

_SCHEMA_ERRORS = (pa.errors.SchemaError, pa.errors.SchemaErrors)


def _df(variables: list[str], families: list[str]) -> pd.DataFrame:
    n = len(variables)
    return pd.DataFrame(
        {
            "schema_version": pd.array([1] * n, dtype="int64"),
            "run_id": pd.array(["r-1"] * n, dtype="string"),
            "model_version": pd.array(["tft_quantile"] * n, dtype="string"),
            "asset": pd.array(["AAPL"] * n, dtype="string"),
            "feature_set_name": pd.array(["fs_all"] * n, dtype="string"),
            "decision_idx": pd.array([100] * n, dtype="int64"),
            "timestamp_utc": pd.array(["2024-01-02T00:00:00Z"] * n, dtype="string"),
            "variable": pd.array(variables, dtype="string"),
            "family": pd.array(families, dtype="string"),
            "weight": pd.array([1.0 / n] * n, dtype="float64"),
            "year": pd.array([2024] * n, dtype="int64"),
        }
    )


def test_valid_rows_pass() -> None:
    df = _df(["close", "rsi_14", "day_of_week"], ["price", "technical", "none"])
    assert len(FACT_VSN_WEIGHTS.schema.validate(df)) == len(df)


def test_primary_key_repeated_refused() -> None:
    with pytest.raises(_SCHEMA_ERRORS):
        FACT_VSN_WEIGHTS.schema.validate(_df(["close", "close"], ["price", "price"]))


def test_vsn_family_vocabulary_includes_none() -> None:
    df = _df(["relative_time_idx", "target"], ["none", "none"])
    assert len(FACT_VSN_WEIGHTS.schema.validate(df)) == len(df)
    with pytest.raises(_SCHEMA_ERRORS):
        FACT_VSN_WEIGHTS.schema.validate(_df(["atr"], ["volatility"]))


def test_partition_by_has_run_id() -> None:
    assert FACT_VSN_WEIGHTS.partition_by == ("asset", "feature_set_name", "run_id", "year")
    assert FACT_VSN_WEIGHTS.update_policy == "append-only"
    assert FACT_VSN_WEIGHTS.logical_pk == ("run_id", "timestamp_utc", "variable")


def test_schema_version_is_1_for_the_new_tables() -> None:
    assert FACT_VSN_WEIGHTS.schema_version == 1
