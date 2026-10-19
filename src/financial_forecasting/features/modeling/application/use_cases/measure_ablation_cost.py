"""Use case `MeasureAblationCost` — piloto de custo do cohort de ablação (Stage 7.3).

Treina UMA unidade de referência (configuração `full`, último fold, seed 1) com o
procedimento da base, chamando o port `TftTrainer` direto (nunca o `TrainTft`), e
devolve o custo medido (concept 7.3 D8, CA6; ADR 7.3.0003 item 4). Não persiste nada:
nenhum persister, nenhum ledger, nenhum `dim_run`; o artefato do treino vai para o
diretório do piloto, fora de `artifacts/` (I9). O relatório alimenta a decisão [P]
do número de seeds no Linux (L3).

Dois números por S = 1..10, rotulados de forma diferente de propósito:

- **teto** (`ceiling_seconds`): `5 · n_folds · S · max_epochs · seconds_per_epoch` —
  toda unidade treinando até `max_epochs`, sem parada antecipada;
- **estimativa** (`estimate_seconds`): `5 · n_folds · S · wall_seconds` — toda unidade
  custando o que a unidade piloto custou. Não é teto: o fold do piloto é o mais longo
  (janela expansiva), mas outra seed pode parar mais tarde.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from financial_forecasting.features.modeling.application.dtos.ablation_cohort_spec import (
    ABLATION_CONFIGURATIONS,
)
from financial_forecasting.features.modeling.application.use_cases.cohort_unit_runner import (
    CohortNotFrozenError,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    load_tft_panel,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import ScopeSpec

if TYPE_CHECKING:
    from financial_forecasting.features.modeling.application.dtos.ablation_cohort_spec import (
        AblationCohortSpec,
    )
    from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec
    from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
        RuntimeEnvironmentProbe,
    )
    from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
        TftTrainer,
    )
    from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
        WalkForwardSplitter,
    )
    from financial_forecasting.shared.application.ports.out.clock import Clock
    from financial_forecasting.shared.application.ports.out.hasher import Hasher
    from financial_forecasting.shared.application.ports.out.medallion_store import (
        MedallionStore,
    )

PILOT_CONFIGURATION: Final = "full"
PILOT_SEED: Final = 1
SEED_COUNTS: Final = tuple(range(1, 11))
_PILOT_COHORT_ID = "ablation-pilot"
_TORCH_KEY = "torch"
_DEVICE_KEY = "device"


@dataclass(frozen=True)
class MeasureAblationCostCommand:
    """DTO de entrada — spec de ablação (rascunho basta), base e diretório do piloto."""

    spec: AblationCohortSpec
    base: CohortSpec
    pilot_dir: str


@dataclass(frozen=True)
class AblationCostReport:
    """Custo medido da unidade piloto e a projeção por número de seeds (CA6)."""

    configuration: str
    seed: int
    fold_index: int
    wall_seconds: float
    epochs_run: int
    best_epoch: int
    seconds_per_epoch: float
    max_epochs: int
    device: str
    torch_build: str
    ceiling_seconds: Mapping[int, float]
    estimate_seconds: Mapping[int, float]
    label: str = "ceiling = no early stopping; estimate = every unit costs the pilot (not a bound)"


class MeasureAblationCost:
    """Mede o custo de uma unidade da ablação sem persistir nada."""

    def __init__(  # noqa: PLR0913 — portas coesas do piloto
        self,
        *,
        store: MedallionStore,
        splitter: WalkForwardSplitter,
        trainer: TftTrainer,
        probe: RuntimeEnvironmentProbe,
        clock: Clock,
        hasher: Hasher,
    ) -> None:
        self._store = store
        self._splitter = splitter
        self._trainer = trainer
        self._probe = probe
        self._clock = clock
        self._hasher = hasher

    def __call__(self, command: MeasureAblationCostCommand) -> AblationCostReport:
        base = command.base
        tft_params = base.tft_params
        if tft_params is None:
            raise CohortNotFrozenError(f"base cohort {base.name!r} has no frozen tft_params")
        geometry = base.geometry
        panel = load_tft_panel(store=self._store, asset_id=base.asset_id)
        scope = ScopeSpec(
            asset_id=base.asset_id,
            feature_set_name=command.spec.feature_set_name,
            max_horizon=base.max_horizon,
            cohort_id=_PILOT_COHORT_ID,
        )
        folds = self._splitter.split(
            panel.sessions,
            scope,
            n_folds=geometry.n_folds,
            test_size=geometry.test_size,
            val_size=geometry.val_size,
            calib_size=geometry.calib_size,
            embargo=geometry.embargo,
            hasher=self._hasher,
        )
        fold = folds[-1]  # o fold mais longo da janela expansiva
        index_by_session = {day.isoformat(): idx for idx, day in enumerate(panel.sessions)}
        params = replace(tft_params, seed=PILOT_SEED)

        started = self._clock.now()
        result = self._trainer.train_and_predict(
            params=params,
            feature_names=panel.feature_names,
            known_feature_names=panel.known_feature_names,
            rows=panel.rows,
            target=panel.target,
            train_decision_indices=tuple(index_by_session[day] for day in fold.train),
            early_stop_decision_indices=tuple(index_by_session[day] for day in fold.early_stop),
            test_decision_indices=tuple(index_by_session[day] for day in fold.test),
            max_horizon=base.max_horizon,
            horizons=base.horizons,
            quantile_levels=base.quantile_levels,
            artifact_dir=command.pilot_dir,
        )
        wall_seconds = (self._clock.now() - started).total_seconds()

        snapshot = self._probe.snapshot()
        epochs_run = len(result.val_loss_by_epoch)
        seconds_per_epoch = wall_seconds / epochs_run if epochs_run else 0.0
        units_per_seed = len(ABLATION_CONFIGURATIONS) * geometry.n_folds
        return AblationCostReport(
            configuration=PILOT_CONFIGURATION,
            seed=PILOT_SEED,
            fold_index=fold.fold_index,
            wall_seconds=wall_seconds,
            epochs_run=epochs_run,
            best_epoch=result.best_epoch,
            seconds_per_epoch=seconds_per_epoch,
            max_epochs=tft_params.max_epochs,
            device=snapshot.get(_DEVICE_KEY, ""),
            torch_build=snapshot.get(_TORCH_KEY, ""),
            ceiling_seconds={
                s: units_per_seed * s * tft_params.max_epochs * seconds_per_epoch
                for s in SEED_COUNTS
            },
            estimate_seconds={s: units_per_seed * s * wall_seconds for s in SEED_COUNTS},
        )
