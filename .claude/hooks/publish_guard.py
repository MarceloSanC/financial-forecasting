"""Hook PreToolUse (Bash/PowerShell): trava o que é irreversível no fechamento autônomo.

As regras `permissions.allow` de `git push`/`gh pr`/`gh issue` (adicionadas pelo humano) tiram o
classificador do modo automático do caminho; este hook põe no lugar uma trava determinística.
Recusa:
- `git push` para `develop`/`main` (refspec, `--delete`, ou branch atual quando sem refspec),
  `--force`/`-f`/`+refspec` (só `--force-with-lease` passa), `--all`/`--mirror`, e push a partir
  do checkout PRINCIPAL (que fica em `develop`; o trabalho sai das worktrees);
- `gh pr merge` sem `--merge`, com `--admin`/`--auto`, ou quando o PR consultado no GitHub não
  cumpre TODAS as condições do fechamento autônomo: base `develop`, não draft, corpo com
  `> **Auditoria:** complete`, todos os checks concluídos com sucesso, `mergeStateStatus` `CLEAN`
  e nenhuma conversa de review sem resolver. Consulta que falha = recusa (fail-closed);
- `gh pr edit --base` e, em `gh pr edit`/`gh issue edit`, label, assignee, milestone e projeto;
- `gh issue close|reopen|delete|transfer`;
- `gh api` que escreve: `-X/--method` diferente de GET, ou `graphql` com `mutation`.

Passam: push da branch da worktree, edição de título/corpo, comentários, leituras.

Diretório efetivo = `cwd` do hook, seguido de `cd <dir>` anteriores no mesmo comando e de
`git -C <dir>` (como no `git_guard`). Regra: docs/GIT-WORKFLOW.md §"Fechamento autônomo pela
auditoria".
"""

from __future__ import annotations

import itertools
import json
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

PROTECTED = frozenset({"develop", "main"})
BASE_BRANCH = "develop"
_RULE = 'GIT-WORKFLOW §"Fechamento autônomo pela auditoria"'
_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\|")
_GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_AUDIT_COMPLETE = re.compile(r"^>\s*\*\*Auditoria:\*\*\s*`?complete`?", re.MULTILINE)
_CHECK_OK = {"SUCCESS", "SKIPPED", "NEUTRAL"}
_PUSH_FORCE = {"--force", "-f", "--force-if-includes"}
_PUSH_BROAD = {"--all", "--mirror", "--branches"}
_PUSH_OPTS_WITH_VALUE = {"--repo", "-o", "--push-option", "--receive-pack", "--exec"}
_GH_OPTS_WITH_VALUE = {"-R", "--repo"}
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
    fields = "number,baseRefName,body,isDraft,mergeStateStatus,statusCheckRollup,url"
    pr = _gh_json(cwd, "pr", "view", *target, *repo_args, "--json", fields)
    if not isinstance(pr, dict):
        return None
    unresolved = _unresolved_threads(cwd, str(pr.get("url", "")), int(pr.get("number", 0)))
    if unresolved is None:
        return None
    pr["unresolvedThreads"] = unresolved
    return pr


def _flags(args: list[str]) -> set[str]:
    return {a.split("=", 1)[0] for a in args if a.startswith("-")}


def _strip_ref(ref: str) -> str:
    return ref.removeprefix("refs/heads/")


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
    src, _, dst = spec.partition(":")
    target = _strip_ref(dst or src)
    if target == "HEAD":
        target = current or "HEAD"
    if target in PROTECTED or target == "HEAD":
        return f"`git push` para `{target}`: só entra por PR com merge commit."
    return None


def _push_reason(
    args: list[str],
    cwd: Path,
    is_main: Callable[[Path], bool],
    branch: Callable[[Path], str | None],
) -> str | None:
    flags = _flags(args)
    refspecs = _push_positional(args)[1:]
    current = branch(cwd)
    if is_main(cwd):
        found: str | None = (
            "`git push` a partir do checkout principal: ele fica em `develop`; "
            "faça push de dentro da worktree da branch."
        )
    elif flags & _PUSH_FORCE:
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


def _merge_target(args: list[str]) -> tuple[str | None, str | None]:
    selector: str | None = None
    repo: str | None = None
    i = 0
    while i < len(args):
        if args[i] in _GH_OPTS_WITH_VALUE and i + 1 < len(args):
            repo = args[i + 1]
            i += 2
            continue
        if args[i].startswith("--repo="):
            repo = args[i].split("=", 1)[1]
        elif not args[i].startswith("-") and selector is None:
            selector = args[i]
        i += 1
    return selector, repo


