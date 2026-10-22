"""Validate that the commit subject follows the project convention.

Wired as `commit-msg` hook in `.pre-commit-config.yaml`. Receives the path
to the commit message file as the first argument; reads only the first
line (subject) and validates against:

  (1) Reserved gate commits (CONVENTIONS.md §4(b)).
  (2) Conventional Commits in Portuguese with required scope (ASCII/kebab)
      and optional `[N.M/task-NN]` or `[N.M/--]` suffix
      (CONVENTIONS.md §4(a)).

Subject description may contain any UTF-8 (PT-BR with accents is the
default); only the scope is restricted to ASCII/kebab so it stays
terminal-friendly.

Body content is NOT validated here — the bullet-list expectation lives in
the docs and is enforced by code review, not by the hook (avoids false
positives on trivial commits where the body is intentionally absent).

It is also the only hook that runs on every clone and worktree of this
repo: the Python of the host runs it, with the standard library only. So
it warns, without blocking, when the `pre-commit` hook is not installed —
then `ruff-format`, `ruff` and `mypy` from `.pre-commit-config.yaml` did
not run on this commit (issue #199).

Exit codes:
  0  subject OK
  1  subject violates convention (message printed to stderr)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ALLOWED_TYPES = (
    "feat",
    "fix",
    "refactor",
    "test",
    "docs",
    "chore",
    "perf",
    "style",
    "build",
    "ci",
)

# Reserved subjects — fixed text, NOT Conventional Commits.
RESERVED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^stage \d+\.\d+: (conceptual|technical) (draft|approved)$"),
    re.compile(r"^stage \d+\.\d+: complete$"),
    re.compile(
        r"^docs\((overview|roadmap)\): approved"
        r"(?: \[projects/[a-z0-9._-]+\](?: \(adoption\))?)?$"
    ),
    re.compile(
        r"^chore\((concept|technical)\): revert to draft "
        r"[—-] revision-from-(technical|execution): .+$"
    ),
    re.compile(r"^chore(?:\([a-z0-9._-]+\))?: bootstrap from [a-z0-9._-]+$"),
)

# Conventional Commits: <type>(<scope>): <description> [optional tag]
# Scope is REQUIRED here (CONVENTIONS.md §4(a) "minimum scope rule").
# Exceptions that genuinely lack a scope go through RESERVED_PATTERNS or
# the passthrough prefixes (merge/revert).
# Optional suffix: `[N.M/task-NN]` or `[N.M/--]`.
CC_PATTERN = re.compile(
    r"^(?P<type>" + "|".join(ALLOWED_TYPES) + r")"
    r"\((?P<scope>[a-z0-9._-]+)\)"
    r": (?P<desc>\S.*?)"
    r"(?: \[(?P<tag>\d+\.\d+/(?:task-\d{2}|--))\])?$"
)

# Allow merges and reverts without further checks.
PASSTHROUGH_PREFIXES = ("Merge ", "Revert ")

MAX_SUBJECT_LEN = 100

# argv esperado: [script_name, commit_msg_path]
_REQUIRED_ARGC = 2


def _format_help() -> str:
    return (
        "\nFormato esperado (um destes):\n"
        "  <tipo>(<escopo>): <descrição em português> [opcional N.M/task-NN]\n"
        f"    onde <tipo> é um de: {', '.join(ALLOWED_TYPES)}\n"
        "    escopo em ASCII/kebab (snake/kebab); descrição livre em PT-BR\n"
        "    exemplos:\n"
        "      feat(ingestion): adicionar S3 source adapter [2.3/task-01]\n"
        "      fix(payment.retry): limitar backoff exponencial em 30s\n"
        "      docs(roadmap): marcar stage 2.3 como done [2.3/--]\n"
        "\n  Mensagens reservadas de gate (ver docs/CONVENTIONS.md §4(b)):\n"
        "      stage N.M: conceptual draft\n"
        "      stage N.M: conceptual approved\n"
        "      stage N.M: technical draft\n"
        "      stage N.M: technical approved\n"
        "      stage N.M: complete\n"
        "      docs(overview): approved\n"
        "      docs(roadmap): approved\n"
        "      chore(concept): revert to draft — revision-from-technical: <motivo>\n"
        "      chore(technical): revert to draft — revision-from-execution: <motivo>\n"
        "\nRegras completas: docs/CONVENTIONS.md §4 e docs/GIT-WORKFLOW.md §Commits.\n"
    )


def _error(subject: str, reason: str) -> int:
    print("check_commit_msg: rejected commit subject", file=sys.stderr)
    print(f"  subject: {subject!r}", file=sys.stderr)
    print(f"  reason : {reason}", file=sys.stderr)
    print(_format_help(), file=sys.stderr)
    return 1


def _no_match_reason(subject: str) -> str:
    no_scope = re.match(
        r"^(?:" + "|".join(ALLOWED_TYPES) + r"): ",
        subject,
    )
    if no_scope:
        return (
            "escopo ausente — subject precisa ser "
            "`<tipo>(<escopo>): <descrição>` (CONVENTIONS.md §4(a) — "
            "regra de escopo mínimo)"
        )
    return (
        "não bate com Conventional Commits "
        "(`<tipo>(<escopo>): <descrição>`) nem com nenhuma mensagem "
        "reservada de gate"
    )


def validate_subject(subject: str) -> int:
    if not subject:
        return _error(subject, "empty subject")

    if subject.startswith(PASSTHROUGH_PREFIXES):
        return 0

    if len(subject) > MAX_SUBJECT_LEN:
        return _error(
            subject,
            f"subject too long ({len(subject)} chars; max {MAX_SUBJECT_LEN})",
        )

    if any(pat.match(subject) for pat in RESERVED_PATTERNS):
        return 0

    if CC_PATTERN.match(subject) is not None:
        return 0

    return _error(subject, _no_match_reason(subject))


def pre_commit_hook_path(cwd: Path) -> Path | None:
    """Where git looks for the `pre-commit` hook of the repo at `cwd`.

    Uses `git rev-parse --git-path`, which follows `core.hooksPath` and the
    common `.git/hooks` shared by every worktree. `None` when git does not
    answer (no git, not a repo): the warning then stays silent.
    """
    try:
        cp = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks/pre-commit"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if cp.returncode != 0 or not cp.stdout.strip():
        return None
    return cwd / cp.stdout.strip()


def warn_if_pre_commit_hook_missing(cwd: Path) -> bool:
    """Print a warning when the `pre-commit` hook is missing. Never blocks.

    Returns True when it warned.
    """
    hook = pre_commit_hook_path(cwd)
    if hook is None or hook.is_file():
        return False
    lines = (
        f"check_commit_msg: aviso — o hook pre-commit não está instalado ({hook.as_posix()}).",
        "  ruff-format, ruff e mypy do .pre-commit-config.yaml NÃO rodaram neste commit.",
        "  Rode o equivalente no container antes do próximo commit",
        "  (docs/RUNBOOK-STAGE-LIFECYCLE.md §Gates em camadas, T1).",
        "  O commit segue: este aviso não bloqueia.",
    )
    for line in lines:
        print(line, file=sys.stderr)
    return True


def main(argv: list[str]) -> int:
    if len(argv) < _REQUIRED_ARGC:
        print(
            "check_commit_msg: missing commit message file argument",
            file=sys.stderr,
        )
        return 2

    msg_path = Path(argv[1])
    try:
        content = msg_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"check_commit_msg: cannot read {msg_path}: {exc}", file=sys.stderr)
        return 2

    if content.startswith("\ufeff"):
        print(
            "check_commit_msg: rejected commit message: starts with a UTF-8 BOM (invisible "
            "U+FEFF that would stay in the subject). Typical cause: PowerShell Out-File / "
            "Set-Content -Encoding utf8. Write the file without BOM (Python "
            "open(..., 'w', encoding='utf-8'), or git commit -m).",
            file=sys.stderr,
        )
        return 1

    # Skip lines comencing with `#` (git commentary) when looking for subject.
    subject = ""
    for line in content.splitlines():
        if not line.startswith("#"):
            subject = line
            break

    verdict = validate_subject(subject.rstrip())
    warn_if_pre_commit_hook_missing(Path.cwd())
    return verdict


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
