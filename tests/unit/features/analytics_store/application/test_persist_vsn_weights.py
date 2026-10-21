"""`PersistVsnWeights` com o `FakeAnalyticsRepository` (Stage 7.3, Task 15; CA10, I19)."""

from __future__ import annotations

import pytest

from financial_forecasting.features.analytics_store.application.use_cases.persist_vsn_weights import (  # noqa: E501
    PersistVsnWeights,
    PersistVsnWeightsCommand,
    VsnDecisionEntry,
)
from financial_forecasting.shared.application.exceptions import DuplicateKeyError
from tests.unit.features.analytics_store.application._silver_writers import (
    TIMESTAMPS as _TIMESTAMPS,
)
from tests.unit.features.analytics_store.application._silver_writers import (
    CountingRepository as _CountingRepository,
)

pytestmark = pytest.mark.unit

_TABLE = "fact_vsn_weights"
_FAMILIES = {"close": "price", "rsi_14": "technical", "day_of_week": "none"}


def _command(decisions: list[VsnDecisionEntry], **overrides: object) -> PersistVsnWeightsCommand:
    fields: dict[str, object] = {
        "run_id": "a" * 64,
        "model_version": "tft_quantile",
        "asset": "AAPL",
        "feature_set_name": "fs_all",
        "schema_version": 1,
        "dataset_timestamps": _TIMESTAMPS,
        "variable_families": _FAMILIES,
        "decisions": decisions,
    }
    fields.update(overrides)
    return PersistVsnWeightsCommand(**fields)  # type: ignore[arg-type]


def _weights() -> dict[str, float]:
    return {"close": 0.5, "rsi_14": 0.3, "day_of_week": 0.2}


def test_rows_cell_by_cell() -> None:
    repo = _CountingRepository()
    result = PersistVsnWeights(repository=repo)(_command([VsnDecisionEntry(4, _weights())]))
    assert result.rows_written == len(_FAMILIES)
    rows = {r["variable"]: dict(r) for r in repo.read(layer="silver", table=_TABLE)}
    assert rows["rsi_14"] == {
        "schema_version": 1,
        "run_id": "a" * 64,
        "model_version": "tft_quantile",
        "asset": "AAPL",
        "feature_set_name": "fs_all",
        "decision_idx": 4,
        "timestamp_utc": _TIMESTAMPS[4],
        "variable": "rsi_14",
        "family": "technical",
        "weight": 0.3,
        "year": 2025,
    }


def test_vsn_family_from_the_command() -> None:
    repo = _CountingRepository()
    families = {**_FAMILIES, "close": "fundamental"}
    PersistVsnWeights(repository=repo)(
        _command([VsnDecisionEntry(1, _weights())], variable_families=families)
    )
    rows = {r["variable"]: r for r in repo.read(layer="silver", table=_TABLE)}
    assert rows["close"]["family"] == "fundamental"
    assert rows["day_of_week"]["family"] == "none"


def test_variable_without_family_refused() -> None:
    repo = _CountingRepository()
    with pytest.raises(ValueError, match="no declared family"):
        PersistVsnWeights(repository=repo)(
            _command([VsnDecisionEntry(1, {**_weights(), "target": 0.0})])
        )
    assert repo.writes == []


def test_one_write_per_run_call_and_year_of_the_decision() -> None:
    repo = _CountingRepository()
    result = PersistVsnWeights(repository=repo)(
        _command([VsnDecisionEntry(d, _weights()) for d in (2, 3, 4)])
    )
    assert repo.writes == [(_TABLE, result.rows_written)]
    years = {(r["decision_idx"], r["year"]) for r in repo.read(layer="silver", table=_TABLE)}
    assert years == {(2, 2024), (3, 2024), (4, 2025)}


def test_decision_outside_the_grid_refused() -> None:
    with pytest.raises(ValueError, match="outside the dataset grid"):
        PersistVsnWeights(repository=_CountingRepository())(
            _command([VsnDecisionEntry(len(_TIMESTAMPS), _weights())])
        )


def test_second_write_of_same_run_raises_duplicate_key() -> None:
    """C4-1: append-only — regravar o mesmo run ergue e não muda a contagem."""
    repo = _CountingRepository()
    writer = PersistVsnWeights(repository=repo)
    writer(_command([VsnDecisionEntry(4, _weights())]))
    before = len(repo.read(layer="silver", table=_TABLE))
    with pytest.raises(DuplicateKeyError):
        writer(_command([VsnDecisionEntry(4, _weights())]))
    assert len(repo.read(layer="silver", table=_TABLE)) == before


def test_negative_decision_refused() -> None:
    """C4-5: decisão negativa não indexa a grade pelo fim (mutante M18)."""
    repo = _CountingRepository()
    with pytest.raises(ValueError, match="outside the dataset grid"):
        PersistVsnWeights(repository=repo)(_command([VsnDecisionEntry(-1, _weights())]))
    assert repo.writes == []
