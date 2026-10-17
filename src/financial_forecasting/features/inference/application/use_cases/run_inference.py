"""Use case `RunInference` — reproduz o teste e completa a partição `calib` do cohort (7.1).

Para o cohort congelado, por seed e por run TFT: prova que o teste re-predito a
partir do checkpoint reproduz o `value_raw` do silver e grava a partição `calib`
em `fact_oos_predictions` por complementação idempotente, com manifesto
write-ahead (concept 7.1 §4/§5; ADRs 7.1.0002 a 0004). Só predições: nada do
realizado é lido para avaliar e nada de `evaluation` é importado (I13).

Ordem (concept §5; technical §1 "Fluxo do RunInference"):

0. C1 (`is_frozen`) e C13 (justificativa) — antes de lock, probe ou I/O;
1. lock de escritor (I11), liberado em `finally`;
2. probe: `code_dirty` → C11; ambiente do cohort gravado no ledger (ausente → C11);
3. por seed: resolver (sem carga; completude C14) → por fold, `dim_run` (C6) e
   sha256 contra o manifesto (C10) → predictor com a lista permitida, partições
   `("test", "calib")` e as threads gravadas pelo cohort;
4. por run, em ordem de fold: reprodução do teste (C7) → C15 → write-ahead /
   retomada (C11) → calib por decisão (escrita se ausente, conferência da linha
   inteira se presente — C8) → releitura da contagem (C9) → `completed`.

Modo (I6, ADR 7.1.0003 item 3): chaves não-código = união das chaves dos dois
ambientes menos `CODE_KEYS` e `DIRTY_KEY` (do port do modeling, nunca
redeclarados). Iguais e sem justificativa → `strict`; iguais com justificativa
válida → `tolerance` forçado; diferentes → `tolerance`. Referência do teste = o
ambiente do cohort; referência do calib já presente = o ambiente da primeira
escrita do run (manifesto).

Arestas de dados de runtime (declaradas no `bc-independence`, ADR 0.0.0053 item
3): os DTOs de comando dos use cases fornecedores do `modeling`, as chaves do port
do probe do `modeling`, o `PersistPredictionsCommand` e o VO `QuantileForecast`
(guardrail, ADR 4.3.0002) do `analytics_store`. As exceções homônimas do
`modeling` (`UnknownRunError`, `ArtifactChangedError`, `CohortNotFrozenError`,
`IncompleteCohortError`) não são importadas: propagam como `ApplicationError`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictionsCommand,
)
from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.inference.domain.services.reproduction_policy import (
    STRICT,
    ReproductionComparison,
    ReproductionMode,
    compare_reproduction,
    reproduction_mode,
    within_mode,
)
from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    CODE_KEYS,
    DIRTY_KEY,
    THREADS_KEY,
)
from financial_forecasting.features.modeling.application.use_cases.predict_tft_from_checkpoints import (  # noqa: E501
    PredictTftFromCheckpointsCommand,
)
from financial_forecasting.features.modeling.application.use_cases.resolve_tft_checkpoints import (
    ResolveTftCheckpointsCommand,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash

if TYPE_CHECKING:
    from financial_forecasting.features.inference.application.ports.out.checkpoint_grid_predictor import (  # noqa: E501
        CheckpointGridPredictor,
    )
    from financial_forecasting.features.inference.application.ports.out.checkpoint_resolver import (
        CheckpointResolver,
    )
    from financial_forecasting.features.inference.application.ports.out.cohort_ledger import (
        CohortLedger,
    )
    from financial_forecasting.features.inference.application.ports.out.inference_manifest import (
        InferenceManifest,
    )
    from financial_forecasting.features.inference.application.ports.out.prediction_persister import (  # noqa: E501
        PredictionPersister,
    )
    from financial_forecasting.features.inference.application.ports.out.runtime_environment_probe import (  # noqa: E501
        RuntimeEnvironmentProbe,
    )
    from financial_forecasting.features.inference.application.ports.out.silver_table_reader import (
        SilverTableReader,
    )
    from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec
    from financial_forecasting.features.modeling.application.use_cases.predict_tft_from_checkpoints import (  # noqa: E501
        CheckpointRunPrediction,
        PredictTftFromCheckpointsResult,
    )
    from financial_forecasting.features.modeling.application.use_cases.resolve_tft_checkpoints import (  # noqa: E501
        CheckpointResolution,
    )
    from financial_forecasting.shared.application.ports.out.clock import Clock
    from financial_forecasting.shared.application.ports.out.hasher import Hasher

_SILVER = "silver"
_DIM_RUN = "dim_run"
_FACT = "fact_oos_predictions"
_TEST = "test"
_CALIB = "calib"
_PARTITIONS = (_TEST, _CALIB)
STARTED = "started"
COMPLETED = "completed"
FINDING_TAG = "[finding]"
# Chaves de ambiente fora da comparação de modo (I6): as do código e a de sujeira,
# do port do `modeling` (nunca redeclaradas); a política fica no domain (ADR 7.2.0005).
_IGNORED_KEYS = frozenset({*CODE_KEYS, DIRTY_KEY})

Row = Mapping[str, object]
_Key = tuple[int, int, float]


class CohortNotFrozenError(ApplicationError):
    """O spec do cohort não está congelado (C1) — homônima LOCAL da do `modeling`."""


class ReproductionError(ApplicationError):
    """Teste re-predito ≠ silver (C7) ou linha de calib presente ≠ re-predita (C8)."""


class UnknownRunError(ApplicationError):
    """Run resolvido ausente do `dim_run` do cohort ou com fold/seed/versão diferentes (C6)."""


class ArtifactChangedError(ApplicationError):
    """sha256 do checkpoint ≠ o gravado no manifesto (C10) — nada foi carregado."""


class IncompleteCalibError(ApplicationError):
    """Calib do run incompleto na releitura (C9); a entrada fica `started`."""


class InferenceEnvironmentError(ApplicationError):
    """Árvore suja, ambiente do cohort ausente ou retomada em outro ambiente (C11)."""


class CalibProvenanceMissingError(ApplicationError):
    """Linhas de calib presentes sem entrada do run no manifesto (C15)."""


@dataclass(frozen=True)
class RunInferenceCommand:
    """DTO de entrada — o spec congelado, o lock e a justificativa de `--cross-environment`."""

    spec: CohortSpec
    break_stale_lock: bool = False
    cross_environment_justification: str | None = None


@dataclass(frozen=True)
class InferenceRunOutcome:
    """O que aconteceu com um run: modo, reprodução e linhas de calib."""

    run_id: str
    fold_index: int
    seed: int
    reproduction_mode: str
    test_values_compared: int
    max_abs_diff: float
    max_normalized_diff: float
    calib_rows_written: int
    calib_rows_verified: int


@dataclass(frozen=True)
class RunInferenceResult:
    """DTO de saída — o cohort e um desfecho por run (seed, depois fold)."""

    cohort_id: str
    outcomes: tuple[InferenceRunOutcome, ...]


def _mode(
    reference: Mapping[str, str], current: Mapping[str, str], justification: str | None
) -> ReproductionMode:
    """Modo do domain com as chaves de código e de sujeira ignoradas (I6)."""
    return reproduction_mode(reference, current, justification, ignored_keys=_IGNORED_KEYS)


def _validate_justification(justification: str | None) -> str | None:
    """C13: a justificativa, quando dada, é não vazia e cita o `[finding]` do diagnóstico."""
    if justification is None:
        return None
    if not justification.strip() or FINDING_TAG not in justification:
        raise ValueError(
            "--cross-environment needs a non-empty justification citing the diagnosed "
            f"{FINDING_TAG} (C13)"
        )
    return justification


def _recorded_threads(environment: Mapping[str, str], cohort_id: str) -> int:
    """`torch_threads` gravado pelo cohort, inteiro >= 1; senão o ambiente é inválido (C11)."""
    value = environment.get(THREADS_KEY)
    try:
        threads = int(str(value))
    except ValueError:
        threads = 0
    if value is None or threads < 1:
        raise InferenceEnvironmentError(
            f"cohort {cohort_id}: recorded {THREADS_KEY}={value!r} is not a positive integer (C11)"
        )
    return threads


def _float(value: object) -> float:
    # célula numérica do silver; `float(str(v))` mudaria um np.float32 e o |Δ| = 0 bit a bit
    return float(value)  # type: ignore[arg-type]


def _int(value: object) -> int:
    return int(str(value))


@dataclass(frozen=True)
class _SeedContext:
    spec: CohortSpec
    cohort_id: str
    seed: int
    cohort_environment: Mapping[str, str]
    current_environment: Mapping[str, str]
    justification: str | None
    recorded_runs: Mapping[str, Mapping[str, object]]
    settings: Mapping[str, str]
    dataset_timestamps: tuple[str, ...]


class RunInference:
    """Reproduz o teste e completa o calib de cada run TFT do cohort congelado."""

    def __init__(  # noqa: PLR0913 — os ports do consumidor (concept §4)
        self,
        *,
        resolver: CheckpointResolver,
        predictor: CheckpointGridPredictor,
        probe: RuntimeEnvironmentProbe,
        persister: PredictionPersister,
        silver: SilverTableReader,
        ledger: CohortLedger,
        manifest: InferenceManifest,
        hasher: Hasher,
        clock: Clock,
    ) -> None:
        self._resolver = resolver
        self._predictor = predictor
        self._probe = probe
        self._persister = persister
        self._silver = silver
        self._ledger = ledger
        self._manifest = manifest
        self._hasher = hasher
        self._clock = clock

    def __call__(self, command: RunInferenceCommand) -> RunInferenceResult:
        spec = command.spec
        if not spec.is_frozen():  # C1 — antes de lock e probe
            raise CohortNotFrozenError(
                f"cohort {spec.name!r} r{spec.revision} is not frozen — nothing to infer (C1)"
            )
        justification = _validate_justification(command.cross_environment_justification)
        cohort_id = spec.cohort_id(
            CohortHash.compute(hasher=self._hasher, payload=spec.hash_payload())
        )

        self._ledger.acquire_writer(break_stale=command.break_stale_lock)
        try:
            current = dict(self._probe.snapshot())
            if current.get(DIRTY_KEY) == "true":
                raise InferenceEnvironmentError(
                    "tracked uncommitted changes in src/, uv.lock or the cohort file — "
                    "commit first (C11)"
                )
            recorded_environment = self._ledger.environment(cohort_id)
            if recorded_environment is None:
                raise InferenceEnvironmentError(
                    f"cohort {cohort_id} has no recorded environment — run the cohort first (C11)"
                )
            _recorded_threads(recorded_environment, cohort_id)  # C11 — antes do resolver
            document = self._manifest.recorded(cohort_id) or {}
            runs = document.get("runs", {})
            recorded_runs: Mapping[str, Mapping[str, object]] = (
                runs if isinstance(runs, Mapping) else {}
            )
            outcomes: list[InferenceRunOutcome] = []
            for seed in spec.seeds:
                outcomes.extend(
                    self._run_seed(
                        spec=spec,
                        cohort_id=cohort_id,
                        seed=seed,
                        cohort_environment=dict(recorded_environment),
                        current_environment=current,
                        justification=justification,
                        recorded_runs=recorded_runs,
                    )
                )
        finally:
            self._ledger.release_writer()
        return RunInferenceResult(cohort_id=cohort_id, outcomes=tuple(outcomes))

    # -- seed ---------------------------------------------------------------------

    def _run_seed(  # noqa: PLR0913 — estado coeso de uma seed
        self,
        *,
        spec: CohortSpec,
        cohort_id: str,
        seed: int,
        cohort_environment: Mapping[str, str],
        current_environment: Mapping[str, str],
        justification: str | None,
        recorded_runs: Mapping[str, Mapping[str, object]],
    ) -> list[InferenceRunOutcome]:
        resolution = self._resolver(ResolveTftCheckpointsCommand(spec=spec, seed=seed))
        if resolution.cohort_id != cohort_id or resolution.seed != seed:
            raise UnknownRunError(
                f"resolver answered for cohort {resolution.cohort_id} seed {resolution.seed}, "
                f"asked for {cohort_id} seed {seed} (C6)"
            )
        dim_rows = {
            str(row["run_id"]): row
            for row in self._silver.read(
                layer=_SILVER,
                table=_DIM_RUN,
                filters={"asset": spec.asset_id, "parent_sweep_id": cohort_id},
            )
            if row.get("parent_sweep_id") == cohort_id
        }
        allowed: dict[str, str] = {}
        for run in resolution.runs:
            self._check_dim_run(spec, cohort_id, seed, run, dim_rows.get(run.run_id))  # C6
            entry = recorded_runs.get(run.run_id)
            if entry is not None and entry.get("checkpoint_sha256") != run.checkpoint_sha256:
                raise ArtifactChangedError(  # C10 — antes de qualquer carga
                    f"run {run.run_id}: checkpoint sha256 {run.checkpoint_sha256[:12]} != "
                    f"manifest {str(entry.get('checkpoint_sha256'))[:12]} (C10)"
                )
            allowed[run.run_id] = run.checkpoint_sha256

        prediction = self._predictor(
            PredictTftFromCheckpointsCommand(
                spec=spec,
                seed=seed,
                allowed=allowed,
                partitions=_PARTITIONS,
                num_threads=_recorded_threads(cohort_environment, cohort_id),
            )
        )
        _check_prediction(prediction, cohort_id=cohort_id, seed=seed, allowed=allowed)
        context = _SeedContext(
            spec=spec,
            cohort_id=cohort_id,
            seed=seed,
            cohort_environment=cohort_environment,
            current_environment=current_environment,
            justification=justification,
            recorded_runs=recorded_runs,
            settings=dict(prediction.settings),
            dataset_timestamps=tuple(prediction.dataset_timestamps),
        )
        resolutions = {run.run_id: run for run in resolution.runs}
        facts = self._facts_by_run(spec, set(allowed))
        return [
            self._run_one(
                context,
                run=run,
                resolution=resolutions[run.run_id],
                dim_row=dim_rows[run.run_id],
                facts=facts.get(run.run_id, []),
            )
            for run in sorted(prediction.runs, key=lambda r: r.fold_index)
        ]

    @staticmethod
    def _check_dim_run(
        spec: CohortSpec,
        cohort_id: str,
        seed: int,
        run: CheckpointResolution,
        row: Row | None,
    ) -> None:
        """C6: o run resolvido existe no `dim_run` do cohort com fold/seed/versão esperados."""
        if (
            row is None
            or str(row.get("fold")) != str(run.fold_index)
            or row.get("seed") != seed
            or row.get("model_version") != run.model_version
            or row.get("feature_set_name") != spec.feature_set_name
        ):
            raise UnknownRunError(
                f"run {run.run_id} (fold {run.fold_index}, seed {seed}, "
                f"{run.model_version}) is not in dim_run of cohort {cohort_id} (C6)"
            )

    def _facts_by_run(self, spec: CohortSpec, run_ids: set[str]) -> dict[str, list[Row]]:
        by_run: dict[str, list[Row]] = {}
        for fact in self._silver.read(
            layer=_SILVER,
            table=_FACT,
            filters={"asset": spec.asset_id, "feature_set_name": spec.feature_set_name},
        ):
            run_id = str(fact["run_id"])
            if run_id in run_ids:
                by_run.setdefault(run_id, []).append(fact)
        return by_run

    # -- run ----------------------------------------------------------------------

    def _run_one(
        self,
        context: _SeedContext,
        *,
        run: CheckpointRunPrediction,
        resolution: CheckpointResolution,
        dim_row: Row,
        facts: Sequence[Row],
    ) -> InferenceRunOutcome:
        spec = context.spec
        center, scale = run.normalizer_center, run.normalizer_scale
        if not (math.isfinite(scale) and scale > 0):
            raise ReproductionError(f"run {run.run_id}: normalizer scale {scale!r} unusable (C7)")
        test_mode = _mode(
            context.cohort_environment, context.current_environment, context.justification
        )
        reproduction = _reproduce_test(
            run, [f for f in facts if f.get("split") == _TEST], spec, test_mode, center, scale
        )  # C7 — antes de qualquer linha de calib

        present = [f for f in facts if f.get("split") == _CALIB]
        entry = context.recorded_runs.get(run.run_id)
        if present and entry is None:
            raise CalibProvenanceMissingError(
                f"run {run.run_id} has {len(present)} calib rows but no manifest entry — "
                "cannot verify rows of unknown provenance (C15)"
            )
        first_environment: Mapping[str, str] = context.current_environment
        if entry is not None:
            recorded_first = entry.get("first_write_environment")
            if isinstance(recorded_first, Mapping):
                first_environment = {str(k): str(v) for k, v in recorded_first.items()}
            if entry.get("status") == STARTED:
                differing = _mode(first_environment, context.current_environment, None)
                if differing.name != STRICT:
                    raise InferenceEnvironmentError(
                        f"run {run.run_id} was started in another environment "
                        f"({differing.reason}) — resume it in the original environment (C11)"
                    )
        calib_mode = _mode(first_environment, context.current_environment, context.justification)
        base_entry = self._entry(
            context,
            run=run,
            resolution=resolution,
            mode=test_mode,
            calib_mode=calib_mode,
            reproduction=reproduction,
        )

        # C8 em memória, sobre os fatos já lidos, ANTES de qualquer escrita: uma
        # divergência ergue sem tocar silver nem manifesto.
        forecasts = _calib_forecasts(run, spec)
        present_by_decision = _present_by_decision(run.run_id, present, forecasts)
        verified = sum(
            _verify_decision(
                run_id=run.run_id,
                decision=decision,
                rows=rows,
                forecasts=forecasts[decision],
                dim_row=dim_row,
                timestamps=context.dataset_timestamps,
                mode=calib_mode.name,
                center=center,
                scale=scale,
            )
            for decision, rows in sorted(present_by_decision.items())
        )
        missing = [decision for decision in forecasts if decision not in present_by_decision]
        written = 0
        if missing:
            # write-ahead: a entrada `started` imediatamente antes da 1ª escrita
            self._manifest.record_run(
                context.cohort_id, run.run_id, {**base_entry, "status": STARTED}
            )
            written = self._write_calib(
                context, run=run, dim_row=dim_row, missing=missing, forecasts=forecasts
            )
        reread = self._calib_rows(context.spec, run.run_id)
        expected = spec.geometry.calib_size * len(spec.horizons) * len(spec.quantile_levels)
        if reread != expected:  # C9 — a entrada fica como estava (`started` se escreveu)
            raise IncompleteCalibError(
                f"run {run.run_id}: {reread} calib rows after writing, expected {expected} (C9)"
            )
        self._manifest.record_run(
            context.cohort_id,
            run.run_id,
            {
                **base_entry,
                "status": COMPLETED,
                "calib_rows_written": written,
                "calib_rows_verified": verified,
                "verified_at": self._clock.now().isoformat(),
            },
        )
        return InferenceRunOutcome(
            run_id=run.run_id,
            fold_index=run.fold_index,
            seed=context.seed,
            reproduction_mode=test_mode.name,
            test_values_compared=reproduction.compared,
            max_abs_diff=reproduction.max_abs_diff,
            max_normalized_diff=reproduction.max_normalized_diff,
            calib_rows_written=written,
            calib_rows_verified=verified,
        )

    def _entry(  # noqa: PLR0913 — os campos de uma entrada do manifesto
        self,
        context: _SeedContext,
        *,
        run: CheckpointRunPrediction,
        resolution: CheckpointResolution,
        mode: ReproductionMode,
        calib_mode: ReproductionMode,
        reproduction: ReproductionComparison,
    ) -> dict[str, object]:
        """Campos comuns de `started` e `completed` (sem `verified_at`, só do `completed`)."""
        return {
            "cohort_environment": dict(context.cohort_environment),
            "checkpoint_sha256": run.checkpoint_sha256,
            "first_write_environment": dict(context.current_environment),
            "first_write_settings": dict(context.settings),
            "first_written_at": self._clock.now().isoformat(),
            "fold_index": run.fold_index,
            "seed": context.seed,
            "checkpoint_path": resolution.checkpoint_path,
            "environment": dict(context.current_environment),
            "settings": dict(context.settings),
            "normalizer_center": run.normalizer_center,
            "normalizer_scale": run.normalizer_scale,
            # `reproduction_mode` é o modo do TESTE (referência: ambiente do cohort);
            # o do calib presente (referência: ambiente da 1ª escrita) vem à parte.
            "reproduction_mode": mode.name,
            "mode_reason": mode.reason,
            "calib_reproduction_mode": calib_mode.name,
            "calib_mode_reason": calib_mode.reason,
            "forced": mode.forced,
            "justification": context.justification,
            "test_values_compared": reproduction.compared,
            "max_abs_diff": reproduction.max_abs_diff,
            "max_normalized_diff": reproduction.max_normalized_diff,
            "calib_rows_written": 0,
            "calib_rows_verified": 0,
        }

    def _write_calib(
        self,
        context: _SeedContext,
        *,
        run: CheckpointRunPrediction,
        dim_row: Row,
        missing: Sequence[int],
        forecasts: Mapping[int, Mapping[int, QuantileForecast]],
    ) -> int:
        """Grava as decisões ausentes pelo `PersistPredictions` (identidade do run de treino)."""
        written = 0
        for decision in sorted(missing):
            result = self._persister(
                PersistPredictionsCommand(
                    run_id=run.run_id,
                    split=_CALIB,
                    model_version=str(dim_row["model_version"]),
                    asset=str(dim_row["asset"]),
                    feature_set_name=str(dim_row["feature_set_name"]),
                    schema_version=_int(dim_row["schema_version"]),
                    decision_idx=decision,
                    dataset_timestamps=context.dataset_timestamps,
                    forecasts=forecasts[decision],
                )
            )
            written += result.rows_written
        return written

    def _calib_rows(self, spec: CohortSpec, run_id: str) -> int:
        return sum(
            1
            for fact in self._silver.read(
                layer=_SILVER,
                table=_FACT,
                filters={"asset": spec.asset_id, "feature_set_name": spec.feature_set_name},
            )
            if str(fact["run_id"]) == run_id and fact.get("split") == _CALIB
        )


def _check_prediction(
    prediction: PredictTftFromCheckpointsResult,
    *,
    cohort_id: str,
    seed: int,
    allowed: Mapping[str, str],
) -> None:
    """A grade devolvida é exatamente a dos runs permitidos, com o sha256 esperado (C6/C10)."""
    returned = {run.run_id for run in prediction.runs}
    if (
        prediction.cohort_id != cohort_id
        or prediction.seed != seed
        or returned != set(allowed)
        or len(returned) != len(prediction.runs)
    ):
        raise UnknownRunError(
            f"predictor answered runs {sorted(returned)} of cohort {prediction.cohort_id} seed "
            f"{prediction.seed}; asked for {sorted(allowed)} of {cohort_id} seed {seed} (C6)"
        )
    changed = sorted(
        run.run_id for run in prediction.runs if run.checkpoint_sha256 != allowed[run.run_id]
    )
    if changed:
        raise ArtifactChangedError(f"runs {changed}: predicted from another checkpoint (C10)")


def _calib_forecasts(
    run: CheckpointRunPrediction, spec: CohortSpec
) -> dict[int, dict[int, QuantileForecast]]:
    """Grade re-predita do calib por decisão x horizonte, com o guardrail do 4.3 (I9)."""
    return {
        decision: {
            horizon: QuantileForecast.from_raw(
                levels=tuple(spec.quantile_levels), raw_values=tuple(grid)
            )
            for horizon, grid in sorted(by_horizon.items())
        }
        for decision, by_horizon in sorted(run.grids.get(_CALIB, {}).items())
    }


def _present_by_decision(
    run_id: str,
    present: Sequence[Row],
    forecasts: Mapping[int, Mapping[int, QuantileForecast]],
) -> dict[int, dict[tuple[int, float], Row]]:
    """Calib presente por decisão, fail-closed (C8): sem chave repetida, só decisões re-preditas."""
    by_decision: dict[int, dict[tuple[int, float], Row]] = {}
    for row in present:
        decision = _int(row["decision_idx"])
        key = (_int(row["horizon"]), _float(row["quantile_level"]))
        rows = by_decision.setdefault(decision, {})
        if key in rows:
            raise ReproductionError(
                f"run {run_id} decision {decision}: calib key (horizon {key[0]}, level "
                f"{key[1]}) present more than once — nothing written (C8)"
            )
        rows[key] = row
    extra = sorted(set(by_decision) - set(forecasts))
    if extra:
        raise ReproductionError(
            f"run {run_id}: calib rows present for decisions {extra} that were not "
            "re-predicted — nothing written (C8)"
        )
    return by_decision


def _reproduce_test(  # noqa: PLR0913 — o run, as linhas de referência e o critério
    run: CheckpointRunPrediction,
    reference_rows: Sequence[Row],
    spec: CohortSpec,
    mode: ReproductionMode,
    center: float,
    scale: float,
) -> ReproductionComparison:
    """C7: mesmas chaves `(decisão, horizonte, nível)` e valores dentro do modo (I5)."""
    reference: dict[_Key, float] = {
        (_int(r["decision_idx"]), _int(r["horizon"]), _float(r["quantile_level"])): _float(
            r["value_raw"]
        )
        for r in reference_rows
    }
    predicted: dict[_Key, float] = {
        (decision, horizon, float(level)): float(value)
        for decision, by_horizon in run.grids.get(_TEST, {}).items()
        for horizon, grid in by_horizon.items()
        for level, value in zip(spec.quantile_levels, grid, strict=True)
    }
    reproduction = compare_reproduction(
        reference, predicted, mode=mode.name, center=center, scale=scale
    )
    if not reference or not predicted:  # fail-closed: nada comparado não prova nada
        raise ReproductionError(
            f"run {run.run_id} ({mode.name}): {len(reference)} silver test values and "
            f"{len(predicted)} re-predicted — nothing to compare (C7)"
        )
    if reproduction.missing or reproduction.extra:
        raise ReproductionError(
            f"run {run.run_id} ({mode.name}): test keys differ from silver — "
            f"{reproduction.missing} missing, {reproduction.extra} extra of {len(reference)} (C7)"
        )
    if reproduction.failures:
        raise ReproductionError(
            f"run {run.run_id} ({mode.name}): {reproduction.failures} of "
            f"{reproduction.compared} test values "
            f"outside the criterion — max|d| {reproduction.max_abs_diff:.3e}, "
            f"max|d|/s {reproduction.max_normalized_diff:.3e} (C7)"
        )
    return reproduction


def _verify_decision(  # noqa: PLR0913 — a linha inteira e o critério
    *,
    run_id: str,
    decision: int,
    rows: Mapping[tuple[int, float], Row],
    forecasts: Mapping[int, QuantileForecast],
    dim_row: Row,
    timestamps: Sequence[str],
    mode: str,
    center: float,
    scale: float,
) -> int:
    """C8: a decisão presente bate com a re-predita em todos os campos da linha."""
    expected = {
        (horizon, float(level))
        for horizon, forecast in forecasts.items()
        for level in forecast.levels
    }
    if set(rows) != expected:
        raise ReproductionError(
            f"run {run_id} decision {decision}: calib rows present for "
            f"{len(rows)} of {len(expected)} (horizon, level) keys — partial write (C8)"
        )
    identity = ("model_version", "asset", "feature_set_name", "schema_version")
    for horizon, forecast in forecasts.items():
        target = decision + horizon
        for position, level in enumerate(forecast.levels):
            row = rows[(horizon, float(level))]
            problems = [name for name in identity if row.get(name) != dim_row.get(name)]
            if row.get("timestamp_utc") != timestamps[decision]:
                problems.append("timestamp_utc")
            if target >= len(timestamps) or row.get("target_timestamp_utc") != timestamps[target]:
                problems.append("target_timestamp_utc")
            if not within_mode(
                new=forecast.raw_values[position],
                ref=_float(row["value_raw"]),
                center=center,
                scale=scale,
                mode=mode,
            ):
                problems.append("value_raw")
            if not within_mode(
                new=forecast.guardrail_values[position],
                ref=_float(row["value_guardrail"]),
                center=center,
                scale=scale,
                mode=mode,
            ):
                problems.append("value_guardrail")
            if mode == STRICT and _int(row["guardrail_applied"]) != int(forecast.guardrail_applied):
                problems.append("guardrail_applied")
            if problems:
                raise ReproductionError(
                    f"run {run_id} decision {decision} horizon {horizon} level {level}: "
                    f"present calib row differs in {problems} ({mode}) — nothing written (C8)"
                )
    return len(expected)
