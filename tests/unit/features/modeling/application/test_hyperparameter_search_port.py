"""Unit — DTOs do port `HyperparameterSearch` (C11) e o fake determinístico.

C11 valida na CONSTRUÇÃO da dimensão, e não na hora de montar os params do
trial: um nome errado ali só apareceria como `TypeError` opaco, longe da causa.
"""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    SearchDimension,
    SearchTrial,
)
from tests.fakes.features.modeling.in_memory_hyperparameter_search import (
    InMemoryHyperparameterSearch,
)

pytestmark = pytest.mark.unit

_SEED = 11
_HIDDEN = "hidden_size"


class TestSearchDimensionValidation:
    def test_valid_dimension_is_accepted(self) -> None:
        dimension = SearchDimension(name=_HIDDEN, low=4, high=32, kind="int")

        assert dimension.name == _HIDDEN
        assert dimension.log is False

    def test_dimension_is_frozen(self) -> None:
        dimension = SearchDimension(name=_HIDDEN, low=4, high=32, kind="int")

        with pytest.raises(dataclasses.FrozenInstanceError):
            dimension.low = 1  # type: ignore[misc]

    def test_invalid_kind_raises(self) -> None:
        with pytest.raises(ValueError, match="kind"):
            SearchDimension(name=_HIDDEN, low=4, high=32, kind="categorical")

    @pytest.mark.parametrize(("low", "high"), [(32, 4), (8, 8)])
    def test_non_increasing_bounds_raise(self, low: float, high: float) -> None:
        with pytest.raises(ValueError, match="low"):
            SearchDimension(name=_HIDDEN, low=low, high=high, kind="int")

    def test_integer_log_scale_below_one_raises(self) -> None:
        """A distribuição inteira logarítmica da lib exige piso >= 1."""
        with pytest.raises(ValueError, match="low"):
            SearchDimension(name=_HIDDEN, low=0, high=32, kind="int", log=True)

    def test_float_log_scale_below_one_is_allowed(self) -> None:
        """A restrição é só da inteira — taxa de aprendizado começa abaixo de 1."""
        dimension = SearchDimension(
            name="learning_rate", low=0.001, high=0.1, kind="float", log=True
        )

        assert dimension.log is True

    def test_name_outside_training_params_raises(self) -> None:
        with pytest.raises(ValueError, match="não é campo de TftTrainingParams"):
            SearchDimension(name="not_a_param", low=1, high=2, kind="int")


class TestSearchTrial:
    def test_trial_is_frozen(self) -> None:
        trial = SearchTrial(number=0, values={_HIDDEN: 8.0})

        with pytest.raises(dataclasses.FrozenInstanceError):
            trial.number = 1  # type: ignore[misc]


class TestFakeSampler:
    _SPACE = (
        SearchDimension(name=_HIDDEN, low=4, high=32, kind="int"),
        SearchDimension(name="dropout", low=0.0, high=0.5, kind="float"),
    )

    def test_trials_are_numbered_from_zero(self) -> None:
        search = InMemoryHyperparameterSearch()
        search.create_study(seed=_SEED)

        numbers = [search.ask(self._SPACE).number for _ in range(3)]

        assert numbers == [0, 1, 2]

    def test_values_respect_the_declared_bounds(self) -> None:
        search = InMemoryHyperparameterSearch()
        search.create_study(seed=_SEED)

        for _ in range(6):
            trial = search.ask(self._SPACE)
            for dimension in self._SPACE:
                assert dimension.low <= trial.values[dimension.name] <= dimension.high

    def test_integer_dimension_yields_integral_values(self) -> None:
        search = InMemoryHyperparameterSearch()
        search.create_study(seed=_SEED)

        trial = search.ask(self._SPACE)

        assert trial.values[_HIDDEN] == int(trial.values[_HIDDEN])

    def test_same_seed_reproduces_the_same_sequence(self) -> None:
        first = InMemoryHyperparameterSearch()
        first.create_study(seed=_SEED)
        second = InMemoryHyperparameterSearch()
        second.create_study(seed=_SEED)

        assert [first.ask(self._SPACE).values for _ in range(4)] == [
            second.ask(self._SPACE).values for _ in range(4)
        ]

    def test_best_trial_picks_the_lowest_objective(self) -> None:
        search = InMemoryHyperparameterSearch()
        search.create_study(seed=_SEED)
        for objective in (0.9, 0.2, 0.5):
            trial = search.ask(self._SPACE)
            search.tell(trial_number=trial.number, objective_value=objective)

        assert search.best_trial().number == 1

    def test_best_trial_without_any_tell_raises(self) -> None:
        search = InMemoryHyperparameterSearch()
        search.create_study(seed=_SEED)
        search.ask(self._SPACE)

        with pytest.raises(ValueError, match="C9"):
            search.best_trial()

    def test_tell_for_an_unknown_trial_raises(self) -> None:
        search = InMemoryHyperparameterSearch()
        search.create_study(seed=_SEED)

        with pytest.raises(ValueError, match="não foi pedido"):
            search.tell(trial_number=99, objective_value=0.1)
