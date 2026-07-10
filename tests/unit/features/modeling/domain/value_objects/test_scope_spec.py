"""Testes unitários do value object `ScopeSpec` (domínio puro).

Cobrem construção válida, imutabilidade (frozen) e cada invariante de validação
(`asset_id`/`feature_set_name` não-vazios, `max_horizon >= 1`).
"""

import dataclasses

import pytest

from financial_forecasting.features.modeling.domain.value_objects.scope_spec import (
    ScopeSpec,
)

_MAX_HORIZON = 7


@pytest.mark.unit
def test_construct_valid_scope() -> None:
    """Cohort válido preserva os campos; cohort_id default é None."""
    scope = ScopeSpec(
        asset_id="AAPL", feature_set_name="tft_v1", max_horizon=_MAX_HORIZON
    )

    assert scope.asset_id == "AAPL"
    assert scope.feature_set_name == "tft_v1"
    assert scope.max_horizon == _MAX_HORIZON
    assert scope.cohort_id is None


@pytest.mark.unit
def test_cohort_id_is_optional() -> None:
    """cohort_id pode ser fornecido (mapeia ao parent_sweep_id a jusante)."""
    scope = ScopeSpec(
        asset_id="AAPL", feature_set_name="tft_v1", max_horizon=1, cohort_id="sweep-42"
    )

    assert scope.cohort_id == "sweep-42"


@pytest.mark.unit
def test_is_frozen() -> None:
    """VO imutável — atribuir a um campo levanta FrozenInstanceError."""
    scope = ScopeSpec(asset_id="AAPL", feature_set_name="tft_v1", max_horizon=7)

    with pytest.raises(dataclasses.FrozenInstanceError):
        scope.max_horizon = 3  # type: ignore[misc]


@pytest.mark.unit
def test_equality_by_value() -> None:
    """Igualdade estrutural (VO): mesmos campos -> iguais."""
    a = ScopeSpec(asset_id="AAPL", feature_set_name="tft_v1", max_horizon=7)
    b = ScopeSpec(asset_id="AAPL", feature_set_name="tft_v1", max_horizon=7)

    assert a == b


@pytest.mark.unit
def test_empty_asset_id_raises() -> None:
    """asset_id vazio é rejeitado na construção."""
    with pytest.raises(ValueError, match="asset_id"):
        ScopeSpec(asset_id="", feature_set_name="tft_v1", max_horizon=7)


@pytest.mark.unit
def test_empty_feature_set_name_raises() -> None:
    """feature_set_name vazio é rejeitado na construção."""
    with pytest.raises(ValueError, match="feature_set_name"):
        ScopeSpec(asset_id="AAPL", feature_set_name="", max_horizon=7)


@pytest.mark.unit
@pytest.mark.parametrize("bad_horizon", [0, -1, -7])
def test_non_positive_max_horizon_raises(bad_horizon: int) -> None:
    """max_horizon < 1 é rejeitado (a purga precisa de pelo menos 1 sessão)."""
    with pytest.raises(ValueError, match="max_horizon"):
        ScopeSpec(asset_id="AAPL", feature_set_name="tft_v1", max_horizon=bad_horizon)
