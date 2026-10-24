"""Guardas de regressão da Stage 8.3 — o que o import-linter não vê.

A15 (ADR 8.3.0003 item 1; concept 8.3 D6): o contrato `evaluation-no-matplotlib-leak`
confina `matplotlib` ao adapter de plots, mas a exceção do pacote de plots deixa passar
qualquer submódulo — inclusive `matplotlib.pyplot`, que carrega estado global (figura
corrente, backend do processo) e quebraria o determinismo do PDF. A guarda lê o AST de
todo `src/**/*.py`, **inclusive** `features/evaluation/adapters/out/plots/`, e reprova as
formas estáticas — `import matplotlib.pyplot`, `from matplotlib import pyplot` e
`from matplotlib.pyplot import …` — e as dinâmicas
`importlib.import_module("matplotlib.pyplot")` e `__import__("matplotlib.pyplot")`
(CC1-2). Um auto-teste sobre fonte sintética prova que a guarda
acusa cada forma (sem ele, uma guarda vazia passaria verde).

A6 (concept 8.3 I3; technical 8.3 Task 07, CB-6): os módulos de montagem do dado plotado
(`GUARDED_MODULES`) não importam serviço inferencial do domínio. A guarda é por **lista
permitida** de `features.evaluation.domain.services`: só `series_assembly`,
`coverage_metrics` e `degeneracy_gate`; qualquer outro módulo (DM, Holm, MCS, Wilson, gate
H1, poder, ACF, CUSUM, Beta, conformal, scoring e serviço futuro) reprova. `from
…domain.services import x` é resolvido pelo `alias.name`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
_PYPLOT = "matplotlib.pyplot"
_DYNAMIC_IMPORTS = frozenset({"import_module", "__import__"})


def _is_pyplot(name: str) -> bool:
    return name == _PYPLOT or name.startswith(f"{_PYPLOT}.")


def _dynamic_pyplot(node: ast.Call) -> bool:
    """`import_module("matplotlib.pyplot…")` (qualquer qualificação) ou `__import__(…)`."""
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    first = node.args[0] if node.args else None
    return (
        name in _DYNAMIC_IMPORTS
        and isinstance(first, ast.Constant)
        and isinstance(first.value, str)
        and _is_pyplot(first.value)
    )


def _pyplot_imports(tree: ast.AST) -> list[int]:
    """Linhas que importam `matplotlib.pyplot`, nas formas estáticas e dinâmicas."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _dynamic_pyplot(node):
            lines.append(node.lineno)
        elif isinstance(node, ast.Import):
            if any(
                alias.name == _PYPLOT or alias.name.startswith(f"{_PYPLOT}.")
                for alias in node.names
            ):
                lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            from_pyplot = node.module == _PYPLOT or node.module.startswith(f"{_PYPLOT}.")
            pyplot_from_package = node.module == "matplotlib" and any(
                alias.name == "pyplot" for alias in node.names
            )
            if from_pyplot or pyplot_from_package:
                lines.append(node.lineno)
    return lines


def _offenders(root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        relative = path.relative_to(root).as_posix()
        found.extend(f"{relative}:{line}" for line in _pyplot_imports(tree))
    return found


@pytest.mark.unit
def test_no_pyplot_anywhere_in_src() -> None:
    assert (_SRC / "financial_forecasting").is_dir()
    assert _offenders(_SRC) == []


@pytest.mark.unit
def test_pyplot_guard_catches_every_import_form() -> None:
    source = (
        "import matplotlib.pyplot as plt\n"
        "from matplotlib import pyplot\n"
        "from matplotlib.pyplot import subplots\n"
        "import matplotlib\n"
        "from matplotlib.figure import Figure\n"
        "from matplotlib import rc_context\n"
        "import importlib\n"
        "importlib.import_module('matplotlib.pyplot')\n"
        "__import__('matplotlib.pyplot')\n"
        "importlib.import_module('matplotlib.figure')\n"
    )
    assert sorted(_pyplot_imports(ast.parse(source))) == [1, 2, 3, 8, 9]


@pytest.mark.unit
def test_pyplot_guard_scans_the_plots_adapter_too(tmp_path: Path) -> None:
    plots = tmp_path / "financial_forecasting/features/evaluation/adapters/out/plots"
    plots.mkdir(parents=True)
    (plots / "renderer.py").write_text("from matplotlib import pyplot\n", encoding="utf-8")
    assert _offenders(tmp_path) == [
        "financial_forecasting/features/evaluation/adapters/out/plots/renderer.py:1"
    ]


# --- A6: nenhum serviço inferencial nos módulos de montagem ----------------------------

_USE_CASES = "financial_forecasting/features/evaluation/application/use_cases"
GUARDED_MODULES = (
    f"{_USE_CASES}/report_figures.py",
    f"{_USE_CASES}/report_silver.py",
    f"{_USE_CASES}/report_dossier.py",
    f"{_USE_CASES}/dossier_markdown.py",
    f"{_USE_CASES}/generate_report_artifacts.py",
)
_SERVICES = "financial_forecasting.features.evaluation.domain.services"
ALLOWED_SERVICES = frozenset({"series_assembly", "coverage_metrics", "degeneracy_gate"})


def _service_imports(tree: ast.AST) -> list[str]:
    """Os módulos de `domain.services` importados, nas três formas de import."""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [
                alias.name.removeprefix(f"{_SERVICES}.").split(".")[0]
                for alias in node.names
                if alias.name.startswith(f"{_SERVICES}.")
            ]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == _SERVICES:
                found += [alias.name for alias in node.names]
            elif node.module.startswith(f"{_SERVICES}."):
                found.append(node.module.removeprefix(f"{_SERVICES}.").split(".")[0])
    return found


def _forbidden_services(source: str) -> list[str]:
    return [name for name in _service_imports(ast.parse(source)) if name not in ALLOWED_SERVICES]


@pytest.mark.unit
@pytest.mark.parametrize("module", GUARDED_MODULES)
def test_report_figures_imports_no_inferential_service(module: str) -> None:
    path = _SRC / module
    assert path.is_file(), module
    assert _forbidden_services(path.read_text(encoding="utf-8")) == []


@pytest.mark.unit
def test_inferential_service_guard_catches_every_import_form() -> None:
    source = (
        f"from {_SERVICES}.diebold_mariano import DieboldMariano\n"
        f"import {_SERVICES}.wilson_band\n"
        f"from {_SERVICES} import holm_correction, coverage_metrics\n"
        f"from {_SERVICES}.conformal_coverage import EMPIRICAL_COVERAGE_LABEL\n"
        f"from {_SERVICES}.series_assembly import SeriesAssembly\n"
        f"from {_SERVICES}.a_future_service import thing\n"
    )
    assert _forbidden_services(source) == [
        "diebold_mariano",
        "wilson_band",
        "holm_correction",
        "conformal_coverage",
        "a_future_service",
    ]
