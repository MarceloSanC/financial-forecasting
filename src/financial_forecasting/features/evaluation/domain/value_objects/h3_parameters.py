"""VO `H3Parameters` — as regras nomeadas do bloco `[h3]` do pré-registro (Stage 7.3).

Value object de domínio frozen, stdlib-only (concept 7.3 §4; ADR 7.3.0005). É o bloco
opcional `[h3]` de uma revisão do pré-registro (proibido no r0) e vai inteiro ao
`RefreshParameters` e ao manifesto. Toda regra é um identificador aceito **só** se o
domínio a implementa (`H3_RULE_CATALOG`, o padrão do `CONFORMAL_RULE_CATALOG`): mudar a
regra exige identificador novo, código novo e revisão nova.

Forma do TOML (technical 7.3 §1 "Chaves finais do bloco `[h3]`"):

- topo: `families`, `feature_set_hash`, os identificadores do catálogo, `k_p`,
  `permutation_seed`, `reps`, `bootstrap_seed` e `family_alpha`;
- `[h3.partition]`: `partition_hash` (literal de 64 hex, conferido por teste contra o
  `FamilyPartitionHash`) e uma lista de features por família;
- `[h3.ablation]`: `cohort_id`, `cohort_hash`, `seeds`, `reference_model` e `models`
  (família → `tft_quantile_loco_minus_<família>`).

O rascunho da r3 traz o sentinela `"__FILL_AFTER_FREEZE__"` nos três campos da ablação
que só existem depois do freeze no Linux; o VO o recusa em cada um (ADR 7.3.0005 item 2).

O algoritmo, o `k_p` e a semente da permutação repetem as constantes do
`permutation_plan` do `inference` (o `bc-independence` não deixa importar); um teste de
integração trava a igualdade (I17). Os nomes dos modelos LOCO repetem a regra
`loco_model_version` do `modeling`, pelo mesmo motivo.

`as_payload()` é a serialização única (a forma do TOML, JSON-safe, e a do manifesto) e
`from_mapping` a inversa, recusando chave desconhecida/ausente com o caminho pontuado
(`h3.ablation.cohort_hash`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._integer import (
    validate_int_at_least,
)
from financial_forecasting.features.evaluation.domain.value_objects._mapping_keys import (
    missing_key_error,
    unknown_key_error,
)
from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex

H3_RULE_CATALOG: Final[Mapping[str, str]] = MappingProxyType(
    {
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
    }
)
"""Chave do bloco → o **único** identificador que o domínio implementa."""

H3_FAMILIES: Final = ("price", "technical", "sentiment", "fundamental")
"""As quatro famílias do ADR 0.0.0016, na ordem dele."""

FILL_AFTER_FREEZE: Final = "__FILL_AFTER_FREEZE__"
"""Sentinela do rascunho da r3 nos três campos de `[h3.ablation]` (ADR 7.3.0005 item 2)."""

LOCO_REFERENCE_MODEL: Final = "tft_quantile_loco_full"
_LOCO_PREFIX: Final = "tft_quantile_loco_minus_"

_ROOT = "h3"
_PARTITION = "partition"
_ABLATION = "ablation"
_PARTITION_HASH = "partition_hash"
_NUMBER_KEYS: Final = ("k_p", "permutation_seed", "reps", "bootstrap_seed", "family_alpha")
_TOP_KEYS: Final = (
    "families",
    "feature_set_hash",
    *H3_RULE_CATALOG,
    *_NUMBER_KEYS,
    _PARTITION,
    _ABLATION,
)
_ABLATION_KEYS: Final = ("cohort_id", "cohort_hash", "seeds", "reference_model", "models")


def loco_model_of(family: str) -> str:
    """O `model_version` do LOCO que exclui `family` (`tft_quantile_loco_minus_<f>`)."""
    return f"{_LOCO_PREFIX}{family}"


def _require_rule(key: str, value: object) -> None:
    expected = H3_RULE_CATALOG[key]
    if value != expected:
        raise ValueError(
            f"{_ROOT}.{key} must be {expected} (the only rule the domain implements), got {value!r}"
        )


def _refuse_sentinel(value: object, *, path: str) -> None:
    if value == FILL_AFTER_FREEZE:
        raise ValueError(
            f"{path} still holds the draft sentinel {FILL_AFTER_FREEZE!r} — fill it from the "
            "frozen ablation spec"
        )


def _text(value: object, *, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string, got {value!r}")
    return value


def _texts(value: object, *, path: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence) or not value:
        raise ValueError(f"{path} must be a non-empty list of strings, got {value!r}")
    items = tuple(_text(item, path=f"{path}[{index}]") for index, item in enumerate(value))
    if len(set(items)) != len(items):
        raise ValueError(f"{path} must not repeat values, got {list(items)}")
    return items


def _check_families(families: object) -> tuple[str, ...]:
    if isinstance(families, str) or not isinstance(families, Sequence):
        raise ValueError(f"{_ROOT}.families must be a list, got {families!r}")
    if tuple(families) != H3_FAMILIES:
        raise ValueError(
            f"{_ROOT}.families must be {list(H3_FAMILIES)} (ADR 0.0.0016, in this order), "
            f"got {list(families)}"
        )
    return H3_FAMILIES


def _check_partition(partition: object, families: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    path = f"{_ROOT}.{_PARTITION}"
    if not isinstance(partition, Mapping):
        raise ValueError(f"{path} must be a table, got {partition!r}")
    if set(partition) != set(families):
        raise ValueError(
            f"{path} must have exactly the families {list(families)}, got {sorted(partition)}"
        )
    canonical = {f: _texts(partition[f], path=f"{path}.{f}") for f in families}
    seen: dict[str, str] = {}
    for family, features in canonical.items():
        for feature in features:
            if feature in seen:
                raise ValueError(
                    f"{path}: feature {feature!r} is in {seen[feature]!r} and {family!r} "
                    "(the families must be disjoint)"
                )
            seen[feature] = family
    return canonical


def _check_seeds(seeds: object) -> tuple[int, ...]:
    path = f"{_ROOT}.{_ABLATION}.seeds"
    _refuse_sentinel(seeds, path=path)
    if isinstance(seeds, str) or not isinstance(seeds, Sequence) or not seeds:
        raise ValueError(f"{path} must be a non-empty list of ints, got {seeds!r}")
    for index, seed in enumerate(seeds):
        validate_int_at_least(seed, minimum=0, field=f"{path}[{index}]")
    if len(set(seeds)) != len(seeds):
        raise ValueError(f"{path} must not repeat values, got {list(seeds)}")
    return tuple(int(seed) for seed in seeds)


def _check_models(models: object, families: tuple[str, ...]) -> dict[str, str]:
    path = f"{_ROOT}.{_ABLATION}.models"
    if not isinstance(models, Mapping):
        raise ValueError(f"{path} must be a table, got {models!r}")
    expected = {family: loco_model_of(family) for family in families}
    if dict(models) != expected:
        raise ValueError(
            f"{path} must map each family to its LOCO version {expected}, got {dict(models)}"
        )
    return expected


@dataclass(frozen=True, kw_only=True)
class H3Parameters:
    """As regras nomeadas da leitura de H3 (ver docstring do módulo)."""

    families: tuple[str, ...]
    feature_set_hash: str
    partition_rule: str
    permutation_scheme: str
    permutation_algorithm: str
    k_p: int
    permutation_seed: int
    measure: str
    pairing: str
    seed_aggregation: str
    bootstrap_scheme: str
    block_rule: str
    reps: int
    bootstrap_seed: int
    interval: str
    multiplicity: str
    family_alpha: float
    nonpositive_total: str
    reading_rule: str
    vsn_summary: str
    partition: Mapping[str, tuple[str, ...]]
    partition_hash: str
    ablation_cohort_id: str
    ablation_cohort_hash: str
    ablation_seeds: tuple[int, ...]
    ablation_reference_model: str
    ablation_models: Mapping[str, str]

    def __post_init__(self) -> None:
        """Catálogo, as 4 famílias, partição disjunta, hashes, números e a ablação LOCO."""
        for key in H3_RULE_CATALOG:
            _require_rule(key, getattr(self, key))
        families = _check_families(self.families)
        validate_sha256_hex(self.feature_set_hash, field=f"{_ROOT}.feature_set_hash")
        for key in ("k_p", "reps"):
            validate_int_at_least(getattr(self, key), minimum=1, field=f"{_ROOT}.{key}")
        for key in ("permutation_seed", "bootstrap_seed"):
            validate_int_at_least(getattr(self, key), minimum=0, field=f"{_ROOT}.{key}")
        alpha = self.family_alpha
        if not is_finite_number(alpha) or not 0 < alpha < 1:
            raise ValueError(f"{_ROOT}.family_alpha must be a number in (0, 1), got {alpha!r}")
        partition = _check_partition(self.partition, families)
        validate_sha256_hex(self.partition_hash, field=f"{_ROOT}.{_PARTITION}.{_PARTITION_HASH}")
        ablation = f"{_ROOT}.{_ABLATION}"
        _refuse_sentinel(self.ablation_cohort_id, path=f"{ablation}.cohort_id")
        _text(self.ablation_cohort_id, path=f"{ablation}.cohort_id")
        _refuse_sentinel(self.ablation_cohort_hash, path=f"{ablation}.cohort_hash")
        validate_sha256_hex(self.ablation_cohort_hash, field=f"{ablation}.cohort_hash")
        seeds = _check_seeds(self.ablation_seeds)
        if self.ablation_reference_model != LOCO_REFERENCE_MODEL:
            raise ValueError(
                f"{ablation}.reference_model must be {LOCO_REFERENCE_MODEL}, "
                f"got {self.ablation_reference_model!r}"
            )
        models = _check_models(self.ablation_models, families)
        object.__setattr__(self, "families", families)
        object.__setattr__(self, "family_alpha", float(alpha))
        object.__setattr__(self, "partition", MappingProxyType(partition))
        object.__setattr__(self, "ablation_seeds", seeds)
        object.__setattr__(self, "ablation_models", MappingProxyType(models))

    def __hash__(self) -> int:
        """Hash pelos campos que identificam o bloco (os mapeamentos não são hasháveis)."""
        return hash((self.partition_hash, self.ablation_cohort_hash, self.ablation_seeds))

    @property
    def interval_level(self) -> float:
        """Nível de cada intervalo de Δ_f: `1 - family_alpha / |famílias|` (Bonferroni)."""
        return 1 - self.family_alpha / len(self.families)

    def as_payload(self) -> dict[str, object]:
        """A forma do TOML — a única serialização (também a do manifesto)."""
        return {
            "families": list(self.families),
            "feature_set_hash": self.feature_set_hash,
            **{key: getattr(self, key) for key in H3_RULE_CATALOG},
            **{key: getattr(self, key) for key in _NUMBER_KEYS},
            _PARTITION: {
                _PARTITION_HASH: self.partition_hash,
                **{family: list(self.partition[family]) for family in self.families},
            },
            _ABLATION: {
                "cohort_id": self.ablation_cohort_id,
                "cohort_hash": self.ablation_cohort_hash,
                "seeds": list(self.ablation_seeds),
                "reference_model": self.ablation_reference_model,
                "models": {family: self.ablation_models[family] for family in self.families},
            },
        }

    @classmethod
    def from_mapping(cls, mapping: object) -> H3Parameters:
        """Inversa de `as_payload`.

        Raises:
            ValueError: chave desconhecida/ausente (caminho pontuado), tipo, regra fora do
                catálogo, sentinela do rascunho, partição ou ablação inválidas.
        """
        top = _table(mapping, path=_ROOT, keys=_TOP_KEYS)
        families = _check_families(top["families"])
        partition = _table(
            top[_PARTITION], path=f"{_ROOT}.{_PARTITION}", keys=(_PARTITION_HASH, *families)
        )
        ablation = _table(top[_ABLATION], path=f"{_ROOT}.{_ABLATION}", keys=_ABLATION_KEYS)
        models = _table(
            ablation["models"], path=f"{_ROOT}.{_ABLATION}.models", keys=tuple(families)
        )
        seeds = ablation["seeds"]
        return cls(
            families=families,
            feature_set_hash=top["feature_set_hash"],  # type: ignore[arg-type]
            **{key: top[key] for key in H3_RULE_CATALOG},  # type: ignore[arg-type]
            k_p=top["k_p"],  # type: ignore[arg-type]
            permutation_seed=top["permutation_seed"],  # type: ignore[arg-type]
            reps=top["reps"],  # type: ignore[arg-type]
            bootstrap_seed=top["bootstrap_seed"],  # type: ignore[arg-type]
            family_alpha=top["family_alpha"],  # type: ignore[arg-type]
            partition={family: partition[family] for family in families},  # type: ignore[misc]
            partition_hash=partition[_PARTITION_HASH],  # type: ignore[arg-type]
            ablation_cohort_id=ablation["cohort_id"],  # type: ignore[arg-type]
            ablation_cohort_hash=ablation["cohort_hash"],  # type: ignore[arg-type]
            ablation_seeds=seeds,  # type: ignore[arg-type]
            ablation_reference_model=ablation["reference_model"],  # type: ignore[arg-type]
            ablation_models=dict(models),  # type: ignore[arg-type]
        )


def _table(value: object, *, path: str, keys: Sequence[str]) -> Mapping[str, object]:
    """Uma tabela com exatamente `keys`: desconhecida e ausente nomeiam o caminho pontuado."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a table, got {value!r}")
    unknown = sorted(str(key) for key in value if key not in keys)
    if unknown:
        raise unknown_key_error(f"{path}.{unknown[0]}")
    for key in keys:
        if key not in value:
            raise missing_key_error(f"{path}.{key}")
    return value
