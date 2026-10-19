"""`RunPermutationInference` com fakes (Stage 7.3, Task 19; CA9, I6, I7, I17, I19; C6-C8).

Harness sintético: o spec congelado de `test_run_confirmatory_cohort.py` (2 seeds,
2 folds, h = 1, 2), as linhas de teste da 7.1 gravadas pelo `PersistPredictions` real
num `FakeAnalyticsRepository` (que também é o silver lido e o destino dos escritores
reais), o resolver e o predictor de atribuição fakes configurados com resultados
coerentes com essas linhas, e o manifesto e o ledger em memória.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pytest

from financial_forecasting.features.analytics_store.application.use_cases.persist_permuted_predictions import (  # noqa: E501
    PersistPermutedPredictions,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictions,
    PersistPredictionsCommand,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_vsn_weights import (  # noqa: E501
    PersistVsnWeights,
)
from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.inference.application.use_cases.run_inference import (
    ArtifactChangedError,
    InferenceEnvironmentError,
    ReproductionError,
    UnknownRunError,
)
from financial_forecasting.features.inference.application.use_cases.run_permutation_inference import (  # noqa: E501
    IncompleteAttributionError,
    PartialAttributionError,
    RunPermutationInference,
    RunPermutationInferenceCommand,
)
from financial_forecasting.features.inference.domain.value_objects.permutation_plan import (
    K_P,
    PERMUTATION_ALGORITHM,
    PERMUTATION_SEED,
    FamilyPermutationPlan,
)
from financial_forecasting.features.modeling.application.use_cases.predict_tft_attribution_from_checkpoints import (  # noqa: E501
    AttributionRunPrediction,
    PredictTftAttributionResult,
)
from financial_forecasting.features.modeling.application.use_cases.resolve_tft_checkpoints import (
    CheckpointResolution,
    ResolveTftCheckpointsResult,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash
from financial_forecasting.shared.domain.value_objects.family_partition_hash import (
    FamilyPartitionHash,
)
from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
    FakeAnalyticsRepository,
)
from tests.fakes.features.inference.in_memory_attribution_manifest import (
    InMemoryAttributionManifest,
)
from tests.fakes.features.inference.in_memory_checkpoint_attribution_predictor import (
    InMemoryCheckpointAttributionPredictor,
)
from tests.fakes.features.inference.in_memory_checkpoint_resolver import (
    InMemoryCheckpointResolver,
)
from tests.fakes.features.inference.in_memory_cohort_ledger import InMemoryCohortLedger
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)
from tests.fakes.shared.in_memory_clock import FakeClock
from tests.unit.features.modeling.application.test_run_confirmatory_cohort import _spec

pytestmark = pytest.mark.unit

_HASHER = CanonicalJsonHasher()
_PARTITION: dict[str, tuple[str, ...]] = {
    "price": ("close", "volume"),
    "technical": ("rsi_14",),
    "sentiment": ("sentiment_score",),
    "fundamental": ("revenue",),
}
_VARIABLES = ("close", "volume", "rsi_14", "sentiment_score", "revenue", "relative_time_idx")
_TIMESTAMPS = tuple(f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}T00:00:00+00:00" for i in range(40))
_DECISIONS = {0: (10, 11, 12, 13, 14), 1: (20, 21, 22, 23, 24)}


def _spec_frozen() -> Any:  # noqa: ANN401
    return _spec()


def _cohort_id(spec: Any) -> str:  # noqa: ANN401
    return spec.cohort_id(CohortHash.compute(hasher=_HASHER, payload=spec.hash_payload()))


def _run_id(seed: int, fold: int) -> str:
    return f"{seed:02d}{fold:02d}" + "0" * 60


def _grid(run_id: str, decision: int, horizon: int, shift: float = 0.0) -> tuple[float, ...]:
    base = int(run_id[:4]) * 1e-4 + decision * 1e-3 + horizon * 1e-2 + shift
    return (base - 0.1, base, base + 0.1)


def _silver_grid(run_id: str, decision: int, horizon: int, crossed: bool) -> tuple[float, ...]:
    values = _grid(run_id, decision, horizon)
    return tuple(reversed(values)) if crossed else values


def _emitted(decision: int, horizons: tuple[int, ...]) -> list[int]:
    return [h for h in horizons if decision + h <= len(_TIMESTAMPS) - 1]


@dataclass
class _Harness:
    spec: Any
    repo: FakeAnalyticsRepository
    resolver: InMemoryCheckpointResolver
    predictor: InMemoryCheckpointAttributionPredictor
    ledger: InMemoryCohortLedger
    manifest: InMemoryAttributionManifest
    probe: InMemoryRuntimeEnvironmentProbe

    def use_case(self) -> RunPermutationInference:
        return RunPermutationInference(
            resolver=self.resolver,
            predictor=self.predictor,
            probe=self.probe,
            permuted_persister=PersistPermutedPredictions(repository=self.repo),
            vsn_persister=PersistVsnWeights(repository=self.repo),
            silver=self.repo,
            ledger=self.ledger,
            manifest=self.manifest,
            hasher=_HASHER,
            clock=FakeClock(),
        )

    def run(self, **command: Any) -> Any:  # noqa: ANN401
        fields: dict[str, Any] = {"spec": self.spec, "family_partition": _PARTITION}
        fields.update(command)
        return self.use_case()(RunPermutationInferenceCommand(**fields))

    def rows(self, table: str) -> list[dict[str, object]]:
        return [
            dict(r) for r in self.repo.read(layer="silver", table=table, filters={"asset": "AAPL"})
        ]


def _attribution_run(
    seed: int, fold: int, *, identity_shift: float = 0.0, crossed: bool = False
) -> AttributionRunPrediction:
    run_id = _run_id(seed, fold)
    decisions = _DECISIONS[fold]
    horizons = (1, 2)

    def grid(decision: int, h: int, shift: float) -> tuple[float, ...]:
        values = _grid(run_id, decision, h, shift)
        return tuple(reversed(values)) if crossed else values

    identity = {
        d: {h: grid(d, h, identity_shift) for h in _emitted(d, horizons)} for d in decisions
    }
    permuted = {
        (family, k): {
            d: {h: grid(d, h, 0.01 * k) for h in _emitted(d, horizons)} for d in decisions
        }
        for family in _PARTITION
        for k in range(1, K_P + 1)
    }
    weights = {d: dict.fromkeys(_VARIABLES, 1.0 / len(_VARIABLES)) for d in decisions}
    return AttributionRunPrediction(
        run_id=run_id,
        fold_index=fold,
        checkpoint_sha256=f"{seed:02d}{fold:02d}".ljust(64, "a"),
        normalizer_center=0.0,
        normalizer_scale=1.0,
        test_decisions=decisions,
        family_columns=_PARTITION,
        identity=identity,
        permuted=permuted,
        encoder_weights=weights,
    )


def _harness(**run_overrides: Any) -> _Harness:  # noqa: ANN401
    crossed = bool(run_overrides.get("crossed", False))
    spec = _spec_frozen()
    cohort_id = _cohort_id(spec)
    repo = FakeAnalyticsRepository(clock=FakeClock())
    persist = PersistPredictions(repository=repo)
    resolutions: dict[int, ResolveTftCheckpointsResult] = {}
    results: dict[int, PredictTftAttributionResult] = {}
    for seed in spec.seeds:
        runs = tuple(_attribution_run(seed, fold, **run_overrides) for fold in _DECISIONS)
        for fold, decisions in _DECISIONS.items():
            for decision in decisions:
                persist(
                    PersistPredictionsCommand(
                        run_id=_run_id(seed, fold),
                        split="test",
                        model_version="tft_quantile",
                        asset="AAPL",
                        feature_set_name=spec.feature_set_name,
                        schema_version=1,
                        decision_idx=decision,
                        dataset_timestamps=_TIMESTAMPS,
                        forecasts={
                            h: QuantileForecast.from_raw(
                                levels=spec.quantile_levels,
                                raw_values=_silver_grid(_run_id(seed, fold), decision, h, crossed),
                            )
                            for h in _emitted(decision, spec.horizons)
                        },
                    )
                )
        resolutions[seed] = ResolveTftCheckpointsResult(
            cohort_id=cohort_id,
            seed=seed,
            runs=tuple(
                CheckpointResolution(
                    fold_index=run.fold_index,
                    run_id=run.run_id,
                    model_version="tft_quantile",
                    checkpoint_path=f"/a/tft/{run.run_id}/best.ckpt",
                    checkpoint_sha256=run.checkpoint_sha256,
                )
                for run in runs
            ),
        )
        results[seed] = PredictTftAttributionResult(
            cohort_id=cohort_id,
            seed=seed,
            dataset_timestamps=_TIMESTAMPS,
            settings={"batch_size": "64", "accelerator": "cpu"},
            runs=runs,
        )
    ledger = InMemoryCohortLedger()
    probe = InMemoryRuntimeEnvironmentProbe(torch_threads="4")
    ledger.record_environment(cohort_id, probe.snapshot(), started_at="2026-10-01T00:00:00")
    return _Harness(
        spec=spec,
        repo=repo,
        resolver=InMemoryCheckpointResolver(resolutions),
        predictor=InMemoryCheckpointAttributionPredictor(
            registry_partition=_PARTITION, results=results
        ),
        ledger=ledger,
        manifest=InMemoryAttributionManifest(),
        probe=probe,
    )


def _partition_hash() -> str:
    return FamilyPartitionHash.compute(
        hasher=_HASHER, feature_set_hash=_spec_frozen().feature_set_hash, partition=_PARTITION
    ).value


# -- identidade e política de reprodução (I7, C6) ------------------------------------


def test_identity_outside_policy_raises_and_writes_nothing() -> None:
    harness = _harness(identity_shift=1e-3)
    with pytest.raises(ReproductionError, match="C6"):
        harness.run()
    assert harness.rows("fact_permuted_predictions") == []
    assert harness.rows("fact_vsn_weights") == []
    assert harness.manifest.recorded(_cohort_id(harness.spec)) is None


def test_strict_in_the_recorded_environment_tolerance_across() -> None:
    harness = _harness()
    result = harness.run()
    assert {o.reproduction_mode for o in result.outcomes} == {"strict"}
    assert all(o.max_abs_diff == 0.0 for o in result.outcomes)

    other = _harness()
    other.probe = InMemoryRuntimeEnvironmentProbe(torch_threads="4", torch="2.14.0+cpu")
    assert {o.reproduction_mode for o in other.run().outcomes} == {"tolerance"}


def test_cross_environment_with_equal_keys_forces_tolerance() -> None:
    harness = _harness()
    result = harness.run(cross_environment_justification="ver [finding] ambiente")
    assert {o.reproduction_mode for o in result.outcomes} == {"tolerance"}
    with pytest.raises(ValueError, match=r"\[finding\]"):
        _harness().run(cross_environment_justification="sem justificativa")


# -- manifesto write-ahead e colunas do plano (I17, I19) -----------------------------


class _OrderRepository(FakeAnalyticsRepository):
    def __init__(self, manifest: InMemoryAttributionManifest) -> None:
        super().__init__(clock=FakeClock())
        self.manifest = manifest
        self.statuses_at_write: list[list[tuple[str, object]]] = []

    def write(self, *, layer: str, table: str, rows: Any, allow_upsert: bool = False) -> Any:  # noqa: ANN401
        if table in {"fact_permuted_predictions", "fact_vsn_weights"}:
            self.statuses_at_write.append(list(self.manifest.history))
        return super().write(layer=layer, table=table, rows=rows, allow_upsert=allow_upsert)


def test_manifest_started_before_first_write_with_plan_identity() -> None:
    harness = _harness()
    spy = _OrderRepository(harness.manifest)
    for row in harness.rows("fact_oos_predictions"):
        spy.write(layer="silver", table="fact_oos_predictions", rows=[row])
    harness.repo = spy
    harness.run()
    first_run = _run_id(11, 0)
    assert spy.statuses_at_write[0] == [(first_run, "started")]
    document = harness.manifest.recorded(_cohort_id(harness.spec))
    assert document is not None
    entry = document["runs"][first_run]  # type: ignore[index]
    assert entry["status"] == "completed"
    assert entry["permutation_seed"] == PERMUTATION_SEED
    assert entry["k_p"] == K_P
    assert entry["permutation_algorithm"] == PERMUTATION_ALGORITHM
    assert entry["fold_index"] == 0
    assert entry["n_decisions"] == len(_DECISIONS[0])
    assert entry["family_partition"] == {f: list(v) for f, v in _PARTITION.items()}
    assert entry["partition_hash"] == _partition_hash()


def test_rows_carry_permutation_seed_algorithm_and_partition_hash() -> None:
    harness = _harness()
    harness.run()
    rows = harness.rows("fact_permuted_predictions")
    assert rows
    assert {r["permutation_seed"] for r in rows} == {PERMUTATION_SEED}
    assert {r["permutation_algorithm"] for r in rows} == {PERMUTATION_ALGORITHM}
    # o hash é o da partição DO COMANDO (não um literal nem o da registry)
    assert {r["partition_hash"] for r in rows} == {_partition_hash()}
    assert (
        _partition_hash()
        != FamilyPartitionHash.compute(
            hasher=_HASHER,
            feature_set_hash=harness.spec.feature_set_hash,
            partition={**_PARTITION, "price": ("close",), "technical": ("rsi_14", "volume")},
        ).value
    )


def test_same_permutation_for_every_seed_and_family() -> None:
    harness = _harness()
    harness.run()
    donors = [command.donors_by_fold for command in harness.predictor.calls]
    assert len(donors) == len(harness.spec.seeds)
    assert donors[0] == donors[1]
    for fold, decisions in _DECISIONS.items():
        expected = FamilyPermutationPlan.generate(
            permutation_seed=PERMUTATION_SEED, k_p=K_P, fold_index=fold, n_decisions=len(decisions)
        )
        assert donors[0][fold] == expected.permutations


def test_vsn_family_follows_the_partition() -> None:
    """C4-3: a família de cada linha da VSN é a da mesma partição do `partition_hash`."""
    harness = _harness()
    harness.run()
    family_of = {feature: family for family, features in _PARTITION.items() for feature in features}
    for row in harness.rows("fact_vsn_weights"):
        assert row["family"] == family_of.get(str(row["variable"]), "none")


def test_predicted_decisions_must_equal_the_silver_test_decisions() -> None:
    """C3-4: as decisões preditas são as de teste do silver da 7.1, na mesma quantidade."""
    harness = _harness()
    seed = harness.spec.seeds[0]
    result = harness.predictor._results[seed]
    runs = list(result.runs)
    runs[0] = replace(runs[0], test_decisions=runs[0].test_decisions[:-1])
    harness.predictor.set_result(seed, replace(result, runs=tuple(runs)))
    with pytest.raises((ReproductionError, ValueError), match=r"C3-4|permutation"):
        harness.run()
    assert harness.rows("fact_permuted_predictions") == []


# -- retomada (C8) ---------------------------------------------------------------------


def test_completed_run_is_reconferred_by_reading_and_skipped() -> None:
    harness = _harness()
    first = harness.run()
    calls = len(harness.predictor.calls)
    second = harness.run()
    assert {o.status for o in first.outcomes} == {"written"}
    assert {o.status for o in second.outcomes} == {"verified"}
    assert len(harness.predictor.calls) == calls  # nada re-predito
    assert sum(o.permuted_rows_verified for o in second.outcomes) == sum(
        o.permuted_rows_written for o in first.outcomes
    )
    assert sum(o.vsn_rows_verified for o in second.outcomes) == sum(
        o.vsn_rows_written for o in first.outcomes
    )


@pytest.mark.parametrize("damage", ["started-with-rows", "k-missing", "vsn-missing"])
def test_partial_run_raises_partial_attribution(damage: str) -> None:
    harness = _harness()
    harness.run()
    cohort_id = _cohort_id(harness.spec)
    run_id = _run_id(11, 0)
    if damage == "started-with-rows":
        harness.manifest.record_run(cohort_id, run_id, {"status": "started"})
    elif damage == "k-missing":
        for key, rows in harness.repo._partitions.items():
            if key[1] == "fact_permuted_predictions":
                rows[:] = [
                    r for r in rows if not (r["run_id"] == run_id and r["permutation_index"] == K_P)
                ]
    else:
        for key, rows in harness.repo._partitions.items():
            if key[1] == "fact_vsn_weights":
                rows[:] = [r for r in rows if r["run_id"] != run_id]
    with pytest.raises(PartialAttributionError, match="C8"):
        harness.run()


# -- grade crua e guardrail ---------------------------------------------------------------


def test_guardrail_applied_with_from_raw() -> None:
    """Grade crua cruzada: gravada crua em `value_raw`, ordenada em `value_guardrail`."""
    harness = _harness(crossed=True)
    harness.run()
    rows = harness.rows("fact_permuted_predictions")
    assert rows
    assert {r["guardrail_applied"] for r in rows} == {1}
    by_point: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for r in rows:
        key = (
            r["run_id"],
            r["permuted_family"],
            r["permutation_index"],
            r["decision_idx"],
            r["horizon"],
        )
        by_point.setdefault(key, []).append(r)
    for point in by_point.values():
        ordered = sorted(point, key=lambda r: float(r["quantile_level"]))  # type: ignore[arg-type]
        raw = [float(r["value_raw"]) for r in ordered]  # type: ignore[arg-type]
        guarded = [float(r["value_guardrail"]) for r in ordered]  # type: ignore[arg-type]
        assert raw == sorted(raw, reverse=True)
        assert guarded == sorted(guarded)


def test_identity_rows_are_written_raw_and_guardrailed() -> None:
    harness = _harness()
    harness.run()
    identity = [
        r for r in harness.rows("fact_permuted_predictions") if r["permuted_family"] == "none"
    ]
    assert identity
    assert all(r["permutation_index"] == 0 for r in identity)
    oos = {
        (r["run_id"], r["decision_idx"], r["horizon"], r["quantile_level"]): r["value_raw"]
        for r in harness.rows("fact_oos_predictions")
    }
    for r in identity:
        assert (
            r["value_raw"]
            == oos[(r["run_id"], r["decision_idx"], r["horizon"], r["quantile_level"])]
        )


# -- guardas antes de escrever --------------------------------------------------------------


def test_partition_refused_by_supplier_before_any_write() -> None:
    harness = _harness()
    moved = {**_PARTITION, "price": ("close",), "technical": ("rsi_14", "volume")}
    with pytest.raises(ApplicationError, match="registry"):
        harness.run(family_partition=moved)
    assert harness.rows("fact_permuted_predictions") == []
    assert harness.manifest.recorded(_cohort_id(harness.spec)) is None


def test_lock_released_on_error() -> None:
    harness = _harness(identity_shift=1e-3)
    with pytest.raises(ReproductionError):
        harness.run()
    assert not harness.ledger.is_locked


def test_artifact_changed_propagates() -> None:
    harness = _harness()
    harness.run()
    cohort_id = _cohort_id(harness.spec)
    harness.manifest.record_run(cohort_id, _run_id(11, 0), {"checkpoint_sha256": "z" * 64})
    harness.manifest = InMemoryAttributionManifest(
        {
            cohort_id: {
                "cohort_id": cohort_id,
                "runs": {_run_id(11, 0): {"status": "completed", "checkpoint_sha256": "z" * 64}},
            }
        }
    )
    with pytest.raises(ArtifactChangedError, match="C7"):
        harness.run()


# -- regras compartilhadas com a 7.1 (C5-9) ------------------------------------------------


def _with_runs(harness: _Harness, seed: int, change: Any) -> None:  # noqa: ANN401
    result = harness.predictor._results[seed]
    harness.predictor.set_result(seed, change(result))


def test_normalizer_scale_zero_is_a_reproduction_error() -> None:
    harness = _harness()
    seed = harness.spec.seeds[0]
    _with_runs(
        harness,
        seed,
        lambda r: replace(r, runs=(replace(r.runs[0], normalizer_scale=0.0), *r.runs[1:])),
    )
    with pytest.raises(ReproductionError, match=r"normalizer scale 0\.0 unusable \(C7\)"):
        harness.run()
    assert harness.rows("fact_permuted_predictions") == []
    assert harness.manifest.recorded(_cohort_id(harness.spec)) is None


@pytest.mark.parametrize("damage", ["seed", "duplicated-run"])
def test_prediction_is_checked_like_the_7_1(damage: str) -> None:
    harness = _harness()
    seed = harness.spec.seeds[0]
    if damage == "seed":
        _with_runs(harness, seed, lambda r: replace(r, seed=seed + 100))
    else:
        _with_runs(harness, seed, lambda r: replace(r, runs=(*r.runs, r.runs[0])))
    with pytest.raises(UnknownRunError, match="C6"):
        harness.run()
    assert harness.rows("fact_permuted_predictions") == []


def test_environment_errors_carry_the_7_1_codes() -> None:
    harness = _harness()
    harness.probe = InMemoryRuntimeEnvironmentProbe(torch_threads="4", code_dirty="true")
    with pytest.raises(InferenceEnvironmentError, match="C11"):
        harness.run()
    with pytest.raises(ValueError, match="C13"):
        _harness().run(cross_environment_justification="sem o marcador")


# -- montagem antes do write-ahead e retomada de `started` (C5-8) ------------------------


def test_from_raw_refusal_happens_before_started() -> None:
    """Grade com tamanho errado: o `from_raw` recusa antes de qualquer entrada no manifesto."""
    harness = _harness()
    seed = harness.spec.seeds[0]
    bad = {
        d: {h: grid[:-1] for h, grid in by_h.items()}
        for d, by_h in harness.predictor._results[seed].runs[0].permuted[("price", 1)].items()
    }
    _with_runs(
        harness,
        seed,
        lambda r: replace(
            r,
            runs=(
                replace(r.runs[0], permuted={**r.runs[0].permuted, ("price", 1): bad}),
                *r.runs[1:],
            ),
        ),
    )
    with pytest.raises(ValueError, match="raw_values"):
        harness.run()
    assert harness.manifest.recorded(_cohort_id(harness.spec)) is None
    assert harness.rows("fact_permuted_predictions") == []


def _started_entry(harness: _Harness, environment: dict[str, str]) -> None:
    harness.manifest.record_run(
        _cohort_id(harness.spec),
        _run_id(11, 0),
        {
            "status": "started",
            "checkpoint_sha256": harness.predictor._results[11].runs[0].checkpoint_sha256,
            "first_write_environment": environment,
        },
    )


def test_started_without_rows_in_another_environment_is_refused() -> None:
    harness = _harness()
    other = dict(InMemoryRuntimeEnvironmentProbe(torch_threads="4", torch="2.14.0+cpu").snapshot())
    _started_entry(harness, other)
    with pytest.raises(InferenceEnvironmentError, match=r"started in another environment.*C11"):
        harness.run()
    assert harness.rows("fact_permuted_predictions") == []
    assert harness.predictor.calls == []


def test_started_without_rows_in_the_same_environment_is_resumed() -> None:
    harness = _harness()
    _started_entry(harness, dict(harness.probe.snapshot()))
    result = harness.run()
    assert {o.status for o in result.outcomes} == {"written"}
    document = harness.manifest.recorded(_cohort_id(harness.spec))
    assert document is not None
    assert document["runs"][_run_id(11, 0)]["status"] == "completed"  # type: ignore[index]


# -- cobertura do plano e releitura antes do `completed` (C5-1) ---------------------------


@pytest.mark.parametrize("probe", ["without-sentiment", "no-vsn-weights", "short-grid"])
def test_incomplete_prediction_refused_on_the_first_run(probe: str) -> None:
    """Sondas do C5-1: a predição que não cobre o plano é recusada antes de escrever."""
    harness = _harness()
    seed = harness.spec.seeds[0]

    def damage(run: AttributionRunPrediction) -> AttributionRunPrediction:
        if probe == "without-sentiment":
            return replace(
                run, permuted={k: v for k, v in run.permuted.items() if k[0] != "sentiment"}
            )
        if probe == "no-vsn-weights":
            return replace(run, encoder_weights={})
        first = min(run.permuted[("price", 1)])
        grids = {d: g for d, g in run.permuted[("price", 1)].items() if d != first}
        return replace(run, permuted={**run.permuted, ("price", 1): grids})

    _with_runs(harness, seed, lambda r: replace(r, runs=(damage(r.runs[0]), *r.runs[1:])))
    with pytest.raises(IncompleteAttributionError, match="C5-1"):
        harness.run()
    assert harness.rows("fact_permuted_predictions") == []
    assert harness.manifest.recorded(_cohort_id(harness.spec)) is None


class _DroppingRepository(FakeAnalyticsRepository):
    """Silver que perde a última linha de VSN de cada escrita (e diz que gravou todas)."""

    def write(self, *, layer: str, table: str, rows: Any, allow_upsert: bool = False) -> Any:  # noqa: ANN401
        if table == "fact_vsn_weights":
            rows = list(rows)[:-1]
        return super().write(layer=layer, table=table, rows=rows, allow_upsert=allow_upsert)


def test_completed_only_after_rereading_the_silver() -> None:
    harness = _harness()
    dropping = _DroppingRepository(clock=FakeClock())
    for row in harness.rows("fact_oos_predictions"):
        dropping.write(layer="silver", table="fact_oos_predictions", rows=[row])
    harness.repo = dropping
    with pytest.raises(PartialAttributionError, match="C8"):
        harness.run()
    document = harness.manifest.recorded(_cohort_id(harness.spec))
    assert document is not None
    assert document["runs"][_run_id(11, 0)]["status"] == "started"  # type: ignore[index]


# -- a retomada confere a entrada contra o plano e o teste da 7.1 (C5-4) -------------------


def _tamper_entry(harness: _Harness, **changes: object) -> None:
    cohort_id = _cohort_id(harness.spec)
    document = harness.manifest.recorded(cohort_id)
    assert document is not None
    entry = dict(document["runs"][_run_id(11, 0)])  # type: ignore[index]
    entry.update(changes)
    harness.manifest.record_run(cohort_id, _run_id(11, 0), entry)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("k_p", K_P - 1),
        ("permutation_seed", PERMUTATION_SEED + 1),
        ("permutation_algorithm", "random_shuffle_v1"),
        ("fold_index", 1),
        ("n_decisions", len(_DECISIONS[0]) + 1),
    ],
)
def test_reconfer_checks_the_entry_against_the_plan(field: str, value: object) -> None:
    harness = _harness()
    harness.run()
    _tamper_entry(harness, **{field: value})
    with pytest.raises(PartialAttributionError, match=rf"manifest {field}"):
        harness.run()


def _edit_rows(harness: _Harness, table: str, change: Any) -> None:  # noqa: ANN401
    for key, rows in harness.repo._partitions.items():
        if key[1] == table:
            rows[:] = [change(r) if r["run_id"] == _run_id(11, 0) else r for r in rows]


def test_reconfer_checks_the_vsn_family_and_decisions() -> None:
    harness = _harness()
    harness.run()
    _edit_rows(
        harness,
        "fact_vsn_weights",
        lambda r: {**r, "family": "price"} if r["variable"] == "rsi_14" else r,
    )
    with pytest.raises(PartialAttributionError, match="vsn family differs"):
        harness.run()
