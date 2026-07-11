"""Valida que toda Stage (`docs/stages/N.M-<slug>/technical.md`) tem uma
issue correspondente no backlog do GitHub, conforme exigido por
CONVENTIONS.md §3 e GIT-WORKFLOW.md §Princípios fundamentais #1
("Issue-first").

Regra aplicada (CONVENTIONS.md §3):

  Pré-requisito de Fase 3A (bloqueante) — a Stage só pode iniciar a
  Fase 3A se já existir uma issue correspondente no backlog do GitHub,
  verificável via `gh issue view <num>`.

O check programático:

1. Descobre os `technical.md` a validar (ver modos abaixo).
2. Lê `issue_id` do frontmatter (regex; sem pyyaml).
3. Roda `gh issue view <id> --json number,state` no repositório atual.
4. Falha se: `issue_id` ausente, não é int, ou a issue não existe.

Modos de descoberta:

- **default (delta-only):** valida apenas os `technical.md` novos ou
  modificados vs o merge-base com `origin/develop` (+ untracked).
  Stage que já está em `develop` passou por este gate quando entrou —
  revalidar o passado a cada run só compra latência e flakiness de
  rede (o custo cresceria com o nº de stages do repo).
- **`--all`:** varredura completa de `docs/stages/*/technical.md`
  (auditoria ocasional; usado pelo workflow agendado
  `stage-issue-audit.yml`, que pega drift pós-merge).
- **`<target>`:** valida um arquivo específico.

Fail-safe: se o delta não pode ser determinado (sem `git`, sem
`origin/develop`, merge-base falhou), cai na varredura completa com
WARN — o gate nunca sub-verifica por erro de ambiente.

Best-effort: se `gh` não está instalado ou não está autenticado, o
script imprime WARN e retorna 0 (não bloqueia local dev sem `gh`).
Em CI com `gh` autenticado (via `GH_TOKEN`/`GITHUB_TOKEN`), funciona
normalmente.

Uso:
    python scripts/check_stage_issue.py
    python scripts/check_stage_issue.py --all
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
        return False, "campo `issue_id` ausente do frontmatter"
    try:
        issue_id = int(raw)
    except ValueError:
        return False, f"`issue_id: {raw!r}` não é um inteiro"
    if not issue_exists(issue_id):
        return False, f"issue #{issue_id} não encontrada via 'gh issue view'"
    return True, f"issue #{issue_id} OK"


_BASE_REF = "origin/develop"


def _git_lines(args: list[str]) -> list[str] | None:
    """Roda `git <args>` e devolve stdout em linhas; `None` em qualquer falha."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def discover_changed_technicals() -> list[Path] | None:
    """`technical.md` novos/modificados vs o merge-base com `origin/develop`.

    Inclui mudanças commitadas na branch, mudanças na working tree e
    arquivos untracked. Arquivos deletados/renomeados saem do resultado
    (`is_file()`). Devolve `None` quando o delta não pode ser determinado
    — o chamador cai na varredura completa (fail-safe).
    """
    merge_base = _git_lines(["merge-base", "HEAD", _BASE_REF])
    if not merge_base:
        return None
    changed = _git_lines(["diff", "--name-only", merge_base[0], "--", "docs/stages"])
    if changed is None:
        return None
    untracked = _git_lines(["ls-files", "--others", "--exclude-standard", "docs/stages"])
    if untracked is None:
        return None
    candidates = {Path(line) for line in changed + untracked}
    return sorted(path for path in candidates if path.name == "technical.md" and path.is_file())


def discover_all_technicals() -> list[Path]:
    stages_dir = Path("docs/stages")
    if not stages_dir.is_dir():
        return []
    return sorted(stages_dir.glob("*/technical.md"))


def discover_technicals(target: Path | None, *, scan_all: bool) -> list[Path]:
    if target is not None:
        if not target.is_file():
            print(f"check_stage_issue: arquivo não existe: {target}", file=sys.stderr)
            sys.exit(2)
        return [target]
    if scan_all:
        return discover_all_technicals()
    changed = discover_changed_technicals()
    if changed is None:
        print(
            "check_stage_issue: WARN — não foi possível determinar o delta da branch "
            f"vs '{_BASE_REF}'; caindo na varredura completa.",
            file=sys.stderr,
        )
        return discover_all_technicals()
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        nargs="?",
        type=Path,
        help=(
            "Caminho de um technical.md específico; se omitido, valida só os "
            "novos/modificados vs origin/develop (delta-only)."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Varre docs/stages/*/technical.md inteiro (auditoria ocasional).",
    )
    args = parser.parse_args()

    technicals = discover_technicals(args.target, scan_all=args.all)
    if not technicals:
        print("check_stage_issue: nenhuma Stage nova/modificada — nada a checar")
        return 0

    if not gh_available():
        print(
            "check_stage_issue: WARN — `gh` não disponível ou não autenticado; "
            "verificação programática pulada (best-effort). Para ativar, "
            "instale `gh` e rode `gh auth login` (em CI, injete `GH_TOKEN`).",
            file=sys.stderr,
        )
        return 0

    failures: list[tuple[Path, str]] = []
    for tech in technicals:
        ok, msg = check_one(tech)
        status_tag = "OK   " if ok else "FAILED"
        print(f"  {status_tag} {tech}: {msg}")
        if not ok:
            failures.append((tech, msg))

    if failures:
        print("", file=sys.stderr)
        print(
            f"check_stage_issue: FALHOU — {len(failures)} Stage(s) sem issue válida:",
            file=sys.stderr,
        )
        for tech, msg in failures:
            print(f"  {tech}: {msg}", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "Toda Stage exige uma issue correspondente no backlog do GitHub antes de\n"
            "iniciar a Fase 3A (CONVENTIONS.md §3 + GIT-WORKFLOW.md §Princípios\n"
            "fundamentais #1). Crie a issue (`gh issue create ...`) e ajuste o campo\n"
            "`issue_id` no frontmatter do `technical.md` — ou, se a Stage não deveria\n"
            "existir, remova `docs/stages/N.M-<slug>/`.",
            file=sys.stderr,
        )
        return 1

    print(f"check_stage_issue: OK — {len(technicals)} stage(s) checada(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())