"""Gate da pureza dos testes unit do slice `evaluation` (concept 6.2 I13; LAYOUT §7).

"Unit = sem I/O" (marcador do `pyproject.toml`) e bibliotecas só via adapter no contrato
ou diretamente na integração: nenhum `tests/unit/features/evaluation/**/*.py` importa
`arch`/`statsmodels`/`scipy`/`numpy`/`sklearn`/`scoringrules` ou um módulo
`*.adapters.*`, nem chama `open`, `read_text`, `read_bytes` ou `json.load`. Verificado
pela AST (não por grep: um nome num docstring ou comentário não conta, e
`from x import y as z` não escapa). A varredura é recursiva (`rglob`): os subpacotes
(ex. `gold/`, Stage 6.4) entram no gate sem registro.
"""

from __future__ import annotations

import ast
from pathlib import Path

_UNIT_DIR = Path(__file__).resolve().parents[1] / "unit" / "features" / "evaluation"
# Os mesmos módulos do grep de pureza do technical 6.2 §3 (Host).
_FORBIDDEN_ROOTS = {"arch", "statsmodels", "scipy", "numpy", "sklearn", "scoringrules"}
_FORBIDDEN_CALLS = {"open", "read_text", "read_bytes", "load"}


def _violations(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules = [node.module]
        for module in modules:
            if module.split(".")[0] in _FORBIDDEN_ROOTS or ".adapters." in f".{module}.":
                found.append(f"{path}:{node.lineno}: import {module}")
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name in _FORBIDDEN_CALLS:
                found.append(f"{path}:{node.lineno}: call {name}()")
    return found


def _scan(root: Path) -> list[str]:
    """Violações de todo `*.py` sob `root`, recursivamente (subpacotes inclusive)."""
    return [item for path in sorted(root.rglob("*.py")) for item in _violations(path)]


def test_unit_evaluation_no_lib_or_adapter_import_unitpure() -> None:
    files = sorted(_UNIT_DIR.rglob("*.py"))
    assert len(files) > 1, f"no unit test found in {_UNIT_DIR}"
    assert _scan(_UNIT_DIR) == []


def test_unit_purity_detector_flags_violations(tmp_path: Path) -> None:
    """O detector não é vácuo: reprova import de lib, de adapter e leitura de arquivo."""
    impure = tmp_path / "impure.py"
    impure.write_text(
        "import numpy as np\n"
        "from scipy import stats\n"
        "from financial_forecasting.features.evaluation.adapters.out.inference import x\n"
        "data = open('f').read()\n"
        "text = path.read_text()\n",
        encoding="utf-8",
    )
    assert len(_violations(impure)) == 5  # noqa: PLR2004 — uma por linha


def test_unit_purity_scans_subpackages(tmp_path: Path) -> None:
    """A varredura é recursiva: arquivo impuro num subpacote é acusado (6.4 Task 03)."""
    (tmp_path / "test_clean.py").write_text("import math\n", encoding="utf-8")
    nested = tmp_path / "gold" / "deeper"
    nested.mkdir(parents=True)
    (nested / "test_impure.py").write_text("import arch\n", encoding="utf-8")
    violations = _scan(tmp_path)
    assert len(violations) == 1
    assert "deeper" in violations[0]
    assert violations[0].endswith("import arch")
