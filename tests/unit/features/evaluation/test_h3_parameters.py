"""Unit do VO `H3Parameters` (Stage 7.3, Task 21) — concept §4, C11, I17; ADR 7.3.0005."""

from __future__ import annotations

import copy
import dataclasses
import math
from typing import Any

import pytest

from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    FILL_AFTER_FREEZE,
    H3_FAMILIES,
    H3_RULE_CATALOG,
    H3Parameters,
)
from tests.unit.features.evaluation._h3_parameters import h3_block, h3_parameters

pytestmark = pytest.mark.unit


def _with(**changes: object) -> dict[str, Any]:
    block = h3_block()
    block.update(changes)
    return block


def _nested(table: str, **changes: object) -> dict[str, Any]:
    block: dict[str, Any] = copy.deepcopy(h3_block())
    block[table].update(changes)
    return block


def test_round_trip() -> None:
    vo = h3_parameters()

    assert H3Parameters.from_mapping(vo.as_payload()) == vo
    assert vo.as_payload() == h3_block()
    assert vo.families == H3_FAMILIES
    assert vo.partition["sentiment"] == ("sentiment_mean",)
    assert vo.ablation_seeds == (11, 12)
    assert vo.ablation_models["price"] == "tft_quantile_loco_minus_price"
    assert hash(vo) == hash(h3_parameters())


def test_unknown_and_missing_keys_refused_with_dotted_path() -> None:
    with pytest.raises(ValueError, match=r"unknown key 'h3\.volatility_profile'"):
        H3Parameters.from_mapping(_with(volatility_profile="x"))
    block = h3_block()
    del block["reps"]
    with pytest.raises(ValueError, match=r"misses the key 'h3\.reps'"):
        H3Parameters.from_mapping(block)
    with pytest.raises(ValueError, match=r"unknown key 'h3\.partition\.volatility'"):
        H3Parameters.from_mapping(_nested("partition", volatility=["atr_14"]))
    nested: dict[str, Any] = copy.deepcopy(h3_block())
    del nested["partition"]["partition_hash"]
    with pytest.raises(ValueError, match=r"misses the key 'h3\.partition\.partition_hash'"):
        H3Parameters.from_mapping(nested)
    nested = copy.deepcopy(h3_block())
    del nested["ablation"]["cohort_hash"]
    with pytest.raises(ValueError, match=r"misses the key 'h3\.ablation\.cohort_hash'"):
        H3Parameters.from_mapping(nested)
    nested = copy.deepcopy(h3_block())
    del nested["ablation"]["models"]["sentiment"]
    with pytest.raises(ValueError, match=r"misses the key 'h3\.ablation\.models\.sentiment'"):
        H3Parameters.from_mapping(nested)
    with pytest.raises(ValueError, match="h3 must be a table"):
        H3Parameters.from_mapping([1, 2])


@pytest.mark.parametrize("key", sorted(H3_RULE_CATALOG))
def test_identifier_outside_the_catalog_refused(key: str) -> None:
    with pytest.raises(ValueError, match=rf"h3\.{key} must be"):
        H3Parameters.from_mapping(_with(**{key: "other_v2"}))


@pytest.mark.parametrize("field", ["cohort_id", "cohort_hash", "seeds"])
def test_sentinel_value_refused(field: str) -> None:
    with pytest.raises(ValueError, match=rf"h3\.ablation\.{field} still holds the draft sentinel"):
        H3Parameters.from_mapping(_nested("ablation", **{field: FILL_AFTER_FREEZE}))


@pytest.mark.parametrize(
    ("partition", "message"),
    [
        ({"price": ["a"], "technical": ["b"], "sentiment": ["c"]}, r"misses the key"),
        (
            {"price": ["a"], "technical": ["a"], "sentiment": ["c"], "fundamental": ["d"]},
            r"'a' is in 'price' and 'technical'",
        ),
        (
            {"price": ["a", "a"], "technical": ["b"], "sentiment": ["c"], "fundamental": ["d"]},
            r"h3\.partition\.price must not repeat",
        ),
        (
            {"price": [], "technical": ["b"], "sentiment": ["c"], "fundamental": ["d"]},
            r"h3\.partition\.price must be a non-empty list",
        ),
        (
            {"price": [""], "technical": ["b"], "sentiment": ["c"], "fundamental": ["d"]},
            r"h3\.partition\.price\[0\] must be a non-empty string",
        ),
    ],
)
def test_partition_must_cover_the_four_families_disjointly(
    partition: dict[str, list[str]], message: str
) -> None:
    block: dict[str, Any] = copy.deepcopy(h3_block())
    block["partition"] = {"partition_hash": block["partition"]["partition_hash"], **partition}

    with pytest.raises(ValueError, match=message):
        H3Parameters.from_mapping(block)


