"""Use case `RunGbmSweep` — varredura EXPLORATÓRIA de hiperparâmetros do GBM quantílico.

Espelho do `RunTftSweep` (ADR 5.4.0005) para o comparador forte, com o MESMO
orçamento de trials e a mesma geometria exploratória (Stage 5.5, D13; ADR
5.5.0002): sem simetria de ajuste, só o TFT seria tunado e a comparação de H2
favoreceria o candidato.

Laço *ask-and-tell*: pede um trial ao port de busca, reconverte os valores por
`kind`, monta `GbmTrainingParams` sobre uma cópia dos `base_params`, chama o
treinador em **modo fit-only** (`test_rows=()` — nenhuma predição OOS é sequer
produzida), informa ao estudo o objetivo e registra o trial com
`phase='exploratory'`.

**Objetivo:** média aritmética, entre os horizontes do comando, da perda de
early_stop que o `QuantileModelTrainer` devolve por horizonte (pinball média da
grade na iteração escolhida — ADR 5.3.0002). Peso igual por horizonte espelha o
objetivo único do TFT (perda média do decoder multi-horizonte).

**Isolamento estrutural (I14):** o use case não recebe persister nem
`AnalyticsRepository`; o `MedallionStore` só é lido (par read-only
`(processed, dataset_tft)`) e a ausência de escritas é assertada em teste.

**Fold:** o último da geometria recebida — o runner da 5.5 passa a geometria
exploratória (um único fold cujo treino e early_stop são os do fold 0
confirmatório), então nenhum dado pontuado pelo confirmatório entra na busca.

Casos de erro: C2 (comando inválido antes de qualquer I/O), C11 (dimensão que
não é campo de `GbmTrainingParams`), C9 (`n_trials < 1` ou todos os trials
falharam).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, replace
from itertools import pairwise
from statistics import fmean
from typing import TYPE_CHECKING, Any

from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    validate_dimension_names,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    _labels_from_full_grid,
    expected_feature_names,
    modeling_columns,
)
from financial_forecasting.features.modeling.domain.exceptions.backend import (
    ModelTrainingError,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    build_training_grid,
)
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (  # noqa: E501
        HyperparameterSearch,
        SearchDimension,
    )
    from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (  # noqa: E501
        QuantileModelTrainer,
    )
    from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
        WalkForwardSplitter,
    )
    from financial_forecasting.features.modeling.domain.value_objects.scope_spec import ScopeSpec
    from financial_forecasting.shared.application.ports.out.experiment_tracker import (
        ExperimentTracker,
    )
    from financial_forecasting.shared.application.ports.out.hasher import Hasher
    from financial_forecasting.shared.application.ports.out.medallion_store import (
        MedallionStore,
    )

logger = logging.getLogger(__name__)

_DATASET_LAYER = "processed"
_DATASET_TABLE = "dataset_tft"
_EXPLORATORY_PHASE = "exploratory"
_INT_KIND = "int"
_TARGET_COLUMN = "target_return"


@dataclass(frozen=True)
class RunGbmSweepCommand:
    """DTO de entrada — espaço, orçamento, base congelada, grade e geometria."""

    scope: ScopeSpec
    base_params: GbmTrainingParams
    space: tuple[SearchDimension, ...]
    n_trials: int
    seed: int
    horizons: tuple[int, ...]
    quantile_levels: tuple[float, ...]
    n_folds: int
    test_size: int
    val_size: int
    calib_size: int
    embargo: int


@dataclass(frozen=True)
class GbmSweepTrialSummary:
    """DTO de saída — um trial avaliado."""

    trial_number: int
    values: Mapping[str, float]
    objective_value: float


@dataclass(frozen=True)
class RunGbmSweepResult:
    """DTO de saída — estudo, trials, melhor conjunto e o dado sobre o qual rodou."""

    study_id: str
    trials: tuple[GbmSweepTrialSummary, ...]
    best_trial_number: int
    best_params: GbmTrainingParams
    dataset_fingerprint: str
    """Impressão digital do conteúdo do grid sobre o qual o sweep treinou (I4)."""


def _recast(values: Mapping[str, float], space: Sequence[SearchDimension]) -> dict[str, Any]:
    """Reconverte os valores da fronteira (sempre `float`) pelo `kind` declarado."""
    kind_by_name = {dimension.name: dimension.kind for dimension in space}
    return {
        name: round(value) if kind_by_name[name] == _INT_KIND else float(value)
        for name, value in values.items()
    }


class RunGbmSweep:
    """Varredura exploratória do GBM: ask -> fit-only -> tell, sem tocar o silver."""

    def __init__(  # noqa: PLR0913 — portas coesas do fluxo
        self,
        *,
        store: MedallionStore,
        splitter: WalkForwardSplitter,
        trainer: QuantileModelTrainer,
        search: HyperparameterSearch,
        tracker: ExperimentTracker,
        hasher: Hasher,
    ) -> None:
        # NOTE: nenhuma porta de persistência de resultados entra aqui (I14).
        self._store = store
        self._splitter = splitter
        self._trainer = trainer
        self._search = search
        self._tracker = tracker
        self._hasher = hasher

    def __call__(self, command: RunGbmSweepCommand) -> RunGbmSweepResult:
        """Roda `n_trials` avaliações exploratórias e devolve o melhor conjunto."""
        _validate_command(command)  # C2/C9/C11 — antes de qualquer I/O

        feature_names = expected_feature_names()
        returns, sessions, feature_rows, dataset_fingerprint = self._load_dataset(
            command.scope, feature_names
        )
        folds = self._splitter.split(
            sessions,
            command.scope,
            n_folds=command.n_folds,
            test_size=command.test_size,
            val_size=command.val_size,
            calib_size=command.calib_size,
            embargo=command.embargo,
            hasher=self._hasher,
        )
        fold = folds[-1]
        index_by_session = {day.isoformat(): idx for idx, day in enumerate(sessions)}
        train_indices = tuple(index_by_session[day] for day in fold.train)
        early_stop_indices = tuple(index_by_session[day] for day in fold.early_stop)
        train_rows = tuple(feature_rows[idx] for idx in train_indices)
        early_stop_rows = tuple(feature_rows[idx] for idx in early_stop_indices)
        train_labels = {
            h: _labels_from_full_grid(train_indices, returns, h) for h in command.horizons
        }
        early_stop_labels = {
            h: _labels_from_full_grid(early_stop_indices, returns, h) for h in command.horizons
        }

        study_id = self._search.create_study(seed=command.seed)
        summaries: list[GbmSweepTrialSummary] = []
        for _ in range(command.n_trials):
            trial = self._search.ask(command.space)
            try:
                # Montagem dos params dentro do `try`: a dimensão valida a forma,
                # não o domínio do campo (ex.: `learning_rate=0.0` recusado pelo
                # DTO) — combinação inviável descarta o trial, não a varredura.
                params = replace(command.base_params, **_recast(trial.values, command.space))
                training = self._trainer.train_and_predict(
                    params=params,
                    feature_names=feature_names,
                    train_rows=train_rows,
                    train_labels_by_horizon=train_labels,
                    early_stop_rows=early_stop_rows,
                    early_stop_labels_by_horizon=early_stop_labels,
                    # FIT-ONLY: nenhuma predição out-of-sample (I14).
                    test_rows=(),
                    test_decision_indices=(),
                    quantile_levels=command.quantile_levels,
                )
            except (ValueError, ModelTrainingError):
                # Mesmos dois tipos do sweep do TFT (issue #84): regra do
                # port/DTO recusando a combinação, ou a biblioteca falhando nela.
                logger.exception("trial %s falhou e foi descartado da varredura", trial.number)
                self._search.fail(trial_number=trial.number)
                continue
            objective = fmean(
                training.early_stop_loss_by_horizon[h] for h in command.horizons
            )
            self._search.tell(trial_number=trial.number, objective_value=objective)
            self._track_trial(command, study_id, trial.number, params, objective)
            summaries.append(
                GbmSweepTrialSummary(
                    trial_number=trial.number,
                    values=dict(trial.values),
                    objective_value=objective,
                )
            )

        if not summaries:
            msg = (
                f"todos os {command.n_trials} trials falharam — a varredura não "
                "produziu nenhum objetivo (C9)"
            )
            raise ValueError(msg)

        best = self._search.best_trial()
        best_params = replace(command.base_params, **_recast(best.values, command.space))
        return RunGbmSweepResult(
            study_id=study_id,
            trials=tuple(summaries),
            best_trial_number=best.number,
            best_params=best_params,
            dataset_fingerprint=dataset_fingerprint,
        )

    # -- rastreamento (I14) -----------------------------------------------------

    def _track_trial(
        self,
        command: RunGbmSweepCommand,
        study_id: str,
        trial_number: int,
        params: GbmTrainingParams,
        objective: float,
    ) -> None:
        """Registra o trial com `phase='exploratory'`; falha de tracking não derruba."""
        try:
            self._tracker.start_run(run_name=f"gbm-sweep-{study_id}-{trial_number}")
            self._tracker.log_params(
                {
                    "study_id": study_id,
                    "trial_number": trial_number,
                    "asset_id": command.scope.asset_id,
                    **asdict(params),
                }
            )
            self._tracker.log_metrics({"objective": objective})
            self._tracker.set_tags({"phase": _EXPLORATORY_PHASE, "study_id": study_id})
            self._tracker.end_run()
        except Exception:
            logger.exception(
                "tracking do trial %s falhou — a varredura segue (observabilidade "
                "não derruba exploração)",
                trial_number,
            )
            try:
                self._tracker.end_run()
            except Exception:
                logger.debug("could not close tracking run for trial %s", trial_number)

    # -- leitura do dataset -----------------------------------------------------

    def _load_dataset(
        self, scope: ScopeSpec, feature_names: tuple[str, ...]
    ) -> tuple[tuple[float, ...], tuple[Any, ...], tuple[tuple[float, ...], ...], str]:
        """Lê pelo grid único: (target_return, sessões, matriz, impressão digital)."""
        rows = self._store.read(
            layer=_DATASET_LAYER, table=_DATASET_TABLE, filters={"asset": scope.asset_id}
        )
        if not rows:
            raise ValueError(
                f"dataset ({_DATASET_LAYER!r}, {_DATASET_TABLE!r}) is empty for "
                f"asset {scope.asset_id!r} — nothing to sweep (C1)"
            )
        columns = modeling_columns()
        grid = build_training_grid(rows, columns=columns)
        fingerprint = DatasetContentFingerprint.compute(
            hasher=self._hasher,
            asset_id=scope.asset_id,
            timestamps=grid.timestamps_iso(),
            columns={name: grid.column(name) for name in columns},
        )
        return (
            grid.column(_TARGET_COLUMN),
            grid.sessions(),
            grid.matrix(feature_names),
            fingerprint.value,
        )


def _validate_command(command: RunGbmSweepCommand) -> None:
    """C2/C9/C11 — comando inválido ergue ANTES de qualquer I/O."""
    if command.n_trials < 1:
        raise ValueError(f"n_trials must be >= 1; got {command.n_trials} (C9)")
    if not command.space:
        raise ValueError("space must declare at least one dimension (C2)")
    validate_dimension_names(command.space, GbmTrainingParams)
    levels = command.quantile_levels
    if not levels:
        raise ValueError("quantile_levels must be non-empty (C2)")
    if any(not 0.0 < tau < 1.0 for tau in levels):
        raise ValueError(f"quantile_levels must all be in (0, 1); got {levels} (C2)")
    if any(b <= a for a, b in pairwise(levels)):
        raise ValueError(
            f"quantile_levels must be strictly increasing and unique; got {levels} (C2)"
        )
    if not command.horizons:
        raise ValueError("horizons must be non-empty (C2)")
    if max(command.horizons) > command.scope.max_horizon:
        raise ValueError(
            f"max(horizons)={max(command.horizons)} exceeds "
            f"scope.max_horizon={command.scope.max_horizon} (C2)"
        )
