"""Unit test dos comandos do cohort (Stage 5.5, Task 28).

Com fakes: os sweeps recebem a geometria EXPLORATÓRIA (espião nos comandos) e o
scope id do rascunho; `--n-trials` sobrepõe e muda o scope id; `sweep` e
`freeze` com o lock já detido erguem `CohortRunLockedError`; o `run` não
adquire o lock no comando; a proveniência do `freeze` vem dos resultados
gravados pelo `sweep`; `verify` sai 0 com a corrida completa e ≠ 0 com
divergência; e o módulo não importa `features.evaluation` (cegamento).
"""

from __future__ import annotations

import ast
import importlib
import inspect
import io
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.modeling.application.dtos.cohort_spec import (
    CohortSpec,
    SweepPlan,
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
from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    CohortNotFrozenError,
    DatasetMismatchError,
    RunConfirmatoryCohortCommand,
    RunConfirmatoryCohortResult,
    cohort_model_keys,
)
from financial_forecasting.features.modeling.application.use_cases.run_gbm_sweep import (
    GbmSweepTrialSummary,
    RunGbmSweepCommand,
    RunGbmSweepResult,
)
from financial_forecasting.features.modeling.application.use_cases.run_tft_sweep import (
    RunTftSweepCommand,
    RunTftSweepResult,
    SweepTrialSummary,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    grid_fingerprint,
    modeling_columns,
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
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

_MODULE = "financial_forecasting.features.modeling.adapters.in.cli.cohort_commands"
commands: Any = importlib.import_module(_MODULE)
cohort_file: Any = importlib.import_module(
    "financial_forecasting.features.modeling.adapters.in.cli.cohort_file"
)

_HASHER = CanonicalJsonHasher()
_ASSET = "AAPL"
_FEATURE_SET = "fs_all"
_FRIDAY = 4
_N_SESSIONS = 120
_HORIZONS = (1, 2)
_LEVELS = (0.1, 0.5, 0.9)
_GEOMETRY = CohortGeometry(n_folds=2, test_size=10, val_size=8, calib_size=6, embargo=1)
_N_TRIALS = 3
_SAMPLER_SEED = 2026
_TFT_BEST_OBJECTIVE = 0.2
_GBM_BEST_LEAVES = 9


def _rows(shift: float = 0.0) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    current = date(2021, 1, 4)
    while len(rows) < _N_SESSIONS:
        if current.weekday() <= _FRIDAY:
            row: dict[str, object] = {
                "timestamp": datetime(current.year, current.month, current.day, tzinfo=UTC),
                "asset_id": _ASSET,
            }
            for position, name in enumerate(modeling_columns()):
                row[name] = float(len(rows)) + position / 100.0 + shift
            rows.append(row)
        current += timedelta(days=1)
    return rows


def _fingerprint(rows: list[dict[str, object]]) -> str:
    grid = build_training_grid(rows, columns=modeling_columns())
    return grid_fingerprint(grid, hasher=_HASHER, asset_id=_ASSET)


def _draft(**overrides: object) -> CohortSpec:
    base: dict[str, object] = {
        "name": "aapl_confirmatory",
        "revision": 0,
        "asset_id": _ASSET,
        "feature_set_name": _FEATURE_SET,
        "feature_set_hash": "f" * 64,
        "pipeline_version": PIPELINE_VERSION,
        "horizons": _HORIZONS,
        "quantile_levels": _LEVELS,
        "geometry": _GEOMETRY,
        "device": "cpu",
        "seeds": (11, 22),
        "sweep": SweepPlan(
            tft_space=(SearchDimension(name="hidden_size", low=8, high=64, kind="int"),),
            tft_base_params=TftTrainingParams(seed=0),
            gbm_space=(SearchDimension(name="num_leaves", low=4, high=64, kind="int"),),
            gbm_base_params=GbmTrainingParams(seed=7),
            n_trials=_N_TRIALS,
            sampler_seed=_SAMPLER_SEED,
        ),
        "tft_params": None,
        "gbm_params": None,
        "baseline_specs": BaselineSpec.canonical_five(historical_quantiles_window=20),
        "provenance": None,
        "dataset_fingerprint": None,
    }
    base.update(overrides)
    return CohortSpec(**base)  # type: ignore[arg-type]


class _Harness:
    """Deps dos comandos com fakes; os sweeps e o use case são espiões."""

    def __init__(self, tmp_path: Path, spec: CohortSpec, rows: list[dict[str, object]]) -> None:
        self.path = tmp_path / "cohort.toml"
        self.path.write_text(cohort_file.dump(spec), encoding="utf-8")
        self.store = FakeMedallionStore()
        self.store.seed_read_only(layer="processed", table="dataset_tft", asset=_ASSET, rows=rows)
        self.swept_on = _fingerprint(rows)
        self.ledger = InMemoryCohortProgressLedger()
        self.index = InMemoryCohortRunIndex()
        self.tft_calls: list[RunTftSweepCommand] = []
        self.gbm_calls: list[RunGbmSweepCommand] = []
        self.run_calls: list[tuple[Path, str, RunConfirmatoryCohortCommand]] = []
        self.lock_held_during_run: bool | None = None
        self.out = io.StringIO()
        self.deps = commands.CohortCommandDeps(
            store=self.store,
            hasher=_HASHER,
            ledger=self.ledger,
            run_index=self.index,
            run_tft_sweep=self._tft,
            run_gbm_sweep=self._gbm,
            confirmatory_cohort_for=self._cohort_for,
            modeling_columns=modeling_columns(),
            load_spec=cohort_file.load,
            parse_spec=cohort_file.parse,
            dump_spec=cohort_file.dump,
        )

    def _tft(self, command: RunTftSweepCommand) -> RunTftSweepResult:
        self.tft_calls.append(command)
        return RunTftSweepResult(
            study_id="tft-study",
            trials=(
                SweepTrialSummary(trial_number=0, values={"hidden_size": 8}, objective_value=0.3),
                SweepTrialSummary(trial_number=1, values={"hidden_size": 24}, objective_value=0.2),
            ),
            best_trial_number=1,
            best_params=replace(command.base_params, hidden_size=24),
            dataset_fingerprint=self.swept_on,
        )

    def _gbm(self, command: RunGbmSweepCommand) -> RunGbmSweepResult:
        self.gbm_calls.append(command)
        return RunGbmSweepResult(
            study_id="gbm-study",
            trials=(
                GbmSweepTrialSummary(trial_number=0, values={"num_leaves": 9}, objective_value=0.4),
            ),
            best_trial_number=0,
            best_params=replace(command.base_params, num_leaves=9),
            dataset_fingerprint=self.swept_on,
        )

    def _cohort_for(
        self, path: Path, device: str
    ) -> Callable[[RunConfirmatoryCohortCommand], RunConfirmatoryCohortResult]:
        def use_case(command: RunConfirmatoryCohortCommand) -> RunConfirmatoryCohortResult:
            # Se o comando tivesse adquirido o lock, esta aquisição falharia.
            self.ledger.acquire_writer()
            self.ledger.release_writer()
            self.run_calls.append((path, device, command))
            return RunConfirmatoryCohortResult(cohort_id="c", cohort_hash="h", outcomes=())

        return use_case

    def spec(self) -> CohortSpec:
        spec: CohortSpec = cohort_file.load(self.path)
        return spec

    def scope_id(self, spec: CohortSpec) -> str:
        draft_hash = CohortHash.compute(hasher=_HASHER, payload=spec.draft_payload())
        return spec.exploratory_scope_id(draft_hash)


@pytest.fixture
def harness(tmp_path: Path) -> _Harness:
    return _Harness(tmp_path, _draft(), _rows())


# -- sweep -------------------------------------------------------------------------------


@pytest.mark.unit
def test_sweeps_receive_the_exploratory_geometry_and_the_draft_scope_id(harness: _Harness) -> None:
    assert commands.sweep(harness.deps, harness.path, out=harness.out) == 0

    exploratory = _GEOMETRY.exploratory()
    scope_id = harness.scope_id(_draft())
    for call in (*harness.tft_calls, *harness.gbm_calls):
        assert call.n_folds == exploratory.n_folds == 1
        assert call.test_size == exploratory.test_size == _GEOMETRY.oos_sessions
        assert (call.val_size, call.calib_size, call.embargo) == (8, 6, 1)
        assert call.scope.cohort_id == scope_id
        assert call.n_trials == _N_TRIALS
        assert call.seed == _SAMPLER_SEED
        assert call.horizons == _HORIZONS
        assert call.quantile_levels == _LEVELS
    assert harness.tft_calls[0].space == _draft().sweep.tft_space
    assert harness.gbm_calls[0].base_params == _draft().sweep.gbm_base_params
    recorded = harness.ledger.sweep_results(scope_id)
    assert recorded["tft"]["best_objective"] == _TFT_BEST_OBJECTIVE
    assert recorded["gbm"]["best_params"]["num_leaves"] == _GBM_BEST_LEAVES


@pytest.mark.unit
def test_n_trials_override_wins_and_changes_the_scope_id(tmp_path: Path) -> None:
    harness = _Harness(tmp_path, _draft(), _rows())

    commands.sweep(harness.deps, harness.path, out=harness.out, n_trials=1)

    measured = replace(_draft(), sweep=replace(_draft().sweep, n_trials=1))
    assert harness.tft_calls[0].n_trials == 1
    assert harness.tft_calls[0].scope.cohort_id == harness.scope_id(measured)
    assert harness.scope_id(measured) != harness.scope_id(_draft())


@pytest.mark.unit
def test_sweep_without_n_trials_is_refused(tmp_path: Path) -> None:
    draft = _draft(sweep=replace(_draft().sweep, n_trials=None))
    harness = _Harness(tmp_path, draft, _rows())

    with pytest.raises(commands.CohortCommandError, match="n_trials"):
        commands.sweep(harness.deps, harness.path, out=harness.out)
    assert harness.tft_calls == []


@pytest.mark.unit
def test_a_sweep_already_recorded_is_not_run_again(harness: _Harness) -> None:
    commands.sweep(harness.deps, harness.path, out=harness.out)

    commands.sweep(harness.deps, harness.path, out=harness.out)

    assert len(harness.tft_calls) == len(harness.gbm_calls) == 1
    assert "already recorded" in harness.out.getvalue()


@pytest.mark.unit
@pytest.mark.parametrize("command", ["sweep", "freeze"])
def test_sweep_and_freeze_refuse_when_the_lock_is_held(harness: _Harness, command: str) -> None:
    commands.sweep(harness.deps, harness.path, out=harness.out)
    harness.ledger.acquire_writer()  # outro processo detém o lock do data_root

    with pytest.raises(CohortRunLockedError):
        getattr(commands, command)(harness.deps, harness.path, out=harness.out)


@pytest.mark.unit
def test_lock_is_released_even_when_a_sweep_fails(harness: _Harness) -> None:
    def boom(command: RunTftSweepCommand) -> RunTftSweepResult:
        raise RuntimeError("trainer crashed")

    deps = replace(harness.deps, run_tft_sweep=boom)
    with pytest.raises(RuntimeError, match="crashed"):
        commands.sweep(deps, harness.path, out=harness.out)

    harness.ledger.acquire_writer()  # não fica preso


# -- freeze ------------------------------------------------------------------------------


@pytest.mark.unit
def test_freeze_writes_params_and_provenance_from_the_recorded_results(
    harness: _Harness,
) -> None:
    commands.sweep(harness.deps, harness.path, out=harness.out)
    harness.tft_calls.clear()

    assert commands.freeze(harness.deps, harness.path, out=harness.out) == 0

    frozen = harness.spec()
    assert frozen.is_frozen()
    assert harness.tft_calls == []  # nenhum retreino no freeze
    assert frozen.tft_params == TftTrainingParams(seed=0, hidden_size=24)
    assert frozen.gbm_params == GbmTrainingParams(seed=7, num_leaves=9)
    provenance = frozen.provenance
    assert provenance is not None
    assert (provenance.tft_study_id, provenance.tft_best_trial) == ("tft-study", 1)
    assert provenance.tft_best_objective == _TFT_BEST_OBJECTIVE
    assert (provenance.gbm_study_id, provenance.gbm_best_trial) == ("gbm-study", 0)
    assert provenance.dataset_fingerprint == harness.swept_on
    assert frozen.dataset_fingerprint == harness.swept_on
    cohort_hash = CohortHash.compute(hasher=_HASHER, payload=frozen.hash_payload())
    assert cohort_hash.value in harness.out.getvalue()
    assert frozen.cohort_id(cohort_hash) in harness.out.getvalue()


@pytest.mark.unit
def test_provenance_comes_from_the_ledger_not_from_a_reread(harness: _Harness) -> None:
    """O resultado gravado manda: adulterá-lo no ledger aparece no congelado."""
    commands.sweep(harness.deps, harness.path, out=harness.out)
    scope_id = harness.scope_id(_draft())
    tft = dict(harness.ledger.sweep_results(scope_id)["tft"])
    tft["study_id"] = "from-the-ledger"
    harness.ledger.record_sweep_result(scope_id, "tft", tft)

    commands.freeze(harness.deps, harness.path, out=harness.out)

    provenance = harness.spec().provenance
    assert provenance is not None
    assert provenance.tft_study_id == "from-the-ledger"


@pytest.mark.unit
def test_freeze_refuses_when_the_data_changed_after_the_sweeps(tmp_path: Path) -> None:
    harness = _Harness(tmp_path, _draft(), _rows())
    commands.sweep(harness.deps, harness.path, out=harness.out)
    rematerialized = FakeMedallionStore()
    rematerialized.seed_read_only(
        layer="processed", table="dataset_tft", asset=_ASSET, rows=_rows(shift=0.5)
    )

    with pytest.raises(DatasetMismatchError, match="changed after the sweeps"):
        commands.freeze(replace(harness.deps, store=rematerialized), harness.path, out=harness.out)
    assert not harness.spec().is_frozen()


@pytest.mark.unit
def test_freeze_without_recorded_sweeps_is_refused(harness: _Harness) -> None:
    with pytest.raises(commands.CohortCommandError, match="run sweep first"):
        commands.freeze(harness.deps, harness.path, out=harness.out)


@pytest.mark.unit
def test_freeze_without_seeds_is_refused(tmp_path: Path) -> None:
    harness = _Harness(tmp_path, _draft(seeds=()), _rows())

    with pytest.raises(commands.CohortCommandError, match="seeds"):
        commands.freeze(harness.deps, harness.path, out=harness.out)


@pytest.mark.unit
def test_freezing_twice_is_refused(harness: _Harness) -> None:
    commands.sweep(harness.deps, harness.path, out=harness.out)
    commands.freeze(harness.deps, harness.path, out=harness.out)

    with pytest.raises(commands.CohortCommandError, match="already frozen"):
        commands.freeze(harness.deps, harness.path, out=harness.out)


# -- run ---------------------------------------------------------------------------------


@pytest.mark.unit
def test_run_does_not_take_the_lock_and_passes_path_device_and_flag(harness: _Harness) -> None:
    commands.sweep(harness.deps, harness.path, out=harness.out)
    commands.freeze(harness.deps, harness.path, out=harness.out)

    assert commands.run(harness.deps, harness.path, out=harness.out, break_stale_lock=True) == 0

    ((path, device, command),) = harness.run_calls
    assert (path, device) == (harness.path, "cpu")
    assert command.spec == harness.spec()
    assert command.break_stale_lock is True


# -- verify ------------------------------------------------------------------------------


def _frozen_harness(tmp_path: Path) -> tuple[_Harness, CohortSpec, str]:
    harness = _Harness(tmp_path, _draft(), _rows())
    commands.sweep(harness.deps, harness.path, out=harness.out)
    commands.freeze(harness.deps, harness.path, out=harness.out)
    spec = harness.spec()
    cohort_id = spec.cohort_id(CohortHash.compute(hasher=_HASHER, payload=spec.hash_payload()))
    return harness, spec, cohort_id


def _record_complete_run(harness: _Harness, spec: CohortSpec, cohort_id: str) -> None:
    """Silver e ledger de uma corrida completa (o `verify` confere os dois — A8)."""
    for unit_key, keys in cohort_model_keys(spec).items():
        rows_by_run: dict[str, int] = {}
        for model_version, seed in keys:
            for fold in range(_GEOMETRY.n_folds):
                rows = _GEOMETRY.expected_prediction_rows(
                    fold_index=fold, horizons=_HORIZONS, n_levels=len(_LEVELS)
                )
                rows_by_run[f"{model_version}-{seed}-{fold}"] = rows
                harness.index.record(
                    asset_id=_ASSET,
                    feature_set_name=_FEATURE_SET,
                    cohort_id=cohort_id,
                    model_version=model_version,
                    seed=seed,
                    run_id=f"{model_version}-{seed}-{fold}",
                    fold=str(fold),
                    targets_by_horizon={h: {f"t{fold}-{h}"} for h in _HORIZONS},
                    rows=rows,
                )
        harness.ledger.mark_completed(cohort_id, unit_key, rows_by_run)


@pytest.mark.unit
def test_verify_exits_zero_when_every_model_has_every_fold(tmp_path: Path) -> None:
    harness, spec, cohort_id = _frozen_harness(tmp_path)
    _record_complete_run(harness, spec, cohort_id)
    out = io.StringIO()

    assert commands.verify(harness.deps, harness.path, out=out) == 0

    n_models = 5 + 1 + 2  # baselines + GBM + seeds do TFT
    per_set = sum(
        _GEOMETRY.expected_prediction_rows(fold_index=f, horizons=_HORIZONS, n_levels=3)
        for f in range(_GEOMETRY.n_folds)
    )
    assert f"rows expected {per_set * n_models}, observed {per_set * n_models}" in out.getvalue()
    assert out.getvalue().rstrip().endswith("OK")


@pytest.mark.unit
def test_verify_exits_nonzero_on_runs_of_an_undeclared_model(tmp_path: Path) -> None:
    harness, spec, cohort_id = _frozen_harness(tmp_path)
    _record_complete_run(harness, spec, cohort_id)
    harness.index.record(
        asset_id=_ASSET,
        feature_set_name=_FEATURE_SET,
        cohort_id=cohort_id,
        model_version="tft_quantile",
        seed=33,
        run_id="stray",
        fold="0",
        targets_by_horizon={h: {f"t0-{h}"} for h in _HORIZONS},
        rows=1,
    )
    out = io.StringIO()

    assert commands.verify(harness.deps, harness.path, out=out) == 1
    assert "undeclared models" in out.getvalue()


@pytest.mark.unit
def test_verify_exits_nonzero_on_wrong_counts_or_targets(tmp_path: Path) -> None:
    harness, spec, cohort_id = _frozen_harness(tmp_path)
    _record_complete_run(harness, spec, cohort_id)
    harness.index.record(
        asset_id=_ASSET,
        feature_set_name=_FEATURE_SET,
        cohort_id=cohort_id,
        model_version="gbm_quantile",
        seed=7,
        run_id="gbm_quantile-7-1",
        fold="1",
        targets_by_horizon={h: {"other"} for h in _HORIZONS},
        rows=5,
    )
    out = io.StringIO()

    assert commands.verify(harness.deps, harness.path, out=out) == 1
    assert "has 5 rows" in out.getvalue()
    assert "fold 1: target_timestamp sets differ" in out.getvalue()


@pytest.mark.unit
def test_verify_with_nothing_recorded_fails(tmp_path: Path) -> None:
    harness, _, _ = _frozen_harness(tmp_path)
    out = io.StringIO()

    assert commands.verify(harness.deps, harness.path, out=out) == 1
    assert "folds []" in out.getvalue()


@pytest.mark.unit
def test_verify_refuses_a_draft(harness: _Harness) -> None:
    with pytest.raises(CohortNotFrozenError):
        commands.verify(harness.deps, harness.path, out=harness.out)


# -- cegamento ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_commands_module_imports_nothing_from_evaluation() -> None:
    """Preventivo: `features.evaluation` ainda não existe em `src/` (entra na 6.x)."""
    tree = ast.parse(inspect.getsource(commands))
    imported = [
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ] + [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]

    assert imported  # o teste leu imports de verdade
    assert not [name for name in imported if ".features.evaluation" in name]
    assert "evaluation" not in {part for name in imported for part in name.split(".")}


@pytest.mark.unit
def test_verify_exits_nonzero_when_a_declared_model_misses_one_fold(tmp_path: Path) -> None:
    """G8 (Checkpoint C 24-31): um fold ausente de um modelo declarado."""
    harness, spec, cohort_id = _frozen_harness(tmp_path)
    _record_complete_run(harness, spec, cohort_id)
    runs = harness.index._runs[(cohort_id, _ASSET, _FEATURE_SET)]
    runs[("tft_quantile", 22)].pop("tft_quantile-22-1")
    out = io.StringIO()

    assert commands.verify(harness.deps, harness.path, out=out) == commands.EXIT_MISMATCH
    assert "tft_quantile seed=22: folds [0], expected 0..1" in out.getvalue()


@pytest.mark.unit
def test_verify_exits_nonzero_when_the_ledger_misses_a_unit(tmp_path: Path) -> None:
    """F2 (Checkpoint C 24-31): silver completo sem a marcação no ledger não é corrida
    concluída (queda entre a gravação da última unidade e o `mark_completed`)."""
    harness, spec, cohort_id = _frozen_harness(tmp_path)
    _record_complete_run(harness, spec, cohort_id)
    harness.ledger._units[cohort_id].pop("tft:seed=22")
    out = io.StringIO()

    assert commands.verify(harness.deps, harness.path, out=out) == commands.EXIT_MISMATCH
    assert "ledger: unit 'tft:seed=22' is not marked completed" in out.getvalue()


@pytest.mark.unit
def test_verify_exits_nonzero_when_ledger_counts_differ_from_the_silver(tmp_path: Path) -> None:
    harness, spec, cohort_id = _frozen_harness(tmp_path)
    _record_complete_run(harness, spec, cohort_id)
    harness.ledger._units[cohort_id]["gbm"]["gbm_quantile-7-0"] = 1
    out = io.StringIO()

    assert commands.verify(harness.deps, harness.path, out=out) == commands.EXIT_MISMATCH
    assert "ledger: unit 'gbm' counts differ" in out.getvalue()


@pytest.mark.unit
def test_freeze_refuses_a_file_that_would_not_read_back_the_same(harness: _Harness) -> None:
    """F3 (Checkpoint C 24-31): o hash publicado tem de ser o do arquivo gravado."""
    commands.sweep(harness.deps, harness.path, out=harness.out)
    before = harness.path.read_text(encoding="utf-8")

    def lossy_dump(spec: CohortSpec) -> str:
        text: str = cohort_file.dump(spec)
        return text.replace("num_leaves = 9", "num_leaves = 10")

    deps = replace(harness.deps, dump_spec=lossy_dump)
    with pytest.raises(commands.CohortCommandError, match="round trip"):
        commands.freeze(deps, harness.path, out=harness.out)
    assert harness.path.read_text(encoding="utf-8") == before
    assert not list(harness.path.parent.glob("*.tmp-*"))
