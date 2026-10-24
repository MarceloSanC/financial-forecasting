"""A evidência anterior nunca é entrada oficial (Stage 8.2, Task 08; concept I7, A14).

Pela AST de todo módulo de `src/financial_forecasting/` (um nome em comentário não conta):
nenhum `import`/`from` de `tests` (o andaime de `tests/equivalence/` incluído), nenhum nome
de módulo `tests`/`tests.*` como texto (import dinâmico, CC3-4) e nenhum
literal de texto com `data/analytics` ou `phase_b` (a raiz e o cohort da evidência
anterior). O contrato `src-no-tests` do `import-linter` (Task 09) espelha a parte de import.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[2] / "src" / "financial_forecasting"
_FORBIDDEN_LITERALS = ("data/analytics", "phase_b")
_FORBIDDEN_PACKAGE = "tests"


def isolation_violations(source: str, *, name: str) -> list[str]:
    """As violações de isolamento de um módulo: import de `tests` ou literal proibido."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source, filename=name)):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules = [node.module]
        found += [
            f"{name}:{node.lineno} imports {module}"  # type: ignore[attr-defined]
            for module in modules
            if module == _FORBIDDEN_PACKAGE or module.startswith(f"{_FORBIDDEN_PACKAGE}.")
        ]
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found += [
                f"{name}:{node.lineno} literal {literal!r}"
                for literal in _FORBIDDEN_LITERALS
                if literal in node.value
            ]
            # CC3-4: import dinâmico (`importlib.import_module("tests...")`, `__import__`)
            # escapa do import-linter; o nome do pacote como texto denuncia
            text = node.value
            if text == _FORBIDDEN_PACKAGE or text.startswith(f"{_FORBIDDEN_PACKAGE}."):
                found.append(f"{name}:{node.lineno} module-name {text!r}")
    return found


def test_no_src_module_reads_prior_evidence_or_imports_the_scaffold() -> None:
    modules = sorted(_SRC.rglob("*.py"))
    assert modules

    found = [
        violation
        for path in modules
        for violation in isolation_violations(
            path.read_text(encoding="utf-8"), name=path.relative_to(_SRC).as_posix()
        )
    ]

    assert found == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import tests.equivalence.prior_evidence\n", "imports tests.equivalence.prior_evidence"),
        ("from tests.equivalence import readers\n", "imports tests.equivalence"),
        ("import tests\n", "imports tests"),
        ('ROOT = "data/analytics/gold"\n', "literal 'data/analytics'"),
        ('COHORT = f"phase_b_{x}"\n', "literal 'phase_b'"),
        (
            'importlib.import_module("tests.equivalence.readers")\n',
            "module-name 'tests.equivalence.readers'",
        ),
        ('__import__("tests")\n', "module-name 'tests'"),
    ],
)
def test_isolation_detector_flags_violations(source: str, expected: str) -> None:
    assert [item.split(" ", 1)[1] for item in isolation_violations(source, name="m.py")] == [
        expected
    ]


@pytest.mark.parametrize(
    "source",
    [
        "import testsuite\n",
        "from .tests import x\n",
        "# data/analytics only in a comment\nx = 1\n",
        'x = "data/analytic"\n',
        'x = "tests are good"\n',
        'x = "testsuite.module"\n',
    ],
)
def test_isolation_detector_ignores_non_violations(source: str) -> None:
    assert isolation_violations(source, name="m.py") == []
