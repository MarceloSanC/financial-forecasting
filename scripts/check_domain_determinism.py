"""Gate de determinismo do domínio — sem relógio, acaso, ambiente nem I/O (issue #61).

Uso:
    python scripts/check_domain_determinism.py
    python scripts/check_domain_determinism.py --list   # imprime cada violação com as linhas

O que reprova, em qualquer módulo sob `*/domain/` (features e `shared/domain`):

- relógio: `datetime.now/utcnow/today`, `date.today`, `time.time/time_ns/monotonic/
  perf_counter`;
- identificador aleatório: `uuid.uuid1/uuid4`, qualquer `secrets.*`;
- acaso com estado GLOBAL: qualquer `random.<função>` do módulo (`random.random`,
  `random.choice`, `random.seed`…), `random.SystemRandom` e `random.Random()` SEM semente;
- sistema operacional: qualquer `os.*` (`os.environ`, `os.getenv`, `os.urandom`,
  `os.listdir`, `os.path.*`…), `shutil.*`, `subprocess.*`, `socket.*`, `tempfile.*`,
  `glob.*`;
- I/O de arquivo: `open`, `io.open` e `pathlib.Path` (a classe concreta lê e escreve:
  `Path(...).read_text()` é o `open` moderno). Caminho como valor puro usa
  `pathlib.PurePath`/`PurePosixPath`, que passam.

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
        "open",
        "io.open",
        "pathlib.Path",
        "random.SystemRandom",
    }
)
# Módulo inteiro: todo membro é acaso criptográfico (`secrets`) ou toca o sistema
# operacional — ambiente, `urandom`, sistema de arquivos, processo, rede.
FORBIDDEN_MODULES: tuple[str, ...] = (
    "secrets",
    "os",
    "shutil",
    "subprocess",
    "socket",
    "tempfile",
    "glob",
)
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


_FUNCTION_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _binds_open(scope: ast.AST) -> bool:
    """O escopo (módulo ou função) liga o nome `open` — parâmetro, `def`/`class`,
    import ou atribuição? O corpo de classe e as funções aninhadas são escopos próprios:
    o campo `open: float` de uma dataclass não sombreia o builtin para o resto do módulo."""
    body: list[ast.AST] = []
    if isinstance(scope, _FUNCTION_SCOPES):
        args = scope.args
        params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        params += [arg for arg in (args.vararg, args.kwarg) if arg is not None]
        if any(param.arg == "open" for param in params):
            return True
        body = [scope.body] if isinstance(scope, ast.Lambda) else list(scope.body)
    elif isinstance(scope, ast.Module):
        body = list(scope.body)
    stack = body
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == "open":
                return True
            continue
        if isinstance(node, ast.Lambda):
            continue
        if isinstance(node, ast.Name) and node.id == "open" and isinstance(node.ctx, ast.Store):
            return True
        if isinstance(node, ast.alias) and (node.asname or node.name) == "open":
            return True
        stack.extend(ast.iter_child_nodes(node))
    return False


def _builtin_open_loads(tree: ast.AST) -> set[int]:
    """`id()` dos `Name("open")` lidos que resolvem ao builtin, pelo escopo léxico: um
    parâmetro `open` numa função sombreia só dentro dela, não no módulo inteiro."""
    found: set[int] = set()

    def visit(node: ast.AST, shadowed: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _FUNCTION_SCOPES):
                visit(child, shadowed or _binds_open(child))
            elif (
                isinstance(child, ast.Name)
                and child.id == "open"
                and isinstance(child.ctx, ast.Load)
                and not shadowed
            ):
                found.add(id(child))
            else:
                visit(child, shadowed)

    visit(tree, _binds_open(tree))
    return found


def forbidden_uses(tree: ast.AST, module: str) -> dict[str, list[int]]:
    """`{nome qualificado proibido: linhas}` encontrados em `tree`."""
    aliases = _ast_lib.import_aliases(tree, module)
    open_loads = _builtin_open_loads(tree)
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
        # `open` sem import é o builtin — se lido (Load) num escopo que não o religa
        # (`open: float` de dataclass é Store; `def body(open, close)` sombreia só ali).
        builtin_open = head is node and id(node) in open_loads
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
