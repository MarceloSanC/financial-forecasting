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
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from financial_forecasting.features.evaluation.application.dtos.gold_schema import GOLD_SCHEMAS
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldGenerationCorruptError,
    GoldManifest,
    GoldManifestNotFoundError,
    GoldPartition,
    GoldTable,
    check_generation,
)
from financial_forecasting.shared.domain.services.path_identifier import (
    validate_path_identifier,
)

logger = logging.getLogger(__name__)

MANIFEST_NAME = "MANIFEST.json"
_CURRENT = "current"
_STAGING = ".staging"
_PREVIOUS = ".previous"


def _write_table(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    table = pa.Table.from_pylist([dict(row) for row in rows])
    pq.write_table(table, path)  # type: ignore[no-untyped-call]


def _write_manifest(path: Path, manifest: GoldManifest) -> None:
    path.write_text(
        json.dumps(manifest.as_mapping(), sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _read_manifest(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise GoldGenerationCorruptError(f"{path.name} is not valid JSON: {error}") from error


def _read_rows(path: Path) -> list[dict[str, object]]:
    table = pq.read_table(path, partitioning=None)  # type: ignore[no-untyped-call]
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
