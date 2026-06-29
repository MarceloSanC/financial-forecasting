"""Unit test do schema silver `fact_config` (Stage 4.1, task-06).

Prova (concept 4.1 A4/A6/A8 / C1-C5): payload VÁLIDO passa; INVÁLIDOS (missing
required, dtype errado, coluna extra, PK duplicada/nula) reprovam; metadata bate
com o contrato (`run_id` PK, `append-only`).
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
import pytest

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.fact_config_schema import (  # noqa: E501
    FACT_CONFIG,
)


def _valid_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "schema_version": pd.array([1], dtype="int64"),
            "run_id": pd.array(["r-1"], dtype="string"),
            "asset": pd.array(["AAPL"], dtype="string"),
            "parent_sweep_id": pd.array(["sweep-1"], dtype="string"),
            "prediction_mode": pd.array(["quantile"], dtype="string"),
            "loss_name": pd.array(["quantile_loss"], dtype="string"),
            "quantile_levels_json": pd.array(["[0.1,0.5,0.9]"], dtype="string"),
            "evaluation_horizons_json": pd.array(["[1,5]"], dtype="string"),
            "training_config_json": pd.array(['{"lr":0.001}'], dtype="string"),
            "dataset_parameters_json": pd.array(['{"enc":63}'], dtype="string"),
        }
    )


@pytest.mark.unit
def test_valid_payload_passes() -> None:
    """A8: payload válido valida."""
    assert len(FACT_CONFIG.schema.validate(_valid_df())) == 1


@pytest.mark.unit
def test_missing_required_column_raises() -> None:
    """C1: coluna obrigatória ausente (loss_name) reprova."""
    df = _valid_df().drop(columns=["loss_name"])

    with pytest.raises((pa.errors.SchemaError, pa.errors.SchemaErrors)):
        FACT_CONFIG.schema.validate(df)


@pytest.mark.unit
def test_wrong_dtype_raises() -> None:
    """C3: dtype divergente (schema_version como string) reprova."""
    df = _valid_df()
    df["schema_version"] = df["schema_version"].astype("string")

    with pytest.raises(pa.errors.SchemaError):
        FACT_CONFIG.schema.validate(df)


@pytest.mark.unit
def test_extra_column_raises() -> None:
    """C4: coluna extra com strict=True reprova."""
    df = _valid_df()
    df["unexpected"] = pd.array(["x"], dtype="string")

    with pytest.raises(pa.errors.SchemaErrors):
        FACT_CONFIG.schema.validate(df)


@pytest.mark.unit
def test_duplicate_pk_raises() -> None:
    """C5: run_id duplicado (PK) reprova via unique."""
    df = pd.concat([_valid_df(), _valid_df()], ignore_index=True)

    with pytest.raises(pa.errors.SchemaError):
        FACT_CONFIG.schema.validate(df)


@pytest.mark.unit
def test_null_pk_raises() -> None:
    """C5: run_id nulo (nullable=False) reprova."""
    df = _valid_df()
    df["run_id"] = pd.array([None], dtype="string")

    with pytest.raises(pa.errors.SchemaError):
        FACT_CONFIG.schema.validate(df)


@pytest.mark.unit
def test_metadata_matches_contract() -> None:
    """A4/A6: metadata bate com o concept §4 — fact_config é append-only."""
    assert FACT_CONFIG.name == "fact_config"
    assert FACT_CONFIG.logical_pk == ("run_id",)
    assert FACT_CONFIG.partition_by == ("asset", "parent_sweep_id")
    assert FACT_CONFIG.update_policy == "append-only"
    assert FACT_CONFIG.schema_version == 1
