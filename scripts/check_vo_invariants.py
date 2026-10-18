"""Gate de invariantes de value object — VO congelado valida na construção (issue #61).

Uso:
    python scripts/check_vo_invariants.py
    python scripts/check_vo_invariants.py --list   # imprime cada VO em violação

O que reprova: classe `@dataclass(frozen=True)` (ou `@dataclasses.dataclass(frozen=True)`)
definida em `domain/value_objects/*.py` sem `__post_init__` — próprio ou herdado de uma
base definida no mesmo módulo.

Por quê: o VO é imutável e não tem identidade; o que o distingue de uma tupla nomeada é
carregar a invariante do valor ("State post-conditions of operations and invariants of
classes and aggregates." — Evans, *DDD Reference*, 2015, ASSERTIONS, p.29). Se a
invariante não é checada ao construir, todo consumidor precisa revalidar ou confiar.

Por que só `__post_init__` (e não "factory validadora"): validar numa factory só garante a
invariante se o caminho cru for fechado — Wlaschin: "If you really want to encapsulate the
internals of the type and force callers to use a constructor function, you can use module
signatures." (*Designing with types: Single case union types*, §Forcing use of the
constructor). Em Python o construtor da dataclass é sempre chamável; uma `from_raw`/
`compute` que valida deixa `Cls(value=...)` aceitar qualquer coisa. Decisão da sessão da
#61 (a issue previa aceitar factory).

Opt-out (VO sem invariante POR DESENHO): comentário `# vo-invariant: none — <motivo>` numa
linha entre a anterior ao primeiro decorador e a linha do `class`. Marcador sem motivo
reprova. Débito (VO que DEVERIA validar e não valida) vai para o baseline, não para o
marcador.

Baseline: `scripts/arch_baseline.toml`, seção `[vo_invariants]`, entradas
`[[vo_invariants.allow]]` com `key = "<arquivo rel>::<Classe>"`, `motivo` e `issue`
(mecanismo em `scripts/arch_baseline_lib.py`). A dívida medida na #61 (10 VOs) foi
zerada pela #160: o baseline está vazio.

Exit codes: 0 sem violação nova; 1 violação nova ou baseline morto; 2 baseline malformado.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = ROOT / "src" / "financial_forecasting"
GATE = "vo_invariants"

_MARKER = re.compile(r"#\s*vo-invariant:\s*none\b\s*(?:[\u2014\u2013:-]\s*)?(?P<motivo>.*)$")


def _is_frozen_dataclass(decorator: ast.expr) -> bool:
    if not isinstance(decorator, ast.Call):
        return False  # `@dataclass` puro não é frozen
    func = decorator.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if name != "dataclass":
        return False
    return any(
        keyword.arg == "frozen"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in decorator.keywords
    )


def _defines_post_init(cls: ast.ClassDef) -> bool:
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__post_init__"
        for node in cls.body
    )


def _marker(cls: ast.ClassDef, lines: list[str]) -> str | None:
    """Motivo do opt-out (`""` se marcador sem motivo; `None` se não há marcador)."""
    first = min([cls.lineno, *(d.lineno for d in cls.decorator_list)])
    for number in range(max(first - 1, 1), cls.lineno + 1):
        match = _MARKER.search(lines[number - 1])
        if match:
            return match.group("motivo").strip()
    return None


def vo_violations(source: str) -> dict[str, str]:
    """`{Classe: motivo da violação}` para os VOs congelados de `source`."""
    tree = ast.parse(source)
    lines = source.splitlines()
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    found: dict[str, str] = {}
    for cls in classes.values():
        if not any(_is_frozen_dataclass(d) for d in cls.decorator_list):
            continue
        bases = [classes.get(getattr(base, "id", "")) for base in cls.bases]
        if _defines_post_init(cls) or any(b is not None and _defines_post_init(b) for b in bases):
            continue
        motivo = _marker(cls, lines)
        if motivo is None:
            found[cls.name] = f"sem __post_init__ (L{cls.lineno})"
        elif not motivo:
            found[cls.name] = f"marcador vo-invariant sem motivo (L{cls.lineno})"
    return found


def scan(*, src_root: Path = SRC_ROOT, root: Path = ROOT) -> dict[str, str]:
    """`{chave: detalhe}` de todo VO congelado sem invariante sob `domain/value_objects/`."""
    violations: dict[str, str] = {}
    for path in sorted(src_root.rglob("*.py")):
        if path.parent.name != "value_objects" or path.parent.parent.name != "domain":
            continue
        rel = path.relative_to(root).as_posix()
        for name, detail in vo_violations(path.read_text(encoding="utf-8")).items():
            violations[f"{rel}::{name}"] = detail
    return violations


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"_{name}", Path(__file__).resolve().parent / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses com annotations adiadas precisam disto
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", action="store_true", help="lista os VOs em violação")
    args = parser.parse_args()

    violations = scan()
    if args.list:
        for key, detail in violations.items():
            print(f"{key}: {detail}")
    lib = _load("arch_baseline_lib")
    baseline = lib.load_baseline(GATE)
    new, dead = lib.reconcile(violations, baseline)
    return int(lib.report(GATE, new, dead, len(baseline)))


if __name__ == "__main__":
    sys.exit(main())
