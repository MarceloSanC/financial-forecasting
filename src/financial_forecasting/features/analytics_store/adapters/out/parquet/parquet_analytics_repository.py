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

import numbers
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb
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
_DIM_RUN_TABLE = "dim_run"
_CREATED_AT_UTC = "created_at_utc"


# Colunas de partição que armazenam o sentinel `__none__` e devem voltar `None`.
_NULLABLE_PARTITION_COLS = frozenset({"parent_sweep_id"})


def _safe_partition(value: object) -> str:
    """Sanitiza um valor de partição (None/vazio → sentinela estável, como o old)."""
    if value is None:
        return _PARTITION_NONE
    text = str(value).strip()
    return text if text else _PARTITION_NONE


def _quote_ident(name: str) -> str:
    """Cita um identificador SQL (DuckDB) escapando aspas duplas embutidas."""
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def _restore_value(key: str, value: object) -> object:
    """`NaN`/`__none__` → `None` (round-trip do sentinel de partição, I6/C6)."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if key in _NULLABLE_PARTITION_COLS and value == _PARTITION_NONE:
        return None
    return value


def _materialize_nullable_int(values: list[object], index: pd.Index) -> pd.Series | None:
    """Materializa uma coluna `Int64` (nullable) SEM afrouxar o gate de escrita.

    Recebe os valores CRUS das linhas, não a coluna do `DataFrame`: o pandas
    infere `[None, 3]` como `float64` (`[nan, 3.0]`), e depois disso um `int`
    genuíno não se distingue de um `3.0` float (issue #119). Converte apenas
    quando TODOS os valores são inteiros genuínos (`numbers.Integral`, que
    inclui os inteiros do numpy, sem `bool`) ou `None`; qualquer outro tipo
    (`"42"` str, `4.0` float) devolve `None` e a coluna inferida fica para o
    pandera reprovar com `SchemaError` (dtype estrito, `coerce=False`). Linha sem
    a chave conta como `None` (o chamador lê `row.get`), como nas demais colunas
    nullable do schema.
    """
    strict_ints = all(
        value is None or (isinstance(value, numbers.Integral) and not isinstance(value, bool))
        for value in values
    )
    if not strict_ints:
        return None
    return pd.Series(pd.array(values, dtype="Int64"), index=index)


def _temp_path(path: Path) -> Path:
    """Arquivo temporário da gravação atômica, ao lado do destino.

    O sufixo `.tmp-<pid>` NÃO casa com o glob de leitura (`**/*.parquet`) nem com
    a checagem de vazio (`rglob("*.parquet")`): um temporário deixado por uma
    queda nunca é lido como dado (ADR 5.5.0003).
    """
    return path.with_name(f"{path.name}.tmp-{os.getpid()}")


def _remove_stale_temps(path: Path) -> None:
    """Remove temporários de gravações anteriores interrompidas desta partição."""
    for stale in path.parent.glob(f"{path.name}.tmp-*"):
        stale.unlink(missing_ok=True)


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    """Grava um `DataFrame` como Parquet via pyarrow (sem índice), de forma atômica.

    Grava num temporário no mesmo diretório e troca por `os.replace` (atômico no
    mesmo sistema de arquivos): uma queda no meio da regravação de uma partição
    deixa o arquivo anterior intacto em vez de truncar linhas de unidades já
    concluídas que dividem o mesmo arquivo (ADR 5.5.0003, D12 da Stage 5.5).

    Escopo da garantia: atomicidade contra queda do PROCESSO. Não há `fsync`
    antes da troca, então queda de energia/VM pode, em alguns sistemas de
    arquivos, persistir o rename antes dos dados — a retomada do cohort reconfere
    as contagens no silver (ADR 5.5.0003) e acusa esse caso.
    """
    table = pa.Table.from_pandas(df, preserve_index=False)
    temp = _temp_path(path)
    try:
        pq.write_table(table, temp)  # type: ignore[no-untyped-call]
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


class ParquetAnalyticsRepository:
    """Implementação do contrato `AnalyticsRepository` sobre pyarrow + duckdb + pandera.

    Satisfaz também, por duck typing, o port `SilverTableReader` do `evaluation` (o
    `read` filtrado por partição; ADR 0.0.0053, ADR 6.4.0004).
    """

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

        prepared = [self._fill_write_time(table, row) for row in rows]
        incoming = pd.DataFrame(prepared)
        # Colunas de extensão nullable `Int64` (ex.: `seed` em dim_run):
        # materializa ANTES do validate — só int/None genuínos convertem; tipos
        # errados ("42" str, 4.0 float) permanecem e reprovam no pandera (gate
        # estrito, coerce=False). Sem a materialização, `seed=None` viraria
        # coluna object/null-type no Parquet e quebraria o merge por partição.
        for name, column in meta.schema.columns.items():
            if str(column.dtype) == "Int64" and name in incoming.columns:
                raw = [row.get(name) for row in prepared]
                materialized = _materialize_nullable_int(raw, incoming.index)
                if materialized is not None:
                    incoming[name] = materialized
        # pandera ANTES do disco (I4/C3): schema/dtype/PK inválido → SchemaError
        # (coluna extra sob strict=True levanta SchemaErrors — ambos são erros
        # pandera que abortam o write antes de tocar o Parquet). Espelha o
        # `ParquetMedallionStore` (`.validate(incoming)` sem `lazy`).
        meta.schema.validate(incoming)

        upsert = allow_upsert or meta.update_policy == _UPSERT_POLICY
        part_cols = meta.partition_by

        # Materializa o sentinel `__none__` na COLUNA FÍSICA das partições nullable
        # (após validar) para que path e coluna concordem e a coluna nunca seja
        # toda-NULL (DuckDB tiparia como NULL e o `WHERE col = ?` falharia). O
        # `read` reconverte `__none__` → `None` (round-trip I6/C6).
        for col in part_cols:
            if col in _NULLABLE_PARTITION_COLS:
                incoming[col] = incoming[col].map(_safe_partition)

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

    def _fill_write_time(self, table: str, row: Row) -> dict[str, object]:
        """Preenche `created_at_utc` write-time em `dim_run` via `Clock` (I5/OBS-1).

        O VO `RunRecord` não carrega `created_at_utc` (`nullable=False` no schema);
        o mapper `run_record_to_row` já o injeta para o caminho tipado, e aqui
        cobrimos o caminho genérico (`write` de uma row dict-like de `dim_run` sem
        a coluna) — paridade com o fake. NUNCA `datetime.now()` hardcoded.
        """
        prepared = dict(row)
        if table == _DIM_RUN_TABLE and prepared.get(_CREATED_AT_UTC) is None:
            prepared[_CREATED_AT_UTC] = self._clock.now().isoformat()
        return prepared

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
            _remove_stale_temps(path)
            _write_parquet(incoming, path)
            return

        _remove_stale_temps(path)

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

        Empurra `WHERE` para as colunas de `partition_by` vindas de `filters`
        (partition pruning, I8), projeta SÓ as colunas do schema na ordem do
        schema (não `SELECT *`), e reconverte o sentinel `__none__`/`NaN` de
        `parent_sweep_id` para `None` no round-trip (I6/C6). `(layer, table)`
        inexistente ou `asset` sem dados → sequência vazia (C4).
        """
        meta = self._table(layer, table)
        table_dir = self._table_dir(layer, table)

        # Dataset ainda não gravado → vazio (C4), sem tocar DuckDB.
        if not any(table_dir.rglob("*.parquet")):
            return []

        glob = str(table_dir / "**" / "*.parquet")
        predicates, params = self._build_predicates(meta, filters)
        where = f" WHERE {' AND '.join(predicates)}" if predicates else ""
        # As colunas de partição silver são FÍSICAS no Parquet (diferença vs
        # bronze, que as deriva): `hive_partitioning=false` evita coluna dupla;
        # projetar o schema garante a ordem/conjunto exato (fidelidade A7/A9).
        projection = ", ".join(_quote_ident(col) for col in meta.schema.columns)
        source = f"read_parquet('{glob}', hive_partitioning=false)"
        sql = f"SELECT {projection} FROM {source}{where}"

        con = duckdb.connect()
        try:
            con.execute("SET TimeZone='UTC'")  # timestamps tz-aware em UTC (D5)
            result_df = con.execute(sql, params).fetch_df()
        finally:
            con.close()

        return [self._restore_row(record) for record in result_df.to_dict(orient="records")]

    @staticmethod
    def _build_predicates(
        meta: SilverTable, filters: Mapping[str, object] | None
    ) -> tuple[list[str], list[object]]:
        """Monta o predicado de pruning a partir das colunas de partição em `filters`.

        Só colunas de `SilverTable.partition_by` viram `WHERE` (pruning); demais
        chaves de `filters` são ignoradas. `parent_sweep_id=None` casa com o
        sentinel `__none__` gravado no path/coluna.
        """
        wanted = dict(filters or {})
        predicates: list[str] = []
        params: list[object] = []
        for col in meta.partition_by:
            if col not in wanted:
                continue
            value = wanted[col]
            if value is None and col in _NULLABLE_PARTITION_COLS:
                predicates.append(f"({_quote_ident(col)} = ? OR {_quote_ident(col)} IS NULL)")
                params.append(_PARTITION_NONE)
            else:
                predicates.append(f"{_quote_ident(col)} = ?")
                params.append(value)
        return predicates, params

    @staticmethod
    def _restore_row(record: Mapping[str, object]) -> dict[str, object]:
        """`NaN`/`__none__` → `None` (round-trip do sentinel de partição, I6/C6)."""
        return {key: _restore_value(key, value) for key, value in record.items()}
