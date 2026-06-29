"""Port compartilhado: Hasher.

Abstrai o hashing canônico determinístico usado pela identidade do projeto
(RunId, DatasetFingerprint, ConfigSignature, SplitFingerprint). Os value
objects de domínio constroem o payload e delegam o hash a este port — nunca
serializam/hasheiam inline — para que a semântica canônica viva num único
lugar (o adapter), seja contract-testada contra um fake, e seja trocável sem
tocar no domínio.

Semântica canônica garantida por qualquer implementação deste contrato:

- `hash_mapping`: sha256 hex sobre o JSON canônico do mapping, com chaves
  ordenadas (`sort_keys`), separadores compactos e UTF-8 preservado. A ORDEM
  de inserção das chaves é IRRELEVANTE (dois mappings com mesmas chaves/valores
  em ordens diferentes produzem o mesmo hash). Floats são canonicalizados de
  forma estável (arredondamento declarado, ver ADR 1.4.0001) para blindar
  contra não-determinismo de último-ULP entre versões/plataformas da stack
  numérica. `None` mapeia para `null`. NaN e ±inf são REJEITADOS com
  `ValueError` (fail-fast: indicam dado corrompido a montante, não estado
  legítimo a fingerprintar).
- `hash_text`: sha256 hex sobre os bytes UTF-8 do texto, direto e SENSÍVEL à
  ordem (usado p.ex. para `feature_set_hash` via `"|".join(features_ordered)`).

Ver ADR docs/adr/1_4_0001-canonicalizacao-de-hash-deterministico.md.
"""

from collections.abc import Mapping
from typing import Protocol


class Hasher(Protocol):
    """Contrato de hashing canônico determinístico."""

    def hash_mapping(self, payload: Mapping[str, object]) -> str:
        """sha256 hex sobre o JSON canônico do mapping.

        Semântica canônica garantida: chaves ordenadas (`sort_keys`); ordem de
        inserção irrelevante; floats canonicalizados de forma estável
        (arredondamento declarado); `None` -> `null`; NaN/±inf REJEITADOS com
        `ValueError`. Retorna o hex digest sha256 do JSON canônico.
        """
        ...

    def hash_text(self, text: str) -> str:
        """sha256 hex sobre os bytes UTF-8 do texto.

        Direto e SENSÍVEL à ordem (`"a|b" != "b|a"`). Usado p.ex. para o
        `feature_set_hash` via `"|".join(features_ordered)`.
        """
        ...
