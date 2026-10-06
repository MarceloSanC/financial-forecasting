"""Unit do `ResolveTftCheckpoints` (Stage 7.1, Task 05; C1/C2/C3/C13/C14).

O oráculo é o `TrainTft` de verdade rodado com fakes (`_frozen_tft_cohort`):
`run_id` e diretório do artefato de cada fold têm de ser os que o treino gravou.
As guardas erguem antes de qualquer `locate` (o fake conta as chamadas).
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from financial_forecasting.features.modeling.application.pipeline_version import PIPELINE_VERSION
from financial_forecasting.features.modeling.application.ports.out.checkpoint_locator import (
    AmbiguousCheckpointError,
    CheckpointNotFoundError,
)
from financial_forecasting.features.modeling.application.use_cases.resolve_tft_checkpoints import (
    IncompleteCohortError,
    ResolveTftCheckpoints,
    ResolveTftCheckpointsCommand,
    ResolveTftCheckpointsResult,
)
from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    CohortDeclarationMismatchError,
    CohortNotFrozenError,
    DatasetMismatchError,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    modeling_columns,
)
from tests.fakes.features.modeling.in_memory_checkpoint_locator import InMemoryCheckpointLocator
from tests.fakes.features.modeling.in_memory_cohort_run_index import InMemoryCohortRunIndex
from tests.unit.features.modeling.application import _frozen_tft_cohort as cohort

pytestmark = pytest.mark.unit

_SEED = cohort.SEEDS[0]


class _Setup:
    def __init__(self, tmp_path: Path, *, complete: bool = True) -> None:
        self.artifacts_root = tmp_path / "artifacts"
        self.spec = cohort.frozen_spec()
        self.index = InMemoryCohortRunIndex()
        self.locator = InMemoryCheckpointLocator()
        self.oracle = {
            seed: cohort.oracle_runs(self.spec, seed, self.artifacts_root) for seed in cohort.SEEDS
        }
        for seed, runs in self.oracle.items():
            if complete or seed == _SEED:
                cohort.record_runs(self.index, self.spec, runs, seed)
            cohort.write_checkpoints(self.locator, runs)

    def use_case(self, **overrides: object) -> ResolveTftCheckpoints:
        arguments: dict[str, object] = {
            "store": cohort.store(),
            "hasher": cohort.HASHER,
            "splitter": cohort.splitter(),
            "run_index": self.index,
            "locator": self.locator,
            "artifacts_root": self.artifacts_root,
            "modeling_columns": modeling_columns(),
            "observed_feature_set_hash": cohort.FEATURE_SET_HASH,
            "pipeline_version": PIPELINE_VERSION,
            "supported_device": "cpu",
        }
        arguments.update(overrides)
        return ResolveTftCheckpoints(**arguments)  # type: ignore[arg-type]

    def resolve(
        self, spec: object = None, seed: int = _SEED, **overrides: object
    ) -> ResolveTftCheckpointsResult:
        return self.use_case(**overrides)(
            ResolveTftCheckpointsCommand(spec=spec or self.spec, seed=seed)  # type: ignore[arg-type]
        )


def test_run_ids_equal_what_train_tft_records(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)

    result = setup.resolve()

    assert result.cohort_id == cohort.cohort_id(setup.spec)
    assert result.seed == _SEED
    assert [(r.fold_index, r.run_id) for r in result.runs] == [
        (run.fold_index, run.run_id) for run in setup.oracle[_SEED]
    ]


def test_artifact_dir_follows_the_train_tft_rule(tmp_path: Path) -> None:
    setup = _Setup(tmp_path)

    result = setup.resolve(seed=cohort.SEEDS[1])

    oracle = setup.oracle[cohort.SEEDS[1]]
    assert [str(Path(r.checkpoint_path).parent) for r in result.runs] == [
        str(Path(run.artifact_dir)) for run in oracle
    ]
    assert setup.locator.calls == [run.artifact_dir for run in oracle]
    for resolution, run in zip(result.runs, oracle, strict=True):
        expected = hashlib.sha256(cohort.checkpoint_bytes(run.run_id)).hexdigest()
        assert resolution.checkpoint_sha256 == expected
        assert Path(resolution.checkpoint_path).name == "best.ckpt"


def test_model_version_is_in_each_resolution(tmp_path: Path) -> None:
    result = _Setup(tmp_path).resolve()

    assert {r.model_version for r in result.runs} == {"tft_quantile"}


def _unfrozen(setup: _Setup) -> object:
    return replace(setup.spec, tft_params=None)


@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("not-frozen", CohortNotFrozenError),
        ("fingerprint", DatasetMismatchError),
        ("feature-set-hash", CohortDeclarationMismatchError),
        ("pipeline-version", CohortDeclarationMismatchError),
        ("device", CohortDeclarationMismatchError),
        ("seed-not-declared", ValueError),
        ("incomplete", IncompleteCohortError),
    ],
)
def test_guards_raise_before_locate(tmp_path: Path, case: str, error: type[Exception]) -> None:
    setup = _Setup(tmp_path, complete=case != "incomplete")
    spec: object = setup.spec
    seed = _SEED
    overrides: dict[str, object] = {}
    if case == "not-frozen":
        spec = _unfrozen(setup)
    elif case == "fingerprint":
        spec = replace(setup.spec, dataset_fingerprint="0" * 64)
    elif case == "feature-set-hash":
        overrides["observed_feature_set_hash"] = "e" * 64
    elif case == "pipeline-version":
        overrides["pipeline_version"] = "other"
    elif case == "device":
        overrides["supported_device"] = "cuda"
    elif case == "seed-not-declared":
        seed = 999

    with pytest.raises(error):
        setup.resolve(spec, seed, **overrides)

    assert setup.locator.calls == []


@pytest.mark.parametrize(
    ("files", "error"),
    [((), CheckpointNotFoundError), (("a.ckpt", "b.ckpt"), AmbiguousCheckpointError)],
    ids=["none", "two"],
)
def test_locator_errors_propagate(
    tmp_path: Path, files: tuple[str, ...], error: type[Exception]
) -> None:
    setup = _Setup(tmp_path)
    locator = InMemoryCheckpointLocator()
    first = setup.oracle[_SEED][0]
    for name in files:
        locator.add_file(first.artifact_dir, name, b"x")

    with pytest.raises(error, match="C3"):
        setup.resolve(locator=locator)
