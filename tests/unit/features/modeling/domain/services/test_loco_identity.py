"""Regra única nome ↔ família das configurações LOCO (Stage 7.3; achado C2-9)."""

from __future__ import annotations

import pytest

from financial_forecasting.features.modeling.domain.services.loco_identity import (
    ABLATION_CONFIGURATIONS,
    TFT_FAMILIES,
    configuration_of,
    excluded_family_of,
    loco_model_version,
)

pytestmark = pytest.mark.unit


def test_configurations_are_full_then_minus_each_family_in_order() -> None:
    assert TFT_FAMILIES == ("price", "technical", "sentiment", "fundamental")
    assert ABLATION_CONFIGURATIONS == (
        "full",
        "minus_price",
        "minus_technical",
        "minus_sentiment",
        "minus_fundamental",
    )


@pytest.mark.parametrize("configuration", ABLATION_CONFIGURATIONS)
def test_name_and_family_round_trip(configuration: str) -> None:
    assert configuration_of(excluded_family_of(configuration)) == configuration
    assert loco_model_version(configuration) == f"tft_quantile_loco_{configuration}"


def test_unknown_configuration_or_family_refused() -> None:
    with pytest.raises(ValueError, match="configuration must be one of"):
        excluded_family_of("minus_volatility")
    with pytest.raises(ValueError, match="excluded_family must be one of"):
        configuration_of("volatility")
