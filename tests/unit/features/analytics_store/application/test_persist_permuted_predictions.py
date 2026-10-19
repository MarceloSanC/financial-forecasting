"""`PersistPermutedPredictions` com o `FakeAnalyticsRepository` (Stage 7.3, Task 15; CA10, I19)."""

from __future__ import annotations

from typing import Any

import pytest

from financial_forecasting.features.analytics_store.application.use_cases.persist_permuted_predictions import (  # noqa: E501
    PermutedDecisionEntry,
    PersistPermutedPredictions,
    PersistPermutedPredictionsCommand,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictions,
    PersistPredictionsCommand,
)
from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
    FakeAnalyticsRepository,
)
from tests.fakes.shared.in_memory_clock import FakeClock
from tests.unit.features.analytics_store.application.test_persist_predictions import (
    _LEVELS,
    _TIMESTAMPS,
)

pytestmark = pytest.mark.unit

_TABLE = "fact_permuted_predictions"
_RUN = "a" * 64


class _CountingRepository(FakeAnalyticsRepository):
    def __init__(self) -> None:
        super().__init__(clock=FakeClock())
        self.writes: list[tuple[str, int]] = []

    def write(self, *, layer: str, table: str, rows: Any, allow_upsert: bool = False) -> Any:  # noqa: ANN401
        self.writes.append((table, len(rows)))
        return super().write(layer=layer, table=table, rows=rows, allow_upsert=allow_upsert)


def _forecast(shift: float = 0.0) -> QuantileForecast:
    return QuantileForecast.from_raw(levels=_LEVELS, raw_values=(0.1 + shift, 0.5, 0.9))


def _entry(family: str = "price", k: int = 1, decision: int = 3) -> PermutedDecisionEntry:
    return PermutedDecisionEntry(
        permuted_family=family,
        permutation_index=k,
        decision_idx=decision,
        forecasts={1: _forecast(0.01 * k), 2: _forecast(0.02 * k)},
    )


def _command(entries: list[PermutedDecisionEntry]) -> PersistPermutedPredictionsCommand:
    return PersistPermutedPredictionsCommand(
        run_id=_RUN,
        model_version="tft_quantile",
        asset="AAPL",
        feature_set_name="fs_all",
        schema_version=1,
        permutation_seed=130,
        permutation_algorithm="fisher_yates_random_random_v1",
        partition_hash="b" * 64,
        dataset_timestamps=_TIMESTAMPS,
        entries=entries,
    )


def _rows(repo: FakeAnalyticsRepository) -> list[dict[str, object]]:
    return [dict(r) for r in repo.read(layer="silver", table=_TABLE, filters={"asset": "AAPL"})]


def test_rows_cell_by_cell() -> None:
    repo = _CountingRepository()
    result = PersistPermutedPredictions(repository=repo)(_command([_entry()]))
    assert result.rows_written == 2 * len(_LEVELS)
    row = next(r for r in _rows(repo) if r["horizon"] == 1 and r["quantile_level"] == _LEVELS[0])
    assert row == {
        "schema_version": 1,
        "run_id": _RUN,
        "model_version": "tft_quantile",
        "asset": "AAPL",
        "feature_set_name": "fs_all",
        "permuted_family": "price",
        "permutation_index": 1,
        "permutation_seed": 130,
        "permutation_algorithm": "fisher_yates_random_random_v1",
        "partition_hash": "b" * 64,
        "horizon": 1,
        "decision_idx": 3,
        "timestamp_utc": _TIMESTAMPS[3],
        "target_timestamp_utc": _TIMESTAMPS[4],
        "quantile_level": _LEVELS[0],
        "value_raw": pytest.approx(0.11),
        "value_guardrail": pytest.approx(0.11),
        "guardrail_applied": 0,
        "year": 2024,
    }


def test_target_timestamp_follows_persist_predictions() -> None:
    oos = FakeAnalyticsRepository(clock=FakeClock())
    PersistPredictions(repository=oos)(
        PersistPredictionsCommand(
            run_id=_RUN,
            split="test",
            model_version="tft_quantile",
            asset="AAPL",
            feature_set_name="fs_all",
            schema_version=1,
            decision_idx=3,
            dataset_timestamps=_TIMESTAMPS,
            forecasts={1: _forecast(), 2: _forecast()},
        )
    )
    repo = _CountingRepository()
    PersistPermutedPredictions(repository=repo)(_command([_entry("none", 0)]))
    expected = {
        (r["horizon"], r["timestamp_utc"], r["target_timestamp_utc"])
        for r in oos.read(layer="silver", table="fact_oos_predictions", filters={"asset": "AAPL"})
    }
    observed = {(r["horizon"], r["timestamp_utc"], r["target_timestamp_utc"]) for r in _rows(repo)}
    assert observed == expected


def test_year_is_the_decision_year() -> None:
    repo = _CountingRepository()
    PersistPermutedPredictions(repository=repo)(_command([_entry(decision=3)]))
    rows = _rows(repo)
    assert {r["year"] for r in rows} == {2024}
    assert {r["target_timestamp_utc"][:4] for r in rows} == {"2025"}


def test_one_write_per_run_call() -> None:
    repo = _CountingRepository()
    entries = [_entry("none", 0, d) for d in (1, 2)] + [
        _entry(f, k, d) for f in ("price", "sentiment") for k in (1, 2) for d in (1, 2)
    ]
    result = PersistPermutedPredictions(repository=repo)(_command(entries))
    assert repo.writes == [(_TABLE, result.rows_written)]
    assert result.rows_written == len(entries) * 2 * len(_LEVELS)


@pytest.mark.parametrize(
    ("family", "k"),
    [
        pytest.param("none", 1, id="none-with-k"),
        pytest.param("price", 0, id="family-k0"),
        pytest.param("price", -1, id="negative"),
    ],
)
def test_identity_entry_must_be_none_zero(family: str, k: int) -> None:
    repo = _CountingRepository()
    with pytest.raises(ValueError, match=r"permutation_index|identity"):
        PersistPermutedPredictions(repository=repo)(
            _command([_entry("none", 0), _entry(family, k)])
        )
    assert repo.writes == []


def test_incomplete_window_is_skipped_and_counted() -> None:
    repo = _CountingRepository()
    last = len(_TIMESTAMPS) - 1
    result = PersistPermutedPredictions(repository=repo)(_command([_entry(decision=last - 1)]))
    assert result.rows_written == len(_LEVELS)
    assert result.rows_skipped == len(_LEVELS)
