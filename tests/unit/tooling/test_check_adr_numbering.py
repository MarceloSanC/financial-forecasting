"""Unit de `scripts/check_adr_numbering.py` — número de ADR único (issue #190)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_adr_numbering.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_adr_numbering", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


can = _load()


def _adr(adr_dir: Path, name: str, adr_id: str | None, *, body: str = "") -> Path:
    adr_dir.mkdir(parents=True, exist_ok=True)
    line = "" if adr_id is None else f"adr_id: {adr_id}\n"
    path = adr_dir / name
    path.write_text(
        f"---\ntitle: ADR\nstatus: accepted\n{line}bounded_context: transversal\n---\n\n"
        f"# ADR\n{body}\n",
        encoding="utf-8",
    )
    return path


def test_unique_numbers_pass(tmp_path: Path) -> None:
    _adr(tmp_path, "0_0_0058-a.md", "0.0.0058")
    _adr(tmp_path, "0_0_0059-b.md", '"0.0.0059"')
    _adr(tmp_path, "7_4_0001-c.md", "'7.4.0001'")
    assert can.main(tmp_path) == 0


def test_same_sequence_in_different_prefixes_is_not_a_collision(tmp_path: Path) -> None:
    _adr(tmp_path, "0_0_0001-a.md", "0.0.0001")
    _adr(tmp_path, "1_1_0001-b.md", "1.1.0001")
    assert can.check_paths(sorted(tmp_path.glob("*.md"))) == []


def test_probe_two_adrs_with_same_number_fails_naming_both(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sonda do critério de aceite: o caso real de 2026-10-18 (#161 x #185)."""
    _adr(tmp_path, "0_0_0058-architecture-harness-gate-hook-agent.md", "0.0.0058")
    _adr(tmp_path, "0_0_0058-planned-full-gate-budget-per-stage.md", "0.0.0058")

    assert can.main(tmp_path) == 1

    err = capsys.readouterr().err
    prefix_line = next(line for line in err.splitlines() if "numero de ADR 0.0.0058" in line)
    assert "0_0_0058-architecture-harness-gate-hook-agent.md" in prefix_line
    assert "0_0_0058-planned-full-gate-budget-per-stage.md" in prefix_line
    assert any("adr_id 0.0.0058 repetido" in line for line in err.splitlines())


def test_duplicate_adr_id_across_different_prefixes_is_refused(tmp_path: Path) -> None:
    _adr(tmp_path, "0_0_0058-a.md", "0.0.0058")
    _adr(tmp_path, "0_0_0059-b.md", "0.0.0058")
    errors = can.check_paths(sorted(tmp_path.glob("*.md")))
    duplicate = [e for e in errors if e.startswith("adr_id 0.0.0058 repetido")]
    assert len(duplicate) == 1
    assert "0_0_0058-a.md" in duplicate[0] and "0_0_0059-b.md" in duplicate[0]
    assert not any(e.startswith("numero de ADR") for e in errors)


@pytest.mark.parametrize(
    "adr_id",
    ["0.0.0057", "0.0.58", "0_0_0058", "0.1.0058", "1.0.0058", "", None],
)
def test_adr_id_not_matching_filename_is_refused(tmp_path: Path, adr_id: str | None) -> None:
    _adr(tmp_path, "0_0_0058-a.md", adr_id)
    errors = can.check_paths(sorted(tmp_path.glob("*.md")))
    assert len(errors) == 1
    assert "0_0_0058-a.md" in errors[0]
    assert "esperado '0.0.0058'" in errors[0]


@pytest.mark.parametrize(
    "name", ["0_0_58-a.md", "0-0-0058-a.md", "0_0_0058.md", "0_0_00058-a.md", "adr-0058.md"]
)
def test_filename_outside_pattern_is_refused(tmp_path: Path, name: str) -> None:
    _adr(tmp_path, name, "0.0.0058")
    errors = can.check_paths(sorted(tmp_path.glob("*.md")))
    assert len(errors) == 1
    assert name in errors[0]
    assert "N_M_NNNN-<slug>.md" in errors[0]


def test_adr_id_in_body_is_not_the_declaration(tmp_path: Path) -> None:
    _adr(tmp_path, "0_0_0058-a.md", None, body="```yaml\nadr_id: 0.0.0058\n```")
    errors = can.check_paths(sorted(tmp_path.glob("*.md")))
    assert len(errors) == 1
    assert "adr_id=None" in errors[0]


def test_missing_frontmatter_has_no_declared_adr_id(tmp_path: Path) -> None:
    path = tmp_path / "0_0_0058-a.md"
    path.write_text("# ADR sem frontmatter\nadr_id: 0.0.0058\n", encoding="utf-8")
    assert can.declared_adr_id(path) is None
    unterminated = tmp_path / "0_0_0059-b.md"
    unterminated.write_text("---\nadr_id: 0.0.0059\n", encoding="utf-8")
    assert can.declared_adr_id(unterminated) is None


def test_bom_does_not_hide_the_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "0_0_0058-a.md"
    path.write_text("---\nadr_id: 0.0.0058\n---\n", encoding="utf-8-sig")
    assert can.declared_adr_id(path) == "0.0.0058"


def test_repo_adrs_are_valid_on_current_tree() -> None:
    """Critério de aceite: o `docs/adr/` atual passa no gate."""
    assert can.check_paths(sorted(can.ADR_DIR.glob("*.md"))) == []
