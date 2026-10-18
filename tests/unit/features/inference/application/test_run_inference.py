"""Unit do `RunInference` (Stage 7.1, Task 09) — concept §5 I4 a I13, §6 C1, C6 a C15.

Dublês que fecham o ciclo escrita → releitura: o persister é o
`PersistPredictions` de verdade sobre um `FakeAnalyticsRepository`, e o leitor do
silver é o MESMO repositório. `dim_run` e o teste de referência são semeados no
repositório (o teste pelo próprio `PersistPredictions`, como o treino o grava).
Resolver e predictor são os fakes do `inference` configurados com um cohort
sintético de uma seed e dois folds; probe, ledger, manifesto e relógio são fakes;
o hasher é o real. Nada aqui calcula métrica: a reprodução compara predição com
predição (I13).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pytest

from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictions,
    PersistPredictionsCommand,
    PersistPredictionsResult,
)
from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.inference.application.use_cases.run_inference import (
    COMPLETED,
    STARTED,
    STRICT,
    TOLERANCE,
    ArtifactChangedError,
    CalibProvenanceMissingError,
    CohortNotFrozenError,
    IncompleteCalibError,
    InferenceEnvironmentError,
    ReproductionError,
    RunInference,
    RunInferenceCommand,
    RunInferenceResult,
    UnknownRunError,
    within_mode,
)
from financial_forecasting.features.modeling.application.ports.out.cohort_progress_ledger import (
    CohortRunLockedError,
)
from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    DIRTY_KEY,
    REQUIRED_KEYS,
    THREADS_KEY,
)
from financial_forecasting.features.modeling.application.use_cases.predict_tft_from_checkpoints import (  # noqa: E501
    CheckpointRunPrediction,
    PredictTftFromCheckpointsResult,
)
from financial_forecasting.features.modeling.application.use_cases.resolve_tft_checkpoints import (
    CheckpointResolution,
    ResolveTftCheckpointsResult,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
    FakeAnalyticsRepository,
)
from tests.fakes.features.inference.in_memory_checkpoint_grid_predictor import (
    InMemoryCheckpointGridPredictor,
)
from tests.fakes.features.inference.in_memory_checkpoint_resolver import (
    InMemoryCheckpointResolver,
)
from tests.fakes.features.inference.in_memory_cohort_ledger import InMemoryCohortLedger
from tests.fakes.features.inference.in_memory_inference_manifest import (
    InMemoryInferenceManifest,
)
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)
from tests.fakes.shared.in_memory_clock import FakeClock
from tests.unit.features.modeling.application import _frozen_tft_cohort as cohort

pytestmark = pytest.mark.unit

# Índices de decisão do cohort sintético (`_FOLDS`) usados como seletores nos testes.
_F0_CALIB_FIRST, _F0_CALIB_SECOND, _F1_TEST_FIRST = 50, 51, 66

_SEED = cohort.SEEDS[0]
_SPEC = cohort.frozen_spec(seeds=(_SEED,))
_COHORT_ID = cohort.cohort_id(_SPEC)
_LEVELS = _SPEC.quantile_levels
_HORIZONS = _SPEC.horizons
_N = 80
_TIMESTAMPS = tuple(
    (datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i)).isoformat() for i in range(_N)
)
_CENTER = 0.001
_SCALE = 0.02
_JUSTIFICATION = "CPU capability differs, see [finding] 2026-10-06 in technical §7"
_EXPECTED_CALIB = _SPEC.geometry.calib_size * len(_HORIZONS) * len(_LEVELS)


@dataclass(frozen=True)
class _Fold:
    run_id: str
    fold_index: int
    calib: tuple[int, ...]
    test: tuple[int, ...]


# `run_id` é sha256 hex (o `PredictionRow` recusa rótulo, #160); o último caractere
# continua distinguindo os folds em `_grid`.
_RUN_F0 = "f0" * 32
_RUN_F1 = "f1" * 32

_FOLDS = (
    _Fold(_RUN_F0, 0, tuple(range(50, 55)), tuple(range(56, 59))),
    _Fold(_RUN_F1, 1, tuple(range(60, 65)), tuple(range(66, 69))),
)


def _grid(run_id: str, decision: int, horizon: int) -> tuple[float, ...]:
    """Grade crua monótona, exatamente representável em float32."""
    shift = 0.01 if run_id.endswith("1") else 0.0
    base = 0.0005 * (decision % 7) + 0.0001 * horizon + shift
    return tuple(
        float(np.float32(base + 0.01 * (position - 1))) for position in range(len(_LEVELS))
    )


def _grids(fold: _Fold, partition: str) -> dict[int, dict[int, tuple[float, ...]]]:
    decisions = fold.test if partition == "test" else fold.calib
    return {d: {h: _grid(fold.run_id, d, h) for h in _HORIZONS} for d in decisions}


def _environment(**overrides: str) -> dict[str, str]:
    base = {key: f"env-{key}" for key in REQUIRED_KEYS}
    base[DIRTY_KEY] = "false"
    base[THREADS_KEY] = "6"
    base.update(overrides)
    return base


class _EventPersister:
    """`PersistPredictions` real que registra cada escrita (e pode falhar na N-ésima)."""

    def __init__(self, repository: FakeAnalyticsRepository, events: list[str]) -> None:
        self._inner = PersistPredictions(repository=repository)
        self._events = events
        self.fail_after: int | None = None
        self.calls = 0

    def __call__(self, command: PersistPredictionsCommand) -> PersistPredictionsResult:
        if self.fail_after is not None and self.calls >= self.fail_after:
            raise RuntimeError("simulated crash between decisions")
        self.calls += 1
        self._events.append(f"persist:{command.run_id}:{command.decision_idx}")
        return self._inner(command)


class _EventManifest(InMemoryInferenceManifest):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self._events = events

    def record_run(self, cohort_id: str, run_id: str, entry: Mapping[str, object]) -> None:
        self._events.append(f"manifest:{run_id}:{entry.get('status')}")
        super().record_run(cohort_id, run_id, entry)


@dataclass
class _World:
    repository: FakeAnalyticsRepository = field(
        default_factory=lambda: FakeAnalyticsRepository(clock=FakeClock())
    )
    events: list[str] = field(default_factory=list)
    cohort_environment: dict[str, str] = field(default_factory=_environment)
    current_environment: dict[str, str] = field(default_factory=_environment)
    record_cohort_environment: bool = True
    grids: dict[str, dict[str, dict[int, dict[int, tuple[float, ...]]]]] = field(
        default_factory=lambda: {
            fold.run_id: {"test": _grids(fold, "test"), "calib": _grids(fold, "calib")}
            for fold in _FOLDS
        }
    )
    resolver_error: Exception | None = None
    silver_patch: Callable[[Mapping[str, object]], Mapping[str, object]] | None = None
    now: datetime = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    tamper_prediction: (
        Callable[[PredictTftFromCheckpointsResult], PredictTftFromCheckpointsResult] | None
    ) = None
    resolved_cohort_id: str = _COHORT_ID
    resolved_seed: int = _SEED

    def __post_init__(self) -> None:
        self.persister = _EventPersister(self.repository, self.events)
        self.manifest = _EventManifest(self.events)
        self.ledger = InMemoryCohortLedger()
        self._seed_silver()

    def _seed_silver(self) -> None:
        self.repository.write(
            layer="silver",
            table="dim_run",
            rows=[
                {
                    "schema_version": 1,
                    "run_id": fold.run_id,
                    "asset": cohort.ASSET,
                    "parent_sweep_id": _COHORT_ID,
                    "feature_set_name": cohort.FEATURE_SET,
                    "config_signature": "sig",
                    "split_fingerprint": "split",
                    "fold": str(fold.fold_index),
                    "seed": _SEED,
                    "model_version": "tft_quantile",
                }
                for fold in _FOLDS
            ],
        )
        writer = PersistPredictions(repository=self.repository)
        for fold in _FOLDS:
            for decision in fold.test:
                writer(self.command(fold.run_id, decision, "test", _grids(fold, "test")[decision]))

    @staticmethod
    def command(
        run_id: str, decision: int, split: str, by_horizon: Mapping[int, tuple[float, ...]]
    ) -> PersistPredictionsCommand:
        return PersistPredictionsCommand(
            run_id=run_id,
            split=split,
            model_version="tft_quantile",
            asset=cohort.ASSET,
            feature_set_name=cohort.FEATURE_SET,
            schema_version=1,
            decision_idx=decision,
            dataset_timestamps=_TIMESTAMPS,
            forecasts={
                h: QuantileForecast.from_raw(levels=_LEVELS, raw_values=grid)
                for h, grid in by_horizon.items()
            },
        )

    def sha(self, run_id: str) -> str:
        return run_id[::-1]

    def resolver(self) -> InMemoryCheckpointResolver:
        if self.resolver_error is not None:
            return InMemoryCheckpointResolver(error=self.resolver_error)
        return InMemoryCheckpointResolver(
            {
                _SEED: ResolveTftCheckpointsResult(
                    cohort_id=self.resolved_cohort_id,
                    seed=self.resolved_seed,
                    runs=tuple(
                        CheckpointResolution(
                            fold_index=fold.fold_index,
                            run_id=fold.run_id,
                            model_version="tft_quantile",
                            checkpoint_path=f"/artifacts/tft/{fold.run_id}/best.ckpt",
                            checkpoint_sha256=self.sha(fold.run_id),
                        )
                        for fold in _FOLDS
                    ),
                )
            }
        )

    def predictor(self) -> InMemoryCheckpointGridPredictor:
        return InMemoryCheckpointGridPredictor(
            {
                _SEED: PredictTftFromCheckpointsResult(
                    cohort_id=_COHORT_ID,
                    seed=_SEED,
                    dataset_timestamps=_TIMESTAMPS,
                    settings={"batch_size": "16", "num_threads": "6", "cpu_capability": "AVX2"},
                    runs=tuple(
                        CheckpointRunPrediction(
                            run_id=fold.run_id,
                            fold_index=fold.fold_index,
                            checkpoint_sha256=self.sha(fold.run_id),
                            normalizer_center=_CENTER,
                            normalizer_scale=_SCALE,
                            grids=self.grids[fold.run_id],
                        )
                        for fold in _FOLDS
                    ),
                )
            }
        )

    def build(self) -> tuple[RunInference, InMemoryCheckpointGridPredictor]:
        if self.record_cohort_environment and self.ledger.environment(_COHORT_ID) is None:
            self.ledger.record_environment(
                _COHORT_ID, self.cohort_environment, started_at="2026-10-01T00:00:00+00:00"
            )
        predictor = self.predictor()
        self.last_resolver = self.resolver()
        use_case = RunInference(
            resolver=self.last_resolver,
            predictor=_TamperingPredictor(predictor, self.tamper_prediction)
            if self.tamper_prediction is not None
            else predictor,
            probe=InMemoryRuntimeEnvironmentProbe(**self.current_environment),
            persister=self.persister,
            silver=_PatchedReader(self.repository, self.silver_patch)
            if self.silver_patch is not None
            else self.repository,
            ledger=self.ledger,
            manifest=self.manifest,
            hasher=cohort.HASHER,
            clock=FakeClock(self.now),
        )
        return use_case, predictor

    def run(self, **command: Any) -> RunInferenceResult:  # noqa: ANN401
        use_case, self.last_predictor = self.build()
        return use_case(RunInferenceCommand(spec=command.pop("spec", _SPEC), **command))

    def facts(self, split: str, run_id: str | None = None) -> list[Mapping[str, object]]:
        return [
            row
            for row in self.repository.read(
                layer="silver", table="fact_oos_predictions", filters={"asset": cohort.ASSET}
            )
            if row["split"] == split and (run_id is None or row["run_id"] == run_id)
        ]

    def entry(self, run_id: str) -> Mapping[str, Any]:
        document = self.manifest.recorded(_COHORT_ID)
        assert document is not None
        return document["runs"][run_id]  # type: ignore[index,no-any-return]


class _TamperingPredictor:
    """Predictor que devolve um resultado adulterado (o fake do inference não o faria)."""

    def __init__(
        self,
        inner: InMemoryCheckpointGridPredictor,
        tamper: Callable[[PredictTftFromCheckpointsResult], PredictTftFromCheckpointsResult],
    ) -> None:
        self._inner = inner
        self._tamper = tamper
        self.calls = inner.calls

    def __call__(self, command: Any) -> PredictTftFromCheckpointsResult:  # noqa: ANN401
        return self._tamper(self._inner(command))


class _PatchedReader:
    """Leitor do silver que devolve as linhas passadas por `patch` (simula linha divergente)."""

    def __init__(
        self,
        inner: FakeAnalyticsRepository,
        patch: Callable[[Mapping[str, object]], Mapping[str, object]],
    ) -> None:
        self._inner = inner
        self._patch = patch

    def read(
        self, *, layer: str, table: str, filters: Mapping[str, object] | None = None
    ) -> list[Mapping[str, object]]:
        rows = self._inner.read(layer=layer, table=table, filters=filters)
        return [self._patch(row) for row in rows]


def _write_calib_directly(world: _World, run_id: str, decision: int) -> None:
    """Grava DIRETO no silver uma decisão de calib (sem passar pelo `RunInference`)."""
    fold = next(f for f in _FOLDS if f.run_id == run_id)
    command = world.command(run_id, decision, "calib", _grids(fold, "calib")[decision])
    PersistPredictions(repository=world.repository)(command)


def _one_ulp_up(value: object) -> float:
    """O float32 seguinte (1 ulp acima) do valor gravado."""
    return float(np.nextafter(np.float32(float(str(value))), np.float32(1)))


def _complete_first_run(world: _World) -> None:
    world.run()
    world.events.clear()


# -- modo (I6) -------------------------------------------------------------------------


def test_strict_when_non_code_keys_equal() -> None:
    world = _World()

    result = world.run()

    assert {o.reproduction_mode for o in result.outcomes} == {STRICT}
    assert [o.max_abs_diff for o in result.outcomes] == [0.0, 0.0]
    assert world.entry(_RUN_F0)["mode_reason"] == "non-code keys equal"


def test_tolerance_when_a_library_key_differs() -> None:
    world = _World(current_environment=_environment(torch="2.14.0+cpu"))

    result = world.run()

    assert {o.reproduction_mode for o in result.outcomes} == {TOLERANCE}
    entry = world.entry(_RUN_F0)
    assert entry["forced"] is False
    assert entry["mode_reason"] == "non-code keys differ: ['torch']"


def test_cross_environment_with_equal_keys_forces_tolerance_and_records_forced() -> None:
    world = _World()

    result = world.run(cross_environment_justification=_JUSTIFICATION)

    assert {o.reproduction_mode for o in result.outcomes} == {TOLERANCE}
    entry = world.entry(_RUN_F1)
    assert entry["forced"] is True
    assert entry["justification"] == _JUSTIFICATION
    assert entry["mode_reason"] == "forced: cross-environment"


def test_code_key_difference_does_not_change_the_mode() -> None:
    world = _World(current_environment=_environment(**{"code.src": "other-tree"}))

    result = world.run()

    assert {o.reproduction_mode for o in result.outcomes} == {STRICT}


class _SpyLedger(InMemoryCohortLedger):
    def __init__(self) -> None:
        super().__init__()
        self.acquired = 0

    def acquire_writer(self, *, break_stale: bool = False) -> None:
        self.acquired += 1
        super().acquire_writer(break_stale=break_stale)


@pytest.mark.parametrize("justification", ["", "   ", "CPU differs, no finding cited"])
def test_invalid_justification_raises_before_lock_and_probe(justification: str) -> None:
    world = _World()
    world.ledger = _SpyLedger()

    with pytest.raises(ValueError, match="C13"):
        world.run(cross_environment_justification=justification)

    assert world.ledger.acquired == 0
    assert world.last_resolver.calls == []


def test_unfrozen_spec_raises_before_lock_and_probe() -> None:
    world = _World()
    world.ledger = _SpyLedger()

    with pytest.raises(CohortNotFrozenError, match="C1"):
        world.run(spec=replace(_SPEC, tft_params=None))

    assert world.ledger.acquired == 0


# -- retomada (C11) ----------------------------------------------------------------------


def _started_entry_after_crash(world: _World) -> None:
    world.persister.fail_after = 2
    with pytest.raises(RuntimeError, match="simulated crash"):
        world.run()
    world.persister.fail_after = None
    assert world.entry(_RUN_F0)["status"] == STARTED


def test_started_entry_resumed_in_other_environment_raises_without_writing() -> None:
    world = _World()
    _started_entry_after_crash(world)
    before = len(world.facts("calib"))
    world.current_environment = _environment(numpy="9.9.9")

    with pytest.raises(InferenceEnvironmentError, match="C11"):
        world.run()

    assert len(world.facts("calib")) == before


def test_started_entry_resumed_in_same_environment_completes() -> None:
    world = _World()
    _started_entry_after_crash(world)

    world.run()

    assert world.entry(_RUN_F0)["status"] == COMPLETED
    assert len(world.facts("calib", _RUN_F0)) == _EXPECTED_CALIB


# -- conferência do calib presente (C8) ----------------------------------------------------


_TIE_DECISION = 50


def _near_tie_present(world: _World) -> None:
    """1ª escrita com quase-empate CRUZADO em q0.1/q0.5 (guardrail aplicado); a grade
    re-predita da 2ª execução é a mesma a menos de ~1e-7, agora SEM cruzar — o
    `guardrail_applied` muda e o `value_guardrail` difere dentro da tolerância."""
    crossed = (0.0100001, 0.0100000, 0.03)
    uncrossed = (0.0099999, 0.0100000, 0.03)
    world.grids[_RUN_F0]["calib"][_TIE_DECISION] = {h: crossed for h in _HORIZONS}
    _complete_first_run(world)
    applied = {
        r["guardrail_applied"]
        for r in world.facts("calib", _RUN_F0)
        if r["decision_idx"] == _TIE_DECISION
    }
    assert applied == {1}
    world.grids[_RUN_F0]["calib"][_TIE_DECISION] = {h: uncrossed for h in _HORIZONS}


def test_tolerance_accepts_flipped_guardrail_applied_within_tolerance() -> None:
    world = _World()
    _near_tie_present(world)
    world.current_environment = _environment(torch="2.14.0+cpu")

    result = world.run()

    assert result.outcomes[0].calib_rows_written == 0
    assert result.outcomes[0].calib_rows_verified == _EXPECTED_CALIB
    assert world.entry(_RUN_F0)["calib_reproduction_mode"] == TOLERANCE


def test_strict_rejects_flipped_guardrail_applied() -> None:
    world = _World()
    _near_tie_present(world)

    with pytest.raises(ReproductionError, match="guardrail_applied"):
        world.run()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("model_version", "tft_other"),
        ("asset", "MSFT"),
        ("feature_set_name", "fs_other"),
        ("schema_version", 2),
        ("timestamp_utc", "2030-01-01T00:00:00+00:00"),
        ("target_timestamp_utc", "2030-01-02T00:00:00+00:00"),
    ],
)
def test_present_row_with_divergent_non_value_field_raises(field_name: str, value: object) -> None:
    world = _World()
    _complete_first_run(world)

    def patch(row: Mapping[str, object]) -> Mapping[str, object]:
        selected = (
            row.get("run_id") == _RUN_F0
            and row.get("split") == "calib"
            and row.get("decision_idx") == 52  # noqa: PLR2004
        )
        return {**row, field_name: value} if selected else row

    world.silver_patch = patch

    with pytest.raises(ReproductionError, match=field_name):
        world.run()
    assert world.events == []
    assert world.entry(_RUN_F0)["status"] == COMPLETED


def test_present_row_with_divergent_value_guardrail_raises() -> None:
    """1 ulp SÓ no `value_guardrail` (cru e `guardrail_applied` iguais), em strict."""
    world = _World()
    _complete_first_run(world)

    def patch(row: Mapping[str, object]) -> Mapping[str, object]:
        selected = (
            row.get("run_id") == _RUN_F0
            and row.get("split") == "calib"
            and row.get("decision_idx") == _F0_CALIB_SECOND
            and row.get("horizon") == 1
            and row.get("quantile_level") == _LEVELS[1]
        )
        return {**row, "value_guardrail": _one_ulp_up(row["value_guardrail"])} if selected else row

    world.silver_patch = patch

    with pytest.raises(ReproductionError, match=r"differs in \['value_guardrail'\] \(strict\)"):
        world.run()
    assert world.events == []


def test_partially_present_decision_raises() -> None:
    world = _World()
    world.manifest.record_run(
        _COHORT_ID,
        _RUN_F0,
        {
            "checkpoint_sha256": world.sha(_RUN_F0),
            "first_write_environment": world.current_environment,
            "status": COMPLETED,
        },
    )
    fold = _FOLDS[0]
    only_h1 = {1: _grids(fold, "calib")[53][1]}
    PersistPredictions(repository=world.repository)(
        world.command(fold.run_id, 53, "calib", only_h1)
    )
    world.events.clear()

    with pytest.raises(ReproductionError, match="partial write"):
        world.run()
    assert not any(e.startswith("persist:") for e in world.events)


def test_present_calib_verified_under_first_write_environment_mode() -> None:
    # 1ª escrita num ambiente com outra versão de numpy (tolerance contra o cohort).
    world = _World(current_environment=_environment(numpy="9.9.9"))
    _complete_first_run(world)
    assert world.entry(_RUN_F0)["first_write_environment"]["numpy"] == "9.9.9"
    # Calib presente com 1 ulp de diferença numa linha: aceitável só em tolerance.
    rows = [r for r in world.facts("calib", _RUN_F0) if r["decision_idx"] == _F0_CALIB_SECOND]
    world.repository.write(
        layer="silver",
        table="fact_oos_predictions",
        rows=[{**r, "value_raw": _one_ulp_up(r["value_raw"])} for r in rows],
        allow_upsert=True,
    )

    # Agora no ambiente do cohort: teste em strict, mas o calib presente nasceu no
    # ambiente da 1ª escrita (numpy diferente) e é conferido em tolerance.
    world.current_environment = _environment()
    result = world.run()
    assert {o.reproduction_mode for o in result.outcomes} == {STRICT}
    assert result.outcomes[0].calib_rows_verified == _EXPECTED_CALIB

    # O inverso: 1ª escrita no ambiente do cohort (strict) → a mesma diferença reprova.
    strict_world = _World()
    _complete_first_run(strict_world)
    rows = [
        r for r in strict_world.facts("calib", _RUN_F0) if r["decision_idx"] == _F0_CALIB_SECOND
    ]
    strict_world.repository.write(
        layer="silver",
        table="fact_oos_predictions",
        rows=[{**r, "value_raw": _one_ulp_up(r["value_raw"])} for r in rows],
        allow_upsert=True,
    )
    with pytest.raises(ReproductionError, match="value_raw"):
        strict_world.run()


# -- critério de reprodução (C7) -------------------------------------------------------------


def _perturb_test_reference(world: _World, change: Callable[[float], float]) -> None:
    rows = [
        r
        for r in world.facts("test", _RUN_F1)
        if r["decision_idx"] == _F1_TEST_FIRST and r["horizon"] == 1
    ]
    world.repository.write(
        layer="silver",
        table="fact_oos_predictions",
        rows=[{**rows[0], "value_raw": change(float(rows[0]["value_raw"]))}],  # type: ignore[arg-type]
        allow_upsert=True,
    )


def _one_ulp(value: float) -> float:
    return float(np.nextafter(np.float32(value), np.float32(math.inf)))


def test_one_float32_ulp_fails_strict_and_passes_tolerance() -> None:
    strict_world = _World()
    _perturb_test_reference(strict_world, _one_ulp)
    with pytest.raises(ReproductionError, match="strict"):
        strict_world.run()

    tolerant = _World(current_environment=_environment(torch="2.14.0+cpu"))
    _perturb_test_reference(tolerant, _one_ulp)
    result = tolerant.run()
    outcome = next(o for o in result.outcomes if o.run_id == _RUN_F1)
    assert outcome.max_abs_diff > 0
    assert outcome.max_normalized_diff == pytest.approx(outcome.max_abs_diff / _SCALE)


def test_normalized_diff_above_tolerance_fails() -> None:
    world = _World(current_environment=_environment(torch="2.14.0+cpu"))
    _perturb_test_reference(world, lambda v: v + 1e-4 * _SCALE)

    with pytest.raises(ReproductionError, match="tolerance"):
        world.run()


def test_test_key_set_mismatch_fails() -> None:
    world = _World()
    del world.grids[_RUN_F0]["test"][58]

    with pytest.raises(ReproductionError, match="keys differ"):
        world.run()


@pytest.mark.parametrize(
    ("silver_empty", "predicted_empty"),
    [(True, True), (True, False), (False, True)],
    ids=["both-empty", "silver-empty", "prediction-empty"],
)
def test_empty_test_comparison_fails_closed(silver_empty: bool, predicted_empty: bool) -> None:
    """C7 fail-closed: zero valores comparados não provam a reprodução."""

    def hide_test_rows(row: Mapping[str, object]) -> Mapping[str, object]:
        if row.get("run_id") == _RUN_F0 and row.get("split") == "test":
            return {**row, "split": "hidden"}
        return row

    world = _World(silver_patch=hide_test_rows if silver_empty else None)
    if predicted_empty:
        world.grids[_RUN_F0]["test"] = {}

    with pytest.raises(ReproductionError, match="nothing to compare"):
        world.run()

    assert world.facts("calib") == []


def test_reproduction_failure_writes_no_calib() -> None:
    world = _World()
    _perturb_test_reference(world, _one_ulp)

    with pytest.raises(ReproductionError):
        world.run()

    assert world.facts("calib", _RUN_F1) == []
    assert not any(e.startswith(f"manifest:{_RUN_F1}") for e in world.events)


# -- guardas (I4) ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "code-dirty",
        "no-cohort-environment",
        "incomplete-cohort",
        "fold",
        "seed",
        "model-version",
        "feature-set",
        "sha",
    ],
)
def test_guards_in_order_never_call_the_predictor(case: str) -> None:
    world = _World()
    error: type[Exception] = InferenceEnvironmentError
    if case == "code-dirty":
        world.current_environment = _environment(**{DIRTY_KEY: "true"})
    elif case == "no-cohort-environment":
        world.record_cohort_environment = False
    elif case == "incomplete-cohort":
        world.resolver_error = ApplicationError("cohort incomplete (C14)")
        error = ApplicationError
    elif case in {"fold", "seed", "model-version", "feature-set"}:
        column, value = {
            "fold": ("fold", "9"),
            "seed": ("seed", 99),
            "model-version": ("model_version", "gbm_quantile"),
            "feature-set": ("feature_set_name", "fs_other"),
        }[case]
        rows = world.repository.read(
            layer="silver", table="dim_run", filters={"asset": cohort.ASSET}
        )
        world.repository.write(
            layer="silver",
            table="dim_run",
            rows=[{**r, column: value} for r in rows if r["run_id"] == _RUN_F1],
            allow_upsert=True,
        )
        error = UnknownRunError
    elif case == "sha":
        world.manifest.record_run(
            _COHORT_ID, _RUN_F1, {"checkpoint_sha256": "0" * 64, "status": COMPLETED}
        )
        error = ArtifactChangedError

    with pytest.raises(error):
        world.run()

    assert world.last_predictor.calls == []
    if case in {"code-dirty", "no-cohort-environment"}:
        assert world.last_resolver.calls == []


def test_first_violated_guard_wins() -> None:
    world = _World(record_cohort_environment=False)
    world.current_environment = _environment(**{DIRTY_KEY: "true"})

    with pytest.raises(InferenceEnvironmentError, match="uncommitted"):
        world.run()

    assert world.last_resolver.calls == []


@pytest.mark.parametrize("threads", ["abc", "0"])
def test_invalid_recorded_threads_is_an_environment_error(threads: str) -> None:
    world = _World(cohort_environment=_environment(**{THREADS_KEY: threads}))
    world.current_environment = _environment(**{THREADS_KEY: threads})

    with pytest.raises(InferenceEnvironmentError, match="C11"):
        world.run()

    assert world.last_resolver.calls == []


# -- write-ahead e proveniência (I8) -------------------------------------------------------------


def test_started_entry_written_before_first_calib_write() -> None:
    world = _World()

    world.run()

    for fold in _FOLDS:
        started = world.events.index(f"manifest:{fold.run_id}:{STARTED}")
        first_write = next(
            i for i, e in enumerate(world.events) if e.startswith(f"persist:{fold.run_id}:")
        )
        completed = world.events.index(f"manifest:{fold.run_id}:{COMPLETED}")
        assert started < first_write < completed


def test_crash_between_decisions_rerun_completes_only_missing_and_keeps_first_write() -> None:
    world = _World()
    _started_entry_after_crash(world)
    first = dict(world.entry(_RUN_F0))
    world.events.clear()
    # Retomada permitida: só uma chave de CÓDIGO mudou; o relógio andou.
    world.current_environment = _environment(**{"code.src": "tree-after-crash"})
    world.now = datetime(2026, 10, 7, 9, 30, tzinfo=UTC)

    result = world.run()

    writes_f0 = [e for e in world.events if e.startswith(f"persist:{_RUN_F0}:")]
    assert len(writes_f0) == _SPEC.geometry.calib_size - 2
    outcome = next(o for o in result.outcomes if o.run_id == _RUN_F0)
    assert outcome.calib_rows_verified == 2 * len(_HORIZONS) * len(_LEVELS)
    entry = world.entry(_RUN_F0)
    assert entry["first_write_environment"]["code.src"] == first["environment"]["code.src"]
    assert entry["environment"]["code.src"] == "tree-after-crash"
    assert entry["first_written_at"] == first["first_written_at"]
    assert entry["verified_at"] == world.now.isoformat()
    assert entry["verified_at"] != first["first_written_at"]
    assert entry["status"] == COMPLETED


def test_calib_without_manifest_entry_raises_provenance_missing() -> None:
    world = _World()
    _write_calib_directly(world, _RUN_F0, 50)

    with pytest.raises(CalibProvenanceMissingError, match="C15"):
        world.run()


# -- guardrail (I9) ---------------------------------------------------------------------------


def test_crossed_raw_grid_written_raw_with_monotone_guardrail() -> None:
    world = _World()
    crossed = (0.03, 0.01, 0.02)
    world.grids[_RUN_F0]["calib"][50] = {h: crossed for h in _HORIZONS}

    world.run()

    rows = sorted(
        (
            r
            for r in world.facts("calib", _RUN_F0)
            if r["decision_idx"] == _F0_CALIB_FIRST and r["horizon"] == 1
        ),
        key=lambda r: float(r["quantile_level"]),  # type: ignore[arg-type]
    )
    assert [r["value_raw"] for r in rows] == list(crossed)
    guardrail = [float(r["value_guardrail"]) for r in rows]  # type: ignore[arg-type]
    assert guardrail == sorted(guardrail)
    assert {r["guardrail_applied"] for r in rows} == {1}


# -- fecho ---------------------------------------------------------------------------------------


def test_reread_count_completes_the_run() -> None:
    world = _World()

    result = world.run()

    for fold, outcome in zip(_FOLDS, result.outcomes, strict=True):
        assert outcome.calib_rows_written == _EXPECTED_CALIB
        assert len(world.facts("calib", fold.run_id)) == _EXPECTED_CALIB
        assert world.entry(fold.run_id)["status"] == COMPLETED


def test_incomplete_reread_raises_and_keeps_started() -> None:
    world = _World()
    del world.grids[_RUN_F0]["calib"][54]

    with pytest.raises(IncompleteCalibError, match="C9"):
        world.run()

    assert world.entry(_RUN_F0)["status"] == STARTED


def test_second_run_writes_zero_and_verifies_all() -> None:
    world = _World()
    world.run()

    result = world.run()

    assert [o.calib_rows_written for o in result.outcomes] == [0, 0]
    assert [o.calib_rows_verified for o in result.outcomes] == [_EXPECTED_CALIB] * 2
    second_run_statuses = [status for _, status in world.manifest.history[4:]]
    assert second_run_statuses == [COMPLETED, COMPLETED]


def test_started_entry_has_no_verified_at() -> None:
    world = _World()
    world.persister.fail_after = 1
    with pytest.raises(RuntimeError):
        world.run()

    assert world.entry(_RUN_F0)["status"] == STARTED
    assert "verified_at" not in world.entry(_RUN_F0)


def test_predictor_receives_the_recorded_threads_and_both_partitions() -> None:
    """As threads vêm do ambiente GRAVADO pelo cohort (3), não do atual (6)."""
    world = _World(cohort_environment=_environment(**{THREADS_KEY: "3"}))

    world.run()

    [command] = world.last_predictor.calls
    assert command.num_threads == 3  # noqa: PLR2004
    assert tuple(command.partitions) == ("test", "calib")
    assert command.seed == _SEED
    assert dict(command.allowed) == {fold.run_id: world.sha(fold.run_id) for fold in _FOLDS}


def test_held_lock_raises_locked_before_probe_and_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _World()
    world.ledger.acquire_writer()  # outro escritor detém o lock
    snapshots: list[object] = []
    original = InMemoryRuntimeEnvironmentProbe.snapshot

    def spy(self: InMemoryRuntimeEnvironmentProbe) -> Mapping[str, str]:
        snapshots.append(self)
        return original(self)

    monkeypatch.setattr(InMemoryRuntimeEnvironmentProbe, "snapshot", spy)

    with pytest.raises(CohortRunLockedError):
        world.run()

    assert snapshots == []
    assert world.last_resolver.calls == []
    assert world.last_predictor.calls == []
    assert world.events == []


class _StaleSpyLedger(InMemoryCohortLedger):
    def __init__(self) -> None:
        super().__init__()
        self.break_stale: list[bool] = []

    def acquire_writer(self, *, break_stale: bool = False) -> None:
        self.break_stale.append(break_stale)
        super().acquire_writer(break_stale=break_stale)


@pytest.mark.parametrize("break_stale", [True, False])
def test_break_stale_lock_reaches_the_ledger(break_stale: bool) -> None:
    world = _World()
    world.ledger = _StaleSpyLedger()

    world.run(break_stale_lock=break_stale)

    assert world.ledger.break_stale == [break_stale]


def test_break_stale_lock_takes_over_an_orphan_lock() -> None:
    world = _World()
    world.ledger.acquire_writer()  # lock órfão (processo morto)

    result = world.run(break_stale_lock=True)

    assert [o.calib_rows_written for o in result.outcomes] == [_EXPECTED_CALIB] * 2


def test_lock_released_on_error() -> None:
    world = _World()
    world.resolver_error = ApplicationError("boom")

    with pytest.raises(ApplicationError):
        world.run()

    world.ledger.acquire_writer()  # o lock foi liberado
    with pytest.raises(CohortRunLockedError):
        world.ledger.acquire_writer()


def test_manifest_entry_has_all_fields() -> None:
    world = _World()

    world.run()

    entry = world.entry(_RUN_F0)
    assert set(entry) == {
        "checkpoint_sha256",
        "first_write_environment",
        "first_write_settings",
        "first_written_at",
        "status",
        "fold_index",
        "seed",
        "checkpoint_path",
        "environment",
        "settings",
        "normalizer_center",
        "normalizer_scale",
        "reproduction_mode",
        "mode_reason",
        "calib_reproduction_mode",
        "calib_mode_reason",
        "forced",
        "justification",
        "test_values_compared",
        "max_abs_diff",
        "max_normalized_diff",
        "calib_rows_written",
        "calib_rows_verified",
        "verified_at",
    }
    assert entry["checkpoint_sha256"] == world.sha(_RUN_F0)
    assert entry["settings"]["cpu_capability"] == "AVX2"
    assert (entry["normalizer_center"], entry["normalizer_scale"]) == (_CENTER, _SCALE)
    assert entry["test_values_compared"] == 3 * len(_HORIZONS) * len(_LEVELS)
    document = world.manifest.recorded(_COHORT_ID)
    assert document is not None
    assert document["cohort_environment"] == world.cohort_environment


def test_calib_rows_inherit_the_training_run_identity() -> None:
    world = _World()

    world.run()

    for fold in _FOLDS:
        test_rows = world.facts("test", fold.run_id)
        calib_rows = world.facts("calib", fold.run_id)
        identity = ("run_id", "model_version", "asset", "feature_set_name", "schema_version")
        assert {tuple(r[k] for k in identity) for r in calib_rows} == {
            tuple(r[k] for k in identity) for r in test_rows
        }
        assert {r["decision_idx"] for r in calib_rows} == set(fold.calib)


# -- C8 fail-closed: decisão extra e chave duplicada (Checkpoint C, C3-2) -----------------------


def _manifest_entry_for(world: _World, run_id: str) -> None:
    world.manifest.record_run(
        _COHORT_ID,
        run_id,
        {
            "checkpoint_sha256": world.sha(run_id),
            "first_write_environment": world.current_environment,
            "status": COMPLETED,
        },
    )


def test_present_decision_outside_the_prediction_raises_before_writing() -> None:
    world = _World()
    _manifest_entry_for(world, _RUN_F0)
    fold = _FOLDS[0]
    extra = 49  # antes do calib do fold: não é re-predita
    PersistPredictions(repository=world.repository)(
        world.command(fold.run_id, extra, "calib", {1: _grid(fold.run_id, extra, 1)})
    )
    world.events.clear()

    with pytest.raises(ReproductionError, match="not re-predicted"):
        world.run()

    assert world.events == []


def test_duplicated_present_key_raises_before_writing() -> None:
    world = _World()
    _complete_first_run(world)
    [row] = [
        r
        for r in world.facts("calib", _RUN_F0)
        if r["decision_idx"] == _F0_CALIB_FIRST
        and r["horizon"] == 1
        and r["quantile_level"] == _LEVELS[1]
    ]
    # Mesma (decisão, horizonte, nível) com outro timestamp: outra PK, mesma chave de C8.
    world.repository.write(
        layer="silver",
        table="fact_oos_predictions",
        rows=[{**row, "timestamp_utc": "2030-01-01T00:00:00+00:00"}],
    )

    with pytest.raises(ReproductionError, match="more than once"):
        world.run()

    assert world.events == []


# -- consistência da resolução e da predição (C3-6) ------------------------------------------------


@pytest.mark.parametrize(
    "answered",
    [{"resolved_cohort_id": "other-cohort"}, {"resolved_seed": 99}],
    ids=["other-cohort", "other-seed"],
)
def test_resolution_of_another_cohort_raises(answered: dict[str, Any]) -> None:
    """O resolver responde por outro cohort ou outra seed: C6 antes de predizer."""
    world = _World(**answered)

    with pytest.raises(UnknownRunError, match="C6"):
        world.run()

    assert world.last_predictor.calls == []


def _drop_last_run(result: PredictTftFromCheckpointsResult) -> PredictTftFromCheckpointsResult:
    return replace(result, runs=result.runs[:-1])


def _swap_sha(result: PredictTftFromCheckpointsResult) -> PredictTftFromCheckpointsResult:
    first, *rest = result.runs
    return replace(result, runs=(replace(first, checkpoint_sha256="f" * 64), *rest))


def _other_cohort(result: PredictTftFromCheckpointsResult) -> PredictTftFromCheckpointsResult:
    return replace(result, cohort_id="other")


def _other_seed(result: PredictTftFromCheckpointsResult) -> PredictTftFromCheckpointsResult:
    return replace(result, seed=99)


def _duplicated_run(result: PredictTftFromCheckpointsResult) -> PredictTftFromCheckpointsResult:
    return replace(result, runs=(*result.runs, result.runs[0]))


@pytest.mark.parametrize(
    ("tamper", "error"),
    [
        (_drop_last_run, UnknownRunError),
        (_swap_sha, ArtifactChangedError),
        (_other_cohort, UnknownRunError),
        (_other_seed, UnknownRunError),
        (_duplicated_run, UnknownRunError),
    ],
    ids=["missing-run", "other-checkpoint", "other-cohort", "other-seed", "duplicated-run"],
)
def test_prediction_must_match_the_allowed_runs(
    tamper: Callable[[PredictTftFromCheckpointsResult], PredictTftFromCheckpointsResult],
    error: type[Exception],
) -> None:
    world = _World(tamper_prediction=tamper)

    with pytest.raises(error):
        world.run()

    assert world.facts("calib") == []


@pytest.mark.parametrize("scale", [0.0, -0.02, math.nan, math.inf], ids=str)
def test_unusable_normalizer_scale_raises_before_writing(scale: float) -> None:
    """Escala do normalizador nula, negativa ou não finita: C7 antes de qualquer calib."""

    def bad_scale(result: PredictTftFromCheckpointsResult) -> PredictTftFromCheckpointsResult:
        first, *rest = result.runs
        return replace(result, runs=(replace(first, normalizer_scale=scale), *rest))

    world = _World(tamper_prediction=bad_scale)

    with pytest.raises(ReproductionError, match="normalizer scale"):
        world.run()

    assert world.facts("calib") == []


# -- regra de tolerância na fronteira (C3-4) ------------------------------------------------------


def test_tolerance_rtol_term_scales_with_the_normalized_reference() -> None:
    scale, ref = 0.01, 1.0  # com c = 0, z_ref = 100
    allowed = (1e-5 + 1.3e-6 * 100) * scale

    assert within_mode(new=ref + 0.9 * allowed, ref=ref, center=0.0, scale=scale, mode=TOLERANCE)
    assert not within_mode(
        new=ref + 1.1 * allowed, ref=ref, center=0.0, scale=scale, mode=TOLERANCE
    )
    # Com c = ref (z_ref = 0) só vale o termo absoluto: o mesmo Δ reprova.
    assert not within_mode(
        new=ref + 0.9 * allowed, ref=ref, center=ref, scale=scale, mode=TOLERANCE
    )
    assert within_mode(new=ref, ref=ref, center=0.0, scale=scale, mode=STRICT)
    assert not within_mode(new=ref + 1e-12, ref=ref, center=0.0, scale=scale, mode=STRICT)
