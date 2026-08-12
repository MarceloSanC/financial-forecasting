"""Integração — comportamento do `OptunaSearch` que só existe na perna real.

O contrato (`tests/contract/.../test_hyperparameter_search_contract.py`) cobre a
semântica compartilhada. Aqui ficam as três coisas que só fazem sentido contra
a biblioteca:

- **a semente do port vira semente do AMOSTRADOR** — no Optuna ela não vive no
  estudo, e essa tradução é justamente o que o port existe para absorver. Dois
  estudos com a mesma semente produzem a mesma sequência de trials; com sementes
  diferentes, sequências diferentes;
- **a escala logarítmica é honrada** pela distribuição traduzida;
- **`create_study` é pré-requisito** de `ask`/`tell`/`best_trial`.
"""

from __future__ import annotations

import pytest

from financial_forecasting.features.modeling.adapters.out.optuna.optuna_search import (
    OptunaSearch,
)
from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    SearchDimension,
)

pytestmark = pytest.mark.integration

_SEED = 11
_OTHER_SEED = 99
_TRIALS = 6
_SPACE = (
    SearchDimension(name="hidden_size", low=4, high=64, kind="int"),
    SearchDimension(name="learning_rate", low=0.001, high=0.1, kind="float", log=True),
)


def _sequence(seed: int, trials: int = _TRIALS) -> list[dict[str, float]]:
    search = OptunaSearch()
    search.create_study(seed=seed)
    return [dict(search.ask(_SPACE).values) for _ in range(trials)]


class TestSeedTranslation:
    def test_same_seed_reproduces_the_same_sequence(self) -> None:
        assert _sequence(_SEED) == _sequence(_SEED)

    def test_different_seed_changes_the_sequence(self) -> None:
        """Se a semente fosse ignorada, as duas sequências coincidiriam."""
        assert _sequence(_SEED) != _sequence(_OTHER_SEED)


class TestLogScale:
    def test_log_dimension_stays_within_bounds_and_varies(self) -> None:
        log_dimension = next(d for d in _SPACE if d.log)
        values = [trial[log_dimension.name] for trial in _sequence(_SEED, trials=8)]

        assert all(log_dimension.low <= value <= log_dimension.high for value in values)
        assert len(set(values)) > 1


class TestStudyIsRequired:
    def test_ask_before_create_study_raises(self) -> None:
        with pytest.raises(RuntimeError, match="create_study"):
            OptunaSearch().ask(_SPACE)

    def test_tell_before_create_study_raises(self) -> None:
        with pytest.raises(RuntimeError, match="create_study"):
            OptunaSearch().tell(trial_number=0, objective_value=0.1)

    def test_best_trial_before_create_study_raises(self) -> None:
        with pytest.raises(RuntimeError, match="create_study"):
            OptunaSearch().best_trial()


class TestMaximizeDirection:
    def test_direction_is_honoured(self) -> None:
        search = OptunaSearch()
        search.create_study(seed=_SEED, direction="maximize")
        for objective in (0.1, 0.8, 0.4):
            trial = search.ask(_SPACE)
            search.tell(trial_number=trial.number, objective_value=objective)

        assert search.best_trial().number == 1
