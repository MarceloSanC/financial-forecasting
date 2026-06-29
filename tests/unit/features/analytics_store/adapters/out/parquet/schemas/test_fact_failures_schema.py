"""Unit test do schema silver `fact_failures` (Stage 4.1, task-06).

Prova (concept 4.1 A4/A6/A8 / C1-C5): payload VÁLIDO passa; INVÁLIDOS reprovam;
PK composta `(run_id, failed_at_utc, stage)` rejeita duplicata; partição `(asset,)`.
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
import pytest

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.fact_failures_schema import (  # noqa: E501
    FACT_FAILURES,
)


def _valid_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "schema_version": pd.array([1], dtype="int64"),
            "run_id": pd.array(["r-1"], dtype="string"),
            "asset": pd.array(["AAPL"], dtype="string"),
            "failed_at_utc": pd.array(["2024-01-02T10:00:00Z"], dtype="string"),
            "stage": pd.array(["train"], dtype="string"),
            "error_type": pd.array(["ValueError"], dtype="string"),
            "error_message": pd.array(["boom"], dtype="string"),
            "trace_hash": pd.array(["t" * 64], dtype="string"),
            "traceback_excerpt": pd.array([None], dtype="string"),
        }
    )


@pytest.mark.unit
def test_valid_payload_passes() -> None:
    """A8: payload válido (traceback_excerpt opcional nulo) valida."""
    assert len(FACT_FAILURES.schema.validate(_valid_df())) == 1


@pytest.mark.unit
def test_missing_required_column_raises() -> None:
    """C1: coluna obrigatória ausente (error_type) reprova."""
    df = _valid_df().drop(columns=["error_type"])

    with pytest.raises((pa.errors.SchemaError, pa.errors.SchemaErrors)):
        FACT_FAILURES.schema.validate(df)


@pytest.mark.unit
def test_wrong_dtype_raises() -> None:
    """C3: dtype divergente (schema_version como string) reprova."""
    df = _valid_df()
    df["schema_version"] = df["schema_version"].astype("string")

    with pytest.raises(pa.errors.SchemaError):
        FACT_FAILURES.schema.validate(df)


@pytest.mark.unit
def test_extra_column_raises() -> None:
    """C4: coluna extra com strict=True reprova."""
    df = _valid_df()
    df["unexpected"] = pd.array(["x"], dtype="string")

    with pytest.raises(pa.errors.SchemaErrors):
        FACT_FAILURES.schema.validate(df)


@pytest.mark.unit
def test_duplicate_composite_pk_raises() -> None:
    """C5: (run_id, failed_at_utc, stage) duplicado reprova via unique composto."""
    df = pd.concat([_valid_df(), _valid_df()], ignore_index=True)

    with pytest.raises(pa.errors.SchemaError):
        FACT_FAILURES.schema.validate(df)


@pytest.mark.unit
def test_null_pk_raises() -> None:
    """C5: stage nulo (nullable=False) reprova."""
    df = _valid_df()
    df["stage"] = pd.array([None], dtype="string")

    with pytest.raises(pa.errors.SchemaError):
        FACT_FAILURES.schema.validate(df)


@pytest.mark.unit
def test_metadata_matches_contract() -> None:
    """A4/A6: metadata bate com o concept §4 — partição (asset,), append-only."""
    assert FACT_FAILURES.name == "fact_failures"
    assert FACT_FAILURES.logical_pk == ("run_id", "failed_at_utc", "stage")
    assert FACT_FAILURES.partition_by == ("asset",)
    assert FACT_FAILURES.update_policy == "append-only"
    assert FACT_FAILURES.schema_version == 1
