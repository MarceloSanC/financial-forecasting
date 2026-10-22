"""Adapter `ParquetGoldStore` — satisfaz o port `GoldStore` com Parquet + troca de pasta.

Concept 6.4 D8, C3, C9; ADR `6_4_0005` itens 2, 5 e 6. Layout por partição:

    <data_root>/gold/asset=<a>/parent_sweep_id=<p>/current/<table>.parquet
    <data_root>/gold/asset=<a>/parent_sweep_id=<p>/current/MANIFEST.json

`publish`, nesta ordem:

1. `check_generation` (dono único da coerência partição x tabelas x manifesto, no
   módulo dos DTOs) e `validate_path_identifier` em `asset` e `parent_sweep_id` (dono único em
   `shared/domain`, C3 "de novo no `ParquetGoldStore`") — antes de montar caminho;
2. remove `.staging/` e `.previous/` sobrantes de uma execução interrompida;
3. grava cada tabela em `.staging/<name>.parquet` (`pyarrow.Table.from_pylist` →
   `pyarrow.parquet.write_table`, em `_write_table`) e o `MANIFEST.json` **por último**
   (`json.dumps(manifest.as_mapping(), sort_keys=True, indent=2)`, em
   `_write_manifest`);
4. `os.replace(current, .previous)` se `current/` existe; `os.replace(.staging,
   current)` — se esta segunda troca falhar, `.previous/` volta a `current/` e o erro
   propaga (rollback); um `publish` que encontra `.previous/MANIFEST.json` sem
   `current/` (crash entre as trocas) restaura `.previous/` antes de limpar;
5. `shutil.rmtree(.previous)` — `OSError` aqui vira `logger.warning` e o `publish`
   retorna normalmente (a geração nova já está viva; o próximo `publish` limpa).

Também satisfaz o port `GoldGenerationReader` (Stage 6.5, ADR `6_5_0005` itens 1, 4, 5):
`read_generation` lê o `MANIFEST.json` de `current/` **antes** de qualquer tabela, lê
cada tabela listada com `pyarrow.parquet.read_table(path, partitioning=None)` (sem
inferência hive: as colunas `asset`/`parent_sweep_id` vêm do conteúdo), passa `[]`
para tabela com zero linhas no manifesto (o arquivo ainda precisa existir) e monta a
geração **só** por `GoldGeneration.from_stored` — este adapter faz apenas I/O.

Falha antes da troca propaga e deixa `current/` intacto (C9). Escritor único por
partição é pré-condição do port (ADR `6_4_0005` item 6): sem lock.

Satisfaz também o port `JudgedGenerationStore` (Stage 8.1, ADRs `8_1_0003` itens 1-5b e
`8_1_0004` item 1) — dono único do layout do gold, então nenhum segundo adapter
redeclara caminhos:

    <partição>/judged/<preregistration_ref>/generation/...   (cópia byte a byte de current/)
    <partição>/judged/<preregistration_ref>/<documento>.json
    <partição>/judged/<preregistration_ref>/CONTENTS.sha256    (gravado por último)
    <partição>/judged/.staging/                               (removido no início do preserve)
    <partição>/judged/ATTEMPTS.jsonl                          (temporário + os.replace)

O formato da listagem, dos documentos e das linhas do log é o de
`application/dtos/judged_generation.py` (o mesmo do fake); o sha256 de cada arquivo é
calculado por streaming (`hashlib`, blocos de 1 MiB). Nenhum caminho de código
sobrescreve, move ou apaga uma cópia selada nem o log.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

import pyarrow as pa
import pyarrow.parquet as pq

from financial_forecasting.features.evaluation.application.dtos.gold_schema import GOLD_SCHEMAS
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    ATTEMPTS_NAME,
    CONTENTS_NAME,
    GENERATION_DIR,
    GENERATION_MANIFEST,
    JudgedAttempt,
    JudgedGeneration,
    attempts_jsonl,
    check_documents,
    contents_listing,
    document_bytes,
    judged_generation_from,
    parse_attempts_jsonl,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldGenerationCorruptError,
    GoldManifest,
    GoldManifestNotFoundError,
    GoldPartition,
    GoldTable,
    check_generation,
)
from financial_forecasting.features.evaluation.application.ports.out.judged_generation_store import (  # noqa: E501
    JudgedGenerationExistsError,
    JudgedGenerationMismatchError,
    JudgedGenerationTamperedError,
)
from financial_forecasting.shared.domain.services.path_identifier import (
    validate_path_identifier,
)

logger = logging.getLogger(__name__)

MANIFEST_NAME = "MANIFEST.json"
_CURRENT = "current"
_STAGING = ".staging"
_PREVIOUS = ".previous"
_JUDGED = "judged"
_SHA256_BLOCK: Final = 1 << 20  # streaming do sha256 em blocos de 1 MiB


def _write_bytes(path: Path, data: bytes) -> None:
    """Toda escrita de documento e da listagem da cópia julgada passa por aqui."""
    path.write_bytes(data)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(_SHA256_BLOCK):
            digest.update(block)
    return digest.hexdigest()


def _file_hashes(root: Path) -> dict[str, str]:
    """Caminho relativo POSIX → sha256 de todo arquivo sob `root`, sem o `CONTENTS.sha256`."""
    return {
        path.relative_to(root).as_posix(): _sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.relative_to(root).as_posix() != CONTENTS_NAME
    }


def _write_table(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    table = pa.Table.from_pylist([dict(row) for row in rows])
    pq.write_table(table, path)  # type: ignore[no-untyped-call]


def _write_manifest(path: Path, manifest: GoldManifest) -> None:
    path.write_text(
        json.dumps(manifest.as_mapping(), sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _read_manifest(path: Path) -> object:
    """O `MANIFEST.json` decodificado; ilegível (bytes, UTF-8 ou JSON) → corrupção."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GoldGenerationCorruptError(f"{path.name} is not valid JSON: {error}") from error


