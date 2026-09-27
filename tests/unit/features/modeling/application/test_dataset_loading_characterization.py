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
    modeling_columns,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    TrainTft,
    known_feature_names,
    unknown_feature_names,
)
from financial_forecasting.features.modeling.domain.exceptions.cohort import (
    InteriorMissingValuesError,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    build_training_grid,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import ScopeSpec
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

_FEATURES = ("f_a", "f_b")
_SHA256_HEX_LEN = 64
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


def _with_modeling_columns(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Completa as rows com todas as colunas de modelagem do registry (valor finito)."""
    return [{**{name: 1.0 for name in modeling_columns()}, **row} for row in rows]


def _self(store: FakeMedallionStore) -> SimpleNamespace:
    return SimpleNamespace(_store=store, _hasher=CanonicalJsonHasher())


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
    rows = _with_modeling_columns(
        [_row(4, 0.03, 3.0, 30.0), _row(2, 0.01, 1.0, 10.0), _row(3, 0.02, 2.0, 20.0)]
    )

    loaded = _load_baselines(_self(_store(rows)), _SCOPE)

    assert loaded == (_EXPECTED_TIMESTAMPS, _EXPECTED_RETURNS, _EXPECTED_SESSIONS)


@pytest.mark.parametrize("load", _TRAINER_LOADERS, ids=["gbm", "tft"])
def test_trainers_read_timestamps_returns_sessions_matrix(load: _Loader) -> None:
    timestamps, returns, sessions, matrix = load(_self(_store()), _SCOPE, _FEATURES)

    assert timestamps == _EXPECTED_TIMESTAMPS
    assert returns == _EXPECTED_RETURNS
    assert sessions == _EXPECTED_SESSIONS
    _assert_matrix(matrix)


def test_tft_sweep_reads_returns_sessions_matrix_and_fingerprint() -> None:
    returns, sessions, matrix, fingerprint = _load_sweep(_self(_store()), _SCOPE, _FEATURES)

    assert returns == _EXPECTED_RETURNS
    assert sessions == _EXPECTED_SESSIONS
    _assert_matrix(matrix)
    assert len(fingerprint) == _SHA256_HEX_LEN


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


def test_run_baselines_requires_the_modeling_columns() -> None:
    """No grid único as baselines exigem as colunas de modelagem (C6) — antes as ignoravam."""
    rows = [
        {"timestamp": datetime(2024, 1, 2, tzinfo=UTC), "asset_id": "AAPL", "target_return": 0.01}
    ]

    with pytest.raises(ValueError, match="C6"):
        _load_baselines(_self(_store(rows)), _SCOPE)


@pytest.mark.parametrize("load", _FEATURE_LOADERS, ids=["gbm", "tft", "sweep"])
def test_feature_readers_reject_non_numeric_target(load: _Loader) -> None:
    rows = [_row(2, 0.01, 1.0, 10.0), {**_row(3, 0.0, 2.0, 20.0), "target_return": "0.02"}]

    with pytest.raises(ValueError, match="target_return"):
        load(_self(_store(rows)), _SCOPE, _FEATURES)


# -- comportamento que MUDA por desenho nas Tasks 07-10 (grid único, D11) --------


_ON_GRID: list[_Loader] = [TrainGbmQuantile._load_dataset, TrainTft._load_dataset]


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


def test_tft_sweep_trims_prefix_and_fingerprints_the_trimmed_grid() -> None:
    """Sweep no grid único: corta o prefixo e a impressão digital muda com o dado."""
    trimmed_rows = [_row(2, 0.01, 1.0, None), _row(3, 0.02, 2.0, 20.0), _row(4, 0.03, 3.0, 30.0)]
    changed_rows = [_row(3, 0.02, 2.0, 20.0), _row(4, 0.03, 3.0, 31.0)]

    returns, sessions, matrix, fingerprint = _load_sweep(
        _self(_store(trimmed_rows)), _SCOPE, _FEATURES
    )
    *_, same_content = _load_sweep(
        _self(_store([_row(3, 0.02, 2.0, 20.0), _row(4, 0.03, 3.0, 30.0)])), _SCOPE, _FEATURES
    )
    *_, other_content = _load_sweep(_self(_store(changed_rows)), _SCOPE, _FEATURES)

    assert returns == _EXPECTED_RETURNS[1:]
    assert sessions == _EXPECTED_SESSIONS[1:]
    assert matrix == ((2.0, 20.0), (3.0, 30.0))
    assert fingerprint == same_content
    assert fingerprint != other_content


def test_baselines_start_on_the_same_row_as_the_models() -> None:
    """I9: com aquecimento numa coluna do registry, baselines e GBM começam juntos."""
    warm_up_column = modeling_columns()[0]
    rows = _with_modeling_columns(
        [_row(2, 0.01, 1.0, 10.0), _row(3, 0.02, 2.0, 20.0), _row(4, 0.03, 3.0, 30.0)]
    )
    rows[0][warm_up_column] = None

    baselines_sessions = _load_baselines(_self(_store(rows)), _SCOPE)[2]
    gbm_sessions = TrainGbmQuantile._load_dataset(
        _self(_store(rows)), _SCOPE, expected_feature_names()
    )[2]

    assert baselines_sessions == gbm_sessions == _EXPECTED_SESSIONS[1:]


def test_gbm_and_tft_consume_the_same_modeling_columns() -> None:
    """GBM e TFT derivam as colunas por caminhos diferentes, mas o conjunto é o mesmo.

    GBM: `expected_feature_names()` (registry habilitado + calendário); TFT/sweep:
    `unknown_feature_names() + known_feature_names()`. O grid único corta pelo
    mesmo conjunto para todos (I9); se as derivações divergirem, este teste acusa.
    """
    tft_columns = unknown_feature_names() + known_feature_names()

    assert set(expected_feature_names()) == set(tft_columns)
    assert len(tft_columns) == len(set(tft_columns))


def test_tft_sweep_rejects_interior_missing_value() -> None:
    rows = [_row(2, 0.01, 1.0, 10.0), _row(3, 0.02, 2.0, None), _row(4, 0.03, 3.0, 30.0)]

    with pytest.raises(InteriorMissingValuesError):
        _load_sweep(_self(_store(rows)), _SCOPE, _FEATURES)


def test_sweep_fingerprint_equals_the_fingerprint_over_modeling_columns() -> None:
    """I4: a impressão digital do sweep (ordem do TFT) = a calculada sobre `modeling_columns()`.

    É a igualdade que o `run` confere entre a proveniência do sweep e o dado do
    cohort; a ordem das colunas não pode fazê-la falhar sem mudança real no dado.
    """
    rows = _with_modeling_columns(
        [_row(2, 0.01, 1.0, 10.0), _row(3, 0.02, 2.0, 20.0), _row(4, 0.03, 3.0, 30.0)]
    )
    # Ordem invertida: simula uma spec `known` fora da ordem do registry — o caso
    # em que a ordem do TFT deixa de coincidir com a de `modeling_columns()`.
    tft_features = tuple(reversed(unknown_feature_names() + known_feature_names()))

    *_, sweep_fingerprint = _load_sweep(_self(_store(rows)), _SCOPE, tft_features)
    grid = build_training_grid(rows, columns=modeling_columns())
    cohort_fingerprint = DatasetContentFingerprint.compute(
        hasher=CanonicalJsonHasher(),
        asset_id=_SCOPE.asset_id,
        timestamps=grid.timestamps_iso(),
        columns={name: grid.column(name) for name in modeling_columns()},
    )

    assert sweep_fingerprint == cohort_fingerprint.value
