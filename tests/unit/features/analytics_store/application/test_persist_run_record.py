"""Unit test do use case `PersistRunRecord` — grava `dim_run` via fake do port (#68).

Prova, com o `FakeAnalyticsRepository` in-memory da 4.2 (fake, NÃO mock; ADR
`0_0_0021`):

- (a) um `RunRecord` vira exatamente 1 linha em `silver.dim_run`, com TODOS os
  campos do VO (inclusive `None` em `parent_sweep_id`/`fold`/`seed`) e o
  `created_at_utc` injetado pelo repositório em write-time (4.2 I5) — o use case
  não o fabrica;
- (b) regravar o mesmo `run_id` substitui a linha (política `upsert` de `dim_run`
  no registry), sem `DuplicateKeyError` e sem duplicar;
- (c) o resultado reporta `rows_written == 1`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from financial_forecasting.features.analytics_store.application.use_cases.persist_run_record import (  # noqa: E501
    PersistRunRecord,
)
from financial_forecasting.features.analytics_store.domain.value_objects.run_record import (
    RunRecord,
)
from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
    FakeAnalyticsRepository,
)

_NOW = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)


class _FakeClock:
    def now(self) -> datetime:
        return _NOW


def _record(**overrides: object) -> RunRecord:
    fields: dict[str, object] = {
        "run_id": "a" * 64,
        "asset": "AAPL",
        "parent_sweep_id": "cohort-1",
        "feature_set_name": "fs_v1",
        "config_signature": "b" * 64,
        "split_fingerprint": "c" * 64,
        "fold": "0",
        "seed": 42,
        "model_version": "gbm_quantile",
        "schema_version": 1,
    }
    fields.update(overrides)
    return RunRecord(**fields)  # type: ignore[arg-type]


def test_one_record_becomes_one_dim_run_row_with_every_vo_field() -> None:
    repo = FakeAnalyticsRepository(clock=_FakeClock())
    record = _record(parent_sweep_id=None, fold=None, seed=None)

    result = PersistRunRecord(repository=repo)(record)

    [row] = repo.read(layer="silver", table="dim_run")
    assert result.rows_written == 1
    assert {key: row[key] for key in vars(record)} == vars(record)
    assert row["created_at_utc"] == _NOW.isoformat()  # write-time, pelo repositório


def test_rewriting_the_same_run_id_replaces_the_row_instead_of_duplicating() -> None:
    repo = FakeAnalyticsRepository(clock=_FakeClock())
    use_case = PersistRunRecord(repository=repo)

    use_case(_record(model_version="v1"))
    use_case(_record(model_version="v2"))

    [row] = repo.read(layer="silver", table="dim_run")
    assert row["model_version"] == "v2"
