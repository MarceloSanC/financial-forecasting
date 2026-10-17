"""Gate de colaboradores de use case — `__init__` só recebe abstrações (issue #61).

Uso:
    python scripts/check_use_case_deps.py
    python scripts/check_use_case_deps.py --list    # imprime cada violação com o tipo anotado

O que reprova: parâmetro do `__init__` de uma classe definida em
`features/<slice>/application/use_cases/*.py` (numa `@dataclass` sem `__init__` explícito,
os campos anotados — o `__init__` gerado os recebe) cuja anotação cita

- um tipo definido em `application/use_cases/` de OUTRO slice — comportamento de outro
  slice entra por port definido no consumidor (LAYOUT §7, ADR 0.0.0053); o use case
  alheio satisfaz esse port por duck-typing no composition root, nunca na assinatura;
- uma classe de `adapters/` (de qualquer slice ou de `shared/adapters/`) ou de
  `shared/infrastructure/` — o use case depende do port, o concreto é escolhido no
  composition root (LAYOUT §6; "BOTH SHOULD DEPEND UPON ABSTRACTIONS", Martin, *The
  Dependency Inversion Principle*, C++ Report 1996, p.6).

O import-linter não pega o caso: ele vê o import, mas um import sob `if TYPE_CHECKING:`
é invisível ao contrato e nada exige que o colaborador seja um `Protocol`.

O que NÃO reprova, por desenho: serviço de domínio concreto (`WalkForwardSplitter`,
`DatasetQualityGate`, `FundamentalsAsofPolicy`) — puro, sem I/O, estável; é a dependência
que a regra de dependência permite (application → domain). Também não reprova use case do
MESMO slice (`BuildDataset` ← `ScoreAndAggregateSentiment`): a fronteira guardada aqui é a
entre slices. A exceção que a issue #61 previa para o `WalkForwardSplitter` fica assim
desnecessária: domínio não é nenhuma das duas categorias proibidas.

Resolução: cada nome da anotação (inclusive dentro de `Callable[...]`, `X | None` e
anotação em string) é resolvido pelos imports do módulo (`scripts/arch_ast_lib.py`) até o
nome qualificado de definição; o slice e a camada saem desse caminho. Reexport por
`__init__.py` de pacote (`...use_cases import X`) ainda carrega o caminho
`application.use_cases` e é pego.

Baseline: `scripts/arch_baseline.toml`, seção `[use_case_deps]`, entradas
`[[use_case_deps.allow]]` com `key = "<arquivo rel>::<Classe>.__init__(<param>)"`,
`motivo` e `issue` (mecanismo em `scripts/arch_baseline_lib.py`).

Exit codes: 0 sem violação nova; 1 violação nova ou baseline morto; 2 baseline malformado.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = ROOT / "src"
PACKAGE = "financial_forecasting"
GATE = "use_case_deps"


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


def forbidden_reason(qualified: str, own_slice: str) -> str | None:
    """Por que o tipo `qualified` não pode anotar colaborador de use case de `own_slice`."""
    parts = qualified.split(".")
    if not parts or parts[0] != PACKAGE:
        return None
    if "adapters" in parts or parts[1:3] == ["shared", "infrastructure"]:
        return "classe concreta de adapter/infraestrutura"
    if (
        len(parts) > 4  # noqa: PLR2004 — financial_forecasting.features.<slice>.application.use_cases
        and parts[1] == "features"
        and parts[3:5] == ["application", "use_cases"]
        and parts[2] != own_slice
    ):
        return f"use case do slice `{parts[2]}`"
    return None


def _annotation_names(annotation: ast.expr, aliases: dict[str, str]) -> list[str]:
    """Nomes qualificados citados numa anotação (recursivo em subscrito, união e string)."""
    found: list[str] = []
    for node in ast.walk(annotation):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                parsed = ast.parse(node.value, mode="eval")
            except SyntaxError:
                continue
            found.extend(_annotation_names(parsed.body, aliases))
        elif isinstance(node, (ast.Name, ast.Attribute)):
            name = _ast_lib.qualified_name(node, aliases)
            if name is not None:
                found.append(name)
    return found


def _use_case_slice(path: Path, src_root: Path) -> str | None:
    parts = path.relative_to(src_root).parts
    if (
        len(parts) > 5  # noqa: PLR2004 — financial_forecasting/features/<s>/application/use_cases/x.py
        and parts[0] == PACKAGE
        and parts[1] == "features"
        and parts[3:5] == ("application", "use_cases")
    ):
        return parts[2]
    return None


def scan(*, src_root: Path = SRC_ROOT, root: Path = ROOT) -> dict[str, str]:
    """`{chave: detalhe}` de todo parâmetro de `__init__` de use case em violação."""
    violations: dict[str, str] = {}
    for path in sorted((src_root / PACKAGE).rglob("*.py")):
        own_slice = _use_case_slice(path, src_root)
        if own_slice is None:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = _ast_lib.import_aliases(tree, _ast_lib.module_name(path, src_root))
        rel = path.relative_to(root).as_posix()
        for cls in (node for node in tree.body if isinstance(node, ast.ClassDef)):
            for param_name, annotation in _constructor_params(cls):
                for name in _annotation_names(annotation, aliases):
                    reason = forbidden_reason(name, own_slice)
                    if reason is not None:
                        key = f"{rel}::{cls.name}.__init__({param_name})"
                        violations[key] = f"anota `{name}` ({reason}), L{annotation.lineno}"
                        break
    return violations


def _constructor_params(cls: ast.ClassDef) -> list[tuple[str, ast.expr]]:
    """`(nome, anotação)` dos parâmetros do construtor: `__init__` explícito ou, numa
    `@dataclass` sem ele, os campos anotados do corpo (o `__init__` gerado os recebe)."""
    params: list[tuple[str, ast.expr]] = []
    for init in cls.body:
        if isinstance(init, ast.FunctionDef) and init.name == "__init__":
            args = init.args
            every = [*args.posonlyargs, *args.args, *args.kwonlyargs]
            every += [arg for arg in (args.vararg, args.kwarg) if arg is not None]
            params += [(arg.arg, arg.annotation) for arg in every if arg.annotation is not None]
            return params
    if any(_is_dataclass_decorator(d) for d in cls.decorator_list):
        params += [
            (stmt.target.id, stmt.annotation)
            for stmt in cls.body
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
        ]
    return params


def _is_dataclass_decorator(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
    return name == "dataclass"


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
