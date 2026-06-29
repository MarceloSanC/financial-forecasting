"""Unit test do schema silver `dim_run` (Stage 4.1, task-06).

Prova (concept 4.1 A4/A6/A8 / C1-C5): payload VÁLIDO passa; payloads INVÁLIDOS
levantam erro `pandera` — coluna obrigatória ausente (C1), dtype divergente (C3),
coluna extra com strict (C4), PK duplicada/nula (C5). `schema_version` mismatch (C2)
é checado comparando o valor do payload com `DIM_RUN.schema_version`. Também confere
a metadata (`logical_pk`/`partition_by`/`update_policy`/`schema_version`).
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
import pytest

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.dim_run_schema import (  # noqa: E501
    DIM_RUN,
)

_VALID_ROWS = 2


def _valid_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "schema_version": pd.array([1, 1], dtype="int64"),
            "run_id": pd.array(["r-1", "r-2"], dtype="string"),
            "asset": pd.array(["AAPL", "AAPL"], dtype="string"),
            "parent_sweep_id": pd.array(["sweep-1", None], dtype="string"),
            "feature_set_name": pd.array(["all", "all"], dtype="string"),
            "config_signature": pd.array(["c" * 64, "c" * 64], dtype="string"),
            "split_fingerprint": pd.array(["s" * 64, "s" * 64], dtype="string"),
            "fold": pd.array(["fold-0", None], dtype="string"),
            "seed": pd.array([42, None], dtype="Int64"),
            "model_version": pd.array(["tft_v1", "tft_v1"], dtype="string"),
            "created_at_utc": pd.array(
                ["2024-01-02T00:00:00Z", "2024-01-03T00:00:00Z"], dtype="string"
            ),
        }
    )


@pytest.mark.unit
def test_valid_payload_passes() -> None:
    """A8: payload válido (com opcionais nulos) valida."""
    validated = DIM_RUN.schema.validate(_valid_df())

    assert len(validated) == _VALID_ROWS


@pytest.mark.unit
def test_missing_required_column_raises() -> None:
    """C1: coluna obrigatória ausente (run_id) reprova."""
    df = _valid_df().drop(columns=["run_id"])

    with pytest.raises((pa.errors.SchemaError, pa.errors.SchemaErrors)):
        DIM_RUN.schema.validate(df)


@pytest.mark.unit
def test_wrong_dtype_raises() -> None:
    """C3: dtype divergente (schema_version como string) reprova (coerce=False)."""
    df = _valid_df()
    df["schema_version"] = df["schema_version"].astype("string")

    with pytest.raises(pa.errors.SchemaError):
        DIM_RUN.schema.validate(df)


@pytest.mark.unit
def test_extra_column_raises() -> None:
    """C4: coluna extra com strict=True reprova."""
    df = _valid_df()
    df["unexpected"] = pd.array(["x", "y"], dtype="string")

    with pytest.raises(pa.errors.SchemaErrors):
        DIM_RUN.schema.validate(df)


@pytest.mark.unit
def test_duplicate_pk_raises() -> None:
    """C5: run_id duplicado (PK) reprova via unique composto."""
    df = _valid_df()
    df.loc[1, "run_id"] = "r-1"

    with pytest.raises(pa.errors.SchemaError):
        DIM_RUN.schema.validate(df)


@pytest.mark.unit
def test_null_pk_raises() -> None:
    """C5: valor nulo em coluna de PK (nullable=False) reprova."""
    df = _valid_df()
    df["run_id"] = pd.array([None, "r-2"], dtype="string")

    with pytest.raises(pa.errors.SchemaError):
        DIM_RUN.schema.validate(df)


@pytest.mark.unit
def test_schema_version_mismatch_detectable() -> None:
    """C2: valor de schema_version do payload != schema_version do contrato é detectável."""
    df = _valid_df()
    df["schema_version"] = pd.array([99, 99], dtype="int64")

    assert (df["schema_version"] != DIM_RUN.schema_version).all()


@pytest.mark.unit
def test_metadata_matches_contract() -> None:
    """A4/A6: metadata bate com o concept §4 — dim_run é a única upsert."""
    assert DIM_RUN.name == "dim_run"
    assert DIM_RUN.logical_pk == ("run_id",)
    assert DIM_RUN.partition_by == ("asset", "parent_sweep_id")
    assert DIM_RUN.update_policy == "upsert"
    assert DIM_RUN.schema_version == 1
