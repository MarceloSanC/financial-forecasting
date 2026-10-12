"""Unit test do VO `ProfileParameters` (Stage 6.6 Task 07; concept D1, I8; ADR 6.6.0001).

Ida e volta `from_mapping(as_payload()) == vo`; cada identificador fora do
`PROFILE_RULE_CATALOG` é recusado com o caminho pontuado; chave desconhecida/ausente
nomeia o caminho; `break_alpha` aceita `int` não-`bool`, guarda `float` e passa pelo
validador dono (`validate_alpha`).
"""

from __future__ import annotations

import copy

import pytest

from financial_forecasting.features.evaluation.domain.value_objects.profile_parameters import (
    PROFILE_RULE_CATALOG,
    ProfileParameters,
    StationarityParameters,
)

_ALPHA = 0.05


def _payload() -> dict[str, object]:
    return {
        "subset_multiplicity": PROFILE_RULE_CATALOG["subset_multiplicity"],
        "partial_degeneracy_pairs": PROFILE_RULE_CATALOG["partial_degeneracy_pairs"],
        "mcs_block_sensitivity_scheme": PROFILE_RULE_CATALOG["mcs_block_sensitivity_scheme"],
        "stationarity": {
            "acf_max_lag": PROFILE_RULE_CATALOG["stationarity.acf_max_lag"],
            "break_test": PROFILE_RULE_CATALOG["stationarity.break_test"],
            "break_alpha": _ALPHA,
        },
    }


def test_catalog_is_the_frozen_set_of_rules() -> None:
    assert dict(PROFILE_RULE_CATALOG) == {
        "subset_multiplicity": "none_raw_p_descriptive_v1",
        "partial_degeneracy_pairs": "symmetric_and_adjacent_non_degenerate_rows_v1",
        "mcs_block_sensitivity_scheme": "primary_scheme",
        "stationarity.acf_max_lag": "min_floor_10_log10_T_T_minus_1",
        "stationarity.break_test": "cusum_mean_dm_primary_variance_kolmogorov_v1",
    }


def test_round_trip() -> None:
    vo = ProfileParameters.from_mapping(_payload())
    assert vo.as_payload() == _payload()
    assert ProfileParameters.from_mapping(vo.as_payload()) == vo
    assert vo.stationarity.break_alpha == _ALPHA


def test_integer_alpha_is_coerced_then_validated_by_the_owner() -> None:
    """`int` não-`bool` passa a coerção (não é "must be a number") e chega ao
    `validate_alpha`, que recusa 0 por estar fora de (0, 1)."""
    payload = _payload()
    payload["stationarity"]["break_alpha"] = 0  # type: ignore[index]
    with pytest.raises(ValueError, match="alpha") as raised:
        ProfileParameters.from_mapping(payload)
    assert "must be a number" not in str(raised.value)


@pytest.mark.parametrize(
    "key",
    ["subset_multiplicity", "partial_degeneracy_pairs", "mcs_block_sensitivity_scheme"],
)
def test_top_level_rule_outside_the_catalog(key: str) -> None:
    payload = _payload()
    payload[key] = "something_else"
    with pytest.raises(ValueError, match=rf"profile_parameters\.{key} must be .* only rule"):
        ProfileParameters.from_mapping(payload)


@pytest.mark.parametrize("key", ["acf_max_lag", "break_test"])
def test_stationarity_rule_outside_the_catalog(key: str) -> None:
    payload = _payload()
    payload["stationarity"][key] = "other"  # type: ignore[index]
    with pytest.raises(ValueError, match=rf"profile_parameters\.stationarity\.{key} must be"):
        ProfileParameters.from_mapping(payload)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda p: p.pop("subset_multiplicity"),
            "misses the key 'profile_parameters.subset_multiplicity'",
        ),
        (lambda p: p.update(extra=1), "unknown key 'profile_parameters.extra'"),
        (
            lambda p: p["stationarity"].pop("break_alpha"),
            "misses the key 'profile_parameters.stationarity.break_alpha'",
        ),
        (
            lambda p: p["stationarity"].update(lags=3),
            "unknown key 'profile_parameters.stationarity.lags'",
        ),
        (lambda p: p.update(stationarity=[]), "profile_parameters.stationarity must be a table"),
    ],
)
def test_keys(mutate: object, message: str) -> None:
    payload = copy.deepcopy(_payload())
    mutate(payload)  # type: ignore[operator]
    with pytest.raises(ValueError, match=message):
        ProfileParameters.from_mapping(payload)


@pytest.mark.parametrize("alpha", [True, "0.05", 1.5, 0.0])
def test_invalid_alpha(alpha: object) -> None:
    payload = _payload()
    payload["stationarity"]["break_alpha"] = alpha  # type: ignore[index]
    with pytest.raises(ValueError, match=r"alpha|number"):
        ProfileParameters.from_mapping(payload)


def test_root_must_be_a_table() -> None:
    with pytest.raises(ValueError, match="profile_parameters must be a table"):
        ProfileParameters.from_mapping(["x"])


def test_direct_construction_requires_the_typed_stationarity() -> None:
    with pytest.raises(ValueError, match="must be a StationarityParameters"):
        ProfileParameters(
            subset_multiplicity=PROFILE_RULE_CATALOG["subset_multiplicity"],
            partial_degeneracy_pairs=PROFILE_RULE_CATALOG["partial_degeneracy_pairs"],
            mcs_block_sensitivity_scheme=PROFILE_RULE_CATALOG["mcs_block_sensitivity_scheme"],
            stationarity=_payload()["stationarity"],  # type: ignore[arg-type]
        )


def test_direct_construction_refuses_an_int_alpha() -> None:
    with pytest.raises(ValueError, match="break_alpha must be a float"):
        StationarityParameters(
            acf_max_lag=PROFILE_RULE_CATALOG["stationarity.acf_max_lag"],
            break_test=PROFILE_RULE_CATALOG["stationarity.break_test"],
            break_alpha=1,  # type: ignore[arg-type]
        )
