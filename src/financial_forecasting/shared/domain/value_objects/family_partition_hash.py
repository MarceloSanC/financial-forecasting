"""Value object FamilyPartitionHash — identidade da partição de famílias (Stage 7.3).

Frozen, domínio puro (stdlib-only). O valor é o sha256 hex do JSON canônico de

    {"feature_set_hash": <64 hex>, "partition": {família: sorted(features)}}

O inference grava esse hash em cada linha permutada e no manifesto da atribuição, e o
evaluation confere o hash das linhas contra o do bloco `[h3]` do pré-registro (concept
7.3 I17; ADR 7.3.0002 item 4). As features de cada família são ordenadas antes do hash:
a troca conjunta de uma família não depende da ordem das colunas. As chaves de família
são ordenadas pelo hasher canônico. Mover uma feature de uma família para outra muda o
hash, e trocar só o `feature_set_hash` também.

Vive aqui porque o `check_layout` (regra 6) só permite `hash_mapping` dentro de
`shared/domain/value_objects/`. Precedentes: `CohortHash` e `PreregistrationHash`. O
`feature_set_hash` vem sempre do chamador, lido do spec do cohort confirmatório, e nunca
é recalculado aqui.

O hash é delegado ao port `Hasher`; o type hint usa `TYPE_CHECKING` para preservar a
pureza do domínio (o Protocol é satisfeito por duck-typing).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex

if TYPE_CHECKING:
    from financial_forecasting.shared.application.ports.out.hasher import Hasher


def _check_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string, got {value!r}")
    return value


def canonical_partition(partition: object) -> dict[str, list[str]]:
    """A partição validada, com as features de cada família ordenadas.

    Raises:
        ValueError: partição vazia ou não-mapeamento, família vazia, nome de família ou
            de feature vazio, feature repetida dentro de uma família ou entre famílias.
    """
    if not isinstance(partition, Mapping) or not partition:
        raise ValueError(f"partition must be a non-empty mapping, got {partition!r}")
    seen: dict[str, str] = {}
    canonical: dict[str, list[str]] = {}
    for family, features in partition.items():
        _check_text(family, field="partition family")
        if isinstance(features, str) or not isinstance(features, Sequence) or not features:
            raise ValueError(
                f"partition.{family} must be a non-empty sequence of features, got {features!r}"
            )
        for feature in features:
            _check_text(feature, field=f"partition.{family} feature")
            if feature in seen:
                raise ValueError(
                    f"partition: feature {feature!r} repeated (in {seen[feature]!r} and {family!r})"
                )
            seen[feature] = family
        canonical[family] = sorted(features)
    return canonical


@dataclass(frozen=True)
class FamilyPartitionHash:
    """Hash sha256 da partição de famílias junto com o `feature_set_hash`.

    Attributes:
        value: string hex sha256 do JSON canônico do payload do módulo.
    """

    value: str

    def __post_init__(self) -> None:
        # o construtor cru também passa por aqui, não só a factory `compute` (#160)
        validate_sha256_hex(self.value, field="FamilyPartitionHash.value")

    @classmethod
    def compute(
        cls,
        *,
        hasher: Hasher,
        feature_set_hash: str,
        partition: Mapping[str, Sequence[str]],
    ) -> FamilyPartitionHash:
        """Calcula o hash da partição validada (features ordenadas por família).

        Raises:
            ValueError: `feature_set_hash` fora de 64 hex minúsculos, ou partição
                inválida (ver `canonical_partition`).
        """
        validate_sha256_hex(feature_set_hash, field="feature_set_hash")
        payload: dict[str, object] = {
            "feature_set_hash": feature_set_hash,
            "partition": canonical_partition(partition),
        }
        return cls(value=hasher.hash_mapping(payload))
