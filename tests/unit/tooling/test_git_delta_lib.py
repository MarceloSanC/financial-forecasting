"""Unit de `scripts/git_delta_lib.py` — delta da branch sem gravar o índice (issue #199).

Os testes rodam `git` num repositório descartável em `tmp_path`.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
_GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OPTIONAL_LOCKS")
_BASE = "origin/develop"
_SPEC = "docs/stages"
# Bem antes de qualquer `stat` gravado no índice: o arquivo fica "stat-dirty".
_PAST_EPOCH_S = 1_000_000_000


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_test_{name}", _SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


lib = _load("git_delta_lib")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _write(root: Path, rel: str, text: str = "x\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Repo com `origin/develop` no commit base; o cwd do teste é a raiz dele."""
    # O container de check exporta GIT_DIR/GIT_WORK_TREE da worktree real; o repo aqui é outro.
    for variable in _GIT_ENV:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "develop")
    for rel in (
        f"{_SPEC}/1.1-a/technical.md",
        f"{_SPEC}/1.1-a/concept.md",
        f"{_SPEC}/1.2-b/technical.md",
        f"{_SPEC}/1.3-c/technical.md",
        f"{_SPEC}/1.4-d/technical.md",
        "README.md",
    ):
        _write(root, rel)
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "update-ref", f"refs/remotes/{_BASE}", "HEAD")
    _git(root, "switch", "-q", "-c", "feature")
    monkeypatch.chdir(root)
    return root


def test_delta_joins_branch_commits_and_every_working_tree_state(repo: Path) -> None:
    _write(repo, f"{_SPEC}/1.1-a/technical.md", "commitado na branch\n")
    _git(repo, "commit", "-q", "-am", "branch")
    _write(repo, f"{_SPEC}/1.2-b/technical.md", "staged\n")
    _git(repo, "add", f"{_SPEC}/1.2-b/technical.md")
    _write(repo, f"{_SPEC}/1.3-c/technical.md", "unstaged\n")
    _write(repo, f"{_SPEC}/9.9-nova/sub/technical.md")  # dentro de diretório untracked
    _write(repo, "README.md", "fora do pathspec\n")

    assert lib.changed_paths(_SPEC, _BASE) == [
        Path(f"{_SPEC}/1.1-a/technical.md"),
        Path(f"{_SPEC}/1.2-b/technical.md"),
        Path(f"{_SPEC}/1.3-c/technical.md"),
        Path(f"{_SPEC}/9.9-nova/sub/technical.md"),
    ]


def test_clean_branch_has_empty_delta(repo: Path) -> None:
    assert lib.changed_paths(_SPEC, _BASE) == []


def test_ignored_file_stays_out_like_ls_files_exclude_standard(repo: Path) -> None:
    _write(repo, ".gitignore", "*.tmp\n")
    _write(repo, f"{_SPEC}/1.1-a/rascunho.tmp")
    assert lib.changed_paths(_SPEC, _BASE) == []


def test_rename_shows_both_names(repo: Path) -> None:
    _git(repo, "mv", f"{_SPEC}/1.4-d/technical.md", f"{_SPEC}/1.4-d/renamed.md")
    _git(repo, "commit", "-q", "-m", "rename")
    assert lib.changed_paths(_SPEC, _BASE) == [
        Path(f"{_SPEC}/1.4-d/renamed.md"),
        Path(f"{_SPEC}/1.4-d/technical.md"),
    ]


def test_path_with_spaces_and_accents_survives_the_parse(repo: Path) -> None:
    _write(repo, f"{_SPEC}/7.3 explicação/technical.md")
    assert lib.changed_paths(_SPEC, _BASE) == [Path(f"{_SPEC}/7.3 explicação/technical.md")]


def test_unknown_base_ref_gives_none(repo: Path) -> None:
    assert lib.changed_paths(_SPEC, "origin/nao-existe") is None


def test_timeout_or_missing_git_gives_none(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _timeout(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired("git", lib._TIMEOUT_S)

    monkeypatch.setattr(lib.subprocess, "run", _timeout)
    assert lib.changed_paths(_SPEC, _BASE) is None

    def _no_git(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(lib.subprocess, "run", _no_git)
    assert lib.changed_paths(_SPEC, _BASE) is None


def test_every_git_call_runs_without_optional_locks(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_run = subprocess.run
    seen: list[tuple[str, str | None]] = []

    def _spy(args: list[str], **kwargs: object) -> object:
        env = kwargs.get("env")
        assert isinstance(env, dict)
        seen.append((args[1], env.get("GIT_OPTIONAL_LOCKS")))
        return real_run(args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(lib.subprocess, "run", _spy)
    lib.changed_paths(_SPEC, _BASE)
    assert seen == [("merge-base", "0"), ("diff", "0"), ("status", "0")]


def _make_index_stale(repo: Path) -> None:
    """Muda o `stat` dos arquivos sem mudar o conteúdo: o índice gravado não bate mais.

    É o estado do container depois de um commit no host, em que o `stat` visto do
    Linux não bate com o que o git do Windows gravou.
    """
    for path in (repo / _SPEC).rglob("*.md"):
        os.utime(path, (_PAST_EPOCH_S, _PAST_EPOCH_S))


def _index_snapshot(repo: Path) -> tuple[bytes, int]:
    index = repo / ".git" / "index"
    return index.read_bytes(), index.stat().st_mtime_ns


def test_porcelain_diff_rewrites_a_stale_index(repo: Path) -> None:
    # controle: prova que o teste abaixo detectaria a escrita que deixava o lock órfão
    _make_index_stale(repo)
    before = _index_snapshot(repo)
    _git(repo, "diff", "--name-only", _BASE, "--", _SPEC)
    assert _index_snapshot(repo) != before


def test_delta_never_writes_a_stale_index(repo: Path) -> None:
    _write(repo, f"{_SPEC}/1.3-c/technical.md", "unstaged\n")
    _make_index_stale(repo)
    before = _index_snapshot(repo)

    assert lib.changed_paths(_SPEC, _BASE) == [Path(f"{_SPEC}/1.3-c/technical.md")]
    assert _index_snapshot(repo) == before
    assert not (repo / ".git" / "index.lock").exists()


@pytest.mark.parametrize(
    ("script", "function", "doc"),
    [
        ("check_stage_issue", "discover_changed_technicals", "technical.md"),
        ("check_concept_directness", "discover_changed_concepts", "concept.md"),
    ],
)
def test_doc_gates_keep_only_their_existing_doc_from_the_delta(
    repo: Path, script: str, function: str, doc: str
) -> None:
    gate = _load(script)
    _write(repo, f"{_SPEC}/1.1-a/technical.md", "mudou\n")
    _write(repo, f"{_SPEC}/1.1-a/concept.md", "mudou\n")
    _write(repo, f"{_SPEC}/1.1-a/notes.md")
    (repo / _SPEC / "1.4-d" / "technical.md").unlink()

    assert getattr(gate, function)() == [Path(f"{_SPEC}/1.1-a/{doc}")]


@pytest.mark.parametrize(
    ("script", "function"),
    [
        ("check_stage_issue", "discover_changed_technicals"),
        ("check_concept_directness", "discover_changed_concepts"),
    ],
)
def test_doc_gates_report_unknown_delta_as_none(
    repo: Path, monkeypatch: pytest.MonkeyPatch, script: str, function: str
) -> None:
    gate = _load(script)
    monkeypatch.setattr(gate, "_BASE_REF", "origin/nao-existe")
    assert getattr(gate, function)() is None
