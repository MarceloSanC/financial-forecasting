"""Adapter `LightgbmQuantileTrainer` — K boosters por (nível x horizonte).

Implementação real do port `QuantileModelTrainer` (concept 5.3 §4; ADRs
5.3.0001-0002). Única fronteira do BC `modeling` com `lightgbm`/`numpy` — o
gate `modeling-no-lightgbm-leak` reprova o import fora daqui, e NENHUM tipo
numpy atravessa o port de volta (toda emissão vira `float` puro).

Mecânica (concept D6, provada por probe no Checkpoint da Fase 3A):

- Por horizonte: filtra pares de label finito para o fit E para o monitor
  (I11 — o eval nativo do LightGBM converteria label NaN em 0, observação
  fantasma); C3 se o fit ficar abaixo de `min_data_in_leaf` ou o monitor
  ficar sem NENHUM par.
- Por nível τ: `lgb.train(objective='quantile', alpha=τ, metric='quantile',
  deterministic=true, force_row_wise=true, device_type='cpu', sem
  subamostragem)` até o teto `num_boost_round_max`, SEM callback de parada;
  `valid_sets` com a partição early_stop e `record_evaluation` capturam a
  pinball por iteração (no alpha do próprio booster — default da lib para o
  objetivo).
- Seleção (ADR 5.3.0002): `m*_h = 1 + argmin_m média_níveis(história[m])`,
  empate resolvido pela menor iteração. O `+1` converte índice 0-based do
  histórico em contagem 1-based de árvores — `predict(num_iteration=0)`
  significa "todas as árvores" e silenciaria o truncamento (F1 do
  Checkpoint A).
- Predição: `booster.predict(test_X, num_iteration=m*_h)`; equivalência de
  truncamento com re-treino no mesmo teto provada por teste (mata o
  off-by-one). Emissão não finita ergue (C5) — nunca sai silenciosamente.
"""

from __future__ import annotations

import math
from statistics import fmean
from typing import TYPE_CHECKING

import lightgbm as lgb
import numpy as np

from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    QuantileTrainingResult,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from numpy.typing import NDArray

    from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
        GridByHorizon,
    )
    from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (  # noqa: E501
        GbmTrainingParams,
    )

_MONITOR_NAME = "monitor"
_METRIC_NAME = "quantile"


class LightgbmQuantileTrainer:
    """Implementação LightGBM do contrato `QuantileModelTrainer` (CPU, I9)."""

    def train_and_predict(  # noqa: PLR0913 — assinatura do port (parâmetros coesos)
        self,
        *,
        params: GbmTrainingParams,
        feature_names: Sequence[str],
        train_rows: Sequence[Sequence[float]],
        train_labels_by_horizon: Mapping[int, Sequence[float]],
        early_stop_rows: Sequence[Sequence[float]],
        early_stop_labels_by_horizon: Mapping[int, Sequence[float]],
        test_rows: Sequence[Sequence[float]],
        test_decision_indices: Sequence[int],
        quantile_levels: Sequence[float],
    ) -> QuantileTrainingResult:
        """Treina K x H boosters e emite a grade crua (ver docstring do módulo)."""
        _validate_structure(
            feature_names=feature_names,
            train_rows=train_rows,
            train_labels_by_horizon=train_labels_by_horizon,
            early_stop_rows=early_stop_rows,
            early_stop_labels_by_horizon=early_stop_labels_by_horizon,
            test_rows=test_rows,
            test_decision_indices=test_decision_indices,
        )
        width = len(feature_names)
        train_matrix = _as_matrix(train_rows, width)
        early_stop_matrix = _as_matrix(early_stop_rows, width)
        test_matrix = _as_matrix(test_rows, width)

        grids: dict[int, dict[int, tuple[float, ...]]] = {
            decision_idx: {} for decision_idx in test_decision_indices
        }
        best_iteration_by_horizon: dict[int, int] = {}
        for horizon in sorted(train_labels_by_horizon):
            fit_matrix, fit_labels = _finite_pairs(
                train_matrix, train_labels_by_horizon[horizon]
            )
            if fit_labels.shape[0] < params.min_data_in_leaf:
                raise ValueError(
                    f"horizon {horizon}: {fit_labels.shape[0]} finite-label train "
                    f"pairs < min_data_in_leaf={params.min_data_in_leaf} (C3)"
                )
            monitor_matrix, monitor_labels = _finite_pairs(
                early_stop_matrix, early_stop_labels_by_horizon[horizon]
            )
            if monitor_labels.shape[0] == 0:
                raise ValueError(
                    f"horizon {horizon}: early_stop has no finite-label monitor "
                    "pairs (C3)"
                )

            histories: list[tuple[float, ...]] = []
            boosters: list[lgb.Booster] = []
            for tau in quantile_levels:
                booster, history = _train_one_booster(
                    params=params,
                    tau=tau,
                    fit_matrix=fit_matrix,
                    fit_labels=fit_labels,
                    monitor_matrix=monitor_matrix,
                    monitor_labels=monitor_labels,
                )
                boosters.append(booster)
                histories.append(history)

            best_iteration = _select_best_iteration(histories)
            best_iteration_by_horizon[horizon] = best_iteration
            predictions = [
                booster.predict(test_matrix, num_iteration=best_iteration)
                for booster in boosters
            ]
            for position, decision_idx in enumerate(test_decision_indices):
                grids[decision_idx][horizon] = _finite_grid(
                    (float(level_pred[position]) for level_pred in predictions),
                    decision_idx=decision_idx,
                    horizon=horizon,
                )

        frozen_grids: dict[int, GridByHorizon] = {
            decision_idx: dict(by_horizon) for decision_idx, by_horizon in grids.items()
        }
        return QuantileTrainingResult(
            grids=frozen_grids, best_iteration_by_horizon=best_iteration_by_horizon
        )


