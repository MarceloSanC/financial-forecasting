"""Caracterização das 4 leituras do dataset de treino (Stage 5.5, Task 04).

Fixa, ANTES da extração para o grid único (Tasks 05-10), o que cada use case
entrega aos passos seguintes a partir do par read-only `("processed",
"dataset_tft")`: timestamps ISO, `target_return`, sessões e matriz de features,
em ordem cronológica, só do ativo do escopo, com `None` de feature virando NaN.
Também fixa os erros: dataset vazio (código de cada use case — C7 nas baselines,
C1 nos treinadores) e coluna esperada ausente (C6).

Chama o `_load_dataset` de cada use case com um `self` mínimo (só o store): a
caracterização é da função de leitura, não do use case inteiro. Quando a leitura
vira o grid único, estes testes passam a exercitar o caminho novo com as mesmas
expectativas (fora do corte do prefixo, que é comportamento novo declarado).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from financial_forecasting.features.modeling.application.use_cases.run_baselines import (
    RunBaselines,
)
from financial_forecasting.features.modeling.application.use_cases.run_tft_sweep import (
    RunTftSweep,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    TrainGbmQuantile,
    expected_feature_names,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    TrainTft,
    known_feature_names,
    unknown_feature_names,
)
from financial_forecasting.features.modeling.domain.exceptions.cohort import (
    InteriorMissingValuesError,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import ScopeSpec
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

_FEATURES = ("f_a", "f_b")
_SCOPE = ScopeSpec(asset_id="AAPL", feature_set_name="fs_all", max_horizon=1)


def _row(day: int, target: float, f_a: float | None, f_b: float | None) -> dict[str, object]:
    return {
        "timestamp": datetime(2024, 1, day, tzinfo=UTC),
        "asset_id": "AAPL",
        "target_return": target,
        "f_a": f_a,
        "f_b": f_b,
        "unused_column": "ignored",
    }


def _store(rows: list[dict[str, object]] | None = None) -> FakeMedallionStore:
    store = FakeMedallionStore()
    seeded = rows if rows is not None else [
        _row(4, 0.03, 3.0, 30.0),
        _row(2, 0.01, 1.0, 10.0),
        _row(3, 0.02, 2.0, 20.0),
    ]
    if seeded:
        store.seed_read_only(layer="processed", table="dataset_tft", asset="AAPL", rows=seeded)
    other = {**_row(5, 9.9, 9.0, 90.0), "asset_id": "MSFT"}
    store.seed_read_only(layer="processed", table="dataset_tft", asset="MSFT", rows=[other])
    return store


def _self(store: FakeMedallionStore) -> SimpleNamespace:
    return SimpleNamespace(_store=store)


_Loader = Callable[..., Any]
_load_baselines: _Loader = RunBaselines._load_dataset
_load_sweep: _Loader = RunTftSweep._load_dataset
_TRAINER_LOADERS: list[_Loader] = [TrainGbmQuantile._load_dataset, TrainTft._load_dataset]
_FEATURE_LOADERS: list[_Loader] = [*_TRAINER_LOADERS, RunTftSweep._load_dataset]

_EXPECTED_TIMESTAMPS = (
    "2024-01-02T00:00:00+00:00",
    "2024-01-03T00:00:00+00:00",
    "2024-01-04T00:00:00+00:00",
)
_EXPECTED_RETURNS = (0.01, 0.02, 0.03)
_EXPECTED_SESSIONS = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))


def _assert_matrix(matrix: tuple[tuple[float, ...], ...]) -> None:
    assert matrix == ((1.0, 10.0), (2.0, 20.0), (3.0, 30.0))


# -- happy path (fixture sem valor ausente): ordem cronológica, só o ativo -------


def test_run_baselines_reads_timestamps_returns_sessions() -> None:
    loaded = _load_baselines(_self(_store()), _SCOPE)

    assert loaded == (_EXPECTED_TIMESTAMPS, _EXPECTED_RETURNS, _EXPECTED_SESSIONS)


@pytest.mark.parametrize("load", _TRAINER_LOADERS, ids=["gbm", "tft"])
def test_trainers_read_timestamps_returns_sessions_matrix(load: _Loader) -> None:
    timestamps, returns, sessions, matrix = load(_self(_store()), _SCOPE, _FEATURES)

    assert timestamps == _EXPECTED_TIMESTAMPS
    assert returns == _EXPECTED_RETURNS
    assert sessions == _EXPECTED_SESSIONS
    _assert_matrix(matrix)


def test_tft_sweep_reads_returns_sessions_matrix_without_timestamps() -> None:
    returns, sessions, matrix = _load_sweep(_self(_store()), _SCOPE, _FEATURES)

    assert returns == _EXPECTED_RETURNS
    assert sessions == _EXPECTED_SESSIONS
    _assert_matrix(matrix)


# -- erros: dataset vazio (código por use case) e coluna ausente (C6) -----------


def test_run_baselines_empty_dataset_raises_c7() -> None:
    with pytest.raises(ValueError, match="C7"):
        _load_baselines(_self(_store([])), _SCOPE)


@pytest.mark.parametrize("load", _FEATURE_LOADERS, ids=["gbm", "tft", "sweep"])
def test_feature_readers_empty_dataset_raises_c1(load: _Loader) -> None:
    with pytest.raises(ValueError, match="C1"):
        load(_self(_store([])), _SCOPE, _FEATURES)


@pytest.mark.parametrize("load", _FEATURE_LOADERS, ids=["gbm", "tft", "sweep"])
def test_feature_readers_missing_column_raises_c6(load: _Loader) -> None:
    with pytest.raises(ValueError, match=r"C6") as excinfo:
        load(_self(_store()), _SCOPE, ("f_a", "f_missing"))

    assert "f_missing" in str(excinfo.value)


def test_run_baselines_ignores_feature_columns() -> None:
    """As baselines hoje não leem features: coluna de feature ausente não ergue."""
    rows = [
        {"timestamp": datetime(2024, 1, 2, tzinfo=UTC), "asset_id": "AAPL", "target_return": 0.01}
    ]

    loaded = _load_baselines(_self(_store(rows)), _SCOPE)

    assert loaded[1] == (0.01,)


@pytest.mark.parametrize("load", _FEATURE_LOADERS, ids=["gbm", "tft", "sweep"])
def test_feature_readers_reject_non_numeric_target(load: _Loader) -> None:
    rows = [_row(2, 0.01, 1.0, 10.0), {**_row(3, 0.0, 2.0, 20.0), "target_return": "0.02"}]

    with pytest.raises(ValueError, match="target_return"):
        load(_self(_store(rows)), _SCOPE, _FEATURES)


# -- comportamento que MUDA por desenho nas Tasks 07-10 (grid único, D11) --------


_NOT_YET_ON_GRID: list[_Loader] = [RunTftSweep._load_dataset]
_ON_GRID: list[_Loader] = [TrainGbmQuantile._load_dataset, TrainTft._load_dataset]


@pytest.mark.parametrize("load", _NOT_YET_ON_GRID, ids=["sweep"])
def test_feature_none_becomes_nan_before_the_single_grid(load: _Loader) -> None:
    """Hoje `None` de feature vira NaN e a linha fica no treino.

    Com o grid único, `None` no prefixo é cortado e `None` no interior ergue
    `InteriorMissingValuesError` (ADR 5.5.0004): este teste é reescrito nas
    Tasks 07-10 para o comportamento novo, nunca apagado sem substituto.
    """
    rows = [_row(2, 0.01, 1.0, None), _row(3, 0.02, 2.0, 20.0)]

    matrix = load(_self(_store(rows)), _SCOPE, _FEATURES)[-1]

    assert matrix[0][0] == 1.0
    assert math.isnan(matrix[0][1])


def test_gbm_and_tft_consume_the_same_modeling_columns() -> None:
    """GBM e TFT derivam as colunas por caminhos diferentes, mas o conjunto é o mesmo.

    GBM: `expected_feature_names()` (registry habilitado + calendário); TFT/sweep:
    `unknown_feature_names() + known_feature_names()`. O grid único corta pelo
    mesmo conjunto para todos (I9); se as derivações divergirem, este teste acusa.
    """
    tft_columns = unknown_feature_names() + known_feature_names()

    assert set(expected_feature_names()) == set(tft_columns)
    assert len(tft_columns) == len(set(tft_columns))


@pytest.mark.parametrize("load", _ON_GRID, ids=["gbm", "tft"])
def test_single_grid_trims_the_warm_up_prefix(load: _Loader) -> None:
    """No grid único, `None` no prefixo sai do treino em vez de virar NaN (D11)."""
    rows = [_row(2, 0.01, 1.0, None), _row(3, 0.02, 2.0, 20.0), _row(4, 0.03, 3.0, 30.0)]

    timestamps, returns, sessions, matrix = load(_self(_store(rows)), _SCOPE, _FEATURES)

    assert timestamps == _EXPECTED_TIMESTAMPS[1:]
    assert returns == _EXPECTED_RETURNS[1:]
    assert sessions == _EXPECTED_SESSIONS[1:]
    assert matrix == ((2.0, 20.0), (3.0, 30.0))


@pytest.mark.parametrize("load", _ON_GRID, ids=["gbm", "tft"])
def test_single_grid_rejects_interior_missing_value(load: _Loader) -> None:
    rows = [_row(2, 0.01, 1.0, 10.0), _row(3, 0.02, 2.0, None), _row(4, 0.03, 3.0, 30.0)]

    with pytest.raises(InteriorMissingValuesError):
        load(_self(_store(rows)), _SCOPE, _FEATURES)
