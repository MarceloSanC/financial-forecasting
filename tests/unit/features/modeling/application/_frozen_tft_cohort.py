"""Cohort TFT congelado e sintético para a predição a partir do checkpoint (Stage 7.1).

Monta, só com fakes, o que os use cases fornecedores da 7.1 leem:

- o painel do dataset TFT no `FakeMedallionStore` (todas as `modeling_columns()`);
- um `CohortSpec` congelado cujo fingerprint é o do painel;
- o ORÁCULO dos runs: o `TrainTft` de verdade, rodado com o `InMemoryTftTrainer`
  pelo `TrainTftCommand` que o cohort monta, devolve `run_id` e `artifact_dir` de
  cada fold — os use cases da 7.1 têm de chegar aos mesmos valores;
- o que o silver teria (`InMemoryCohortRunIndex`) e os checkpoints em disco
  (`InMemoryCheckpointLocator`) desses runs.

Reusado pelos testes dos use cases do modeling (Task 05) e pelos contratos dos
ports do `inference` (Task 07).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictions,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_run_record import (  # noqa: E501
    PersistRunRecord,
)
from financial_forecasting.features.modeling.application.dtos.cohort_spec import (
    CohortSpec,
    SweepPlan,
    SweepProvenance,
)
from financial_forecasting.features.modeling.application.pipeline_version import PIPELINE_VERSION
from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    SearchDimension,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    tft_train_command,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    grid_fingerprint,
    modeling_columns,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    MODEL_VERSION,
    TrainTft,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    build_training_grid,
)
from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
    WalkForwardSplitter,
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
from financial_forecasting.shared.domain.services.trading_calendar import TradingCalendar
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash
from financial_forecasting.shared.domain.value_objects.trading_sessions import TradingSessions
from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
    FakeAnalyticsRepository,
)
from tests.fakes.features.modeling.in_memory_checkpoint_locator import InMemoryCheckpointLocator
from tests.fakes.features.modeling.in_memory_cohort_run_index import InMemoryCohortRunIndex
from tests.fakes.features.modeling.in_memory_tft_trainer import InMemoryTftTrainer
from tests.fakes.shared.in_memory_clock import FakeClock
from tests.fakes.shared.in_memory_experiment_tracker import FakeExperimentTracker
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

HASHER = CanonicalJsonHasher()
ASSET = "AAPL"
FEATURE_SET = "fs_all"
FEATURE_SET_HASH = "f" * 64
HORIZONS = (1, 2)
LEVELS = (0.1, 0.5, 0.9)
GEOMETRY = CohortGeometry(n_folds=2, test_size=3, val_size=5, calib_size=5, embargo=1)
SEEDS = (11, 22)
N_SESSIONS = 120
SCHEMA_VERSION = 1
_FRIDAY = 4


@dataclass(frozen=True)
class OracleRun:
    """O que o `TrainTft` grava para um fold: identidade e diretório do artefato."""

    fold_index: int
    run_id: str
    artifact_dir: str


def sessions() -> tuple[date, ...]:
    days: list[date] = []
    current = date(2021, 1, 4)
    while len(days) < N_SESSIONS:
        if current.weekday() <= _FRIDAY:
            days.append(current)
        current += timedelta(days=1)
    return tuple(days)


def dataset_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx, day in enumerate(sessions()):
        row: dict[str, object] = {
            "timestamp": datetime(day.year, day.month, day.day, tzinfo=UTC),
            "asset_id": ASSET,
        }
        for position, name in enumerate(modeling_columns()):
            row[name] = float(idx) + position / 100.0
        rows.append(row)
    return rows


def store() -> FakeMedallionStore:
    medallion = FakeMedallionStore()
    medallion.seed_read_only(
        layer="processed", table="dataset_tft", asset=ASSET, rows=dataset_rows()
    )
    return medallion


def splitter() -> WalkForwardSplitter:
    return WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=sessions())))


def fingerprint() -> str:
    grid = build_training_grid(dataset_rows(), columns=modeling_columns())
    return grid_fingerprint(grid, hasher=HASHER, asset_id=ASSET)


def frozen_spec(**overrides: object) -> CohortSpec:
    """Spec congelado do cohort sintético (`overrides` troca campos do dataclass)."""
    digest = fingerprint()
    base: dict[str, object] = {
        "name": "aapl_confirmatory",
        "revision": 0,
        "asset_id": ASSET,
        "feature_set_name": FEATURE_SET,
        "feature_set_hash": FEATURE_SET_HASH,
        "pipeline_version": PIPELINE_VERSION,
        "horizons": HORIZONS,
        "quantile_levels": LEVELS,
        "geometry": GEOMETRY,
        "device": "cpu",
        "seeds": SEEDS,
        "sweep": SweepPlan(
            tft_space=(SearchDimension(name="hidden_size", low=8, high=64, kind="int"),),
            tft_base_params=TftTrainingParams(seed=0),
            gbm_space=(SearchDimension(name="num_leaves", low=4, high=64, kind="int"),),
            gbm_base_params=GbmTrainingParams(seed=7),
            n_trials=5,
            sampler_seed=2026,
        ),
        "tft_params": TftTrainingParams(seed=0, max_encoder_length=12, max_epochs=2, batch_size=16),
        "gbm_params": GbmTrainingParams(seed=7, num_leaves=16),
        "baseline_specs": BaselineSpec.canonical_five(historical_quantiles_window=20),
        "provenance": SweepProvenance(
            tft_study_id="s1",
            tft_best_trial=1,
            tft_best_objective=0.1,
            gbm_study_id="s2",
            gbm_best_trial=2,
            gbm_best_objective=0.2,
            dataset_fingerprint=digest,
        ),
        "dataset_fingerprint": digest,
    }
    base.update(overrides)
    return CohortSpec(**base)  # type: ignore[arg-type]


def cohort_id(spec: CohortSpec) -> str:
    return spec.cohort_id(CohortHash.compute(hasher=HASHER, payload=spec.hash_payload()))


def oracle_runs(spec: CohortSpec, seed: int, artifacts_root: Path) -> tuple[OracleRun, ...]:
    """Os runs que o `TrainTft` grava para `seed` — o oráculo dos use cases da 7.1."""
    repository = FakeAnalyticsRepository(clock=FakeClock())
    trainer = InMemoryTftTrainer()
    TrainTft(
        store=store(),
        splitter=splitter(),
        trainer=trainer,
        persist_predictions=PersistPredictions(repository=repository),
        persist_run_record=PersistRunRecord(repository=repository),
        tracker=FakeExperimentTracker(),
        hasher=HASHER,
        artifacts_root=artifacts_root,
    )(
        tft_train_command(
            spec, scope=spec.scope(cohort_id(spec)), seed=seed, schema_version=SCHEMA_VERSION
        )
    )
    by_fold = {
        int(str(row["fold"])): str(row["run_id"])
        for row in repository.read(layer="silver", table="dim_run")
    }
    return tuple(
        OracleRun(fold_index=fold, run_id=by_fold[fold], artifact_dir=call["artifact_dir"])
        for fold, call in enumerate(trainer.calls)
    )


def record_runs(
    index: InMemoryCohortRunIndex, spec: CohortSpec, runs: tuple[OracleRun, ...], seed: int
) -> None:
    """Registra no índice o que o silver teria: um run completo por fold."""
    for run in runs:
        index.record(
            asset_id=ASSET,
            feature_set_name=FEATURE_SET,
            cohort_id=cohort_id(spec),
            model_version=MODEL_VERSION,
            seed=seed,
            run_id=run.run_id,
            fold=str(run.fold_index),
            targets_by_horizon={h: {f"t{run.fold_index}-{h}"} for h in spec.horizons},
            rows=spec.geometry.expected_prediction_rows(
                fold_index=run.fold_index,
                horizons=spec.horizons,
                n_levels=len(spec.quantile_levels),
            ),
        )


def checkpoint_bytes(run_id: str) -> bytes:
    return f"checkpoint-of-{run_id}".encode()


def write_checkpoints(locator: InMemoryCheckpointLocator, runs: tuple[OracleRun, ...]) -> None:
    """Um `best.ckpt` (e um arquivo que não é checkpoint) no diretório de cada run."""
    for run in runs:
        locator.add_file(run.artifact_dir, "best.ckpt", checkpoint_bytes(run.run_id))
        locator.add_file(run.artifact_dir, "metrics.csv", b"epoch,val_loss")
