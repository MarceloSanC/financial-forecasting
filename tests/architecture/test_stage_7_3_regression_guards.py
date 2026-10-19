"""Guardas de regressão da Stage 7.3 — o que o import-linter não vê.

Os dois executores de cohort (`run_confirmatory_cohort` e `run_ablation_cohort`)
compartilham a máquina de unidades de `cohort_unit_runner` e nunca importam um ao outro
(concept 7.3 D7; ADR 7.3.0003 item 3). O import-linter não cobre o caso: os dois
estão no mesmo slice e na mesma camada, e imports sob `TYPE_CHECKING` são invisíveis a
ele. A guarda lê o AST e acusa as três formas: `from … import …`, `import …` (inclusive
sob `if TYPE_CHECKING:`) e `importlib.import_module("…")` com constante.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[2]
_USE_CASES = _REPO / "src/financial_forecasting/features/modeling/application/use_cases"
_PACKAGE = "financial_forecasting.features.modeling.application.use_cases"
_CONFIRMATORY = f"{_PACKAGE}.run_confirmatory_cohort"
_ABLATION = f"{_PACKAGE}.run_ablation_cohort"
_RUNNER = f"{_PACKAGE}.cohort_unit_runner"


def _absolute(module: str | None, level: int, package: str) -> str:
    """O nome absoluto de um `from` relativo, resolvido contra `package` (C2-5)."""
    if level == 0:
        return module or ""
    parts = package.split(".")
    base = ".".join(parts[: len(parts) - (level - 1)])
    return f"{base}.{module}" if module else base


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _constant_target(node: ast.Call) -> str | None:
    """O módulo constante de `import_module(...)`/`__import__(...)`, posicional ou `name=`."""
    candidates = [*node.args[:1], *(kw.value for kw in node.keywords if kw.arg == "name")]
    for candidate in candidates:
        if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
            return candidate.value
    return None


def imported_modules(source: str, *, package: str = _PACKAGE) -> set[str]:
    """Módulos importados por qualquer forma (absoluta, relativa ou dinâmica).

    `from pacote import modulo` conta como `pacote.modulo` (o nome pode ser um
    submódulo), além do próprio `pacote`. `from . import x` e `from .x import y` são
    resolvidos contra `package` (o pacote dos executores). `importlib.import_module` e
    `__import__` com o nome constante, posicional ou `name=`, também contam.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module = _absolute(node.module, node.level, package)
            found.add(module)
            found.update(f"{module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call) and _call_name(node) in {"import_module", "__import__"}:
            target = _constant_target(node)
            if target is not None:
                found.add(target)
    return found


def _imports(path: Path) -> set[str]:
    return imported_modules(path.read_text(encoding="utf-8"))


def test_cohort_runners_never_import_each_other() -> None:
    confirmatory = _imports(_USE_CASES / "run_confirmatory_cohort.py")
    ablation = _imports(_USE_CASES / "run_ablation_cohort.py")

    assert _ABLATION not in confirmatory
    assert _CONFIRMATORY not in ablation
    assert _RUNNER in confirmatory
    assert _RUNNER in ablation


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(f"from {_CONFIRMATORY} import tft_train_command\n", id="from-module"),
        pytest.param(f"from {_PACKAGE} import run_confirmatory_cohort\n", id="from-package"),
        pytest.param(f"import {_CONFIRMATORY} as other\n", id="import"),
        pytest.param(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            f"    from {_CONFIRMATORY} import RunConfirmatoryCohort\n",
            id="type-checking",
        ),
        pytest.param(
            f"import importlib\nmodule = importlib.import_module({_CONFIRMATORY!r})\n",
            id="importlib",
        ),
        pytest.param(
            f"from importlib import import_module\nmodule = import_module({_CONFIRMATORY!r})\n",
            id="import-module-name",
        ),
        pytest.param("from . import run_confirmatory_cohort\n", id="relative-package"),
        pytest.param("from .run_confirmatory_cohort import X\n", id="relative-module"),
        pytest.param(f"module = __import__({_CONFIRMATORY!r})\n", id="dunder-import"),
        pytest.param(
            f"import importlib\nmodule = importlib.import_module(name={_CONFIRMATORY!r})\n",
            id="import-module-keyword",
        ),
    ],
)
def test_guard_catches_every_import_form(tmp_path: Path, source: str) -> None:
    planted = tmp_path / "planted.py"
    planted.write_text(source, encoding="utf-8")
    assert _CONFIRMATORY in _imports(planted)
