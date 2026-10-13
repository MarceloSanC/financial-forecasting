"""Use case `ResolveTftCheckpoints` — o checkpoint de cada fold de uma seed, sem carregar (7.1).

Fornecedor do port `CheckpointResolver` do slice `inference` (ADR 7.1.0001; ADR
7.1.0004 item 1). Nada aqui importa a pilha de DL nem desserializa checkpoint:
o `CheckpointLocator` lista o diretório e lê o sha256 por streaming.

Ordem (concept 7.1 §4/§6):

1. **C1** — spec congelado (`CohortNotFrozenError`) e **C13** — `seed` em
   `spec.seeds` (`ValueError`), antes de qualquer I/O;
2. **C2** — declarações do cohort por `check_cohort_declarations` (as mesmas
   exceções da corrida da 5.5);
3. **C14** — completude: os runs TFT de TODAS as seeds do spec gravados no silver
   (`recorded_run_problems`, fonte única de "unidade completa");
   problema → `IncompleteCohortError`;
4. painel por `load_tft_panel`, folds pelo `splitter`, e por fold: o
   `TrainTftCommand` do cohort (`tft_train_command`), a identidade do treino
   (`tft_run_identity`), o diretório pela regra do treino (`tft_artifact_dir`) e
   `locator.locate` (C3 propaga).

Nenhum passo recopia o treino: identidade, painel, diretório e conferências são
as funções públicas do `TrainTft` e do `RunConfirmatoryCohort` (ADR 7.1.0001
item 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    CohortNotFrozenError,
    check_cohort_declarations,
    recorded_run_problems,
    tft_train_command,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    MODEL_VERSION,
    TrainTftCommand,
    load_tft_panel,
    tft_artifact_dir,
    tft_run_identity,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date
    from pathlib import Path

    from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec
    from financial_forecasting.features.modeling.application.ports.out.checkpoint_locator import (
        CheckpointLocator,
    )
    from financial_forecasting.features.modeling.application.ports.out.cohort_run_index import (
        CohortRunIndex,
    )
    from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
        WalkForwardSplitter,
    )
    from financial_forecasting.features.modeling.domain.value_objects.fold_split import FoldSplit
    from financial_forecasting.features.modeling.domain.value_objects.scope_spec import ScopeSpec
    from financial_forecasting.shared.application.ports.out.hasher import Hasher
    from financial_forecasting.shared.application.ports.out.medallion_store import (
        MedallionStore,
    )

# `schema_version` é coluna de `dim_run`, não slot da identidade (ADR 5.2.0004):
# o comando reconstruído só serve à identidade e à geometria dos folds.
_IDENTITY_SCHEMA_VERSION = 0


class IncompleteCohortError(ApplicationError):
    """O silver não tem os runs TFT de todas as seeds do cohort (C14)."""


@dataclass(frozen=True)
class ResolveTftCheckpointsCommand:
    """DTO de entrada — o spec congelado e a seed (∈ `spec.seeds`)."""

    spec: CohortSpec
    seed: int


@dataclass(frozen=True)
class CheckpointResolution:
    """O checkpoint de um fold: identidade do run, caminho e sha256 (streaming)."""

    fold_index: int
    run_id: str
    model_version: str
    checkpoint_path: str
    checkpoint_sha256: str


@dataclass(frozen=True)
class ResolveTftCheckpointsResult:
    """DTO de saída — um `CheckpointResolution` por fold, em ordem de fold."""

    cohort_id: str
    seed: int
    runs: tuple[CheckpointResolution, ...]


def require_frozen_seed(spec: CohortSpec, seed: int) -> None:
    """C1 (spec congelado) e C13 (seed declarada) — antes de qualquer I/O."""
    if not spec.is_frozen():
        raise CohortNotFrozenError(
            f"cohort {spec.name!r} r{spec.revision} is not frozen — nothing to resolve (C1)"
        )
    if seed not in spec.seeds:
        raise ValueError(f"seed {seed} is not one of the cohort seeds {list(spec.seeds)} (C13)")


def cohort_tft_folds(
    spec: CohortSpec,
    *,
    seed: int,
    panel_sessions: Sequence[date],
    splitter: WalkForwardSplitter,
    hasher: Hasher,
) -> tuple[str, ScopeSpec, TrainTftCommand, tuple[FoldSplit, ...]]:
    """`(cohort_id, scope, comando do TFT da seed, folds)` — como a corrida os montou."""
    cohort_id = spec.cohort_id(CohortHash.compute(hasher=hasher, payload=spec.hash_payload()))
    scope = spec.scope(cohort_id)
    command = tft_train_command(
        spec, scope=scope, seed=seed, schema_version=_IDENTITY_SCHEMA_VERSION
    )
    folds = splitter.split(
        tuple(panel_sessions),
        scope,
        n_folds=command.n_folds,
        test_size=command.test_size,
        val_size=command.val_size,
        calib_size=command.calib_size,
        embargo=command.embargo,
        hasher=hasher,
    )
    return cohort_id, scope, command, tuple(folds)


class ResolveTftCheckpoints:
    """Resolve o checkpoint de cada fold de uma seed do cohort, sem carregá-lo."""

    def __init__(  # noqa: PLR0913 — portas e declarações conferidas (concept §4)
        self,
        *,
        store: MedallionStore,
        hasher: Hasher,
        splitter: WalkForwardSplitter,
        run_index: CohortRunIndex,
        locator: CheckpointLocator,
        artifacts_root: Path,
        modeling_columns: Sequence[str],
        observed_feature_set_hash: str,
        pipeline_version: str,
        supported_device: str,
    ) -> None:
        self._store = store
        self._hasher = hasher
        self._splitter = splitter
        self._run_index = run_index
        self._locator = locator
        self._artifacts_root = artifacts_root
        self._modeling_columns = tuple(modeling_columns)
        self._observed_feature_set_hash = observed_feature_set_hash
        self._pipeline_version = pipeline_version
        self._supported_device = supported_device

    def __call__(self, command: ResolveTftCheckpointsCommand) -> ResolveTftCheckpointsResult:
        spec = command.spec
        require_frozen_seed(spec, command.seed)  # C1, C13
        check_cohort_declarations(  # C2
            spec,
            store=self._store,
            hasher=self._hasher,
            modeling_columns=self._modeling_columns,
            observed_feature_set_hash=self._observed_feature_set_hash,
            pipeline_version=self._pipeline_version,
            supported_device=self._supported_device,
        )
        cohort_id = spec.cohort_id(
            CohortHash.compute(hasher=self._hasher, payload=spec.hash_payload())
        )
        self._require_complete(spec, cohort_id)  # C14
        panel = load_tft_panel(store=self._store, asset_id=spec.asset_id)
        _, _, train_command, folds = cohort_tft_folds(
            spec,
            seed=command.seed,
            panel_sessions=panel.sessions,
            splitter=self._splitter,
            hasher=self._hasher,
        )

        resolutions = []
        for fold in folds:
            _, run_id = tft_run_identity(
                command=train_command,
                feature_names=panel.feature_names,
                known_names=panel.known_feature_names,
                fold=fold,
                hasher=self._hasher,
            )
            location = self._locator.locate(
                artifact_dir=str(tft_artifact_dir(self._artifacts_root, run_id))
            )  # C3 propaga
            resolutions.append(
                CheckpointResolution(
                    fold_index=fold.fold_index,
                    run_id=run_id,
                    model_version=MODEL_VERSION,
                    checkpoint_path=location.path,
                    checkpoint_sha256=location.sha256,
                )
            )
        return ResolveTftCheckpointsResult(
            cohort_id=cohort_id, seed=command.seed, runs=tuple(resolutions)
        )

    def _require_complete(self, spec: CohortSpec, cohort_id: str) -> None:
        """C14: os runs TFT de todas as seeds estão no silver, completos."""
        recorded = self._run_index.recorded_runs(
            asset_id=spec.asset_id, feature_set_name=spec.feature_set_name, cohort_id=cohort_id
        )
        problems = recorded_run_problems(
            spec, [(MODEL_VERSION, seed) for seed in spec.seeds], recorded
        )
        if problems:
            raise IncompleteCohortError(
                f"cohort {cohort_id} is incomplete for the TFT seeds — "
                + "; ".join(problems)
                + " (C14)"
            )
