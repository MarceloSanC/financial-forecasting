"""Port-out `JudgedGenerationStore` — a cópia selada da geração julgada (Stage 8.1).

Port do **consumidor** (concept 8.1 §4, D5, D12; ADRs `8_1_0003` itens 1-5b e
`8_1_0004` item 1). Por partição do gold:

- `find(partition, preregistration_ref)` — sem `judged/<ref>/` → `None`; senão relê
  `CONTENTS.sha256`, recalcula o sha256 de cada arquivo e o digest; arquivo alterado,
  faltando, a mais ou `generation/` vazio → `JudgedGenerationTamperedError`;
- `preserve(partition, preregistration_ref, expected_manifest, documents)` — com
  `judged/<ref>/` já existente → `JudgedGenerationExistsError` antes de escrever; senão
  remove o staging sobrante, copia `current/` para o staging, confere o manifesto copiado
  contra `expected_manifest` (diferente → `JudgedGenerationMismatchError`, staging
  removido), grava os documentos (`document_bytes`), grava `CONTENTS.sha256` **por
  último** e troca o staging para `judged/<ref>/`; falha de escrita propaga e não sela;
- `judged_refs(partition)` — as referências seladas (nunca o staging nem o log);
- `record_attempt(partition, attempt)` / `attempts(partition)` — o log write-ahead
  `judged/ATTEMPTS.jsonl`, na ordem de gravação.

Nenhum caminho de código sobrescreve, move ou apaga uma cópia selada ou o log. A geração
viva é lida pelo `GoldGenerationReader.read_generation` que já existe. O formato da
listagem, dos documentos e das linhas do log tem dono único em
`application/dtos/judged_generation.py`.

O real é o `ParquetGoldStore` (`adapters/out/duckdb/`), dono único do layout do gold; o
fake é o `InMemoryJudgedGenerationStore` (`tests/fakes/features/evaluation/`). Os erros
moram aqui, junto do port (precedente `PreregistrationNotFoundError`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    JudgedAttempt,
    JudgedGeneration,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldManifest,
    GoldPartition,
)
from financial_forecasting.shared.application.exceptions import ApplicationError


class JudgedGenerationTamperedError(ApplicationError):
    """A cópia selada não confere com o seu `CONTENTS.sha256` (ou com o registro commitado)."""


class JudgedGenerationMismatchError(ApplicationError):
    """O manifesto copiado de `current/` não é o que o refresh devolveu (nada é selado)."""


class JudgedGenerationExistsError(ApplicationError):
    """Já existe uma geração julgada (ou tentativa) que impede selar esta (D12)."""


class JudgedGenerationStore(Protocol):
    """Preserva e relê a cópia selada da geração julgada de uma partição."""

    def find(
        self, *, partition: GoldPartition, preregistration_ref: str
    ) -> JudgedGeneration | None:
        """A cópia selada de `preregistration_ref`, conferida, ou `None` se não houver.

        Raises:
            JudgedGenerationTamperedError: a cópia não confere com o `CONTENTS.sha256`.
        """
        ...

    def preserve(
        self,
        *,
        partition: GoldPartition,
        preregistration_ref: str,
        expected_manifest: GoldManifest,
        documents: Mapping[str, Mapping[str, object]],
    ) -> JudgedGeneration:
        """Copia `current/`, grava os documentos e sela com `CONTENTS.sha256` por último.

        Raises:
            JudgedGenerationExistsError: `judged/<ref>/` já existe (nada é escrito).
            JudgedGenerationMismatchError: o manifesto copiado ≠ `expected_manifest`.
            GoldManifestNotFoundError: a partição não tem geração viva.
            OSError: falha de escrita (nada é selado).
        """
        ...

    def judged_refs(self, *, partition: GoldPartition) -> tuple[str, ...]:
        """As referências com cópia selada na partição, ordenadas."""
        ...

    def record_attempt(self, *, partition: GoldPartition, attempt: JudgedAttempt) -> None:
        """Acrescenta uma linha ao log de tentativas da partição."""
        ...

    def attempts(self, *, partition: GoldPartition) -> tuple[JudgedAttempt, ...]:
        """As linhas do log de tentativas da partição, na ordem de gravação."""
        ...
