"""Gate de literais de schema — coordenadas do dataset TFT com dono único (issue #61).

Uso:
    python scripts/check_schema_literals.py
    python scripts/check_schema_literals.py --list   # imprime cada ocorrência com as linhas

O que reprova: um literal string EXATAMENTE igual a `"processed"`, `"dataset_tft"` ou
`"target_return"` em código (docstring não conta) sob `features/modeling/application/`.
São as coordenadas do par read-only do dataset TFT no `MedallionStore` e a coluna-alvo:
hoje cada use case do modeling redeclara as três como constante local, e um rename do par
ou da coluna exige editar todos — esquecer um é silencioso. "Every piece of knowledge must
have a single, unambiguous, authoritative representation within a system." (Hunt & Thomas,
*The Pragmatic Programmer*, 20th anniv., Tip 15); o módulo se organiza pela decisão que
esconde: "Every module in the second decomposition is characterized by its knowledge of a
design decision which it hides from all others." (Parnas 1972, p.1056, §The Criteria,
doi:10.1145/361598.361623; a prescrição equivalente da p.1058, §Conclusion, é a que a skill
`architecture-fitness` cita).

Perímetro estreito de propósito (issue #61, correção pós-verificação):

- `"processed"` entra no lugar de `"time_idx"`: é o literal que de fato se repete nos use
  cases; `"time_idx"` aparece num só (`train_gbm_quantile`) e não tem dono a consolidar.
- `"timestamp"` NÃO entra: é legítimo em `build_dataset`/`ingest_candles`, que falam do
  schema da bronze — um gate largo aqui daria falso-vermelho e morreria.
- só `features/modeling/application/`: o produtor do dataset (`feature_engineering`) é o
  dono natural desses nomes.

Baseline: `scripts/arch_baseline.toml`, seção `[schema_literals]`, entradas
`[[schema_literals.allow]]` com `key = '<arquivo rel>::"<literal>"'`, `motivo` e `issue`
(mecanismo em `scripts/arch_baseline_lib.py`). A dívida de hoje aponta para a #159.

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
SCOPE = ROOT / "src" / "financial_forecasting" / "features" / "modeling" / "application"
FORBIDDEN_LITERALS: frozenset[str] = frozenset({"processed", "dataset_tft", "target_return"})
GATE = "schema_literals"


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


def forbidden_literals(tree: ast.AST) -> dict[str, list[int]]:
    """`{literal proibido: linhas}` em código de `tree` (docstrings descartadas)."""
    docstrings = _ast_lib.docstring_nodes(tree)
    found: dict[str, list[int]] = defaultdict(list)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in FORBIDDEN_LITERALS
            and id(node) not in docstrings
        ):
            found[node.value].append(node.lineno)
    return dict(found)


def scan(*, scope: Path = SCOPE, root: Path = ROOT) -> dict[str, str]:
    """`{chave: detalhe}` de todo literal proibido sob `scope`."""
    violations: dict[str, str] = {}
    for path in sorted(scope.rglob("*.py")):
        found = forbidden_literals(ast.parse(path.read_text(encoding="utf-8")))
        rel = path.relative_to(root).as_posix()
        for literal, lines in sorted(found.items()):
            violations[f'{rel}::"{literal}"'] = "linhas " + ", ".join(f"L{n}" for n in lines)
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", action="store_true", help="lista as ocorrências (diagnóstico)")
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
