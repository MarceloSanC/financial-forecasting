"""Paridade dos hooks de ruff/mypy do pre-commit com o `make check` (issue #222).

`make lint` e `make typecheck` rodam `uv run ruff`/`uv run mypy`: a versão sai do
`uv.lock` e a config do `pyproject.toml`. Um hook com `repo:` remoto traz versão própria
(`rev:`) e um env isolado sem as dependências do projeto, e diverge do gate em silêncio:
a #199 mediu o `ruff-pre-commit` v0.6.9 e o `mirrors-mypy` v1.11.2 reprovando código que
o `make check` aprova. Este teste reprova a volta desse arranjo: os hooks de ruff e mypy
têm de ser `local` e chamar a ferramenta pelo `uv run`.

O parser lê só a forma plana do `.pre-commit-config.yaml` (chave: valor por linha), sem
depender de `pyyaml`, que o projeto não declara.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[2]
_CONFIG = _REPO / ".pre-commit-config.yaml"
_MAKEFILE = _REPO / "Makefile"

# Ferramenta de cada hook que tem de rodar pelo venv, e o comando esperado no `entry:`.
_VENV_HOOKS = {
    "ruff-format": "uv run ruff format",
    "ruff": "uv run ruff check",
    "mypy": "uv run mypy",
}
_GATED_TOOLS = ("ruff", "mypy")

_REPO_LINE = re.compile(r"^\s*-\s*repo:\s*(\S+)\s*$")
_ID_LINE = re.compile(r"^\s*-\s*id:\s*(\S+)\s*$")
_KEY_LINE = re.compile(r"^\s*([a-z_]+):\s*(.*?)\s*$")


@dataclass
class Hook:
    """Um hook do config: o `repo:` dono e as chaves escalares dele."""

    repo: str
    id: str
    keys: dict[str, str] = field(default_factory=dict)


def parse_hooks(text: str) -> list[Hook]:
    """Hooks do config, cada um com o `repo:` em que está declarado."""
    hooks: list[Hook] = []
    repo = ""
    current: Hook | None = None
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0] if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        repo_match = _REPO_LINE.match(line)
        if repo_match:
            repo = repo_match.group(1)
            current = None
            continue
        id_match = _ID_LINE.match(line)
        if id_match:
            current = Hook(repo=repo, id=id_match.group(1))
            hooks.append(current)
            continue
        key_match = _KEY_LINE.match(line)
        if key_match and current is not None:
            current.keys[key_match.group(1)] = key_match.group(2)
    return hooks


def parity_violations(text: str) -> list[str]:
    """Motivos pelos quais os hooks de ruff/mypy divergiriam do `make check`."""
    hooks = parse_hooks(text)
    problems: list[str] = []
    for hook in hooks:
        remote_tool = hook.repo != "local" and any(t in hook.repo for t in _GATED_TOOLS)
        if remote_tool:
            problems.append(f"hook {hook.id!r} vem de repo remoto {hook.repo} (versão própria)")
    by_id = {hook.id: hook for hook in hooks}
    for hook_id, command in _VENV_HOOKS.items():
        found = by_id.get(hook_id)
        if found is None:
            problems.append(f"hook {hook_id!r} ausente")
            continue
        entry = found.keys.get("entry", "")
        if found.repo != "local" or not entry.startswith(command):
            problems.append(f"hook {hook_id!r} não roda {command!r} (entry={entry!r})")
    mypy = by_id.get("mypy")
    if mypy is not None and mypy.keys.get("pass_filenames") != "false":
        problems.append("hook 'mypy' precisa de pass_filenames: false (alvos do pyproject)")
    return problems


def test_repo_config_hooks_run_through_the_venv() -> None:
    assert parity_violations(_CONFIG.read_text(encoding="utf-8")) == []


_OLD_CONFIG = """\
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff-format
      - id: ruff
        args: [--fix]
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.2
    hooks:
      - id: mypy
        files: ^src/
"""


def test_pinned_remote_hooks_are_rejected() -> None:
    problems = parity_violations(_OLD_CONFIG)

    assert any("ruff-pre-commit" in p for p in problems)
    assert any("mirrors-mypy" in p for p in problems)
    assert len([p for p in problems if "não roda" in p]) == len(_VENV_HOOKS)


_LOCAL_OK = """\
repos:
  - repo: local
    hooks:
      - id: ruff-format
        entry: uv run ruff format
      - id: ruff
        entry: uv run ruff check --fix  # comentário no fim da linha
      - id: mypy
        entry: uv run mypy
        pass_filenames: false
"""


def test_local_venv_hooks_pass() -> None:
    assert parity_violations(_LOCAL_OK) == []


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("entry: uv run mypy\n", "entry: mypy\n", "não roda 'uv run mypy'"),
        ("pass_filenames: false", "pass_filenames: true", "pass_filenames: false"),
        ("      - id: ruff-format\n        entry: uv run ruff format\n", "", "ausente"),
        ("entry: uv run ruff check --fix", "entry: ruff check --fix", "'uv run ruff check'"),
    ],
)
def test_each_divergence_is_reported(old: str, new: str, expected: str) -> None:
    assert old in _LOCAL_OK
    problems = parity_violations(_LOCAL_OK.replace(old, new))

    assert any(expected in p for p in problems), problems


def test_local_hook_named_like_a_tool_in_a_remote_repo_is_rejected() -> None:
    text = _LOCAL_OK.replace("  - repo: local", "  - repo: https://example.org/mypy-mirror")

    problems = parity_violations(text)

    assert any("repo remoto" in p for p in problems)


def make_target_recipe(text: str, target: str) -> list[str]:
    """Linhas de receita (com tab) do alvo `target:` do Makefile."""
    lines = text.splitlines()
    recipe: list[str] = []
    inside = False
    for line in lines:
        if inside:
            if not line.startswith("\t"):
                break
            recipe.append(line.strip())
        elif line.startswith(f"{target}:"):
            inside = True
    return recipe


def test_make_lint_checks_formatting() -> None:
    """O hook `ruff-format` só concorda com o gate se o gate também checar o formato."""
    recipe = make_target_recipe(_MAKEFILE.read_text(encoding="utf-8"), "lint")

    assert any(line.startswith("uv run ruff format --check") for line in recipe), recipe


def test_make_target_recipe_stops_at_next_target() -> None:
    text = "lint:\n\tuv run ruff check src/\n\nlint-imports:\n\tuv run lint-imports\n"

    assert make_target_recipe(text, "lint") == ["uv run ruff check src/"]
    assert make_target_recipe(text, "lint-imports") == ["uv run lint-imports"]
    assert make_target_recipe(text, "absent") == []
