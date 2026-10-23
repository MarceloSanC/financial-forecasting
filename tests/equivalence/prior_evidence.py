"""Registro de hashes da evidência anterior: checagem e gerador (Stage 8.2, Task 08).

ADR 8.2.0003 itens 1, 4 e 6; concept 8.2 D5, I6 (EQ-HASH). O registro
`docs/reports/prior_evidence_registry.toml` é commitado **antes** de qualquer leitura de
valor e tem a forma (technical 8.2 §1):

    registry_version = 1
    root = "data/analytics"
    [[file]]
    path = "gold/gold_oos_consolidated.parquet"   # relativo a data/analytics/, POSIX
    sha256 = "<64 hex>"
    rows = 410208
    columns = [{ name = "schema_version", type = "int64" }, ...]   # ordem do footer
    [[definition_source]]                          # opcional (E1)
    repo = "..."
    commit = "..."
    path = "..."
    blob = "..."

- `load_registry(path)` lê e valida a forma (`PriorEvidenceRegistryError`);
- `verify_registered_files(*, oracle_root, registry)` confere cada arquivo registrado —
  sha256 por streaming, linhas e tipo físico de cada coluna pelo **footer**
  (`pyarrow.parquet.read_metadata` / `read_schema`, sem ler valor) — e devolve caminho
  relativo → caminho absoluto; qualquer divergência → `PriorEvidenceHashError` com a lista
  (o teste opt-in **falha**, nunca pula nem regenera);
- `registered_path(verified, path)` é a única porta de leitura do andaime: caminho fora do
  registro é recusado (D5: o conjunto lido é o do registro e nenhum outro);
- `build_registry(*, oracle_root, paths, definition_sources=())` monta o TOML só com footer
  e sha256; `python -m tests.equivalence.prior_evidence build <oracle_root> <path>...`
  **imprime** o TOML (o redirecionamento para o arquivo é do runbook da E1; CB-7).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

import pyarrow.parquet as pq

REGISTRY_PATH: Final = (
    Path(__file__).resolve().parents[2] / "docs" / "reports" / "prior_evidence_registry.toml"
)
REGISTRY_VERSION: Final = 1
ROOT_LABEL: Final = "data/analytics"
_SHA256: Final = re.compile(r"[0-9a-f]{64}")
_BLOCK: Final = 1 << 20
_FILE_KEYS: Final = frozenset({"path", "sha256", "rows", "columns"})
_COLUMN_KEYS: Final = frozenset({"name", "type"})
_SOURCE_KEYS: Final = ("repo", "commit", "path", "blob")
_TOP_KEYS: Final = frozenset({"registry_version", "root", "file", "definition_source"})


class PriorEvidenceRegistryError(ValueError):
    """O registro não tem a forma esperada."""


class PriorEvidenceHashError(AssertionError):
    """Arquivo da evidência anterior diferente do registro, ausente ou fora dele."""

    def __init__(self, divergences: Sequence[str]) -> None:
        self.divergences = tuple(divergences)
        super().__init__("prior evidence differs from the registry: " + "; ".join(divergences))


@dataclass(frozen=True)
class RegisteredColumn:
    """Uma coluna do footer: nome e tipo físico (`str(pyarrow.DataType)`)."""

    name: str
    type: str


@dataclass(frozen=True)
class RegisteredFile:
    """Um arquivo registrado: caminho relativo, sha256, linhas e colunas do footer."""

    path: str
    sha256: str
    rows: int
    columns: tuple[RegisteredColumn, ...]


@dataclass(frozen=True)
class DefinitionSource:
    """Uma fonte de definição de baseline do lado anterior (E1, D12 a)."""

    repo: str
    commit: str
    path: str
    blob: str


@dataclass(frozen=True)
class PriorEvidenceRegistry:
    """O registro lido: os arquivos (ordem do arquivo) e as fontes de definição."""

    files: tuple[RegisteredFile, ...]
    definition_sources: tuple[DefinitionSource, ...] = ()


def check_relative(path: object) -> str:
    """Caminho relativo POSIX sem `..`, raiz, `\\` nem parte vazia.

    Raises:
        PriorEvidenceRegistryError: fora dessa forma.
    """
    if not isinstance(path, str) or not path or "\\" in path:
        raise PriorEvidenceRegistryError(f"path must be a relative POSIX str, got {path!r}")
    pure = PurePosixPath(path)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in path.split("/")):
        raise PriorEvidenceRegistryError(f"path must be relative without '..', got {path!r}")
    return path


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PriorEvidenceRegistryError(f"{field} must be a non-empty str, got {value!r}")
    return value


def _file(entry: object, index: int) -> RegisteredFile:
    if not isinstance(entry, dict) or set(entry) != _FILE_KEYS:
        raise PriorEvidenceRegistryError(f"file {index} must have exactly {sorted(_FILE_KEYS)}")
    sha256 = entry["sha256"]
    if not isinstance(sha256, str) or _SHA256.fullmatch(sha256) is None:
        raise PriorEvidenceRegistryError(f"file {index} sha256 is not 64 hex: {sha256!r}")
    rows = entry["rows"]
    if not isinstance(rows, int) or isinstance(rows, bool) or rows < 0:
        raise PriorEvidenceRegistryError(f"file {index} rows must be an int >= 0, got {rows!r}")
    columns = entry["columns"]
    if not isinstance(columns, list):
        raise PriorEvidenceRegistryError(f"file {index} columns must be a list")
    parsed: list[RegisteredColumn] = []
    for column in columns:
        if not isinstance(column, dict) or set(column) != _COLUMN_KEYS:
            raise PriorEvidenceRegistryError(f"file {index} column must be {{name, type}}")
        parsed.append(
            RegisteredColumn(
                _text(column["name"], field="column name"),
                _text(column["type"], field="column type"),
            )
        )
    return RegisteredFile(check_relative(entry["path"]), sha256, rows, tuple(parsed))


def _source(entry: object) -> DefinitionSource:
    if not isinstance(entry, dict) or set(entry) != set(_SOURCE_KEYS):
        raise PriorEvidenceRegistryError(f"definition_source must have exactly {_SOURCE_KEYS}")
    return DefinitionSource(*(_text(entry[key], field=key) for key in _SOURCE_KEYS))


def parse_registry(text: str) -> PriorEvidenceRegistry:
    """O registro a partir do texto TOML.

    Raises:
        PriorEvidenceRegistryError: TOML inválido, versão/raiz diferentes, chave a mais,
            campo inválido ou caminho repetido.
    """
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise PriorEvidenceRegistryError(f"registry is not TOML: {error}") from error
    unknown = sorted(set(document) - _TOP_KEYS)
    if unknown:
        raise PriorEvidenceRegistryError(f"unknown registry keys {unknown}")
    if document.get("registry_version") != REGISTRY_VERSION:
        raise PriorEvidenceRegistryError(
            f"registry_version must be {REGISTRY_VERSION}, got {document.get('registry_version')!r}"
        )
    if document.get("root") != ROOT_LABEL:
        raise PriorEvidenceRegistryError(
            f"root must be {ROOT_LABEL!r}, got {document.get('root')!r}"
        )
    entries = document.get("file", [])
    if not isinstance(entries, list) or not entries:
        raise PriorEvidenceRegistryError("registry must list at least one [[file]]")
    files = tuple(_file(entry, index) for index, entry in enumerate(entries))
    paths = [item.path for item in files]
    if len(set(paths)) != len(paths):
        raise PriorEvidenceRegistryError(f"registry repeats a path: {paths}")
    sources = document.get("definition_source", [])
    if not isinstance(sources, list):
        raise PriorEvidenceRegistryError("definition_source must be an array of tables")
    return PriorEvidenceRegistry(files, tuple(_source(entry) for entry in sources))


def load_registry(path: Path) -> PriorEvidenceRegistry:
    """O registro do arquivo `path` (UTF-8)."""
    return parse_registry(Path(path).read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    """sha256 hex do conteúdo, por streaming."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(_BLOCK):
            digest.update(block)
    return digest.hexdigest()


