"""Port-out `RuntimeEnvironmentProbe` do slice `inference` — o ambiente atual (Stage 7.1).

Port do CONSUMIDOR (ADR 0.0.0053), mesma forma do homônimo do `modeling`: o
`RunInference` confere a árvore limpa (`code_dirty`, C11) e compara o ambiente
atual com o gravado pelo cohort para escolher o modo de reprodução (I6; ADR
7.1.0003 item 3). As chaves (`CODE_KEYS`, `DIRTY_KEY`, `THREADS_KEY`) NÃO são
redeclaradas aqui: são as do port do `modeling`, consumidas como dado.

Real: `GitRuntimeEnvironmentProbe` (adapter do `modeling`), por duck-typing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class RuntimeEnvironmentProbe(Protocol):
    """Foto do ambiente atual: versões, device, threads, CPU e identidade do código."""

    def snapshot(self) -> Mapping[str, str]:
        """Todas as chaves do probe do cohort; `code_dirty` é `"true"` ou `"false"`."""
        ...
