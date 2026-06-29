"""Value object SplitFingerprint — impressão das listas de timestamps do split.

Frozen, domínio puro (stdlib-only). O valor é uma string hex sha256 sobre o
JSON canônico de `{train, val, test}`, com cada split ORDENADO (`sorted`) antes
do hash — a impressão é invariante à ordem DENTRO de cada split e sensível ao
CONTEÚDO de cada split (invariante I6). Replica `compute_split_fingerprint` do
repo antigo (analytics_store_schema.py:44-55).

Os timestamps chegam como strings ISO8601 já formatadas (o domínio nunca
recebe `datetime` cru — invariante I8). O hash é delegado ao port `Hasher`
(injetado na factory); o domínio não importa o port em runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from financial_forecasting.shared.application.ports.out.hasher import Hasher


@dataclass(frozen=True)
class SplitFingerprint:
    """Impressão sha256 das listas de timestamps de train/val/test.

    Attributes:
        value: string hex sha256 do JSON canônico de `{train, val, test}`
            com cada split ordenado.
    """

    value: str

    @classmethod
    def compute(
        cls,
        *,
        hasher: Hasher,
        train: Sequence[str],
        val: Sequence[str],
        test: Sequence[str],
    ) -> SplitFingerprint:
        """Calcula a impressão ordenando cada split antes do hash.

        Monta `{"train": sorted(train), "val": sorted(val), "test":
        sorted(test)}` e delega ao `hasher.hash_mapping`.
        """
        payload = {
            "train": sorted(train),
            "val": sorted(val),
            "test": sorted(test),
        }
        return cls(value=hasher.hash_mapping(payload))
