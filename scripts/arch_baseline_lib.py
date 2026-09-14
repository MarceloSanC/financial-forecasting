"""Baseline declarado dos gates de arquitetura (`scripts/arch_baseline.toml`) — issue #62.

Mecanismo compartilhado pelos scripts `check_fake_parity.py` e `check_port_coverage.py`
(onda 3 do plano de fitness functions; a onda 2, #61, ainda não entrou — este módulo é
o mínimo que os dois gates precisam, e nasce aqui para que #61 o reutilize):

- Cada gate tem uma seção `[[<gate>.allow]]` no TOML; cada entrada é uma violação
  CONHECIDA, com `motivo` (texto) e `issue` (inteiro, card real no GitHub) obrigatórios.
  Entrada sem `motivo` ou `issue` reprova — baseline sem dono é sedimento.
- Violação fora do baseline reprova (é o gate).
- Entrada do baseline que NÃO ocorre mais reprova ("baseline morto") — a lista
  encolhe sozinha em vez de virar permissão permanente (mesma postura do
  `unmatched_ignore_imports_alerting = error` do `.importlinter`).

A chave de identidade de cada entrada é específica do gate (`key` no TOML); o script
dono explica no seu docstring como a chave é montada.

Stdlib-only (`tomllib` é stdlib desde o 3.11). Importado pelos scripts via
`importlib` a partir de `scripts/`, como os demais helpers de gate.
"""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = ROOT / "scripts" / "arch_baseline.toml"


@dataclass(frozen=True)
class BaselineEntry:
    """Uma violação conhecida: chave do gate + motivo + issue."""

    key: str
    motivo: str
    issue: int


def load_baseline(gate: str, path: Path = BASELINE_PATH) -> dict[str, BaselineEntry]:
    """Lê as entradas `[[<gate>.allow]]`; entrada malformada é erro (exit 2)."""
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    section = data.get(gate, {})
    entries: dict[str, BaselineEntry] = {}
    for raw in section.get("allow", []):
        key = raw.get("key")
        motivo = raw.get("motivo")
        issue = raw.get("issue")
        if not isinstance(key, str) or not key:
            _fail(f"[{gate}] entrada sem `key`: {raw!r}")
        if not isinstance(motivo, str) or not motivo.strip():
            _fail(f"[{gate}] entrada {key!r} sem `motivo` — baseline sem dono é sedimento")
        if not isinstance(issue, int) or issue <= 0:
            _fail(f"[{gate}] entrada {key!r} sem `issue` (inteiro > 0, card real no GitHub)")
        if key in entries:
            _fail(f"[{gate}] chave duplicada no baseline: {key!r}")
        entries[key] = BaselineEntry(key=key, motivo=motivo, issue=issue)
    return entries


def reconcile(
    gate: str, violations: dict[str, str], baseline: dict[str, BaselineEntry]
) -> tuple[list[str], list[str]]:
    """Cruza violações medidas x baseline.

    Devolve `(novas, mortas)`: violações fora do baseline (reprovam) e entradas do
    baseline que não ocorrem mais (reprovam — remover a linha do TOML).
    """
    new = [f"{key}: {detail}" for key, detail in violations.items() if key not in baseline]
    dead = [
        f"{key} (motivo: {entry.motivo}; issue #{entry.issue})"
        for key, entry in baseline.items()
        if key not in violations
    ]
    return new, dead


def report(gate: str, new: list[str], dead: list[str], tolerated: int) -> int:
    """Imprime o veredito e devolve o exit code (0 ok / 1 violação)."""
    if not new and not dead:
        suffix = f" ({tolerated} no baseline)" if tolerated else ""
        print(f"[{gate}] PASSOU — nenhuma violação nova{suffix}.")
        return 0
    if new:
        print(f"[{gate}] REPROVOU — {len(new)} violação(ões) fora do baseline:")
        for line in new:
            print(f"  - {line}")
    if dead:
        print(
            f"[{gate}] REPROVOU — {len(dead)} entrada(s) do baseline que não ocorrem mais "
            "(remover):"
        )
        for line in dead:
            print(f"  - {line}")
    return 1


def _fail(message: str) -> None:
    print(f"arch_baseline: {message}", file=sys.stderr)
    sys.exit(2)
