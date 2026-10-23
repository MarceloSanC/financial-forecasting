"""Delta da branch contra a base, sem gravar o índice do git (issue #199).

`check_stage_issue.py` e `check_concept_directness.py` validam só os docs que a
branch mudou. Os dois usavam `git diff --name-only <merge-base> -- <pathspec>`
com `timeout=15`. Esse `git diff` compara com a working tree e, quando o
`stat` do índice não bate com o dos arquivos, regrava o índice: ele toma
`index.lock` e o segura durante o refresh inteiro. No container de check, a
worktree vem de um bind mount do Windows, e o índice gravado pelo git do host
não bate com o `stat` visto do Linux. O refresh passa de 15 s, o
`subprocess.run` mata o git com SIGKILL, e o `index.lock` fica órfão. O
próximo commit no host falha com "Another git process seems to be running".
`GIT_OPTIONAL_LOCKS=0` não resolve, porque o `git diff` não respeita a
variável. Só o `git status` respeita.

Aqui o delta sai de dois comandos que não gravam o índice:

- commits da branch: `git diff <merge-base> HEAD`, que compara duas árvores e
  não olha a working tree;
- working tree (staged, unstaged e untracked): `git status --porcelain` com
  `GIT_OPTIONAL_LOCKS=0`, que faz o refresh só em memória e só no pathspec.

Matar qualquer um dos dois no timeout não deixa lock. Stdlib-only. `scripts/`
não é pacote: os gates carregam este módulo por
`importlib.util.spec_from_file_location`, como fazem com `arch_baseline_lib.py`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_TIMEOUT_S = 15
# `git status --porcelain` v1: "XY <caminho>"; o caminho começa na coluna 3.
_STATUS_PATH_COLUMN = 3


def _git(args: list[str]) -> str | None:
    """Stdout de `git <args>`, sem locks opcionais; `None` em qualquer falha."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            check=False,
            env=env,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def changed_paths(pathspec: str, base_ref: str) -> list[Path] | None:
    """Caminhos sob `pathspec` que a branch mudou contra o merge-base com `base_ref`.

    Junta os commits da branch e a working tree (staged, unstaged e untracked).
    Os caminhos saem relativos à raiz do repositório. Renome aparece pelos dois
    nomes, e o chamador filtra com `is_file()`. Devolve `None` quando o delta não
    pode ser determinado: sem git, sem `base_ref`, merge-base ou timeout.
    """
    merge_base = _git(["merge-base", "HEAD", base_ref])
    if merge_base is None or not merge_base.strip():
        return None
    committed = _git(
        ["diff", "--name-only", "--no-renames", "-z", merge_base.strip(), "HEAD", "--", pathspec]
    )
    if committed is None:
        return None
    working = _git(
        ["status", "--porcelain", "-z", "--no-renames", "--untracked-files=all", "--", pathspec]
    )
    if working is None:
        return None
    names = {name for name in committed.split("\0") if name}
    names |= {entry[_STATUS_PATH_COLUMN:] for entry in working.split("\0") if entry}
    return sorted(Path(name) for name in names)
