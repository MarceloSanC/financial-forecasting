"""Unit do executor `.claude/skills/architecture-fitness/scripts/check_changed.py` (#161).

Roda os gates REAIS de `scripts/` sobre uma árvore em `tmp_path` (nada toca o `src/` real):
o que se testa é o filtro por arquivo e o cruzamento com o baseline, não as regras — essas
têm regressão própria em `tests/architecture/`.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / ".claude" / "skills" / "architecture-fitness" / "scripts" / "check_changed.py"
_SCRIPTS = _REPO / "scripts"
_FEATURES = "src/financial_forecasting/features"
_DOMAIN_FILE = f"{_FEATURES}/evaluation/domain/services/clocky.py"
_CLOCK = "import time\nx = time.time()\n"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_changed", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cc = _load()


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _findings(root: Path, *paths: Path) -> list[Any]:
    return list(cc.findings_for(list(paths), root=root, scripts_dir=_SCRIPTS))


@pytest.mark.parametrize(
    ("rel", "body", "gate"),
    [
        pytest.param(_DOMAIN_FILE, _CLOCK, "domain_determinism", id="relogio-no-dominio"),
        pytest.param(
            f"{_FEATURES}/modeling/application/use_cases/train_x.py",
            "from financial_forecasting.features.analytics_store.application.use_cases"
            ".persist_predictions import PersistPredictions\n\n"
            "class TrainX:\n"
            "    def __init__(self, *, sink: PersistPredictions) -> None:\n"
            "        self._sink = sink\n",
            "use_case_deps",
            id="use-case-de-outro-slice",
        ),
        pytest.param(
            f"{_FEATURES}/modeling/application/use_cases/read_x.py",
            'TABLE = "dataset_tft"\n',
            "schema_literals",
            id="literal-de-schema",
        ),
        pytest.param(
            f"{_FEATURES}/evaluation/domain/value_objects/level.py",
            "from dataclasses import dataclass\n\n"
            "@dataclass(frozen=True)\nclass Level:\n    value: float\n",
            "vo_invariants",
            id="vo-sem-invariante",
        ),
    ],
)
def test_each_gate_reports_a_violation_in_the_edited_file(
    tmp_path: Path, rel: str, body: str, gate: str
) -> None:
    edited = _write(tmp_path, rel, body)

    found = _findings(tmp_path, edited)

    assert [(f.gate, f.dead) for f in found] == [(gate, False)]
    assert found[0].text.startswith(f"{rel}::")


def test_violation_in_another_file_is_left_to_make_check(tmp_path: Path) -> None:
    _write(tmp_path, _DOMAIN_FILE, _CLOCK)
    clean = _write(tmp_path, f"{_FEATURES}/evaluation/domain/services/pure.py", "x = 1\n")

    assert _findings(tmp_path, clean) == []


def test_relative_path_and_path_outside_the_root(tmp_path: Path) -> None:
    _write(tmp_path, _DOMAIN_FILE, _CLOCK)
    outside = _write(tmp_path.parent / f"{tmp_path.name}-other", "x.py", _CLOCK)

    assert len(_findings(tmp_path, Path(_DOMAIN_FILE))) == 1
    assert _findings(tmp_path, outside) == []


def _baseline(root: Path, key: str) -> None:
    _write(
        root,
        "scripts/arch_baseline.toml",
        f"[[domain_determinism.allow]]\nkey = '{key}'\nmotivo = \"débito\"\nissue = 1\n",
    )


def test_violation_in_the_baseline_is_tolerated(tmp_path: Path) -> None:
    edited = _write(tmp_path, _DOMAIN_FILE, _CLOCK)
    _baseline(tmp_path, f"{_DOMAIN_FILE}::time.time")

    assert _findings(tmp_path, edited) == []


def test_fixed_violation_reports_the_dead_baseline_entry_of_that_file(tmp_path: Path) -> None:
    edited = _write(tmp_path, _DOMAIN_FILE, "x = 1\n")
    _baseline(tmp_path, f"{_DOMAIN_FILE}::time.time")

    found = _findings(tmp_path, edited)

    assert [(f.gate, f.dead) for f in found] == [("domain_determinism", True)]
    assert "baseline morto" in found[0].render()
    assert "arch_baseline.toml" in found[0].render()


def test_dead_entry_of_another_file_is_not_reported(tmp_path: Path) -> None:
    edited = _write(tmp_path, _DOMAIN_FILE, "x = 1\n")
    _baseline(tmp_path, f"{_FEATURES}/evaluation/domain/services/other.py::time.time")

    assert _findings(tmp_path, edited) == []


def test_render_points_to_the_rule_reference(tmp_path: Path) -> None:
    found = _findings(tmp_path, _write(tmp_path, _DOMAIN_FILE, _CLOCK))

    rendered = found[0].render()

    assert rendered.startswith(f"[domain_determinism] {_DOMAIN_FILE}::time.time: linhas L2")
    assert "reference/domain-purity.md" in rendered


def test_every_gate_has_a_reference_file() -> None:
    gates = {cc._load(_SCRIPTS, name).GATE for name in cc.GATES}

    assert gates == set(cc.REFERENCE)
    for name in cc.REFERENCE.values():
        assert (cc.SKILL_DIR / "reference" / name).is_file(), name


def test_gate_list_matches_make_arch_ast() -> None:
    """Gate novo em `make arch-ast` sem entrar no executor deixaria o hook cego para ele."""
    makefile = (_REPO / "Makefile").read_text(encoding="utf-8")
    target = re.search(r"^arch-ast:\n((?:\t.*\n)+)", makefile, re.MULTILINE)
    assert target is not None

    assert tuple(re.findall(r"scripts/(check_\w+)\.py", target.group(1))) == cc.GATES


def test_find_root_walks_up_to_the_baseline(tmp_path: Path) -> None:
    _baseline(tmp_path, "x::y")
    edited = _write(tmp_path, _DOMAIN_FILE, "x = 1\n")

    assert cc.find_root(edited) == tmp_path
    assert cc.find_root(tmp_path.parent) != tmp_path


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_changed_files_takes_diff_and_untracked_python_under_src(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in ("GIT_DIR", "GIT_WORK_TREE"):  # o container de check exporta os dois
        monkeypatch.delenv(var, raising=False)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    committed = _write(tmp_path, f"{_FEATURES}/a.py", "x = 1\n")
    _write(tmp_path, f"{_FEATURES}/untouched.py", "x = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    committed.write_text("x = 2\n", encoding="utf-8")
    untracked = _write(tmp_path, f"{_FEATURES}/b.py", "x = 1\n")
    _write(tmp_path, "scripts/tool.py", "x = 1\n")
    _write(tmp_path, f"{_FEATURES}/notes.md", "x\n")

    assert cc.changed_files(tmp_path, "HEAD") == [committed, untracked]


def test_main_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clean = _REPO / "src" / "financial_forecasting" / "__init__.py"
    monkeypatch.chdir(_REPO)
    assert cc.main([str(clean)]) == 0

    fake = cc.Finding(gate="domain_determinism", dead=False, text="src/x.py::time.time: L1")
    monkeypatch.setattr(cc, "findings_for", lambda paths, root: [fake])
    assert cc.main([str(clean)]) == 1
    assert "src/x.py::time.time: L1" in capsys.readouterr().out

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cc, "find_root", lambda start: None)
    assert cc.main([]) == 2  # noqa: PLR2004 — exit 2 = raiz não encontrada
