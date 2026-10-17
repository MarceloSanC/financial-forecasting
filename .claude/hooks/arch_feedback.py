"""Hook PostToolUse (Edit|Write): devolve na hora a violação de arquitetura do arquivo editado.

Quando o arquivo editado é um `.py` sob `src/`, roda os gates AST de `make arch-ast` só
sobre ele, pelo executor da skill `architecture-fitness`
(`.claude/skills/architecture-fitness/scripts/check_changed.py`), que importa os gates de
`scripts/` — o hook não tem regra própria (ADR 0.0.0058).

Achado → stderr + exit 2: no PostToolUse o Claude Code mostra o stderr ao agente ("the tool
already ran"; code.claude.com/docs/en/hooks, §Exit code 2 behavior per event). Sem achado,
arquivo fora de escopo ou qualquer erro do próprio hook → exit 0 em silêncio (fail open):
o veredito é do `make check`, não do hook.

A raiz é o ancestral do arquivo editado que contém `scripts/arch_baseline.toml` — não o
`CLAUDE_PROJECT_DIR`, porque a sessão aberta no checkout principal edita arquivos de
worktrees (`scripts/worktree-new.py`); o executor carregado é o dessa raiz.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

RUNNER_REL = Path(".claude") / "skills" / "architecture-fitness" / "scripts" / "check_changed.py"
BASELINE_REL = Path("scripts") / "arch_baseline.toml"
EXIT_FEEDBACK = 2


def find_root(path: Path) -> Path | None:
    """Ancestral de `path` com o baseline e o executor (repo ou worktree)."""
    for candidate in path.parents:
        if (candidate / BASELINE_REL).is_file() and (candidate / RUNNER_REL).is_file():
            return candidate
    return None


def _load_runner(root: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("_arch_feedback_runner", root / RUNNER_REL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def feedback(payload: dict[str, Any]) -> str | None:
    """Texto para o agente, ou None se não há o que dizer."""
    raw = str((payload.get("tool_input") or {}).get("file_path") or "")
    if not raw.endswith(".py"):
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path(str(payload.get("cwd") or ".")) / path
    path = path.resolve()
    root = find_root(path)
    if root is None or not path.is_relative_to(root / "src") or not path.is_file():
        return None
    findings = _load_runner(root).findings_for([path], root=root)
    if not findings:
        return None
    rel = path.relative_to(root).as_posix()
    lines = [f"arch_feedback: {rel} — o `make check` vai reprovar (gates de make arch-ast):"]
    lines += [finding.render() for finding in findings]
    return "\n".join(lines)


def main() -> int:
    try:
        # `-sig`: o pipe do Windows PowerShell 5.1 prefixa BOM, que o `json.loads` recusa
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
        message = feedback(payload) if isinstance(payload, dict) else None
    except (Exception, SystemExit):  # fail open: baseline malformado, gate quebrado, JSON ruim
        return 0
    if message is None:
        return 0
    print(message, file=sys.stderr)
    return EXIT_FEEDBACK


if __name__ == "__main__":
    sys.exit(main())
