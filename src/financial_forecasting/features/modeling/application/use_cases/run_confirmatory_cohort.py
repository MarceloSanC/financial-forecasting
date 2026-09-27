"""Use case `RunConfirmatoryCohort` — corrida retomável do cohort confirmatório (Stage 5.5).

Executa as unidades de um cohort CONGELADO — `baselines` → `gbm` → uma unidade
`tft:seed=<s>` por seed, na ordem declarada (baratas primeiro) — chamando os use
cases de treino existentes, todas com o mesmo `parent_sweep_id` (o `cohort_id`
que carrega o hash do spec — I3; ADR 5.5.0001).

Antes de treinar qualquer coisa, na ordem:

1. **I1** — o spec tem de estar congelado (`CohortNotFrozenError`).
2. **I12** — adquire o lock de escritor único do `data_root` (dono único do lock
   no `run`); liberado em `finally`, inclusive em erro.
3. **I4** — declarado = observado: impressão digital do grid lido = a declarada;
   a dos sweeps = a declarada; `feature_set_hash` e `pipeline_version` = os do
   código (`DatasetMismatchError` / `CohortDeclarationMismatchError`).
4. Geometria cabe no grid útil (`GeometryDoesNotFitError`).
5. **I5** — ambiente: árvore com mudança rastreada não commitada é recusada já na
   primeira execução; a primeira grava a foto e o instante de início; a retomada
   com qualquer diferença aborta (`EnvironmentMismatchError`).

Cada unidade é então classificada (ADR 5.5.0003):

- no ledger → as contagens por `run_id` são reconferidas no silver (I6);
  divergência → `CompletedUnitCorruptedError`;
- fora do ledger, pelo silver (I7): sem run ou só órfãos (0 linhas) → roda;
  todos os runs esperados com a contagem esperada do seu fold → marca como
  `verified_completed` sem treinar; qualquer outro estado → `PartialCohortUnitError`.

A marcação no ledger só acontece depois de o use case da unidade retornar.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    DIRTY_KEY,
)
from financial_forecasting.features.modeling.application.use_cases.run_baselines import (
    RunBaselinesCommand,
    RunBaselinesResult,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    TrainGbmQuantileCommand,
    TrainGbmQuantileResult,
    grid_fingerprint,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    TrainTftCommand,
    TrainTftResult,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    build_training_grid,
)
from financial_forecasting.shared.domain.exceptions.base import ApplicationError
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash

if TYPE_CHECKING:
    from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec
    from financial_forecasting.features.modeling.application.ports.out.cohort_progress_ledger import (  # noqa: E501
        CohortProgressLedger,
    )
    from financial_forecasting.features.modeling.application.ports.out.cohort_run_index import (
        CohortRunIndex,
    )
    from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
        RuntimeEnvironmentProbe,
    )
    from financial_forecasting.features.modeling.domain.value_objects.scope_spec import ScopeSpec
    from financial_forecasting.shared.application.ports.out.clock import Clock
    from financial_forecasting.shared.application.ports.out.hasher import Hasher
    from financial_forecasting.shared.application.ports.out.medallion_store import (
        MedallionStore,
    )

_DATASET_LAYER = "processed"
_DATASET_TABLE = "dataset_tft"
# `model_version` que cada use case grava (fixado em teste contra os use cases).
GBM_MODEL_VERSION = "gbm_quantile"
TFT_MODEL_VERSION = "tft_quantile"
BASELINE_MODEL_VERSION_PREFIX = "baseline_"

_RAN = "ran"
_SKIPPED = "skipped_completed"
_VERIFIED = "verified_completed"


class CohortNotFrozenError(ApplicationError):
    """O spec não está congelado (I1): falta HP, proveniência, dado ou seeds."""


class DatasetMismatchError(ApplicationError):
    """A impressão digital do dado lido difere da declarada no spec (I4)."""


class CohortDeclarationMismatchError(ApplicationError):
    """Declarado ≠ observado: proveniência dos sweeps, feature set ou versão do pipeline (I4)."""


class EnvironmentMismatchError(ApplicationError):
    """Árvore suja ou ambiente/código diferente do gravado na primeira execução (I5)."""


class PartialCohortUnitError(ApplicationError):
    """Unidade fora do ledger com gravação parcial no silver (I7-d); remediação: nova revisão."""


class CompletedUnitCorruptedError(ApplicationError):
    """Unidade marcada no ledger cujas contagens não batem mais com o silver (I6)."""


@dataclass(frozen=True)
class RunConfirmatoryCohortCommand:
    """DTO de entrada — o spec congelado do cohort."""

    spec: CohortSpec


@dataclass(frozen=True)
class CohortUnitOutcome:
    """DTO de saída — o que aconteceu com uma unidade."""

    unit_key: str
    status: str
    run_ids: tuple[str, ...]
    rows_written: int


@dataclass(frozen=True)
class RunConfirmatoryCohortResult:
    """DTO de saída — identidade do cohort e o desfecho de cada unidade."""

    cohort_id: str
    cohort_hash: str
    outcomes: tuple[CohortUnitOutcome, ...]


@dataclass(frozen=True)
class _Unit:
    key: str
    model_keys: tuple[tuple[str, int | None], ...]
    execute: Callable[[], Mapping[str, int]]


class RunConfirmatoryCohort:
    """Orquestra a corrida do cohort congelado, retomável por unidade."""

    def __init__(  # noqa: PLR0913 — portas e use cases coesos da orquestração
        self,
        *,
        store: MedallionStore,
        hasher: Hasher,
        clock: Clock,
        ledger: CohortProgressLedger,
        run_index: CohortRunIndex,
        probe: RuntimeEnvironmentProbe,
        run_baselines: Callable[[RunBaselinesCommand], RunBaselinesResult],
        train_gbm: Callable[[TrainGbmQuantileCommand], TrainGbmQuantileResult],
        train_tft: Callable[[TrainTftCommand], TrainTftResult],
        modeling_columns: Sequence[str],
        observed_feature_set_hash: str,
        pipeline_version: str,
        schema_version: int,
    ) -> None:
        self._store = store
        self._hasher = hasher
        self._clock = clock
        self._ledger = ledger
        self._run_index = run_index
        self._probe = probe
        self._run_baselines = run_baselines
        self._train_gbm = train_gbm
        self._train_tft = train_tft
        self._modeling_columns = tuple(modeling_columns)
        self._observed_feature_set_hash = observed_feature_set_hash
        self._pipeline_version = pipeline_version
        self._schema_version = schema_version

    def __call__(self, command: RunConfirmatoryCohortCommand) -> RunConfirmatoryCohortResult:
        spec = command.spec
        if not spec.is_frozen():
            raise CohortNotFrozenError(
                f"cohort {spec.name!r} r{spec.revision} is not frozen — run sweep and "
                "freeze first (seeds, n_trials, params, provenance and dataset fingerprint)"
            )
        cohort_hash = CohortHash.compute(hasher=self._hasher, payload=spec.hash_payload())
        cohort_id = spec.cohort_id(cohort_hash)
        scope = spec.scope(cohort_id)

        self._ledger.acquire_writer()
        try:
            self._check_declarations(spec)
            self._check_environment(cohort_id)
            outcomes = tuple(
                self._run_unit(spec, scope, cohort_id, unit) for unit in self._units(spec, scope)
            )
        finally:
            self._ledger.release_writer()
        return RunConfirmatoryCohortResult(
            cohort_id=cohort_id, cohort_hash=cohort_hash.value, outcomes=outcomes
        )

    # -- pré-condições ----------------------------------------------------------

    def _check_declarations(self, spec: CohortSpec) -> None:
        """I4 + geometria: o dado e o código de agora são os que o spec declara."""
        rows = self._store.read(
            layer=_DATASET_LAYER, table=_DATASET_TABLE, filters={"asset": spec.asset_id}
        )
        grid = build_training_grid(rows, columns=self._modeling_columns)
        observed = grid_fingerprint(grid, hasher=self._hasher, asset_id=spec.asset_id)
        if observed != spec.dataset_fingerprint:
            raise DatasetMismatchError(
                f"dataset fingerprint {observed[:12]} != declared "
                f"{str(spec.dataset_fingerprint)[:12]} — the materialized data changed"
            )
        provenance = spec.provenance
        if provenance is None or provenance.dataset_fingerprint != spec.dataset_fingerprint:
            raise CohortDeclarationMismatchError(
                "sweeps ran on a different dataset than the one declared for the run"
            )
        if spec.feature_set_hash != self._observed_feature_set_hash:
            raise CohortDeclarationMismatchError(
                f"feature_set_hash {spec.feature_set_hash[:12]} != registry "
                f"{self._observed_feature_set_hash[:12]}"
            )
        if spec.pipeline_version != self._pipeline_version:
            raise CohortDeclarationMismatchError(
                f"pipeline_version {spec.pipeline_version!r} != code {self._pipeline_version!r}"
            )
        spec.geometry.fits(n_sessions=len(grid.timestamps), max_horizon=spec.max_horizon)

    def _check_environment(self, cohort_id: str) -> None:
        """I5: árvore limpa sempre; ambiente gravado na 1ª vez e igual nas seguintes."""
        snapshot = dict(self._probe.snapshot())
        if snapshot.get(DIRTY_KEY) == "true":
            raise EnvironmentMismatchError(
                "tracked uncommitted changes in src/, uv.lock or the cohort file — commit first"
            )
        recorded = self._ledger.environment(cohort_id)
        if recorded is None:
            self._ledger.record_environment(
                cohort_id, snapshot, started_at=self._clock.now().isoformat()
            )
            return
        differing = sorted(
            key for key in set(recorded) | set(snapshot) if recorded.get(key) != snapshot.get(key)
        )
        if differing:
            raise EnvironmentMismatchError(
                f"environment differs from the first run on {differing} — resume refused"
            )

    # -- unidades -----------------------------------------------------------------

    def _units(self, spec: CohortSpec, scope: ScopeSpec) -> list[_Unit]:
        geometry = spec.geometry
        common = {
            "scope": scope,
            "horizons": spec.horizons,
            "quantile_levels": spec.quantile_levels,
            "n_folds": geometry.n_folds,
            "test_size": geometry.test_size,
            "val_size": geometry.val_size,
            "calib_size": geometry.calib_size,
            "embargo": geometry.embargo,
            "schema_version": self._schema_version,
        }
        gbm_params = spec.gbm_params
        tft_params = spec.tft_params
        assert gbm_params is not None and tft_params is not None  # is_frozen garante

        def baselines() -> Mapping[str, int]:
            result = self._run_baselines(
                RunBaselinesCommand(specs=spec.baseline_specs, **common)  # type: ignore[arg-type]
            )
            return {run.run_id: run.rows_written for run in result.runs}

        def gbm() -> Mapping[str, int]:
            result = self._train_gbm(TrainGbmQuantileCommand(params=gbm_params, **common))  # type: ignore[arg-type]
            return {run.run_id: run.rows_written for run in result.runs}

        def tft(seed: int) -> Callable[[], Mapping[str, int]]:
            def execute() -> Mapping[str, int]:
                params = replace(tft_params, seed=seed)
                result = self._train_tft(TrainTftCommand(params=params, **common))  # type: ignore[arg-type]
                return {run.run_id: run.rows_written for run in result.runs}

            return execute

        units = [
            _Unit(
                key="baselines",
                model_keys=tuple(
                    (f"{BASELINE_MODEL_VERSION_PREFIX}{b.family}", None)
                    for b in spec.baseline_specs
                ),
                execute=baselines,
            ),
            _Unit(key="gbm", model_keys=((GBM_MODEL_VERSION, gbm_params.seed),), execute=gbm),
        ]
        units += [
            _Unit(
                key=f"tft:seed={seed}",
                model_keys=((TFT_MODEL_VERSION, seed),),
                execute=tft(seed),
            )
            for seed in spec.seeds
        ]
        return units

    def _run_unit(
        self, spec: CohortSpec, scope: ScopeSpec, cohort_id: str, unit: _Unit
    ) -> CohortUnitOutcome:
        recorded = self._run_index.recorded_runs(
            asset_id=spec.asset_id, feature_set_name=spec.feature_set_name, cohort_id=cohort_id
        )
        runs = {
            run_id: summary
            for model_key in unit.model_keys
            for run_id, summary in recorded.get(model_key, {}).items()
        }
        completed = self._ledger.completed_units(cohort_id)
        if unit.key in completed:
            marked = completed[unit.key]
            for run_id, rows in marked.items():
                if run_id not in runs or runs[run_id][1] != rows:
                    raise CompletedUnitCorruptedError(
                        f"unit {unit.key!r}: run {run_id} has "
                        f"{runs[run_id][1] if run_id in runs else 'no'} rows in silver, "
                        f"ledger says {rows}"
                    )
            return CohortUnitOutcome(
                unit_key=unit.key,
                status=_SKIPPED,
                run_ids=tuple(sorted(marked)),
                rows_written=0,
            )

        if runs and any(summary[1] > 0 for summary in runs.values()):
            if self._is_complete(spec, unit, runs):
                rows_by_run = {run_id: summary[1] for run_id, summary in runs.items()}
                self._ledger.mark_completed(cohort_id, unit.key, rows_by_run)
                return CohortUnitOutcome(
                    unit_key=unit.key,
                    status=_VERIFIED,
                    run_ids=tuple(sorted(rows_by_run)),
                    rows_written=0,
                )
            raise PartialCohortUnitError(
                f"unit {unit.key!r} of cohort {cohort_id} is partially persisted in silver "
                "— start a new cohort revision (revision += 1)"
            )

        rows_by_run = dict(unit.execute())
        self._ledger.mark_completed(cohort_id, unit.key, rows_by_run)
        return CohortUnitOutcome(
            unit_key=unit.key,
            status=_RAN,
            run_ids=tuple(sorted(rows_by_run)),
            rows_written=sum(rows_by_run.values()),
        )

    @staticmethod
    def _is_complete(
        spec: CohortSpec,
        unit: _Unit,
        runs: Mapping[str, tuple[str, int, Mapping[int, frozenset[str]]]],
    ) -> bool:
        geometry = spec.geometry
        if len(runs) != geometry.expected_runs(runs_per_fold=len(unit.model_keys)):
            return False
        n_levels = len(spec.quantile_levels)
        return all(
            rows
            == geometry.expected_prediction_rows(
                fold_index=int(fold), horizons=spec.horizons, n_levels=n_levels
            )
            for fold, rows, _ in runs.values()
        )
