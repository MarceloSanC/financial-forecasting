"""Helpers do treinador e do cohort extraídos para a inferência (Stage 7.1, Task 02).

A predição a partir do checkpoint (Tasks 04 e 05) só pode chamar as MESMAS funções
que o treino e o cohort usam — nunca recopiá-las (concept 7.1 §1 "extração de
helpers", ADR 7.1.0001 item 2). Cada teste aqui prova que a função pública é o
que o use case de origem já fazia, observado pela sua saída (silver gravado,
argumentos que chegaram ao port, comando que chegou ao callable de treino):

- `tft_run_identity` → o `run_id` que o `TrainTft` grava em `dim_run`;
- `tft_artifact_dir` → o `artifact_dir` que o `TrainTft` passa ao trainer;
- `load_tft_panel` → o painel que o `TrainTft` passa ao trainer;
- `tft_train_command` → o `TrainTftCommand` que o `RunConfirmatoryCohort` monta;
- `check_cohort_declarations` → as exceções e mensagens do cohort (I4);
- `assert_emission_within_request` → a guarda D5 nomeando a partição pedida;
- `THREADS_KEY` → a chave das threads que o probe grava.

Tudo com fakes e o `CanonicalJsonHasher` real (puro, sem I/O).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

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
from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    REQUIRED_KEYS,
    THREADS_KEY,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.application.use_cases.run_baselines import (
    BaselineRunSummary,
    RunBaselinesResult,
)
from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    CohortDeclarationMismatchError,
    DatasetMismatchError,
    RunConfirmatoryCohort,
    RunConfirmatoryCohortCommand,
    check_cohort_declarations,
    tft_train_command,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    GbmRunSummary,
    TrainGbmQuantileResult,
    grid_fingerprint,
    modeling_columns,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    TftRunSummary,
    TrainTft,
    TrainTftCommand,
    TrainTftResult,
    assert_emission_within_request,
    load_tft_panel,
    tft_artifact_dir,
    tft_run_identity,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    TrainingGrid,
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
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import ScopeSpec
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.services.trading_calendar import TradingCalendar
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash
from financial_forecasting.shared.domain.value_objects.trading_sessions import TradingSessions
from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
    FakeAnalyticsRepository,
)
from tests.fakes.features.modeling.in_memory_cohort_progress_ledger import (
    InMemoryCohortProgressLedger,
)
from tests.fakes.features.modeling.in_memory_cohort_run_index import InMemoryCohortRunIndex
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)
from tests.fakes.features.modeling.in_memory_tft_trainer import InMemoryTftTrainer
from tests.fakes.shared.in_memory_clock import FakeClock
from tests.fakes.shared.in_memory_experiment_tracker import FakeExperimentTracker
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

pytestmark = pytest.mark.unit

_HASHER = CanonicalJsonHasher()
_ASSET = "AAPL"
_FEATURE_SET = "fs_all"
_FEATURE_SET_HASH = "f" * 64
_FRIDAY = 4
_N_SESSIONS = 120
_HORIZONS = (1, 2)
_LEVELS = (0.1, 0.5, 0.9)
_GEOMETRY = CohortGeometry(n_folds=2, test_size=3, val_size=5, calib_size=5, embargo=1)
_SEEDS = (11, 22)
_SCOPE = ScopeSpec(asset_id=_ASSET, feature_set_name=_FEATURE_SET, max_horizon=2, cohort_id="c-1")


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


def _store() -> FakeMedallionStore:
    store = FakeMedallionStore()
    store.seed_read_only(layer="processed", table="dataset_tft", asset=_ASSET, rows=_rows())
    return store


def _splitter() -> WalkForwardSplitter:
    return WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=_sessions())))


def _train_command() -> TrainTftCommand:
    return TrainTftCommand(
        scope=_SCOPE,
        params=TftTrainingParams(seed=42, max_encoder_length=12, max_epochs=3),
        horizons=_HORIZONS,
        quantile_levels=_LEVELS,
        n_folds=_GEOMETRY.n_folds,
        test_size=_GEOMETRY.test_size,
        val_size=_GEOMETRY.val_size,
        calib_size=_GEOMETRY.calib_size,
        embargo=_GEOMETRY.embargo,
        schema_version=1,
    )


def _train(tmp_path: Path) -> tuple[TrainTftResult, FakeAnalyticsRepository, InMemoryTftTrainer]:
    repo = FakeAnalyticsRepository(clock=FakeClock())
    trainer = InMemoryTftTrainer()
    use_case = TrainTft(
        store=_store(),
        splitter=_splitter(),
        trainer=trainer,
        persist_predictions=PersistPredictions(repository=repo),
        persist_run_record=PersistRunRecord(repository=repo),
        tracker=FakeExperimentTracker(),
        hasher=_HASHER,
        artifacts_root=tmp_path / "artifacts",
    )
    return use_case(_train_command()), repo, trainer


def _folds(command: TrainTftCommand) -> tuple[Any, ...]:
    return _splitter().split(
        _sessions(),
        command.scope,
        n_folds=command.n_folds,
        test_size=command.test_size,
        val_size=command.val_size,
        calib_size=command.calib_size,
        embargo=command.embargo,
        hasher=_HASHER,
    )


# -- TrainTft: identidade, diretório do artefato, painel ------------------------------


def test_run_id_from_shared_identity_matches_train_tft(tmp_path: Path) -> None:
    result, repo, _ = _train(tmp_path)
    command = _train_command()
    panel = load_tft_panel(store=_store(), asset_id=_ASSET)

    derived = [
        tft_run_identity(
            command=command,
            feature_names=panel.feature_names,
            known_names=panel.known_feature_names,
            fold=fold,
            hasher=_HASHER,
        )
        for fold in _folds(command)
    ]

    assert [run_id for _, run_id in derived] == [run.run_id for run in result.runs]
    recorded = {
        (row["run_id"], row["config_signature"])
        for row in repo.read(layer="silver", table="dim_run")
    }
    assert recorded == {(run_id, signature) for signature, run_id in derived}


def test_artifact_dir_rule_matches_train_tft(tmp_path: Path) -> None:
    result, _, trainer = _train(tmp_path)

    assert [call["artifact_dir"] for call in trainer.calls] == [
        str(tft_artifact_dir(tmp_path / "artifacts", run.run_id)) for run in result.runs
    ]
    assert tft_artifact_dir(Path("root"), "abc") == Path("root") / "tft" / "abc"


def test_load_tft_panel_matches_train_tft_dataset(tmp_path: Path) -> None:
    _, repo, trainer = _train(tmp_path)

    panel = load_tft_panel(store=_store(), asset_id=_ASSET)

    for call in trainer.calls:
        assert call["feature_names"] == panel.feature_names
        assert call["known_feature_names"] == panel.known_feature_names
        assert call["rows"] == panel.rows
        assert call["target"] == panel.target
    assert len(panel.sessions) == len(panel.timestamps) == len(panel.rows) == _N_SESSIONS
    facts = repo.read(layer="silver", table="fact_oos_predictions")
    assert facts
    for fact in facts:
        decision_idx = int(fact["decision_idx"])  # type: ignore[call-overload]
        assert fact["timestamp_utc"] == panel.timestamps[decision_idx]


# -- guarda de emissão (D5 / I12 da 7.1) -------------------------------------------


def test_emission_guard_names_the_partition() -> None:
    with pytest.raises(ValueError, match="outside the requested calib range"):
        assert_emission_within_request(
            grids={7: {1: (0.1,)}, 99: {1: (0.1,)}},
            requested_decision_indices=(7, 8),
            horizons=(1,),
            partition="calib",
        )
    with pytest.raises(ValueError, match="outside the requested test range"):
        assert_emission_within_request(
            grids={99: {1: (0.1,)}},
            requested_decision_indices=(7,),
            horizons=(1,),
            partition="test",
        )
    with pytest.raises(ValueError, match="horizons that were not requested"):
        assert_emission_within_request(
            grids={7: {3: (0.1,)}},
            requested_decision_indices=(7,),
            horizons=(1,),
            partition="calib",
        )
    assert_emission_within_request(
        grids={7: {1: (0.1,)}},
        requested_decision_indices=(7, 8),
        horizons=(1, 2),
        partition="calib",
    )


# -- cohort: declarações (I4) e comando do TFT ---------------------------------------


def _fingerprint() -> str:
    grid = build_training_grid(_rows(), columns=modeling_columns())
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
            gbm_base_params=GbmTrainingParams(seed=7),
            n_trials=5,
            sampler_seed=2026,
        ),
        "tft_params": TftTrainingParams(seed=0, hidden_size=24),
        "gbm_params": GbmTrainingParams(seed=7, num_leaves=16),
        "baseline_specs": BaselineSpec.canonical_five(historical_quantiles_window=20),
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


def _check(spec: CohortSpec, **overrides: object) -> TrainingGrid:
    arguments: dict[str, object] = {
        "store": _store(),
        "hasher": _HASHER,
        "modeling_columns": modeling_columns(),
        "observed_feature_set_hash": _FEATURE_SET_HASH,
        "pipeline_version": PIPELINE_VERSION,
        "supported_device": "cpu",
    }
    arguments.update(overrides)
    return check_cohort_declarations(spec, **arguments)  # type: ignore[arg-type]


def test_declarations_check_returns_the_grid_when_everything_matches() -> None:
    grid = _check(_spec())

    assert len(grid.timestamps) == _N_SESSIONS


@pytest.mark.parametrize(
    ("spec_overrides", "check_overrides", "error", "message"),
    [
        ({"dataset_fingerprint": "0" * 64}, {}, DatasetMismatchError, "materialized data changed"),
        ({}, {"observed_feature_set_hash": "e" * 64}, CohortDeclarationMismatchError, "registry"),
        ({}, {"pipeline_version": "other"}, CohortDeclarationMismatchError, "pipeline_version"),
        ({"device": "rocm"}, {}, CohortDeclarationMismatchError, "device"),
    ],
    ids=["fingerprint", "feature_set_hash", "pipeline_version", "device"],
)
def test_declarations_check_raises_the_cohort_errors(
    spec_overrides: dict[str, object],
    check_overrides: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        _check(_spec(**spec_overrides), **check_overrides)


def test_declarations_check_rejects_sweep_provenance_on_other_data() -> None:
    spec = _spec()
    assert spec.provenance is not None
    other = replace(spec, provenance=replace(spec.provenance, dataset_fingerprint="0" * 64))

    with pytest.raises(CohortDeclarationMismatchError, match="sweeps ran on a different dataset"):
        _check(other)


class _SpyUnits:
    """Callables de treino que capturam o comando e "persistem" no índice de runs."""

    def __init__(self, index: InMemoryCohortRunIndex) -> None:
        self._index = index
        self.tft_commands: list[TrainTftCommand] = []

    def _persist(self, command: Any, model_version: str, seed: int | None) -> list[str]:  # noqa: ANN401
        run_ids = []
        for fold in range(_GEOMETRY.n_folds):
            run_id = f"{model_version}-s{seed}-f{fold}"
            self._index.record(
                asset_id=_ASSET,
                feature_set_name=_FEATURE_SET,
                cohort_id=command.scope.cohort_id,
                model_version=model_version,
                seed=seed,
                run_id=run_id,
                fold=str(fold),
                targets_by_horizon={h: {f"t{fold}-{h}"} for h in _HORIZONS},
                rows=_GEOMETRY.expected_prediction_rows(
                    fold_index=fold, horizons=_HORIZONS, n_levels=len(_LEVELS)
                ),
            )
            run_ids.append(run_id)
        return run_ids

    def baselines(self, command: Any) -> RunBaselinesResult:  # noqa: ANN401
        return RunBaselinesResult(
            runs=tuple(
                BaselineRunSummary(
                    run_id=r,
                    model_version=b.model_version,
                    fold_index=0,
                    rows_written=1,
                    rows_skipped=0,
                )
                for b in command.specs
                for r in self._persist(command, b.model_version, None)
            )
        )

    def gbm(self, command: Any) -> TrainGbmQuantileResult:  # noqa: ANN401
        return TrainGbmQuantileResult(
            runs=tuple(
                GbmRunSummary(
                    run_id=r,
                    model_version="gbm_quantile",
                    fold_index=0,
                    rows_written=1,
                    rows_skipped=0,
                    best_iteration_by_horizon={1: 1},
                )
                for r in self._persist(command, "gbm_quantile", command.params.seed)
            )
        )

    def tft(self, command: TrainTftCommand) -> TrainTftResult:
        self.tft_commands.append(command)
        return TrainTftResult(
            runs=tuple(
                TftRunSummary(
                    run_id=r,
                    model_version="tft_quantile",
                    fold_index=0,
                    rows_written=1,
                    rows_skipped=0,
                    best_epoch=1,
                    best_val_loss=0.1,
                    fitted_decision_count=1,
                    monitored_decision_count=1,
                    artifact_path="x",
                    tracking_run_id="t",
                )
                for r in self._persist(command, "tft_quantile", command.params.seed)
            )
        )


def test_tft_command_builder_matches_confirmatory_cohort_units() -> None:
    spec = _spec()
    index = InMemoryCohortRunIndex()
    spy = _SpyUnits(index)
    use_case = RunConfirmatoryCohort(
        store=_store(),
        hasher=_HASHER,
        clock=FakeClock(),
        ledger=InMemoryCohortProgressLedger(),
        run_index=index,
        probe=InMemoryRuntimeEnvironmentProbe(),
        run_baselines=spy.baselines,
        train_gbm=spy.gbm,
        train_tft=spy.tft,
        modeling_columns=modeling_columns(),
        observed_feature_set_hash=_FEATURE_SET_HASH,
        pipeline_version=PIPELINE_VERSION,
        schema_version=3,
        supported_device="cpu",
    )

    result = use_case(RunConfirmatoryCohortCommand(spec=spec))

    cohort_id = spec.cohort_id(CohortHash.compute(hasher=_HASHER, payload=spec.hash_payload()))
    assert result.cohort_id == cohort_id
    assert spy.tft_commands == [
        tft_train_command(spec, scope=spec.scope(cohort_id), seed=seed, schema_version=3)
        for seed in _SEEDS
    ]


# -- probe: a chave das threads ------------------------------------------------------


def test_threads_key_is_the_probe_key() -> None:
    assert THREADS_KEY == "torch_threads"
    assert THREADS_KEY in REQUIRED_KEYS
