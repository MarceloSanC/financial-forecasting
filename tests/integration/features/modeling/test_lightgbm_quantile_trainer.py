"""Integration — `LightgbmQuantileTrainer` contra o LightGBM REAL (Task 04).

Prova a mecânica que a suite de contrato (Task 05) não cobre (concept A3/A5;
ADR 5.3.0002):

- histórias de avaliação existem, com comprimento == teto, para todos os níveis
  (mecânica R3 validada por construção — um run feliz implica `_history_from`
  satisfeito) e o R3 defensivo ergue em histórico ausente/curto (helper puro);
- `_select_best_iteration`: argmin da média, empate -> menor, 1-based;
- oráculo do truncamento: labels de ruído (features não informativas) têm ótimo
  na PRIMEIRA iteração (probe da Fase 3A) -> `best_iteration == 1` e grades ==
  re-treino com teto 1 (mata o off-by-one índice-0 = modelo cheio);
- determinismo bit a bit (I4) com params D6 (sem subamostragem);
- I11-monitor: NaN em labels de early_stop == pares pré-removidos;
- C3 (fit e monitor), C5 (helper puro) e I9 (`device_type='cpu'` nos params).
"""

from __future__ import annotations

import math

import pytest

from financial_forecasting.features.modeling.adapters.out.lightgbm.lightgbm_quantile_trainer import (  # noqa: E501
    LightgbmQuantileTrainer,
    _booster_params,
    _finite_grid,
    _history_from,
    _select_best_iteration,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
    QuantileTrainingResult,
)

pytestmark = pytest.mark.integration

_LEVELS = (0.1, 0.5, 0.9)
_HORIZONS = (1, 2)
_CEILING = 25
_SEED = 42
_N_TRAIN = 80
_N_MONITOR = 20
_N_TEST = 5
_N_FEATURES = 4


def _params(**overrides: object) -> GbmTrainingParams:
    base: dict[str, object] = {
        "seed": _SEED,
        "num_boost_round_max": _CEILING,
        "min_data_in_leaf": 5,
    }
    base.update(overrides)
    return GbmTrainingParams(**base)  # type: ignore[arg-type]


def _lcg(seed: int) -> float:
    """Gerador determinístico stdlib-free de ruído em [-0.5, 0.5)."""
    return ((seed * 1103515245 + 12345) % 2**31) / 2**31 - 0.5


def _noise_rows(count: int, *, salt: int) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple(_lcg(salt + row * _N_FEATURES + col) for col in range(_N_FEATURES))
        for row in range(count)
    )


def _noise_labels(count: int, *, salt: int) -> tuple[float, ...]:
    return tuple(0.01 * _lcg(salt + i) for i in range(count))


_FEATURE_NAMES = tuple(f"f{i}" for i in range(_N_FEATURES))
_TRAIN_ROWS = _noise_rows(_N_TRAIN, salt=1)
_MONITOR_ROWS = _noise_rows(_N_MONITOR, salt=7_000)
_TEST_ROWS = _noise_rows(_N_TEST, salt=11_000)
_TRAIN_LABELS = {h: _noise_labels(_N_TRAIN, salt=100_000 * h) for h in _HORIZONS}
_MONITOR_LABELS = {h: _noise_labels(_N_MONITOR, salt=500_000 * h) for h in _HORIZONS}
_DECISIONS = tuple(range(100, 100 + _N_TEST))


def _train(
    trainer: LightgbmQuantileTrainer,
    *,
    params: GbmTrainingParams | None = None,
    monitor_labels: dict[int, tuple[float, ...]] | None = None,
) -> QuantileTrainingResult:
    return trainer.train_and_predict(
        params=params if params is not None else _params(),
        feature_names=_FEATURE_NAMES,
        train_rows=_TRAIN_ROWS,
        train_labels_by_horizon=_TRAIN_LABELS,
        early_stop_rows=_MONITOR_ROWS,
        early_stop_labels_by_horizon=(
            monitor_labels if monitor_labels is not None else _MONITOR_LABELS
        ),
        test_rows=_TEST_ROWS,
        test_decision_indices=_DECISIONS,
        quantile_levels=_LEVELS,
    )


# -- estrutura e mecânica ----------------------------------------------------------


