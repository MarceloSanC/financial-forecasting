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

`cohort_model_keys` e `load_training_grid` são públicos para o comando `verify`
e o `freeze` do CLI usarem a MESMA enumeração de modelos e a MESMA leitura do
grid que a corrida — uma fonte só. Pelo mesmo motivo, `check_cohort_declarations`
(I4 + geometria) e `tft_train_command` (o `TrainTftCommand` de uma seed) são
públicos para a predição a partir do checkpoint (Stage 7.1, ADR 7.1.0001 item 2)
conferir as declarações e reconstruir a identidade do run sem recopiá-las.

**Stage 7.3 (ADR 7.3.0003 item 3):** o lock, o ambiente, a classificação das
unidades, as exceções, `load_training_grid`, `check_cohort_declarations` e
`recorded_run_problems` moram em `cohort_unit_runner`, compartilhado com o executor
de ablação. Este módulo os reexporta (os importadores da 5.5/7.1 ficam intocados) e
define só a lista de unidades e as pré-condições do cohort confirmatório.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from financial_forecasting.features.modeling.application.use_cases.cohort_unit_runner import (
    CohortDeclarationMismatchError,
    CohortNotFrozenError,
    CohortUnitOutcome,
    CompletedUnitCorruptedError,
    DatasetMismatchError,
    EnvironmentMismatchError,
    PartialCohortUnitError,
    UnitOutputMismatchError,
    UnitPlan,
    check_cohort_declarations,
    check_environment,
    classify_and_run,
    load_training_grid,
    recorded_run_problems,
    writer_lock,
)
from financial_forecasting.features.modeling.application.use_cases.run_baselines import (
    RunBaselinesCommand,
    RunBaselinesResult,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    MODEL_VERSION as GBM_USE_CASE_MODEL_VERSION,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    TrainGbmQuantileCommand,
    TrainGbmQuantileResult,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    MODEL_VERSION as TFT_USE_CASE_MODEL_VERSION,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    TrainTftCommand,
    TrainTftResult,
)
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash

