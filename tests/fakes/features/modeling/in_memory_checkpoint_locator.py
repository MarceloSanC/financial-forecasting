"""Fake in-memory do port `CheckpointLocator` (Stage 7.1).

Os diretórios de artefato são um `dict` diretório → lista de `(nome, bytes)`; o
sha256 sai da MESMA `sha256_of_stream` do port (sobre `io.BytesIO`), então fake e
`FilesystemCheckpointLocator` concordam no hash por construção. Registra os
diretórios consultados em `calls` (os use cases provam "nenhum `locate` antes das
guardas" contando chamadas). Paridade pelo contrato `[fake, real]`.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence

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
            directory: list(files) for directory, files in (directories or {}).items()
        }
        self.calls: list[str] = []

    def add_file(self, artifact_dir: str, name: str, data: bytes) -> str:
        """Grava um arquivo no diretório e devolve o caminho que `locate` devolveria."""
        self._directories.setdefault(artifact_dir, []).append((name, data))
        return self._path(artifact_dir, name)

    def locate(self, *, artifact_dir: str) -> CheckpointLocation:
        self.calls.append(artifact_dir)
        checkpoints = sorted(
            (name, data)
            for name, data in self._directories.get(artifact_dir, [])
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
            path=self._path(artifact_dir, name), sha256=sha256_of_stream(io.BytesIO(data))
        )

    @staticmethod
    def _path(artifact_dir: str, name: str) -> str:
        return f"{artifact_dir.rstrip('/')}/{name}"
