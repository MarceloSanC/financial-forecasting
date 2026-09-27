"""Contrato do port `CohortRunIndex` (Stage 5.5, A4 / I7 / A8).

A fixture devolve `(index, seed_run)`: `seed_run` grava um run como o silver o
teria — no fake, registrando; no adapter real (perna `real`, Task 21), gravando
`dim_run` e `fact_oos_predictions` no repositório Parquet. A mesma suíte prova:
contagem de linhas por `run_id` (níveis vezes decisões com alvo), fold e conjuntos de
`target_timestamp` por horizonte; órfão (dim_run sem predição) → 0 linhas;
atribuição por `(model_version, seed)` com seed nula nas baselines; outro cohort
no mesmo arquivo anual não contamina; cohort inexistente → vazio.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest

from financial_forecasting.features.modeling.application.ports.out.cohort_run_index import (
    CohortRunIndex,
)
from tests.fakes.features.modeling.in_memory_cohort_run_index import InMemoryCohortRunIndex

_ASSET = "AAPL"
_FEATURE_SET = "fs_all"
_COHORT = "aapl_confirmatory-r0-abc"
_OTHER_COHORT = "aapl_confirmatory-r1-def"
_LEVELS = (0.1, 0.5, 0.9)

# (timestamp_utc, target_timestamp_utc, horizon)
_Decision = tuple[str, str, int]
_SeedRun = Callable[..., None]


def _decisions(horizon: int, days: Sequence[int]) -> list[_Decision]:
    return [
        (
            f"2024-01-{day:02d}T00:00:00+00:00",
            f"2024-01-{day + horizon:02d}T00:00:00+00:00",
            horizon,
        )
        for day in days
    ]


def _fake_leg() -> tuple[CohortRunIndex, _SeedRun]:
    index = InMemoryCohortRunIndex()

    def seed_run(  # noqa: PLR0913
        *,
        cohort_id: str,
        model_version: str,
        seed: int | None,
        run_id: str,
        fold: str,
        decisions: Sequence[_Decision],
    ) -> None:
        targets: dict[int, set[str]] = {}
        for _, target, horizon in decisions:
            targets.setdefault(horizon, set()).add(target)
        index.record(
            asset_id=_ASSET,
            feature_set_name=_FEATURE_SET,
            cohort_id=cohort_id,
            model_version=model_version,
            seed=seed,
            run_id=run_id,
            fold=fold,
            targets_by_horizon=targets,
            rows=len(decisions) * len(_LEVELS),
        )

    return index, seed_run


@pytest.fixture(params=["fake"])
def leg(request: pytest.FixtureRequest) -> tuple[CohortRunIndex, _SeedRun]:
    if request.param == "fake":
        return _fake_leg()
    raise AssertionError(request.param)  # pragma: no cover


def _read(index: CohortRunIndex, cohort_id: str = _COHORT) -> dict:  # type: ignore[type-arg]
    return dict(
        index.recorded_runs(asset_id=_ASSET, feature_set_name=_FEATURE_SET, cohort_id=cohort_id)
    )


@pytest.mark.contract
def test_counts_folds_and_targets_per_run(leg: tuple[CohortRunIndex, _SeedRun]) -> None:
    index, seed_run = leg
    seed_run(
        cohort_id=_COHORT,
        model_version="tft_quantile",
        seed=11,
        run_id="run-f0",
        fold="fold-0",
        decisions=_decisions(1, [2, 3]) + _decisions(7, [2, 3]),
    )

    runs = _read(index)

    fold, rows, targets = runs[("tft_quantile", 11)]["run-f0"]
    assert fold == "fold-0"
    assert rows == 4 * len(_LEVELS)
    assert targets == {
        1: frozenset({"2024-01-03T00:00:00+00:00", "2024-01-04T00:00:00+00:00"}),
        7: frozenset({"2024-01-09T00:00:00+00:00", "2024-01-10T00:00:00+00:00"}),
    }


@pytest.mark.contract
def test_orphan_run_has_zero_rows(leg: tuple[CohortRunIndex, _SeedRun]) -> None:
    index, seed_run = leg
    seed_run(
        cohort_id=_COHORT,
        model_version="gbm_quantile",
        seed=7,
        run_id="run-orphan",
        fold="fold-1",
        decisions=[],
    )

    fold, rows, targets = _read(index)[("gbm_quantile", 7)]["run-orphan"]

    assert (fold, rows) == ("fold-1", 0)
    assert all(not ts for ts in targets.values())


@pytest.mark.contract
def test_baselines_are_keyed_with_null_seed(leg: tuple[CohortRunIndex, _SeedRun]) -> None:
    index, seed_run = leg
    seed_run(
        cohort_id=_COHORT,
        model_version="baseline_zero_return",
        seed=None,
        run_id="run-b",
        fold="fold-0",
        decisions=_decisions(1, [2]),
    )

    assert ("baseline_zero_return", None) in _read(index)


@pytest.mark.contract
def test_other_cohort_does_not_contaminate(leg: tuple[CohortRunIndex, _SeedRun]) -> None:
    index, seed_run = leg
    seed_run(
        cohort_id=_COHORT,
        model_version="tft_quantile",
        seed=11,
        run_id="run-mine",
        fold="fold-0",
        decisions=_decisions(1, [2]),
    )
    seed_run(
        cohort_id=_OTHER_COHORT,
        model_version="tft_quantile",
        seed=11,
        run_id="run-theirs",
        fold="fold-0",
        decisions=_decisions(1, [3, 4]),
    )

    mine = _read(index)[("tft_quantile", 11)]

    assert set(mine) == {"run-mine"}
    assert mine["run-mine"][1] == len(_LEVELS)


@pytest.mark.contract
def test_unknown_cohort_is_empty(leg: tuple[CohortRunIndex, _SeedRun]) -> None:
    index, _ = leg

    assert _read(index, "no-such-cohort") == {}
