"""Guardas de regressão da Stage 7.2 — o que o import-linter não vê.

I1 (ADR 7.2.0002 item 6; ADR 6.4.0008): nenhum use case nem o composition root chama
o oráculo `ConformalBackend`. O `exclude_type_checking_imports = True` deixa imports
sob `TYPE_CHECKING` invisíveis ao import-linter, então a guarda lê o AST de todo
`src/`, inclusive esses blocos: além do próprio módulo do port, só
`features/inference/adapters/out/mapie/**` pode importar `conformal_backend`. As três
formas são acusadas: `from ….conformal_backend import …`, `from ….ports.out import
conformal_backend [as x]` e `importlib.import_module("…conformal_backend")`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
_PORT_MODULE = "conformal_backend"
_PORT_FILE = "financial_forecasting/features/inference/application/ports/out/conformal_backend.py"
_ALLOWED_PREFIX = "financial_forecasting/features/inference/adapters/out/mapie/"


def _imports_port(tree: ast.AST) -> list[int]:
    """Linhas que importam o módulo do port, em qualquer das três formas."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[-1] == _PORT_MODULE or any(
                alias.name == _PORT_MODULE for alias in node.names
            ):
                lines.append(node.lineno)
        elif isinstance(node, ast.Import):
            if any(alias.name.split(".")[-1] == _PORT_MODULE for alias in node.names):
                lines.append(node.lineno)
        elif isinstance(node, ast.Call):
            for argument in node.args:
                if (
                    isinstance(argument, ast.Constant)
                    and isinstance(argument.value, str)
                    and argument.value.split(".")[-1] == _PORT_MODULE
                ):
                    lines.append(node.lineno)
    return lines


def _offenders(root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative == _PORT_FILE or relative.startswith(_ALLOWED_PREFIX):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found.extend(f"{relative}:{line}" for line in _imports_port(tree))
    return found


@pytest.mark.unit
def test_only_the_mapie_adapter_imports_the_conformal_backend_port() -> None:
    assert (_SRC / _PORT_FILE).is_file()
    assert _offenders(_SRC) == []


@pytest.mark.unit
def test_guard_catches_every_import_form(tmp_path: Path) -> None:
    use_cases = tmp_path / "financial_forecasting/features/inference/application/use_cases"
    use_cases.mkdir(parents=True)
    forms = {
        "direct.py": (
            "from financial_forecasting.features.inference.application.ports.out"
            ".conformal_backend import ConformalBackend\n"
        ),
        "package.py": (
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from financial_forecasting.features.inference.application.ports.out import (\n"
            "        conformal_backend as backend,\n"
            "    )\n"
        ),
        "dynamic.py": (
            "import importlib\n"
            "importlib.import_module(\n"
            "    'financial_forecasting.features.inference.application.ports.out"
            ".conformal_backend'\n"
            ")\n"
        ),
    }
    for name, source in forms.items():
        (use_cases / name).write_text(source, encoding="utf-8")
    root = tmp_path / "financial_forecasting/composition_root.py"
    root.write_text(
        "import financial_forecasting.features.inference.application.ports.out.conformal_backend\n",
        encoding="utf-8",
    )
    allowed = tmp_path / _ALLOWED_PREFIX / "mapie_cqr_backend.py"
    allowed.parent.mkdir(parents=True)
    allowed.write_text(forms["direct.py"], encoding="utf-8")

    offenders = {entry.split(":")[0].rsplit("/", 1)[-1] for entry in _offenders(tmp_path)}
    assert offenders == {"direct.py", "package.py", "dynamic.py", "composition_root.py"}


_FAKE = _REPO / "tests/fakes/features/evaluation/fake_conformal_calibration.py"
_SUPPLIER = "financial_forecasting.features.inference.application.use_cases.calibrate_conformal"


def _fake_violations(source: str) -> list[str]:
    """O que o fake do `ConformalCalibration` não pode ter, e o que ele precisa importar.

    O `check_fake_parity.py` compara fake e adapter, e é cego a use case: esta guarda
    cobre o ponto cego. O fake reusa as regras do fornecedor (`validate_command` e
    `calibration_set_for`) e não calibra: não define `calibrate` nem importa o
    `ConformalCalibrator`.
    """
    tree = ast.parse(source)
    imported_from_supplier: set[str] = set()
    problems: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == _SUPPLIER:
            imported_from_supplier.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom | ast.Import) and any(
            alias.name == "ConformalCalibrator" for alias in node.names
        ):
            problems.append(f"imports ConformalCalibrator (line {node.lineno})")
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == "calibrate":
            problems.append(f"defines calibrate (line {node.lineno})")
    for name in ("validate_command", "calibration_set_for"):
        if name not in imported_from_supplier:
            problems.append(f"does not import {name} from calibrate_conformal")
    return problems


@pytest.mark.unit
def test_fake_conformal_calibration_reuses_the_supplier_rules() -> None:
    assert _fake_violations(_FAKE.read_text(encoding="utf-8")) == []


@pytest.mark.unit
def test_fake_guard_catches_a_reimplemented_calibrator() -> None:
    bad = (
        "from financial_forecasting.features.inference.domain.services.conformal_calibrator "
        "import ConformalCalibrator\n"
        "def calibrate(x):\n    return x\n"
    )
    problems = _fake_violations(bad)
    assert any("ConformalCalibrator" in p for p in problems)
    assert any("defines calibrate" in p for p in problems)
    assert any("validate_command" in p for p in problems)
    assert any("calibration_set_for" in p for p in problems)
