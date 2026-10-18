"""Hook PreToolUse (Bash/PowerShell): trava o que é irreversível no fechamento autônomo.

As regras `permissions.allow` de `git push`/`gh pr`/`gh issue` (adicionadas pelo humano) tiram o
classificador do modo automático do caminho; este hook põe no lugar uma trava determinística.
Recusa:
- `git push` para `develop`/`main` (refspec, `--delete`, `HEAD`/`@`, ou branch atual quando
  sem refspec), refspec com curinga ou matching (`:`), `--force`/`-f`/`+refspec` (só
  `--force-with-lease` passa), `--all`/`--mirror`/`--prune`, `-c push.*`/`-c remote.*`, e push a
  partir do checkout PRINCIPAL (que fica em `develop`; o trabalho sai das worktrees);
- `gh pr merge` sem `--merge`, com `--admin`/`--auto`, ou quando o PR consultado no GitHub não
  cumpre TODAS as condições do fechamento autônomo: base `develop`, não draft, corpo com
  `> **Auditoria:** complete`, checks obrigatórios presentes e todos os checks com sucesso,
  `mergeStateStatus` `CLEAN`, nenhuma conversa de review sem resolver e `--match-head-commit`
  igual ao HEAD consultado (fecha a janela entre a checagem e o merge). Consulta que falha =
  recusa (fail-closed);
- `gh pr edit --base` e, em `gh pr edit`/`gh issue edit`, label, assignee, milestone e projeto;
- `gh issue close|reopen|delete|transfer`;
- `gh api` que escreve: `-X/--method` diferente de GET, campo sem método, ou `graphql` com
  `mutation`.

Segmentos, diretório efetivo (`cd`, `git -C`) e o que fica fora do alcance do parsing: regra
comum em `_shell_segments.py` (a mesma do `git_guard`). O classificador continua cobrindo o que
o parsing não vê, porque não casa com as regras allow (alias do `gh`, scripts, curl, `bash -c`).

Passam: push da branch da worktree, edição de título/corpo, comentários, leituras.

Regra: docs/GIT-WORKFLOW.md §"Fechamento autônomo pela auditoria".
"""

from __future__ import annotations

import itertools
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from _shell_segments import commands, executable, git_invocation

PROTECTED = frozenset({"develop", "main"})
BASE_BRANCH = "develop"
_RULE = 'GIT-WORKFLOW §"Fechamento autônomo pela auditoria"'
_AUDIT_COMPLETE = re.compile(r"^>\s*\*\*Auditoria:\*\*\s*`?complete`?\s*$", re.MULTILINE)
_CHECK_OK = {"SUCCESS", "SKIPPED", "NEUTRAL"}
_REQUIRED_CHECKS = frozenset({"lint-and-test", "audit-status"})
_PUSH_FORCE = {"--force", "-f"}
_PUSH_BROAD = {"--all", "--mirror", "--branches", "--prune"}
_PUSH_CONFIG = ("push.", "remote.")
_PUSH_OPTS_WITH_VALUE = {"--repo", "-o", "--push-option", "--receive-pack", "--exec"}
_EDIT_FORBIDDEN = {
    "--add-label",
    "--remove-label",
    "--add-assignee",
    "--remove-assignee",
    "--milestone",
    "-m",
    "--remove-milestone",
    "--add-project",
    "--remove-project",
}
_ISSUE_FORBIDDEN = {"close", "reopen", "delete", "transfer"}
_MERGE_FORBIDDEN = {"--squash", "-s", "--rebase", "-r", "--admin", "--auto"}
_API_FIELD_FLAGS = {"-f", "-F", "--field", "--raw-field", "--input"}

PrFetcher = Callable[[str | None, Path, str | None], dict[str, Any] | None]


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


def current_branch(path: Path) -> str | None:
    return _git(path, "branch", "--show-current") or None


