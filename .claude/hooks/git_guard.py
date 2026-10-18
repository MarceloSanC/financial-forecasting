"""Hook PreToolUse (Bash/PowerShell): o checkout principal fica livre em `develop`.

Recusa, quando o diretório efetivo do comando é o checkout PRINCIPAL (não uma worktree):
- criar branch: `git checkout -b|-B`, `git switch -c|-C|--create`;
- trocar para outra branch: `git switch <b>` / `git checkout <b>` com `<b>` != develop (local ou
  só remota — o `checkout` cria a local por DWIM), e `-` (volta à branch anterior);
- `git worktree add` manual (o script valida nome/issue, copia `.env` e isola portas).

Segmentos (`&&`, `||`, `;`, `|`, `&`, quebra de linha, grupos `( )`/`{ }`) e diretório efetivo
(`cwd` do hook, `cd <dir>` anteriores no mesmo comando, `git -C <dir>`): regra comum em
`_shell_segments.py`, a mesma do `publish_guard`. Regra: docs/GIT-WORKFLOW.md §"Branches em voo".
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from _shell_segments import commands, executable, git_invocation

BASE_BRANCH = "develop"
REASON = (
    'Checkout principal fica livre em `develop` (GIT-WORKFLOW §"Branches em voo"). '
    "Crie a worktree: `python scripts/worktree-new.py <branch> --no-setup --no-vscode` "
    "e trabalhe dentro dela."
)


def _git(cwd: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=5, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def is_main_worktree(path: Path) -> bool:
    out = _git(path, "rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir")
    if out is None:
        return False
    git_dir, _, common_dir = out.partition("\n")
    return Path(git_dir).resolve() == Path(common_dir).resolve()


def branch_exists(path: Path, name: str) -> bool:
    """Local ou só remota: `git checkout <b>` com `<b>` só em `origin/` cria e troca (DWIM)."""
    refs = (f"refs/heads/{name}", f"refs/remotes/*/{name}")
    return bool(_git(path, "for-each-ref", "--count=1", "--format=%(refname)", *refs))


def _positional(rest: list[str]) -> list[str]:
    return [a for a in rest if not a.startswith("-")]


def _switch(rest: list[str], _cwd: Path, _exists: Callable[[Path, str], bool]) -> bool:
    targets = _positional(rest)
    creates = any(a in ("-c", "-C", "--create") for a in rest)
    return creates or "-" in rest or (bool(targets) and targets[0] != BASE_BRANCH)


def _checkout(rest: list[str], cwd: Path, exists: Callable[[Path, str], bool]) -> bool:
    if any(a in ("-b", "-B", "-t", "--track", "-") for a in rest):
        return True
    targets = _positional(rest)  # `--` = restaurar arquivo, não troca de branch
    switches = "--" not in rest and len(targets) == 1 and targets[0] != BASE_BRANCH
    return switches and exists(cwd, targets[0])


def _worktree(rest: list[str], _cwd: Path, _exists: Callable[[Path, str], bool]) -> bool:
    return rest[:1] == ["add"]


_CHECKS = {"switch": _switch, "checkout": _checkout, "worktree": _worktree}


def _violation(args: list[str], cwd: Path, exists: Callable[[Path, str], bool]) -> bool:
    check = _CHECKS.get(args[0]) if args else None
    return check is not None and check(args[1:], cwd, exists)


def blocked(
    command: str,
    cwd: Path,
    is_main: Callable[[Path], bool] = is_main_worktree,
    exists: Callable[[Path, str], bool] = branch_exists,
) -> bool:
    for here, tokens in commands(command, cwd):
        if executable(tokens) != "git":
            continue
        target, _config, args = git_invocation(tokens, here)
        if _violation(args, target, exists) and is_main(target):
            return True
    return False


def main() -> int:
    try:
        payload: dict[str, Any] = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    command = str((payload.get("tool_input") or {}).get("command") or "")
    cwd = Path(str(payload.get("cwd") or "."))
    if command and blocked(command, cwd):
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": REASON,
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
