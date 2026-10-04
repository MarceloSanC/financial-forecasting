"""Value object AssetId — a regra única de "mesmo ativo" (issue #69 c).

Frozen, domínio puro (stdlib-only). Antes desta VO, só o `ParquetFundamentalFetcher`
normalizava o identificador (`asset_id.split(".", maxsplit=1)[0].upper()`), e os
outros adapters de ingestão passavam o texto adiante como veio: `IngestFundamentals`
gravava `"AAPL"` e `IngestCandles` gravaria `"aapl"`, e o join a jusante devolveria
candles sem fundamentos, em silêncio (Evans, ENTITIES: "the model must define what
it means to be the same thing").

`AssetId.parse(raw)` aplica a regra herdada do fetcher de fundamentos (contrato da
Stage 2.3): tira espaços das pontas, corta o sufixo de bolsa no primeiro `.`
(`"AAPL.US"` → `"AAPL"`) e passa a maiúsculas. O resultado precisa casar com o
padrão de identificador de caminho (`validate_path_identifier`), porque o ativo vira
pedaço de caminho do medalhão (`asset=<valor>`). O construtor direto exige a forma
já canônica.
"""

from __future__ import annotations

from dataclasses import dataclass

from financial_forecasting.shared.domain.services.path_identifier import (
    validate_path_identifier,
)


@dataclass(frozen=True)
class AssetId:
    """Identificador canônico de um ativo (ex.: `"AAPL"`).

    Attributes:
        value: o ticker canônico — sem sufixo de bolsa, em maiúsculas, casando com o
            padrão de identificador de caminho.
    """

    value: str

    def __post_init__(self) -> None:
        validate_path_identifier(self.value, field="asset_id")
        if "." in self.value or self.value != self.value.upper():
            raise ValueError(
                f"asset_id must be canonical (no exchange suffix, uppercase); "
                f"got {self.value!r} — use AssetId.parse"
            )

    @classmethod
    def parse(cls, raw: object) -> AssetId:
        """Normaliza `raw` para a forma canônica (`" aapl.us "` → `"AAPL"`).

        Raises:
            ValueError: `raw` não é `str`, ou a forma normalizada é vazia ou tem
                caractere fora do padrão de identificador de caminho.
        """
        if not isinstance(raw, str):
            raise ValueError(f"asset_id must be a str; got {raw!r}")
        return cls(raw.strip().split(".", maxsplit=1)[0].upper())

    def __str__(self) -> str:
        return self.value
