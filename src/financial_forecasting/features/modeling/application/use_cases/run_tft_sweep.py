"""Use case `RunTftSweep` — varredura EXPLORATÓRIA de hiperparâmetros do TFT.

Orquestra o laço *ask-and-tell* (ADR 5.4.0005): pede um trial ao port de busca,
reconverte os valores por `kind`, monta os params sobre uma cópia dos
`base_params`, chama o trainer em **modo fit-only**, informa a perda de
validação de volta ao estudo e registra o trial no tracker com
`phase='exploratory'`.

**O isolamento é ESTRUTURAL, não procedimental (I14/D8).** Este use case não
recebe `PersistPredictions` nem `AnalyticsRepository`: os caminhos que produzem
linhas em `fact_oos_predictions` e `dim_run` estão AUSENTES do seu grafo de
dependências, então gravar no armazém confirmatório não é um comportamento que
ele possa expressar — não é um que ele evite por disciplina. O `MedallionStore`
que ele recebe existe para LER o par read-only `(processed, dataset_tft)`; esse
port expõe um `write` genérico, então a ausência de escritas por ele não é
estrutural e é assertada em teste.

Por que isso importa: o protocolo de Raschka (2018 §3-4) exige que a seleção de
hiperparâmetros use apenas treino+validação, e que a avaliação final aconteça
uma única vez com hiperparâmetros congelados. Se a varredura persistisse
predições no mesmo armazém do confirmatório, a separação passaria a depender de
todo leitor futuro aplicar o filtro certo — e um filtro esquecido no Step 6
reintroduziria exatamente o viés que o desenho elimina.

**Qual fold a varredura usa:** o ÚLTIMO. É o de janela de treino mais longa e
histórico mais recente, portanto o mais representativo do regime em que o
candidato será treinado no confirmatório. Explorar sobre todos os folds
multiplicaria o custo por `n_folds` sem mudar a natureza exploratória do
resultado.

Casos de erro (concept §6): C2 (comando inválido antes de qualquer I/O — os
mesmos limites do `TrainTft`), C9 (`n_trials < 1`, ou todos os trials falharam).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime
from itertools import pairwise
from typing import TYPE_CHECKING, Any

from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    known_feature_names,
    unknown_feature_names,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import date
    from pathlib import Path

    from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (  # noqa: E501
        HyperparameterSearch,
        SearchDimension,
    )
    from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
        TftTrainer,
        TftTrainingParams,
    )
    from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
        WalkForwardSplitter,
    )
    from financial_forecasting.features.modeling.domain.value_objects.scope_spec import (
        ScopeSpec,
    )
    from financial_forecasting.shared.application.ports.out.experiment_tracker import (
        ExperimentTracker,
    )
    from financial_forecasting.shared.application.ports.out.hasher import Hasher
    from financial_forecasting.shared.application.ports.out.medallion_store import (
        MedallionStore,
        Row,
    )

logger = logging.getLogger(__name__)

_DATASET_LAYER = "processed"
_DATASET_TABLE = "dataset_tft"
_ARTIFACT_SUBDIR = "tft-sweep"
_EXPLORATORY_PHASE = "exploratory"
_INT_KIND = "int"


@dataclass(frozen=True)
class RunTftSweepCommand:
    """DTO de entrada — cohort, base congelada, espaço e geometria dos folds."""

    scope: ScopeSpec
    base_params: TftTrainingParams
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
class SweepTrialSummary:
    """DTO de saída — um trial avaliado."""

    trial_number: int
    values: Mapping[str, float]
    objective_value: float


@dataclass(frozen=True)
class RunTftSweepResult:
    """DTO de saída — estudo, trials avaliados e o melhor conjunto de params."""

    study_id: str
    trials: tuple[SweepTrialSummary, ...]
    best_trial_number: int
    best_params: TftTrainingParams


def _recast(
    values: Mapping[str, float], space: Sequence[SearchDimension]
) -> dict[str, Any]:
    """Reconverte os valores da fronteira pelo `kind` declarado.

    O port devolve sempre `float` (contrato declarado lá); montar
    `TftTrainingParams` com `hidden_size=16.0` passaria pela validação e só
    quebraria dentro da biblioteca, longe da causa.
    """
    kind_by_name = {dimension.name: dimension.kind for dimension in space}
    return {
        name: round(value) if kind_by_name[name] == _INT_KIND else float(value)
        for name, value in values.items()
    }


class RunTftSweep:
    """Varredura exploratória: ask -> fit-only -> tell, sem tocar o silver."""

    def __init__(  # noqa: PLR0913 — portas coesas do fluxo (concept §4)
        self,
        *,
        store: MedallionStore,
        splitter: WalkForwardSplitter,
        trainer: TftTrainer,
        search: HyperparameterSearch,
        tracker: ExperimentTracker,
        hasher: Hasher,
        artifacts_root: Path,
    ) -> None:
        # NOTE: nenhuma porta de persistência de resultados entra aqui. Se
        # alguém adicionar `PersistPredictions` ou `AnalyticsRepository` a esta
        # assinatura, o teste estrutural de A10 reprova — é o gate de I14.
        self._store = store
        self._splitter = splitter
        self._trainer = trainer
        self._search = search
        self._tracker = tracker
        self._hasher = hasher
        self._artifacts_root = artifacts_root

    def __call__(self, command: RunTftSweepCommand) -> RunTftSweepResult:
        """Roda `n_trials` avaliações exploratórias e devolve o melhor conjunto."""
        _validate_command(command)  # C2/C9 — antes de qualquer I/O

        unknown_names = unknown_feature_names()
        known_names = known_feature_names()
        feature_names = unknown_names + known_names
        returns, sessions, feature_rows = self._load_dataset(command.scope, feature_names)

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
        # Último fold: janela de treino mais longa e histórico mais recente.
        fold = folds[-1]
        index_by_session = {day.isoformat(): idx for idx, day in enumerate(sessions)}
        train_indices = tuple(index_by_session[day] for day in fold.train)
        early_stop_indices = tuple(index_by_session[day] for day in fold.early_stop)

        study_id = self._search.create_study(seed=command.seed)
        summaries: list[SweepTrialSummary] = []
        for _ in range(command.n_trials):
            trial = self._search.ask(command.space)
            params = replace(command.base_params, **_recast(trial.values, command.space))
            try:
                training = self._trainer.train_and_predict(
                    params=params,
                    feature_names=feature_names,
                    known_feature_names=known_names,
                    rows=feature_rows,
                    target=returns,
                    train_decision_indices=train_indices,
                    early_stop_decision_indices=early_stop_indices,
                    # FIT-ONLY: nenhuma predição out-of-sample é sequer
                    # produzida na fase exploratória (I14/D8).
                    test_decision_indices=(),
                    max_horizon=command.scope.max_horizon,
                    horizons=command.horizons,
                    quantile_levels=command.quantile_levels,
                    artifact_dir=str(self._artifacts_root / _ARTIFACT_SUBDIR / study_id),
                )
            except (ValueError, RuntimeError):
                # Trial inviável (combinação de hiperparâmetros que a lib
                # recusa) não derruba a varredura — mas também não é informado
                # ao estudo, para não contaminar o amostrador com um objetivo
                # inventado.
                logger.exception(
                    "trial %s falhou e foi descartado da varredura", trial.number
                )
                continue
            objective = training.best_val_loss
            self._search.tell(trial_number=trial.number, objective_value=objective)
            self._track_trial(command, study_id, trial.number, params, objective)
            summaries.append(
                SweepTrialSummary(
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
        return RunTftSweepResult(
            study_id=study_id,
            trials=tuple(summaries),
            best_trial_number=best.number,
            best_params=best_params,
        )

    # -- rastreamento (I14) -----------------------------------------------------

    def _track_trial(
        self,
        command: RunTftSweepCommand,
        study_id: str,
        trial_number: int,
        params: TftTrainingParams,
        objective: float,
    ) -> None:
        """Registra o trial com `phase='exploratory'` — a segunda camada de I14."""
        try:
            self._tracker.start_run(run_name=f"sweep-{study_id}-{trial_number}")
            self._tracker.log_params(
                {
                    "study_id": study_id,
                    "trial_number": trial_number,
                    "asset_id": command.scope.asset_id,
                    "seed": params.seed,
                    "max_encoder_length": params.max_encoder_length,
                    "hidden_size": params.hidden_size,
                    "attention_head_size": params.attention_head_size,
                    "dropout": params.dropout,
                    "hidden_continuous_size": params.hidden_continuous_size,
                    "learning_rate": params.learning_rate,
                    "max_epochs": params.max_epochs,
                    "patience": params.patience,
                    "batch_size": params.batch_size,
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
    ) -> tuple[tuple[float, ...], tuple[date, ...], tuple[tuple[float, ...], ...]]:
        """Lê o dataset TFT: (target_return, sessões, matriz de features)."""
        rows = self._store.read(
            layer=_DATASET_LAYER, table=_DATASET_TABLE, filters={"asset": scope.asset_id}
        )
        if not rows:
            raise ValueError(
                f"dataset ({_DATASET_LAYER!r}, {_DATASET_TABLE!r}) is empty for "
                f"asset {scope.asset_id!r} — nothing to sweep (C1)"
            )
        missing = tuple(name for name in feature_names if name not in rows[0])
        if missing:
            raise ValueError(
                f"dataset is missing expected feature columns {missing!r} — "
                "registry x dataset drift (C6)"
            )
        parsed = sorted(
            (
                (
                    _timestamp_of(row),
                    _target_return_of(row),
                    tuple(_feature_value_of(row, name) for name in feature_names),
                )
                for row in rows
            ),
            key=lambda triple: triple[0],
        )
        returns = tuple(value for _, value, _ in parsed)
        sessions = tuple(ts.date() for ts, _, _ in parsed)
        feature_rows = tuple(features for _, _, features in parsed)
        return returns, sessions, feature_rows


def _validate_command(command: RunTftSweepCommand) -> None:
    """C2/C9 — comando inválido ergue ANTES de qualquer I/O."""
    if command.n_trials < 1:
        raise ValueError(f"n_trials must be >= 1; got {command.n_trials} (C9)")
    if not command.space:
        raise ValueError("space must declare at least one dimension (C2)")

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


def _timestamp_of(row: Row) -> datetime:
    value = row.get("timestamp")
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"dataset row 'timestamp' must be a tz-aware datetime; got {value!r}")
    return value


def _target_return_of(row: Row) -> float:
    value = row.get("target_return")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"dataset row 'target_return' must be numeric; got {value!r}")
    return float(value)


def _feature_value_of(row: Row, column: str) -> float:
    value = row.get(column)
    if value is None:
        return float("nan")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"dataset row {column!r} must be numeric or None; got {value!r}")
    return float(value)
