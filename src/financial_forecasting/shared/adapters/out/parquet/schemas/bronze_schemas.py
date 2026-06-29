"""Schemas `pandera` bronze + registry `(layer, table)` (Stage 2.1).

Contratos de schema das três tabelas bronze — `candle`/`news`/`fundamental` —
espelhando EXATAMENTE os dtypes do raw real verificado em disco (concept 2.1 §9
/ ADR 2.1.0001): OHLC `float32`, `volume` `int64`, fundamentals `float64`, datas
`datetime64[ns, UTC]`, `reported_date` NULLABLE (o raw tem 17/81 `NaT`). Sem
essa fidelidade, as Stages 2.2/2.3 não conseguem reler o raw existente sem drift
de dtype.

Cada tabela é descrita por um `BronzeTable` (dataclass frozen, conceito do antigo
`AnalyticsTableSchema`) que pareia o `DataFrameSchema` `pandera` com sua metadata
de PK lógica e partição. As três tabelas formam o `BRONZE_REGISTRY`, chaveado por
`("bronze", <table>)`, sobre o qual o `ParquetMedallionStore` despacha.

Estes schemas vivem SÓ no adapter: o gate `import-linter` `store-no-storage-leak`
(Stage 2.1, task-03) reprova se `application`/`domain` importarem `pandera`.

Layout de partição em disco (ADR 2.1.0001):
    <root>/bronze/<table>/asset=<asset>/year=<year>/<table>.parquet
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandera.pandas as pa

# dtype literal de datetime UTC tz-aware (pandas). Strict no `pandera`: tz-naive
# ou outra tz é rejeitada (C3) — protege a fidelidade temporal do bronze.
_UTC_DT = "datetime64[ns, UTC]"


@dataclass(frozen=True)
class BronzeTable:
    """Metadata + schema de uma tabela bronze (concept §9 / ADR 2.1.0001).

    - `logical_pk`: colunas que formam a PK lógica (dedup append-only).
    - `asset_col`: coluna que identifica o ativo (`asset` em candle, `asset_id`
      em news/fundamental); sempre mapeada para a coluna de partição `asset`.
    - `year_anchor`: coluna temporal de onde o `year` da partição é derivado.
    - `partition_by`: colunas de partição em disco — sempre `(asset, year)`.
    - `update_policy`: política de atualização (somente `append-only` nesta Stage).
    - `schema`: `DataFrameSchema` `pandera` espelhando os dtypes reais.
    """

    name: str
    logical_pk: tuple[str, ...]
    asset_col: str
    year_anchor: str
    partition_by: tuple[str, ...]
    update_policy: str
    schema: pa.DataFrameSchema


# ---------------------------------------------------------------------------
# candle — OHLC float32, volume int64, timestamp UTC (4024 linhas reais AAPL)
# ---------------------------------------------------------------------------
_CANDLE_SCHEMA = pa.DataFrameSchema(
    {
        "asset": pa.Column(str, nullable=False),
        "timestamp": pa.Column(_UTC_DT, nullable=False),
        "open": pa.Column("float32", nullable=False),
        "high": pa.Column("float32", nullable=False),
        "low": pa.Column("float32", nullable=False),
        "close": pa.Column("float32", nullable=False),
        "volume": pa.Column("int64", nullable=False),
    },
    strict=True,
    coerce=False,
)

# ---------------------------------------------------------------------------
# news — 8 colunas string + published_at UTC (6921 linhas reais AAPL)
# ---------------------------------------------------------------------------
_NEWS_SCHEMA = pa.DataFrameSchema(
    {
        "asset_id": pa.Column(str, nullable=False),
        "article_id": pa.Column(str, nullable=False),
        "published_at": pa.Column(_UTC_DT, nullable=False),
        "headline": pa.Column(str, nullable=False),
        "summary": pa.Column(str, nullable=False),
        "source": pa.Column(str, nullable=False),
        "url": pa.Column(str, nullable=False),
        "language": pa.Column(str, nullable=False),
    },
    strict=True,
    coerce=False,
)

# ---------------------------------------------------------------------------
# fundamental — 5 floats float64, datas UTC, reported_date NULLABLE (81 linhas,
# 17 com NaT em reported_date — real, não hipotético: DEVE ser nullable)
# ---------------------------------------------------------------------------
_FUNDAMENTAL_SCHEMA = pa.DataFrameSchema(
    {
        "asset_id": pa.Column(str, nullable=False),
        "report_type": pa.Column(str, nullable=False),
        "fiscal_date_end": pa.Column(_UTC_DT, nullable=False),
        "reported_date": pa.Column(_UTC_DT, nullable=True),
        "revenue": pa.Column("float64", nullable=True),
        "net_income": pa.Column("float64", nullable=True),
        "operating_cash_flow": pa.Column("float64", nullable=True),
        "total_shareholder_equity": pa.Column("float64", nullable=True),
        "total_liabilities": pa.Column("float64", nullable=True),
        "source": pa.Column(str, nullable=False),
    },
    strict=True,
    coerce=False,
)


CANDLE = BronzeTable(
    name="candle",
    logical_pk=("asset", "timestamp"),
    asset_col="asset",
    year_anchor="timestamp",
    partition_by=("asset", "year"),
    update_policy="append-only",
    schema=_CANDLE_SCHEMA,
)

NEWS = BronzeTable(
    name="news",
    logical_pk=("asset_id", "article_id"),
    asset_col="asset_id",
    year_anchor="published_at",
    partition_by=("asset", "year"),
    update_policy="append-only",
    schema=_NEWS_SCHEMA,
)

FUNDAMENTAL = BronzeTable(
    name="fundamental",
    logical_pk=("asset_id", "report_type", "fiscal_date_end"),
    asset_col="asset_id",
    year_anchor="fiscal_date_end",
    partition_by=("asset", "year"),
    update_policy="append-only",
    schema=_FUNDAMENTAL_SCHEMA,
)


BRONZE_LAYER = "bronze"

# Registry `(layer, table) -> BronzeTable` sobre o qual o adapter despacha.
# Um par fora deste registry é erro de aplicação (concept §6 C2).
BRONZE_REGISTRY: Mapping[tuple[str, str], BronzeTable] = {
    (BRONZE_LAYER, CANDLE.name): CANDLE,
    (BRONZE_LAYER, NEWS.name): NEWS,
    (BRONZE_LAYER, FUNDAMENTAL.name): FUNDAMENTAL,
}
