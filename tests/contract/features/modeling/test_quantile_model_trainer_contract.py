"""Suite de contrato do `QuantileModelTrainer` — fake e real sob os MESMOS testes.

Parametrizada sobre `[fake, real]` (skill `pytest-with-fakes` §contract, padrão
da 5.2): `FakeQuantileModelTrainer` (tests/fakes) e `LightgbmQuantileTrainer`
(adapter LightGBM) devem exibir o MESMO comportamento observável do port
(concept 5.3 §4/§5/§6):

- estrutura: uma grade por decisão de teste x horizonte, alinhada 1:1 aos
  níveis; `best_iteration_by_horizon` em [1, teto] (A2);
- determinismo bit a bit (I4/A5-port);
- C3 nas duas formas (fit insuficiente; monitor sem par finito — F2 do
  Checkpoint C bloco 1), C4 estrutural exatamente como o concept define
  (largura, comprimento de labels, early_stop vazio, horizontes descasados,
  test_decision_indices descasado — levels inválidos são C2 do use case e NÃO
  entram aqui, Checkpoint B F2);
- I11-fit: resultado invariante à pré-remoção de pares de train com label NaN;
- A6 — oráculo de emissão: com features CONSTANTES (nenhum split possível) a
  emissão colapsa no quantil empírico tipo 7 dos labels finitos de train
  (`sample_quantiles_type7`, domínio 5.2), tolerância abs 1e-6 justificada
  pelo armazenamento float32 dos labels no `lgb.Dataset` (concept A6), com
  mutante de janela numericamente discriminado (ADR 0.0.0021).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from financial_forecasting.features.modeling.adapters.out.lightgbm.lightgbm_quantile_trainer import (  # noqa: E501
    LightgbmQuantileTrainer,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from financial_forecasting.features.modeling.domain.services.quantile_grid_emission import (
    sample_quantiles_type7,
)
from tests.fakes.features.modeling.in_memory_quantile_model_trainer import (
    FakeQuantileModelTrainer,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (  # noqa: E501
        QuantileModelTrainer,
        QuantileTrainingResult,
    )


def _build_fake() -> QuantileModelTrainer:
    return FakeQuantileModelTrainer()


def _build_real() -> QuantileModelTrainer:
    return LightgbmQuantileTrainer()


_FACTORIES: list[Callable[[], QuantileModelTrainer]] = [_build_fake, _build_real]
_IDS = ["fake", "real"]


@pytest.fixture(params=_FACTORIES, ids=_IDS)
def trainer(request: pytest.FixtureRequest) -> QuantileModelTrainer:
    factory: Callable[[], QuantileModelTrainer] = request.param
    return factory()


# -- fixtures determinísticas ------------------------------------------------------

_LEVELS = (0.1, 0.5, 0.9)
_HORIZONS = (1, 2)
_CEILING = 10
_SEED = 7
_N_TRAIN = 40
_N_MONITOR = 12
_N_TEST = 3
_N_FEATURES = 3
_FEATURE_NAMES = tuple(f"f{i}" for i in range(_N_FEATURES))
_DECISIONS = (200, 201, 202)
_ORACLE_TOLERANCE = 1e-6  # labels em float32 no lgb.Dataset (concept A6)


def _lcg(seed: int) -> float:
    """Ruído determinístico em [-0.5, 0.5) sem dependência de RNG global."""
    return ((seed * 1103515245 + 12345) % 2**31) / 2**31 - 0.5


def _rows(count: int, *, salt: int) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple(_lcg(salt + row * _N_FEATURES + col) for col in range(_N_FEATURES))
        for row in range(count)
    )


def _labels(count: int, *, salt: int) -> tuple[float, ...]:
    return tuple(0.01 * _lcg(salt + i) for i in range(count))


_TRAIN_ROWS = _rows(_N_TRAIN, salt=3)
_MONITOR_ROWS = _rows(_N_MONITOR, salt=9_000)
_TEST_ROWS = _rows(_N_TEST, salt=13_000)
_TRAIN_LABELS = {h: _labels(_N_TRAIN, salt=70_000 * h) for h in _HORIZONS}
_MONITOR_LABELS = {h: _labels(_N_MONITOR, salt=90_000 * h) for h in _HORIZONS}


def _params(**overrides: object) -> GbmTrainingParams:
    base: dict[str, object] = {
        "seed": _SEED,
        "num_boost_round_max": _CEILING,
        "min_data_in_leaf": 3,
    }
    base.update(overrides)
    return GbmTrainingParams(**base)  # type: ignore[arg-type]


def _train(  # noqa: PLR0913 — espelha a assinatura coesa do port sob teste
    trainer: QuantileModelTrainer,
    *,
    params: GbmTrainingParams | None = None,
    train_rows: Sequence[Sequence[float]] = _TRAIN_ROWS,
    train_labels: Mapping[int, Sequence[float]] = _TRAIN_LABELS,
    early_stop_rows: Sequence[Sequence[float]] = _MONITOR_ROWS,
    early_stop_labels: Mapping[int, Sequence[float]] = _MONITOR_LABELS,
    test_rows: Sequence[Sequence[float]] = _TEST_ROWS,
    test_decision_indices: Sequence[int] = _DECISIONS,
) -> QuantileTrainingResult:
    return trainer.train_and_predict(
        params=params if params is not None else _params(),
        feature_names=_FEATURE_NAMES,
        train_rows=train_rows,
        train_labels_by_horizon=train_labels,
        early_stop_rows=early_stop_rows,
        early_stop_labels_by_horizon=early_stop_labels,
        test_rows=test_rows,
        test_decision_indices=test_decision_indices,
        quantile_levels=_LEVELS,
    )


# -- estrutura (A2) ----------------------------------------------------------------


@pytest.mark.contract
def test_grid_present_for_every_decision_and_horizon_aligned_to_levels(
    trainer: QuantileModelTrainer,
) -> None:
    result = _train(trainer)

    assert set(result.grids) == set(_DECISIONS)
    for by_horizon in result.grids.values():
        assert set(by_horizon) == set(_HORIZONS)
        for grid in by_horizon.values():
            assert len(grid) == len(_LEVELS)
            assert all(isinstance(value, float) for value in grid)


@pytest.mark.contract
def test_best_iteration_is_one_based_and_bounded_by_the_ceiling(
    trainer: QuantileModelTrainer,
) -> None:
    result = _train(trainer)

    assert set(result.best_iteration_by_horizon) == set(_HORIZONS)
    assert all(
        1 <= iteration <= _CEILING
        for iteration in result.best_iteration_by_horizon.values()
    )


# -- determinismo (I4) -------------------------------------------------------------


@pytest.mark.contract
def test_two_identical_calls_produce_identical_results(
    trainer: QuantileModelTrainer,
) -> None:
    first = _train(trainer)
    second = _train(trainer)

    assert first.grids == second.grids
    assert first.best_iteration_by_horizon == second.best_iteration_by_horizon


# -- I11: labels não finitos excluem o par -----------------------------------------


@pytest.mark.contract
def test_nan_train_labels_equal_pre_removed_pairs(
    trainer: QuantileModelTrainer,
) -> None:
    """Poluir 2 pares de train com NaN == removê-los antes (fit-side I11)."""
    nan = float("nan")
    polluted = {
        h: (nan, *_TRAIN_LABELS[h][1:20], nan, *_TRAIN_LABELS[h][21:])
        for h in _HORIZONS
    }
    keep = [i for i in range(_N_TRAIN) if i not in (0, 20)]

    with_nan = _train(trainer, train_labels=polluted)
    pre_removed = _train(
        trainer,
        train_rows=tuple(_TRAIN_ROWS[i] for i in keep),
        train_labels={h: tuple(polluted[h][i] for i in keep) for h in _HORIZONS},
    )

    assert with_nan.grids == pre_removed.grids
    assert with_nan.best_iteration_by_horizon == pre_removed.best_iteration_by_horizon


# -- C3: dados insuficientes -------------------------------------------------------


@pytest.mark.contract
def test_c3_insufficient_finite_train_pairs_raise(
    trainer: QuantileModelTrainer,
) -> None:
    nan = float("nan")
    two_finite = {h: (0.01, -0.02, *([nan] * (_N_TRAIN - 2))) for h in _HORIZONS}

    with pytest.raises(ValueError, match=r"C3"):
        _train(trainer, params=_params(min_data_in_leaf=3), train_labels=two_finite)


@pytest.mark.contract
def test_c3_monitor_without_any_finite_label_raises(
    trainer: QuantileModelTrainer,
) -> None:
    nan = float("nan")
    all_nan = {h: tuple([nan] * _N_MONITOR) for h in _HORIZONS}

    with pytest.raises(ValueError, match=r"C3"):
        _train(trainer, early_stop_labels=all_nan)


# -- C4: estrutura inconsistente ---------------------------------------------------


@pytest.mark.contract
def test_c4_row_width_mismatch_raises(trainer: QuantileModelTrainer) -> None:
    bad = (*_TRAIN_ROWS[:-1], _TRAIN_ROWS[-1][:-1])

    with pytest.raises(ValueError, match=r"C4"):
        _train(trainer, train_rows=bad)


@pytest.mark.contract
def test_c4_labels_length_mismatch_raises(trainer: QuantileModelTrainer) -> None:
    short = {h: _TRAIN_LABELS[h][:-1] for h in _HORIZONS}

    with pytest.raises(ValueError, match=r"C4"):
        _train(trainer, train_labels=short)


@pytest.mark.contract
def test_c4_empty_early_stop_raises(trainer: QuantileModelTrainer) -> None:
    with pytest.raises(ValueError, match=r"C4"):
        _train(
            trainer,
            early_stop_rows=(),
            early_stop_labels={h: () for h in _HORIZONS},
        )


@pytest.mark.contract
def test_c4_mismatched_horizon_keys_raise(trainer: QuantileModelTrainer) -> None:
    only_first = {_HORIZONS[0]: _MONITOR_LABELS[_HORIZONS[0]]}

    with pytest.raises(ValueError, match=r"C4"):
        _train(trainer, early_stop_labels=only_first)


@pytest.mark.contract
def test_c4_decision_indices_length_mismatch_raises(
    trainer: QuantileModelTrainer,
) -> None:
    with pytest.raises(ValueError, match=r"C4"):
        _train(trainer, test_decision_indices=(200,))


# -- A6: oráculo de emissão sob features constantes --------------------------------


@pytest.mark.contract
def test_a6_constant_features_collapse_to_type7_quantiles_of_train_labels(
    trainer: QuantileModelTrainer,
) -> None:
    """Sem split possível, a emissão == quantil tipo 7 dos labels de train.

    Real: `boost_from_average` do objetivo quantile inicializa no
    alpha-percentil (interpolação linear == tipo 7) e nenhuma árvore ganha
    split com feature constante. Fake: mesma emissão por construção. Tolerância
    1e-6 (labels float32 no `lgb.Dataset`). Mutante de janela (sem o último
    label — que é outlier de propósito) difere além da tolerância.
    """
    constant_rows = tuple((1.0,) * _N_FEATURES for _ in range(_N_TRAIN))
    labels = {
        h: (*_labels(_N_TRAIN - 1, salt=40_000 * h), 0.25)  # outlier no fim
        for h in _HORIZONS
    }

    result = _train(
        trainer,
        params=_params(min_data_in_leaf=1),
        train_rows=constant_rows,
        train_labels=labels,
        early_stop_rows=tuple((1.0,) * _N_FEATURES for _ in range(_N_MONITOR)),
        test_rows=tuple((1.0,) * _N_FEATURES for _ in range(_N_TEST)),
    )

    for horizon in _HORIZONS:
        expected = sample_quantiles_type7(values=labels[horizon], levels=_LEVELS)
        mutant = sample_quantiles_type7(values=labels[horizon][:-1], levels=_LEVELS)
        # O oráculo discrimina o mutante de janela (ADR 0.0.0021).
        assert expected != pytest.approx(mutant, abs=_ORACLE_TOLERANCE)
        for decision_idx in _DECISIONS:
            grid = result.grids[decision_idx][horizon]
            assert grid == pytest.approx(expected, abs=_ORACLE_TOLERANCE)
            assert grid != pytest.approx(mutant, abs=_ORACLE_TOLERANCE)
