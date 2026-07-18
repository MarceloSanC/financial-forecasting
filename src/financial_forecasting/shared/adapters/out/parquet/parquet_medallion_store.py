"""Adapter `ParquetMedallionStore` — implementação concreta do port `MedallionStore`.

Único lugar (com os schemas bronze) que importa `pandas`/`pyarrow`/`duckdb`/
`pandera` (invariante I4; o gate `import-linter` `store-no-storage-leak` reprova
se vazar para `application`/`domain`). Implementa o contrato `MedallionStore`:

- **write** (`pyarrow`): materializa as `rows` em `DataFrame`, coage os dtypes
  para o schema bronze do `(layer, table)` e valida com `pandera` (C3); deriva o
  `year` da âncora temporal; agrupa em batch por partição Hive
  (`asset=<asset>/year=<year>`); para cada partição alvo, lê as PKs lógicas já
  gravadas, detecta colisão (sem `overwrite` → `DuplicateKeyError`, C1; com
  `overwrite=True` substitui as colididas, I2) e grava o Parquet da partição.
- **read** (`duckdb`): monta um `SELECT` das colunas DECLARADAS no schema bronze
  (não `SELECT *`) sobre o glob Hive da tabela, com `WHERE` nas colunas de
  partição vindas de `filters` (partition pruning, I7); dataset/asset inexistente
  → sequência vazia (C4). Projetar só o schema dropa as colunas de partição que o
  `hive_partitioning` materializa mas não pertencem ao schema (o `asset` em news/
  fundamental, cuja coluna lógica é `asset_id`) — sem isso o `read` devolveria uma
  coluna fantasma, quebrando a paridade fake↔real (I6) e a fidelidade de schema
  (A5/A6). Sessão DuckDB com `TimeZone='UTC'` para devolver timestamps tz-aware em
  UTC (fidelidade temporal, I5).

A raiz de dados (`data_root`) é INJETADA (não hardcoded, I8); o adapter é
instanciado só no `composition_root` (I9). Layout em disco (ADR 2.1.0001):
    <data_root>/bronze/<table>/asset=<asset>/year=<year>/<table>.parquet

Stage 5.2 (Task 04, concept D3): o par **read-only** `("processed",
"dataset_tft")` entra num registry read-only próprio (fora do `BRONZE_REGISTRY`
pandera — o contrato físico do dataset é da 3.5). O `read` resolve o layout já
existente por diretório de asset (NÃO Hive):
    <data_root>/processed/dataset_tft/<asset>/dataset_tft_<asset>.parquet
com `SELECT *` sem `hive_partitioning` (não há coluna de partição fantasma),
sessão DuckDB `TimeZone='UTC'` e normalização NaN → None como no read bronze;
dataset/asset inexistente → vazio (C4). `write` no par ergue `ApplicationError`
("read-only") — a semântica de escrita bronze fica intacta.

Disciplina de filtro do par read-only (paridade fake↔real no contract test):
`filters={"asset": None}` equivale a filtro ausente (união dos assets); o valor
de `asset` é validado contra `^[A-Za-z0-9._-]+$` ANTES de interpolar no
glob/SQL (sem separadores de path — `ValueError` se violar); qualquer chave de
filtro diferente de `asset` ergue `ValueError` em vez de ser ignorada
silenciosamente.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from financial_forecasting.shared.adapters.out.parquet.schemas.bronze_schemas import (
    BRONZE_REGISTRY,
    BronzeTable,
)
from financial_forecasting.shared.domain.exceptions.base import (
    ApplicationError,
    DuplicateKeyError,
)

Row = Mapping[str, object]

_PARTITION_NONE = "__none__"
_COLLISION_SAMPLE_SIZE = 5
# Registry read-only (Stage 5.2 D3): pares legíveis pelo port cujo layout físico
# é diretório-por-asset (3.5), NÃO Hive; `write` neles ergue ApplicationError.
_READ_ONLY_PAIRS: frozenset[tuple[str, str]] = frozenset({("processed", "dataset_tft")})
# Valor de filtro `asset` interpolado em glob/SQL: conservador, sem separadores
# de path (disciplina de interpolação do par read-only).
_READ_ONLY_ASSET_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_read_only_filters(
    layer: str, table: str, filters: Mapping[str, object] | None
) -> str | None:
    """Valida o filtro do par read-only e devolve o `asset` (ou None ≡ união).

    `asset=None` equivale a filtro ausente; chave ≠ `asset` ergue `ValueError`
    (nunca ignora silenciosamente); valor fora de `^[A-Za-z0-9._-]+$` ergue
    ANTES de qualquer interpolação em glob/SQL.
    """
    wanted = dict(filters or {})
    unsupported = sorted(set(wanted) - {"asset"})
    if unsupported:
        raise ValueError(
            f"read-only pair ({layer!r}, {table!r}) supports only the 'asset' "
            f"filter; got unsupported keys {unsupported}"
        )
    asset_val = wanted.get("asset")
    if asset_val is None:
        return None
    asset = str(asset_val)
    if not _READ_ONLY_ASSET_PATTERN.fullmatch(asset):
        raise ValueError(
            f"read-only pair ({layer!r}, {table!r}) asset filter must match "
            f"{_READ_ONLY_ASSET_PATTERN.pattern!r}; got {asset!r}"
        )
    return asset


def _safe_partition(value: object) -> str:
    """Sanitiza um valor de partição (None/vazio → sentinela estável, como o old)."""
    if value is None:
        return _PARTITION_NONE
    text = str(value).strip()
    return text if text else _PARTITION_NONE


def _quote_ident(name: str) -> str:
    """Cita um identificador SQL (DuckDB) escapando aspas duplas embutidas.

    Projetar colunas do schema por nome no `read` exige citar para tolerar nomes
    que colidem com keywords (ex.: `open`) sem depender da heurística do parser.
    """
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    """Grava um `DataFrame` como Parquet via pyarrow (sem índice)."""
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, path)  # type: ignore[no-untyped-call]


def _frame_to_rows(result_df: pd.DataFrame) -> list[Row]:
    """Materializa o resultado DuckDB como rows dict-like, normalizando NaN → None."""
    return [
        {k: (None if pd.isna(v) else v) for k, v in record.items()}
        for record in result_df.to_dict(orient="records")
    ]


class ParquetMedallionStore:
    """Implementação do contrato `MedallionStore` sobre pyarrow + duckdb + pandera."""

    def __init__(self, data_root: Path | str) -> None:
        self._data_root = Path(data_root)

    # -- registry / paths ----------------------------------------------------

    @staticmethod
    def _table(layer: str, table: str) -> BronzeTable:
        meta = BRONZE_REGISTRY.get((layer, table))
        if meta is None:
            raise ApplicationError(
                f"Unknown medallion (layer, table)=({layer!r}, {table!r}); "
                f"supported: {sorted(BRONZE_REGISTRY)}"
            )
        return meta

    def _table_dir(self, layer: str, table: str) -> Path:
        return self._data_root / layer / table

    def _partition_path(self, layer: str, table: str, asset: str, year: str) -> Path:
        return (
            self._table_dir(layer, table) / f"asset={asset}" / f"year={year}" / f"{table}.parquet"
        )

    # -- coerção / validação -------------------------------------------------

    @staticmethod
    def _coerce(df: pd.DataFrame, meta: BronzeTable) -> pd.DataFrame:
        """Coage os dtypes do `df` para o schema bronze antes de validar.

        Rows chegam como dict-like (floats Python viram float64, ints int64);
        coagimos para os dtypes EXATOS do schema (float32, UTC, etc.) para que a
        validação `pandera` (coerce=False) passe e o Parquet preserve os dtypes.
        Datetimes usam `to_datetime(utc=True)` — `.astype` falha em coluna
        all-NaT tz-naive (ex.: `reported_date`).
        """
        coerced = df.copy()
        for name, column in meta.schema.columns.items():
            dtype = str(column.dtype)
            if dtype.startswith("datetime64"):
                coerced[name] = pd.to_datetime(coerced[name], utc=True)
            elif dtype == "str":
                coerced[name] = coerced[name].astype("string")
            else:
                coerced[name] = coerced[name].astype(dtype)
        return coerced

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
        overwrite: bool = False,
    ) -> None:
        """Grava `rows` append-only, particionado por asset/year (ver port)."""
        if (layer, table) in _READ_ONLY_PAIRS:
            raise ApplicationError(
                f"Medallion pair ({layer!r}, {table!r}) is read-only; "
                "write is not supported (Stage 5.2 D3)"
            )
        meta = self._table(layer, table)
        if not rows:
            return

        incoming = self._coerce(pd.DataFrame([dict(r) for r in rows]), meta)
        meta.schema.validate(incoming)  # C3 — rejeita schema/dtype inválido

        # year derivado da âncora temporal (já UTC após coerção).
        year_series = incoming[meta.year_anchor].dt.year
        asset_series = incoming[meta.asset_col].astype("string")

        # Bucket por partição (asset, year) — batch-por-partição (nunca linha-a-linha).
        incoming = incoming.assign(_asset_part=asset_series, _year_part=year_series)
        for (asset_val, year_val), group in incoming.groupby(
            ["_asset_part", "_year_part"], dropna=False
        ):
            asset = _safe_partition(asset_val)
            year = _safe_partition(int(year_val) if pd.notna(year_val) else None)
            bucket = group.drop(columns=["_asset_part", "_year_part"])
            self._write_partition(meta, layer, table, asset, year, bucket, overwrite)

    def _write_partition(  # noqa: PLR0913 — args coesos de uma partição alvo
        self,
        meta: BronzeTable,
        layer: str,
        table: str,
        asset: str,
        year: str,
        incoming: pd.DataFrame,
        overwrite: bool,
    ) -> None:
        path = self._partition_path(layer, table, asset, year)
        pk_cols = meta.logical_pk

        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_parquet(incoming, path)
            return

        current = self._coerce(pd.read_parquet(path), meta)
        collisions = self._pk_tuples(current, pk_cols) & self._pk_tuples(incoming, pk_cols)

        if collisions and not overwrite:
            sample = sorted(collisions, key=str)[:_COLLISION_SAMPLE_SIZE]
            raise DuplicateKeyError(
                f"Duplicate logical PK collision in ({layer}, {table}): "
                f"pk_columns={pk_cols} collisions={sample} path={path}"
            )

        if collisions:
            current_pk = pd.MultiIndex.from_frame(current.loc[:, list(pk_cols)])
            collision_index = pd.MultiIndex.from_tuples(list(collisions), names=list(pk_cols))
            current = current.loc[~current_pk.isin(collision_index)]

        merged = self._coerce(pd.concat([current, incoming], ignore_index=True), meta)
        _write_parquet(merged, path)

    # -- read ----------------------------------------------------------------

    def read(
        self,
        *,
        layer: str,
        table: str,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Row]:
        """Lê o dataset filtrado por partição (`filters`); inexistente → vazio."""
        if (layer, table) in _READ_ONLY_PAIRS:
            return self._read_read_only(layer, table, filters)
        meta = self._table(layer, table)
        table_dir = self._table_dir(layer, table)
        glob = str(table_dir / "**" / "*.parquet")

        # Dataset ainda não gravado → vazio (C4), sem tocar DuckDB.
        if not any(table_dir.rglob("*.parquet")):
            return []

        predicates, params = self._build_predicates(meta, filters)
        where = f" WHERE {' AND '.join(predicates)}" if predicates else ""
        # Projeta SÓ as colunas declaradas no schema bronze (não `SELECT *`): o
        # `hive_partitioning` materializa as colunas de partição `asset` e `year`,
        # e para news/fundamental (coluna lógica `asset_id`) o `asset` da partição
        # NÃO está no schema — seria uma coluna fantasma no `read`, quebrando a
        # paridade fake↔real (I6) e a fidelidade de schema (A5/A6). Projetar as
        # colunas do schema dropa o fantasma e mantém `WHERE asset = ?` válido
        # (a partição segue disponível para pruning, só não é selecionada).
        projection = ", ".join(_quote_ident(col) for col in meta.schema.columns)
        source = f"read_parquet('{glob}', hive_partitioning=true)"
        sql = f"SELECT {projection} FROM {source}{where}"

        con = duckdb.connect()
        try:
            con.execute("SET TimeZone='UTC'")  # timestamps tz-aware em UTC (I5)
            result_df = con.execute(sql, params).fetch_df()
        finally:
            con.close()

        return _frame_to_rows(result_df)

    def _read_read_only(
        self, layer: str, table: str, filters: Mapping[str, object] | None
    ) -> Sequence[Row]:
        """Lê um par read-only no layout diretório-por-asset da 3.5 (sem Hive).

        Com `filters={"asset": ...}` o glob é `<table>/<asset>/*.parquet`; sem
        filtro (ou `asset=None` ≡ ausente), `<table>/**/*.parquet` (união dos
        assets). O filtro passa por `_validate_read_only_filters` ANTES de
        qualquer interpolação (chave ≠ `asset` ou valor fora do padrão ergue).
        `SELECT *` sem `hive_partitioning` (não há coluna de partição fantasma
        aqui); sessão DuckDB `TimeZone='UTC'`; NaN → None como no read bronze;
        dataset/asset inexistente → vazio (C4).
        """
        table_dir = self._table_dir(layer, table)
        asset = _validate_read_only_filters(layer, table, filters)

        if asset is not None:
            scope_dir = table_dir / asset
            glob = str(scope_dir / "*.parquet")
            if not any(scope_dir.glob("*.parquet")):
                return []
        else:
            glob = str(table_dir / "**" / "*.parquet")
            if not any(table_dir.rglob("*.parquet")):
                return []

        con = duckdb.connect()
        try:
            con.execute("SET TimeZone='UTC'")  # timestamps tz-aware em UTC
            result_df = con.execute(f"SELECT * FROM read_parquet('{glob}')").fetch_df()
        finally:
            con.close()

        return _frame_to_rows(result_df)

    @staticmethod
    def _build_predicates(
        meta: BronzeTable, filters: Mapping[str, object] | None
    ) -> tuple[list[str], list[object]]:
        """Monta o predicado de partition pruning a partir de `filters`.

        Aceita `{"asset": ...}` (coluna de partição sempre `asset`, mesmo quando
        a coluna lógica é `asset_id`) e, opcionalmente, `{"year": ...}`.
        """
        wanted = dict(filters or {})
        predicates: list[str] = []
        params: list[object] = []

        asset_val = wanted.get("asset", wanted.get(meta.asset_col))
        if asset_val is not None:
            predicates.append("asset = ?")
            params.append(str(asset_val))
        year_val = wanted.get("year")
        if year_val is not None:
            predicates.append("year = ?")
            params.append(int(str(year_val)))
        return predicates, params
