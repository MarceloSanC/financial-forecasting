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
"""

from __future__ import annotations

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
