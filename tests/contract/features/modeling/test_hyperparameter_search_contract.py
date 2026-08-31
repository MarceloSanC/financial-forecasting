"""Contract test do port `HyperparameterSearch` — paridade fake ↔ `OptunaSearch`.

Um contrato parametrizado sobre `[fake, real]` provando a semântica observável
compartilhada (concept 5.4 §4 / ADR 5.4.0005):

- `create_study` devolve identificador não vazio;
- `ask` respeita os limites de cada dimensão e devolve um valor por dimensão;
- dimensão inteira produz valor integral, mesmo atravessando como `float`;
- os trials são numerados a partir de 0, em sequência;
- `best_trial` devolve o de menor objetivo informado;
- `best_trial` sem nenhum `tell` ergue com o marcador de C9.

**O que este contrato NÃO compara, de propósito:** convergência ou a sequência
de valores amostrados. O real usa TPE, estocástico por desenho; o fake usa uma
grade regular. Exigir a mesma sequência tornaria o contrato refém do amostrador
da biblioteca sem provar nada sobre o port.
"""

from __future__ import annotations

import pytest

from financial_forecasting.features.modeling.adapters.out.optuna.optuna_search import (
    OptunaSearch,
)
from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    HyperparameterSearch,
    SearchDimension,
)
from tests.fakes.features.modeling.in_memory_hyperparameter_search import (
    InMemoryHyperparameterSearch,
)

pytestmark = pytest.mark.contract

_SEED = 11
_HIDDEN = "hidden_size"
_SPACE = (
    SearchDimension(name=_HIDDEN, low=4, high=32, kind="int"),
    SearchDimension(name="dropout", low=0.0, high=0.5, kind="float"),
    SearchDimension(name="learning_rate", low=0.001, high=0.1, kind="float", log=True),
)


@pytest.fixture(params=["fake", "real"])
def leg(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def search(leg: str) -> HyperparameterSearch:
    return InMemoryHyperparameterSearch() if leg == "fake" else OptunaSearch()


class TestStudyLifecycle:
    def test_create_study_returns_an_identifier(self, search: HyperparameterSearch) -> None:
        study_id = search.create_study(seed=_SEED)

        assert isinstance(study_id, str)
        assert study_id


class TestAsk:
    def test_one_value_per_declared_dimension(self, search: HyperparameterSearch) -> None:
        search.create_study(seed=_SEED)

        trial = search.ask(_SPACE)

        assert set(trial.values) == {dimension.name for dimension in _SPACE}

    def test_values_respect_the_declared_bounds(self, search: HyperparameterSearch) -> None:
        search.create_study(seed=_SEED)

        for _ in range(5):
            trial = search.ask(_SPACE)
            for dimension in _SPACE:
                assert dimension.low <= trial.values[dimension.name] <= dimension.high

    def test_integer_dimension_yields_integral_values(self, search: HyperparameterSearch) -> None:
        """Atravessa como `float`, mas o valor é integral — o use case reconverte."""
        search.create_study(seed=_SEED)

        for _ in range(5):
            value = search.ask(_SPACE).values[_HIDDEN]
            assert value == int(value)

    def test_trials_are_numbered_in_sequence_from_zero(self, search: HyperparameterSearch) -> None:
        search.create_study(seed=_SEED)

        numbers = [search.ask(_SPACE).number for _ in range(4)]

        assert numbers == [0, 1, 2, 3]


class TestTellAndBest:
    def test_best_trial_is_the_lowest_objective(self, search: HyperparameterSearch) -> None:
        search.create_study(seed=_SEED)
        for objective in (0.9, 0.2, 0.5):
            trial = search.ask(_SPACE)
            search.tell(trial_number=trial.number, objective_value=objective)

        assert search.best_trial().number == 1

    def test_best_trial_carries_the_sampled_values(self, search: HyperparameterSearch) -> None:
        search.create_study(seed=_SEED)
        sampled: dict[int, dict[str, float]] = {}
        for objective in (0.9, 0.2):
            trial = search.ask(_SPACE)
            sampled[trial.number] = dict(trial.values)
            search.tell(trial_number=trial.number, objective_value=objective)

        best = search.best_trial()

        assert dict(best.values) == sampled[best.number]

    def test_best_trial_without_any_tell_raises(self, search: HyperparameterSearch) -> None:
        search.create_study(seed=_SEED)
        search.ask(_SPACE)

        with pytest.raises(ValueError, match="C9"):
            search.best_trial()


def test_both_legs_are_exercised(search: HyperparameterSearch, leg: str) -> None:
    """Guarda anti-suite-de-uma-perna, amarrando o parâmetro ao TIPO.

    `isinstance(search, Fake | Real)` seria satisfeita pelo fake nas duas
    parametrizações — uma fixture que devolvesse sempre o fake apagaria a perna
    real sem reprovar nada.
    """
    expected = OptunaSearch if leg == "real" else InMemoryHyperparameterSearch
    assert isinstance(search, expected)
