"""Port-out `CheckpointLocator` — o checkpoint de um run, sem carregá-lo (Stage 7.1).

A inferência resolve o artefato de cada run ANTES de qualquer unpickle (ADR
7.1.0004 item 1): o diretório `<artifacts_root>/tft/<run_id>` tem de conter
exatamente um `*.ckpt` (C3), e o sha256 dos seus bytes é lido por streaming — é
o que o manifesto grava na primeira escrita e o que a predição confere antes de
carregar (C10).

Listar diretório e ler bytes é I/O, que a application não faz (LAYOUT §3) — por
isso é um port, com o adapter (`FilesystemCheckpointLocator`, stdlib) fora dela.
O módulo do adapter não importa a pilha de DL: resolver não carrega nada.

`sha256_of_stream` mora aqui (ADR 7.1.0001 item 3) para o locator e a predição a
partir do checkpoint calcularem o hash pela MESMA função: ela recebe um stream já
aberto e não abre arquivo (o locator passa o arquivo; a predição, `io.BytesIO`
dos bytes lidos uma vez).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import IO, Protocol

from financial_forecasting.shared.application.exceptions import ApplicationError

_DEFAULT_CHUNK = 1 << 20


class CheckpointNotFoundError(ApplicationError):
    """O diretório do artefato não tem nenhum `*.ckpt` (C3); a mensagem nomeia o diretório."""


class AmbiguousCheckpointError(ApplicationError):
    """O diretório do artefato tem mais de um `*.ckpt` (C3) — nenhum é escolhido."""


@dataclass(frozen=True)
class CheckpointLocation:
    """O checkpoint resolvido: caminho absoluto e sha256 (hex) dos bytes."""

    path: str
    sha256: str


def sha256_of_stream(stream: IO[bytes], *, chunk_size: int = _DEFAULT_CHUNK) -> str:
    """sha256 (hex) de um stream binário lido em blocos até o fim — não abre arquivo."""
    if chunk_size < 1:
        raise ValueError(f"chunk_size must be >= 1, got {chunk_size}")
    digest = hashlib.sha256()
    while chunk := stream.read(chunk_size):
        digest.update(chunk)
    return digest.hexdigest()


class CheckpointLocator(Protocol):
    """Resolve o único checkpoint de um diretório de artefato, sem carregá-lo."""

    def locate(self, *, artifact_dir: str) -> CheckpointLocation:
        """O único `*.ckpt` de `artifact_dir` e seu sha256.

        Raises:
            CheckpointNotFoundError: nenhum `*.ckpt` (ou diretório inexistente).
            AmbiguousCheckpointError: mais de um `*.ckpt`.
        """
        ...
