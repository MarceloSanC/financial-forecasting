"""Regressão de `scripts/arch_ast_lib.py` — resolução de nomes dos gates da onda 2 (#61).

Os gates `check_use_case_deps` e `check_domain_determinism` decidem em cima do nome
qualificado que esta lib devolve; um alias mal resolvido vira falso verde nos dois. Os
testes dos gates exercitam o caminho comum; aqui ficam as formas de import que eles não
cobrem uma a uma.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture
def lib() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_arch_ast_lib_under_test", _SCRIPTS / "arch_ast_lib.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("import os.path", {"os": "os"}, id="import-pontilhado-liga-a-cabeca"),
        pytest.param("import os.path as osp", {"osp": "os.path"}, id="import-com-alias"),
        pytest.param("from a.b import C as D", {"D": "a.b.C"}, id="from-com-alias"),
        pytest.param("from a.b import *", {}, id="estrela-ignorada"),
        pytest.param(
            "from . import sibling", {"sibling": "pkg.mod.sibling"}, id="relativo-sem-modulo"
        ),
        pytest.param("from ..x import Y", {"Y": "pkg.x.Y"}, id="relativo-dois-niveis"),
        pytest.param(
            "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from a import B\n",
            {"TYPE_CHECKING": "typing.TYPE_CHECKING", "B": "a.B"},
            id="aninhado-em-type-checking",
        ),
    ],
)
def test_import_aliases(lib: ModuleType, source: str, expected: dict[str, str]) -> None:
    assert lib.import_aliases(ast.parse(source), "pkg.mod.here") == expected


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        pytest.param("osp.join", "os.path.join", id="alias-na-cabeca"),
        pytest.param("local.attr", "local.attr", id="nome-sem-import"),
        pytest.param("f().attr", None, id="cadeia-que-parte-de-chamada"),
        pytest.param("xs[0].attr", None, id="cadeia-que-parte-de-subscrito"),
    ],
)
def test_qualified_name(lib: ModuleType, expr: str, expected: str | None) -> None:
    node = ast.parse(expr, mode="eval").body

    assert lib.qualified_name(node, {"osp": "os.path"}) == expected


def test_module_name_strips_init_and_suffix(lib: ModuleType, tmp_path: Path) -> None:
    src = tmp_path / "src"

    assert lib.module_name(src / "pkg" / "sub" / "mod.py", src) == "pkg.sub.mod"
    assert lib.module_name(src / "pkg" / "sub" / "__init__.py", src) == "pkg.sub"


def test_docstring_nodes_only_marks_first_string_of_each_scope(lib: ModuleType) -> None:
    tree = ast.parse(
        '"""m"""\nx = "lit"\nclass C:\n    """c"""\ndef f():\n    """f"""\n    "nao"\n'
    )

    marked = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and id(node) in lib.docstring_nodes(tree)
    }

    assert marked == {"m", "c", "f"}
