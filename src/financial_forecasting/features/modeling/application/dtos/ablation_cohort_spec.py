"""DTO `AblationCohortSpec` — cohort de ablação LOCO por referência ao confirmatório (Stage 7.3).

Espelho, em memória, de `config/cohorts/aapl_ablation.toml` (ADR 7.3.0003 item 1). O
spec de ablação NÃO repete o procedimento: geometria, `tft_params`, horizontes, grade
de quantis, `dataset_fingerprint` e `pipeline_version` vêm do cohort confirmatório
(`base_*`, referenciado pelo id e pelo hash, I4). O que é próprio da ablação:

- as cinco configurações, em ordem fixa (`ABLATION_CONFIGURATIONS`). Cada uma tem a
  identidade derivada do NOME: `excluded_family` (`None` em `full`) e
  `model_version = tft_quantile_loco_<nome>` (I3), mais o `feature_set_hash` do
  subconjunto da registry;
- o `feature_set_name` da ablação (`fs_all_ablation`), uma partição própria de
  `fact_oos_predictions`;
- a partição de famílias congelada (família → features);
- `seeds` ([P], vazio no rascunho), `device` e `torch_build` (versão do torch
  instalada, `None` no rascunho; ADR 7.3.0004).

**Identidade:** `hash_payload()` cobre todo campo (I5: `device` e `torch_build`
inclusive). O hash é calculado por `CohortHash.compute` (regra 6 do `check_layout`),
e `cohort_id = <nome>-r<revisão>-<12 hex>` vai no `parent_sweep_id` de todo run.
`is_frozen()` = seeds não vazias e `torch_build` declarado; `with_freeze` só troca
esses dois campos.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from financial_forecasting.features.modeling.domain.services.loco_identity import (
    ABLATION_CONFIGURATIONS,
    TFT_FAMILIES,
    excluded_family_of,
    loco_model_version,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex

if TYPE_CHECKING:
    from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash

# A regra configuração ↔ família é do domínio (`loco_identity`); reexportada aqui para
# os consumidores do spec.
__all__ = [
    "ABLATION_CONFIGURATIONS",
    "ABLATION_FEATURE_SET_NAME",
    "AblationCohortSpec",
    "AblationConfiguration",
    "AblationDeclarationError",
    "excluded_family_of",
]

ABLATION_FEATURE_SET_NAME: Final = "fs_all_ablation"
_HASH_PREFIX = 12


class AblationDeclarationError(ApplicationError):
    """O arquivo de ablação diverge do confirmatório ou da registry (C2)."""


def _check_text(value: object, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"AblationCohortSpec.{field} must be a non-empty string, got {value!r}")


@dataclass(frozen=True)
class AblationConfiguration:
    """Uma configuração da ablação, com a identidade derivada do nome (I3)."""

    name: str
    excluded_family: str | None
    model_version: str
    feature_set_hash: str

    def __post_init__(self) -> None:
        expected_family = excluded_family_of(self.name)
        if self.excluded_family != expected_family:
            raise ValueError(
                f"configuration {self.name!r}: excluded_family must be {expected_family!r}, "
                f"got {self.excluded_family!r}"
            )
        if self.model_version != loco_model_version(self.name):
            raise ValueError(
                f"configuration {self.name!r}: model_version must be "
                f"{loco_model_version(self.name)!r}, got {self.model_version!r}"
            )
        validate_sha256_hex(
            self.feature_set_hash, field=f"configurations.{self.name}.feature_set_hash"
        )

    @classmethod
    def of(cls, name: str, *, feature_set_hash: str) -> AblationConfiguration:
        """A configuração pelo nome: `excluded_family` e `model_version` derivados."""
        return cls(
            name=name,
            excluded_family=excluded_family_of(name),
            model_version=loco_model_version(name),
            feature_set_hash=feature_set_hash,
        )


def _canonical_partition(partition: object) -> dict[str, tuple[str, ...]]:
    if not isinstance(partition, Mapping):
        raise ValueError(
            f"AblationCohortSpec.family_partition must be a mapping, got {partition!r}"
        )
    if set(partition) != set(TFT_FAMILIES):
        raise ValueError(
            "AblationCohortSpec.family_partition must have exactly the families "
            f"{list(TFT_FAMILIES)}, got {sorted(partition)}"
        )
    seen: dict[str, str] = {}
    canonical: dict[str, tuple[str, ...]] = {}
    for family in TFT_FAMILIES:
        features = partition[family]
        if isinstance(features, str) or not isinstance(features, Sequence) or not features:
            raise ValueError(
                f"AblationCohortSpec.family_partition.{family} must be a non-empty list, "
                f"got {features!r}"
            )
        for feature in features:
            _check_text(feature, field=f"family_partition.{family}")
            if feature in seen:
                raise ValueError(
                    f"AblationCohortSpec.family_partition: feature {feature!r} in both "
                    f"{seen[feature]!r} and {family!r}"
                )
            seen[feature] = family
        canonical[family] = tuple(features)
    return canonical


@dataclass(frozen=True)
class AblationCohortSpec:
    """Especificação do cohort de ablação LOCO (concept 7.3 §4; ADR 7.3.0003)."""

    name: str
    revision: int
    base_cohort_file: str
    base_cohort_id: str
    base_cohort_hash: str
    feature_set_name: str
    configurations: tuple[AblationConfiguration, ...]
    family_partition: Mapping[str, tuple[str, ...]]
    seeds: tuple[int, ...]
    device: str
    torch_build: str | None

    def __post_init__(self) -> None:
        """Forma dos campos; a coerência com a base e a registry é do loader (C2)."""
        for field_name in (
            "name",
            "base_cohort_file",
            "base_cohort_id",
            "feature_set_name",
            "device",
        ):
            _check_text(getattr(self, field_name), field=field_name)
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 0
        ):
            raise ValueError(
                f"AblationCohortSpec.revision must be an int >= 0, got {self.revision!r}"
            )
        validate_sha256_hex(self.base_cohort_hash, field="AblationCohortSpec.base_cohort_hash")
        names = tuple(getattr(c, "name", None) for c in self.configurations)
        if names != ABLATION_CONFIGURATIONS:
            raise ValueError(
                "AblationCohortSpec.configurations must be exactly "
                f"{list(ABLATION_CONFIGURATIONS)} in this order, got {list(names)}"
            )
        if not all(isinstance(c, AblationConfiguration) for c in self.configurations):
            raise ValueError("AblationCohortSpec.configurations must be AblationConfiguration")
        object.__setattr__(self, "family_partition", _canonical_partition(self.family_partition))
        object.__setattr__(self, "seeds", tuple(self.seeds))
        for seed in self.seeds:
            if not isinstance(seed, int) or isinstance(seed, bool) or seed < 1:
                raise ValueError(f"AblationCohortSpec.seeds must be ints >= 1, got {self.seeds!r}")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError(f"AblationCohortSpec.seeds must be unique, got {self.seeds!r}")
        if self.torch_build is not None:
            _check_text(self.torch_build, field="torch_build")

    def configuration(self, name: str) -> AblationConfiguration:
        """A configuração pelo nome."""
        for configuration in self.configurations:
            if configuration.name == name:
                return configuration
        raise KeyError(name)

    def is_frozen(self) -> bool:
        """Congelado = seeds decididas e o build do torch declarado (ADR 7.3.0004)."""
        return bool(self.seeds) and self.torch_build is not None

    def hash_payload(self) -> dict[str, object]:
        """Payload canônico de TODO campo (I5)."""
        return {
            "name": self.name,
            "revision": self.revision,
            "base_cohort_file": self.base_cohort_file,
            "base_cohort_id": self.base_cohort_id,
            "base_cohort_hash": self.base_cohort_hash,
            "feature_set_name": self.feature_set_name,
            "configurations": [
                {
                    "name": c.name,
                    "excluded_family": c.excluded_family,
                    "model_version": c.model_version,
                    "feature_set_hash": c.feature_set_hash,
                }
                for c in self.configurations
            ],
            "family_partition": {f: list(v) for f, v in self.family_partition.items()},
            "seeds": list(self.seeds),
            "device": self.device,
            "torch_build": self.torch_build,
        }

    def cohort_id(self, cohort_hash: CohortHash) -> str:
        """`<nome>-r<revisão>-<12 hex do hash>` — vai no `parent_sweep_id` (I3)."""
        return f"{self.name}-r{self.revision}-{cohort_hash.value[:_HASH_PREFIX]}"

    def with_freeze(self, *, seeds: Sequence[int], torch_build: str) -> AblationCohortSpec:
        """O spec congelado: só `seeds` e `torch_build` mudam."""
        return replace(self, seeds=tuple(seeds), torch_build=torch_build)
