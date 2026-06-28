"""Valida que toda Stage (`docs/stages/N.M-<slug>/technical.md`) tem uma
issue correspondente no backlog do GitHub, conforme exigido por
CONVENTIONS.md §3 e GIT-WORKFLOW.md §Princípios fundamentais #1
("Issue-first").

Regra aplicada (CONVENTIONS.md §3):

  Pré-requisito de Fase 3A (bloqueante) — a Stage só pode iniciar a
  Fase 3A se já existir uma issue correspondente no backlog do GitHub,
  verificável via `gh issue view <num>`.

O check programático:

1. Varre `docs/stages/*/technical.md`.
2. Lê `issue_id` do frontmatter (regex; sem pyyaml).
3. Roda `gh issue view <id> --json number,state` no repositório atual.
4. Falha se: `issue_id` ausente, não é int, ou a issue não existe.

Best-effort: se `gh` não está instalado ou não está autenticado, o
script imprime WARN e retorna 0 (não bloqueia local dev sem `gh`).
Em CI com `gh` autenticado (via `GH_TOKEN`/`GITHUB_TOKEN`), funciona
normalmente.

Uso:
    python scripts/check_stage_issue.py
    python scripts/check_stage_issue.py docs/stages/2.3-s3-source/technical.md

Exit codes:
  0  todas as Stages têm issue válida (ou `gh` indisponível — WARN)
  1  pelo menos uma Stage tem issue inválida ou ausente
  2  erro interno
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_ISSUE_ID_RE = re.compile(r"^\s*issue_id:\s*(.+?)\s*$", re.MULTILINE)
_STATUS_RE = re.compile(r"^\s*status:\s*(\S+)\s*$", re.MULTILINE)


def gh_available() -> bool:
    """True se `gh` está instalado E autenticado."""
    if shutil.which("gh") is None:
        return False
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def issue_exists(issue_id: int) -> bool:
    """True se a issue existe no repositório atual (cwd)."""
    try:
        result = subprocess.run(
            ["gh", "issue", "view", str(issue_id), "--json", "number,state"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            return False
        data = json.loads(result.stdout)
        return data.get("number") == issue_id
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return False


def parse_frontmatter(path: Path) -> dict[str, str]:
    """Extrai os campos do frontmatter YAML (apenas key: value flat)."""
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if m is None:
        return {}
    block = m.group(1)
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line and not line.lstrip().startswith("-"):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def check_one(technical_path: Path) -> tuple[bool, str]:
    """Retorna (ok, mensagem). ok=False indica falha bloqueante."""
    fm = parse_frontmatter(technical_path)
    raw = fm.get("issue_id")
    if raw is None:
        return False, "campo `issue_id` ausente no frontmatter"
    try:
        issue_id = int(raw)
    except ValueError:
        return False, f"`issue_id: {raw!r}` não é inteiro"
    if not issue_exists(issue_id):
        return False, f"issue #{issue_id} não encontrada via `gh issue view`"
    return True, f"issue #{issue_id} OK"


def discover_technicals(target: Path | None) -> list[Path]:
    if target is not None:
        if not target.is_file():
            print(f"check_stage_issue: arquivo não existe: {target}", file=sys.stderr)
            sys.exit(2)
        return [target]
    stages_dir = Path("docs/stages")
    if not stages_dir.is_dir():
        return []
    return sorted(stages_dir.glob("*/technical.md"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        nargs="?",
        type=Path,
        help="Caminho de um technical.md específico; se omitido, varre docs/stages/*/.",
    )
    args = parser.parse_args()

    technicals = discover_technicals(args.target)
    if not technicals:
        print("check_stage_issue: nenhuma Stage encontrada — nada a checar")
        return 0

    if not gh_available():
        print(
            "check_stage_issue: WARN — `gh` não disponível ou não autenticado; "
            "verificação programática pulada (best-effort). Para ativar, "
            "instale `gh` e rode `gh auth login`.",
            file=sys.stderr,
        )
        return 0

    failures: list[tuple[Path, str]] = []
    for tech in technicals:
        ok, msg = check_one(tech)
        status_tag = "OK   " if ok else "FALHA"
        print(f"  {status_tag} {tech}: {msg}")
        if not ok:
            failures.append((tech, msg))

    if failures:
        print("", file=sys.stderr)
        print(
            f"check_stage_issue: FALHA — {len(failures)} Stage(s) sem issue válida:",
            file=sys.stderr,
        )
        for tech, msg in failures:
            print(f"  {tech}: {msg}", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "Toda Stage exige issue correspondente no backlog do GitHub antes\n"
            "de iniciar a Fase 3A (CONVENTIONS.md §3 + GIT-WORKFLOW.md §Princípios\n"
            "fundamentais #1). Crie a issue (`gh issue create ...`) e ajuste o\n"
            "campo `issue_id` no frontmatter do `technical.md` — ou, se a Stage\n"
            "não deveria existir, remova `docs/stages/N.M-<slug>/`.",
            file=sys.stderr,
        )
        return 1

    print(f"check_stage_issue: OK — {len(technicals)} stage(s) checada(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
