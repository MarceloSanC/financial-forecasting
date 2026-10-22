"""DTO `SilverContent` — a identidade do silver que o refresh do gold consumiu (Stage 8.1).

DTO de aplicação **frozen** (concept 8.1 §4, D4; ADR `8_1_0002` itens 3 e 4): o que vai
em `GoldManifest.silver_content`, com `as_mapping()` como a única serialização
(JSON-safe) e `from_mapping()` como a inversa (chaves exatas, hex validado).

- `units` — chave de unidade → digest (`SilverContentHash.value`) de cada unidade de
  conteúdo: `dim_run|<parent_sweep_id>`, `<tabela de fato>|<run_id>|<year>` (com o
  `year` da linha) e `realized|<asset>`. As chaves saem de `unit_key`, dono único do
  formato;
- `tables` — tabela → digest combinado das suas unidades (o realizado entra como a
  tabela `REALIZED_TABLE`);
- `digest` — combinado de **todas** as unidades.

Os digests são calculados pelo `SilverContentAccumulator`; este DTO só os carrega.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex

REALIZED_TABLE: Final = "realized"
UNIT_KEY_SEPARATOR: Final = "|"
_FIELDS: Final = ("digest", "tables", "units")


def unit_key(*parts: object) -> str:
    """Chave de unidade: as partes (`str` não vazia ou `int`) unidas por `|`.

    Raises:
        ValueError: nenhuma parte, parte de outro tipo (inclusive `bool`), `str` vazia
            ou contendo o separador.
    """
    if not parts:
        raise ValueError("unit_key needs at least one part")
    texts: list[str] = []
    for part in parts:
        if isinstance(part, bool) or not isinstance(part, str | int):
            raise ValueError(f"unit key parts must be str or int, got {part!r}")
        text = str(part)
        if not text or UNIT_KEY_SEPARATOR in text:
            raise ValueError(
                f"unit key part must be non-empty and free of {UNIT_KEY_SEPARATOR!r}, got {part!r}"
            )
        texts.append(text)
    return UNIT_KEY_SEPARATOR.join(texts)


def _digest_map(value: object, *, field: str) -> Mapping[str, str]:
    """Mapeamento `str` não vazia → sha256 hex, congelado e ordenado por chave."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a Mapping, got {type(value).__name__}")
    for key, digest in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{field} keys must be non-empty str, got {key!r}")
        validate_sha256_hex(digest, field=f"{field}[{key!r}]")
    return MappingProxyType({key: value[key] for key in sorted(value)})


@dataclass(frozen=True)
class SilverContent:
    """Digest combinado, digest por tabela e digest por unidade do silver consumido.

    Raises:
        ValueError: digest fora de sha256 hex minúsculo, mapeamento não-`Mapping` ou
            chave vazia, na construção.
    """

    digest: str
    tables: Mapping[str, str]
    units: Mapping[str, str]

    def __post_init__(self) -> None:
        validate_sha256_hex(self.digest, field="SilverContent.digest")
        object.__setattr__(self, "tables", _digest_map(self.tables, field="tables"))
        object.__setattr__(self, "units", _digest_map(self.units, field="units"))

    def as_mapping(self) -> dict[str, object]:
        """Serialização JSON-safe (a única), com chaves ordenadas."""
        return {"digest": self.digest, "tables": dict(self.tables), "units": dict(self.units)}

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> SilverContent:
        """Inversa de `as_mapping`.

        Raises:
            ValueError: não-`Mapping`, chave desconhecida ou ausente, ou valor inválido.
        """
        if not isinstance(mapping, Mapping):
            raise ValueError(f"silver_content must be a Mapping, got {type(mapping).__name__}")
        unknown = sorted(str(key) for key in mapping if key not in _FIELDS)
        if unknown:
            raise ValueError(f"silver_content has unknown keys {unknown}")
        missing = [key for key in _FIELDS if key not in mapping]
        if missing:
            raise ValueError(f"silver_content misses the keys {missing}")
        digest = mapping["digest"]
        if not isinstance(digest, str):
            raise ValueError(f"silver_content.digest must be a str, got {digest!r}")
        tables = _digest_map(mapping["tables"], field="tables")
        units = _digest_map(mapping["units"], field="units")
        return cls(digest=digest, tables=tables, units=units)