def footer_shape(path: Path) -> tuple[int, tuple[RegisteredColumn, ...]]:
    """Linhas e colunas (nome, tipo físico) só pelo footer Parquet — nenhum valor é lido."""
    rows = pq.read_metadata(path).num_rows  # type: ignore[no-untyped-call]
    schema = pq.read_schema(path)  # type: ignore[no-untyped-call]
    return int(rows), tuple(RegisteredColumn(field.name, str(field.type)) for field in schema)


def verify_registered_files(
    *, oracle_root: Path, registry: PriorEvidenceRegistry
) -> Mapping[str, Path]:
    """Caminho relativo → absoluto de cada arquivo registrado, conferido contra o registro.

    Raises:
        PriorEvidenceHashError: arquivo ausente, sha256, linhas ou colunas (nome, tipo,
            ordem) diferentes do registro — todas as divergências numa só mensagem.
    """
    root = Path(oracle_root)
    divergences: list[str] = []
    verified: dict[str, Path] = {}
    for item in registry.files:
        path = root / item.path
        if not path.is_file():
            divergences.append(f"{item.path}: missing")
            continue
        digest = sha256_file(path)
        if digest != item.sha256:
            divergences.append(f"{item.path}: sha256 {digest} != registry {item.sha256}")
            continue
        rows, columns = footer_shape(path)
        if rows != item.rows:
            divergences.append(f"{item.path}: rows {rows} != registry {item.rows}")
        if columns != item.columns:
            divergences.append(f"{item.path}: footer columns differ from the registry")
        verified[item.path] = path
    if divergences:
        raise PriorEvidenceHashError(divergences)
    return verified


