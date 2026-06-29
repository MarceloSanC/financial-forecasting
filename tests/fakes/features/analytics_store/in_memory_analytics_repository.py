"""Fake in-memory do port `AnalyticsRepository` — NÃO um mock.

`FakeAnalyticsRepository` aplica a MESMA semântica observável do adapter real
(`ParquetAnalyticsRepository`): despacho por `(layer, table)` via registry-leve,
append-only com dedup por PK lógica (colisão sem `allow_upsert` →
`DuplicateKeyError`; com `allow_upsert=True` ou `update_policy=="upsert"`
substitui só as colididas), particionamento pelas colunas literais de
`partition_by` (`None` → sentinel `__none__`), filtro por partição no `read`,
round-trip `__none__` → `None` em `parent_sweep_id` e `read` de dataset/asset
inexistente devolvendo vazio. Mantém as linhas em memória por
`(layer, table, <valores de partição>)` para produzir COMPORTAMENTO real e
estável, não asserts de chamada.

O fake é stdlib-only (vive em `tests/`, fora do gate, mas mantém o contrato
agnóstico de `pandas`/`pandera`): carrega um registry-leve interno
(`_PK_BY_TABLE`/`_PARTITION_BY_TABLE`/`_UPDATE_POLICY_BY_TABLE`) que ESPELHA as
mesmas PKs lógicas, colunas de partição e políticas do `SILVER_REGISTRY` `pandera`
do adapter (Stage 4.1), de modo que fake e real respondam idênticos ao MESMO
contract test (`tests/contract/features/analytics_store/...`, parametrizado sobre
`[fake, real]`). Levanta o MESMO `DuplicateKeyError` do real.

Aceita um `Clock` injetado: em `dim_run`, se a row não traz `created_at_utc`,
preenche via `clock.now()` ISO UTC — espelha o write-time do adapter para que o
contract com `FakeClock` determinístico passe idêntico nas duas implementações
(concept 4.2 I5/A6).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from financial_forecasting.shared.domain.exceptions.base import (
    ApplicationError,
    DuplicateKeyError,
)

if TYPE_CHECKING:
    from financial_forecasting.shared.application.ports.out.clock import Clock

Row = Mapping[str, object]

# Registry-leve: espelha o SILVER_REGISTRY pandera do adapter (Stage 4.1). Mantido
# como dado puro (sem pandas) para o fake permanecer agnóstico de storage libs.
_PK_BY_TABLE: dict[str, tuple[str, ...]] = {
    "dim_run": ("run_id",),
    "fact_config": ("run_id",),
    "fact_oos_predictions": (
        "run_id",
        "split",
        "horizon",
        "timestamp_utc",
        "target_timestamp_utc",
        "quantile_level",
    ),
    "fact_split_metrics": ("run_id", "split"),
    "fact_failures": ("run_id", "failed_at_utc", "stage"),
}
_PARTITION_BY_TABLE: dict[str, tuple[str, ...]] = {
    "dim_run": ("asset", "parent_sweep_id"),
    "fact_config": ("asset", "parent_sweep_id"),
    "fact_oos_predictions": ("asset", "feature_set_name", "year"),
    "fact_split_metrics": ("asset", "parent_sweep_id"),
    "fact_failures": ("asset",),
}
_UPDATE_POLICY_BY_TABLE: dict[str, str] = {
    "dim_run": "upsert",
    "fact_config": "append-only",
    "fact_oos_predictions": "append-only",
    "fact_split_metrics": "append-only",
    "fact_failures": "append-only",
}
# Colunas de partição que devem voltar como `None` quando armazenadas como sentinel.
_NULLABLE_PARTITION_COLS = frozenset({"parent_sweep_id"})

_SUPPORTED_LAYER = "silver"
_PARTITION_NONE = "__none__"
_COLLISION_SAMPLE_SIZE = 5


def _safe_partition(value: object) -> str:
    """Sanitiza um valor de partição (None/vazio → sentinela estável, como o old)."""
    if value is None:
        return _PARTITION_NONE
    text = str(value).strip()
    return text if text else _PARTITION_NONE


class FakeAnalyticsRepository:
    """Implementação in-memory determinística do contrato `AnalyticsRepository`."""

    def __init__(self, *, clock: Clock) -> None:
        self._clock = clock
        # (layer, table, <valores de partição como str>) -> lista de rows (cópias).
        self._partitions: dict[tuple[str, ...], list[dict[str, object]]] = {}

    # -- helpers de schema ---------------------------------------------------

    @staticmethod
    def _require_known(layer: str, table: str) -> None:
        if layer != _SUPPORTED_LAYER or table not in _PK_BY_TABLE:
            raise ApplicationError(
                f"Unknown silver (layer, table)=({layer!r}, {table!r}); "
                f"supported: {_SUPPORTED_LAYER} x {sorted(_PK_BY_TABLE)}"
            )

    @staticmethod
    def _pk_tuple(row: Row, pk_cols: tuple[str, ...]) -> tuple[object, ...]:
        return tuple(row.get(col) for col in pk_cols)

    @staticmethod
    def _partition_key(layer: str, table: str, row: Row) -> tuple[str, ...]:
        cols = _PARTITION_BY_TABLE[table]
        return (layer, table, *(_safe_partition(row.get(col)) for col in cols))

    # -- contrato ------------------------------------------------------------

    def write(
        self,
        *,
        layer: str,
        table: str,
        rows: Sequence[Row],
        allow_upsert: bool = False,
    ) -> None:
        """Grava `rows` append-only, particionado pelas colunas literais (ver port)."""
        self._require_known(layer, table)
        if not rows:
            return
        pk_cols = _PK_BY_TABLE[table]
        upsert = allow_upsert or _UPDATE_POLICY_BY_TABLE[table] == "upsert"

        prepared = [self._prepare(table, row) for row in rows]

        # Agrupa o incoming em batch por partição (espelha batch-por-partição, I7).
        buckets: dict[tuple[str, ...], list[dict[str, object]]] = {}
        for row in prepared:
            buckets.setdefault(self._partition_key(layer, table, row), []).append(row)

        for key, incoming in buckets.items():
            current = self._partitions.get(key, [])
            current_keys = {self._pk_tuple(r, pk_cols) for r in current}
            incoming_keys = {self._pk_tuple(r, pk_cols) for r in incoming}
            collisions = current_keys & incoming_keys

            if collisions and not upsert:
                sample = sorted(collisions, key=str)[:_COLLISION_SAMPLE_SIZE]
                raise DuplicateKeyError(
                    f"Duplicate logical PK collision in ({layer}, {table}): "
                    f"pk_columns={pk_cols} collisions={sample}"
                )

            if collisions:
                kept = [r for r in current if self._pk_tuple(r, pk_cols) not in collisions]
            else:
                kept = list(current)
            self._partitions[key] = kept + incoming

    def _prepare(self, table: str, row: Row) -> dict[str, object]:
        """Copia a row e preenche `created_at_utc` write-time em `dim_run` (I5)."""
        prepared = dict(row)
        if table == "dim_run" and prepared.get("created_at_utc") is None:
            prepared["created_at_utc"] = self._clock.now().isoformat()
        return prepared

    def read(
        self,
        *,
        layer: str,
        table: str,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Row]:
        """Lê o dataset filtrado por partição (`filters`); inexistente → vazio."""
        self._require_known(layer, table)
        cols = _PARTITION_BY_TABLE[table]
        wanted = dict(filters or {})
        # Predicado de partição: cada coluna de partição presente em `filters`.
        wanted_parts = {col: _safe_partition(wanted[col]) for col in cols if col in wanted}

        result: list[Row] = []
        for key, part_rows in self._partitions.items():
            if (key[0], key[1]) != (layer, table):
                continue
            part_values = dict(zip(cols, key[2:], strict=True))
            if any(part_values[col] != val for col, val in wanted_parts.items()):
                continue
            result.extend(self._restore(r) for r in part_rows)
        return result

    @staticmethod
    def _restore(row: dict[str, object]) -> dict[str, object]:
        """Round-trip `__none__` → `None` nas colunas de partição nullable (I6/C6)."""
        restored = dict(row)
        for col in _NULLABLE_PARTITION_COLS:
            if restored.get(col) == _PARTITION_NONE:
                restored[col] = None
        return restored
