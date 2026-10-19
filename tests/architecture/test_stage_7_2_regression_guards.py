"""Guardas de regressão da Stage 7.2 — o que o import-linter não vê.

I1 (ADR 7.2.0002 item 6; ADR 6.4.0008): nenhum use case nem o composition root chama
o oráculo `ConformalBackend`. O `exclude_type_checking_imports = True` deixa imports
sob `TYPE_CHECKING` invisíveis ao import-linter, então a guarda lê o AST de todo
`src/`, inclusive esses blocos: além do próprio módulo do port, só
`features/inference/adapters/out/mapie/**` pode importar `conformal_backend`. As três
formas são acusadas: `from ….conformal_backend import …`, `from ….ports.out import
conformal_backend [as x]` e `importlib.import_module("…conformal_backend")`.

ADR 7.2.0003 item 3: do `evaluation`, só o `RefreshGold` importa a `inference` em
runtime, e só o módulo `calibrate_conformal`; o port `ConformalCalibration` o anota
só sob `TYPE_CHECKING`; DTOs, builders e domínio do `evaluation` nunca o importam.
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


_EVALUATION = _SRC / "financial_forecasting/features/evaluation"
_INFERENCE = "financial_forecasting.features.inference"


def _inference_imports(source: str) -> list[tuple[str, bool]]:
    """(módulo da `inference` importado, se está sob `if TYPE_CHECKING:`)."""
    tree = ast.parse(source)
    typing_only: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and ast.unparse(node.test).endswith("TYPE_CHECKING"):
            typing_only.update(id(child) for child in ast.walk(node))
    found: list[tuple[str, bool]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules = [node.module]
        elif isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        else:
            continue
        found.extend(
            (module, id(node) in typing_only)
            for module in modules
            if module == _INFERENCE or module.startswith(_INFERENCE + ".")
        )
    return found


def _read(relative: str) -> str:
    return (_EVALUATION / relative).read_text(encoding="utf-8")


@pytest.mark.unit
def test_evaluation_dtos_builders_and_domain_never_import_inference() -> None:
    offenders = [
        f"{path.relative_to(_EVALUATION).as_posix()}: {module}"
        for folder in ("application/dtos", "adapters", "domain")
        for path in sorted((_EVALUATION / folder).rglob("*.py"))
        for module, _ in _inference_imports(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


@pytest.mark.unit
def test_conformal_calibration_port_imports_inference_only_for_typing() -> None:
    found = _inference_imports(_read("application/ports/out/conformal_calibration.py"))
    assert found
    assert all(typing_only for _, typing_only in found), found


@pytest.mark.unit
def test_refresh_gold_imports_only_calibrate_conformal_from_inference() -> None:
    found = _inference_imports(_read("application/use_cases/refresh_gold.py"))
    assert {module for module, _ in found} == {_SUPPLIER}


def _supplier_names(source: str) -> dict[bool, set[str]]:
    """Nomes importados do `calibrate_conformal`, por `typing_only` (C4-12)."""
    tree = ast.parse(source)
    typing_only: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and ast.unparse(node.test).endswith("TYPE_CHECKING"):
            typing_only.update(id(child) for child in ast.walk(node))
    names: dict[bool, set[str]] = {False: set(), True: set()}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == _SUPPLIER:
            names[id(node) in typing_only].update(alias.name for alias in node.names)
    return names


@pytest.mark.unit
def test_refresh_gold_imports_only_the_command_dtos_at_runtime() -> None:
    """C4-12: em runtime só os DTOs de comando; o resultado só para tipo."""
    names = _supplier_names(_read("application/use_cases/refresh_gold.py"))
    assert names[False] == {
        "CalibrateConformalCommand",
        "ConformalUnitInput",
        "ConformalPointInput",
    }
    assert names[True] == {"ConformalUnitResult"}


@pytest.mark.unit
def test_supplier_names_helper_splits_runtime_and_typing() -> None:
    source = (
        "from typing import TYPE_CHECKING\n"
        f"from {_SUPPLIER} import CalibrateConformal\n"
        "if TYPE_CHECKING:\n"
        f"    from {_SUPPLIER} import ConformalUnitResult\n"
    )
    assert _supplier_names(source) == {False: {"CalibrateConformal"}, True: {"ConformalUnitResult"}}


@pytest.mark.unit
def test_inference_import_helper_sees_typing_blocks_and_plain_imports() -> None:
    source = (
        "from typing import TYPE_CHECKING\n"
        "import financial_forecasting.features.inference.domain\n"
        "if TYPE_CHECKING:\n"
        "    from financial_forecasting.features.inference.application import x\n"
        "from financial_forecasting.features.inferencex import y\n"
    )
    assert _inference_imports(source) == [
        ("financial_forecasting.features.inference.domain", False),
        ("financial_forecasting.features.inference.application", True),
    ]
