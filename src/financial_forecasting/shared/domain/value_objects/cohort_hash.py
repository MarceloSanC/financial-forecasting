"""Value object CohortHash — identidade do cohort confirmatório (Stage 5.5).

Frozen, domínio puro (stdlib-only). O valor é o sha256 hex do JSON canônico do
payload inteiro da especificação do cohort (candidato, comparadores, seeds,
geometria, grade de quantis, sweeps, proveniência, impressão digital do dado):
mudar qualquer campo muda o hash (ADR 5.5.0001, I2). Vive aqui porque o
`check_layout` só permite `hash_mapping` dentro de `shared/domain/value_objects/`
— identidade só pelos VOs de shared (precedente: ADR 5.2.0004).

O hash é delegado ao port `Hasher`; o type hint usa `TYPE_CHECKING` para
preservar a pureza do domínio (o Protocol é satisfeito por duck-typing).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from financial_forecasting.shared.application.ports.out.hasher import Hasher


@dataclass(frozen=True)
class CohortHash:
    """Hash sha256 do payload canônico de um cohort.

    Attributes:
        value: string hex sha256 do JSON canônico do payload.
    """

    value: str

    @classmethod
    def compute(cls, *, hasher: Hasher, payload: Mapping[str, object]) -> CohortHash:
        """Calcula o hash do payload inteiro (sem remover chave nenhuma)."""
        return cls(value=hasher.hash_mapping(payload))
