"""Value object DatasetContentFingerprint — impressão digital do CONTEÚDO do grid.

Frozen, domínio puro (stdlib-only). Identifica o dado sobre o qual um cohort
treina pelo conteúdo — ativo, nomes das colunas em ordem, timestamps ISO-8601 e
os valores de cada coluna — e não pelos bytes do Parquet (que mudam com a versão
do pyarrow e com metadados). Recebe só as colunas de modelagem do grid já sem o
prefixo sem valor (valores finitos); o `Hasher` canônico arredonda floats a 10
casas, então diferenças abaixo de 1e-10 não mudam a impressão digital (Stage
5.5, concept §4; ADR 5.5.0004).

Coexiste com `DatasetFingerprint` (1.4: somas de close/volume + hash do arquivo),
que não se aplica ao dataset de treino (sem `close`/`volume`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from financial_forecasting.shared.application.ports.out.hasher import Hasher


@dataclass(frozen=True)
class DatasetContentFingerprint:
    """Impressão digital sha256 do conteúdo do grid de treino.

    Attributes:
        value: string hex sha256 do JSON canônico do conteúdo.
    """

    value: str

    @classmethod
    def compute(
        cls,
        *,
        hasher: Hasher,
        asset_id: str,
        timestamps: Sequence[str],
        columns: Mapping[str, Sequence[float]],
    ) -> DatasetContentFingerprint:
        """Calcula a impressão digital do conteúdo.

        A ordem das colunas entra no payload (lista de nomes); valores de cada
        coluna devem ter o mesmo tamanho dos timestamps. NaN/inf são recusados
        pelo hasher canônico.
        """
        for name, values in columns.items():
            if len(values) != len(timestamps):
                raise ValueError(
                    f"column {name!r} has {len(values)} values for {len(timestamps)} timestamps"
                )
        payload = {
            "asset": asset_id,
            "columns": list(columns),
            "timestamps": list(timestamps),
            "values": {name: list(values) for name, values in columns.items()},
        }
        return cls(value=hasher.hash_mapping(payload))
