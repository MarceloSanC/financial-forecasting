"""Unit test do schema silver `fact_split_metrics` (Stage 4.1, task-06).

Prova (concept 4.1 A4/A6/A8 / C1-C5): payload VÁLIDO passa; INVÁLIDOS reprovam;
PK composta `(run_id, split)` rejeita duplicata; metadata bate com o contrato.
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
import pytest

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.fact_split_metrics_schema import (  # noqa: E501
    FACT_SPLIT_METRICS,
)

_VALID_ROWS = 2


def _valid_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "schema_version": pd.array([1, 1], dtype="int64"),
            "run_id": pd.array(["r-1", "r-1"], dtype="string"),
            "asset": pd.array(["AAPL", "AAPL"], dtype="string"),
            "parent_sweep_id": pd.array(["sweep-1", "sweep-1"], dtype="string"),
            "split": pd.array(["val", "test"], dtype="string"),
            "rmse": pd.array([0.1, 0.2], dtype="float64"),
            "mae": pd.array([0.08, 0.15], dtype="float64"),
            "mape": pd.array([1.2, None], dtype="float64"),
            "smape": pd.array([1.1, None], dtype="float64"),
            "directional_accuracy": pd.array([0.55, 0.52], dtype="float64"),
            "n_samples": pd.array([200, 250], dtype="int64"),
        }
    )


@pytest.mark.unit
def test_valid_payload_passes() -> None:
    """A8: payload válido (mape/smape opcionais nulos) valida."""
    assert len(FACT_SPLIT_METRICS.schema.validate(_valid_df())) == _VALID_ROWS


@pytest.mark.unit
def test_missing_required_column_raises() -> None:
    """C1: coluna obrigatória ausente (rmse) reprova."""
    df = _valid_df().drop(columns=["rmse"])

    with pytest.raises((pa.errors.SchemaError, pa.errors.SchemaErrors)):
        FACT_SPLIT_METRICS.schema.validate(df)


@pytest.mark.unit
def test_wrong_dtype_raises() -> None:
    """C3: dtype divergente (n_samples como float) reprova."""
    df = _valid_df()
    df["n_samples"] = df["n_samples"].astype("float64")

    with pytest.raises(pa.errors.SchemaError):
        FACT_SPLIT_METRICS.schema.validate(df)


@pytest.mark.unit
def test_extra_column_raises() -> None:
    """C4: coluna extra com strict=True reprova."""
    df = _valid_df()
    df["unexpected"] = pd.array([1.0, 2.0], dtype="float64")

    with pytest.raises(pa.errors.SchemaErrors):
        FACT_SPLIT_METRICS.schema.validate(df)


@pytest.mark.unit
def test_duplicate_composite_pk_raises() -> None:
    """C5: (run_id, split) duplicado reprova via unique composto."""
    df = _valid_df()
    df.loc[1, "split"] = "val"

    with pytest.raises(pa.errors.SchemaError):
        FACT_SPLIT_METRICS.schema.validate(df)


@pytest.mark.unit
def test_null_pk_raises() -> None:
    """C5: split nulo (nullable=False) reprova."""
    df = _valid_df()
    df["split"] = pd.array([None, "test"], dtype="string")

    with pytest.raises(pa.errors.SchemaError):
        FACT_SPLIT_METRICS.schema.validate(df)


@pytest.mark.unit
def test_metadata_matches_contract() -> None:
    """A4/A6: metadata bate com o concept §4 — append-only, PK composta."""
    assert FACT_SPLIT_METRICS.name == "fact_split_metrics"
    assert FACT_SPLIT_METRICS.logical_pk == ("run_id", "split")
    assert FACT_SPLIT_METRICS.partition_by == ("asset", "parent_sweep_id")
    assert FACT_SPLIT_METRICS.update_policy == "append-only"
    assert FACT_SPLIT_METRICS.schema_version == 1
