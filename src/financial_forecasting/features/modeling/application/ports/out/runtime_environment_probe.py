"""Port-out `RuntimeEnvironmentProbe` — ambiente e identidade do código (Stage 5.5).

A retomada do cohort só é equivalente a uma execução contínua sob o mesmo
ambiente (PyTorch *Reproducibility*: resultados podem diferir entre versões e
entre CPU e GPU). O use case grava o `snapshot()` na primeira execução e aborta
a retomada se qualquer campo mudar (I5, ADR 5.5.0003).

Ler versões de bibliotecas, CPU e git importa o que o domínio e a aplicação não
podem importar (LAYOUT §3) — por isso é um port, com o adapter fora deles.

Chaves obrigatórias (`REQUIRED_KEYS`): versões das bibliotecas que tocam os
números do cohort, device, threads, CPU e a identidade do código — hash de
conteúdo git de `src/`, `uv.lock` e do arquivo do cohort (commits só de docs não
a mudam) — e `code_dirty` (`"true"`/`"false"`: mudança rastreada não commitada
nesses caminhos; arquivos não rastreados não contam).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

LIBRARY_KEYS = (
    "python",
    "torch",
    "lightning",
    "pytorch-forecasting",
    "lightgbm",
    "statsforecast",
    "optuna",
    "numpy",
    "pandas",
    "pyarrow",
    "exchange-calendars",
)
CODE_KEYS = ("code.src", "code.uv_lock", "code.cohort_file")
REQUIRED_KEYS = (*LIBRARY_KEYS, "device", "torch_threads", "cpu", *CODE_KEYS, "code_dirty")
DIRTY_KEY = "code_dirty"


class RuntimeEnvironmentProbe(Protocol):
    """Foto do ambiente da corrida: `REQUIRED_KEYS` → valores em texto."""

    def snapshot(self) -> Mapping[str, str]:
        """Todas as `REQUIRED_KEYS`; `code_dirty` é `"true"` ou `"false"`."""
        ...