def _pr_problems(pr: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if pr.get("baseRefName") != BASE_BRANCH:
        problems.append(f"base `{pr.get('baseRefName')}` (esperado `{BASE_BRANCH}`)")
    if pr.get("isDraft"):
        problems.append("PR em draft")
    if not _AUDIT_COMPLETE.search(str(pr.get("body") or "")):
        problems.append("corpo sem `> **Auditoria:** complete`")
    bad = [
        str(c.get("name") or c.get("context") or "?")
        for c in pr.get("statusCheckRollup") or []
        if (c.get("conclusion") or c.get("state") or "").upper() not in _CHECK_OK
    ]
    if bad:
        problems.append(f"checks não verdes: {', '.join(bad)}")
    if pr.get("mergeStateStatus") != "CLEAN":
        problems.append(f"mergeStateStatus `{pr.get('mergeStateStatus')}` (esperado `CLEAN`)")
    if pr.get("unresolvedThreads", 1):
        problems.append(f"{pr.get('unresolvedThreads')} conversa(s) de review sem resolver")
    return problems


def _merge_reason(args: list[str], cwd: Path, fetch: PrFetcher) -> str | None:
    flags = _flags(args)
    if flags & _MERGE_FORBIDDEN:
        return "`gh pr merge`: só merge commit (`--merge`), sem `--squash/--rebase/--admin/--auto`."
    if not flags & {"--merge", "-m"}:
        return "`gh pr merge` sem `--merge`: o merge commit é obrigatório (GIT-WORKFLOW §Gates)."
    selector, repo = _merge_target(args)
    pr = fetch(selector, cwd, repo)
    if pr is None:
        return "`gh pr merge`: não consegui consultar o PR no GitHub — recuso por segurança."
    problems = _pr_problems(pr)
    if not problems:
        return None
    return f"`gh pr merge` #{pr.get('number')}: " + "; ".join(problems) + "."


def _api_reason(rest: list[str]) -> str | None:
    if rest[:1] == ["graphql"]:
        mutation = any("mutation" in a for a in rest)
        return "`gh api graphql` com `mutation`: escrita direta na API." if mutation else None
    pairs = itertools.pairwise(rest)
    explicit = next((value for flag, value in pairs if flag in ("-X", "--method")), None)
    inline = (a.split("=", 1)[1] for a in rest if a.startswith("--method="))
    explicit = explicit or next(inline, None)
    has_fields = any(a.split("=", 1)[0] in _API_FIELD_FLAGS for a in rest)
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
    while args and args[0] in _GH_OPTS_WITH_VALUE:
        args = args[2:]
    group, rest = (args[0], args[1:]) if args else ("", [])
    sub, sub_args = (rest[0], rest[1:]) if rest else ("", [])
    found: str | None = None
    if group == "api":
        found = _api_reason(rest)
    elif group == "pr" and sub == "merge":
        found = _merge_reason(sub_args, cwd, fetch)
    elif group in ("pr", "issue") and sub == "edit":
        found = _edit_reason(group, sub_args)
    elif group == "issue" and sub in _ISSUE_FORBIDDEN:
        found = f"`gh issue {sub}`: a issue fecha pelo `Closes #N` do merge; o resto é do humano."
    return found


def _tokens(segment: str) -> list[str]:
    try:  # posix=False preserva `\` de caminho Windows; aspas removidas à mão
        return [t.strip("\"'") for t in shlex.split(segment, posix=False)]
    except ValueError:
        return segment.split()


def reason(
    command: str,
    cwd: Path,
    is_main: Callable[[Path], bool] = is_main_worktree,
    branch: Callable[[Path], str | None] = current_branch,
    fetch: PrFetcher = fetch_pr,
) -> str | None:
    here = cwd
    for segment in _SEGMENT_SPLIT.split(command):
        tokens = _tokens(segment)
        while tokens and _ENV_ASSIGN.match(tokens[0]):
            tokens = tokens[1:]
        if not tokens:
            continue
        if tokens[0] in ("cd", "Set-Location", "pushd") and len(tokens) > 1:
            here = (here / tokens[1]).resolve()
            continue
        exe = Path(tokens[0]).stem.lower()
        found: str | None = None
        if exe == "git":
            target, i = here, 1
            while i < len(tokens) and tokens[i].startswith("-"):
                if tokens[i] == "-C" and i + 1 < len(tokens):
                    target = (here / tokens[i + 1]).resolve()
                i += 2 if tokens[i] in _GIT_OPTS_WITH_VALUE else 1
            if tokens[i : i + 1] == ["push"]:
                found = _push_reason(tokens[i + 1 :], target, is_main, branch)
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
