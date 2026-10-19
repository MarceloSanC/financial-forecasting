"""`RunAblationCohort` com fakes (Stage 7.3, Task 08; CA4, I2, I3, I5, C3, C4).

O `TrainTft` é um stub que registra o comando e grava no `InMemoryCohortRunIndex` o
que o silver teria (um run por fold, com a contagem esperada da geometria da base),
sob o `feature_set_name` e o `model_version` do comando. A base é o spec sintético
congelado de `test_run_confirmatory_cohort.py`.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from financial_forecasting.features.modeling.application.dtos.ablation_cohort_spec import (
    ABLATION_CONFIGURATIONS,
    ABLATION_FEATURE_SET_NAME,
    AblationCohortSpec,
    AblationConfiguration,
    excluded_family_of,
)
from financial_forecasting.features.modeling.application.pipeline_version import PIPELINE_VERSION
from financial_forecasting.features.modeling.application.use_cases.cohort_unit_runner import (
    CohortNotFrozenError,
    CompletedUnitCorruptedError,
    DatasetMismatchError,
    EnvironmentMismatchError,
    PartialCohortUnitError,
    recorded_run_problems,
)
from financial_forecasting.features.modeling.application.use_cases.run_ablation_cohort import (
    RunAblationCohort,
    RunAblationCohortCommand,
    ablation_model_keys,
)
from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    tft_train_command,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    modeling_columns,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    TftRunSummary,
    TrainTftResult,
    registry_family_partition,
    tft_feature_set_hash,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import ScopeSpec
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash
from tests.fakes.features.modeling.in_memory_cohort_progress_ledger import (
    InMemoryCohortProgressLedger,
)
from tests.fakes.features.modeling.in_memory_cohort_run_index import InMemoryCohortRunIndex
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)
from tests.fakes.shared.in_memory_clock import FakeClock
from tests.unit.features.modeling.application.test_run_confirmatory_cohort import (
    _ASSET,
    _FEATURE_SET_HASH,
    _GEOMETRY,
    _HASHER,
    _HORIZONS,
    _LEVELS,
    _rows,
    _spec,
    _store,
    _targets,
)

pytestmark = pytest.mark.unit

_TORCH = "2.13.0+rocm6.4"
_SEEDS = (1, 2)


def _base() -> Any:  # noqa: ANN401
    return _spec()


def _ablation(**overrides: Any) -> AblationCohortSpec:  # noqa: ANN401
    base = _base()
    base_hash = CohortHash.compute(hasher=_HASHER, payload=base.hash_payload())
    fields: dict[str, Any] = {
        "name": "aapl_ablation",
        "revision": 0,
        "base_cohort_file": "config/cohorts/aapl_confirmatory.toml",
        "base_cohort_id": base.cohort_id(base_hash),
        "base_cohort_hash": base_hash.value,
        "feature_set_name": ABLATION_FEATURE_SET_NAME,
        "configurations": tuple(
            AblationConfiguration.of(
                name, feature_set_hash=tft_feature_set_hash(excluded_family_of(name))
            )
            for name in ABLATION_CONFIGURATIONS
        ),
        "family_partition": registry_family_partition(),
        "seeds": _SEEDS,
        "device": "rocm",
        "torch_build": _TORCH,
    }
    fields.update(overrides)
    return AblationCohortSpec(**fields)


def _cohort_id(spec: AblationCohortSpec) -> str:
    return spec.cohort_id(CohortHash.compute(hasher=_HASHER, payload=spec.hash_payload()))


def _gpu_probe(**overrides: str) -> InMemoryRuntimeEnvironmentProbe:
    return InMemoryRuntimeEnvironmentProbe.with_gpu(
        **{"torch": _TORCH, "hip_version": "6.4.43482", **overrides}
    )


class _Harness:
    def __init__(
        self,
        *,
        store: Any = None,  # noqa: ANN401
        probe: InMemoryRuntimeEnvironmentProbe | None = None,
        fail_unit: str | None = None,
    ) -> None:
        self.ledger = InMemoryCohortProgressLedger()
        self.index = InMemoryCohortRunIndex()
        self.commands: list[Any] = []
        self._fail_unit = fail_unit
        self.probe = probe if probe is not None else _gpu_probe()
        self.use_case = RunAblationCohort(
            store=store if store is not None else _store(),
            hasher=_HASHER,
            clock=FakeClock(),
            ledger=self.ledger,
            run_index=self.index,
            probe=self.probe,
            train_tft=self._tft,
            modeling_columns=modeling_columns(),
            observed_feature_set_hash=_FEATURE_SET_HASH,
            pipeline_version=PIPELINE_VERSION,
            schema_version=1,
            base_supported_device="cpu",
        )

    def persist(self, command: Any, *, folds: range | None = None) -> list[tuple[str, int, int]]:  # noqa: ANN401
        persisted = []
        for fold in folds if folds is not None else range(_GEOMETRY.n_folds):
            rows = _GEOMETRY.expected_prediction_rows(
                fold_index=fold, horizons=_HORIZONS, n_levels=len(_LEVELS)
            )
            run_id = f"{command.model_version}-s{command.params.seed}-f{fold}"
            self.index.record(
                asset_id=_ASSET,
                feature_set_name=command.scope.feature_set_name,
                cohort_id=command.scope.cohort_id,
                model_version=command.model_version,
                seed=command.params.seed,
                run_id=run_id,
                fold=str(fold),
                targets_by_horizon=_targets(fold),
                rows=rows,
            )
            persisted.append((run_id, fold, rows))
        return persisted

    def _tft(self, command: Any) -> TrainTftResult:  # noqa: ANN401
        self.commands.append(command)
        if self._fail_unit == (command.model_version, command.params.seed):
            raise RuntimeError("boom")
        runs = [
            TftRunSummary(
                run_id=r,
                model_version=command.model_version,
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
            for r, f, n in self.persist(command)
        ]
        return TrainTftResult(runs=tuple(runs))

    def run(self, spec: AblationCohortSpec | None = None, base: Any = None) -> Any:  # noqa: ANN401
        return self.use_case(
            RunAblationCohortCommand(spec=spec or _ablation(), base=base or _base())
        )


class _CountingProbe(InMemoryRuntimeEnvironmentProbe):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def snapshot(self) -> Any:  # noqa: ANN401
        self.calls += 1
        return super().snapshot()


def test_unfrozen_spec_refused_before_lock_and_probe() -> None:
    probe = _CountingProbe()
    harness = _Harness(probe=probe)
    for spec in (_ablation(seeds=()), _ablation(torch_build=None)):
        with pytest.raises(CohortNotFrozenError, match="ablation-freeze"):
            harness.run(spec)
    assert probe.calls == 0
    assert not harness.ledger.is_locked
    assert harness.commands == []


def test_units_are_configurations_outer_seeds_inner() -> None:
    harness = _Harness()
    result = harness.run()
    assert [o.unit_key for o in result.outcomes] == [
        f"tft:{name}:seed={seed}" for name in ABLATION_CONFIGURATIONS for seed in _SEEDS
    ]
    assert [o.status for o in result.outcomes] == ["ran"] * 10
    assert result.cohort_id == _cohort_id(_ablation())


def test_each_unit_trains_with_its_configuration_identity() -> None:
    harness = _Harness()
    harness.run()
    cohort_id = _cohort_id(_ablation())
    expected = [(name, seed) for name in ABLATION_CONFIGURATIONS for seed in _SEEDS]
    for command, (name, seed) in zip(harness.commands, expected, strict=True):
        assert command.excluded_family == excluded_family_of(name)
        assert command.model_version == f"tft_quantile_loco_{name}"
        assert command.scope.feature_set_name == ABLATION_FEATURE_SET_NAME
        assert command.scope.cohort_id == cohort_id
        assert command.params.seed == seed


def test_command_equals_the_confirmatory_command_except_identity() -> None:
    """O procedimento é o da base: só a identidade da configuração difere."""
    harness = _Harness()
    harness.run()
    for command in harness.commands:
        confirmatory = tft_train_command(
            _base(), scope=command.scope, seed=command.params.seed, schema_version=1
        )
        assert command.params == confirmatory.params
        assert (command.horizons, command.quantile_levels) == (
            confirmatory.horizons,
            confirmatory.quantile_levels,
        )
        assert (
            command.n_folds,
            command.test_size,
            command.val_size,
            command.calib_size,
            command.embargo,
            command.schema_version,
        ) == (
            confirmatory.n_folds,
            confirmatory.test_size,
            confirmatory.val_size,
            confirmatory.calib_size,
            confirmatory.embargo,
            confirmatory.schema_version,
        )


def test_no_run_id_collision_across_configurations_and_seeds() -> None:
    harness = _Harness()
    result = harness.run()
    run_ids = [run_id for outcome in result.outcomes for run_id in outcome.run_ids]
    assert len(run_ids) == len(set(run_ids)) == 5 * len(_SEEDS) * _GEOMETRY.n_folds
    keys = {(c.model_version, c.params.seed) for c in harness.commands}
    assert len(keys) == 5 * len(_SEEDS)


def test_geometry_equal_across_configurations_and_base() -> None:
    harness = _Harness()
    harness.run()
    geometry = {
        (c.n_folds, c.test_size, c.val_size, c.calib_size, c.embargo, c.scope.max_horizon)
        for c in harness.commands
    }
    base = _base()
    assert geometry == {
        (
            base.geometry.n_folds,
            base.geometry.test_size,
            base.geometry.val_size,
            base.geometry.calib_size,
            base.geometry.embargo,
            base.max_horizon,
        )
    }


def test_base_declarations_checked_with_the_base_device() -> None:
    rows = _rows()
    rows[5]["close"] = 999.0
    harness = _Harness(store=_store(rows))
    with pytest.raises(DatasetMismatchError):
        harness.run()
    assert harness.commands == []
    assert not harness.ledger.is_locked
    # base `cpu` com ablação `rocm` passa
    assert _Harness().run().outcomes


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        pytest.param({"available": "false"}, "no GPU", id="gpu-unavailable"),
        pytest.param({"hip_version": ""}, "no HIP", id="hip-empty"),
        pytest.param({"torch": "2.13.0+cpu"}, "torch_build", id="torch-differs"),
    ],
)
def test_probe_guard_refuses_before_training(overrides: dict[str, str], match: str) -> None:
    harness = _Harness(probe=_gpu_probe(**overrides))
    with pytest.raises(EnvironmentMismatchError, match=match):
        harness.run()
    assert harness.commands == []
    assert harness.ledger.environment(_cohort_id(_ablation())) is None


def test_probe_guard_accepts_gpu_hip_and_build() -> None:
    harness = _Harness()
    harness.run()
    recorded = harness.ledger.environment(_cohort_id(_ablation()))
    assert recorded is not None
    assert recorded["gpu.available"] == "true"
    assert recorded["torch"] == _TORCH


def test_resume_reconfers_ledger_units() -> None:
    harness = _Harness()
    harness.run()
    trained = len(harness.commands)
    again = harness.run()
    assert [o.status for o in again.outcomes] == ["skipped_completed"] * 10
    assert len(harness.commands) == trained
    cohort_id = _cohort_id(_ablation())
    key = ("tft_quantile_loco_minus_price", 1)
    harness.index._runs[(cohort_id, _ASSET, ABLATION_FEATURE_SET_NAME)][key].pop(
        "tft_quantile_loco_minus_price-s1-f0"
    )
    with pytest.raises(CompletedUnitCorruptedError):
        harness.run()


def test_silver_complete_unit_verified() -> None:
    harness = _Harness()
    first = _ablation()
    template = tft_train_command(_base(), scope=_scope(first), seed=1, schema_version=1)
    harness.persist(replace(template, model_version="tft_quantile_loco_full"))
    result = harness.run()
    assert result.outcomes[0].status == "verified_completed"
    assert result.outcomes[1].status == "ran"
    assert ("tft_quantile_loco_full", 1) not in {
        (c.model_version, c.params.seed) for c in harness.commands
    }


def _scope(spec: AblationCohortSpec) -> Any:  # noqa: ANN401
    return ScopeSpec(
        asset_id=_ASSET,
        feature_set_name=spec.feature_set_name,
        max_horizon=max(_HORIZONS),
        cohort_id=_cohort_id(spec),
    )


def test_partial_unit_raises() -> None:
    harness = _Harness()
    spec = _ablation()
    template = tft_train_command(_base(), scope=_scope(spec), seed=2, schema_version=1)
    harness.persist(replace(template, model_version="tft_quantile_loco_full"), folds=range(1))
    with pytest.raises(PartialCohortUnitError, match="tft:full:seed=2"):
        harness.run()


def test_environment_mismatch_on_resume() -> None:
    harness = _Harness()
    harness.run()
    harness.use_case._probe = _gpu_probe(**{"code.src": "other-tree"})
    with pytest.raises(EnvironmentMismatchError, match=r"code.src"):
        harness.run()


def test_recorded_run_problems_over_model_version_seed_keys() -> None:
    harness = _Harness()
    harness.run()
    spec = _ablation()
    recorded = harness.index.recorded_runs(
        asset_id=_ASSET, feature_set_name=ABLATION_FEATURE_SET_NAME, cohort_id=_cohort_id(spec)
    )
    keys = [key for keys in ablation_model_keys(spec).values() for key in keys]
    assert len(keys) == 5 * len(_SEEDS)
    assert recorded_run_problems(_base(), keys, recorded) == []
    missing = ("tft_quantile_loco_minus_sentiment", 99)
    assert recorded_run_problems(_base(), [missing], recorded) == [
        "tft_quantile_loco_minus_sentiment seed=99: folds [], expected 0..1"
    ]


def test_failing_unit_releases_the_lock_and_is_not_marked() -> None:
    harness = _Harness(fail_unit=("tft_quantile_loco_minus_price", 1))
    with pytest.raises(RuntimeError, match="boom"):
        harness.run()
    assert not harness.ledger.is_locked
    completed = harness.ledger.completed_units(_cohort_id(_ablation()))
    assert "tft:minus_price:seed=1" not in completed
    assert "tft:full:seed=2" in completed
