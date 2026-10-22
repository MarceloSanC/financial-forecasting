"""Fake do port `SilverTableReader` — linhas em memória filtradas SÓ por partição.

Recebe as linhas por tabela e as chaves de partição de cada tabela; o `read` aplica
apenas as chaves de `filters` que são de partição e ignora as demais — o mesmo
superconjunto que o `ParquetAnalyticsRepository` devolve (ADR 6.4.0004 item 1).
Tabela desconhecida ergue `ApplicationError` (como o real). `columns` devolve os tipos
declarados de `SILVER_COLUMNS` (Stage 8.1). `reads` registra cada chamada
`(layer, table, filters)` para os testes de ordem do use case.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from financial_forecasting.shared.application.exceptions import ApplicationError

# Partições do silver usadas pelo refresh do gold (espelham o schema do 4.1).
SILVER_PARTITIONS: Mapping[str, tuple[str, ...]] = {
    "dim_run": ("asset", "parent_sweep_id"),
    "fact_oos_predictions": ("asset", "feature_set_name", "year"),
    # Stage 7.3 (ADR 7.3.0002 item 4): o `run_id` particiona as tabelas de atribuição.
    "fact_permuted_predictions": ("asset", "feature_set_name", "run_id", "year"),
    "fact_vsn_weights": ("asset", "feature_set_name", "run_id", "year"),
}

# Tipos declarados das colunas (Stage 8.1, ADR 8.1.0002 item 2b): espelham os schemas
# silver do 4.1 — o contrato `[fake, real]` exige igualdade exata com o real.
_STR = ("str", False)
_INT = ("int", False)
_FLOAT = ("float", False)
SILVER_COLUMNS: Mapping[str, Mapping[str, tuple[str, bool]]] = {
    "dim_run": {
        "schema_version": _INT,
        "run_id": _STR,
        "asset": _STR,
        "parent_sweep_id": ("str", True),
        "feature_set_name": _STR,
        "config_signature": _STR,
        "split_fingerprint": _STR,
        "fold": ("str", True),
        "seed": ("int", True),
        "model_version": _STR,
        "created_at_utc": _STR,
    },
    "fact_oos_predictions": {
        "schema_version": _INT,
        "run_id": _STR,
        "model_version": _STR,
        "asset": _STR,
        "feature_set_name": _STR,
        "split": _STR,
        "horizon": _INT,
        "decision_idx": _INT,
        "timestamp_utc": _STR,
        "target_timestamp_utc": _STR,
        "quantile_level": _FLOAT,
        "value_raw": _FLOAT,
        "value_guardrail": _FLOAT,
        "guardrail_applied": _INT,
        "year": _INT,
    },
    "fact_permuted_predictions": {
        "schema_version": _INT,
        "run_id": _STR,
        "model_version": _STR,
        "asset": _STR,
        "feature_set_name": _STR,
        "permuted_family": _STR,
        "permutation_index": _INT,
        "permutation_seed": _INT,
        "permutation_algorithm": _STR,
        "partition_hash": _STR,
        "horizon": _INT,
        "decision_idx": _INT,
        "timestamp_utc": _STR,
        "target_timestamp_utc": _STR,
        "quantile_level": _FLOAT,
        "value_raw": _FLOAT,
        "value_guardrail": _FLOAT,
        "guardrail_applied": _INT,
        "year": _INT,
    },
    "fact_vsn_weights": {
        "schema_version": _INT,
        "run_id": _STR,
        "model_version": _STR,
        "asset": _STR,
        "feature_set_name": _STR,
        "decision_idx": _INT,
        "timestamp_utc": _STR,
        "variable": _STR,
        "family": _STR,
        "weight": _FLOAT,
        "year": _INT,
    },
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

    def columns(self, *, layer: str, table: str) -> Mapping[str, tuple[str, bool]]:
        if table not in SILVER_COLUMNS:
            raise ApplicationError(f"Unknown silver (layer, table)=({layer!r}, {table!r})")
        return dict(SILVER_COLUMNS[table])
