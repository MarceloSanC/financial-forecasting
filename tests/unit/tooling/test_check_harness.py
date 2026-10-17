"""Unit de `scripts/check_harness.py` — frontmatter de skills/subagentes."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_harness.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_harness", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ch = _load()


def _skill(tmp_path: Path, frontmatter: str) -> list[str]:
    path = tmp_path / "SKILL.md"
    path.write_text(f"---\n{frontmatter}\n---\n\ncorpo\n", encoding="utf-8")
    return list(ch.check_file(path, ch.SKILL_FIELDS, ()))


def test_clean_skill_has_no_findings(tmp_path: Path) -> None:
    assert _skill(tmp_path, "name: x\ndescription: Faz X quando Y.") == []


def test_plain_scalar_hash_truncation_is_caught(tmp_path: Path) -> None:
    # caso real da issue-audit: ` #` sem aspas vira comentário YAML
    found = _skill(tmp_path, "description: Audita o CORPO (## Escopo + ## Critério) da issue")
    assert any("truncada" in f for f in found)


def test_quoted_hash_is_fine(tmp_path: Path) -> None:
    assert _skill(tmp_path, 'description: "Audita o CORPO (## Escopo) com \\"aspas\\""') == []


def test_unknown_field_and_invalid_yaml(tmp_path: Path) -> None:
    assert any("desconhecido" in f for f in _skill(tmp_path, "description: x\nallowed_tools: Read"))
    assert any("YAML inválido" in f for f in _skill(tmp_path, "description: a: b: c"))


def test_description_over_listing_cap(tmp_path: Path) -> None:
    long_desc = "x" * (ch.DESC_CAP + 1)
    assert any("cortada" in f for f in _skill(tmp_path, f"description: {long_desc}"))


def test_agent_requires_name_and_description(tmp_path: Path) -> None:
    path = tmp_path / "agent.md"
    path.write_text("---\nmodel: opus\n---\nprompt\n", encoding="utf-8")
    found = ch.check_file(path, ch.AGENT_FIELDS, ("name", "description"))
    assert len([f for f in found if "obrigatório" in f]) == len(("name", "description"))


def test_overrides_must_point_to_existing_skills(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"skillOverrides": {"ghost": "off"}}), encoding="utf-8")
    assert ch.check_overrides(settings, {"real"}) == [
        "skillOverrides aponta skill inexistente: `ghost`"
    ]


# --- estrutura de skill, subagente e hooks (#161) -------------------------------------------


def _skill_dir(root: Path, body: str, name: str = "demo") -> Path:
    skill = root / ".claude" / "skills" / name / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(f"---\nname: {name}\ndescription: x\n---\n{body}", encoding="utf-8")
    return skill


def _layout(root: Path, skill: Path) -> dict[str, str]:
    return dict(ch.check_skill_layout(skill, root))


def test_clean_skill_layout(tmp_path: Path) -> None:
    skill = _skill_dir(tmp_path, "Ver [regra](reference/rule.md) e `scripts/run.py`.\n")
    (skill.parent / "reference").mkdir()
    (skill.parent / "reference" / "rule.md").write_text("# Regra\n", encoding="utf-8")
    (skill.parent / "scripts").mkdir()
    (skill.parent / "scripts" / "run.py").write_text("", encoding="utf-8")

    assert _layout(tmp_path, skill) == {}


def test_body_over_500_lines_counts_only_the_body(tmp_path: Path) -> None:
    at_cap = _skill_dir(tmp_path, "x\n" * ch.SKILL_BODY_CAP, name="at-cap")
    over = _skill_dir(tmp_path, "x\n" * (ch.SKILL_BODY_CAP + 1), name="over")

    assert _layout(tmp_path, at_cap) == {}
    assert list(_layout(tmp_path, over)) == [".claude/skills/over::body"]


def test_reference_must_be_one_level_and_linked(tmp_path: Path) -> None:
    skill = _skill_dir(tmp_path, "sem links\n")
    nested = skill.parent / "reference" / "deep"
    nested.mkdir(parents=True)
    (skill.parent / "reference" / "orphan.md").write_text("# x\n", encoding="utf-8")

    assert set(_layout(tmp_path, skill)) == {
        ".claude/skills/demo/reference/deep::depth",
        ".claude/skills/demo/reference/orphan.md::unlinked",
    }


@pytest.mark.parametrize(
    ("head", "ok"),
    [
        pytest.param("# Tema\n\n## Sumário\n", True, id="titulo-sumario"),
        pytest.param("# Topic\n\n## Contents\n", True, id="titulo-contents"),
        pytest.param("# Tema\n- [A](#a)\n- [B](#b)\n", True, id="links-de-ancora"),
        pytest.param("# Tema\n- [A](#a)\n", False, id="um-link-so"),
        pytest.param("# Tema\n\ntexto\n", False, id="sem-sumario"),
    ],
)
def test_long_reference_needs_a_table_of_contents(tmp_path: Path, head: str, ok: bool) -> None:
    skill = _skill_dir(tmp_path, "[r](references/long.md)\n")
    ref = skill.parent / "references" / "long.md"
    ref.parent.mkdir()
    ref.write_text(head + "linha\n" * ch.TOC_THRESHOLD, encoding="utf-8")

    found = _layout(tmp_path, skill)

    assert (".claude/skills/demo/references/long.md::toc" not in found) is ok


def test_short_reference_needs_no_table_of_contents(tmp_path: Path) -> None:
    skill = _skill_dir(tmp_path, "[r](reference/short.md)\n")
    ref = skill.parent / "reference" / "short.md"
    ref.parent.mkdir()
    ref.write_text("linha\n" * ch.TOC_THRESHOLD, encoding="utf-8")

    assert _layout(tmp_path, skill) == {}


def test_cited_files_must_exist_relative_to_skill_or_root(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "gate.py").write_text("", encoding="utf-8")
    body = (
        "Roda `scripts/gate.py` e `scripts/ghost.py`; ver [doc](docs/missing.md), "
        "[site](https://x.org/a.md), [exemplo](caminho) e [âncora](#topo).\n"
    )
    skill = _skill_dir(tmp_path, body)

    assert set(_layout(tmp_path, skill)) == {
        ".claude/skills/demo::missing:scripts/ghost.py",
        ".claude/skills/demo::missing:docs/missing.md",
    }


def test_agent_skills_must_exist(tmp_path: Path) -> None:
    agent = tmp_path / "agent.md"
    agent.write_text("---\nname: a\ndescription: b\nskills: [real, ghost]\n---\n", encoding="utf-8")

    assert ch.check_agent_skills(agent, {"real"}) == ["`skills:` aponta skill inexistente: `ghost`"]


def test_hook_scripts_must_exist(tmp_path: Path) -> None:
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / ".claude" / "hooks" / "real.py").write_text("", encoding="utf-8")
    hook = {"type": "command", "command": "python"}
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "hooks": [
                                {**hook, "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/real.py"]}
                            ]
                        }
                    ],
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    **hook,
                                    "command": "python ${CLAUDE_PROJECT_DIR}/.claude/hooks/x.py",
                                }
                            ]
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    assert ch.check_hook_scripts(settings, tmp_path) == [
        "hook aponta arquivo inexistente: `.claude/hooks/x.py`"
    ]


def test_known_debt_tolerates_shrinks_and_needs_an_owner() -> None:
    found = {"a/skill::body": "corpo longo", "b/skill::body": "corpo longo"}
    debt = {"a/skill::body": ("legado", 7), "gone::toc": ("legado", 7), "b/skill::body": ("", 7)}

    assert ch.reconcile_debt(found, debt) == [
        "b/skill: corpo longo",
        "KNOWN_DEBT `gone::toc` não ocorre mais (remover a entrada)",
        "KNOWN_DEBT `b/skill::body` sem motivo ou issue (débito sem dono)",
    ]


def test_real_harness_passes() -> None:
    """O harness do repo (skills, subagentes, settings) passa com o débito declarado."""
    assert ch.main() == 0
