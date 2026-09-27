"""Unit test do use case `RunConfirmatoryCohort` com fakes (Stage 5.5, A2).

Os três use cases de treino são stubs que registram o comando recebido e gravam
no `InMemoryCohortRunIndex` o que o silver teria (um run por fold e modelo, com a
contagem esperada da geometria) — assim retomada e verificação por contagem rodam
sobre o que as unidades "persistiram". Prova: ordem das unidades; escopo com o
`cohort_id` do spec e `max_horizon = max(horizons)`; seed por unidade no TFT; I1;
as quatro igualdades de I4; geometria; I5 (árvore suja já na 1ª execução,
ambiente gravado e comparado); I6 e I7 (a) a (d), com colisão de seed GBM/TFT e
baselines de seed nula; unidade com use case falho não é marcada; lock liberado
em erro.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from financial_forecasting.features.modeling.application.dtos.cohort_spec import (
    CohortSpec,
    SweepPlan,
    SweepProvenance,
)
from financial_forecasting.features.modeling.application.pipeline_version import PIPELINE_VERSION
from financial_forecasting.features.modeling.application.ports.out.cohort_progress_ledger import (
    CohortRunLockedError,
)
from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    SearchDimension,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.application.use_cases import (
    run_confirmatory_cohort as module,
)
from financial_forecasting.features.modeling.application.use_cases import (
    train_gbm_quantile,
    train_tft,
)
from financial_forecasting.features.modeling.application.use_cases.run_baselines import (
    BaselineRunSummary,
    RunBaselinesResult,
)
from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    CohortDeclarationMismatchError,
    CohortNotFrozenError,
    CompletedUnitCorruptedError,
    DatasetMismatchError,
    EnvironmentMismatchError,
    PartialCohortUnitError,
    RunConfirmatoryCohort,
    RunConfirmatoryCohortCommand,
    cohort_model_keys,
    load_training_grid,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    GbmRunSummary,
    TrainGbmQuantileResult,
    grid_fingerprint,
    modeling_columns,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    TftRunSummary,
    TrainTftResult,
)
from financial_forecasting.features.modeling.domain.exceptions.cohort import (
    GeometryDoesNotFitError,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    build_training_grid,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BaselineSpec,
)
from financial_forecasting.features.modeling.domain.value_objects.cohort_geometry import (
    CohortGeometry,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash
from tests.fakes.features.modeling.in_memory_cohort_progress_ledger import (
    InMemoryCohortProgressLedger,
)
from tests.fakes.features.modeling.in_memory_cohort_run_index import InMemoryCohortRunIndex
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)
from tests.fakes.shared.in_memory_clock import FakeClock
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

_HASHER = CanonicalJsonHasher()
_ASSET = "AAPL"
_FEATURE_SET = "fs_all"
_FEATURE_SET_HASH = "f" * 64
_FRIDAY = 4
_N_SESSIONS = 120
_HORIZONS = (1, 2)
_LEVELS = (0.1, 0.5, 0.9)
_GEOMETRY = CohortGeometry(n_folds=2, test_size=10, val_size=8, calib_size=6, embargo=1)
_SEEDS = (11, 22)
_GBM_SEED = 22  # colide com uma seed do TFT de propósito
_BASELINES = BaselineSpec.canonical_five(historical_quantiles_window=20)


def _sessions() -> tuple[date, ...]:
    days: list[date] = []
    current = date(2021, 1, 4)
    while len(days) < _N_SESSIONS:
        if current.weekday() <= _FRIDAY:
            days.append(current)
        current += timedelta(days=1)
    return tuple(days)


def _rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx, day in enumerate(_sessions()):
        row: dict[str, object] = {
            "timestamp": datetime(day.year, day.month, day.day, tzinfo=UTC),
            "asset_id": _ASSET,
        }
        for position, name in enumerate(modeling_columns()):
            row[name] = float(idx) + position / 100.0
        rows.append(row)
    return rows


def _store(rows: list[dict[str, object]] | None = None) -> FakeMedallionStore:
    store = FakeMedallionStore()
    store.seed_read_only(layer="processed", table="dataset_tft", asset=_ASSET, rows=rows or _rows())
    return store


def _fingerprint(rows: list[dict[str, object]] | None = None) -> str:
    grid = build_training_grid(rows or _rows(), columns=modeling_columns())
    return grid_fingerprint(grid, hasher=_HASHER, asset_id=_ASSET)


def _spec(**overrides: object) -> CohortSpec:
    fingerprint = _fingerprint()
    base: dict[str, object] = {
        "name": "aapl_confirmatory",
        "revision": 0,
        "asset_id": _ASSET,
        "feature_set_name": _FEATURE_SET,
        "feature_set_hash": _FEATURE_SET_HASH,
        "pipeline_version": PIPELINE_VERSION,
        "horizons": _HORIZONS,
        "quantile_levels": _LEVELS,
        "geometry": _GEOMETRY,
        "device": "cpu",
        "seeds": _SEEDS,
        "sweep": SweepPlan(
            tft_space=(SearchDimension(name="hidden_size", low=8, high=64, kind="int"),),
            tft_base_params=TftTrainingParams(seed=0),
            gbm_space=(SearchDimension(name="num_leaves", low=4, high=64, kind="int"),),
            gbm_base_params=GbmTrainingParams(seed=_GBM_SEED),
            n_trials=5,
            sampler_seed=2026,
        ),
        "tft_params": TftTrainingParams(seed=0, hidden_size=24),
        "gbm_params": GbmTrainingParams(seed=_GBM_SEED, num_leaves=16),
        "baseline_specs": _BASELINES,
        "provenance": SweepProvenance(
            tft_study_id="s1",
            tft_best_trial=1,
            tft_best_objective=0.1,
            gbm_study_id="s2",
            gbm_best_trial=2,
            gbm_best_objective=0.2,
            dataset_fingerprint=fingerprint,
        ),
        "dataset_fingerprint": fingerprint,
    }
    base.update(overrides)
    return CohortSpec(**base)  # type: ignore[arg-type]


def _cohort_id(spec: CohortSpec) -> str:
    return spec.cohort_id(CohortHash.compute(hasher=_HASHER, payload=spec.hash_payload()))


class _Harness:
    """Monta o use case com fakes e stubs que "persistem" no índice de runs."""

    def __init__(
        self,
        *,
        store: FakeMedallionStore | None = None,
        probe: InMemoryRuntimeEnvironmentProbe | None = None,
        fail_unit: str | None = None,
    ) -> None:
        self.ledger = InMemoryCohortProgressLedger()
        self.index = InMemoryCohortRunIndex()
        self.calls: list[tuple[str, Any]] = []
        self._fail_unit = fail_unit
        self.use_case = RunConfirmatoryCohort(
            store=store or _store(),
            hasher=_HASHER,
            clock=FakeClock(),
            ledger=self.ledger,
            run_index=self.index,
            probe=probe or InMemoryRuntimeEnvironmentProbe(),
            run_baselines=self._baselines,
            train_gbm=self._gbm,
            train_tft=self._tft,
            modeling_columns=modeling_columns(),
            observed_feature_set_hash=_FEATURE_SET_HASH,
            pipeline_version=PIPELINE_VERSION,
            schema_version=1,
        )

    def _persist(
        self,
        command: Any,  # noqa: ANN401
        model_version: str,
        seed: int | None,
    ) -> list[tuple[str, int, int]]:
        persisted = []
        for fold in range(_GEOMETRY.n_folds):
            rows = _GEOMETRY.expected_prediction_rows(
                fold_index=fold, horizons=_HORIZONS, n_levels=len(_LEVELS)
            )
            run_id = f"{model_version}-s{seed}-f{fold}"
            self.index.record(
                asset_id=_ASSET,
                feature_set_name=_FEATURE_SET,
                cohort_id=command.scope.cohort_id,
                model_version=model_version,
                seed=seed,
                run_id=run_id,
                fold=str(fold),
                targets_by_horizon={},
                rows=rows,
            )
            persisted.append((run_id, fold, rows))
        return persisted

    def _maybe_fail(self, unit: str) -> None:
        if self._fail_unit == unit:
            raise RuntimeError(f"boom in {unit}")

    def _baselines(self, command: Any) -> RunBaselinesResult:  # noqa: ANN401
        self.calls.append(("baselines", command))
        self._maybe_fail("baselines")
        runs = [
            BaselineRunSummary(
                run_id=r,
                model_version=f"baseline_{b.family}",
                fold_index=f,
                rows_written=n,
                rows_skipped=0,
            )
            for b in command.specs
            for r, f, n in self._persist(command, f"baseline_{b.family}", None)
        ]
        return RunBaselinesResult(runs=tuple(runs))

    def _gbm(self, command: Any) -> TrainGbmQuantileResult:  # noqa: ANN401
        self.calls.append(("gbm", command))
        self._maybe_fail("gbm")
        runs = [
            GbmRunSummary(
                run_id=r,
                model_version="gbm_quantile",
                fold_index=f,
                rows_written=n,
                rows_skipped=0,
                best_iteration_by_horizon={1: 1},
            )
            for r, f, n in self._persist(command, "gbm_quantile", command.params.seed)
        ]
        return TrainGbmQuantileResult(runs=tuple(runs))

    def _tft(self, command: Any) -> TrainTftResult:  # noqa: ANN401
        unit = f"tft:seed={command.params.seed}"
        self.calls.append((unit, command))
        self._maybe_fail(unit)
        runs = [
            TftRunSummary(
                run_id=r,
                model_version="tft_quantile",
                fold_index=f,
                rows_written=n,
                rows_skipped=0,
                best_epoch=1,
                best_val_loss=0.1,
                fitted_decision_count=1,
                monitored_decision_count=1,
                artifact_path="x",
                tracking_run_id="t",
            )
            for r, f, n in self._persist(command, "tft_quantile", command.params.seed)
        ]
        return TrainTftResult(runs=tuple(runs))

    def run(self, spec: CohortSpec | None = None) -> Any:  # noqa: ANN401
        return self.use_case(RunConfirmatoryCohortCommand(spec=spec or _spec()))


# -- caminho feliz ------------------------------------------------------------------


def test_units_run_in_order_with_the_cohort_scope() -> None:
    harness = _Harness()

    result = harness.run()

    assert [unit for unit, _ in harness.calls] == ["baselines", "gbm", "tft:seed=11", "tft:seed=22"]
    assert all(cmd.scope.cohort_id == _cohort_id(_spec()) for _, cmd in harness.calls)
    assert all(cmd.scope.max_horizon == max(_HORIZONS) for _, cmd in harness.calls)
    assert [o.status for o in result.outcomes] == ["ran"] * 4
    assert result.cohort_id == _cohort_id(_spec())


def test_tft_units_get_their_own_seed_and_the_frozen_params() -> None:
    harness = _Harness()

    harness.run()

    tft_params = [cmd.params for unit, cmd in harness.calls if unit.startswith("tft")]
    assert [p.seed for p in tft_params] == list(_SEEDS)
    assert all(p.hidden_size == 24 for p in tft_params)  # noqa: PLR2004


def test_model_versions_match_the_use_cases() -> None:
    assert module.GBM_MODEL_VERSION == train_gbm_quantile._MODEL_VERSION
    assert module.TFT_MODEL_VERSION == train_tft._MODEL_VERSION


def test_resume_skips_completed_units_after_reconfirming_counts() -> None:
    harness = _Harness()
    harness.run()
    harness.calls.clear()

    result = harness.run()

    assert harness.calls == []
    assert [o.status for o in result.outcomes] == ["skipped_completed"] * 4


# -- I1, I4, geometria ---------------------------------------------------------------


def test_unfrozen_spec_is_refused_before_anything() -> None:
    harness = _Harness()

    with pytest.raises(CohortNotFrozenError):
        harness.run(_spec(seeds=()))
    assert harness.calls == []
    assert not harness.ledger.is_locked


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"dataset_fingerprint": "0" * 64}, DatasetMismatchError),
        ({"feature_set_hash": "e" * 64}, CohortDeclarationMismatchError),
        ({"pipeline_version": "999"}, CohortDeclarationMismatchError),
    ],
    ids=["dataset", "feature-set-hash", "pipeline-version"],
)
def test_declared_differs_from_observed(overrides: dict[str, object], error: type) -> None:
    harness = _Harness()
    spec = _spec(**overrides)
    if "dataset_fingerprint" in overrides:
        spec = replace(spec, provenance=replace(spec.provenance, dataset_fingerprint="0" * 64))  # type: ignore[type-var]

    with pytest.raises(error):
        harness.run(spec)
    assert harness.calls == []
    assert not harness.ledger.is_locked


def test_sweeps_on_other_data_than_the_run_are_refused() -> None:
    harness = _Harness()
    spec = _spec()
    spec = replace(spec, provenance=replace(spec.provenance, dataset_fingerprint="0" * 64))  # type: ignore[type-var]

    with pytest.raises(CohortDeclarationMismatchError, match="sweeps"):
        harness.run(spec)


def test_geometry_that_does_not_fit_is_refused_before_training() -> None:
    harness = _Harness()
    too_big = CohortGeometry(n_folds=10, test_size=10, val_size=8, calib_size=6, embargo=1)

    with pytest.raises(GeometryDoesNotFitError):
        harness.run(_spec(geometry=too_big))
    assert harness.calls == []


# -- I5 ---------------------------------------------------------------------------------


def test_dirty_tree_is_refused_on_the_first_run() -> None:
    harness = _Harness(probe=InMemoryRuntimeEnvironmentProbe(code_dirty="true"))

    with pytest.raises(EnvironmentMismatchError, match="uncommitted"):
        harness.run()
    assert harness.calls == []
    assert harness.ledger.environment(_cohort_id(_spec())) is None


def test_first_run_records_environment_and_start() -> None:
    harness = _Harness()

    harness.run()

    cohort_id = _cohort_id(_spec())
    assert harness.ledger.environment(cohort_id) is not None
    assert harness.ledger.run_started_at(cohort_id) == FakeClock().now().isoformat()


def test_resume_with_a_different_environment_is_refused() -> None:
    harness = _Harness()
    harness.run()
    harness.use_case._probe = InMemoryRuntimeEnvironmentProbe(torch="9.9")

    with pytest.raises(EnvironmentMismatchError, match="torch"):
        harness.run()


# -- I6, I7 -----------------------------------------------------------------------------


def _record_gbm(harness: _Harness, *, rows: int | None, n_folds: int = 2) -> None:
    for fold in range(n_folds):
        expected = _GEOMETRY.expected_prediction_rows(
            fold_index=fold, horizons=_HORIZONS, n_levels=len(_LEVELS)
        )
        harness.index.record(
            asset_id=_ASSET,
            feature_set_name=_FEATURE_SET,
            cohort_id=_cohort_id(_spec()),
            model_version="gbm_quantile",
            seed=_GBM_SEED,
            run_id=f"pre-{fold}",
            fold=str(fold),
            targets_by_horizon={},
            rows=expected if rows is None else rows,
        )


def test_orphan_runs_are_retried() -> None:
    harness = _Harness()
    _record_gbm(harness, rows=0)

    result = harness.run()

    assert "gbm" in [unit for unit, _ in harness.calls]
    assert result.outcomes[1].status == "ran"


def test_complete_but_unmarked_unit_is_verified_without_training() -> None:
    harness = _Harness()
    _record_gbm(harness, rows=None)

    result = harness.run()

    assert "gbm" not in [unit for unit, _ in harness.calls]
    assert result.outcomes[1].status == "verified_completed"
    assert "gbm" in harness.ledger.completed_units(_cohort_id(_spec()))


def test_partial_unit_fails_closed() -> None:
    harness = _Harness()
    _record_gbm(harness, rows=None, n_folds=1)  # só 1 dos 2 runs esperados

    with pytest.raises(PartialCohortUnitError, match="revision"):
        harness.run()
    assert not harness.ledger.is_locked


def test_gbm_seed_colliding_with_a_tft_seed_does_not_mix_units() -> None:
    """GBM seed 22 = TFT seed 22: a atribuição é por (model_version, seed)."""
    harness = _Harness()
    _record_gbm(harness, rows=None)

    harness.run()

    assert "tft:seed=22" in [unit for unit, _ in harness.calls]


def test_completed_unit_with_changed_counts_is_reported_corrupted() -> None:
    harness = _Harness()
    harness.run()
    cohort_id = _cohort_id(_spec())
    harness.index.record(
        asset_id=_ASSET,
        feature_set_name=_FEATURE_SET,
        cohort_id=cohort_id,
        model_version="gbm_quantile",
        seed=_GBM_SEED,
        run_id=f"gbm_quantile-s{_GBM_SEED}-f0",
        fold="0",
        targets_by_horizon={},
        rows=1,
    )

    with pytest.raises(CompletedUnitCorruptedError, match="gbm"):
        harness.run()


def test_failing_unit_is_not_marked_and_the_lock_is_released() -> None:
    harness = _Harness(fail_unit="tft:seed=11")

    with pytest.raises(RuntimeError, match="boom"):
        harness.run()

    completed = harness.ledger.completed_units(_cohort_id(_spec()))
    assert set(completed) == {"baselines", "gbm"}
    assert not harness.ledger.is_locked


@pytest.mark.unit
def test_break_stale_lock_takes_over_an_orphan_lock() -> None:
    harness = _Harness()
    harness.ledger.acquire_writer()  # lock órfão de um processo morto

    with pytest.raises(CohortRunLockedError):
        harness.use_case(RunConfirmatoryCohortCommand(spec=_spec()))
    harness.use_case(RunConfirmatoryCohortCommand(spec=_spec(), break_stale_lock=True))

    assert not harness.ledger.is_locked


@pytest.mark.unit
def test_cohort_model_keys_lists_every_unit_in_run_order() -> None:
    keys = cohort_model_keys(_spec())

    assert list(keys) == ["baselines", "gbm", "tft:seed=11", "tft:seed=22"]
    assert keys["baselines"] == tuple((f"baseline_{b.family}", None) for b in _BASELINES)
    assert keys["gbm"] == (("gbm_quantile", _GBM_SEED),)
    assert keys["tft:seed=22"] == (("tft_quantile", 22),)


@pytest.mark.unit
def test_cohort_model_keys_of_a_draft_is_refused() -> None:
    with pytest.raises(CohortNotFrozenError):
        cohort_model_keys(_spec(gbm_params=None))


@pytest.mark.unit
def test_load_training_grid_reads_the_same_grid_the_run_checks() -> None:
    grid = load_training_grid(store=_store(), asset_id=_ASSET, columns=modeling_columns())

    assert grid_fingerprint(grid, hasher=_HASHER, asset_id=_ASSET) == _fingerprint()
