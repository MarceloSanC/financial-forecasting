"""Gate da pureza dos testes unit do slice `evaluation` (concept 6.2 I13; LAYOUT §7).

"Unit = sem I/O" (marcador do `pyproject.toml`) e bibliotecas só via adapter no contrato
ou diretamente na integração: nenhum `tests/unit/features/evaluation/*.py` importa
`arch`/`statsmodels`/`scipy`/`numpy` ou um módulo `*.adapters.*`, nem chama `open`,
`read_text`, `read_bytes` ou `json.load`. Verificado pela AST (não por grep: um nome num
docstring ou comentário não conta, e `from x import y as z` não escapa).
"""

from __future__ import annotations

import ast
from pathlib import Path

_UNIT_DIR = Path(__file__).resolve().parents[1] / "unit" / "features" / "evaluation"
_FORBIDDEN_ROOTS = {"arch", "statsmodels", "scipy", "numpy"}
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
                found.append(f"{path.name}:{node.lineno}: import {module}")
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name in _FORBIDDEN_CALLS:
                found.append(f"{path.name}:{node.lineno}: call {name}()")
    return found


def test_unit_evaluation_no_lib_or_adapter_import_unitpure() -> None:
    files = sorted(_UNIT_DIR.glob("*.py"))
    assert len(files) > 1, f"no unit test found in {_UNIT_DIR}"
    violations = [item for path in files for item in _violations(path)]
    assert violations == []


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