# -- mecânica LightGBM (D6) --------------------------------------------------------


def _booster_params(params: GbmTrainingParams, tau: float) -> dict[str, object]:
    """Params de um booster: pré-registro D6 + bloco de reprodutibilidade (I4/I9)."""
    return {
        "objective": "quantile",
        "alpha": tau,
        "metric": _METRIC_NAME,
        "learning_rate": params.learning_rate,
        "num_leaves": params.num_leaves,
        "min_data_in_leaf": params.min_data_in_leaf,
        "seed": params.seed,
        "deterministic": True,
        "force_row_wise": True,
        "device_type": "cpu",
        "feature_fraction": 1.0,
        "bagging_fraction": 1.0,
        "bagging_freq": 0,
        "verbosity": -1,
    }


def _train_one_booster(  # noqa: PLR0913 — estado coeso de um booster (nível x horizonte)
    *,
    params: GbmTrainingParams,
    tau: float,
    fit_matrix: NDArray[np.float64],
    fit_labels: NDArray[np.float64],
    monitor_matrix: NDArray[np.float64],
    monitor_labels: NDArray[np.float64],
) -> tuple[lgb.Booster, tuple[float, ...]]:
    """Treina UM booster até o teto (sem parada) e devolve (booster, história)."""
    train_set = lgb.Dataset(fit_matrix, label=fit_labels)
    monitor_set = lgb.Dataset(monitor_matrix, label=monitor_labels, reference=train_set)
    evals: dict[str, dict[str, list[float]]] = {}
    booster = lgb.train(
        _booster_params(params, tau),
        train_set,
        num_boost_round=params.num_boost_round_max,
        valid_sets=[monitor_set],
        valid_names=[_MONITOR_NAME],
        callbacks=[lgb.record_evaluation(evals)],
    )
    history = _history_from(evals, ceiling=params.num_boost_round_max)
    return booster, history


def _history_from(
    evals: Mapping[str, Mapping[str, Sequence[float]]], *, ceiling: int
) -> tuple[float, ...]:
    """Extrai a história da pinball do monitor, validando a mecânica (risco R3).

    Se a lib mudar o nome do valid/métrica ou o comprimento do histórico, o
    erro aqui é o gatilho do fallback do ADR 5.3.0002 (Alternativa B) — nunca
    computar pinball manualmente (escopo do concept §1).
    """
    monitor = evals.get(_MONITOR_NAME)
    if monitor is None or _METRIC_NAME not in monitor:
        raise ValueError(
            f"eval history missing {_MONITOR_NAME!r}/{_METRIC_NAME!r} — LightGBM "
            "eval mechanics changed (R3; fallback = ADR 5.3.0002 Alternative B)"
        )
    history = tuple(float(value) for value in monitor[_METRIC_NAME])
    if len(history) != ceiling:
        raise ValueError(
            f"eval history length {len(history)} != num_boost_round_max {ceiling} "
            "(R3; fallback = ADR 5.3.0002 Alternative B)"
        )
    return history


