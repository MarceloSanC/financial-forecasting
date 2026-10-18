"""Executor fino dos gates AST de arquitetura só sobre os arquivos alterados (issue #161).

Uso (stdlib only — roda no host, sem venv):
    python .claude/skills/architecture-fitness/scripts/check_changed.py <arquivo.py> [...]
    python .claude/skills/architecture-fitness/scripts/check_changed.py          # vs origin/develop
    python .claude/skills/architecture-fitness/scripts/check_changed.py --base origin/main

Sem arquivos, usa `git diff --name-only <base>` (commitado + não commitado) e os não
rastreados; entra só `.py` sob `src/`.

Roda OS MESMOS gates de `scripts/` (raiz): importa cada `check_*.py`, chama o `scan()`
dele e cruza com o baseline pelo `reconcile()` de `scripts/arch_baseline_lib.py`. Não há
regra aqui — copiar a lógica de um gate seria a duplicação que o `check_schema_literals`
reprova (ADR 0.0.0058 item 3). O filtro por arquivo funciona porque toda chave desses
gates começa com `<arquivo rel>::`. O custo é o da varredura inteira (~1 s nos quatro).

Também é a implementação do hook `.claude/hooks/arch_feedback.py` (PostToolUse).

Achados:
- violação fora do baseline num arquivo alterado (o `make check` vai reprovar);
- entrada do baseline de um arquivo alterado que não ocorre mais (baseline morto — o
  `make check` também reprova; remover a entrada de `scripts/arch_baseline.toml`).

Exit codes: 0 nenhum achado; 1 achados; 2 baseline malformado (o gate já reporta).
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

# Os gates de `make arch-ast`, na ordem do Makefile (um teste compara as duas listas).
GATES: tuple[str, ...] = (
    "check_use_case_deps",
    "check_domain_determinism",
    "check_schema_literals",
    "check_vo_invariants",
)
# Gate → reference/ da skill que explica a regra e a correção (apresentação, não regra).
REFERENCE: dict[str, str] = {
    "use_case_deps": "dependency-rule.md",
    "domain_determinism": "domain-purity.md",
    "schema_literals": "schema-knowledge.md",
    "vo_invariants": "value-object-invariants.md",
}
SKILL_DIR = Path(__file__).resolve().parent.parent
BASELINE_REL = Path("scripts") / "arch_baseline.toml"


@dataclass(frozen=True)
class Finding:
    """Um achado de um gate num arquivo alterado."""

    gate: str
    dead: bool  # True = entrada do baseline que não ocorre mais
    text: str  # linha do `reconcile()`: `<chave>: <detalhe>` ou `<chave> (motivo: …)`

    def render(self) -> str:
        ref = SKILL_DIR / "reference" / REFERENCE.get(self.gate, "")
        if self.dead:
            head = f"[{self.gate}] baseline morto — remova a entrada de {BASELINE_REL.as_posix()}"
            return f"{head}: {self.text}"
        return f"[{self.gate}] {self.text}\n  regra e correção: {ref.as_posix()}"


def find_root(start: Path) -> Path | None:
    """Raiz do repo (ou da worktree) que contém `start`: o ancestral com o baseline."""
    for candidate in (start, *start.parents):
        if (candidate / BASELINE_REL).is_file():
            return candidate
    return None


def _load(scripts_dir: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"_arch_changed_{name}", scripts_dir / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses com annotations adiadas precisam disto
    spec.loader.exec_module(module)
    return module


def _scan_kwargs(gate: ModuleType, root: Path) -> dict[str, Path]:
    """Os defaults `Path` do `scan()` do gate (`root`, `src_root`, `scope`…) realocados
    de `gate.ROOT` para `root` — sem saber o que cada gate varre."""
    kwargs: dict[str, Path] = {}
    for name, param in inspect.signature(gate.scan).parameters.items():
        default = param.default
        if isinstance(default, Path) and default.is_relative_to(gate.ROOT):
            kwargs[name] = root / default.relative_to(gate.ROOT)
    return kwargs


def _relative(paths: list[Path], root: Path) -> set[str]:
    rels: set[str] = set()
    for path in paths:
        resolved = (path if path.is_absolute() else root / path).resolve()
        if resolved.is_relative_to(root.resolve()):
            rels.add(resolved.relative_to(root.resolve()).as_posix())
    return rels


def findings_for(
    paths: list[Path], *, root: Path, scripts_dir: Path | None = None
) -> list[Finding]:
    """Achados dos gates AST restritos a `paths` (absolutos ou relativos a `root`)."""
    rels = _relative(paths, root)
    if not rels:
        return []
    scripts = scripts_dir or root / "scripts"
    lib = _load(scripts, "arch_baseline_lib")
    found: list[Finding] = []
    for name in GATES:
        gate = _load(scripts, name)
        violations = gate.scan(**_scan_kwargs(gate, root))
        baseline = lib.load_baseline(gate.GATE, root / BASELINE_REL)
        new, dead = lib.reconcile(violations, baseline)
        for text, is_dead in [*((t, False) for t in new), *((t, True) for t in dead)]:
            if text.split("::", 1)[0] in rels:
                found.append(Finding(gate=gate.GATE, dead=is_dead, text=text))
    return found


def changed_files(root: Path, base: str) -> list[Path]:
    """`.py` sob `src/` alterados vs `base` (inclui não commitados e não rastreados)."""

    def git(*args: str) -> list[str]:
        out = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True
        ).stdout
        return [line for line in out.splitlines() if line]

    names = {*git("diff", "--name-only", base), *git("ls-files", "--others", "--exclude-standard")}
    return [
        root / name
        for name in sorted(names)
        if name.startswith("src/") and name.endswith(".py") and (root / name).is_file()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("paths", nargs="*", type=Path, help="arquivos a checar")
    parser.add_argument("--base", default="origin/develop", help="base do diff sem arquivos")
    args = parser.parse_args(argv)

    root = find_root(Path.cwd().resolve()) or find_root(SKILL_DIR)
    if root is None:
        print("check_changed: raiz do repo não encontrada", file=sys.stderr)
        return 2
    # relativo ao cwd, como no shell: o `findings_for` resolve relativo contra a raiz, e
    # rodar de uma subpasta descartava o arquivo calado (0 achados = falso limpo)
    paths = [Path.cwd() / p for p in args.paths] or changed_files(root, args.base)
    found = findings_for(paths, root=root)
    for finding in found:
        print(finding.render())
    print(f"check_changed: {len(paths)} arquivo(s), {len(found)} achado(s)", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