def _gh_json(cwd: Path, *args: str) -> object:
    try:
        out = subprocess.run(
            ["gh", *args], cwd=cwd, capture_output=True, text=True, timeout=30, check=True
        )
        return json.loads(out.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def _unresolved_threads(cwd: Path, url: str, number: int) -> int | None:
    match = re.search(r"github\.com/([^/]+)/([^/]+)/pull/", url)
    if match is None:
        return None
    query = (
        "query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n)"
        "{reviewThreads(first:100){nodes{isResolved}}}}}"
    )
    owner, name = match.group(1), match.group(2)
    graphql = ["api", "graphql", "-f", f"query={query}", "-F", f"o={owner}", "-F", f"r={name}"]
    threads: Any = _gh_json(cwd, *graphql, "-F", f"n={number}")
    try:
        nodes = threads["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    except (TypeError, KeyError):
        return None
    return sum(1 for n in nodes if not n.get("isResolved"))


def fetch_pr(selector: str | None, cwd: Path, repo: str | None) -> dict[str, Any] | None:
    """Estado do PR no GitHub + `unresolvedThreads`; None se qualquer consulta falhar."""
    target = [selector] if selector else []
    repo_args = ["-R", repo] if repo else []
    fields = "number,baseRefName,body,isDraft,mergeStateStatus,statusCheckRollup,url,headRefOid"
    pr = _gh_json(cwd, "pr", "view", *target, *repo_args, "--json", fields)
    if not isinstance(pr, dict):
        return None
    unresolved = _unresolved_threads(cwd, str(pr.get("url", "")), int(pr.get("number", 0)))
    if unresolved is None:
        return None
    pr["unresolvedThreads"] = unresolved
    return pr


def _flags(args: list[str]) -> set[str]:
    """Nomes das opções: `--x=v` → `--x`; `-Bmain`/`-X=PUT` → `-B`/`-X` (valor colado)."""
    return {a.split("=", 1)[0] if a.startswith("--") else a[:2] for a in args if a.startswith("-")}


def _strip_ref(ref: str) -> str:
    return ref.removeprefix("refs/").removeprefix("heads/")


def _push_positional(args: list[str]) -> list[str]:
    positional: list[str] = []
    i = 0
    while i < len(args):
        if args[i] in _PUSH_OPTS_WITH_VALUE:
            i += 2
            continue
        if not args[i].startswith("-"):
            positional.append(args[i])
        i += 1
    return positional


def _refspec_reason(spec: str, current: str | None) -> str | None:
    if spec.startswith("+"):
        return f"`git push {spec}`: refspec com `+` força o push; use `--force-with-lease`."
    if "*" in spec or spec == ":":
        return (
            f"`git push {spec}`: curinga/matching empurra `develop`/`main` junto; nomeie a branch."
        )
    src, _, dst = spec.partition(":")
    target = _strip_ref(dst or src)
    if target in ("HEAD", "@"):
        target = current or "HEAD"
    if target in PROTECTED or target == "HEAD":
        return f"`git push` para `{target}`: só entra por PR com merge commit."
    return None


def _push_reason(
    args: list[str],
    cwd: Path,
    is_main: Callable[[Path], bool],
    branch: Callable[[Path], str | None],
    config: list[str],
) -> str | None:
    flags = _flags(args)
    clustered_force = any(a[:2] != "--" and a[:1] == "-" and "f" in a[1:] for a in args)
    refspecs = _push_positional(args)[1:]
    current = branch(cwd)
    if any(c.startswith(_PUSH_CONFIG) for c in config):
        found: str | None = "`git -c push.*/remote.* push` muda o destino do push; tire o `-c`."
    elif is_main(cwd):
        found = (
            "`git push` a partir do checkout principal: ele fica em `develop`; "
            "faça push de dentro da worktree da branch."
        )
    elif flags & _PUSH_FORCE or clustered_force:
        found = "`git push --force`: use `--force-with-lease` (não sobrescreve trabalho alheio)."
    elif flags & _PUSH_BROAD:
        found = "`git push --all/--mirror` empurra `develop`/`main` junto; nomeie a branch."
    elif not refspecs and (current is None or current in PROTECTED):
        found = (
            f"`git push` sem refspec na branch `{current}`: só branch de worktree "
            "(nunca `develop`/`main`) sai por push."
        )
    else:
        found = next(filter(None, (_refspec_reason(s, current) for s in refspecs)), None)
    return found


def _split_repo(args: list[str]) -> tuple[str | None, list[str]]:
    """Tira `-R X`, `-RX`, `--repo X` e `--repo=X` de qualquer posição (o gh aceita todas)."""
    repo: str | None = None
    rest: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-R", "--repo") and i + 1 < len(args):
            repo, i = args[i + 1], i + 2
            continue
        if a.startswith("--repo="):
            repo = a.split("=", 1)[1]
        elif a.startswith("-R") and len(a) > 2:  # noqa: PLR2004 — `-R` + valor colado
            repo = a[2:].lstrip("=")
        else:
            rest.append(a)
        i += 1
    return repo, rest


def _merge_options(args: list[str]) -> tuple[str | None, str | None]:
    """(seletor do PR, valor de `--match-head-commit`)."""
    selector: str | None = None
    head: str | None = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--match-head-commit" and i + 1 < len(args):
            head, i = args[i + 1], i + 2
            continue
        if a.startswith("--match-head-commit="):
            head = a.split("=", 1)[1]
        elif a in ("-b", "--body", "-F", "--body-file", "-t", "--subject", "-A", "--author-email"):
            i += 1  # pula o valor da opção
        elif not a.startswith("-") and selector is None:
            selector = a
        i += 1
    return selector, head


def _pr_problems(pr: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if pr.get("baseRefName") != BASE_BRANCH:
        problems.append(f"base `{pr.get('baseRefName')}` (esperado `{BASE_BRANCH}`)")
    if pr.get("isDraft"):
        problems.append("PR em draft")
    if not _AUDIT_COMPLETE.search(str(pr.get("body") or "")):
        problems.append("corpo sem `> **Auditoria:** complete`")
    checks = pr.get("statusCheckRollup") or []
    status = {
        str(c.get("name") or c.get("context") or "?"): (
            c.get("conclusion") or c.get("state") or ""
        ).upper()
        for c in checks
    }
    bad = [name for name, conclusion in status.items() if conclusion not in _CHECK_OK]
    if bad:
        problems.append(f"checks não verdes: {', '.join(bad)}")
    missing = sorted(n for n in _REQUIRED_CHECKS if status.get(n) != "SUCCESS")
    if missing:
        problems.append(f"checks obrigatórios sem sucesso no HEAD: {', '.join(missing)}")
    if pr.get("mergeStateStatus") != "CLEAN":
        problems.append(f"mergeStateStatus `{pr.get('mergeStateStatus')}` (esperado `CLEAN`)")
    if pr.get("unresolvedThreads", 1):
        problems.append(f"{pr.get('unresolvedThreads')} conversa(s) de review sem resolver")
    return problems


def _merge_reason(args: list[str], cwd: Path, fetch: PrFetcher, repo: str | None) -> str | None:
    flags = _flags(args)
    if flags & _MERGE_FORBIDDEN:
        return "`gh pr merge`: só merge commit (`--merge`), sem `--squash/--rebase/--admin/--auto`."
    if not flags & {"--merge", "-m"}:
        return "`gh pr merge` sem `--merge`: o merge commit é obrigatório (GIT-WORKFLOW §Gates)."
    selector, head = _merge_options(args)
    pr = fetch(selector, cwd, repo)
    if pr is None:
        return "`gh pr merge`: não consegui consultar o PR no GitHub — recuso por segurança."
    problems = _pr_problems(pr)
    if head is None:
        problems.append("sem `--match-head-commit <headRefOid>`")
    elif head != pr.get("headRefOid"):
        problems.append(f"`--match-head-commit` {head} ≠ HEAD do PR {pr.get('headRefOid')}")
    if not problems:
        return None
    return f"`gh pr merge` #{pr.get('number')}: " + "; ".join(problems) + "."


def _api_reason(rest: list[str]) -> str | None:
    if rest[:1] == ["graphql"]:
        mutation = any("mutation" in a for a in rest)
        return "`gh api graphql` com `mutation`: escrita direta na API." if mutation else None
    pairs = itertools.pairwise(rest)
    explicit = next((value for flag, value in pairs if flag in ("-X", "--method")), None)
    inline = (
        a.split("=", 1)[1] if a.startswith("--") else a[2:].lstrip("=")
        for a in rest
        if a.startswith("--method=") or (a.startswith("-X") and len(a) > 2)  # noqa: PLR2004
    )
    explicit = explicit or next(inline, None)
    has_fields = bool(_flags(rest) & _API_FIELD_FLAGS)
    method = (explicit or ("POST" if has_fields else "GET")).upper()  # gh: campo ⇒ POST
    return None if method == "GET" else f"`gh api` com método {method}: escrita direta na API."


def _edit_reason(group: str, sub_args: list[str]) -> str | None:
    flags = _flags(sub_args)
    if group == "pr" and flags & {"--base", "-B"}:
        return "`gh pr edit --base`: trocar a base do PR fica com o humano."
    if flags & _EDIT_FORBIDDEN:
        return (
            f"`gh {group} edit` com label/assignee/milestone/projeto: fora do fechamento autônomo "
            "(edite só título e corpo)."
        )
    return None


def _gh_reason(args: list[str], cwd: Path, fetch: PrFetcher) -> str | None:
    repo, args = _split_repo(args)
    group, rest = (args[0], args[1:]) if args else ("", [])
    sub, sub_args = (rest[0], rest[1:]) if rest else ("", [])
    found: str | None = None
    if group == "api":
        found = _api_reason(rest)
    elif group == "pr" and sub == "merge":
        found = _merge_reason(sub_args, cwd, fetch, repo)
    elif group in ("pr", "issue") and sub == "edit":
        found = _edit_reason(group, sub_args)
    elif group == "issue" and sub in _ISSUE_FORBIDDEN:
        found = f"`gh issue {sub}`: a issue fecha pelo `Closes #N` do merge; o resto é do humano."
    return found


def reason(
    command: str,
    cwd: Path,
    is_main: Callable[[Path], bool] = is_main_worktree,
    branch: Callable[[Path], str | None] = current_branch,
    fetch: PrFetcher = fetch_pr,
) -> str | None:
    for here, tokens in commands(command, cwd):
        exe = executable(tokens)
        found: str | None = None
        if exe == "git":
            target, config, args = git_invocation(tokens, here)
            if args[:1] == ["push"]:
                found = _push_reason(args[1:], target, is_main, branch, config)
        elif exe == "gh":
            found = _gh_reason(tokens[1:], here, fetch)
        if found:
            return found
    return None


def main() -> int:
    try:
        payload: dict[str, Any] = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    command = str((payload.get("tool_input") or {}).get("command") or "")
    cwd = Path(str(payload.get("cwd") or "."))
    found = reason(command, cwd) if command else None
    if found:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"{found} ({_RULE}; hook publish_guard)",
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
