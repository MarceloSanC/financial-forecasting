"""Adapter `ParquetAnalyticsRepository` — implementação do port `AnalyticsRepository`.

Único lugar (com os schemas silver 4.1) do BC `analytics_store` que importa
`pandas`/`pyarrow`/`duckdb`/`pandera` (invariante I1; o gate `import-linter`
`store-no-storage-leak` reprova se vazar para `application`/`domain`). Implementa
o contrato `AnalyticsRepository` despachando por `SILVER_REGISTRY[("silver",
<table>)]` (4.1) — sem hard-coding tabela a tabela, sem reusar o
`ParquetMedallionStore` do bronze (adapter DEDICADO; concept 4.2 D2/ADR 4.2.0001):

- **write** (`pyarrow`): materializa as `rows` em `DataFrame`, valida com `pandera`
  (`strict=True`, `coerce=False`) ANTES de tocar o Parquet (I4/C3); particiona em
  Hive pelas **colunas literais** de `SilverTable.partition_by` (1..3 níveis,
  `None` → sentinel `__none__`) — **sem** derivar ano de âncora temporal como o
  bronze (I2/D2); agrupa em batch por partição (I7); para cada partição alvo, lê
  as PKs lógicas já gravadas, detecta colisão (append-only sem flag →
  `DuplicateKeyError`, C1; com `allow_upsert=True` ou `update_policy=="upsert"`
  substitui só as colididas, C5/I3) e grava o Parquet da partição.
- **read** (`duckdb`): partition pruning + projeção do schema + round-trip
  `__none__` → `None` (preenchido na task-05).

O mapper `RunRecord -> row` de `dim_run` injeta `created_at_utc` write-time via
`Clock` (I5/OBS-1; `mappers/run_record_mapper.py`). A raiz de dados (`data_root`)
e o `Clock` são INJETADOS (I10); o adapter é instanciado só no `composition_root`.
Layout em disco (concept 4.2 §9):
    <data_root>/silver/<table>/<part_col>=<val>/.../<table>.parquet
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.silver_registry import (  # noqa: E501
    SILVER_REGISTRY,
)
from financial_forecasting.shared.domain.exceptions.base import (
    ApplicationError,
    DuplicateKeyError,
)

if TYPE_CHECKING:
    from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.silver_table import (  # noqa: E501
        SilverTable,
    )
    from financial_forecasting.shared.application.ports.out.clock import Clock

Row = Mapping[str, object]

_PARTITION_NONE = "__none__"
_COLLISION_SAMPLE_SIZE = 5
_UPSERT_POLICY = "upsert"


def _safe_partition(value: object) -> str:
    """Sanitiza um valor de partição (None/vazio → sentinela estável, como o old)."""
    if value is None:
        return _PARTITION_NONE
    text = str(value).strip()
    return text if text else _PARTITION_NONE


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    """Grava um `DataFrame` como Parquet via pyarrow (sem índice)."""
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, path)  # type: ignore[no-untyped-call]


class ParquetAnalyticsRepository:
    """Implementação do contrato `AnalyticsRepository` sobre pyarrow + duckdb + pandera."""

    def __init__(self, *, data_root: Path | str, clock: Clock) -> None:
        self._data_root = Path(data_root)
        self._clock = clock

    # -- registry / paths ----------------------------------------------------

    @staticmethod
    def _table(layer: str, table: str) -> SilverTable:
        meta = SILVER_REGISTRY.get((layer, table))
        if meta is None:
            raise ApplicationError(
                f"Unknown silver (layer, table)=({layer!r}, {table!r}); "
                f"supported: {sorted(SILVER_REGISTRY)}"
            )
        return meta

    def _table_dir(self, layer: str, table: str) -> Path:
        return self._data_root / layer / table

    def _partition_path(
        self, layer: str, table: str, partition_values: tuple[str, ...], part_cols: tuple[str, ...]
    ) -> Path:
        path = self._table_dir(layer, table)
        for col, value in zip(part_cols, partition_values, strict=True):
            path = path / f"{col}={value}"
        return path / f"{table}.parquet"

    # -- validação -----------------------------------------------------------

    @staticmethod
    def _pk_tuples(df: pd.DataFrame, pk_cols: tuple[str, ...]) -> set[tuple[object, ...]]:
        return set(df.loc[:, list(pk_cols)].itertuples(index=False, name=None))

    # -- write ---------------------------------------------------------------

    def write(
        self,
        *,
        layer: str,
        table: str,
        rows: Sequence[Row],
        allow_upsert: bool = False,
    ) -> None:
        """Grava `rows` append-only, particionado por colunas literais (ver port)."""
        meta = self._table(layer, table)
        if not rows:
            return

        incoming = pd.DataFrame([dict(r) for r in rows])
        # pandera ANTES do disco (I4/C3): schema/dtype/PK inválido → SchemaError
        # (coluna extra sob strict=True levanta SchemaErrors — ambos são erros
        # pandera que abortam o write antes de tocar o Parquet). Espelha o
        # `ParquetMedallionStore` (`.validate(incoming)` sem `lazy`).
        meta.schema.validate(incoming)

        upsert = allow_upsert or meta.update_policy == _UPSERT_POLICY
        part_cols = meta.partition_by

        # Bucket por partição (colunas literais) — batch-por-partição (I7).
        part_series = [incoming[col].map(_safe_partition) for col in part_cols]
        incoming = incoming.assign(**{f"_part_{i}": series for i, series in enumerate(part_series)})
        group_keys = [f"_part_{i}" for i in range(len(part_cols))]
        for raw_key, group in incoming.groupby(group_keys, dropna=False):
            key_tuple = raw_key if isinstance(raw_key, tuple) else (raw_key,)
            partition_values = tuple(str(v) for v in key_tuple)
            bucket = group.drop(columns=group_keys)
            self._write_partition(
                meta, layer, table, partition_values, part_cols, bucket, upsert=upsert
            )

    def _write_partition(  # noqa: PLR0913 — args coesos de uma partição alvo
        self,
        meta: SilverTable,
        layer: str,
        table: str,
        partition_values: tuple[str, ...],
        part_cols: tuple[str, ...],
        incoming: pd.DataFrame,
        *,
        upsert: bool,
    ) -> None:
        path = self._partition_path(layer, table, partition_values, part_cols)
        pk_cols = meta.logical_pk

        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_parquet(incoming, path)
            return

        current = pd.read_parquet(path)
        collisions = self._pk_tuples(current, pk_cols) & self._pk_tuples(incoming, pk_cols)

        if collisions and not upsert:
            sample = sorted(collisions, key=str)[:_COLLISION_SAMPLE_SIZE]
            raise DuplicateKeyError(
                f"Duplicate logical PK collision in ({layer}, {table}): "
                f"pk_columns={pk_cols} collisions={sample} path={path}"
            )

        if collisions:
            current_pk = pd.MultiIndex.from_frame(current.loc[:, list(pk_cols)])
            collision_index = pd.MultiIndex.from_tuples(list(collisions), names=list(pk_cols))
            current = current.loc[~current_pk.isin(collision_index)]

        merged = pd.concat([current, incoming], ignore_index=True)
        _write_parquet(merged, path)

    # -- read ----------------------------------------------------------------

    def read(
        self,
        *,
        layer: str,
        table: str,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Row]:
        """Lê o dataset filtrado por partição (`filters`); inexistente → vazio.

        Implementado na task-05 (pruning + projeção + round-trip `__none__`).
        """
        raise NotImplementedError
