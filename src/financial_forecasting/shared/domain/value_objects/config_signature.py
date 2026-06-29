"""Value object ConfigSignature — assinatura determinística de um dict de config.

Frozen, domínio puro (stdlib-only). O valor é uma string hex sha256 sobre o
JSON canônico da config APÓS remover as chaves voláteis
(`created_at/started_at/ended_at/timestamp`) — variar essas chaves não muda a
assinatura (invariante I5). Replica `compute_config_signature` do repo antigo
(analytics_store_schema.py:37-41) com a canonicalização endurecida vivendo no
`Hasher` (ADR 1.4.0001).

O hash é delegado ao port `Hasher` (injetado na factory `compute`); o domínio
não importa o port em runtime — o type hint usa `TYPE_CHECKING` para preservar
a pureza e a direção inward-only (o Protocol é satisfeito por duck-typing).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from financial_forecasting.shared.application.ports.out.hasher import Hasher

_VOLATILE_KEYS = ("created_at", "started_at", "ended_at", "timestamp")


@dataclass(frozen=True)
class ConfigSignature:
    """Assinatura sha256 de um dict de config sem chaves voláteis.

    Attributes:
        value: string hex sha256 do JSON canônico da config limpa.
    """

    value: str

    @classmethod
    def compute(
        cls,
        *,
        hasher: Hasher,
        config: Mapping[str, object],
    ) -> ConfigSignature:
        """Calcula a assinatura removendo as chaves voláteis antes do hash.

        Copia o config numa estrutura defensiva, descarta
        `created_at/started_at/ended_at/timestamp` e delega ao
        `hasher.hash_mapping`.
        """
        cleaned = {
            key: item for key, item in config.items() if key not in _VOLATILE_KEYS
        }
        return cls(value=hasher.hash_mapping(cleaned))
