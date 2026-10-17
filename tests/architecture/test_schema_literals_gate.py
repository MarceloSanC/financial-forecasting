"""Regressão do gate `scripts/check_schema_literals.py` (issue #61).

O gate nasce com baseline cheio (17 ocorrências → #159); o teste prova que ele reprova
uma ocorrência NOVA e que o perímetro é o estreito que a issue pediu.

Cobre:

- cada literal proibido em código reprova, inclusive dentro de coleção e de chamada;
- docstring (módulo/classe/função) não conta; substring/f-string/`"timestamp"`/`"time_idx"`
  não contam;
- só `features/modeling/application/` é varrido;
- o repo real casa exatamente com o baseline (nenhuma nova, nenhuma morta);
- `main()` devolve 1 quando uma ocorrência nova aparece.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_{name}_under_test", _SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gate() -> ModuleType:
    return _load("check_schema_literals")


@pytest.fixture
def baseline_lib() -> ModuleType:
    return _load("arch_baseline_lib")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param('_LAYER = "processed"', {"processed": [1]}, id="processed"),
        pytest.param('_TABLE = "dataset_tft"', {"dataset_tft": [1]}, id="dataset_tft"),
        pytest.param(
            'cols = {"timestamp", "target_return"}', {"target_return": [1]}, id="em-colecao"
        ),
        pytest.param(
            'store.read("processed", "dataset_tft")',
            {"processed": [1], "dataset_tft": [1]},
            id="em-chamada",
        ),
        pytest.param(
            'def f():\n    """Lê `dataset_tft`."""\n    return "target_return"\n',
            {"target_return": [3]},
            id="codigo-apos-docstring",
        ),
    ],
)
def test_forbidden_literal_in_code_is_a_violation(
    gate: ModuleType, source: str, expected: dict[str, list[int]]
) -> None:
    assert gate.forbidden_literals(ast.parse(source)) == expected


@pytest.mark.parametrize(
    "source",
    [
        pytest.param('"""dataset_tft"""\n', id="docstring-modulo"),
        pytest.param('class C:\n    """processed"""\n', id="docstring-classe"),
        pytest.param('def f():\n    """target_return"""\n', id="docstring-funcao"),
        pytest.param('x = "dataset_tft_v2"', id="substring"),
        pytest.param('x = f"{layer}/dataset_tft"', id="f-string"),
        pytest.param('x = "timestamp"', id="timestamp-bronze"),
        pytest.param('x = "time_idx"', id="time_idx-fora-do-perimetro"),
    ],
)
def test_allowed_strings_pass(gate: ModuleType, source: str) -> None:
    assert gate.forbidden_literals(ast.parse(source)) == {}


def test_scan_is_scoped_to_modeling_application(gate: ModuleType, tmp_path: Path) -> None:
    features = tmp_path / "src" / "financial_forecasting" / "features"
    scope = features / "modeling" / "application"
    for path in (
        scope / "use_cases" / "train_x.py",
        features / "feature_engineering" / "application" / "use_cases" / "build.py",
        features / "modeling" / "adapters" / "out" / "x" / "reader.py",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('TABLE = "dataset_tft"\n', encoding="utf-8")

    violations = gate.scan(scope=scope, root=tmp_path)

    rel = (scope / "use_cases" / "train_x.py").relative_to(tmp_path).as_posix()
    assert violations == {f'{rel}::"dataset_tft"': "linhas L1"}


def test_real_repo_matches_the_declared_baseline(
    gate: ModuleType, baseline_lib: ModuleType
) -> None:
    """A dívida medida é exatamente a declarada (#159): nada novo, nada morto."""
    baseline = baseline_lib.load_baseline(gate.GATE)

    new, dead = baseline_lib.reconcile(gate.scan(), baseline)

    assert (new, dead) == ([], [])
    assert {entry.issue for entry in baseline.values()} == {159}


def test_main_exit_code_follows_the_baseline_verdict(
    gate: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main()`: 0 no repo real (baseline casado); 1 com ocorrência nova injetada."""
    monkeypatch.setattr(sys, "argv", ["check_schema_literals.py", "--list"])
    assert gate.main() == 0
    assert "[schema_literals] PASSOU" in capsys.readouterr().out

    real = gate.scan()
    monkeypatch.setattr(gate, "scan", lambda: {**real, 'src/new.py::"processed"': "linhas L1"})
    assert gate.main() == 1
    out = capsys.readouterr().out
    assert 'src/new.py::"processed": linhas L1' in out
    assert "[schema_literals] REPROVOU" in out
