"""Fake in-memory do port `MedallionStore` — NÃO um mock.

`FakeMedallionStore` aplica a MESMA semântica observável do adapter real
(`ParquetMedallionStore`): append-only com dedup por PK lógica (colisão sem
`overwrite` → `DuplicateKeyError`; com `overwrite=True` substitui as colididas),
particionamento por `asset`/`year` derivado do schema, filtro por partição no
`read`, e `read` de dataset/asset inexistente devolve vazio. Mantém as linhas em
memória por `(layer, table, asset, year)` para produzir COMPORTAMENTO real e
estável, não asserts de chamada.

O fake é stdlib-only (vive em `tests/`, fora do gate, mas mantém o contrato
agnóstico de `pandas`/`pyarrow`): carrega um registry-leve interno
(`_PK_BY_TABLE`/`_ANCHOR_BY_TABLE`/`_ASSET_COL_BY_TABLE`) que ESPELHA as mesmas
PKs lógicas e âncoras de partição do registry `pandera` do adapter (concept 2.1
§9 / ADR 2.1.0001), de modo que fake e real respondam idênticos ao MESMO contract
test (`tests/contract/shared/test_medallion_store_contract.py`, parametrizado
sobre `[fake, real]`). Levanta o MESMO `DuplicateKeyError` do real.

Stage 5.2 (Task 04, concept D3): o fake também suporta o par **read-only**
`("processed", "dataset_tft")` — `read` filtrado por `asset` (ou união sem
filtro), asset/dataset inexistente → vazio (C4) e `write` no par →
`ApplicationError` ("read-only"), espelhando o registry read-only do adapter
real. A semeadura acontece FORA do port, via o helper `seed_read_only`
(análogo, no fake, a gravar o Parquet direto no layout da 3.5). A disciplina de
filtro do par espelha o real: `asset=None` ≡ filtro ausente (união), valor de
`asset` fora de `^[A-Za-z0-9._-]+$` ergue `ValueError` (mesmo padrão que o real
valida antes de interpolar em glob/SQL) e chave de filtro ≠ `asset` ergue em
vez de ser ignorada silenciosamente.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime

from financial_forecasting.shared.domain.exceptions.base import (
    ApplicationError,
    DuplicateKeyError,
)

Row = Mapping[str, object]

# Registry-leve: espelha o registry pandera do adapter (ADR 2.1.0001). Mantido
# como dado puro (sem pandas) para o fake permanecer agnóstico de storage libs.
_PK_BY_TABLE: dict[str, tuple[str, ...]] = {
    "candle": ("asset", "timestamp"),
    "news": ("asset_id", "article_id"),
    "fundamental": ("asset_id", "report_type", "fiscal_date_end"),
}
_ANCHOR_BY_TABLE: dict[str, str] = {
    "candle": "timestamp",
    "news": "published_at",
    "fundamental": "fiscal_date_end",
}
_ASSET_COL_BY_TABLE: dict[str, str] = {
    "candle": "asset",
    "news": "asset_id",
    "fundamental": "asset_id",
}
_SUPPORTED_LAYER = "bronze"
# Pares read-only (Stage 5.2 D3): legíveis pelo port, write ergue ApplicationError.
_READ_ONLY_PAIRS: frozenset[tuple[str, str]] = frozenset({("processed", "dataset_tft")})
# Espelha o padrão de validação do adapter real (disciplina de interpolação).
_READ_ONLY_ASSET_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_PARTITION_NONE = "__none__"


def _safe_partition(value: object) -> str:
    """Sanitiza um valor de partição (None/vazio → sentinela estável, como o old)."""
    if value is None:
        return _PARTITION_NONE
    text = str(value).strip()
    return text if text else _PARTITION_NONE


def _year_of(value: object) -> str:
    """Deriva o ano (string) de uma âncora temporal; None/inválido → sentinela."""
    if isinstance(value, datetime):
        return str(value.year)
    if value is None:
        return _PARTITION_NONE
    # Aceita ISO-8601 ("2024-01-02..."); o prefixo de 4 dígitos é o ano.
    text = str(value).strip()
    if len(text) >= 4 and text[:4].isdigit():  # noqa: PLR2004 — 4 = dígitos do ano
        return text[:4]
    return _PARTITION_NONE


class FakeMedallionStore:
    """Implementação in-memory determinística do contrato `MedallionStore`."""

    def __init__(self) -> None:
        # (layer, table, asset, year) -> lista de rows (cópias defensivas).
        self._partitions: dict[tuple[str, str, str, str], list[dict[str, object]]] = {}
        # Pares read-only: (layer, table, asset) -> lista de rows semeadas.
        self._read_only: dict[tuple[str, str, str], list[dict[str, object]]] = {}

    # -- semeadura read-only (fora do port) -----------------------------------

    def seed_read_only(
        self, *, layer: str, table: str, asset: str, rows: Sequence[Row]
    ) -> None:
        """Semeia um par read-only in-memory (análogo a gravar o Parquet da 3.5).

        NÃO faz parte do port `MedallionStore` — existe para os testes popularem
        o dataset que o `write` (read-only) se recusa a gravar.
        """
        if (layer, table) not in _READ_ONLY_PAIRS:
            raise ApplicationError(
                f"seed_read_only only supports read-only pairs {sorted(_READ_ONLY_PAIRS)}; "
                f"got ({layer!r}, {table!r})"
            )
        bucket = self._read_only.setdefault((layer, table, asset), [])
        bucket.extend(dict(row) for row in rows)

    # -- helpers de schema ---------------------------------------------------

    @staticmethod
    def _require_known(layer: str, table: str) -> None:
        if layer != _SUPPORTED_LAYER or table not in _PK_BY_TABLE:
            raise ApplicationError(
                f"Unknown medallion (layer, table)=({layer!r}, {table!r}); "
                f"supported: {_SUPPORTED_LAYER} x {sorted(_PK_BY_TABLE)}"
            )

    @staticmethod
    def _pk_tuple(row: Row, pk_cols: tuple[str, ...]) -> tuple[object, ...]:
        return tuple(row.get(col) for col in pk_cols)

    def _partition_key(self, layer: str, table: str, row: Row) -> tuple[str, str, str, str]:
        asset_col = _ASSET_COL_BY_TABLE[table]
        anchor = _ANCHOR_BY_TABLE[table]
        asset = _safe_partition(row.get(asset_col))
        year = _year_of(row.get(anchor))
        return (layer, table, asset, year)

    # -- contrato ------------------------------------------------------------

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
        self._require_known(layer, table)
        if not rows:
            return
        pk_cols = _PK_BY_TABLE[table]

        # Agrupa o incoming em batch por partição (espelha batch-por-partição).
        buckets: dict[tuple[str, str, str, str], list[dict[str, object]]] = {}
        for row in rows:
            key = self._partition_key(layer, table, row)
            buckets.setdefault(key, []).append(dict(row))

        for key, incoming in buckets.items():
            current = self._partitions.get(key, [])
            current_keys = {self._pk_tuple(r, pk_cols) for r in current}
            incoming_keys = {self._pk_tuple(r, pk_cols) for r in incoming}
            collisions = current_keys & incoming_keys

            if collisions and not overwrite:
                sample = sorted(collisions, key=str)[:5]
                raise DuplicateKeyError(
                    f"Duplicate logical PK collision in ({layer}, {table}): "
                    f"pk_columns={pk_cols} collisions={sample}"
                )

            if collisions:
                kept = [r for r in current if self._pk_tuple(r, pk_cols) not in collisions]
            else:
                kept = list(current)
            self._partitions[key] = kept + incoming

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
        self._require_known(layer, table)
        asset_col = _ASSET_COL_BY_TABLE[table]
        wanted = dict(filters or {})

        # Normaliza o predicado de asset: aceita {"asset": ...} mesmo quando a
        # coluna real é `asset_id` (a coluna de partição é sempre `asset`).
        wanted_asset = None
        if "asset" in wanted:
            wanted_asset = _safe_partition(wanted["asset"])
        elif asset_col in wanted:
            wanted_asset = _safe_partition(wanted[asset_col])
        wanted_year = _safe_partition(wanted["year"]) if "year" in wanted else None

        result: list[Row] = []
        for (p_layer, p_table, p_asset, p_year), part_rows in self._partitions.items():
            if (p_layer, p_table) != (layer, table):
                continue
            if wanted_asset is not None and p_asset != wanted_asset:
                continue
            if wanted_year is not None and p_year != wanted_year:
                continue
            result.extend(dict(r) for r in part_rows)
        return result

    def _read_read_only(
        self, layer: str, table: str, filters: Mapping[str, object] | None
    ) -> Sequence[Row]:
        """Lê um par read-only: filtro por `asset` (ou união); inexistente → vazio.

        Mesma disciplina de filtro do adapter real: `asset=None` ≡ ausente;
        chave ≠ `asset` ergue; valor fora de `^[A-Za-z0-9._-]+$` ergue.
        """
        wanted = dict(filters or {})
        unsupported = sorted(set(wanted) - {"asset"})
        if unsupported:
            raise ValueError(
                f"read-only pair ({layer!r}, {table!r}) supports only the 'asset' "
                f"filter; got unsupported keys {unsupported}"
            )
        asset_val = wanted.get("asset")
        wanted_asset: str | None = None
        if asset_val is not None:
            wanted_asset = str(asset_val)
            if not _READ_ONLY_ASSET_PATTERN.fullmatch(wanted_asset):
                raise ValueError(
                    f"read-only pair ({layer!r}, {table!r}) asset filter must match "
                    f"{_READ_ONLY_ASSET_PATTERN.pattern!r}; got {wanted_asset!r}"
                )

        result: list[Row] = []
        for (p_layer, p_table, p_asset), part_rows in self._read_only.items():
            if (p_layer, p_table) != (layer, table):
                continue
            if wanted_asset is not None and p_asset != wanted_asset:
                continue
            result.extend(dict(r) for r in part_rows)
        return result
