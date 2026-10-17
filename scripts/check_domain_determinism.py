"""Gate de determinismo do domínio — sem relógio, acaso, ambiente nem I/O (issue #61).

Uso:
    python scripts/check_domain_determinism.py
    python scripts/check_domain_determinism.py --list   # imprime cada violação com as linhas

O que reprova, em qualquer módulo sob `*/domain/` (features e `shared/domain`):

- relógio: `datetime.now/utcnow/today`, `date.today`, `time.time/time_ns/monotonic/
  perf_counter`;
- identificador aleatório: `uuid.uuid1/uuid4`, `os.urandom`, qualquer `secrets.*`;
- acaso com estado GLOBAL: qualquer `random.<função>` do módulo (`random.random`,
  `random.choice`, `random.seed`…), `random.SystemRandom` e `random.Random()` SEM semente;
- ambiente: `os.environ`, `os.getenv`;
- I/O de arquivo: `open`, `io.open`.

Por quê: o domínio é o núcleo puro — "eliminate any dependency on infrastructure" (Evans,
*DDD Reference*, 2015, LAYERED ARCHITECTURE, p.17) e "functions, operations that return
results with no observable side effects" (idem, SIDE-EFFECT-FREE FUNCTIONS, p.28). Tempo
entra pelo port `Clock` (ADR 4.2.0002), arquivo e ambiente pelos adapters. Esta é a classe
de apodrecimento que a ADR 1.3.0001 descreve no repo antigo; o import-linter não a vê,
porque `datetime`/`random`/`os` são stdlib e o domínio pode importar stdlib.

O que NÃO reprova, por desenho: `random.Random(seed)` com semente explícita — gerador
local, reprodutível, sem estado global (é o que o teste de Christoffersen usa para a
simulação Monte Carlo). A biblioteca `random` do Haskell faz a mesma distinção: gerador
passado explicitamente é puro; o global "in presence of concurrency [is] naturally
non-deterministic" (`random-1.3.1`, System.Random, §Global standard pseudo-random number
generator). Também não reprova a mera menção do tipo (`rng: random.Random`).

Resolução: aliases de import (`from datetime import datetime as dt` → `dt.now()` é
`datetime.datetime.now`) via `scripts/arch_ast_lib.py`. Um nome rebatizado sem import
(`agora = datetime.now; agora()`) é pego na atribuição, que já cita o nome proibido.

Baseline: `scripts/arch_baseline.toml`, seção `[domain_determinism]`, entradas
`[[domain_determinism.allow]]` com `key = "<arquivo rel>::<nome qualificado>"`, `motivo` e
`issue` (mecanismo em `scripts/arch_baseline_lib.py`).

Exit codes: 0 sem violação nova; 1 violação nova ou baseline morto; 2 baseline malformado.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = ROOT / "src"
PACKAGE = "financial_forecasting"
GATE = "domain_determinism"

FORBIDDEN: frozenset[str] = frozenset(
    {
        "datetime.datetime.now",
        "datetime.datetime.utcnow",
        "datetime.datetime.today",
        "datetime.date.today",
        "time.time",
        "time.time_ns",
        "time.monotonic",
        "time.perf_counter",
        "uuid.uuid1",
        "uuid.uuid4",
        "os.urandom",
        "os.environ",
        "os.getenv",
        "open",
        "io.open",
        "random.SystemRandom",
    }
)
FORBIDDEN_MODULES: tuple[str, ...] = ("secrets",)
_SEEDED_RNG = "random.Random"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"_{name}", Path(__file__).resolve().parent / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses com annotations adiadas precisam disto
    spec.loader.exec_module(module)
    return module


_ast_lib = _load("arch_ast_lib")


def is_forbidden(name: str) -> bool:
    """`name` (qualificado) é fonte de não-determinismo proibida no domínio?"""
    if name in FORBIDDEN:
        return True
    head, _, attr = name.partition(".")
    if head in FORBIDDEN_MODULES and attr:
        return True
    # `random.<função>` do módulo usa o gerador global; `random.Random` é a classe.
    return head == "random" and bool(attr) and "." not in attr and name != _SEEDED_RNG


def _binds_open(tree: ast.AST) -> bool:
    """O módulo liga o nome `open` (parâmetro, `def`, atribuição a nome solto)?"""
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.arg == "open":
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "open":
            return True
        if (
            isinstance(node, ast.Name)
            and node.id == "open"
            and isinstance(node.ctx, ast.Store)
            and not _is_class_field(tree, node)
        ):
            return True
    return False


def _is_class_field(tree: ast.AST, name: ast.Name) -> bool:
    """`name` é alvo de uma atribuição direta no corpo de uma classe (campo/atributo)?"""
    for cls in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
        for stmt in cls.body:
            targets: list[ast.expr] = []
            if isinstance(stmt, ast.AnnAssign):
                targets = [stmt.target]
            elif isinstance(stmt, ast.Assign):
                targets = stmt.targets
            if any(target is name for target in targets):
                return True
    return False


def forbidden_uses(tree: ast.AST, module: str) -> dict[str, list[int]]:
    """`{nome qualificado proibido: linhas}` encontrados em `tree`."""
    aliases = _ast_lib.import_aliases(tree, module)
    open_shadowed = _binds_open(tree)
    found: dict[str, list[int]] = defaultdict(list)
    chain_members: set[int] = set()  # elos internos de `a.b.c` já avaliados pela cadeia
    for node in ast.walk(tree):
        if id(node) in chain_members:
            continue
        if isinstance(node, ast.Call):
            callee = _ast_lib.qualified_name(node.func, aliases)
            if callee == _SEEDED_RNG and not node.args and not node.keywords:
                found[f"{_SEEDED_RNG}()"].append(node.lineno)
            continue
        if not isinstance(node, (ast.Name, ast.Attribute)):
            continue
        head: ast.AST = node
        while isinstance(head, ast.Attribute):
            head = head.value
            chain_members.add(id(head))
        if not isinstance(head, ast.Name):
            continue
        # `open` sem import é o builtin — se lido (Load) e não religado no módulo
        # (`open: float` de dataclass é Store; `def body(open, close)` sombreia).
        builtin_open = (
            head is node
            and node.id == "open"
            and isinstance(node.ctx, ast.Load)
            and not open_shadowed
        )
        if head.id not in aliases and not builtin_open:
            continue  # cadeia que parte de variável local / parâmetro, não de nome importado
        name = _ast_lib.qualified_name(node, aliases)
        if name is None:
            continue
        # Cada prefixo da cadeia conta: `os.environ.get` é uso de `os.environ`.
        parts = name.split(".")
        for size in range(1, len(parts) + 1):
            prefix = ".".join(parts[:size])
            if is_forbidden(prefix):
                found[prefix].append(node.lineno)
                break
    return dict(found)


def scan(*, src_root: Path = SRC_ROOT, root: Path = ROOT) -> dict[str, str]:
    """`{chave: detalhe}` de todo uso proibido sob `*/domain/`."""
    violations: dict[str, str] = {}
    for path in sorted((src_root / PACKAGE).rglob("*.py")):
        if "domain" not in path.relative_to(src_root).parts[:-1]:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        uses = forbidden_uses(tree, _ast_lib.module_name(path, src_root))
        rel = path.relative_to(root).as_posix()
        for name, lines in sorted(uses.items()):
            violations[f"{rel}::{name}"] = "linhas " + ", ".join(f"L{n}" for n in lines)
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", action="store_true", help="lista as violações (diagnóstico)")
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