def test_emits_full_grid_per_decision_and_horizon_with_valid_best_iteration() -> None:
    """Grade 1:1 com os níveis por (decisão x horizonte); m* em [1, teto]."""
    result = _train(LightgbmQuantileTrainer())

    assert set(result.grids) == set(_DECISIONS)
    for by_horizon in result.grids.values():
        assert set(by_horizon) == set(_HORIZONS)
        for grid in by_horizon.values():
            assert len(grid) == len(_LEVELS)
            assert all(math.isfinite(value) for value in grid)
    assert set(result.best_iteration_by_horizon) == set(_HORIZONS)
    assert all(1 <= m <= _CEILING for m in result.best_iteration_by_horizon.values())


def test_a3_noise_labels_select_iteration_one_and_match_ceiling_one_retrain() -> None:
    """Oráculo do truncamento: learning rate alto faz cada árvore extra piorar o
    monitor (overshoot), então o ótimo é a PRIMEIRA iteração -> m*=1 e grades ==
    re-treino com teto 1. Uma implementação que devolvesse o ÍNDICE do argmin
    (0) prederia com o modelo CHEIO e divergiria do re-treino (off-by-one morto).
    """
    overshoot = _params(learning_rate=5.0)
    full = _train(LightgbmQuantileTrainer(), params=overshoot)
    assert all(m == 1 for m in full.best_iteration_by_horizon.values()), (
        "fixture de overshoot deveria ter ótimo na primeira iteração "
        f"(got {dict(full.best_iteration_by_horizon)})"
    )

    ceiling_one = _train(
        LightgbmQuantileTrainer(),
        params=_params(learning_rate=5.0, num_boost_round_max=1),
    )
    for decision_idx in _DECISIONS:
        for horizon in _HORIZONS:
            assert full.grids[decision_idx][horizon] == pytest.approx(
                ceiling_one.grids[decision_idx][horizon], abs=0.0
            )


def test_i4_two_identical_calls_are_bitwise_identical() -> None:
    """Determinismo D6: sem subamostragem + seed fixa -> saída idêntica."""
    first = _train(LightgbmQuantileTrainer())
    second = _train(LightgbmQuantileTrainer())

    assert first.grids == second.grids
    assert first.best_iteration_by_horizon == second.best_iteration_by_horizon


