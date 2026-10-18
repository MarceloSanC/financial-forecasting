"""VO `ConformalParameters` — as regras nomeadas do bloco `[conformal]` (Stage 7.2; ADR 7.2.0001).

Value object de domínio frozen, stdlib-only (concept 7.2 §4). É o bloco opcional
`[conformal]` de uma revisão do pré-registro (proibido no r0) e vai inteiro ao
`RefreshParameters` e ao manifesto. Toda regra é um identificador aceito **só** se o
domínio a implementa (`CONFORMAL_RULE_CATALOG`, o padrão do `PROFILE_RULE_CATALOG`):
mudar a regra exige identificador novo, código novo e revisão nova. Os ids das
variantes repetem os valores do `ConformalVariant` do `inference` (o
`bc-independence` não deixa importar), e um teste de integração trava a igualdade
(I16). ACI e EnbPI não existem (I17).

Os pares são simétricos **exatamente** pelo decimal mais curto de cada nível
(`Fraction(repr(x))`, a convenção do ADR 6.5.0001): 0,1/0,9 e 0,02/0,98 passam,
0,4/0,6000000000000001 não (em float64 a soma dá 1,0).

`as_payload()` é a serialização única (a forma do TOML, JSON-safe, e a do manifesto) e
`from_mapping` a inversa, recusando chave desconhecida/ausente com o caminho pontuado
(`conformal.pairs[1]`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_real_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._mapping_keys import (
    missing_key_error,
    unknown_key_error,
)

CONFORMAL_RULE_CATALOG: Final[Mapping[str, str]] = MappingProxyType(
    {
        "variant_of_record": "split_cqr_asymmetric_unweighted_v1",
        "rank": "ceil_n_plus_1_one_minus_tail_alpha_exact_v1",
        "sensitivity": "nexcp_fixed_geometric_weights_v1",
        "weighted_threshold": "smallest_score_cumulative_weight_ge_v1",
        "calibration_unit": "fold_seed_horizon_pair_tail_v1",
        "base_vector": "guardrail",
        "output_rearrangement": "none",
        "comparison": "descriptive_model_full_native_mask_seed_mean_counts_v1",
        "profile_quantities": "nesting_crossing_seed_dispersion_tail_beta_reference_v1",
    }
)
"""Chave do bloco → o **único** identificador que o domínio implementa."""

_ROOT = "conformal"
_KEYS: Final = (
    "variant_of_record",
    "rank",
    "sensitivity",
    "nexcp_rho",
    "weighted_threshold",
    "calibration_unit",
    "base_vector",
    "output_rearrangement",
    "pairs",
    "primary_pair",
    "comparison",
    "profile_quantities",
)
_HALF = Fraction(1, 2)
_PAIR_SIZE = 2


def _exact(value: float) -> Fraction:
    return Fraction(repr(float(value)))


def _require_rule(key: str, value: object) -> None:
    expected = CONFORMAL_RULE_CATALOG[key]
    if value != expected:
        raise ValueError(
            f"{_ROOT}.{key} must be {expected} (the only rule the domain implements), got {value!r}"
        )


def _pair(value: object, *, path: str) -> tuple[float, float]:
    if (
        isinstance(value, str)
        or not isinstance(value, Sequence)
        or len(value) != _PAIR_SIZE
        or not all(is_real_number(level) and math.isfinite(level) for level in value)
    ):
        raise ValueError(f"{path} must be a pair of two finite numbers, got {value!r}")
    low, high = float(value[0]), float(value[1])
    if _exact(low) + _exact(high) != 1:
        raise ValueError(f"{path} {[low, high]} is not symmetric (lower + upper != 1 exactly)")
    if not 0 < _exact(low) < _HALF:
        raise ValueError(f"{path} lower level {low!r} is not in (0, 0.5)")
    return (low, high)


@dataclass(frozen=True, kw_only=True)
class ConformalParameters:
    """As regras nomeadas do benchmark conformal (ver docstring do módulo)."""

    variant_of_record: str
    rank: str
    sensitivity: str
    nexcp_rho: float
    weighted_threshold: str
    calibration_unit: str
    base_vector: str
    output_rearrangement: str
    pairs: tuple[tuple[float, float], ...]
    primary_pair: tuple[float, float]
    comparison: str
    profile_quantities: str

    def __post_init__(self) -> None:
        """Identificadores do catálogo, rho em (0, 1], pares exatos e o primário entre eles."""
        for key in CONFORMAL_RULE_CATALOG:
            _require_rule(key, getattr(self, key))
        rho = self.nexcp_rho
        if not is_real_number(rho) or not math.isfinite(rho) or not 0 < _exact(rho) <= 1:
            raise ValueError(f"{_ROOT}.nexcp_rho must be a number in (0, 1], got {rho!r}")
        if isinstance(self.pairs, str) or not isinstance(self.pairs, Sequence) or not self.pairs:
            raise ValueError(f"{_ROOT}.pairs must be a non-empty list of pairs, got {self.pairs!r}")
        pairs = tuple(
            _pair(pair, path=f"{_ROOT}.pairs[{index}]") for index, pair in enumerate(self.pairs)
        )
        if len(set(pairs)) != len(pairs):
            raise ValueError(f"{_ROOT}.pairs has a duplicated pair: {list(pairs)}")
        primary = _pair(self.primary_pair, path=f"{_ROOT}.primary_pair")
        if primary not in pairs:
            raise ValueError(f"{_ROOT}.primary_pair {list(primary)} is not one of the pairs")
        object.__setattr__(self, "nexcp_rho", float(rho))
        object.__setattr__(self, "pairs", pairs)
        object.__setattr__(self, "primary_pair", primary)

    def as_payload(self) -> dict[str, object]:
        """A forma do TOML — a única serialização (também a do manifesto)."""
        return {
            "variant_of_record": self.variant_of_record,
            "rank": self.rank,
            "sensitivity": self.sensitivity,
            "nexcp_rho": self.nexcp_rho,
            "weighted_threshold": self.weighted_threshold,
            "calibration_unit": self.calibration_unit,
            "base_vector": self.base_vector,
            "output_rearrangement": self.output_rearrangement,
            "pairs": [list(pair) for pair in self.pairs],
            "primary_pair": list(self.primary_pair),
            "comparison": self.comparison,
            "profile_quantities": self.profile_quantities,
        }

    @classmethod
    def from_mapping(cls, mapping: object) -> ConformalParameters:
        """Inversa de `as_payload`.

        Raises:
            ValueError: chave desconhecida/ausente (caminho pontuado), tipo, regra,
                rho ou par inválidos.
        """
        if not isinstance(mapping, Mapping):
            raise ValueError(f"{_ROOT} must be a table, got {mapping!r}")
        unknown = sorted(str(key) for key in mapping if key not in _KEYS)
        if unknown:
            raise unknown_key_error(f"{_ROOT}.{unknown[0]}")
        for key in _KEYS:
            if key not in mapping:
                raise missing_key_error(f"{_ROOT}.{key}")
        pairs = mapping["pairs"]
        if isinstance(pairs, str) or not isinstance(pairs, Sequence):
            raise ValueError(f"{_ROOT}.pairs must be a list of pairs, got {pairs!r}")
        return cls(
            variant_of_record=mapping["variant_of_record"],
            rank=mapping["rank"],
            sensitivity=mapping["sensitivity"],
            nexcp_rho=mapping["nexcp_rho"],
            weighted_threshold=mapping["weighted_threshold"],
            calibration_unit=mapping["calibration_unit"],
            base_vector=mapping["base_vector"],
            output_rearrangement=mapping["output_rearrangement"],
            pairs=tuple(pairs),
            primary_pair=mapping["primary_pair"],
            comparison=mapping["comparison"],
            profile_quantities=mapping["profile_quantities"],
        )
