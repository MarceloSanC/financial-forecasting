"""Unit do `PredictTftFromCheckpoints` (Stage 7.1, Task 05; C1/C2/C6/C13, I12).

O oráculo dos runs é o `TrainTft` com fakes (`_frozen_tft_cohort`); o predictor é
o `InMemoryTftCheckpointPredictor`, com um checkpoint registrado por run. Prova:
decisões pedidas = sessões de `fold.test`/`fold.calib`; `run_id` fora da lista
permitida ergue sem predizer; emissão fora do pedido ergue (I12); guardas antes
de predizer; sha256, normalizador, settings, `batch_size` e threads repassados.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.modeling.application.pipeline_version import PIPELINE_VERSION
from financial_forecasting.features.modeling.application.ports.out.tft_checkpoint_predictor import (
    TftCheckpointPrediction,
)
from financial_forecasting.features.modeling.application.use_cases.predict_tft_from_checkpoints import (  # noqa: E501
    PredictTftFromCheckpoints,
    PredictTftFromCheckpointsCommand,
    PredictTftFromCheckpointsResult,
    UnknownRunError,
)
from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    CohortDeclarationMismatchError,
    CohortNotFrozenError,
    DatasetMismatchError,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    modeling_columns,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    known_feature_names,
    unknown_feature_names,
)
from tests.fakes.features.modeling.in_memory_checkpoint_locator import InMemoryCheckpointLocator
from tests.fakes.features.modeling.in_memory_tft_checkpoint_predictor import (
    FakeCheckpoint,
    InMemoryTftCheckpointPredictor,
)
from tests.unit.features.modeling.application import _frozen_tft_cohort as cohort

pytestmark = pytest.mark.unit

_SEED = cohort.SEEDS[0]
_CENTER = 0.25
_SCALE = 0.5


class _Setup:
    def __init__(
        self, tmp_path: Path, predictor: InMemoryTftCheckpointPredictor | None = None
    ) -> None:
        self.artifacts_root = tmp_path / "artifacts"
        self.spec = cohort.frozen_spec()
        self.runs = cohort.oracle_runs(self.spec, _SEED, self.artifacts_root)
        self.locator = InMemoryCheckpointLocator()
        cohort.write_checkpoints(self.locator, self.runs)
        self.predictor = predictor or InMemoryTftCheckpointPredictor()
        self.allowed = {
            run.run_id: hashlib.sha256(cohort.checkpoint_bytes(run.run_id)).hexdigest()
            for run in self.runs
        }
        for run in self.runs:
            self.predictor.register(
                f"{run.artifact_dir}/best.ckpt",
                FakeCheckpoint(
                    sha256=self.allowed[run.run_id],
                    feature_names=unknown_feature_names() + known_feature_names(),
                    known_feature_names=known_feature_names(),
                    max_horizon=max(cohort.HORIZONS),
                    quantile_levels=cohort.LEVELS,
                    normalizer_center=_CENTER + run.fold_index,
                    normalizer_scale=_SCALE + run.fold_index,
                ),
            )

    def use_case(self, **overrides: object) -> PredictTftFromCheckpoints:
        arguments: dict[str, object] = {
            "store": cohort.store(),
            "hasher": cohort.HASHER,
            "splitter": cohort.splitter(),
            "locator": self.locator,
            "predictor": self.predictor,
            "artifacts_root": self.artifacts_root,
            "modeling_columns": modeling_columns(),
            "observed_feature_set_hash": cohort.FEATURE_SET_HASH,
            "pipeline_version": PIPELINE_VERSION,
            "supported_device": "cpu",
        }
        arguments.update(overrides)
        return PredictTftFromCheckpoints(**arguments)  # type: ignore[arg-type]

    def predict(
        self, *, use_case: dict[str, object] | None = None, **command: object
    ) -> PredictTftFromCheckpointsResult:
        fields: dict[str, object] = {
            "spec": self.spec,
            "seed": _SEED,
            "allowed": self.allowed,
            "partitions": ("test", "calib"),
            "num_threads": 6,
        }
        fields.update(command)
        return self.use_case(**(use_case or {}))(
            PredictTftFromCheckpointsCommand(**fields)  # type: ignore[arg-type]
        )

    def folds(self) -> tuple[Any, ...]:
        return cohort.splitter().split(
            cohort.sessions(),
            self.spec.scope(cohort.cohort_id(self.spec)),
            n_folds=cohort.GEOMETRY.n_folds,
            test_size=cohort.GEOMETRY.test_size,
            val_size=cohort.GEOMETRY.val_size,
            calib_size=cohort.GEOMETRY.calib_size,
            embargo=cohort.GEOMETRY.embargo,
            hasher=cohort.HASHER,
        )


def _indices(days: Sequence[str]) -> tuple[int, ...]:
    by_day = {day.isoformat(): idx for idx, day in enumerate(cohort.sessions())}
    return tuple(by_day[day] for day in days)


def _calls_for(predictor: InMemoryTftCheckpointPredictor, run_dir: str) -> list[dict[str, Any]]:
    return [c for c in predictor.calls if c["checkpoint_path"].startswith(run_dir + "/")]


def test_calib_decisions_are_the_fold_calib_sessions(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)

    result = setup.predict(partitions=("calib",))

    for run, fold in zip(setup.runs, setup.folds(), strict=True):
        [call] = _calls_for(setup.predictor, run.artifact_dir)
        assert call["decision_indices"] == _indices(fold.calib)
    for prediction, fold in zip(result.runs, setup.folds(), strict=True):
        assert set(prediction.grids) == {"calib"}
        assert sorted(prediction.grids["calib"]) == list(_indices(fold.calib))


def test_test_decisions_are_the_fold_test_sessions(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)

    result = setup.predict(partitions=("test",))

    for run, fold in zip(setup.runs, setup.folds(), strict=True):
        [call] = _calls_for(setup.predictor, run.artifact_dir)
        assert call["decision_indices"] == _indices(fold.test)
    assert [r.run_id for r in result.runs] == [run.run_id for run in setup.runs]
    assert [r.fold_index for r in result.runs] == [run.fold_index for run in setup.runs]
    assert result.dataset_timestamps[0].startswith(cohort.sessions()[0].isoformat())
    assert len(result.dataset_timestamps) == cohort.N_SESSIONS


def test_run_outside_allowlist_raises_without_predicting(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)
    allowed = dict(setup.allowed)
    del allowed[setup.runs[-1].run_id]

    with pytest.raises(UnknownRunError, match="C6"):
        setup.predict(allowed=allowed)

    assert setup.predictor.calls == []
    assert setup.locator.calls == []


class _LeakingPredictor(InMemoryTftCheckpointPredictor):
    """Devolve uma decisão ou um horizonte que não foi pedido (prova I12)."""

    def __init__(self, *, extra_decision: bool) -> None:
        super().__init__()
        self._extra_decision = extra_decision

    def predict_from_checkpoint(self, **kwargs: Any) -> TftCheckpointPrediction:  # noqa: ANN401
        result = super().predict_from_checkpoint(**kwargs)
        grids: dict[int, Mapping[int, tuple[float, ...]]] = dict(result.grids)
        first = min(kwargs["decision_indices"])
        if self._extra_decision:
            grids[first - 1] = grids[first]
        else:
            grids[first] = {**grids[first], 99: grids[first][1]}
        return replace(result, grids=grids)


@pytest.mark.parametrize("extra_decision", [True, False], ids=["decision", "horizon"])
def test_emission_outside_request_raises(tmp_path: Path, extra_decision: bool) -> None:
    setup = _Setup(tmp_path, predictor=_LeakingPredictor(extra_decision=extra_decision))
    message = "outside the requested calib range" if extra_decision else "not requested"

    with pytest.raises(ValueError, match=message):
        setup.predict(partitions=("calib",))


@pytest.mark.parametrize(
    "case",
    [
        "not-frozen",
        "fingerprint",
        "feature-set-hash",
        "pipeline-version",
        "device",
        "seed-not-declared",
        "unknown-partition",
        "repeated-partition",
        "no-partition",
        "zero-threads",
    ],
)
def test_guards_raise_before_predicting(tmp_path: Path, case: str) -> None:
    setup = _Setup(tmp_path)
    command: dict[str, object] = {}
    use_case: dict[str, object] = {}
    error: type[Exception] = ValueError
    if case == "not-frozen":
        command["spec"], error = replace(setup.spec, tft_params=None), CohortNotFrozenError
    elif case == "fingerprint":
        command["spec"] = replace(setup.spec, dataset_fingerprint="0" * 64)
        error = DatasetMismatchError
    elif case == "feature-set-hash":
        use_case["observed_feature_set_hash"] = "e" * 64
        error = CohortDeclarationMismatchError
    elif case == "pipeline-version":
        use_case["pipeline_version"], error = "other", CohortDeclarationMismatchError
    elif case == "device":
        use_case["supported_device"], error = "cuda", CohortDeclarationMismatchError
    elif case == "seed-not-declared":
        command["seed"] = 999
    elif case == "unknown-partition":
        command["partitions"] = ("train",)
    elif case == "repeated-partition":
        command["partitions"] = ("calib", "calib")
    elif case == "no-partition":
        command["partitions"] = ()
    elif case == "zero-threads":
        command["num_threads"] = 0

    with pytest.raises(error):
        setup.predict(use_case=use_case, **command)

    assert setup.predictor.calls == []


def test_settings_normalizer_and_sha_are_forwarded(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)

    result = setup.predict()

    for prediction, run in zip(result.runs, setup.runs, strict=True):
        assert prediction.checkpoint_sha256 == setup.allowed[run.run_id]
        assert prediction.normalizer_center == _CENTER + run.fold_index
        assert prediction.normalizer_scale == _SCALE + run.fold_index
        assert set(prediction.grids) == {"test", "calib"}
    for call in setup.predictor.calls:
        assert call["expected_sha256"] in setup.allowed.values()
    assert result.settings["num_threads"] == "6"
    assert result.cohort_id == cohort.cohort_id(setup.spec)
    assert result.seed == _SEED


def test_batch_size_and_threads_reach_the_port(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)

    setup.predict(num_threads=3)

    assert setup.spec.tft_params is not None
    assert {c["batch_size"] for c in setup.predictor.calls} == {setup.spec.tft_params.batch_size}
    assert {c["num_threads"] for c in setup.predictor.calls} == {3}
    assert len(setup.predictor.calls) == 2 * cohort.GEOMETRY.n_folds
