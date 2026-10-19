"""Use case `RunAblationCohort` — corrida retomável do cohort de ablação LOCO (Stage 7.3).

Executa as unidades de um cohort de ablação CONGELADO: uma unidade
`tft:<configuração>:seed=<s>` por configuração (de fora) e seed (de dentro), na ordem
do spec, todas chamando o `TrainTft` com a identidade da configuração
(`excluded_family`, `model_version`), o `feature_set_name` da ablação e o
`parent_sweep_id` = `cohort_id` da ablação (concept 7.3 §1 item 3, I2-I5; ADR
7.3.0003 item 3). O procedimento (geometria, `tft_params`, horizontes, grade) vem do
spec confirmatório de base, nunca do arquivo de ablação (I4).

Antes de treinar qualquer coisa, na ordem:

1. spec de ablação congelado (seeds e `torch_build`) e base congelada
   (`CohortNotFrozenError`) — antes do lock e do probe (C3);
2. lock de escritor único (I12, liberado em `finally`);
3. declarações da BASE (`check_cohort_declarations`, com o device da base: a base
   `cpu` passa com a ablação em `rocm`);
4. guarda de hardware observado (I5, ADR 7.3.0004 item 3): fora do `cpu`, GPU
   disponível e HIP não vazio; em qualquer device, a chave `torch` do probe igual ao
   `torch_build` declarado (`EnvironmentMismatchError`);
5. ambiente gravado na 1ª execução e igual nas seguintes (I5).

A classificação por unidade (ledger, silver completo, parcial, ausente) é a da máquina
compartilhada `cohort_unit_runner`. Este módulo nunca importa o executor confirmatório,
e vice-versa (guarda AST da Stage 7.3).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    CPU_DEVICE,
    GPU_KEYS,
)
from financial_forecasting.features.modeling.application.use_cases.cohort_unit_runner import (
    CohortNotFrozenError,
    CohortUnitOutcome,
    EnvironmentMismatchError,
    RecordedRuns,
    UnitPlan,
    check_cohort_declarations,
    check_environment,
    classify_and_run,
    writer_lock,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    TrainTftCommand,
    TrainTftResult,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import ScopeSpec
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash

if TYPE_CHECKING:
    from financial_forecasting.features.modeling.application.dtos.ablation_cohort_spec import (
        AblationCohortSpec,
        AblationConfiguration,
    )
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
    from financial_forecasting.shared.application.ports.out.clock import Clock
    from financial_forecasting.shared.application.ports.out.hasher import Hasher
    from financial_forecasting.shared.application.ports.out.medallion_store import (
        MedallionStore,
    )

_TORCH_KEY = "torch"


def ablation_unit_key(configuration: str, seed: int) -> str:
    """Chave da unidade: `tft:<configuração>:seed=<s>`."""
    return f"tft:{configuration}:seed={seed}"


def ablation_model_keys(spec: AblationCohortSpec) -> dict[str, tuple[tuple[str, int | None], ...]]:
    """Unidade → `(model_version, seed)` que ela grava, na ordem da corrida."""
    return {
        ablation_unit_key(configuration.name, seed): ((configuration.model_version, seed),)
        for configuration in spec.configurations
        for seed in spec.seeds
    }


@dataclass(frozen=True)
class RunAblationCohortCommand:
    """DTO de entrada — o spec de ablação congelado e o spec confirmatório de base.

    `break_stale_lock` remove um lock órfão (processo morto) antes de adquirir —
    decisão explícita do operador (`--break-stale-lock`), nunca automática.
    """

    spec: AblationCohortSpec
    base: CohortSpec
    break_stale_lock: bool = False


@dataclass(frozen=True)
class RunAblationCohortResult:
    """DTO de saída — identidade do cohort de ablação e o desfecho de cada unidade."""

    cohort_id: str
    cohort_hash: str
    outcomes: tuple[CohortUnitOutcome, ...]


class RunAblationCohort:
    """Orquestra a corrida do cohort de ablação congelado, retomável por unidade."""

    def __init__(  # noqa: PLR0913 — portas e use case coesos da orquestração
        self,
        *,
        store: MedallionStore,
        hasher: Hasher,
        clock: Clock,
        ledger: CohortProgressLedger,
        run_index: CohortRunIndex,
        probe: RuntimeEnvironmentProbe,
        train_tft: Callable[[TrainTftCommand], TrainTftResult],
        modeling_columns: Sequence[str],
        observed_feature_set_hash: str,
        pipeline_version: str,
        schema_version: int,
        base_supported_device: str,
    ) -> None:
        self._store = store
        self._hasher = hasher
        self._clock = clock
        self._ledger = ledger
        self._run_index = run_index
        self._probe = probe
        self._train_tft = train_tft
        self._modeling_columns = tuple(modeling_columns)
        self._observed_feature_set_hash = observed_feature_set_hash
        self._pipeline_version = pipeline_version
        self._schema_version = schema_version
        self._base_supported_device = base_supported_device

    def __call__(self, command: RunAblationCohortCommand) -> RunAblationCohortResult:
        spec, base = command.spec, command.base
        if not spec.is_frozen():
            raise CohortNotFrozenError(
                f"ablation cohort {spec.name!r} r{spec.revision} is not frozen — run "
                "ablation-freeze first (seeds and torch_build)"
            )
        if not base.is_frozen():
            raise CohortNotFrozenError(f"base cohort {base.name!r} is not frozen")
        cohort_hash = CohortHash.compute(hasher=self._hasher, payload=spec.hash_payload())
        cohort_id = spec.cohort_id(cohort_hash)
        scope = ScopeSpec(
            asset_id=base.asset_id,
            feature_set_name=spec.feature_set_name,
            max_horizon=base.max_horizon,
            cohort_id=cohort_id,
        )

        with writer_lock(self._ledger, break_stale=command.break_stale_lock):
            check_cohort_declarations(
                base,
                store=self._store,
                hasher=self._hasher,
                modeling_columns=self._modeling_columns,
                observed_feature_set_hash=self._observed_feature_set_hash,
                pipeline_version=self._pipeline_version,
                supported_device=self._base_supported_device,
            )
            self._check_hardware(spec)
            check_environment(self._ledger, self._probe, cohort_id, clock=self._clock)
            outcomes = tuple(
                classify_and_run(
                    unit,
                    spec=base,
                    cohort_id=cohort_id,
                    ledger=self._ledger,
                    recorded=lambda: self._recorded(base, spec, cohort_id),
                )
                for unit in self._units(spec, base, scope)
            )
        return RunAblationCohortResult(
            cohort_id=cohort_id, cohort_hash=cohort_hash.value, outcomes=outcomes
        )

    # -- pré-condições ----------------------------------------------------------

    def _check_hardware(self, spec: AblationCohortSpec) -> None:
        """I5: o hardware e o build OBSERVADOS são os declarados, antes de treinar."""
        snapshot = dict(self._probe.snapshot())
        problems: list[str] = []
        if spec.device != CPU_DEVICE:
            available_key, _, hip_key = GPU_KEYS
            if snapshot.get(available_key) != "true":
                problems.append(f"device {spec.device!r} declared, but no GPU is available")
            if not snapshot.get(hip_key):
                problems.append(f"device {spec.device!r} declared, but torch has no HIP build")
        if snapshot.get(_TORCH_KEY) != spec.torch_build:
            problems.append(
                f"torch {snapshot.get(_TORCH_KEY)!r} installed, but torch_build "
                f"{spec.torch_build!r} declared"
            )
        if problems:
            raise EnvironmentMismatchError("; ".join(problems) + " — ablation run refused")

    # -- unidades -----------------------------------------------------------------

    def _train_command(
        self, base: CohortSpec, configuration: AblationConfiguration, *, scope: ScopeSpec, seed: int
    ) -> TrainTftCommand:
        """O `TrainTftCommand` da unidade: procedimento da base, identidade da configuração.

        Campos nomeados um a um (sem `**dict`): o mypy confere nome e tipo.
        """
        tft_params = base.tft_params
        if tft_params is None:
            raise CohortNotFrozenError(f"base cohort {base.name!r} has no frozen tft_params")
        geometry = base.geometry
        return TrainTftCommand(
            params=replace(tft_params, seed=seed),
            scope=scope,
            horizons=base.horizons,
            quantile_levels=base.quantile_levels,
            n_folds=geometry.n_folds,
            test_size=geometry.test_size,
            val_size=geometry.val_size,
            calib_size=geometry.calib_size,
            embargo=geometry.embargo,
            schema_version=self._schema_version,
            excluded_family=configuration.excluded_family,
            model_version=configuration.model_version,
        )

    def _units(
        self, spec: AblationCohortSpec, base: CohortSpec, scope: ScopeSpec
    ) -> list[UnitPlan]:
        model_keys = ablation_model_keys(spec)

        def unit(configuration: AblationConfiguration, seed: int) -> UnitPlan:
            def execute() -> Mapping[str, int]:
                result = self._train_tft(
                    self._train_command(base, configuration, scope=scope, seed=seed)
                )
                return {run.run_id: run.rows_written for run in result.runs}

            key = ablation_unit_key(configuration.name, seed)
            return UnitPlan(key=key, execute=execute, model_keys=model_keys[key])

        return [
            unit(configuration, seed)
            for configuration in spec.configurations
            for seed in spec.seeds
        ]

    def _recorded(self, base: CohortSpec, spec: AblationCohortSpec, cohort_id: str) -> RecordedRuns:
        return self._run_index.recorded_runs(
            asset_id=base.asset_id, feature_set_name=spec.feature_set_name, cohort_id=cohort_id
        )
