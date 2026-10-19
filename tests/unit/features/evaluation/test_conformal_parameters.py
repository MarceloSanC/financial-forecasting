"""Unit do VO `ConformalParameters` (Stage 7.2, Task 11) — concept §4, §6 C4, I16, I17."""

from __future__ import annotations

import math

import pytest

from financial_forecasting.features.evaluation.domain.value_objects.conformal_parameters import (
    CONFORMAL_RULE_CATALOG,
    ConformalParameters,
)
from tests.unit.features.evaluation._conformal_parameters import (
    conformal_block,
    conformal_parameters,
)

pytestmark = pytest.mark.unit


def _with(**changes: object) -> dict[str, object]:
    block = conformal_block()
    block.update(changes)
    return block


def test_round_trip() -> None:
    vo = conformal_parameters()
    assert ConformalParameters.from_mapping(vo.as_payload()) == vo
    assert vo.as_payload() == conformal_block()
    assert vo.pairs == ((0.02, 0.98), (0.1, 0.9), (0.25, 0.75))
    assert vo.primary_pair == (0.1, 0.9)
    assert vo.nexcp_rho == 0.99  # noqa: PLR2004


def test_unknown_and_missing_keys_refused_with_dotted_path() -> None:
    with pytest.raises(ValueError, match=r"unknown key 'conformal\.aci_gamma'"):
        ConformalParameters.from_mapping(_with(aci_gamma=0.005))
    block = conformal_block()
    del block["rank"]
    with pytest.raises(ValueError, match=r"misses the key 'conformal\.rank'"):
        ConformalParameters.from_mapping(block)
    with pytest.raises(ValueError, match="conformal must be a table"):
        ConformalParameters.from_mapping([1, 2])


@pytest.mark.parametrize("key", sorted(CONFORMAL_RULE_CATALOG))
def test_identifier_outside_the_catalog_refused(key: str) -> None:
    with pytest.raises(ValueError, match=rf"conformal\.{key} must be"):
        ConformalParameters.from_mapping(_with(**{key: "other_v2"}))


@pytest.mark.parametrize("variant", ["aci", "enbpi"])
@pytest.mark.parametrize("key", ["variant_of_record", "sensitivity"])
def test_aci_and_enbpi_refused(key: str, variant: str) -> None:
    with pytest.raises(ValueError, match=rf"conformal\.{key} must be"):
        ConformalParameters.from_mapping(_with(**{key: variant}))


@pytest.mark.parametrize("rho", [0, 0.0, 1.5, 1.0000001, -0.5, math.nan, math.inf, True, "0.99"])
def test_rho_refused(rho: object) -> None:
    with pytest.raises(ValueError, match=r"conformal\.nexcp_rho"):
        ConformalParameters.from_mapping(_with(nexcp_rho=rho))


def test_rho_one_accepted() -> None:
    assert ConformalParameters.from_mapping(_with(nexcp_rho=1)).nexcp_rho == 1.0


def test_central_level_pair_refused() -> None:
    """C4-3: (0,5; 0,5) é simétrico, mas não é intervalo (tau_lo tem de ficar em (0; 0,5))."""
    with pytest.raises(ValueError, match=r"conformal\.pairs\[0\]"):
        ConformalParameters.from_mapping(_with(pairs=[[0.5, 0.5]], primary_pair=[0.5, 0.5]))


def test_non_symmetric_pair_refused() -> None:
    with pytest.raises(ValueError, match=r"conformal\.pairs\[1\] \[0\.1, 0\.8\] is not symmetric"):
        ConformalParameters.from_mapping(_with(pairs=[[0.02, 0.98], [0.1, 0.8]]))
    with pytest.raises(ValueError, match=r"conformal\.pairs\[0\] lower level"):
        ConformalParameters.from_mapping(_with(pairs=[[0.9, 0.1]], primary_pair=[0.9, 0.1]))


def test_pair_symmetry_is_exact() -> None:
    assert 0.4 + 0.6000000000000001 == 1.0  # a armadilha do float64
    accepted = ConformalParameters.from_mapping(
        _with(pairs=[[0.1, 0.9], [0.02, 0.98]], primary_pair=[0.1, 0.9])
    )
    assert accepted.pairs == ((0.1, 0.9), (0.02, 0.98))
    with pytest.raises(ValueError, match=r"conformal\.pairs\[0\] .* is not symmetric"):
        ConformalParameters.from_mapping(
            _with(pairs=[[0.4, 0.6000000000000001]], primary_pair=[0.4, 0.6000000000000001])
        )


@pytest.mark.parametrize(
    "pairs",
    [[], "0.1,0.9", [[0.1]], [[0.1, 0.9, 0.5]], [["0.1", "0.9"]], [[0.1, 0.9], [0.1, 0.9]]],
)
def test_malformed_pairs_refused(pairs: object) -> None:
    with pytest.raises(ValueError, match=r"conformal\.pairs"):
        ConformalParameters.from_mapping(_with(pairs=pairs))


def test_primary_pair_must_be_a_pair() -> None:
    with pytest.raises(ValueError, match=r"conformal\.primary_pair \[0\.25, 0\.75\] is not one"):
        ConformalParameters.from_mapping(_with(pairs=[[0.1, 0.9]], primary_pair=[0.25, 0.75]))
    with pytest.raises(ValueError, match=r"conformal\.primary_pair must be a pair"):
        ConformalParameters.from_mapping(_with(primary_pair=0.1))


@pytest.mark.parametrize("huge", [10**400, -(10**400)])
def test_huge_int_refused_with_value_error(huge: int) -> None:
    # int além do float64: ValueError nomeado, nunca o OverflowError cru (Checkpoint C, C3-3)
    with pytest.raises(ValueError, match=r"conformal\.nexcp_rho"):
        ConformalParameters.from_mapping(_with(nexcp_rho=huge))
    with pytest.raises(ValueError, match=r"conformal\.pairs\[0\]"):
        ConformalParameters.from_mapping(_with(pairs=[[huge, 0.9]], primary_pair=[0.1, 0.9]))
