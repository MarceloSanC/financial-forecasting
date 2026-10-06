"""Use case `PredictTftFromCheckpoints` — grade crua de teste/calib dos checkpoints (Stage 7.1).

Fornecedor do port `CheckpointGridPredictor` do slice `inference` (ADR 7.1.0001;
ADR 7.1.0004 item 3). Para uma seed do cohort congelado, reconstrói os folds e a
identidade de cada run exatamente como o treino (funções públicas do `TrainTft`
e do `RunConfirmatoryCohort`) e pede ao `TftCheckpointPredictor` a grade crua das
partições pedidas — `test` (para a reprodução) e/ou `calib`.

Guardas, antes de qualquer predição (concept 7.1 §4/§6):

- **C1/C13** — spec congelado, seed declarada; partições = subconjunto não vazio
  e sem repetição de `("test", "calib")`; `num_threads >= 1` (`ValueError`);
- **C2** — `check_cohort_declarations`;
- **C6** — o `run_id` derivado de CADA fold tem de estar em `allowed`; senão
  `UnknownRunError` e nenhum checkpoint é carregado;
- **C10** — `expected_sha256 = allowed[run_id]`: o adapter confere o sha256 dos
  bytes que carrega;
- **I12** — a emissão só pode conter os pares pedidos
  (`assert_emission_within_request`, nomeando a partição).

O caminho do checkpoint vem do `CheckpointLocator` — a mesma regra (um único
`*.ckpt`) da resolução —, porque o nome do arquivo (`epoch=N-step=M.ckpt`) não é
derivável e a application não lista diretório (LAYOUT §3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from financial_forecasting.features.modeling.application.use_cases.resolve_tft_checkpoints import (
    cohort_tft_folds,
    require_frozen_seed,
)
from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    check_cohort_declarations,
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

PARTITIONS = ("test", "calib")

GridByPartition = Mapping[str, Mapping[int, Mapping[int, tuple[float, ...]]]]


class UnknownRunError(ApplicationError):
    """O `run_id` derivado de um fold não está na lista permitida (C6) — nada foi carregado."""


@dataclass(frozen=True)
class PredictTftFromCheckpointsCommand:
    """DTO de entrada — seed, lista permitida `run_id -> sha256`, partições e threads."""

    spec: CohortSpec
    seed: int
    allowed: Mapping[str, str]
    partitions: tuple[str, ...]
    num_threads: int


@dataclass(frozen=True)
class CheckpointRunPrediction:
    """Grade crua de um run: partição -> decisão -> horizonte -> tupla (níveis do spec)."""

    run_id: str
    fold_index: int
    checkpoint_sha256: str
    normalizer_center: float
    normalizer_scale: float
    grids: GridByPartition


@dataclass(frozen=True)
class PredictTftFromCheckpointsResult:
    """DTO de saída — grade de pregão, parâmetros da inferência e um item por fold."""

    cohort_id: str
    seed: int
    dataset_timestamps: tuple[str, ...]
    settings: Mapping[str, str]
    runs: tuple[CheckpointRunPrediction, ...]


def _validate_request(command: PredictTftFromCheckpointsCommand) -> None:
    partitions = command.partitions
    if not partitions:
        raise ValueError("partitions must be a non-empty subset of ('test', 'calib') (C13)")
    unknown = sorted(set(partitions) - set(PARTITIONS))
    if unknown or len(set(partitions)) != len(partitions):
        raise ValueError(
            f"partitions must be distinct values of {PARTITIONS}; got {partitions!r} (C13)"
        )
    if command.num_threads < 1:
        raise ValueError(f"num_threads must be >= 1; got {command.num_threads}")


class PredictTftFromCheckpoints:
    """Prediz, a partir dos checkpoints da seed, a grade das partições pedidas."""

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

    def __call__(
        self, command: PredictTftFromCheckpointsCommand
    ) -> PredictTftFromCheckpointsResult:
        spec = command.spec
        require_frozen_seed(spec, command.seed)  # C1, C13
        _validate_request(command)
        check_cohort_declarations(  # C2
            spec,
            store=self._store,
            hasher=self._hasher,
            modeling_columns=self._modeling_columns,
            observed_feature_set_hash=self._observed_feature_set_hash,
            pipeline_version=self._pipeline_version,
            supported_device=self._supported_device,
        )
        panel = load_tft_panel(store=self._store, asset_id=spec.asset_id)
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
        unknown = [run_id for run_id in run_ids if run_id not in command.allowed]
        if unknown:  # C6 — antes de qualquer carga
            raise UnknownRunError(
                f"runs {unknown} of cohort {cohort_id} seed {command.seed} are not in the "
                "allowed list — nothing was loaded (C6)"
            )

        index_by_session = {day.isoformat(): idx for idx, day in enumerate(panel.sessions)}
        batch_size = train_command.params.batch_size
        settings: Mapping[str, str] | None = None
        runs: list[CheckpointRunPrediction] = []
        for fold, run_id in zip(folds, run_ids, strict=True):
            expected_sha256 = command.allowed[run_id]
            location = self._locator.locate(
                artifact_dir=str(tft_artifact_dir(self._artifacts_root, run_id))
            )
            grids: dict[str, Mapping[int, Mapping[int, tuple[float, ...]]]] = {}
            center = scale = 0.0
            for partition in command.partitions:
                sessions = fold.test if partition == "test" else fold.calib
                decisions = tuple(index_by_session[day] for day in sessions)
                prediction = self._predictor.predict_from_checkpoint(
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
                )
                assert_emission_within_request(  # I12
                    grids=prediction.grids,
                    requested_decision_indices=decisions,
                    horizons=spec.horizons,
                    partition=partition,
                )
                grids[partition] = {
                    decision: {h: tuple(grid) for h, grid in by_horizon.items()}
                    for decision, by_horizon in prediction.grids.items()
                }
                center, scale = prediction.normalizer_center, prediction.normalizer_scale
                if settings is None:
                    settings = dict(prediction.settings)
            runs.append(
                CheckpointRunPrediction(
                    run_id=run_id,
                    fold_index=fold.fold_index,
                    checkpoint_sha256=expected_sha256,
                    normalizer_center=center,
                    normalizer_scale=scale,
                    grids=grids,
                )
            )
        return PredictTftFromCheckpointsResult(
            cohort_id=cohort_id,
            seed=command.seed,
            dataset_timestamps=panel.timestamps,
            settings=settings or {},
            runs=tuple(runs),
        )
