"""Port-out `EvaluationEnvironment` — código e ambiente da corrida confirmatória (Stage 8.1).

Port do **consumidor** (concept 8.1 §4, D6, I13; ADR `8_1_0003` item 6; technical 8.1 §1
"Chaves do `EvaluationEnvironment`"): `snapshot()` devolve, só em tipos embutidos, a foto
gravada no registro de execução e comparada entre tentativas. Os nomes de chave são do
próprio `evaluation` — o real recebe do composition root o probe da 5.5 e as constantes
dele, sem que este slice importe o `modeling` (Checkpoint A, CA-5):

- `commit` (`git rev-parse HEAD`), `code_dirty` e `preregistration_dirty`
  (`"true"`/`"false"`; arquivo não rastreado em `config/preregistration` conta);
- **código** — chaves com o prefixo `code.` (`code.src`, `code.uv_lock`,
  `code.cohort_file`, vindas do probe);
- **ambiente** (R-BIT) — chaves com o prefixo `env.`: `env.image_id` (obrigatório;
  sem ele → `MissingImageIdError`), `env.platform`, `env.cpu_count`,
  `env.cpu_capability`, `env.lib.<dist>` das bibliotecas do caminho do gold
  (`GOLD_LIBRARIES`) e `env.probe.<chave>` para as demais chaves do probe.

A comparação do I13 é por prefixo: código = `code.*`, ambiente = `env.*`.

O real é o `GitEvaluationEnvironment` (`adapters/out/runtime/`); o fake é o
`InMemoryEvaluationEnvironment` (`tests/fakes/features/evaluation/`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Protocol

from financial_forecasting.shared.application.exceptions import ApplicationError

COMMIT_KEY: Final = "commit"
CODE_DIRTY_KEY: Final = "code_dirty"
PREREGISTRATION_DIRTY_KEY: Final = "preregistration_dirty"
CODE_PREFIX: Final = "code."
ENV_PREFIX: Final = "env."
IMAGE_ID_KEY: Final = f"{ENV_PREFIX}image_id"
PLATFORM_KEY: Final = f"{ENV_PREFIX}platform"
CPU_COUNT_KEY: Final = f"{ENV_PREFIX}cpu_count"
CPU_CAPABILITY_KEY: Final = f"{ENV_PREFIX}cpu_capability"
LIBRARY_PREFIX: Final = f"{ENV_PREFIX}lib."
PROBE_PREFIX: Final = f"{ENV_PREFIX}probe."
GOLD_LIBRARIES: Final = (
    "arch",
    "statsmodels",
    "scipy",
    "scikit-learn",
    "scoringrules",
    "duckdb",
    "mapie",
)
"""As bibliotecas do caminho do gold que o probe da 5.5 não tem (lista fechada, D6)."""
TRUE: Final = "true"
FALSE: Final = "false"
BASE_KEYS: Final = (
    COMMIT_KEY,
    CODE_DIRTY_KEY,
    PREREGISTRATION_DIRTY_KEY,
    IMAGE_ID_KEY,
    PLATFORM_KEY,
    CPU_COUNT_KEY,
    CPU_CAPABILITY_KEY,
)


def library_key(distribution: str) -> str:
    """A chave da versão de uma biblioteca (`env.lib.<dist>`)."""
    return f"{LIBRARY_PREFIX}{distribution}"


def probe_key(key: str) -> str:
    """A chave de uma chave de ambiente do probe da 5.5 (`env.probe.<chave>`)."""
    return f"{PROBE_PREFIX}{key}"


REQUIRED_KEYS: Final = (*BASE_KEYS, *(library_key(name) for name in GOLD_LIBRARIES))
"""As chaves que toda foto tem; as `code.*` e `env.probe.*` vêm do probe."""


class MissingImageIdError(ApplicationError):
    """Sem o id da imagem Docker a foto não identifica o ambiente (ADR 8.1.0003 item 6)."""


class EvaluationEnvironment(Protocol):
    """A foto do código e do ambiente da corrida."""

    def snapshot(self) -> Mapping[str, str]:
        """Chave → valor em texto (ver docstring do módulo).

        Raises:
            MissingImageIdError: o id da imagem não foi informado.
        """
        ...
