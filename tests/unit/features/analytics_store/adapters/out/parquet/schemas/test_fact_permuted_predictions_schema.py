"""Schema silver `fact_permuted_predictions` (Stage 7.3, Task 14; CA10, I19; ADR 7.3.0002)."""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
import pytest

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.fact_permuted_predictions_schema import (  # noqa: E501
    FACT_PERMUTED_PREDICTIONS,
)

pytestmark = pytest.mark.unit

_SCHEMA_ERRORS = (pa.errors.SchemaError, pa.errors.SchemaErrors)


def _df(families: list[str], indices: list[int]) -> pd.DataFrame:
    n = len(families)
    return pd.DataFrame(
        {
            "schema_version": pd.array([1] * n, dtype="int64"),
            "run_id": pd.array(["r-1"] * n, dtype="string"),
            "model_version": pd.array(["tft_quantile"] * n, dtype="string"),
            "asset": pd.array(["AAPL"] * n, dtype="string"),
            "feature_set_name": pd.array(["fs_all"] * n, dtype="string"),
            "permuted_family": pd.array(families, dtype="string"),
            "permutation_index": pd.array(indices, dtype="int64"),
            "permutation_seed": pd.array([130] * n, dtype="int64"),
            "permutation_algorithm": pd.array(
                ["fisher_yates_random_random_v1"] * n, dtype="string"
            ),
            "partition_hash": pd.array(["a" * 64] * n, dtype="string"),
            "horizon": pd.array([1] * n, dtype="int64"),
            "decision_idx": pd.array([100] * n, dtype="int64"),
            "timestamp_utc": pd.array(["2024-01-02T00:00:00Z"] * n, dtype="string"),
            "target_timestamp_utc": pd.array(["2024-01-03T00:00:00Z"] * n, dtype="string"),
            "quantile_level": pd.array([0.5] * n, dtype="float64"),
            "value_raw": pd.array([0.0] * n, dtype="float64"),
            "value_guardrail": pd.array([0.0] * n, dtype="float64"),
            "guardrail_applied": pd.array([0] * n, dtype="int64"),
            "year": pd.array([2024] * n, dtype="int64"),
        }
    )


def test_valid_identity_and_permuted_rows_pass() -> None:
    df = _df(["none", "price", "price"], [0, 1, 2])
    assert len(FACT_PERMUTED_PREDICTIONS.schema.validate(df)) == len(df)


def test_primary_key_repeated_refused() -> None:
    df = _df(["price", "price"], [1, 1])
    with pytest.raises(_SCHEMA_ERRORS):
        FACT_PERMUTED_PREDICTIONS.schema.validate(df)


def test_family_outside_vocabulary_refused() -> None:
    with pytest.raises(_SCHEMA_ERRORS):
        FACT_PERMUTED_PREDICTIONS.schema.validate(_df(["volatility"], [1]))


@pytest.mark.parametrize(
    ("family", "index"),
    [pytest.param("none", 2, id="none-with-index"), pytest.param("price", 0, id="family-zero")],
)
def test_none_iff_index_zero(family: str, index: int) -> None:
    with pytest.raises(_SCHEMA_ERRORS):
        FACT_PERMUTED_PREDICTIONS.schema.validate(_df([family], [index]))


def test_negative_index_refused() -> None:
    with pytest.raises(_SCHEMA_ERRORS):
        FACT_PERMUTED_PREDICTIONS.schema.validate(_df(["price"], [-1]))


def test_partition_by_has_run_id() -> None:
    assert FACT_PERMUTED_PREDICTIONS.partition_by == ("asset", "feature_set_name", "run_id", "year")
    assert FACT_PERMUTED_PREDICTIONS.update_policy == "append-only"
    assert FACT_PERMUTED_PREDICTIONS.logical_pk == (
        "run_id",
        "permuted_family",
        "permutation_index",
        "horizon",
        "timestamp_utc",
        "target_timestamp_utc",
        "quantile_level",
    )


def test_schema_version_is_1_for_the_new_tables() -> None:
    assert FACT_PERMUTED_PREDICTIONS.schema_version == 1
