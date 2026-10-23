"""Fake do port `JudgedGenerationStore` — cópias seladas em memória (Stage 8.1).

Copia a geração viva de um `InMemoryGoldStore` para "arquivos" em memória (caminho
relativo → bytes): `generation/MANIFEST.json` com os bytes de `document_bytes` do
manifesto guardado e `generation/<tabela>.parquet` com os bytes JSON das linhas —
determinísticos, então o digest se repete entre execuções. Os documentos, a listagem
`CONTENTS.sha256` e o digest saem das MESMAS funções de
`application/dtos/judged_generation.py` que o `ParquetGoldStore` usa; o `find` monta a
cópia por `judged_generation_from`, a mesma conferência do real.

`read_judged_generation` (Stage 8.2) confere a cópia pelo `find` e devolve a geração
copiada no `preserve` (manifesto e linhas guardados junto da cópia), montada pelo dono único
`GoldGeneration.from_stored` — o real relê os arquivos de `judged/<ref>/generation/`.

Contadores: `preserves` (selagens concluídas) e `recorded` (linhas de tentativa).
Ganchos da suíte de contrato: `tamper` (troca ou remove um arquivo selado),
`rewrite_contents` (regrava a listagem coerente com os arquivos atuais),
`leave_staging` (deixa um staging sobrante, como um `preserve` interrompido) e
`fail_writes` (nomes de arquivo cuja escrita ergue `OSError`).
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping

from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    CONTENTS_NAME,
    GENERATION_DIR,
    GENERATION_MANIFEST,
    JudgedAttempt,
    JudgedGeneration,
    check_documents,
    check_identity,
    check_judged_ref,
    contents_listing,
    document_bytes,
    judged_generation_from,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldGenerationCorruptError,
    GoldManifest,
    GoldManifestNotFoundError,
    GoldPartition,
)
from financial_forecasting.features.evaluation.application.ports.out.judged_generation_store import (  # noqa: E501
    JudgedGenerationExistsError,
    JudgedGenerationMismatchError,
    JudgedGenerationNotFoundError,
    JudgedGenerationTamperedError,
)
from tests.fakes.features.evaluation.in_memory_gold_store import Generation, InMemoryGoldStore

Files = dict[str, bytes]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class InMemoryJudgedGenerationStore:
    """Satisfaz `JudgedGenerationStore` sobre a geração viva de um `InMemoryGoldStore`."""

    def __init__(self, store: InMemoryGoldStore) -> None:
        self._store = store
        self._sealed: dict[tuple[GoldPartition, str], Files] = {}
        self._copied: dict[tuple[GoldPartition, str], Generation] = {}
        self._staging: dict[GoldPartition, Files] = {}
        self._attempts: dict[GoldPartition, list[JudgedAttempt]] = {}
        self.preserves = 0
        self.recorded = 0
        self.fail_writes: set[str] = set()

    # -- port ------------------------------------------------------------------------

    def find(
        self, *, partition: GoldPartition, preregistration_ref: str
    ) -> JudgedGeneration | None:
        check_judged_ref(preregistration_ref)
        files = self._sealed.get((partition, preregistration_ref))
        if files is None:
            return None
        if CONTENTS_NAME not in files:
            raise JudgedGenerationTamperedError(f"{preregistration_ref}: no {CONTENTS_NAME}")
        actual = {path: _sha256(data) for path, data in files.items() if path != CONTENTS_NAME}
        try:
            return judged_generation_from(
                partition=partition,
                preregistration_ref=preregistration_ref,
                listing=files[CONTENTS_NAME],
                actual=actual,
                read=files.__getitem__,
            )
        except ValueError as error:
            raise JudgedGenerationTamperedError(f"{preregistration_ref}: {error}") from error

    def preserve(
        self,
        *,
        partition: GoldPartition,
        preregistration_ref: str,
        expected_manifest: GoldManifest,
        documents: Mapping[str, Mapping[str, object]],
    ) -> JudgedGeneration:
        check_judged_ref(preregistration_ref)
        if (partition, preregistration_ref) in self._sealed:
            raise JudgedGenerationExistsError(f"{preregistration_ref} is already sealed")
        try:
            check_identity(
                partition=partition,
                preregistration_ref=preregistration_ref,
                manifest=expected_manifest,
            )
        except ValueError as error:
            raise JudgedGenerationMismatchError(str(error)) from error
        check_documents(documents)
        self._staging.pop(partition, None)  # staging sobrante de um preserve interrompido
        live = self._store.current(partition)
        if live is None:
            raise GoldManifestNotFoundError(f"no gold generation for {partition}")
        staging: Files = {}
        self._staging[partition] = staging
        manifest_mapping, tables = live
        staging[GENERATION_MANIFEST] = document_bytes(manifest_mapping)
        for name, rows in tables.items():
            staging[f"{GENERATION_DIR}/{name}.parquet"] = document_bytes({"rows": rows})
        copied = GoldManifest.from_mapping(json.loads(staging[GENERATION_MANIFEST]))
        if copied != expected_manifest:
            del self._staging[partition]
            raise JudgedGenerationMismatchError(
                f"the copied manifest of {partition} is not the one the refresh returned"
            )
        for name in sorted(documents):
            self._write(staging, name, document_bytes(documents[name]))
        listing = contents_listing({path: _sha256(data) for path, data in staging.items()})
        self._write(staging, CONTENTS_NAME, listing)
        self._sealed[partition, preregistration_ref] = self._staging.pop(partition)
        self._copied[partition, preregistration_ref] = copy.deepcopy(live)
        self.preserves += 1
        sealed = self.find(partition=partition, preregistration_ref=preregistration_ref)
        assert sealed is not None
        return sealed

    def read_judged_generation(
        self, *, partition: GoldPartition, preregistration_ref: str
    ) -> GoldGeneration:
        if self.find(partition=partition, preregistration_ref=preregistration_ref) is None:
            raise JudgedGenerationNotFoundError(
                f"no judged copy of {preregistration_ref} for {partition}"
            )
        manifest, rows_by_table = self._copied[partition, preregistration_ref]
        try:
            return GoldGeneration.from_stored(manifest, rows_by_table, partition=partition)
        except GoldGenerationCorruptError as error:
            raise JudgedGenerationTamperedError(f"{preregistration_ref}: {error}") from error

    def judged_refs(self, *, partition: GoldPartition) -> tuple[str, ...]:
        return tuple(sorted(ref for owner, ref in self._sealed if owner == partition))

    def record_attempt(self, *, partition: GoldPartition, attempt: JudgedAttempt) -> None:
        self._attempts.setdefault(partition, []).append(attempt)
        self.recorded += 1

    def attempts(self, *, partition: GoldPartition) -> tuple[JudgedAttempt, ...]:
        return tuple(self._attempts.get(partition, ()))

    # -- ganchos da suíte de contrato --------------------------------------------------

    def staging_exists(self, partition: GoldPartition) -> bool:
        return partition in self._staging

    def leave_staging(self, partition: GoldPartition) -> None:
        """Um staging sobrante com lixo, como o de um `preserve` interrompido."""
        self._staging[partition] = {f"{GENERATION_DIR}/leftover.parquet": b"partial"}

    def tamper(
        self, *, partition: GoldPartition, preregistration_ref: str, path: str, data: bytes | None
    ) -> None:
        """Troca (`data`) ou remove (`None`) um arquivo da cópia selada."""
        files = self._sealed[partition, preregistration_ref]
        if data is None:
            del files[path]
        else:
            files[path] = data

    def move(self, *, partition: GoldPartition, source: str, target: str) -> None:
        """Move a cópia selada `source` para `target` (como um `mv` no disco)."""
        self._sealed[partition, target] = self._sealed.pop((partition, source))
        self._copied[partition, target] = self._copied.pop((partition, source))

    def rewrite_contents(self, *, partition: GoldPartition, preregistration_ref: str) -> None:
        """Regrava `CONTENTS.sha256` coerente com os arquivos atuais da cópia."""
        files = self._sealed[partition, preregistration_ref]
        actual = {path: _sha256(data) for path, data in files.items() if path != CONTENTS_NAME}
        files[CONTENTS_NAME] = contents_listing(actual)

    def _write(self, staging: Files, name: str, data: bytes) -> None:
        if name in self.fail_writes:
            raise OSError(f"injected write failure on {name}")
        staging[name] = data
