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


def imported_modules(source: str) -> set[str]:
    """Módulos importados por qualquer forma: `from`, `import` e `import_module` constante.

    `from pacote import modulo` conta como `pacote.modulo` (o nome pode ser um
    submódulo), além do próprio `pacote`.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute | ast.Name)
            and (node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id)
            == "import_module"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            found.add(node.args[0].value)
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
    ],
)
def test_guard_catches_every_import_form(tmp_path: Path, source: str) -> None:
    planted = tmp_path / "planted.py"
    planted.write_text(source, encoding="utf-8")
    assert _CONFIRMATORY in _imports(planted)
