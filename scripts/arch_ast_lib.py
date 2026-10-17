"""Leitura AST compartilhada pelos gates de arquitetura da onda 2 (issue #61).

O import-linter raciocina sobre IMPORTS; os gates da #61 raciocinam sobre o que o
código FAZ com um nome importado — anotar um parâmetro, chamar `datetime.now`,
escrever um literal. Os dois primeiros precisam da mesma coisa: saber a que nome
qualificado um identificador local se refere. Este módulo é essa resolução, uma vez
só (o mesmo conhecimento em dois scripts seria o defeito que o `check_schema_literals`
reprova).

- `import_aliases(tree, module)`: `nome local → nome qualificado`, de `import a.b`,
  `import a.b as c`, `from a import b`, `from a import b as c` e imports relativos
  (resolvidos contra `module`). Imports sob `if TYPE_CHECKING:` entram (é onde a
  anotação de tipo costuma morar).
- `qualified_name(node, aliases)`: nome qualificado de um `Name`/`Attribute`
  (`dt.datetime.now` → `datetime.datetime.now`); `None` para o que não é cadeia de
  nomes (`f().x`, subscrito).
- `docstring_nodes(tree)`: as `Constant` que são docstring (módulo/classe/função).

Stdlib-only. `scripts/` não é pacote: os gates carregam este módulo por
`importlib.util.spec_from_file_location` relativo ao próprio `__file__`, como fazem
com `arch_baseline_lib.py`.
"""

from __future__ import annotations

import ast
from pathlib import Path


def module_name(path: Path, src_root: Path) -> str:
    """Nome de módulo de `path` relativo à raiz de pacotes (`src/`)."""
    parts = list(path.relative_to(src_root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def import_aliases(tree: ast.AST, module: str) -> dict[str, str]:
    """`nome local → nome qualificado` de todos os imports do módulo (inclusive aninhados)."""
    aliases: dict[str, str] = {}
    package = module.split(".")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
                else:  # `import a.b` liga só `a`
                    head = alias.name.split(".")[0]
                    aliases[head] = head
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - node.level]
                origin = ".".join([*base, node.module] if node.module else base)
            else:
                origin = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue
                aliases[alias.asname or alias.name] = f"{origin}.{alias.name}"
    return aliases


def qualified_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    """Nome qualificado de uma cadeia `a.b.c`; o primeiro elo passa pelos aliases."""
    attrs: list[str] = []
    while isinstance(node, ast.Attribute):
        attrs.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    head = aliases.get(node.id, node.id)
    return ".".join([head, *reversed(attrs)])


def docstring_nodes(tree: ast.AST) -> set[int]:
    """`id()` das `Constant` que são docstring de módulo, classe ou função."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(id(body[0].value))
    return found