def test_interval_level_is_0_9875() -> None:
    """Bonferroni sobre as 4 famílias: `1 - 0.05/4` (mata o nível 0.95 sem ajuste)."""
    assert h3_parameters().interval_level == 0.9875  # noqa: PLR2004
    assert H3Parameters.from_mapping(_with(family_alpha=0.1)).interval_level == 0.975  # noqa: PLR2004


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"reference_model": "tft_quantile"}, r"h3\.ablation\.reference_model must be"),
        (
            {
                "models": {
                    "price": "tft_quantile_loco_minus_technical",
                    "technical": "tft_quantile_loco_minus_price",
                    "sentiment": "tft_quantile_loco_minus_sentiment",
                    "fundamental": "tft_quantile_loco_minus_fundamental",
                }
            },
            r"h3\.ablation\.models must map each family to its LOCO version",
        ),
        (
            {
                "models": {
                    "price": "tft_quantile",
                    "technical": "tft_quantile_loco_minus_technical",
                    "sentiment": "tft_quantile_loco_minus_sentiment",
                    "fundamental": "tft_quantile_loco_minus_fundamental",
                }
            },
            r"h3\.ablation\.models must map",
        ),
    ],
)
def test_ablation_models_are_the_loco_versions(changes: dict[str, object], message: str) -> None:
    assert h3_parameters().ablation_reference_model == "tft_quantile_loco_full"
    with pytest.raises(ValueError, match=message):
        H3Parameters.from_mapping(_nested("ablation", **changes))


@pytest.mark.parametrize("key", ["k_p", "reps"])
@pytest.mark.parametrize("value", [0, -1, True, 1.0, "10", None])
def test_k_p_and_reps_positive_ints(key: str, value: object) -> None:
    with pytest.raises(ValueError, match=rf"h3\.{key} must be an int >= 1"):
        H3Parameters.from_mapping(_with(**{key: value}))


@pytest.mark.parametrize("key", ["permutation_seed", "bootstrap_seed"])
@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_seeds_are_non_negative_ints(key: str, value: object) -> None:
    with pytest.raises(ValueError, match=rf"h3\.{key} must be an int >= 0"):
        H3Parameters.from_mapping(_with(**{key: value}))


@pytest.mark.parametrize("seeds", [[], [11, 11], [-1], [True], "11"])
def test_ablation_seeds_refused(seeds: object) -> None:
    with pytest.raises(ValueError, match=r"h3\.ablation\.seeds"):
        H3Parameters.from_mapping(_nested("ablation", seeds=seeds))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("family_alpha", 0.0, r"h3\.family_alpha must be a number in \(0, 1\)"),
        ("family_alpha", 1.0, r"h3\.family_alpha"),
        ("family_alpha", math.nan, r"h3\.family_alpha"),
        ("family_alpha", True, r"h3\.family_alpha"),
        ("partition_hash", "A1" * 32, r"h3\.partition\.partition_hash must be a lowercase"),
        ("partition_hash", "a1" * 31, r"h3\.partition\.partition_hash"),
        ("feature_set_hash", "x", r"h3\.feature_set_hash"),
        ("ablation_cohort_hash", "b2", r"h3\.ablation\.cohort_hash"),
        ("ablation_cohort_id", " ", r"h3\.ablation\.cohort_id"),
        (
            "families",
            ("price", "technical", "sentiment"),
            r"h3\.families must be \['price', 'technical', 'sentiment', 'fundamental'\]",
        ),
        ("families", ("technical", "price", "sentiment", "fundamental"), r"h3\.families"),
        (
            "partition",
            {"price": ("a",), "technical": ("b",), "sentiment": ("c",)},
            r"h3\.partition must have exactly the families",
        ),
        ("bootstrap_scheme", "circular", r"h3\.bootstrap_scheme must be stationary"),
    ],
)
def test_raw_construction_with_invalid_field_refused(
    field: str, value: object, message: str
) -> None:
    """O construtor direto (sem `from_mapping`) valida no `__post_init__`."""
    valid = h3_parameters()
    with pytest.raises(ValueError, match=message):
        dataclasses.replace(valid, **{field: value})


def test_mappings_are_read_only() -> None:
    vo = h3_parameters()
    with pytest.raises(TypeError):
        vo.partition["price"] = ("x",)  # type: ignore[index]
    with pytest.raises(TypeError):
        vo.ablation_models["price"] = "x"  # type: ignore[index]
