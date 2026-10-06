"""Adapter `FilesystemCheckpointLocator` — satisfaz o port `CheckpointLocator` (Stage 7.1).

Só stdlib (`pathlib` + `sha256_of_stream` do port, sobre `hashlib`): resolver o
checkpoint de um run não importa a pilha de DL nem carrega nada (ADR 7.1.0004
item 1). Exige exatamente um `*.ckpt` no diretório do artefato (C3) e devolve o
caminho absoluto com o sha256 dos bytes, lido em blocos.
"""

from __future__ import annotations

from pathlib import Path

from financial_forecasting.features.modeling.application.ports.out.checkpoint_locator import (
    AmbiguousCheckpointError,
    CheckpointLocation,
    CheckpointNotFoundError,
    sha256_of_stream,
)

_CHECKPOINT_GLOB = "*.ckpt"


class FilesystemCheckpointLocator:
    """O único `*.ckpt` de um diretório de artefato, com o sha256 dos seus bytes."""

    def locate(self, *, artifact_dir: str) -> CheckpointLocation:
        directory = Path(artifact_dir)
        candidates = (
            sorted(p for p in directory.glob(_CHECKPOINT_GLOB) if p.is_file())
            if directory.is_dir()
            else []
        )
        if not candidates:
            raise CheckpointNotFoundError(f"no {_CHECKPOINT_GLOB} checkpoint in {directory} (C3)")
        if len(candidates) > 1:
            names = [p.name for p in candidates]
            raise AmbiguousCheckpointError(
                f"{len(candidates)} checkpoints in {directory}: {names} — expected exactly one (C3)"
            )
        path = candidates[0].resolve()
        with path.open("rb") as stream:
            digest = sha256_of_stream(stream)
        return CheckpointLocation(path=str(path), sha256=digest)
