"""Fake in-memory do port `RunRecordPersister` (modeling, issue #68).

Satisfaz o Protocol por duck-typing, como o real (`PersistRunRecord` do
`analytics_store`). Guarda os `RunRecord` recebidos indexados por `run_id` com a
mesma semântica de `dim_run` (política `upsert`: regravar o mesmo `run_id`
substitui, sem erguer) e devolve `rows_written == 1` — o que a suíte `[fake, real]`
(`tests/contract/features/modeling/test_persistence_ports_contract.py`) assevera
nas duas pernas. Não injeta `created_at_utc`: isso é do adapter (4.2 I5), não do port.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from financial_forecasting.features.analytics_store.application.use_cases.persist_run_record import (  # noqa: E501
    PersistRunRecordResult,
)

if TYPE_CHECKING:
    from financial_forecasting.features.analytics_store.domain.value_objects.run_record import (
        RunRecord,
    )


class InMemoryRunRecordPersister:
    """Guarda o último `RunRecord` por `run_id` (upsert), sem gravar nada."""

    def __init__(self) -> None:
        self.records: dict[str, RunRecord] = {}

    def __call__(self, record: RunRecord) -> PersistRunRecordResult:
        self.records[record.run_id] = record
        return PersistRunRecordResult(rows_written=1)