def _read_rows(path: Path) -> list[dict[str, object]]:
    """As linhas de uma tabela; arquivo Parquet ilegível (truncado, lixo) → corrupção."""
    try:
        table = pq.read_table(path, partitioning=None)  # type: ignore[no-untyped-call]
    except (OSError, pa.ArrowInvalid) as error:
        raise GoldGenerationCorruptError(
            f"{path.name} is not a readable Parquet file: {error}"
        ) from error
    rows: list[dict[str, object]] = table.to_pylist()
    return rows


class ParquetGoldStore:
    """Satisfaz o port `GoldStore`: geração inteira por partição, manifesto por último."""

    def __init__(self, data_root: Path) -> None:
        self._gold_root = Path(data_root) / "gold"

    def partition_root(self, partition: GoldPartition) -> Path:
        """Raiz da partição (valida os identificadores antes de montar o caminho)."""
        validate_path_identifier(partition.asset, field="asset")
        validate_path_identifier(partition.parent_sweep_id, field="parent_sweep_id")
        return (
            self._gold_root
            / f"asset={partition.asset}"
            / f"parent_sweep_id={partition.parent_sweep_id}"
        )

    def current_dir(self, partition: GoldPartition) -> Path:
        """`current/` da partição (leitura da geração viva pelos consumidores)."""
        return self.partition_root(partition) / _CURRENT

    def publish(
        self, *, partition: GoldPartition, tables: Sequence[GoldTable], manifest: GoldManifest
    ) -> None:
        """Staging → manifesto por último → troca de pasta (ADR `6_4_0005` item 5)."""
        check_generation(partition, tables, manifest)
        root = self.partition_root(partition)
        staging, current, previous = root / _STAGING, root / _CURRENT, root / _PREVIOUS
        if not current.exists() and (previous / MANIFEST_NAME).exists():
            # crash entre as duas trocas: a geração anterior completa volta a ser a viva
            os.replace(previous, current)
        for leftover in (staging, previous):
            if leftover.exists():
                shutil.rmtree(leftover)
        staging.mkdir(parents=True)
        for table in tables:
            _write_table(staging / f"{table.name}.parquet", table.rows)
        _write_manifest(staging / MANIFEST_NAME, manifest)
        if current.exists():
            os.replace(current, previous)
        try:
            os.replace(staging, current)
        except OSError:
            if previous.exists() and not current.exists():
                os.replace(previous, current)  # rollback: a geração anterior segue viva
            raise
        if previous.exists():
            try:
                shutil.rmtree(previous)
            except OSError as error:
                logger.warning(
                    "gold publish: could not delete %s (%s); the new generation is live "
                    "and the next publish removes it",
                    previous,
                    error,
                )

    def read_generation(self, *, partition: GoldPartition) -> GoldGeneration:
        """A geração viva da partição — satisfaz o port `GoldGenerationReader`.

        Raises:
            GoldManifestNotFoundError: `current/MANIFEST.json` ausente.
            GoldGenerationCorruptError: manifesto ilegível, tabela desconhecida ou com
                arquivo ausente, ou a montagem do `from_stored` recusa a geração.
        """
        current = self.current_dir(partition)
        manifest_path = current / MANIFEST_NAME
        if not manifest_path.is_file():
            raise GoldManifestNotFoundError(f"no gold generation for {partition}")
        manifest = _read_manifest(manifest_path)
        if not isinstance(manifest, dict):
            raise GoldGenerationCorruptError(f"{MANIFEST_NAME} is not a JSON object")
        listed = manifest.get("rows_by_table")
        if not isinstance(listed, dict):
            raise GoldGenerationCorruptError(f"{MANIFEST_NAME} has no rows_by_table table")
        rows_by_table: dict[str, list[dict[str, object]]] = {}
        for name, count in listed.items():
            if name not in GOLD_SCHEMAS:  # antes de montar caminho com o nome lido
                raise GoldGenerationCorruptError(f"unknown gold table {name!r} in the manifest")
            path = current / f"{name}.parquet"
            if not path.is_file():
                raise GoldGenerationCorruptError(f"table file {path.name} is missing")
            rows_by_table[name] = [] if count == 0 else _read_rows(path)
        return GoldGeneration.from_stored(manifest, rows_by_table, partition=partition)

    # -- geração julgada (Stage 8.1, port `JudgedGenerationStore`) ----------------------

    def _judged_root(self, partition: GoldPartition) -> Path:
        return self.partition_root(partition) / _JUDGED

    def _judged_dir(self, partition: GoldPartition, preregistration_ref: str) -> Path:
        validate_path_identifier(preregistration_ref, field="preregistration_ref")
        return self._judged_root(partition) / preregistration_ref

    def find(
        self, *, partition: GoldPartition, preregistration_ref: str
    ) -> JudgedGeneration | None:
        """A cópia selada conferida contra o seu `CONTENTS.sha256`, ou `None`.

        Raises:
            JudgedGenerationTamperedError: listagem ausente ou que não confere com os
                arquivos (alterado, faltando, a mais, `generation/` vazio).
        """
        directory = self._judged_dir(partition, preregistration_ref)
        if not directory.exists():
            return None
        contents = directory / CONTENTS_NAME
        if not contents.is_file():
            raise JudgedGenerationTamperedError(f"{preregistration_ref}: no {CONTENTS_NAME}")
        try:
            return judged_generation_from(
                partition=partition,
                preregistration_ref=preregistration_ref,
                listing=contents.read_bytes(),
                actual=_file_hashes(directory),
                read=lambda path: (directory / path).read_bytes(),
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
        """Copia `current/`, confere o manifesto, grava os documentos e sela por último.

        Raises:
            JudgedGenerationExistsError: `judged/<ref>/` já existe (nada é escrito).
            JudgedGenerationMismatchError: o manifesto copiado ≠ `expected_manifest`.
            GoldManifestNotFoundError: a partição não tem geração viva.
            OSError: falha de escrita (nada é selado; o próximo `preserve` limpa o staging).
        """
        target = self._judged_dir(partition, preregistration_ref)
        if target.exists():
            raise JudgedGenerationExistsError(f"{preregistration_ref} is already sealed")
        check_documents(documents)
        staging = self._judged_root(partition) / _STAGING
        if staging.exists():
            shutil.rmtree(staging)
        current = self.current_dir(partition)
        if not (current / MANIFEST_NAME).is_file():
            raise GoldManifestNotFoundError(f"no gold generation for {partition}")
        shutil.copytree(current, staging / GENERATION_DIR, copy_function=shutil.copyfile)
        copied = GoldManifest.from_mapping(
            json.loads((staging / GENERATION_MANIFEST).read_text(encoding="utf-8"))
        )
        if copied != expected_manifest:
            shutil.rmtree(staging)
            raise JudgedGenerationMismatchError(
                f"the copied manifest of {partition} is not the one the refresh returned"
            )
        for name in sorted(documents):
            _write_bytes(staging / name, document_bytes(documents[name]))
        _write_bytes(staging / CONTENTS_NAME, contents_listing(_file_hashes(staging)))
        os.replace(staging, target)
        sealed = self.find(partition=partition, preregistration_ref=preregistration_ref)
        if sealed is None:  # pragma: no cover — acabou de ser selada
            raise JudgedGenerationTamperedError(f"{preregistration_ref}: sealed copy vanished")
        return sealed

    def judged_refs(self, *, partition: GoldPartition) -> tuple[str, ...]:
        """As referências com cópia selada (diretórios de `judged/` sem prefixo `.`)."""
        root = self._judged_root(partition)
        if not root.exists():
            return ()
        return tuple(
            sorted(
                path.name
                for path in root.iterdir()
                if path.is_dir() and not path.name.startswith(".")
            )
        )

    def record_attempt(self, *, partition: GoldPartition, attempt: JudgedAttempt) -> None:
        """Acrescenta a linha ao `ATTEMPTS.jsonl` (arquivo inteiro por temporário + replace)."""
        root = self._judged_root(partition)
        root.mkdir(parents=True, exist_ok=True)
        path = root / ATTEMPTS_NAME
        existing = path.read_bytes() if path.exists() else b""
        temporary = root / f".{ATTEMPTS_NAME}.tmp"
        temporary.write_bytes(existing + attempts_jsonl([attempt]))
        os.replace(temporary, path)

    def attempts(self, *, partition: GoldPartition) -> tuple[JudgedAttempt, ...]:
        """As linhas do `ATTEMPTS.jsonl`, na ordem de gravação (sem arquivo → vazio)."""
        path = self._judged_root(partition) / ATTEMPTS_NAME
        return parse_attempts_jsonl(path.read_bytes()) if path.exists() else ()