def _select_best_iteration(histories: Sequence[Sequence[float]]) -> int:
    """`m* = 1 + argmin` da média das histórias por iteração (ADR 5.3.0002).

    1-based de propósito: `predict(num_iteration=0)` usa TODAS as árvores, então
    devolver o índice cru silenciaria o truncamento quando o ótimo é a primeira
    iteração. Empate resolvido pela menor iteração (argmin devolve a primeira).
    """
    if not histories:
        raise ValueError("no histories to select best iteration from")
    length = len(histories[0])
    if length == 0 or any(len(history) != length for history in histories):
        raise ValueError(
            f"histories must be non-empty and equal-length; got "
            f"{[len(history) for history in histories]}"
        )
    means = [
        fmean(history[iteration] for history in histories)
        for iteration in range(length)
    ]
    best_index = min(range(length), key=lambda iteration: (means[iteration], iteration))
    return best_index + 1


# -- conversões e validações de fronteira ------------------------------------------


def _as_matrix(rows: Sequence[Sequence[float]], width: int) -> NDArray[np.float64]:
    """Converte linhas do port em matriz float64 (NaN preservado = missing nativo)."""
    if not rows:
        return np.empty((0, width), dtype=np.float64)
    return np.asarray([[float(value) for value in row] for row in rows], dtype=np.float64)


def _finite_pairs(
    matrix: NDArray[np.float64], labels: Sequence[float]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Filtra pares (linha, label) com label finito (I11 — fit E monitor)."""
    label_array = np.asarray([float(label) for label in labels], dtype=np.float64)
    mask = np.isfinite(label_array)
    return matrix[mask], label_array[mask]


def _finite_grid(
    values: Iterable[float], *, decision_idx: int, horizon: int
) -> tuple[float, ...]:
    """Materializa a grade crua de uma decisão, erguendo em não finito (C5)."""
    grid = tuple(float(value) for value in values)
    if any(not math.isfinite(value) for value in grid):
        raise ValueError(
            f"non-finite raw grid emitted at decision {decision_idx}, "
            f"horizon {horizon}: {grid} (C5)"
        )
    return grid


def _validate_structure(  # noqa: PLR0913 — validação C4 espelhada no fake
    *,
    feature_names: Sequence[str],
    train_rows: Sequence[Sequence[float]],
    train_labels_by_horizon: Mapping[int, Sequence[float]],
    early_stop_rows: Sequence[Sequence[float]],
    early_stop_labels_by_horizon: Mapping[int, Sequence[float]],
    test_rows: Sequence[Sequence[float]],
    test_decision_indices: Sequence[int],
) -> None:
    """C4: estrutura inconsistente ergue `ValueError` (paridade fake<->real)."""
    if not feature_names:
        raise ValueError("feature_names must be non-empty (C4)")
    if not train_labels_by_horizon:
        raise ValueError("train_labels_by_horizon must be non-empty (C4)")
    if set(train_labels_by_horizon) != set(early_stop_labels_by_horizon):
        raise ValueError(
            "train and early_stop label horizons must match; got "
            f"{sorted(train_labels_by_horizon)} vs "
            f"{sorted(early_stop_labels_by_horizon)} (C4)"
        )
    if not early_stop_rows:
        raise ValueError("early_stop_rows must be non-empty — no monitor, no m* (C4)")
    if len(test_decision_indices) != len(test_rows):
        raise ValueError(
            f"test_decision_indices length {len(test_decision_indices)} != "
            f"test_rows length {len(test_rows)} (C4)"
        )
    width = len(feature_names)
    for block_name, rows in (
        ("train_rows", train_rows),
        ("early_stop_rows", early_stop_rows),
        ("test_rows", test_rows),
    ):
        for position, row in enumerate(rows):
            if len(row) != width:
                raise ValueError(
                    f"{block_name}[{position}] width {len(row)} != "
                    f"len(feature_names)={width} (C4)"
                )
    for block_name, rows_len, labels_by_horizon in (
        ("train", len(train_rows), train_labels_by_horizon),
        ("early_stop", len(early_stop_rows), early_stop_labels_by_horizon),
    ):
        for horizon, labels in labels_by_horizon.items():
            if len(labels) != rows_len:
                raise ValueError(
                    f"{block_name} labels for horizon {horizon} length "
                    f"{len(labels)} != rows length {rows_len} (C4)"
                )
