"""VO `FamilyLossDifferentials` — as séries d_t de H3 de um método (Stage 7.3).

Value object de domínio frozen, stdlib-only (concept 7.3 §4; ADR 7.3.0001 item 1; I10,
I11). Uma série de diferenciais de perda por (família, horizonte), pareada por ponto de
decisão na interseção de h+1 e h+7 (H3-PAIR), já agregada nas seeds (H3-SEEDS):

- `permutation`: d_{f,t}(h) = média nas seeds da média nas k de (L^{perm f,k} - L^{id});
- `loco`: d_{f,t}(h) = média nas seeds de L^{-f} - média nas seeds de L^{full}.

Mais os perfis: a importância por seed (média em t, por seed) e, só na permutação, por
permutação k (média em t e nas seeds). É o insumo do `FamilyContribution` (bootstrap
conjunto dos dois métodos sobre as mesmas decisões).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._integer import (
    validate_int_at_least,
)
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3_FAMILIES,
)
from financial_forecasting.features.evaluation.domain.value_objects.permuted_run_losses import (
    check_decision_timestamps,
    check_loss_series,
)

PERMUTATION: Final = "permutation"
LOCO: Final = "loco"
H3_METHODS: Final = (PERMUTATION, LOCO)
H3_HORIZONS: Final = (1, 7)


def _check_profile(
    profile: object, *, field: str, families: tuple[str, ...], horizons: tuple[int, ...]
) -> dict[tuple[str, int, int], float]:
    """(família, h, índice) → importância finita, com família e horizonte do VO."""
    if not isinstance(profile, Mapping):
        raise ValueError(f"{field} must be a mapping, got {profile!r}")
    checked: dict[tuple[str, int, int], float] = {}
    for key, value in profile.items():
        if not isinstance(key, tuple) or len(key) != 3:  # noqa: PLR2004 — (f, h, índice)
            raise ValueError(f"{field} key must be (family, horizon, index), got {key!r}")
        family, horizon, index = key
        if family not in families or horizon not in horizons:
            raise ValueError(f"{field} key {key!r} is outside the families and horizons")
        validate_int_at_least(index, minimum=0, field=f"{field}{list(key)} index")
        if not is_finite_number(value):
            raise ValueError(f"{field}{list(key)} must be a finite number, got {value!r}")
        checked[key] = float(value)
    return {key: checked[key] for key in sorted(checked)}


@dataclass(frozen=True, kw_only=True)
class FamilyLossDifferentials:
    """As séries d_t por (família, horizonte) de um método, com os perfis por seed e por k."""

    method: str
    families: tuple[str, ...]
    horizons: tuple[int, ...]
    decision_timestamps: tuple[str, ...]
    differentials: Mapping[tuple[str, int], tuple[float, ...]]
    seed_importances: Mapping[tuple[str, int, int], float]
    permutation_importances: Mapping[tuple[str, int, int], float]

    def __post_init__(self) -> None:
        """Método, as 4 famílias, horizontes (1, 7), uma d_t por decisão e perfis coerentes."""
        if self.method not in H3_METHODS:
            raise ValueError(f"method must be one of {list(H3_METHODS)}, got {self.method!r}")
        if tuple(self.families) != H3_FAMILIES:
            raise ValueError(f"families must be {list(H3_FAMILIES)}, got {self.families!r}")
        if tuple(self.horizons) != H3_HORIZONS:
            raise ValueError(f"horizons must be {list(H3_HORIZONS)}, got {self.horizons!r}")
        families, horizons = H3_FAMILIES, H3_HORIZONS
        timestamps = check_decision_timestamps(self.decision_timestamps)
        if not isinstance(self.differentials, Mapping):
            raise ValueError(f"differentials must be a mapping, got {self.differentials!r}")
        expected = {(family, horizon) for family in families for horizon in horizons}
        if set(self.differentials) != expected:
            raise ValueError(
                f"differentials must have exactly the keys (family, horizon) of "
                f"{list(families)} x {list(horizons)}, got {sorted(self.differentials)}"
            )
        differentials = {
            key: check_loss_series(
                self.differentials[key], length=len(timestamps), field=f"differentials{list(key)}"
            )
            for key in sorted(expected, key=lambda k: (families.index(k[0]), k[1]))
        }
        seeds = _check_profile(
            self.seed_importances, field="seed_importances", families=families, horizons=horizons
        )
        permutations = _check_profile(
            self.permutation_importances,
            field="permutation_importances",
            families=families,
            horizons=horizons,
        )
        if self.method == LOCO and permutations:
            raise ValueError("permutation_importances must be empty in the loco method")
        if self.method == PERMUTATION and any(key[2] < 1 for key in permutations):
            raise ValueError("permutation_importances indices are k >= 1")
        object.__setattr__(self, "families", families)
        object.__setattr__(self, "horizons", horizons)
        object.__setattr__(self, "decision_timestamps", timestamps)
        object.__setattr__(self, "differentials", MappingProxyType(differentials))
        object.__setattr__(self, "seed_importances", MappingProxyType(seeds))
        object.__setattr__(self, "permutation_importances", MappingProxyType(permutations))

    def __hash__(self) -> int:
        """Hash pelo método e decisões (os mapeamentos não são hasháveis)."""
        return hash((self.method, self.decision_timestamps))
