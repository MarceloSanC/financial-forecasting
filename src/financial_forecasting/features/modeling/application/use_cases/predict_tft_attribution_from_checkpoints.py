"""Use case `PredictTftAttributionFromCheckpoints` — predições de atribuição (Stage 7.3).

Fornecedor do port `CheckpointAttributionPredictor` do slice `inference` (ADR 7.3.0002
item 1). Espelha o `PredictTftFromCheckpoints` da 7.1: para uma seed do cohort
confirmatório congelado, reconstrói os folds e a identidade de cada run exatamente como
o treino (mesmas funções públicas), confere a lista permitida e o sha256, e pede ao
`TftCheckpointPredictor` a identidade, as predições permutadas por (família, k) e os
pesos da VSN das decisões de teste do fold.

Guardas, antes de qualquer predição (concept 7.3 §4, I8; C1, C5, C7):

- spec congelado e seed declarada (`require_frozen_seed`), `num_threads >= 1`;
- **partição = a da registry injetada** (`registry_partition`): a partição do comando é
  a que o hash de H3 identifica (ADR 7.3.0002 item 1) — senão
  `FamilyPartitionMismatchError`;
- `check_cohort_declarations` da base (I4);
- **I8** — toda coluna de família está no painel e é `unknown` (não `known`), senão
  `FamilyFeatureKnownError` (o adapter confere de novo contra o checkpoint, C5);
- `run_id` de cada fold na lista permitida (`UnknownRunError`) e sha256 localizado =
  o permitido (`ArtifactChangedError`, C7);
- **doadores**: por fold, K_p permutações (o mesmo K_p em todo fold) de
  `range(n_decisões)`; as posições indexam as decisões de teste do fold que têm
  emissão, em ordem crescente (`ValueError`, C1);
- emissão só nos pares pedidos (`assert_emission_within_request`), na identidade e em
  toda permutada.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from financial_forecasting.features.modeling.application.ports.out.tft_checkpoint_predictor import (
    ArtifactChangedError,
    FamilyFeatureKnownError,
    check_donors,
)
from financial_forecasting.features.modeling.application.use_cases.cohort_unit_runner import (
    check_cohort_declarations,
)
from financial_forecasting.features.modeling.application.use_cases.predict_tft_from_checkpoints import (  # noqa: E501
    UnknownRunError,
)
from financial_forecasting.features.modeling.application.use_cases.resolve_tft_checkpoints import (
    cohort_tft_folds,
    require_frozen_seed,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    assert_emission_within_request,
    load_tft_panel,
    tft_artifact_dir,
    tft_run_identity,
)
from financial_forecasting.shared.application.exceptions import ApplicationError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec
    from financial_forecasting.features.modeling.application.ports.out.checkpoint_locator import (
        CheckpointLocator,
    )
    from financial_forecasting.features.modeling.application.ports.out.tft_checkpoint_predictor import (  # noqa: E501
        TftCheckpointPredictor,
    )
    from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
        WalkForwardSplitter,
    )
    from financial_forecasting.shared.application.ports.out.hasher import Hasher
    from financial_forecasting.shared.application.ports.out.medallion_store import (
        MedallionStore,
    )

Grids = Mapping[int, Mapping[int, tuple[float, ...]]]


class FamilyPartitionMismatchError(ApplicationError):
    """A partição de famílias do comando difere da partição da registry (CA9)."""


@dataclass(frozen=True)
class PredictTftAttributionCommand:
    """DTO de entrada — seed, lista permitida, threads, doadores por fold e partição."""

    spec: CohortSpec
    seed: int
    allowed: Mapping[str, str]
    num_threads: int
    donors_by_fold: Mapping[int, tuple[tuple[int, ...], ...]]
    family_partition: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class AttributionRunPrediction:
    """Identidade, permutadas e VSN de um run, nas decisões de teste com emissão."""

    run_id: str
    fold_index: int
    checkpoint_sha256: str
    normalizer_center: float
    normalizer_scale: float
    test_decisions: tuple[int, ...]
    family_columns: Mapping[str, tuple[str, ...]]
    identity: Grids
    permuted: Mapping[tuple[str, int], Grids]
    encoder_weights: Mapping[int, Mapping[str, float]]


@dataclass(frozen=True)
class PredictTftAttributionResult:
    """DTO de saída — grade de pregão, parâmetros da inferência e um item por fold."""

    cohort_id: str
    seed: int
    dataset_timestamps: tuple[str, ...]
    settings: Mapping[str, str]
    runs: tuple[AttributionRunPrediction, ...]


def _frozen_grids(
    grids: Mapping[int, Mapping[int, Sequence[float]]],
) -> dict[int, dict[int, tuple[float, ...]]]:
    return {
        decision: {h: tuple(grid) for h, grid in by_horizon.items()}
        for decision, by_horizon in grids.items()
    }


class PredictTftAttributionFromCheckpoints:
    """Prediz a atribuição a partir dos checkpoints da seed (identidade, permutadas, VSN)."""

    def __init__(  # noqa: PLR0913 — portas e declarações conferidas (concept §4)
        self,
        *,
        store: MedallionStore,
        hasher: Hasher,
        splitter: WalkForwardSplitter,
        locator: CheckpointLocator,
        predictor: TftCheckpointPredictor,
        artifacts_root: Path,
        modeling_columns: Sequence[str],
        observed_feature_set_hash: str,
        pipeline_version: str,
        supported_device: str,
        registry_partition: Mapping[str, tuple[str, ...]],
    ) -> None:
        self._store = store
        self._hasher = hasher
        self._splitter = splitter
        self._locator = locator
        self._predictor = predictor
        self._artifacts_root = artifacts_root
        self._modeling_columns = tuple(modeling_columns)
        self._observed_feature_set_hash = observed_feature_set_hash
        self._pipeline_version = pipeline_version
        self._supported_device = supported_device
        self._registry_partition = {f: tuple(v) for f, v in registry_partition.items()}

    def __call__(self, command: PredictTftAttributionCommand) -> PredictTftAttributionResult:
        spec = command.spec
        require_frozen_seed(spec, command.seed)
        if command.num_threads < 1:
            raise ValueError(f"num_threads must be >= 1; got {command.num_threads}")
        partition = {f: tuple(v) for f, v in command.family_partition.items()}
        if partition != self._registry_partition:
            raise FamilyPartitionMismatchError(
                "the command's family partition differs from the registry's — the H3 "
                "partition hash would not identify what was permuted (CA9)"
            )
        check_cohort_declarations(
            spec,
            store=self._store,
            hasher=self._hasher,
            modeling_columns=self._modeling_columns,
            observed_feature_set_hash=self._observed_feature_set_hash,
            pipeline_version=self._pipeline_version,
            supported_device=self._supported_device,
        )
        panel = load_tft_panel(store=self._store, asset_id=spec.asset_id)
        unknown = set(panel.feature_names) - set(panel.known_feature_names)
        offending = sorted(
            name for names in partition.values() for name in names if name not in unknown
        )
        if offending:
            raise FamilyFeatureKnownError(
                f"family columns {offending} are not unknown reals of the panel (I8)"
            )
        cohort_id, _, train_command, folds = cohort_tft_folds(
            spec,
            seed=command.seed,
            panel_sessions=panel.sessions,
            splitter=self._splitter,
            hasher=self._hasher,
        )
        run_ids = [
            tft_run_identity(
                command=train_command,
                feature_names=panel.feature_names,
                known_names=panel.known_feature_names,
                fold=fold,
                hasher=self._hasher,
            )[1]
            for fold in folds
        ]
        unknown_runs = [run_id for run_id in run_ids if run_id not in command.allowed]
        if unknown_runs:
            raise UnknownRunError(
                f"runs {unknown_runs} of cohort {cohort_id} seed {command.seed} are not in the "
                "allowed list — nothing was loaded (C6)"
            )

        index_by_session = {day.isoformat(): idx for idx, day in enumerate(panel.sessions)}
        last = len(panel.target) - 1
        first_horizon = min(spec.horizons)
        decisions_by_fold: dict[int, tuple[int, ...]] = {}
        k_p: int | None = None
        for fold in folds:
            decisions = tuple(
                sorted(
                    index_by_session[day]
                    for day in fold.test
                    if index_by_session[day] + first_horizon <= last
                )
            )
            donors = command.donors_by_fold.get(fold.fold_index)
            if donors is None:
                raise ValueError(f"no donors for fold {fold.fold_index} (C1)")
            check_donors(donors, n_decisions=len(decisions))
            if k_p is not None and len(donors) != k_p:
                raise ValueError(
                    f"fold {fold.fold_index} has {len(donors)} permutations, expected {k_p} (C1)"
                )
            k_p = len(donors)
            decisions_by_fold[fold.fold_index] = decisions

        batch_size = train_command.params.batch_size
        settings: Mapping[str, str] | None = None
        runs: list[AttributionRunPrediction] = []
        for fold, run_id in zip(folds, run_ids, strict=True):
            expected_sha256 = command.allowed[run_id]
            location = self._locator.locate(
                artifact_dir=str(tft_artifact_dir(self._artifacts_root, run_id))
            )
            if location.sha256 != expected_sha256:
                raise ArtifactChangedError(
                    f"run {run_id}: checkpoint sha256 {location.sha256[:12]} != expected "
                    f"{expected_sha256[:12]} — not loaded (C10)"
                )
            decisions = decisions_by_fold[fold.fold_index]
            prediction = self._predictor.predict_attribution_from_checkpoint(
                checkpoint_path=location.path,
                expected_sha256=expected_sha256,
                feature_names=panel.feature_names,
                known_feature_names=panel.known_feature_names,
                rows=panel.rows,
                target=panel.target,
                decision_indices=decisions,
                max_horizon=spec.max_horizon,
                horizons=spec.horizons,
                quantile_levels=spec.quantile_levels,
                batch_size=batch_size,
                num_threads=command.num_threads,
                permuted_columns=partition,
                donors=command.donors_by_fold[fold.fold_index],
            )
            for grids in (prediction.identity, *prediction.permuted.values()):
                assert_emission_within_request(
                    grids=grids,
                    requested_decision_indices=decisions,
                    horizons=spec.horizons,
                    partition="test",
                )
            if settings is None:
                settings = dict(prediction.settings)
            runs.append(
                AttributionRunPrediction(
                    run_id=run_id,
                    fold_index=fold.fold_index,
                    checkpoint_sha256=expected_sha256,
                    normalizer_center=prediction.normalizer_center,
                    normalizer_scale=prediction.normalizer_scale,
                    test_decisions=decisions,
                    family_columns=partition,
                    identity=_frozen_grids(prediction.identity),
                    permuted={key: _frozen_grids(g) for key, g in prediction.permuted.items()},
                    encoder_weights={d: dict(w) for d, w in prediction.encoder_weights.items()},
                )
            )
        return PredictTftAttributionResult(
            cohort_id=cohort_id,
            seed=command.seed,
            dataset_timestamps=panel.timestamps,
            settings=settings or {},
            runs=tuple(runs),
        )
