"""Fake in-memory do port `CheckpointLocator` (Stage 7.1).

Os diretórios de artefato são um `dict` diretório → lista de `(nome, bytes)`; o
sha256 sai da MESMA `sha256_of_stream` do port (sobre `io.BytesIO`), então fake e
`FilesystemCheckpointLocator` concordam no hash por construção. Registra os
diretórios consultados em `calls` (os use cases provam "nenhum `locate` antes das
guardas" contando chamadas). Paridade pelo contrato `[fake, real]`.

Diretórios são normalizados para caminho absoluto (`os.path.abspath`, que também
normaliza `..`, como o `resolve()` do adapter real faz com um relativo): o caminho
devolvido é sempre absoluto, e um diretório relativo e o seu absoluto são o mesmo.
"""

from __future__ import annotations

import io
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from financial_forecasting.features.modeling.application.ports.out.checkpoint_locator import (
    AmbiguousCheckpointError,
    CheckpointLocation,
    CheckpointNotFoundError,
    sha256_of_stream,
)

_SUFFIX = ".ckpt"


class InMemoryCheckpointLocator:
    """Diretórios em memória; `locate` exige exatamente um `*.ckpt` (C3)."""

    def __init__(
        self, directories: Mapping[str, Sequence[tuple[str, bytes]]] | None = None
    ) -> None:
        self._directories: dict[str, list[tuple[str, bytes]]] = {
            _absolute(directory): list(files) for directory, files in (directories or {}).items()
        }
        self.calls: list[str] = []

    def add_file(self, artifact_dir: str, name: str, data: bytes) -> str:
        """Grava um arquivo no diretório e devolve o caminho que `locate` devolveria."""
        directory = _absolute(artifact_dir)
        self._directories.setdefault(directory, []).append((name, data))
        return self._path(directory, name)

    def locate(self, *, artifact_dir: str) -> CheckpointLocation:
        self.calls.append(artifact_dir)
        directory = _absolute(artifact_dir)
        checkpoints = sorted(
            (name, data)
            for name, data in self._directories.get(directory, [])
            if name.endswith(_SUFFIX)
        )
        if not checkpoints:
            raise CheckpointNotFoundError(f"no *{_SUFFIX} checkpoint in {artifact_dir} (C3)")
        if len(checkpoints) > 1:
            names = [name for name, _ in checkpoints]
            raise AmbiguousCheckpointError(
                f"{len(checkpoints)} checkpoints in {artifact_dir}: {names} — expected exactly one"
                " (C3)"
            )
        name, data = checkpoints[0]
        return CheckpointLocation(
            path=self._path(directory, name), sha256=sha256_of_stream(io.BytesIO(data))
        )

    @staticmethod
    def _path(artifact_dir: str, name: str) -> str:
        return f"{artifact_dir.rstrip('/')}/{name}"


def _absolute(directory: str) -> str:
    return Path(os.path.abspath(directory)).as_posix()  # abspath também normaliza `..`
