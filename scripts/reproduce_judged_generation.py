"""Driver da reprodução da geração julgada (Stage 8.2; concept §4; ADR 8.2.0001 itens 3 e 7).

Contrato operacional, fora de `src/`: versionado no HEAD e executado no container da imagem
da corrida (`b69a7620…`) com a árvore de `060537fc` montada como `/app` e este arquivo
montado à parte (`/driver/`, fora dos caminhos do probe — a árvore segue limpa):

    python /driver/reproduce_judged_generation.py --data-root <descartável> \\
        --cohort config/cohorts/aapl_confirmatory.toml --preregistration <nome> \\
        --revision <r> --preregistration-ref <ref> [--check]

Só faz wiring pelo `ApplicationDependencies` daquele commit e só importa nomes presentes
em `060537fc` (o `--check` em `060537fc` é a prova: `ImportError` ali = parada):

1. recusa, nos dois modos e ANTES de montar o wiring, um `data_root` cujo caminho resolvido
   tem as partes consecutivas `data`/`cohorts` (a partição viva nunca é destino, I1/I2) ou
   que já tem `gold/` ou `reproduction/`;
2. `wire_dependencies(Settings(data_root=...))`; `TomlPreregistrationSource` de
   `config/preregistration` (cwd = `/app`, o `repo_root`);
3. resolve a revisão (`resolve_judged_revision`, cadeia, hash e âncora);
4. tira a foto do ambiente pelo MESMO produtor da linha `started` da 8.1:
   `deps.run_confirmatory_evaluation_for(cohort, "cpu")._environment.snapshot()`. O acesso
   ao atributo privado `_environment` é **declarado e justificado** (ADR 8.2.0001 item 7):
   em `060537fc` o `GitEvaluationEnvironment` só é montado dentro dessa closure do
   composition root (com `_torch_cpu_capability` privada e `CODE_KEYS`/`DIRTY_KEY` do
   modeling) — é o único caminho que dá, sem código novo em `060537fc`, a mesma foto que a
   8.1 gravou. O use case montado não é chamado;
5. `--check`: escreve no stdout exatamente os bytes `document_bytes(foto)` (os mesmos do
   `environment.json`; nenhuma outra linha) e sai 0 — nada é gravado nem recalculado;
6. senão cria `reproduction/` e grava `environment.json` = `document_bytes(foto)` **antes**
   do refresh (como na 8.1) → `refresh_gold(refresh_command_from(plan, ref))` → status ≠
   `COMPLETED` → stderr e exit 1, sem scorecard → `build_confirmatory_scorecard(...)` →
   `scorecard.json` = `document_bytes(scorecard.as_mapping())` (o serializador da cópia
   julgada). Stdout: `reproduction <ref>: refresh <STATUS> tables <n>` e
   `reproduction <ref>: scorecard sha256 <64 hex>`.

Exceções sobem (traceback, exit ≠ 0): o driver não traduz erro. `reproduce(...)` recebe as
dependências prontas (testável com fakes no HEAD — smoke test em
`tests/unit/tooling/test_reproduce_judged_generation.py`, que prova a lógica do driver,
não o wiring de `060537fc`).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, BinaryIO, Final, TextIO

from financial_forecasting.composition_root import wire_dependencies
from financial_forecasting.features.evaluation.adapters.out.toml.toml_preregistration_source import (  # noqa: E501
    TomlPreregistrationSource,
)
from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    BuildConfirmatoryScorecardCommand,
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    document_bytes,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.use_cases.judged_revision import (
    resolve_judged_revision,
)
from financial_forecasting.shared.infrastructure.config.settings import Settings

REPRODUCTION_DIR: Final = "reproduction"
ENVIRONMENT_FILE: Final = "environment.json"
SCORECARD_FILE: Final = "scorecard.json"
DEVICE: Final = "cpu"
_FORBIDDEN_PARTS: Final = ("data", "cohorts")
_EXISTING: Final = ("gold", REPRODUCTION_DIR)
EXIT_NOT_COMPLETED: Final = 1


class RefusedDataRootError(ValueError):
    """O `data_root` é a partição viva (`data/cohorts/...`) ou já tem `gold/`/`reproduction/`."""


def check_data_root(data_root: Path) -> Path:
    """O `data_root` resolvido, se é um destino descartável válido.

    Raises:
        RefusedDataRootError: caminho resolvido com `data`/`cohorts` consecutivos, ou
            `gold/`/`reproduction/` já existente.
    """
    resolved = Path(data_root).resolve()
    parts = resolved.parts
    if any(parts[i : i + 2] == _FORBIDDEN_PARTS for i in range(len(parts) - 1)):
        raise RefusedDataRootError(
            f"data root {resolved} is under data/cohorts: the live partition is never a target"
        )
    existing = [name for name in _EXISTING if (resolved / name).exists()]
    if existing:
        raise RefusedDataRootError(f"data root {resolved} already has {existing}")
    return resolved


def reproduce(  # noqa: PLR0913 — as dependências e os argumentos do contrato (keyword-only)
    *,
    deps: Any,  # noqa: ANN401 — o `ApplicationDependencies` de `060537fc` (duck typing)
    source: Any,  # noqa: ANN401 — o `PreregistrationSource` de `060537fc`
    data_root: Path,
    cohort: Path,
    name: str,
    revision: int,
    preregistration_ref: str,
    snapshot: Callable[[], Mapping[str, str]],
    check: bool,
    out: BinaryIO,
    err: TextIO,
) -> int:
    """Refresh + scorecard da revisão no `data_root` descartável (ou só a foto, `--check`)."""
    root = check_data_root(data_root)
    del cohort  # o `snapshot` já vem do `run_confirmatory_evaluation_for(cohort, "cpu")`
    resolved = resolve_judged_revision(
        source=source,
        hasher=deps.hasher,
        name=name,
        revision=revision,
        preregistration_ref=preregistration_ref,
    )
    environment = document_bytes(dict(snapshot()))
    if check:
        out.write(environment)
        return 0
    target = root / REPRODUCTION_DIR
    target.mkdir(parents=True)
    (target / ENVIRONMENT_FILE).write_bytes(environment)
    result = deps.refresh_gold(refresh_command_from(resolved.plan, preregistration_ref))
    status = result.status
    out.write(
        f"reproduction {preregistration_ref}: refresh {status.value} "
        f"tables {len(result.rows_by_table)}\n".encode()
    )
    if status is not RefreshStatus.COMPLETED:
        err.write(f"reproduction {preregistration_ref}: refresh {status.value}, no scorecard\n")
        return EXIT_NOT_COMPLETED
    scorecard = deps.build_confirmatory_scorecard(
        BuildConfirmatoryScorecardCommand(
            name=name, revision=revision, preregistration_ref=preregistration_ref
        )
    )
    data = document_bytes(scorecard.as_mapping())
    (target / SCORECARD_FILE).write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    out.write(f"reproduction {preregistration_ref}: scorecard sha256 {digest}\n".encode())
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--preregistration", required=True)
    parser.add_argument("--revision", type=int, required=True)
    parser.add_argument("--preregistration-ref", required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    wire: Callable[[Settings], Any] = wire_dependencies,
) -> int:
    """Recusas, wiring de `060537fc`, foto e (sem `--check`) refresh + scorecard."""
    args = _parser().parse_args(argv)
    check_data_root(args.data_root)  # antes de montar o wiring
    deps = wire(Settings(data_root=args.data_root))
    source = TomlPreregistrationSource(root=Path("config/preregistration"))
    # acesso privado declarado (ADR 8.2.0001 item 7): o produtor da linha `started` da 8.1
    snapshot = deps.run_confirmatory_evaluation_for(args.cohort, DEVICE)._environment.snapshot
    return reproduce(
        deps=deps,
        source=source,
        data_root=args.data_root,
        cohort=args.cohort,
        name=args.preregistration,
        revision=args.revision,
        preregistration_ref=args.preregistration_ref,
        snapshot=snapshot,
        check=args.check,
        out=sys.stdout.buffer,
        err=sys.stderr,
    )


if __name__ == "__main__":
    sys.exit(main())
