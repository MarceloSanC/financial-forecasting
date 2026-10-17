"""Unit de `scripts/check_technical_postexec.py` — vocabulário de tags da §7."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_technical_postexec.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_technical_postexec", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ctp = _load()


def _technical(tmp_path: Path, section: str, *, status: str = "draft", outside: str = "") -> Path:
    path = tmp_path / "technical.md"
    path.write_text(
        f"---\nstatus: {status}\n---\n\n# Technical\n{outside}\n"
        f"## 7. Execução\n<!-- BEGIN: post-execution -->\n{section}\n"
        "<!-- END: post-execution -->\n",
        encoding="utf-8",
    )
    return path


def _entry(tag: str, sep: str = "—") -> str:
    return f"### 2026-10-17 {sep} [{tag}] task-01 — escopo — Claude\n**Contexto:** x\n"


@pytest.mark.parametrize(
    "tag", ["decision", "decision:E", "decision:C", "finding", "deviation", "measurement"]
)
def test_vocabulary_tags_pass(tmp_path: Path, tag: str) -> None:
    assert ctp.check_file(_technical(tmp_path, _entry(tag))) == []


@pytest.mark.parametrize(
    "tag", ["nota", "fix", "P", "decision:P", "Measurement", "measurements", "", "deviation "]
)
def test_tag_outside_vocabulary_is_refused(tmp_path: Path, tag: str) -> None:
    errors = ctp.check_file(_technical(tmp_path, _entry("finding") + _entry(tag)))
    assert len(errors) == 1
    assert f"`[{tag}]`" in errors[0]
    assert "CONVENTIONS §3.4" in errors[0]


def test_error_points_to_the_offending_line(tmp_path: Path) -> None:
    path = _technical(tmp_path, _entry("nota"))
    line = path.read_text(encoding="utf-8").splitlines().index(_entry("nota").splitlines()[0])
    assert ctp.check_file(path)[0].startswith(f"{path}:{line + 1}: ")


@pytest.mark.parametrize("sep", ["\u2013", "-"])
def test_other_dash_separators_are_checked(tmp_path: Path, sep: str) -> None:
    assert len(ctp.check_file(_technical(tmp_path, _entry("nota", sep)))) == 1


def test_every_offending_entry_is_reported(tmp_path: Path) -> None:
    section = _entry("nota") + _entry("measurement") + _entry("fix")
    errors = ctp.check_file(_technical(tmp_path, section))
    assert [e.split("`[")[1].split("]`")[0] for e in errors] == ["nota", "fix"]


def test_refused_also_when_status_done(tmp_path: Path) -> None:
    # Sem commit `stage N.M: technical approved` (caminho fora de docs/stages),
    # a checagem de diff é pulada; a de tag continua valendo.
    assert len(ctp.check_file(_technical(tmp_path, _entry("nota"), status="done"))) == 1


def test_header_outside_the_window_is_not_checked(tmp_path: Path) -> None:
    assert ctp.check_file(_technical(tmp_path, "", outside=_entry("nota"))) == []


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_header_inside_a_code_fence_is_not_checked(tmp_path: Path, fence: str) -> None:
    section = f"{fence}markdown\n{_entry('nota')}{fence}\n" + _entry("nota")
    # só a entrada depois do fence conta: o fence fechou e voltou a valer
    assert len(ctp.check_file(_technical(tmp_path, section))) == 1


def test_untagged_entry_and_template_placeholder_pass(tmp_path: Path) -> None:
    section = (
        "### 2026-10-17 — Checkpoint C — disposições — Claude\n"
        "### YYYY-MM-DD — [tag] <Task NN ou escopo> — <Autor>\n"
        "#### 2026-10-17 — [nota] subtítulo de nível 4\n"
    )
    assert ctp.check_file(_technical(tmp_path, section)) == []


def test_main_exit_code_follows_the_tags(tmp_path: Path) -> None:
    good = _technical(tmp_path, _entry("measurement"))
    assert ctp.main([str(good)]) == 0
    bad = _technical(tmp_path, _entry("nota"))
    assert ctp.main([str(bad)]) == 1


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("sem marcadores\n", "encontrei 0 BEGIN e 0 END"),
        (
            "<!-- BEGIN: post-execution -->\n<!-- BEGIN: post-execution -->\n"
            "<!-- END: post-execution -->\n",
            "encontrei 2 BEGIN e 1 END",
        ),
        ("<!-- END: post-execution -->\n<!-- BEGIN: post-execution -->\n", "deve vir depois"),
    ],
)
def test_invalid_markers_are_refused(tmp_path: Path, body: str, expected: str) -> None:
    path = tmp_path / "technical.md"
    path.write_text(f"---\nstatus: draft\n---\n\n{body}", encoding="utf-8")
    errors = ctp.check_file(path)
    assert len(errors) == 1
    assert expected in errors[0]


def test_file_without_frontmatter_is_not_done(tmp_path: Path) -> None:
    assert not ctp._has_status_done("# Technical\nstatus: done\n")


def test_main_reports_missing_file(tmp_path: Path) -> None:
    assert ctp.main([str(tmp_path / "ausente.md")]) == 1


def test_main_without_targets_passes(tmp_path: Path) -> None:
    assert ctp.main(["--root", str(tmp_path)]) == 0
