"""Fake do port `SilverTableReader` — linhas em memória filtradas SÓ por partição.

Recebe as linhas por tabela e as chaves de partição de cada tabela; o `read` aplica
apenas as chaves de `filters` que são de partição e ignora as demais — o mesmo
superconjunto que o `ParquetAnalyticsRepository` devolve (ADR 6.4.0004 item 1).
Tabela desconhecida ergue `ApplicationError` (como o real). `reads` registra cada chamada
`(layer, table, filters)` para os testes de ordem do use case.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from financial_forecasting.shared.application.exceptions import ApplicationError

# Partições do silver usadas pelo refresh do gold (espelham o schema do 4.1).
SILVER_PARTITIONS: Mapping[str, tuple[str, ...]] = {
    "dim_run": ("asset", "parent_sweep_id"),
    "fact_oos_predictions": ("asset", "feature_set_name", "year"),
}


class FakeSilverTableReader:
    """Satisfaz `SilverTableReader` com dicionários por tabela."""

    def __init__(
        self,
        rows_by_table: Mapping[str, Sequence[Mapping[str, object]]],
        partition_keys: Mapping[str, tuple[str, ...]] = SILVER_PARTITIONS,
    ) -> None:
        self._rows = {name: [dict(row) for row in rows] for name, rows in rows_by_table.items()}
        self._partition_keys = dict(partition_keys)
        self.reads: list[tuple[str, str, dict[str, object]]] = []

    def read(
        self,
        *,
        layer: str,
        table: str,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Mapping[str, object]]:
        if table not in self._partition_keys:
            raise ApplicationError(f"Unknown silver (layer, table)=({layer!r}, {table!r})")
        wanted = dict(filters or {})
        self.reads.append((layer, table, wanted))
        keys = [key for key in self._partition_keys[table] if key in wanted]
        return [
            dict(row)
            for row in self._rows.get(table, [])
            if all(row.get(key) == wanted[key] for key in keys)
        ]
