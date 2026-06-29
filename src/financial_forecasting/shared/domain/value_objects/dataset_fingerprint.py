"""Value object DatasetFingerprint — impressão digital estrutural de um dataset.

Frozen, domínio puro (stdlib-only). O valor é uma string hex sha256 sobre o
JSON canônico do payload estruturado
`{asset, timestamp_min, timestamp_max, row_count, close_sum, volume_sum,
parquet_file_hash}`. Replica o esquema de `compute_dataset_fingerprint` do repo
antigo (analytics_store_schema.py:58-77) — adotando SOMENTE o esquema
estruturado e descartando a variante ad-hoc `'|'.join` (concept D4).

A canonicalização de floats (`round(x, 10)`) e a rejeição de NaN/±inf vivem
DENTRO do `Hasher` (ADR 1.4.0001), não no VO: o VO monta o payload com os
floats crus e confia no contrato do port. O `parquet_file_hash` chega
pré-calculado (sem I/O no domínio — invariante I8); o cálculo do hash do
arquivo é do adapter de persistência (Step 4.x).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from financial_forecasting.shared.application.ports.out.hasher import Hasher


@dataclass(frozen=True)
class DatasetFingerprint:
    """Impressão sha256 estrutural de um dataset.

    Attributes:
        value: string hex sha256 do JSON canônico do payload estruturado.
    """

    value: str

    @classmethod
    def compute(  # noqa: PLR0913 — payload canônico do dataset tem 7 campos
        # fixos (concept §4 / old analytics_store_schema.py:68-76); a assinatura
        # explícita keyword-only é o contrato, não acidente — preferível a um
        # dict opaco que perderia type safety.
        cls,
        *,
        hasher: Hasher,
        asset: str,
        timestamp_min: str,
        timestamp_max: str,
        row_count: int,
        close_sum: float,
        volume_sum: float,
        parquet_file_hash: str,
    ) -> DatasetFingerprint:
        """Monta o payload estruturado e delega o hash ao port.

        `row_count` é normalizado para `int` e os somatórios para `float`
        (espelha o old); o arredondamento a 10 casas e a rejeição de NaN/±inf
        são responsabilidade do `Hasher` (ADR 1.4.0001).
        """
        payload: dict[str, object] = {
            "asset": asset,
            "timestamp_min": timestamp_min,
            "timestamp_max": timestamp_max,
            "row_count": int(row_count),
            "close_sum": float(close_sum),
            "volume_sum": float(volume_sum),
            "parquet_file_hash": parquet_file_hash,
        }
        return cls(value=hasher.hash_mapping(payload))
