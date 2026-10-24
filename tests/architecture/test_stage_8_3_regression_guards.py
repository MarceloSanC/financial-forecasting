"""Guardas de regressão da Stage 8.3 — o que o import-linter não vê.

A15 (ADR 8.3.0003 item 1; concept 8.3 D6): o contrato `evaluation-no-matplotlib-leak`
confina `matplotlib` ao adapter de plots, mas a exceção do pacote de plots deixa passar
qualquer submódulo — inclusive `matplotlib.pyplot`, que carrega estado global (figura
corrente, backend do processo) e quebraria o determinismo do PDF. A guarda lê o AST de
todo `src/**/*.py`, **inclusive** `features/evaluation/adapters/out/plots/`, e reprova as
três formas: `import matplotlib.pyplot`, `from matplotlib import pyplot` e
`from matplotlib.pyplot import …`. Um auto-teste sobre fonte sintética prova que a guarda
acusa cada forma (sem ele, uma guarda vazia passaria verde).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
_PYPLOT = "matplotlib.pyplot"


def _pyplot_imports(tree: ast.AST) -> list[int]:
    """Linhas que importam `matplotlib.pyplot`, em qualquer das três formas."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
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
    )
    assert _pyplot_imports(ast.parse(source)) == [1, 2, 3]


@pytest.mark.unit
def test_pyplot_guard_scans_the_plots_adapter_too(tmp_path: Path) -> None:
    plots = tmp_path / "financial_forecasting/features/evaluation/adapters/out/plots"
    plots.mkdir(parents=True)
    (plots / "renderer.py").write_text("from matplotlib import pyplot\n", encoding="utf-8")
    assert _offenders(tmp_path) == [
        "financial_forecasting/features/evaluation/adapters/out/plots/renderer.py:1"
    ]
