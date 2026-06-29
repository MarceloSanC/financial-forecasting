"""Unit test da dataclass `SilverTable` (Stage 4.1, task-05).

Prova (concept 4.1 §4): `SilverTable` é frozen e carrega os 6 campos esperados
(`name`, `schema_version`, `logical_pk`, `partition_by`, `update_policy`, `schema`)
com os tipos certos, pareando metadata com um `pandera.DataFrameSchema`.
"""

from __future__ import annotations

import dataclasses

import pandera.pandas as pa
import pytest

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.silver_table import (  # noqa: E501
    SilverTable,
)


def _minimal_table() -> SilverTable:
    schema = pa.DataFrameSchema(
        {"run_id": pa.Column(str, nullable=False)},
        strict=True,
        coerce=False,
    )
    return SilverTable(
        name="probe",
        schema_version=1,
        logical_pk=("run_id",),
        partition_by=("asset",),
        update_policy="append-only",
        schema=schema,
    )


@pytest.mark.unit
def test_carries_six_fields_with_expected_types() -> None:
    """A SilverTable pareia metadata + schema pandera com os tipos esperados."""
    table = _minimal_table()

    assert table.name == "probe"
    assert table.schema_version == 1
    assert table.logical_pk == ("run_id",)
    assert table.partition_by == ("asset",)
    assert table.update_policy == "append-only"
    assert isinstance(table.schema, pa.DataFrameSchema)


@pytest.mark.unit
def test_silver_table_is_frozen() -> None:
    """A SilverTable é imutável — reatribuir um campo levanta FrozenInstanceError."""
    table = _minimal_table()

    with pytest.raises(dataclasses.FrozenInstanceError):
        table.name = "other"  # type: ignore[misc]


@pytest.mark.unit
def test_field_names_match_contract() -> None:
    """Os 6 campos do contrato (concept §4) estão exatamente declarados."""
    field_names = {f.name for f in dataclasses.fields(SilverTable)}

    assert field_names == {
        "name",
        "schema_version",
        "logical_pk",
        "partition_by",
        "update_policy",
        "schema",
    }
