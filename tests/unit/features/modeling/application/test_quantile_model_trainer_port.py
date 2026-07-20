"""Unit — DTOs do port `QuantileModelTrainer` (validação C2-params + imutabilidade).

Cobre o contrato do concept 5.3 §4/§6-C2 (parcela dos params): defaults
pré-registrados válidos, cada violação de faixa ergue `ValueError` nomeando o
campo, e os DTOs são frozen (identidade do run não muta após construída).
"""

import dataclasses

import pytest

from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
    QuantileTrainingResult,
)

pytestmark = pytest.mark.unit

_SEED = 42
# Contrato pré-registrado do concept D6: defaults da lib + teto do ADR 5.3.0002.
_EXPECTED_CEILING = 500
_EXPECTED_NUM_LEAVES = 31
_EXPECTED_LEARNING_RATE = 0.1
_EXPECTED_MIN_DATA_IN_LEAF = 20


class TestGbmTrainingParamsDefaults:
    def test_defaults_are_the_preregistered_contract(self) -> None:
        """Defaults do concept D6: lib defaults + teto 500 do ADR 5.3.0002."""
        params = GbmTrainingParams(seed=_SEED)

        assert params.seed == _SEED
        assert params.num_boost_round_max == _EXPECTED_CEILING
        assert params.num_leaves == _EXPECTED_NUM_LEAVES
        assert params.learning_rate == _EXPECTED_LEARNING_RATE
        assert params.min_data_in_leaf == _EXPECTED_MIN_DATA_IN_LEAF

    def test_params_are_frozen(self) -> None:
        params = GbmTrainingParams(seed=_SEED)

        with pytest.raises(dataclasses.FrozenInstanceError):
            params.seed = 7  # type: ignore[misc]


class TestGbmTrainingParamsValidation:
    @pytest.mark.parametrize("num_boost_round_max", [0, -1])
    def test_non_positive_ceiling_raises_naming_the_field(
        self, num_boost_round_max: int
    ) -> None:
        with pytest.raises(ValueError, match="num_boost_round_max"):
            GbmTrainingParams(seed=_SEED, num_boost_round_max=num_boost_round_max)

    @pytest.mark.parametrize("learning_rate", [0.0, -0.1])
    def test_non_positive_learning_rate_raises_naming_the_field(
        self, learning_rate: float
    ) -> None:
        with pytest.raises(ValueError, match="learning_rate"):
            GbmTrainingParams(seed=_SEED, learning_rate=learning_rate)

    @pytest.mark.parametrize("num_leaves", [1, 0, -3])
    def test_num_leaves_below_two_raises_naming_the_field(self, num_leaves: int) -> None:
        with pytest.raises(ValueError, match="num_leaves"):
            GbmTrainingParams(seed=_SEED, num_leaves=num_leaves)

    @pytest.mark.parametrize("min_data_in_leaf", [0, -1])
    def test_non_positive_min_data_in_leaf_raises_naming_the_field(
        self, min_data_in_leaf: int
    ) -> None:
        with pytest.raises(ValueError, match="min_data_in_leaf"):
            GbmTrainingParams(seed=_SEED, min_data_in_leaf=min_data_in_leaf)

    def test_boundary_values_are_accepted(self) -> None:
        """Fronteiras válidas (>=1 / >=2 / >0) não erguem — pina o limiar exato."""
        minimum_ceiling = 1
        minimum_leaves = 2

        params = GbmTrainingParams(
            seed=0,
            num_boost_round_max=minimum_ceiling,
            num_leaves=minimum_leaves,
            learning_rate=1e-9,
            min_data_in_leaf=1,
        )

        assert params.num_boost_round_max == minimum_ceiling
        assert params.num_leaves == minimum_leaves


class TestQuantileTrainingResult:
    def test_result_is_frozen(self) -> None:
        result = QuantileTrainingResult(
            grids={0: {1: (0.1, 0.2)}}, best_iteration_by_horizon={1: 3}
        )

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.grids = {}  # type: ignore[misc]

    def test_result_holds_the_shapes_verbatim(self) -> None:
        """O Result não transforma nada — grades e m* saem como entraram."""
        grids = {5: {1: (-0.01, 0.0, 0.01), 7: (-0.02, 0.0, 0.02)}}
        best = {1: 12, 7: 3}

        result = QuantileTrainingResult(grids=grids, best_iteration_by_horizon=best)

        assert result.grids[5][7] == (-0.02, 0.0, 0.02)
        assert result.best_iteration_by_horizon == {1: 12, 7: 3}
