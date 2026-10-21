"""Helper de teste: o bloco `[h3]` com os valores do technical 7.3 §1 (Task 21).

As regras, os números e o `feature_set_hash` são os do §1. A partição e a ablação são
sintéticas: uma lista curta por família, um `partition_hash` e um cohort de ablação
inventados (o literal da r3 só existe no rascunho da Task 32, e o cohort real só depois
do freeze no Linux). Nada aqui vem do cohort real.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3Parameters,
)

FEATURE_SET_HASH = "7df0e1b4d6e93e3edb5695414a47d2d77882a2ffc674d00037f2a9f87a6409e0"
SYNTHETIC_PARTITION_HASH = "a1" * 32
SYNTHETIC_ABLATION_HASH = "b2" * 32
SYNTHETIC_ABLATION_ID = "synthetic_ablation_r0_b2b2b2b2b2b2"
SYNTHETIC_PARTITION: dict[str, list[str]] = {
    "price": ["log_return", "range_pct"],
    "technical": ["rsi_14", "macd"],
    "sentiment": ["sentiment_mean"],
    "fundamental": ["pe_ratio", "eps_growth"],
}


def h3_block() -> dict[str, object]:
    """O bloco `[h3]` na forma do TOML (chaves e valores finais do §1, ablação sintética)."""
    return {
        "families": ["price", "technical", "sentiment", "fundamental"],
        "feature_set_hash": FEATURE_SET_HASH,
        "partition_rule": "registry_family_lists_frozen_v1",
        "permutation_scheme": "whole_encoder_window_joint_between_fold_test_decisions_v1",
        "permutation_algorithm": "fisher_yates_random_random_v1",
        "measure": "grid_mean_pinball_difference_guardrail_v1",
        "pairing": "decision_point_horizon_intersection_v1",
        "seed_aggregation": "pointwise_seed_mean_then_permutation_mean_v1",
        "bootstrap_scheme": "stationary",
        "block_rule": "max_7_ceil_max_bsb_joint_16_series_v1",
        "interval": "basic_linear_percentile_v1",
        "multiplicity": "bonferroni_over_families_v1",
        "nonpositive_total": "undefined_if_point_total_nonpositive_replicas_as_infinite_v1",
        "reading_rule": "interval_side_agreement_same_family_v1",
        "vsn_summary": "per_decision_seed_mean_p10_p50_p90_family_sum_v1",
        "k_p": 10,
        "permutation_seed": 130,
        "reps": 1000,
        "bootstrap_seed": 129,
        "family_alpha": 0.05,
        "partition": {
            "partition_hash": SYNTHETIC_PARTITION_HASH,
            **{family: list(features) for family, features in SYNTHETIC_PARTITION.items()},
        },
        "ablation": {
            "cohort_id": SYNTHETIC_ABLATION_ID,
            "cohort_hash": SYNTHETIC_ABLATION_HASH,
            "seeds": [11, 12],
            "reference_model": "tft_quantile_loco_full",
            "models": {
                "price": "tft_quantile_loco_minus_price",
                "technical": "tft_quantile_loco_minus_technical",
                "sentiment": "tft_quantile_loco_minus_sentiment",
                "fundamental": "tft_quantile_loco_minus_fundamental",
            },
        },
    }


def h3_parameters() -> H3Parameters:
    """O VO do bloco do §1."""
    return H3Parameters.from_mapping(h3_block())
