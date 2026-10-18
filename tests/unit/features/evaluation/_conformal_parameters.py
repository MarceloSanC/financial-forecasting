"""Helper de teste: o bloco `[conformal]` com os valores do technical 7.2 §1 (Task 11)."""

from __future__ import annotations

from financial_forecasting.features.evaluation.domain.value_objects.conformal_parameters import (
    ConformalParameters,
)


def conformal_block() -> dict[str, object]:
    """O bloco `[conformal]` na forma do TOML (chaves e valores finais do §1)."""
    return {
        "variant_of_record": "split_cqr_asymmetric_unweighted_v1",
        "rank": "ceil_n_plus_1_one_minus_tail_alpha_exact_v1",
        "sensitivity": "nexcp_fixed_geometric_weights_v1",
        "nexcp_rho": 0.99,
        "weighted_threshold": "smallest_score_cumulative_weight_ge_v1",
        "calibration_unit": "fold_seed_horizon_pair_tail_v1",
        "base_vector": "guardrail",
        "output_rearrangement": "none",
        "pairs": [[0.02, 0.98], [0.1, 0.9], [0.25, 0.75]],
        "primary_pair": [0.1, 0.9],
        "comparison": "descriptive_model_full_native_mask_seed_mean_counts_v1",
        "profile_quantities": "nesting_crossing_seed_dispersion_tail_beta_reference_v1",
    }


def conformal_parameters() -> ConformalParameters:
    """O VO do bloco do §1."""
    return ConformalParameters.from_mapping(conformal_block())
