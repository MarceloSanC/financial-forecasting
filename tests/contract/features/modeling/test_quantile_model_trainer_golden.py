"""Golden do `QuantileModelTrainer` — trava das DUAS pernas antes do refactor.

Rede de regressão da issue #71. A movimentação da validação estrutural C4
(`_validate_structure`, 49 linhas idênticas entre adapter e fake) para o
serviço de domínio `quantile_training_validation` é **refactor puro**: nem a
emissão nem o texto das mensagens de erro pode mudar. Este módulo congela, em
literais, o que foi capturado ANTES da movimentação.

Duas travas:

1. **Emissão** — grade por decisão x horizonte e `best_iteration_by_horizon`,
   com golden POR PERNA (fake e real divergem legitimamente no modelo: quantil
   empírico tipo 7 vs K boosters). A perna fake é aritmética stdlib e é
   comparada por igualdade exata; a perna real usa tolerância relativa `1e-9`
   por vir do LightGBM (que carrega labels em float32), ordens de grandeza
   mais apertada que qualquer mudança de lógica.
2. **Fronteira C4** — as 10 bordas estruturais (nomes de feature vazios,
   horizontes descasados, early_stop vazio, larguras de linha, comprimentos de
   label, alinhamento de `test_decision_indices`) erguem `ValueError` com a
   mensagem IDÊNTICA nas duas pernas; o texto exato está congelado. É
   exatamente o bloco que a issue #71 manda extrair.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from financial_forecasting.features.modeling.adapters.out.lightgbm.lightgbm_quantile_trainer import (  # noqa: E501
    LightgbmQuantileTrainer,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from tests.fakes.features.modeling.in_memory_quantile_model_trainer import (
    FakeQuantileModelTrainer,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (  # noqa: E501
        QuantileModelTrainer,
        QuantileTrainingResult,
    )


def _build_fake() -> QuantileModelTrainer:
    return FakeQuantileModelTrainer()


def _build_real() -> QuantileModelTrainer:
    return LightgbmQuantileTrainer()


_BUILDERS: dict[str, Callable[[], QuantileModelTrainer]] = {
    "fake": _build_fake,
    "real": _build_real,
}
_LEGS = ("fake", "real")

# Tolerância da perna real: o LightGBM guarda os labels em float32 e a predição
# vem de árvores treinadas numericamente. 1e-9 é ordens de grandeza mais
# apertado que qualquer mudança de LÓGICA (o teste do oráculo A6 do contrato
# usa 1e-6 justamente por causa do float32).
_REAL_RTOL = 1e-9

# -- fixture determinística (idêntica à do contract test) ----------------------

_LEVELS = (0.1, 0.5, 0.9)
_HORIZONS = (1, 2)
_CEILING = 10
_SEED = 7
_N_TRAIN, _N_MONITOR, _N_TEST, _N_FEATURES = 40, 12, 3, 3
_FEATURE_NAMES = tuple(f"f{i}" for i in range(_N_FEATURES))
_DECISIONS = (200, 201, 202)


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
_PARAMS = GbmTrainingParams(seed=_SEED, num_boost_round_max=_CEILING, min_data_in_leaf=3)


def _train(trainer: QuantileModelTrainer, **overrides: Any) -> QuantileTrainingResult:  # noqa: ANN401
    """Chama o port com a fixture canônica, aplicando os overrides da borda."""
    kwargs: dict[str, Any] = {
        "params": _PARAMS,
        "feature_names": _FEATURE_NAMES,
        "train_rows": _TRAIN_ROWS,
        "train_labels_by_horizon": _TRAIN_LABELS,
        "early_stop_rows": _MONITOR_ROWS,
        "early_stop_labels_by_horizon": _MONITOR_LABELS,
        "test_rows": _TEST_ROWS,
        "test_decision_indices": _DECISIONS,
        "quantile_levels": _LEVELS,
    }
    kwargs.update(overrides)
    return trainer.train_and_predict(**kwargs)


# -- golden da emissão (por perna) ---------------------------------------------

_FAKE_H1 = (-0.004303769404999912, -4.299955209717154e-05, 0.0036631971187889583)
_FAKE_H2 = (-0.004398747216444463, -8.605659008026123e-05, 0.003832525704987348)

_GOLDEN_GRIDS: dict[str, dict[int, dict[int, tuple[float, ...]]]] = {
    "fake": {
        200: {1: _FAKE_H1, 2: _FAKE_H2},
        201: {1: _FAKE_H1, 2: _FAKE_H2},
        202: {1: _FAKE_H1, 2: _FAKE_H2},
    },
    "real": {
        200: {
            1: (
                -0.004287132457623417,
                -0.0001335597575234715,
                0.0035384177649971536,
            ),
            2: (
                -0.00401142948750164,
                0.00013325419220200276,
                0.0038347882387284684,
            ),
        },
        201: {
            1: (
                -0.004162353485927622,
                1.9832004181807863e-05,
                0.003704789715968615,
            ),
            2: (
                -0.0037374703340128114,
                -0.00027391825150698424,
                0.0035045510097471083,
            ),
        },
        202: {
            1: (
                -0.004287132457623417,
                -0.00010583110051811674,
                0.0035384177649971536,
            ),
            2: (
                -0.00401142948750164,
                -2.4114034778904162e-05,
                0.0039762044157707266,
            ),
        },
    },
}

_GOLDEN_BEST_ITERATION: dict[str, dict[int, int]] = {
    "fake": {1: 1, 2: 1},
    "real": {1: 1, 2: 3},
}

# -- golden da fronteira C4 (mensagem EXATA, idêntica nas duas pernas) ----------

_C4_CASES: dict[str, dict[str, Any]] = {
    "empty_feature_names": {"feature_names": ()},
    "empty_train_labels": {
        "train_labels_by_horizon": {},
        "early_stop_labels_by_horizon": {},
    },
    "horizon_sets_mismatch": {
        "early_stop_labels_by_horizon": {
            1: _MONITOR_LABELS[1],
            3: _MONITOR_LABELS[2],
        }
    },
    "empty_early_stop_rows": {"early_stop_rows": ()},
    "decisions_length_mismatch": {"test_decision_indices": (200, 201)},
    "train_row_width": {"train_rows": (_TRAIN_ROWS[0][:2], *_TRAIN_ROWS[1:])},
    "early_stop_row_width": {"early_stop_rows": (_MONITOR_ROWS[0][:2], *_MONITOR_ROWS[1:])},
    "test_row_width": {"test_rows": (_TEST_ROWS[0][:2], *_TEST_ROWS[1:])},
    "train_labels_length": {
        "train_labels_by_horizon": {1: _TRAIN_LABELS[1][:-1], 2: _TRAIN_LABELS[2]}
    },
    "early_stop_labels_length": {
        "early_stop_labels_by_horizon": {
            1: _MONITOR_LABELS[1][:-1],
            2: _MONITOR_LABELS[2],
        }
    },
}

_GOLDEN_C4_MESSAGES: dict[str, str] = {
    "empty_feature_names": "feature_names must be non-empty (C4)",
    "empty_train_labels": "train_labels_by_horizon must be non-empty (C4)",
    "horizon_sets_mismatch": (
        "train and early_stop label horizons must match; got [1, 2] vs [1, 3] (C4)"
    ),
    "empty_early_stop_rows": ("early_stop_rows must be non-empty — no monitor, no m* (C4)"),
    "decisions_length_mismatch": ("test_decision_indices length 2 != test_rows length 3 (C4)"),
    "train_row_width": "train_rows[0] width 2 != len(feature_names)=3 (C4)",
    "early_stop_row_width": "early_stop_rows[0] width 2 != len(feature_names)=3 (C4)",
    "test_row_width": "test_rows[0] width 2 != len(feature_names)=3 (C4)",
    "train_labels_length": ("train labels for horizon 1 length 39 != rows length 40 (C4)"),
    "early_stop_labels_length": (
        "early_stop labels for horizon 1 length 11 != rows length 12 (C4)"
    ),
}


# -- travas --------------------------------------------------------------------


@pytest.mark.contract
@pytest.mark.parametrize("leg", _LEGS)
def test_emission_matches_the_frozen_grid_of_its_own_leg(leg: str) -> None:
    """A grade emitida e o `m*` batem com o golden — fake exato, real a 1e-9."""
    result = _train(_BUILDERS[leg]())

    tolerance = 0.0 if leg == "fake" else _REAL_RTOL
    golden = _GOLDEN_GRIDS[leg]
    assert set(result.grids) == set(golden)
    for decision, by_horizon in golden.items():
        for horizon, grid in by_horizon.items():
            assert result.grids[decision][horizon] == pytest.approx(
                grid, rel=tolerance, abs=tolerance
            )
    assert dict(result.best_iteration_by_horizon) == _GOLDEN_BEST_ITERATION[leg]


@pytest.mark.contract
@pytest.mark.parametrize("leg", _LEGS)
@pytest.mark.parametrize("case", sorted(_C4_CASES))
def test_c4_boundary_message_is_frozen_and_identical_in_both_legs(leg: str, case: str) -> None:
    """Cada borda C4 ergue `ValueError` com o texto EXATO congelado, nas 2 pernas."""
    with pytest.raises(ValueError) as raised:
        _train(_BUILDERS[leg](), **_C4_CASES[case])

    assert str(raised.value) == _GOLDEN_C4_MESSAGES[case]
