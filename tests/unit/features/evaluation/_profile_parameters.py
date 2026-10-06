"""Bloco de regras de perfil válido para testes (Stage 6.6) — do catálogo do VO."""

from __future__ import annotations

import copy

from financial_forecasting.features.evaluation.domain.value_objects.profile_parameters import (
    PROFILE_RULE_CATALOG,
    ProfileParameters,
)

_BLOCK: dict[str, object] = {
    "subset_multiplicity": PROFILE_RULE_CATALOG["subset_multiplicity"],
    "partial_degeneracy_pairs": PROFILE_RULE_CATALOG["partial_degeneracy_pairs"],
    "mcs_block_sensitivity_scheme": PROFILE_RULE_CATALOG["mcs_block_sensitivity_scheme"],
    "stationarity": {
        "acf_max_lag": PROFILE_RULE_CATALOG["stationarity.acf_max_lag"],
        "break_test": PROFILE_RULE_CATALOG["stationarity.break_test"],
        "break_alpha": 0.05,
    },
}


def profile_block() -> dict[str, object]:
    """Cópia profunda do bloco `[profile_parameters]` (forma do TOML)."""
    return copy.deepcopy(_BLOCK)


def profile_parameters() -> ProfileParameters:
    """O VO do bloco válido."""
    return ProfileParameters.from_mapping(_BLOCK)