if TYPE_CHECKING:
    from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec
    from financial_forecasting.features.modeling.application.ports.out.cohort_progress_ledger import (  # noqa: E501
        CohortProgressLedger,
    )
    from financial_forecasting.features.modeling.application.ports.out.cohort_run_index import (
        CohortRunIndex,
        RunSummary,
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

# Reexportados da máquina compartilhada (Stage 7.3): os importadores da 5.5/7.1 seguem
# importando daqui.
__all__ = [
    "GBM_MODEL_VERSION",
    "TFT_MODEL_VERSION",
    "CohortDeclarationMismatchError",
    "CohortNotFrozenError",
    "CohortUnitOutcome",
    "CompletedUnitCorruptedError",
    "DatasetMismatchError",
    "EnvironmentMismatchError",
    "PartialCohortUnitError",
    "RunConfirmatoryCohort",
    "RunConfirmatoryCohortCommand",
    "RunConfirmatoryCohortResult",
    "UnitOutputMismatchError",
    "check_cohort_declarations",
    "cohort_model_keys",
    "load_training_grid",
    "recorded_run_problems",
    "tft_train_command",
]

# `model_version` que o GBM e o TFT gravam — o dono é o use case de cada um; o dos
# baselines vem de `BaselineSpec.model_version`.
GBM_MODEL_VERSION = GBM_USE_CASE_MODEL_VERSION
TFT_MODEL_VERSION = TFT_USE_CASE_MODEL_VERSION


@dataclass(frozen=True)
class RunConfirmatoryCohortCommand:
    """DTO de entrada — o spec congelado do cohort.

    `break_stale_lock` remove um lock órfão (processo morto) antes de adquirir —
    decisão explícita do operador (`--break-stale-lock`), nunca automática.
    """

    spec: CohortSpec
    break_stale_lock: bool = False


@dataclass(frozen=True)
class RunConfirmatoryCohortResult:
    """DTO de saída — identidade do cohort e o desfecho de cada unidade."""

    cohort_id: str
    cohort_hash: str
    outcomes: tuple[CohortUnitOutcome, ...]


def _tft_unit(seed: int) -> str:
    return f"tft:seed={seed}"


def cohort_model_keys(spec: CohortSpec) -> dict[str, tuple[tuple[str, int | None], ...]]:
    """Unidade → `(model_version, seed)` que ela grava, na ordem da corrida.

    Baselines não têm seed (`None`); o GBM usa a seed dos seus params congelados;
    cada seed do TFT é uma unidade. Exige o spec congelado (`gbm_params`).
    """
    gbm_params = spec.gbm_params
    if gbm_params is None:
        raise CohortNotFrozenError(f"cohort {spec.name!r} has no frozen gbm_params")
    keys: dict[str, tuple[tuple[str, int | None], ...]] = {
        "baselines": tuple((b.model_version, None) for b in spec.baseline_specs),
        "gbm": ((GBM_MODEL_VERSION, gbm_params.seed),),
    }
    for seed in spec.seeds:
        keys[_tft_unit(seed)] = ((TFT_MODEL_VERSION, seed),)
    return keys


def tft_train_command(
    spec: CohortSpec, *, scope: ScopeSpec, seed: int, schema_version: int
) -> TrainTftCommand:
    """O `TrainTftCommand` da unidade `tft:seed=<seed>` — params congelados com a seed.

    Campos nomeados um a um (sem `**dict`): o mypy confere nome e tipo, e uma
    troca val_size/calib_size não passa despercebida. Exige o spec congelado.
    """
    tft_params = spec.tft_params
    if tft_params is None:
        raise CohortNotFrozenError(f"cohort {spec.name!r} has no frozen tft_params")
    geometry = spec.geometry
    return TrainTftCommand(
        params=replace(tft_params, seed=seed),
        scope=scope,
        horizons=spec.horizons,
        quantile_levels=spec.quantile_levels,
        n_folds=geometry.n_folds,
        test_size=geometry.test_size,
        val_size=geometry.val_size,
        calib_size=geometry.calib_size,
        embargo=geometry.embargo,
        schema_version=schema_version,
    )


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
        supported_device: str,
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
        self._supported_device = supported_device

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

        with writer_lock(self._ledger, break_stale=command.break_stale_lock):
            self._check_declarations(spec)
            check_environment(self._ledger, self._probe, cohort_id, clock=self._clock)
            outcomes = tuple(
                classify_and_run(
                    unit,
                    spec=spec,
                    cohort_id=cohort_id,
                    ledger=self._ledger,
                    recorded=lambda: self._recorded(spec, cohort_id),
                )
                for unit in self._units(spec, scope)
            )
        return RunConfirmatoryCohortResult(
            cohort_id=cohort_id, cohort_hash=cohort_hash.value, outcomes=outcomes
        )

    # -- pré-condições ----------------------------------------------------------

    def _check_declarations(self, spec: CohortSpec) -> None:
        """I4 + geometria — delega a `check_cohort_declarations`."""
        check_cohort_declarations(
            spec,
            store=self._store,
            hasher=self._hasher,
            modeling_columns=self._modeling_columns,
            observed_feature_set_hash=self._observed_feature_set_hash,
            pipeline_version=self._pipeline_version,
            supported_device=self._supported_device,
        )

    # -- unidades -----------------------------------------------------------------

    def _units(self, spec: CohortSpec, scope: ScopeSpec) -> list[UnitPlan]:
        geometry = spec.geometry
        gbm_params = spec.gbm_params
        assert gbm_params is not None  # is_frozen garante
        model_keys = cohort_model_keys(spec)
        # Campos nomeados um a um (sem `**dict`): o mypy confere nome e tipo, e
        # uma troca val_size/calib_size não passa despercebida.

        def baselines() -> Mapping[str, int]:
            result = self._run_baselines(
                RunBaselinesCommand(
                    specs=spec.baseline_specs,
                    scope=scope,
                    horizons=spec.horizons,
                    quantile_levels=spec.quantile_levels,
                    n_folds=geometry.n_folds,
                    test_size=geometry.test_size,
                    val_size=geometry.val_size,
                    calib_size=geometry.calib_size,
                    embargo=geometry.embargo,
                    schema_version=self._schema_version,
                )
            )
            return {run.run_id: run.rows_written for run in result.runs}

        def gbm() -> Mapping[str, int]:
            result = self._train_gbm(
                TrainGbmQuantileCommand(
                    params=gbm_params,
                    scope=scope,
                    horizons=spec.horizons,
                    quantile_levels=spec.quantile_levels,
                    n_folds=geometry.n_folds,
                    test_size=geometry.test_size,
                    val_size=geometry.val_size,
                    calib_size=geometry.calib_size,
                    embargo=geometry.embargo,
                    schema_version=self._schema_version,
                )
            )
            return {run.run_id: run.rows_written for run in result.runs}

        def tft(seed: int) -> Callable[[], Mapping[str, int]]:
            def execute() -> Mapping[str, int]:
                result = self._train_tft(
                    tft_train_command(
                        spec, scope=scope, seed=seed, schema_version=self._schema_version
                    )
                )
                return {run.run_id: run.rows_written for run in result.runs}

            return execute

        units = [
            UnitPlan(key="baselines", model_keys=model_keys["baselines"], execute=baselines),
            UnitPlan(key="gbm", model_keys=model_keys["gbm"], execute=gbm),
        ]
        units += [
            UnitPlan(key=_tft_unit(seed), model_keys=model_keys[_tft_unit(seed)], execute=tft(seed))
            for seed in spec.seeds
        ]
        return units

    def _recorded(
        self, spec: CohortSpec, cohort_id: str
    ) -> Mapping[tuple[str, int | None], Mapping[str, RunSummary]]:
        return self._run_index.recorded_runs(
            asset_id=spec.asset_id, feature_set_name=spec.feature_set_name, cohort_id=cohort_id
        )
