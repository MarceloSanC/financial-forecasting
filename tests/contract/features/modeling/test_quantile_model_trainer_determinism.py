"""Determinismo do GBM: a seed não muda as predições (Stage 5.5, A3 / D4).

O adapter LightGBM fixa `deterministic=True`, `feature_fraction=1.0`,
`bagging_fraction=1.0` e `bagging_freq=0`: sem amostragem de linhas ou colunas,
a seed não tem onde agir. É o que justifica o cohort rodar o GBM UMA vez por
fold, enquanto o TFT roda uma vez por seed e fold (ADR 0.0.0010). Prova empírica com o
adapter real: duas seeds distintas → grades exatamente iguais (`==`, não
`allclose`) e mesma iteração escolhida, para os params default da 5.3, para
pontos das faixas de busca do sweep do GBM e, depois do congelamento, para os
`gbm_params` do cohort AAPL,
lidos de `config/cohorts/aapl_confirmatory.toml` (tabela `[gbm_params]`).
Enquanto o arquivo não tem essa tabela, esse caso fica fora da parametrização;
o id do parâmetro mostra qual conjunto rodou.
"""

from __future__ import annotations

import random
import tomllib
from pathlib import Path

import pytest

from financial_forecasting.features.modeling.adapters.out.lightgbm.lightgbm_quantile_trainer import (  # noqa: E501
    LightgbmQuantileTrainer,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)

_COHORT_FILE = Path(__file__).resolve().parents[4] / "config" / "cohorts" / "aapl_confirmatory.toml"
_FEATURES = ("f_a", "f_b", "f_c")
_HORIZONS = (1, 7)
_LEVELS = (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98)
_SEEDS = (0, 12345)


def _rows(n: int, salt: int) -> tuple[tuple[float, ...], ...]:
    rng = random.Random(salt)
    return tuple(tuple(rng.gauss(0.0, 1.0) for _ in _FEATURES) for _ in range(n))


def _labels(rows: tuple[tuple[float, ...], ...], salt: int) -> tuple[float, ...]:
    """Rótulo com SINAL (combinação linear das features + ruído).

    Com ruído puro o early stopping escolhe a iteração 1 e o teste compararia uma
    árvore só (Checkpoint C); o sinal força modelos de várias árvores.
    """
    rng = random.Random(salt)
    return tuple(
        0.02 * row[0] - 0.01 * row[1] + 0.005 * row[2] + rng.gauss(0.0, 0.002) for row in rows
    )


def _param_sets() -> list[pytest.param]:  # type: ignore[type-arg]
    sets = [
        pytest.param({}, id="defaults-5.3"),
        pytest.param(
            {"num_leaves": 8, "learning_rate": 0.02, "min_data_in_leaf": 10}, id="search-low"
        ),
        pytest.param(
            {"num_leaves": 63, "learning_rate": 0.2, "min_data_in_leaf": 40}, id="search-high"
        ),
    ]
    if _COHORT_FILE.exists():
        frozen = tomllib.loads(_COHORT_FILE.read_text(encoding="utf-8")).get("gbm_params")
        if isinstance(frozen, dict):
            sets.append(
                pytest.param(
                    {key: value for key, value in frozen.items() if key != "seed"},
                    id="aapl-cohort-frozen",
                )
            )
    return sets


@pytest.mark.contract
@pytest.mark.parametrize("overrides", _param_sets())
def test_two_seeds_produce_identical_grids(overrides: dict[str, object]) -> None:
    trainer = LightgbmQuantileTrainer()
    # Escala do fold 0 do cohort AAPL (1641 treino, 252 early_stop): com 120 linhas,
    # `min_data_in_leaf = 97` (congelado) não deixa árvore alguma dividir e o teste
    # cairia na guarda de vacuidade abaixo em vez de comparar modelos reais.
    train_rows, monitor_rows, test_rows = _rows(1641, 1), _rows(252, 2), _rows(15, 3)
    base = {"num_boost_round_max": 40, **overrides}

    results = [
        trainer.train_and_predict(
            params=GbmTrainingParams(seed=seed, **base),  # type: ignore[arg-type]
            feature_names=_FEATURES,
            train_rows=train_rows,
            train_labels_by_horizon={h: _labels(train_rows, 10 * h) for h in _HORIZONS},
            early_stop_rows=monitor_rows,
            early_stop_labels_by_horizon={h: _labels(monitor_rows, 20 * h) for h in _HORIZONS},
            test_rows=test_rows,
            test_decision_indices=tuple(range(15)),
            quantile_levels=_LEVELS,
        )
        for seed in _SEEDS
    ]

    first, second = results
    # Sem isto o teste pode degradar em silêncio para "compara uma árvore só".
    assert max(first.best_iteration_by_horizon.values()) > 1
    assert first.grids == second.grids
    assert first.best_iteration_by_horizon == second.best_iteration_by_horizon
    # A perda de early_stop vem da métrica de avaliação do LightGBM e varia no
    # último ulp entre EXECUÇÕES (mesmo com a mesma seed), sem efeito nas
    # predições nem na iteração escolhida — o que o cohort persiste é exato. Os
    # sweeps arredondam o objetivo antes de informá-lo ao estudo (§7).
    assert first.early_stop_loss_by_horizon == pytest.approx(
        second.early_stop_loss_by_horizon, rel=1e-12
    )
