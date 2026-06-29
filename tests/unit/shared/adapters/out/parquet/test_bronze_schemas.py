"""Unit test dos schemas `pandera` bronze + registry (Stage 2.1, task-06).

Prova que cada schema bronze (candle/news/fundamental) espelha os dtypes reais
(concept §9 / ADR 2.1.0001): um DataFrame com os dtypes corretos VALIDA;
`reported_date` com `NaT` é ACEITO (nullable, C3/I5); um DataFrame com dtype
errado (`volume` `float64`, `timestamp` tz-naive) FALHA. Também checa que o
`BRONZE_REGISTRY` tem exatamente as 3 chaves esperadas com PK/partição corretas.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pandera.pandas as pa
import pytest

from financial_forecasting.shared.adapters.out.parquet.schemas.bronze_schemas import (
    BRONZE_LAYER,
    BRONZE_REGISTRY,
    CANDLE,
    FUNDAMENTAL,
    NEWS,
)

_EXPECTED_TABLES = 3


def _candle_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "asset": pd.array(["AAPL"], dtype="string"),
            "timestamp": pd.to_datetime(["2024-01-02"], utc=True),
            "open": np.array([99.0], dtype="float32"),
            "high": np.array([101.0], dtype="float32"),
            "low": np.array([98.0], dtype="float32"),
            "close": np.array([100.0], dtype="float32"),
            "volume": np.array([1_000_000], dtype="int64"),
        }
    )


def _news_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "asset_id": pd.array(["AAPL"], dtype="string"),
            "article_id": pd.array(["a-1"], dtype="string"),
            "published_at": pd.to_datetime(["2024-03-01"], utc=True),
            "headline": pd.array(["h"], dtype="string"),
            "summary": pd.array(["s"], dtype="string"),
            "source": pd.array(["src"], dtype="string"),
            "url": pd.array(["http://x"], dtype="string"),
            "language": pd.array(["en"], dtype="string"),
        }
    )


def _fundamental_df(reported: object) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "asset_id": pd.array(["AAPL"], dtype="string"),
            "report_type": pd.array(["10-K"], dtype="string"),
            "fiscal_date_end": pd.to_datetime(["2024-03-31"], utc=True),
            "reported_date": pd.to_datetime([reported], utc=True),
            "revenue": np.array([1.0e9], dtype="float64"),
            "net_income": np.array([1.0e8], dtype="float64"),
            "operating_cash_flow": np.array([2.0e8], dtype="float64"),
            "total_shareholder_equity": np.array([3.0e8], dtype="float64"),
            "total_liabilities": np.array([4.0e8], dtype="float64"),
            "source": pd.array(["sec"], dtype="string"),
        }
    )


@pytest.mark.unit
def test_candle_schema_validates_correct_dtypes() -> None:
    """A2: candle com OHLC float32/volume int64/timestamp UTC valida."""
    validated = CANDLE.schema.validate(_candle_df())

    assert validated["volume"].dtype == np.int64
    assert validated["open"].dtype == np.float32


@pytest.mark.unit
def test_candle_schema_rejects_float_volume() -> None:
    """C3: `volume` float64 (em vez de int64) falha a validação."""
    df = _candle_df()
    df["volume"] = df["volume"].astype("float64")

    with pytest.raises(pa.errors.SchemaError):
        CANDLE.schema.validate(df)


@pytest.mark.unit
def test_candle_schema_rejects_tz_naive_timestamp() -> None:
    """C3: `timestamp` tz-naive (sem UTC) falha a validação."""
    df = _candle_df()
    df["timestamp"] = pd.to_datetime(["2024-01-02"])  # tz-naive

    with pytest.raises(pa.errors.SchemaError):
        CANDLE.schema.validate(df)


@pytest.mark.unit
def test_candle_schema_rejects_extra_column() -> None:
    """C3: coluna fora do schema (strict=True) falha a validação.

    Coluna extra em strict-mode levanta `SchemaErrors` (plural), enquanto um
    dtype errado levanta `SchemaError` (singular) — daí o tipo distinto aqui.
    """
    df = _candle_df()
    df["unexpected"] = [1]

    with pytest.raises(pa.errors.SchemaErrors):
        CANDLE.schema.validate(df)


@pytest.mark.unit
def test_news_schema_validates_string_columns() -> None:
    """A2: news com 8 strings + published_at UTC valida."""
    validated = NEWS.schema.validate(_news_df())

    assert len(validated) == 1


@pytest.mark.unit
def test_fundamental_schema_accepts_reported_date_value() -> None:
    """A2: fundamental com `reported_date` preenchido (float64 numéricos) valida."""
    validated = FUNDAMENTAL.schema.validate(_fundamental_df(datetime(2024, 5, 1, tzinfo=UTC)))

    assert validated["revenue"].dtype == np.float64


@pytest.mark.unit
def test_fundamental_schema_accepts_nat_reported_date() -> None:
    """C3/I5: `reported_date` `NaT` é ACEITO (nullable — o raw tem 17/81 NaT)."""
    validated = FUNDAMENTAL.schema.validate(_fundamental_df(pd.NaT))

    assert pd.isna(validated["reported_date"].iloc[0])


@pytest.mark.unit
def test_registry_has_three_bronze_tables() -> None:
    """O `BRONZE_REGISTRY` tem exatamente as 3 chaves bronze esperadas."""
    assert len(BRONZE_REGISTRY) == _EXPECTED_TABLES
    assert set(BRONZE_REGISTRY) == {
        (BRONZE_LAYER, "candle"),
        (BRONZE_LAYER, "news"),
        (BRONZE_LAYER, "fundamental"),
    }


@pytest.mark.unit
def test_registry_logical_pks_and_partition() -> None:
    """PKs lógicas e partição `(asset, year)` corretas por tabela (ADR 2.1.0001)."""
    assert BRONZE_REGISTRY[(BRONZE_LAYER, "candle")].logical_pk == ("asset", "timestamp")
    assert BRONZE_REGISTRY[(BRONZE_LAYER, "news")].logical_pk == ("asset_id", "article_id")
    assert BRONZE_REGISTRY[(BRONZE_LAYER, "fundamental")].logical_pk == (
        "asset_id",
        "report_type",
        "fiscal_date_end",
    )
    for table in BRONZE_REGISTRY.values():
        assert table.partition_by == ("asset", "year")
        assert table.update_policy == "append-only"


@pytest.mark.unit
def test_registry_year_anchors() -> None:
    """A âncora de `year` por tabela bate com a coluna temporal (ADR 2.1.0001)."""
    assert BRONZE_REGISTRY[(BRONZE_LAYER, "candle")].year_anchor == "timestamp"
    assert BRONZE_REGISTRY[(BRONZE_LAYER, "news")].year_anchor == "published_at"
    assert BRONZE_REGISTRY[(BRONZE_LAYER, "fundamental")].year_anchor == "fiscal_date_end"
