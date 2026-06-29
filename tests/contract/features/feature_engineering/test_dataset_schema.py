"""Contract test do `dataset_schema` pandera (Task 04) — contrato físico 62 colunas.

Cobre concept 3.5 I7 / C7/C8 / A5:

- happy path: `DataFrame` mínimo conforme valida (62 colunas, dtypes, ordem).
- C7: coluna ausente, dtype divergente, ordem trocada → `SchemaError`.
- C8: coluna extra → `SchemaError` (strict).
- set/ordem das features vem do `FeatureRegistry` (62 colunas; regimes float64 D2).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandera.pandas as pa
import pytest

from financial_forecasting.features.feature_engineering.adapters.out.parquet.schemas.dataset_schema import (  # noqa: E501
    DATASET_TFT_SCHEMA,
    dataset_column_order,
)
from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    list_feature_specs,
)

_INT64 = {"news_volume", "has_news", "volume_spike_flag", "day_of_week", "month", "time_idx"}
_UTC = {"timestamp", "fundamentals_effective_date"}

# pandera levanta `SchemaError` (singular) em falhas pontuais e `SchemaErrors`
# (plural, agregada) em violações de ordem/strict — ambas são falhas de schema.
_SCHEMA_FAILURE = (pa.errors.SchemaError, pa.errors.SchemaErrors)


def _conforming_frame(n: int = 3) -> pd.DataFrame:
    """`DataFrame` mínimo conforme ao schema (dtypes/ordem corretos)."""
    order = dataset_column_order()
    data: dict[str, object] = {}
    for col in order:
        if col == "asset_id":
            data[col] = pd.array(["AAPL"] * n, dtype="string")
        elif col in _UTC:
            data[col] = pd.to_datetime([f"2024-01-0{i + 1}" for i in range(n)], utc=True)
        elif col in _INT64:
            data[col] = np.arange(n, dtype="int64")
        else:
            data[col] = np.linspace(0.1, 1.0, n).astype("float64")
    return pd.DataFrame(data)[list(order)]


def test_schema_has_62_columns_in_registry_order() -> None:
    """A1/I7 — 62 colunas; bloco de feature na ordem do registry."""
    order = dataset_column_order()
    expected_cols = 62
    assert len(order) == expected_cols

    feature_names = tuple(spec.name for spec in list_feature_specs())
    # As features ocupam o bloco entre asset_id e fundamentals_effective_date.
    start = order.index("asset_id") + 1
    assert order[start : start + len(feature_names)] == feature_names


def test_conforming_dataframe_passes() -> None:
    """Happy path — `DataFrame` conforme valida sem erro."""
    DATASET_TFT_SCHEMA.validate(_conforming_frame())


def test_missing_column_raises_schema_error() -> None:
    """C7 — coluna ausente → `SchemaError`."""
    frame = _conforming_frame().drop(columns=["rsi_14"])
    with pytest.raises(pa.errors.SchemaError):
        DATASET_TFT_SCHEMA.validate(frame)


def test_extra_column_raises_schema_error() -> None:
    """C8 — coluna extra (strict) → `SchemaError`."""
    frame = _conforming_frame()
    frame["unexpected"] = 1.0
    with pytest.raises(_SCHEMA_FAILURE):
        DATASET_TFT_SCHEMA.validate(frame)


def test_wrong_dtype_raises_schema_error() -> None:
    """C7 — dtype divergente (target_return como string) → `SchemaError`."""
    frame = _conforming_frame()
    frame["target_return"] = frame["target_return"].astype("string")
    with pytest.raises(pa.errors.SchemaError):
        DATASET_TFT_SCHEMA.validate(frame)


def test_wrong_order_raises_schema_error() -> None:
    """C7 — ordem de colunas trocada (ordered=True) → `SchemaError`."""
    frame = _conforming_frame()
    cols = list(frame.columns)
    cols[1], cols[2] = cols[2], cols[1]  # troca asset_id <-> 1ª feature
    with pytest.raises(_SCHEMA_FAILURE):
        DATASET_TFT_SCHEMA.validate(frame[cols])


def test_regime_features_are_float64_nullable() -> None:
    """D2 / ADR 3.5.0002 — regimes/flags float64 nullable (NaN no warmup permitido)."""
    frame = _conforming_frame()
    for col in ("volatility_regime", "trend_regime", "stress_tail_return_flag"):
        frame.loc[0, col] = np.nan
    DATASET_TFT_SCHEMA.validate(frame)  # NaN no warmup não falha (nullable)