def registered_path(verified: Mapping[str, Path], path: str) -> Path:
    """O caminho absoluto de um arquivo conferido; fora do registro → recusa.

    Raises:
        PriorEvidenceHashError: `path` não é um arquivo registrado e conferido.
    """
    if path not in verified:
        raise PriorEvidenceHashError([f"{path}: not in the registry, never read"])
    return verified[path]


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def build_registry(
    *,
    oracle_root: Path,
    paths: Sequence[str],
    definition_sources: Sequence[DefinitionSource] = (),
) -> str:
    """O TOML do registro dos `paths` (sha256 + footer), na ordem dada.

    Raises:
        PriorEvidenceRegistryError: caminho fora da forma ou repetido.
        FileNotFoundError: arquivo ausente.
    """
    checked = [check_relative(path) for path in paths]
    if len(set(checked)) != len(checked) or not checked:
        raise PriorEvidenceRegistryError(f"paths must be non-empty and distinct: {checked}")
    lines = [f"registry_version = {REGISTRY_VERSION}", f"root = {_quote(ROOT_LABEL)}"]
    for relative in checked:
        path = Path(oracle_root) / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        rows, columns = footer_shape(path)
        cells = ", ".join(
            f"{{ name = {_quote(column.name)}, type = {_quote(column.type)} }}"
            for column in columns
        )
        lines += [
            "",
            "[[file]]",
            f"path = {_quote(relative)}",
            f"sha256 = {_quote(sha256_file(path))}",
            f"rows = {rows}",
            f"columns = [{cells}]",
        ]
    for source in definition_sources:
        lines += ["", "[[definition_source]]"]
        lines += [f"{key} = {_quote(getattr(source, key))}" for key in _SOURCE_KEYS]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """`build <oracle_root> <path>... [--definition-source REPO COMMIT PATH BLOB]`."""
    parser = argparse.ArgumentParser(prog="python -m tests.equivalence.prior_evidence")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="imprime o TOML do registro")
    build.add_argument("oracle_root", type=Path)
    build.add_argument("paths", nargs="+")
    build.add_argument("--definition-source", nargs=4, action="append", default=[], metavar="FIELD")
    args = parser.parse_args(argv)
    sources = [DefinitionSource(*fields) for fields in args.definition_source]
    sys.stdout.write(
        build_registry(oracle_root=args.oracle_root, paths=args.paths, definition_sources=sources)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
