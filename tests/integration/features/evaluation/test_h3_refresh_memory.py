"""Teto de memória da leitura de H3 do refresh (Stage 7.3, Task 31; CA14b, I19).

O silver de atribuição real tem ~8,7 M linhas; o `RefreshGold` lê um run por chamada
(permutadas e VSN, filtro `run_id`) e a partição da ablação uma vez por `year`, reduz e
descarta. Aqui um leitor gera as linhas sob demanda, nos volumes reais, e devolve o
superconjunto da partição pedida, como o adapter. O pico é medido pelo `tracemalloc`
durante as etapas de leitura e redução do H3 (`_attribution_reductions` e
`_ablation_reductions`), as que tocam o volume. Nenhum dado real.
"""

from __future__ import annotations

import math
import random
import tracemalloc
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta

import pytest

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
)
from financial_forecasting.features.evaluation.application.use_cases.refresh_gold import (
    RefreshGold,
)
from financial_forecasting.features.evaluation.domain.value_objects.ablation_run_losses import (
    AblationRunLosses,
)
from financial_forecasting.features.evaluation.domain.value_objects.cohort_run import CohortRun
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3_FAMILIES,
    LOCO_REFERENCE_MODEL,
    loco_model_of,
)
from financial_forecasting.features.evaluation.domain.value_objects.permuted_run_losses import (
    PermutedRunLosses,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from tests.fakes.features.evaluation.fake_conformal_calibration import FakeConformalCalibration
from tests.fakes.features.evaluation.fake_mcs_backend import FakeMcsBackend
from tests.fakes.features.evaluation.fake_training_grid_reader import FakeTrainingGridReader
from tests.fakes.features.evaluation.in_memory_gold_store import InMemoryGoldStore
from tests.fakes.shared.in_memory_clock import FakeClock

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_ASSET = "AAPL"
_LEVELS = (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98)
_OFFSETS = (-0.041, -0.0256, -0.0135, 0.0, 0.0135, 0.0256, 0.041)
_HORIZONS = (1, 7)
_DECISIONS = 252  # decisões de teste de um fold real
_YEARS = tuple(range(2019, 2025))  # ~6 blocos anuais
_SEEDS = 10
_VARIABLES = 59
_MIB = 1024 * 1024
_CEILING = 512 * _MIB
_EPOCH = datetime(2019, 1, 1, tzinfo=UTC)
_SESSIONS = (len(_YEARS) + 1) * 366
_PARTITION = GoldPartition(_ASSET, "sweep-memory")
_PARTITION_HASH = "a1" * 32


def _session(index: int) -> str:
    return (_EPOCH + timedelta(days=index)).isoformat()


def _first_session_of(year: int) -> int:
    return (datetime(year, 1, 1, tzinfo=UTC) - _EPOCH).days


_REALIZED = RealizedReturns(
    timestamps=tuple(_session(i) for i in range(_SESSIONS)),
    returns=tuple(random.Random("realized").uniform(-0.03, 0.03) for _ in range(_SESSIONS)),
)


def _grid(seed: int, decision: int, horizon: int, shift: float = 0.0) -> list[float]:
    center = math.sin(decision * 0.01 + seed) * 0.01 + shift
    return [center + offset for offset in _OFFSETS]


def _points(year: int) -> Iterator[tuple[int, int]]:
    first = _first_session_of(year)
    for horizon in _HORIZONS:
        for decision in range(first, first + _DECISIONS):
            yield horizon, decision


def _fact(run: CohortRun, horizon: int, decision: int, level: float, value: float) -> dict:  # type: ignore[type-arg]
    return {
        "run_id": run.run_id,
        "model_version": run.model,
        "asset": _ASSET,
        "feature_set_name": run.feature_set_name,
        "split": "test",
        "horizon": horizon,
        "decision_idx": decision,
        "timestamp_utc": _session(decision),
        "target_timestamp_utc": _session(decision + horizon),
        "quantile_level": level,
        "value_raw": value,
        "value_guardrail": value,
        "guardrail_applied": 0,
        "year": int(_session(decision)[:4]),
    }


class _GeneratingReader:
    """`SilverTableReader` que gera as linhas da partição pedida na hora (nada guardado)."""

    def __init__(
        self,
        *,
        candidate: Sequence[CohortRun],
        ablation: Sequence[CohortRun],
        year_of: Callable[[CohortRun], int],
    ) -> None:
        self._candidate = {run.run_id: run for run in candidate}
        self._ablation = list(ablation)
        self._year_of = year_of
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.rows = 0

    def read(
        self, *, layer: str, table: str, filters: Mapping[str, object] | None = None
    ) -> Sequence[Mapping[str, object]]:
        wanted = dict(filters or {})
        self.calls.append((table, wanted))
        rows = list(self._generate(table, wanted))
        self.rows += len(rows)
        return rows

    def _generate(self, table: str, wanted: Mapping[str, object]) -> Iterator[dict]:  # type: ignore[type-arg]
        if table == "fact_oos_predictions":
            year = int(str(wanted["year"]))
            for run in self._ablation:
                if self._year_of(run) != year:
                    continue
                shift = 0.0 if run.model == LOCO_REFERENCE_MODEL else 0.002
                for horizon, decision in _points(year):
                    grid = _grid(run.seed or 0, decision, horizon, shift)
                    for level, value in zip(_LEVELS, grid, strict=True):
                        yield _fact(run, horizon, decision, level, value)
            return
        run = self._candidate[str(wanted["run_id"])]
        year = self._year_of(run)
        if table == "fact_permuted_predictions":
            labels = [("none", 0)] + [(f, k) for f in H3_FAMILIES for k in range(1, 11)]
            for family, k in labels:
                for horizon, decision in _points(year):
                    grid = _grid(run.seed or 0, decision, horizon, 0.001 * k)
                    for level, value in zip(_LEVELS, grid, strict=True):
                        row = _fact(run, horizon, decision, level, value)
                        row.update(
                            permuted_family=family,
                            permutation_index=k,
                            permutation_seed=130,
                            permutation_algorithm="fisher_yates_random_random_v1",
                            partition_hash=_PARTITION_HASH,
                        )
                        yield row
        elif table == "fact_vsn_weights":
            first = _first_session_of(year)
            for decision in range(first, first + _DECISIONS):
                for v in range(_VARIABLES):
                    yield {
                        "run_id": run.run_id,
                        "model_version": run.model,
                        "asset": _ASSET,
                        "feature_set_name": run.feature_set_name,
                        "decision_idx": decision,
                        "timestamp_utc": _session(decision),
                        "variable": f"var_{v:02d}",
                        "family": "none",
                        "weight": 1.0 / _VARIABLES,
                        "year": year,
                    }


def _use_case(reader: _GeneratingReader) -> RefreshGold:
    return RefreshGold(
        silver_reader=reader,
        grid_reader=FakeTrainingGridReader(
            {}, columns=("target_return",), hasher=CanonicalJsonHasher()
        ),
        clock=FakeClock(),
        mcs_backend=FakeMcsBackend(),
        gold_store=InMemoryGoldStore(),
        builders=[],
        conformal_calibration=FakeConformalCalibration(),
    )


def _run(run_id: str, model: str, seed: int, fold: int, feature_set: str) -> CohortRun:
    return CohortRun(
        run_id=run_id,
        model=model,
        seed=seed,
        fold=str(fold),
        feature_set_name=feature_set,
        config_signature=f"sig-{model}",
    )


def _ablation_runs(seeds: int, folds: int) -> list[CohortRun]:
    models = (LOCO_REFERENCE_MODEL, *(loco_model_of(f) for f in H3_FAMILIES))
    return [
        _run(f"{model}-s{seed}-{fold}", model, seed, fold, "fs_all_ablation")
        for model in models
        for seed in range(1, seeds + 1)
        for fold in range(folds)
    ]


def _peak(action: Callable[[], object]) -> tuple[object, int]:
    tracemalloc.start()
    try:
        result = action()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, peak


def test_ablation_partition_read_once_per_year_at_real_size() -> None:
    """~1 M linhas: 5 configurações x 6 anos x 10 seeds x ~3 500, lidas uma vez por ano."""
    runs = _ablation_runs(_SEEDS, len(_YEARS))
    reader = _GeneratingReader(
        candidate=(), ablation=runs, year_of=lambda run: _YEARS[int(str(run.fold))]
    )
    use_case = _use_case(reader)

    reductions, peak = _peak(
        lambda: use_case._ablation_reductions(_PARTITION, runs, _YEARS, _REALIZED, _LEVELS)
    )

    assert [table for table, _ in reader.calls] == ["fact_oos_predictions"] * len(_YEARS)
    assert [filters["year"] for _, filters in reader.calls] == list(_YEARS)
    assert reader.rows == len(runs) * _DECISIONS * len(_HORIZONS) * len(_LEVELS)
    assert reader.rows > 1_000_000  # noqa: PLR2004
    assert all(isinstance(r, AblationRunLosses) for r in reductions)  # type: ignore[attr-defined]
    assert peak <= _CEILING, f"peak {peak / _MIB:.0f} MiB"


def _h3_reading(n_runs: int) -> int:
    """O pico da leitura por run (permutadas, VSN e ablação) com `n_runs` de cada tipo."""
    candidate = [_run(f"tft-s{s}-0", "tft", s, 0, "fs-core") for s in range(1, n_runs + 1)]
    ablation = [
        _run(f"{LOCO_REFERENCE_MODEL}-s{s}-0", LOCO_REFERENCE_MODEL, s, 0, "fs_all_ablation")
        for s in range(1, n_runs + 1)
    ]
    reader = _GeneratingReader(candidate=candidate, ablation=ablation, year_of=lambda run: 2019)
    use_case = _use_case(reader)

    def read() -> tuple[object, object]:
        permuted, vsn, _ = use_case._attribution_reductions(
            _PARTITION, candidate, _REALIZED, _LEVELS
        )
        losses = use_case._ablation_reductions(_PARTITION, ablation, (2019,), _REALIZED, _LEVELS)
        return (permuted, vsn), losses

    (pair, losses), peak = _peak(read)  # type: ignore[misc]
    permuted, vsn = pair  # type: ignore[misc]
    assert all(isinstance(r, PermutedRunLosses) for r in permuted), permuted
    assert len(vsn) == n_runs
    assert all(isinstance(r, AblationRunLosses) for r in losses)  # type: ignore[attr-defined]
    per_run = 41 * _DECISIONS * len(_HORIZONS) * len(_LEVELS)
    assert reader.rows == n_runs * (
        per_run + _DECISIONS * _VARIABLES + _DECISIONS * len(_HORIZONS) * len(_LEVELS)
    )
    return peak


def test_peak_memory_bounded_and_flat_in_runs() -> None:
    three = _h3_reading(3)
    six = _h3_reading(6)
    assert three <= _CEILING, f"peak {three / _MIB:.0f} MiB"
    assert six <= _CEILING, f"peak {six / _MIB:.0f} MiB"
    assert six <= 1.1 * three, (three / _MIB, six / _MIB)
