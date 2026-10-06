"""Contrato dos ports `CheckpointResolver` e `CheckpointGridPredictor` do `inference` (7.1).

Duas pernas por port, tipadas pelo Protocol DO INFERENCE (o mypy prova a
conformidade estrutural): `fake` (`InMemoryCheckpointResolver` /
`InMemoryCheckpointGridPredictor`) e `real` — os use cases do `modeling`
`ResolveTftCheckpoints` e `PredictTftFromCheckpoints` (Task 05) montados sobre o
cohort sintético `_frozen_tft_cohort` com os fakes do modeling (locator,
predictor do checkpoint, índice). O fake é configurado com o que o real devolve
sobre o mesmo cohort (gravação), e as duas pernas passam pelas mesmas asserções:

- o resolver devolve um item por fold, em ordem, com a identidade do treino;
- cohort incompleto ergue `ApplicationError` (C14);
- o predictor recusa run fora da lista permitida (C6);
- devolve só as partições pedidas, com grade alinhada aos níveis do spec.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pytest

from financial_forecasting.features.inference.application.ports.out.checkpoint_grid_predictor import (  # noqa: E501
    CheckpointGridPredictor,
)
from financial_forecasting.features.inference.application.ports.out.checkpoint_resolver import (
    CheckpointResolver,
)
from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec
from financial_forecasting.features.modeling.application.pipeline_version import PIPELINE_VERSION
from financial_forecasting.features.modeling.application.use_cases.predict_tft_from_checkpoints import (  # noqa: E501
    PredictTftFromCheckpoints,
    PredictTftFromCheckpointsCommand,
)
from financial_forecasting.features.modeling.application.use_cases.resolve_tft_checkpoints import (
    ResolveTftCheckpoints,
    ResolveTftCheckpointsCommand,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    modeling_columns,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    known_feature_names,
    unknown_feature_names,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from tests.fakes.features.inference.in_memory_checkpoint_grid_predictor import (
    InMemoryCheckpointGridPredictor,
)
from tests.fakes.features.inference.in_memory_checkpoint_resolver import (
    InMemoryCheckpointResolver,
)
from tests.fakes.features.modeling.in_memory_checkpoint_locator import InMemoryCheckpointLocator
from tests.fakes.features.modeling.in_memory_cohort_run_index import InMemoryCohortRunIndex
from tests.fakes.features.modeling.in_memory_tft_checkpoint_predictor import (
    FakeCheckpoint,
    InMemoryTftCheckpointPredictor,
)
from tests.unit.features.modeling.application import _frozen_tft_cohort as cohort

pytestmark = pytest.mark.contract

_SEED = cohort.SEEDS[0]


@dataclass(frozen=True)
class _Leg:
    resolver: CheckpointResolver
    predictor: CheckpointGridPredictor
    spec: CohortSpec
    allowed: dict[str, str]
    oracle: tuple[cohort.OracleRun, ...]


def _real(
    tmp_path: Path, *, complete: bool
) -> tuple[
    ResolveTftCheckpoints,
    PredictTftFromCheckpoints,
    CohortSpec,
    dict[str, str],
    tuple[cohort.OracleRun, ...],
]:
    root = tmp_path / "artifacts"
    spec = cohort.frozen_spec()
    oracle = {seed: cohort.oracle_runs(spec, seed, root) for seed in cohort.SEEDS}
    index = InMemoryCohortRunIndex()
    locator = InMemoryCheckpointLocator()
    model_predictor = InMemoryTftCheckpointPredictor()
    allowed: dict[str, str] = {}
    for seed, runs in oracle.items():
        if complete or seed == _SEED:
            cohort.record_runs(index, spec, runs, seed)
        cohort.write_checkpoints(locator, runs)
        for run in runs:
            sha = hashlib.sha256(cohort.checkpoint_bytes(run.run_id)).hexdigest()
            allowed[run.run_id] = sha
            model_predictor.register(
                f"{run.artifact_dir}/best.ckpt",
                FakeCheckpoint(
                    sha256=sha,
                    feature_names=unknown_feature_names() + known_feature_names(),
                    known_feature_names=known_feature_names(),
                    max_horizon=max(cohort.HORIZONS),
                    quantile_levels=cohort.LEVELS,
                ),
            )
    common: dict[str, object] = {
        "store": cohort.store(),
        "hasher": cohort.HASHER,
        "splitter": cohort.splitter(),
        "locator": locator,
        "artifacts_root": root,
        "modeling_columns": modeling_columns(),
        "observed_feature_set_hash": cohort.FEATURE_SET_HASH,
        "pipeline_version": PIPELINE_VERSION,
        "supported_device": "cpu",
    }
    resolver = ResolveTftCheckpoints(run_index=index, **common)  # type: ignore[arg-type]
    predictor = PredictTftFromCheckpoints(predictor=model_predictor, **common)  # type: ignore[arg-type]
    return resolver, predictor, spec, allowed, oracle[_SEED]


def _command(
    spec: CohortSpec, allowed: dict[str, str], partitions: tuple[str, ...]
) -> PredictTftFromCheckpointsCommand:
    return PredictTftFromCheckpointsCommand(
        spec=spec, seed=_SEED, allowed=allowed, partitions=partitions, num_threads=1
    )


def _leg(kind: str, tmp_path: Path, *, complete: bool = True) -> _Leg:
    resolver, predictor, spec, allowed, oracle = _real(tmp_path, complete=complete)
    if kind == "real":
        return _Leg(resolver, predictor, spec, allowed, oracle)
    # A gravação usa sempre o cohort completo; o fake de um cohort incompleto
    # devolve a mesma classe de erro do real (`ApplicationError`, C14).
    full_resolver, full_predictor, *_ = _real(tmp_path / "recording", complete=True)
    fake_resolver = (
        InMemoryCheckpointResolver(
            {s: full_resolver(ResolveTftCheckpointsCommand(spec=spec, seed=s)) for s in spec.seeds}
        )
        if complete
        else InMemoryCheckpointResolver(error=ApplicationError("cohort incomplete (C14)"))
    )
    fake_predictor = InMemoryCheckpointGridPredictor(
        {_SEED: full_predictor(_command(spec, allowed, ("test", "calib")))}
    )
    return _Leg(fake_resolver, fake_predictor, spec, allowed, oracle)


@pytest.fixture(params=["fake", "real"])
def kind(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def test_resolver_returns_one_resolution_per_fold_in_order(kind: str, tmp_path: Path) -> None:
    leg = _leg(kind, tmp_path)

    result = leg.resolver(ResolveTftCheckpointsCommand(spec=leg.spec, seed=_SEED))

    assert result.seed == _SEED
    assert result.cohort_id == cohort.cohort_id(leg.spec)
    assert [r.fold_index for r in result.runs] == list(range(cohort.GEOMETRY.n_folds))
    assert [r.run_id for r in result.runs] == [run.run_id for run in leg.oracle]
    assert {r.model_version for r in result.runs} == {"tft_quantile"}
    assert all(r.checkpoint_sha256 == leg.allowed[r.run_id] for r in result.runs)


def test_resolver_incomplete_cohort_raises_application_error(kind: str, tmp_path: Path) -> None:
    leg = _leg(kind, tmp_path, complete=False)

    with pytest.raises(ApplicationError):
        leg.resolver(ResolveTftCheckpointsCommand(spec=leg.spec, seed=_SEED))


def test_grid_predictor_rejects_run_outside_allowlist(kind: str, tmp_path: Path) -> None:
    leg = _leg(kind, tmp_path)
    allowed = dict(leg.allowed)
    del allowed[leg.oracle[0].run_id]

    with pytest.raises(ApplicationError):
        leg.predictor(_command(leg.spec, allowed, ("calib",)))


def test_grid_predictor_returns_only_the_requested_partitions(kind: str, tmp_path: Path) -> None:
    leg = _leg(kind, tmp_path)

    calib_only = leg.predictor(_command(leg.spec, leg.allowed, ("calib",)))
    both = leg.predictor(_command(leg.spec, leg.allowed, ("test", "calib")))

    assert [r.run_id for r in calib_only.runs] == [run.run_id for run in leg.oracle]
    assert all(set(r.grids) == {"calib"} for r in calib_only.runs)
    assert all(set(r.grids) == {"test", "calib"} for r in both.runs)
    assert len(calib_only.dataset_timestamps) == cohort.N_SESSIONS


def test_grid_predictor_grid_aligned_to_quantile_levels(kind: str, tmp_path: Path) -> None:
    leg = _leg(kind, tmp_path)

    result = leg.predictor(_command(leg.spec, leg.allowed, ("test", "calib")))

    grids = [
        grid
        for run in result.runs
        for by_decision in run.grids.values()
        for by_horizon in by_decision.values()
        for grid in by_horizon.values()
    ]
    assert grids
    assert all(len(grid) == len(leg.spec.quantile_levels) for grid in grids)
    for run in result.runs:
        assert all(set(by_h) <= set(leg.spec.horizons) for by_h in run.grids["calib"].values())
