"""Unit test do schema silver `fact_oos_predictions` LONGO (Stage 4.1, task-07).

Prova (concept 4.1 A5/A8/I5 / H-1 / C1-C5): payload VÁLIDO com >=2 níveis de quantil
para a mesma decisão passa; INVÁLIDOS reprovam (C1/C3/C4/C5); e — crucial para H-1 —
que NÃO há coluna `quantile_p*`, que `quantile_level` está na PK, partição
`(asset, feature_set_name, year)`, `append-only`.
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
import pytest

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.fact_oos_predictions_schema import (  # noqa: E501
    FACT_OOS_PREDICTIONS,
)

_VALID_ROWS = 3


def _valid_df() -> pd.DataFrame:
    """3 linhas longas: mesma decisão (run/split/horizon/ts/target), 3 níveis de quantil."""
    levels = [0.1, 0.5, 0.9]
    return pd.DataFrame(
        {
            "schema_version": pd.array([1, 1, 1], dtype="int64"),
            "run_id": pd.array(["r-1"] * 3, dtype="string"),
            "model_version": pd.array(["tft_v1"] * 3, dtype="string"),
            "asset": pd.array(["AAPL"] * 3, dtype="string"),
            "feature_set_name": pd.array(["all"] * 3, dtype="string"),
            "split": pd.array(["test"] * 3, dtype="string"),
            "horizon": pd.array([1, 1, 1], dtype="int64"),
            "decision_idx": pd.array([100, 100, 100], dtype="int64"),
            "timestamp_utc": pd.array(["2024-01-02T00:00:00Z"] * 3, dtype="string"),
            "target_timestamp_utc": pd.array(["2024-01-03T00:00:00Z"] * 3, dtype="string"),
            "quantile_level": pd.array(levels, dtype="float64"),
            "value_raw": pd.array([-0.01, 0.0, 0.01], dtype="float64"),
            "value_guardrail": pd.array([-0.01, 0.0, 0.01], dtype="float64"),
            "guardrail_applied": pd.array([0, 0, 0], dtype="int64"),
            "year": pd.array([2024, 2024, 2024], dtype="int64"),
        }
    )


@pytest.mark.unit
def test_valid_long_payload_passes() -> None:
    """A8: payload longo com 3 níveis de quantil para a mesma decisão valida."""
    assert len(FACT_OOS_PREDICTIONS.schema.validate(_valid_df())) == _VALID_ROWS


@pytest.mark.unit
def test_missing_required_column_raises() -> None:
    """C1: coluna obrigatória ausente (quantile_level) reprova."""
    df = _valid_df().drop(columns=["quantile_level"])

    with pytest.raises((pa.errors.SchemaError, pa.errors.SchemaErrors)):
        FACT_OOS_PREDICTIONS.schema.validate(df)


@pytest.mark.unit
def test_wrong_dtype_raises() -> None:
    """C3: dtype divergente (quantile_level como string) reprova (coerce=False)."""
    df = _valid_df()
    df["quantile_level"] = df["quantile_level"].astype("string")

    with pytest.raises(pa.errors.SchemaError):
        FACT_OOS_PREDICTIONS.schema.validate(df)


@pytest.mark.unit
def test_extra_column_raises() -> None:
    """C4: coluna extra com strict=True reprova."""
    df = _valid_df()
    df["unexpected"] = pd.array([1.0, 2.0, 3.0], dtype="float64")

    with pytest.raises(pa.errors.SchemaErrors):
        FACT_OOS_PREDICTIONS.schema.validate(df)


@pytest.mark.unit
def test_duplicate_long_pk_raises() -> None:
    """C5: dois níveis de quantil iguais para a mesma decisão reprovam (PK longa)."""
    df = _valid_df()
    df.loc[1, "quantile_level"] = 0.1  # colide com a linha 0

    with pytest.raises(pa.errors.SchemaError):
        FACT_OOS_PREDICTIONS.schema.validate(df)


@pytest.mark.unit
def test_null_pk_raises() -> None:
    """C5: quantile_level nulo (nullable=False, na PK) reprova."""
    df = _valid_df()
    df["quantile_level"] = pd.array([None, 0.5, 0.9], dtype="float64")

    with pytest.raises(pa.errors.SchemaError):
        FACT_OOS_PREDICTIONS.schema.validate(df)


@pytest.mark.unit
def test_null_string_pk_column_raises() -> None:
    """C5: run_id (coluna string da PK longa, nullable=False) nulo reprova."""
    df = _valid_df()
    df["run_id"] = pd.array([None, "r-1", "r-1"], dtype="string")

    with pytest.raises(pa.errors.SchemaError):
        FACT_OOS_PREDICTIONS.schema.validate(df)


@pytest.mark.unit
def test_schema_version_mismatch_detectable() -> None:
    """C2: schema_version do payload != schema_version do contrato é detectável (A8)."""
    df = _valid_df()
    df["schema_version"] = pd.array([99, 99, 99], dtype="int64")

    assert (df["schema_version"] != FACT_OOS_PREDICTIONS.schema_version).all()


@pytest.mark.unit
def test_no_per_quantile_columns_in_schema() -> None:
    """A5/I5 (H-1): NENHUMA coluna quantile_p* no schema (anti-regressao do layout largo)."""
    columns = set(FACT_OOS_PREDICTIONS.schema.columns)

    assert not any(c.startswith("quantile_p") for c in columns), (
        f"colunas por quantil proibidas (H-1) no schema: "
        f"{sorted(c for c in columns if c.startswith('quantile_p'))}"
    )


@pytest.mark.unit
def test_quantile_level_in_logical_pk() -> None:
    """A5/I5: quantile_level participa da PK lógica (materializa o formato longo)."""
    assert "quantile_level" in FACT_OOS_PREDICTIONS.logical_pk


@pytest.mark.unit
def test_metadata_matches_contract() -> None:
    """A5/A6: partição (asset, feature_set_name, year), append-only, PK longa de 6 colunas."""
    assert FACT_OOS_PREDICTIONS.name == "fact_oos_predictions"
    assert FACT_OOS_PREDICTIONS.logical_pk == (
        "run_id",
        "split",
        "horizon",
        "timestamp_utc",
        "target_timestamp_utc",
        "quantile_level",
    )
    assert FACT_OOS_PREDICTIONS.partition_by == ("asset", "feature_set_name", "year")
    assert FACT_OOS_PREDICTIONS.update_policy == "append-only"
    assert FACT_OOS_PREDICTIONS.schema_version == 1
