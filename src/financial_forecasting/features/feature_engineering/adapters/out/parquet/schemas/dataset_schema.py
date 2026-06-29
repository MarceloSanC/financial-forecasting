"""Schema `pandera` do dataset TFT — contrato físico das 62 colunas (Stage 3.5).

Valida o `DataFrame` montado pelo `DatasetAssembler` ANTES de persistir: presença,
ordem e dtypes das colunas-base + identificador + o set de features do
`FeatureRegistry` (3.4) na ORDEM do registry (I7) + a cauda fixa
(`fundamentals_effective_date`/`day_of_week`/`month`/`target_return`/`time_idx`).

Confinado a `adapters/out` (I6): `pandera`/`pandas` só aqui — o gate
`store-no-storage-leak` reprova `pandera` em `application`/`domain`. **Sem** regra de
negócio: unicidade/monotonia/warmup/missing ficam no `DatasetQualityGate` (domain).
O schema cobre só o contrato FÍSICO (colunas/dtypes/ordem), `strict + ordered` →
coluna ausente, extra, dtype divergente ou ordem trocada ⇒ `SchemaError` (C7/C8).

Dtype de armazenamento por feature (a fonte é o que o assembler PRODUZ = o oráculo
`data/processed/dataset_tft/AAPL/...parquet`, não a declaração lógica do registry):

- `news_volume`/`has_news`/`volume_spike_flag` → `int64` (contagens/flags inteiras).
- `volatility_regime`/`trend_regime`/`stress_tail_return_flag` → `float64` com `NaN`
  no warmup (D2 / ADR 3.5.0002), apesar de o registry declarar `int64`.
- demais features → `float64`.

O set e a ORDEM das colunas de feature vêm de `list_feature_specs()` (registry,
fonte única, I7) — sem lista paralela hardcoded.
"""

from __future__ import annotations

import pandera.pandas as pa

from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    list_feature_specs,
)

# dtype literal de datetime UTC tz-aware (pandas), igual ao bronze (2.1).
_UTC_DT = "datetime64[ns, UTC]"

# Features de armazenamento int64 (contagens/flags inteiras — paridade oráculo).
# Exposta (pública) para o `DatasetAssembler` casar a montagem ao contrato físico
# (fonte única do conjunto de features int64; evita lista paralela divergente).
INT64_STORAGE_FEATURES: frozenset[str] = frozenset({"news_volume", "has_news", "volume_spike_flag"})
_INT64_FEATURES: frozenset[str] = INT64_STORAGE_FEATURES
# Features que o registry declara int64 mas o dataset armazena float64 (D2 / ADR
# 3.5.0002): regimes/flags carregam `NaN` no warmup → promoção a float.
_FLOAT64_OVERRIDE: frozenset[str] = frozenset(
    {"volatility_regime", "trend_regime", "stress_tail_return_flag"}
)


def _feature_storage_dtype(name: str, registry_dtype: str) -> str:
    """Resolve o dtype de ARMAZENAMENTO de uma feature (oráculo, não registry)."""
    if name in _INT64_FEATURES:
        return "int64"
    if name in _FLOAT64_OVERRIDE:
        return "float64"
    return "float64" if registry_dtype == "float64" else registry_dtype


def _feature_columns() -> dict[str, pa.Column]:
    """Colunas de feature na ordem do registry (I7), com dtype de armazenamento."""
    columns: dict[str, pa.Column] = {}
    for spec in list_feature_specs():
        dtype = _feature_storage_dtype(spec.name, spec.dtype)
        # Features carregam `NaN` no warmup (exceto as int64, sem warmup → não-nulas).
        nullable = dtype != "int64"
        columns[spec.name] = pa.Column(dtype, nullable=nullable, required=True)
    return columns


def _build_schema() -> pa.DataFrameSchema:
    """Monta o schema completo: base + features (registry) + cauda fixa, ordenado."""
    columns: dict[str, pa.Column] = {
        "timestamp": pa.Column(_UTC_DT, nullable=False, required=True),
        "asset_id": pa.Column(str, nullable=False, required=True),
    }
    columns.update(_feature_columns())
    columns["fundamentals_effective_date"] = pa.Column(_UTC_DT, nullable=True, required=True)
    columns["day_of_week"] = pa.Column("int64", nullable=False, required=True)
    columns["month"] = pa.Column("int64", nullable=False, required=True)
    columns["target_return"] = pa.Column("float64", nullable=False, required=True)
    columns["time_idx"] = pa.Column("int64", nullable=False, required=True)
    return pa.DataFrameSchema(columns, strict=True, ordered=True, coerce=False)


# Schema imutável do dataset TFT (62 colunas — paridade de set/contagem com o oráculo).
DATASET_TFT_SCHEMA: pa.DataFrameSchema = _build_schema()


def dataset_column_order() -> tuple[str, ...]:
    """Ordem canônica das 62 colunas do dataset (governada pelo registry, I7)."""
    return tuple(DATASET_TFT_SCHEMA.columns.keys())