def test_i11_nan_monitor_labels_equal_pre_removed_pairs() -> None:
    """NaN no monitor == pares pré-removidos (o eval nativo converteria em 0)."""
    nan = float("nan")
    polluted = {
        h: (nan, *_MONITOR_LABELS[h][1:_N_MONITOR // 2], nan,
            *_MONITOR_LABELS[h][_N_MONITOR // 2 + 1:])
        for h in _HORIZONS
    }
    finite_mask = [
        i for i in range(_N_MONITOR) if i not in (0, _N_MONITOR // 2)
    ]

    with_nan = _train(LightgbmQuantileTrainer(), monitor_labels=polluted)
    pre_removed = LightgbmQuantileTrainer().train_and_predict(
        params=_params(),
        feature_names=_FEATURE_NAMES,
        train_rows=_TRAIN_ROWS,
        train_labels_by_horizon=_TRAIN_LABELS,
        early_stop_rows=tuple(_MONITOR_ROWS[i] for i in finite_mask),
        early_stop_labels_by_horizon={
            h: tuple(polluted[h][i] for i in finite_mask) for h in _HORIZONS
        },
        test_rows=_TEST_ROWS,
        test_decision_indices=_DECISIONS,
        quantile_levels=_LEVELS,
    )

    assert with_nan.grids == pre_removed.grids
    assert with_nan.best_iteration_by_horizon == pre_removed.best_iteration_by_horizon


# -- seleção de m* (helper puro) ---------------------------------------------------


def test_select_best_iteration_is_one_based_argmin_of_the_mean() -> None:
    """Média sobre níveis, 1-based: mínimo da média em índice 2 -> m*=3."""
    histories = [
        (3.0, 2.0, 1.0, 4.0),
        (1.0, 2.0, 0.5, 4.0),
    ]  # médias: (2.0, 2.0, 0.75, 4.0) -> argmin índice 2
    expected_one_based = 3

    assert _select_best_iteration(histories) == expected_one_based


def test_select_best_iteration_tie_breaks_to_the_smallest_iteration() -> None:
    """Empate na média -> menor iteração (1-based)."""
    histories = [(1.0, 1.0, 2.0)]  # médias empatam nas iterações 1 e 2

    assert _select_best_iteration(histories) == 1


def test_select_best_iteration_rejects_empty_or_ragged_histories() -> None:
    with pytest.raises(ValueError, match="no histories"):
        _select_best_iteration([])
    with pytest.raises(ValueError, match="equal-length"):
        _select_best_iteration([(1.0, 2.0), (1.0,)])
    with pytest.raises(ValueError, match="equal-length"):
        _select_best_iteration([()])


# -- R3 defensivo e C5 (helpers puros) ---------------------------------------------


def test_history_from_validates_the_eval_mechanics_r3() -> None:
    """Nome do valid/métrica ausente ou comprimento != teto -> R3 ergue."""
    good = {"monitor": {"quantile": [1.0, 2.0, 3.0]}}
    assert _history_from(good, ceiling=3) == (1.0, 2.0, 3.0)

    with pytest.raises(ValueError, match=r"R3"):
        _history_from({}, ceiling=3)
    with pytest.raises(ValueError, match=r"R3"):
        _history_from({"monitor": {"other_metric": [1.0]}}, ceiling=1)
    with pytest.raises(ValueError, match=r"R3"):
        _history_from({"monitor": {"quantile": [1.0, 2.0]}}, ceiling=3)


def test_c5_non_finite_emission_raises() -> None:
    assert _finite_grid((0.1, 0.2), decision_idx=1, horizon=1) == (0.1, 0.2)

    with pytest.raises(ValueError, match=r"C5"):
        _finite_grid((0.1, float("nan")), decision_idx=1, horizon=1)
    with pytest.raises(ValueError, match=r"C5"):
        _finite_grid((float("inf"), 0.2), decision_idx=1, horizon=1)


# -- C3/C4 na fronteira real -------------------------------------------------------


def test_c3_insufficient_finite_train_pairs_raise() -> None:
    nan = float("nan")
    mostly_nan = {h: (0.01, 0.02, *([nan] * (_N_TRAIN - 2))) for h in _HORIZONS}

    with pytest.raises(ValueError, match=r"C3"):
        LightgbmQuantileTrainer().train_and_predict(
            params=_params(min_data_in_leaf=5),
            feature_names=_FEATURE_NAMES,
            train_rows=_TRAIN_ROWS,
            train_labels_by_horizon=mostly_nan,
            early_stop_rows=_MONITOR_ROWS,
            early_stop_labels_by_horizon=_MONITOR_LABELS,
            test_rows=_TEST_ROWS,
            test_decision_indices=_DECISIONS,
            quantile_levels=_LEVELS,
        )


def test_c3_monitor_without_finite_labels_raises() -> None:
    nan = float("nan")
    all_nan_monitor = {h: tuple([nan] * _N_MONITOR) for h in _HORIZONS}

    with pytest.raises(ValueError, match=r"monitor|C3"):
        _train(LightgbmQuantileTrainer(), monitor_labels=all_nan_monitor)


def test_c4_row_width_mismatch_raises() -> None:
    bad_rows = (*_TRAIN_ROWS[:-1], _TRAIN_ROWS[-1][:-1])

    with pytest.raises(ValueError, match=r"C4"):
        LightgbmQuantileTrainer().train_and_predict(
            params=_params(),
            feature_names=_FEATURE_NAMES,
            train_rows=bad_rows,
            train_labels_by_horizon=_TRAIN_LABELS,
            early_stop_rows=_MONITOR_ROWS,
            early_stop_labels_by_horizon=_MONITOR_LABELS,
            test_rows=_TEST_ROWS,
            test_decision_indices=_DECISIONS,
            quantile_levels=_LEVELS,
        )


# -- I9: CPU fixado nos params -----------------------------------------------------


def test_i9_booster_params_pin_cpu_and_the_preregistered_block() -> None:
    """`device_type='cpu'`, objetivo/alpha por nível e bloco D6 sem subamostragem."""
    tau = 0.9

    params = _booster_params(_params(), tau)

    assert params["device_type"] == "cpu"
    assert params["objective"] == "quantile"
    assert params["alpha"] == tau
    assert params["metric"] == "quantile"
    assert params["deterministic"] is True
    assert params["force_row_wise"] is True
    assert params["feature_fraction"] == 1.0
    assert params["bagging_fraction"] == 1.0
    assert params["seed"] == _SEED
