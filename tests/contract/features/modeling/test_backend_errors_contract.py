"""Contract test #84 — "a biblioteca falhou" ergue o MESMO tipo nas duas pernas dos 4 ports.

Os ports do caminho confirmatório (`BaselineForecaster`, `QuantileModelTrainer`,
`TftTrainer`, `HyperparameterSearch`) passam a declarar uma exceção nomeada para a
falha do backend (`ModelTrainingError` / `HyperparameterSearchError`, subclasses de
`DomainError`), com a original em `__cause__`. Sem uma suíte `[fake, real]` que force
a falha, a tradução seria inverificável: o fake precisa SIMULAR (hook
`simulate_backend_failure`, no ponto em que o real chama a lib) e a perna real precisa
FALHAR DE VERDADE onde dá, ou ter a chamada à lib substituída por uma que ergue o tipo
da lib onde não dá:

- **TFT** — falha GENUÍNA: `NaN` no painel passa pela regra do port (C4 não checa
  finitude de feature) e a `TimeSeriesDataSet` ergue `ValueError` da lib → traduzido.
- **Baselines** — o seam `fit_ar1` do adapter recebe um estimador que ergue
  `RuntimeError("No ARIMA model able to be estimated")` (a mensagem real da lib).
- **LightGBM** — `lgb.train` substituído (monkeypatch da função da LIB, não de um port)
  por um que ergue `LightGBMError` — o tipo que `alpha` fora de (0, 1) produz de fato.
- **Optuna** — `Study.ask` substituído por um que ergue `StorageInternalError`
  (subclasse de `OptunaError`).

Em todas: o tipo do contrato, `__cause__` preservado (na real, a exceção da lib), e a
ordem — a regra do port ERGUE `ValueError` ANTES de a lib ser tocada, então uma
estrutura inválida continua `ValueError` mesmo com o backend quebrado.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any

import optuna
import pytest
from lightgbm.basic import LightGBMError
from optuna.exceptions import StorageInternalError

from financial_forecasting.features.modeling.adapters.out.lightgbm import (
    lightgbm_quantile_trainer as gbm_module,
)
from financial_forecasting.features.modeling.adapters.out.lightgbm.lightgbm_quantile_trainer import (  # noqa: E501
    LightgbmQuantileTrainer,
)
from financial_forecasting.features.modeling.adapters.out.optuna.optuna_search import OptunaSearch
from financial_forecasting.features.modeling.adapters.out.pytorch_forecasting.pf_tft_trainer import (  # noqa: E501
    PfTftTrainer,
)
from financial_forecasting.features.modeling.adapters.out.statsforecast.statsforecast_baseline_forecaster import (  # noqa: E501
    StatsforecastBaselineForecaster,
)
from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    SearchDimension,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.domain.exceptions.backend import (
    HyperparameterSearchError,
    ModelTrainingError,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BaselineSpec,
)
from financial_forecasting.shared.domain.exceptions.base import DomainError
from tests.fakes.features.modeling.in_memory_baseline_forecaster import FakeBaselineForecaster
from tests.fakes.features.modeling.in_memory_hyperparameter_search import (
    InMemoryHyperparameterSearch,
)
from tests.fakes.features.modeling.in_memory_quantile_model_trainer import (
    FakeQuantileModelTrainer,
)
from tests.fakes.features.modeling.in_memory_tft_trainer import InMemoryTftTrainer

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

pytestmark = pytest.mark.contract

_LEGS = ("fake", "real")
_SIMULATED = "simulated backend failure"
_LEVELS = (0.1, 0.5, 0.9)


def test_contract_exceptions_are_domain_errors() -> None:
    """As duas exceções nomeadas são `DomainError` — vocabulário do domínio, não infra."""
    assert issubclass(ModelTrainingError, DomainError)
    assert issubclass(HyperparameterSearchError, DomainError)
    assert not issubclass(ModelTrainingError, ValueError)
    assert not issubclass(HyperparameterSearchError, ValueError)


# =============================================================== BaselineForecaster


def _ar1_returns(n: int = 60) -> tuple[float, ...]:
    rng = random.Random(7)
    mu, phi, sigma_eps = 0.001, 0.5, 0.01
    values = [mu + rng.gauss(0.0, sigma_eps)]
    for _ in range(n - 1):
        values.append(mu + phi * (values[-1] - mu) + rng.gauss(0.0, sigma_eps))
    return tuple(values)


def _failing_fit_ar1(train: Sequence[float]) -> tuple[float, float, float]:
    """A mensagem REAL de `statsforecast.arima` quando nenhum modelo é estimável."""
    msg = "No ARIMA model able to be estimated"
    raise RuntimeError(msg)


def _baseline(leg: str, *, broken: bool) -> Any:  # noqa: ANN401
    if leg == "fake":
        return FakeBaselineForecaster(simulate_backend_failure=_SIMULATED if broken else None)
    return StatsforecastBaselineForecaster(fit_ar1=_failing_fit_ar1 if broken else None)


def _forecast(forecaster: Any, **overrides: Any) -> Any:  # noqa: ANN401
    kwargs: dict[str, Any] = {
        "spec": BaselineSpec(family="ar1"),
        "returns": _ar1_returns(),
        "train_end_idx": 39,
        "decision_indices": (48, 52),
        "horizons": (1, 3),
        "quantile_levels": _LEVELS,
    }
    kwargs.update(overrides)
    return forecaster.forecast(**kwargs)


class TestBaselineForecasterBackendFailure:
    @pytest.mark.parametrize("leg", _LEGS)
    def test_backend_failure_raises_the_contract_type_with_cause(self, leg: str) -> None:
        with pytest.raises(ModelTrainingError) as raised:
            _forecast(_baseline(leg, broken=True))

        assert raised.value.__cause__ is not None
        if leg == "real":
            assert isinstance(raised.value.__cause__, RuntimeError)
            assert "No ARIMA model" in str(raised.value)

    @pytest.mark.parametrize("leg", _LEGS)
    def test_port_rule_still_raises_value_error_before_the_backend(self, leg: str) -> None:
        """C1 (train curto) é regra do port: `ValueError` mesmo com o backend quebrado."""
        with pytest.raises(ValueError, match=r"\(C1\)"):
            _forecast(_baseline(leg, broken=True), train_end_idx=1, decision_indices=(3,))

    @pytest.mark.parametrize("leg", _LEGS)
    def test_healthy_backend_control(self, leg: str) -> None:
        assert _forecast(_baseline(leg, broken=False))


# =============================================================== QuantileModelTrainer

_N_FEATURES = 3
_FEATURE_NAMES = tuple(f"f{i}" for i in range(_N_FEATURES))


def _lcg(seed: int) -> float:
    return ((seed * 1103515245 + 12345) % 2**31) / 2**31 - 0.5


def _rows(count: int, *, salt: int) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple(_lcg(salt + row * _N_FEATURES + col) for col in range(_N_FEATURES))
        for row in range(count)
    )


def _labels(count: int, *, salt: int) -> tuple[float, ...]:
    return tuple(0.01 * _lcg(salt + i) for i in range(count))


def _gbm_kwargs(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    kwargs: dict[str, Any] = {
        "params": GbmTrainingParams(seed=7, num_boost_round_max=10, min_data_in_leaf=3),
        "feature_names": _FEATURE_NAMES,
        "train_rows": _rows(40, salt=3),
        "train_labels_by_horizon": {h: _labels(40, salt=70_000 * h) for h in (1, 2)},
        "early_stop_rows": _rows(12, salt=9_000),
        "early_stop_labels_by_horizon": {h: _labels(12, salt=90_000 * h) for h in (1, 2)},
        "test_rows": _rows(3, salt=13_000),
        "test_decision_indices": (200, 201, 202),
        "quantile_levels": _LEVELS,
    }
    kwargs.update(overrides)
    return kwargs


def _raising_lgb_train(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
    """O tipo e a mensagem que o C++ do LightGBM produz para `alpha` fora de (0, 1)."""
    msg = "Check failed: alpha_ > 0 && alpha_ < 1 at regression_objective.hpp"
    raise LightGBMError(msg)


def _gbm(leg: str, *, broken: bool, monkeypatch: pytest.MonkeyPatch) -> Any:  # noqa: ANN401
    if leg == "fake":
        return FakeQuantileModelTrainer(simulate_backend_failure=_SIMULATED if broken else None)
    if broken:
        monkeypatch.setattr(gbm_module.lgb, "train", _raising_lgb_train)
    return LightgbmQuantileTrainer()


class TestQuantileModelTrainerBackendFailure:
    @pytest.mark.parametrize("leg", _LEGS)
    def test_backend_failure_raises_the_contract_type_with_cause(
        self, leg: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        trainer = _gbm(leg, broken=True, monkeypatch=monkeypatch)

        with pytest.raises(ModelTrainingError) as raised:
            trainer.train_and_predict(**_gbm_kwargs())

        assert raised.value.__cause__ is not None
        if leg == "real":
            assert isinstance(raised.value.__cause__, LightGBMError)
            assert "alpha_" in str(raised.value)

    @pytest.mark.parametrize("leg", _LEGS)
    def test_port_rule_still_raises_value_error_before_the_backend(
        self, leg: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """C4 (largura de linha) é regra do port: `ValueError` mesmo com a lib quebrada."""
        trainer = _gbm(leg, broken=True, monkeypatch=monkeypatch)
        rows = _rows(40, salt=3)
        bad = (rows[0][:2], *rows[1:])

        with pytest.raises(ValueError, match=r"\(C4\)"):
            trainer.train_and_predict(**_gbm_kwargs(train_rows=bad))

    @pytest.mark.parametrize("leg", _LEGS)
    def test_healthy_backend_control(self, leg: str, monkeypatch: pytest.MonkeyPatch) -> None:
        result = _gbm(leg, broken=False, monkeypatch=monkeypatch).train_and_predict(**_gbm_kwargs())
        assert result.grids


# =============================================================== TftTrainer

_PANEL = 54
_TFT_PARAMS = TftTrainingParams(
    seed=7,
    max_encoder_length=12,
    hidden_size=4,
    attention_head_size=1,
    hidden_continuous_size=2,
    max_epochs=2,
    patience=2,
    batch_size=8,
    learning_rate=0.01,
)


def _panel() -> tuple[list[list[float]], list[float]]:
    rows = [
        [0.01 * index, 50.0 + index, float(index % 5), float(index % 12 + 1)]
        for index in range(_PANEL)
    ]
    target = [0.001 * index for index in range(_PANEL)]
    return rows, target


def _tft_kwargs(tmp_path: Path, **overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    rows, target = _panel()
    kwargs: dict[str, Any] = {
        "params": _TFT_PARAMS,
        "feature_names": ("close_return", "rsi_14", "day_of_week", "month"),
        "known_feature_names": ("day_of_week", "month"),
        "rows": rows,
        "target": target,
        "train_decision_indices": tuple(range(30)),
        "early_stop_decision_indices": tuple(range(33, 38)),
        "test_decision_indices": tuple(range(49, 54)),
        "max_horizon": 2,
        "horizons": (1, 2),
        "quantile_levels": _LEVELS,
        "artifact_dir": str(tmp_path / "ckpt"),
    }
    kwargs.update(overrides)
    return kwargs


def _rows_with_nan() -> list[list[float]]:
    rows, _ = _panel()
    rows[0] = [math.nan] * 4
    return rows


class TestTftTrainerBackendFailure:
    def test_real_backend_failure_is_genuine_nan_in_the_panel(self, tmp_path: Path) -> None:
        """A lib (`TimeSeriesDataSet`) ergue `ValueError` para NA — e o port entrega
        `ModelTrainingError` com ESSE `ValueError` em `__cause__`, não um `ValueError`."""
        with pytest.raises(ModelTrainingError) as raised:
            PfTftTrainer().train_and_predict(**_tft_kwargs(tmp_path, rows=_rows_with_nan()))

        assert isinstance(raised.value.__cause__, ValueError)
        assert "NA" in str(raised.value.__cause__)

    def test_fake_simulates_the_backend_failure_after_the_rule(self, tmp_path: Path) -> None:
        with pytest.raises(ModelTrainingError) as raised:
            InMemoryTftTrainer(simulate_backend_failure=_SIMULATED).train_and_predict(
                **_tft_kwargs(tmp_path)
            )

        assert raised.value.__cause__ is not None

    @pytest.mark.parametrize("leg", _LEGS)
    def test_port_rule_still_raises_value_error_before_the_backend(
        self, leg: str, tmp_path: Path
    ) -> None:
        """C3 (janela maior que o treino) é regra do port: `ValueError` nas duas pernas,
        mesmo com o backend quebrado (fake) / o painel com NaN (real)."""
        trainer: Any = (
            InMemoryTftTrainer(simulate_backend_failure=_SIMULATED)
            if leg == "fake"
            else PfTftTrainer()
        )
        rows = _rows_with_nan() if leg == "real" else _panel()[0]

        with pytest.raises(ValueError, match=r"\(C3\)"):
            trainer.train_and_predict(
                **_tft_kwargs(
                    tmp_path, rows=rows, params=TftTrainingParams(seed=7, max_encoder_length=40)
                )
            )


# =============================================================== HyperparameterSearch

_SPACE = (
    SearchDimension(name="hidden_size", low=4, high=32, kind="int"),
    SearchDimension(name="learning_rate", low=0.001, high=0.1, kind="float", log=True),
)


def _raising_ask(self: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
    msg = "storage backend unavailable"
    raise StorageInternalError(msg)


def _search(leg: str, *, broken: bool, monkeypatch: pytest.MonkeyPatch) -> Any:  # noqa: ANN401
    if leg == "fake":
        return InMemoryHyperparameterSearch(simulate_backend_failure=_SIMULATED if broken else None)
    if broken:
        monkeypatch.setattr(optuna.study.Study, "ask", _raising_ask)
    return OptunaSearch()


class TestHyperparameterSearchBackendFailure:
    @pytest.mark.parametrize("leg", _LEGS)
    def test_backend_failure_raises_the_contract_type_with_cause(
        self, leg: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        search = _search(leg, broken=True, monkeypatch=monkeypatch)
        search.create_study(seed=11)

        with pytest.raises(HyperparameterSearchError) as raised:
            search.ask(_SPACE)

        assert raised.value.__cause__ is not None
        if leg == "real":
            assert isinstance(raised.value.__cause__, StorageInternalError)

    @pytest.mark.parametrize("leg", _LEGS)
    def test_unknown_trial_is_still_the_callers_value_error(
        self, leg: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`tell` de trial nunca pedido é uso indevido (ValueError), não falha do backend."""
        search = _search(leg, broken=False, monkeypatch=monkeypatch)
        search.create_study(seed=11)

        with pytest.raises(ValueError, match="999"):
            search.tell(trial_number=999, objective_value=1.0)

    def test_missing_study_is_a_wiring_runtime_error_not_translated(self) -> None:
        """`_require_study` continua `RuntimeError`: bug de wiring propaga (issue #84)."""
        with pytest.raises(RuntimeError, match="create_study"):
            OptunaSearch().ask(_SPACE)
