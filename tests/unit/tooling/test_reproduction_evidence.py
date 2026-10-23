"""Unit de `scripts/reproduction_evidence.py` (Stage 8.2, Task 06; CB-7, base de A2 e A7).

`env-equal` sobre `ATTEMPTS.jsonl` e foto sintéticos; `ast-equal` sobre um repositório git
temporário com dois commits (sem `GIT_DIR`/`GIT_WORK_TREE` do container).
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "reproduction_evidence.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("reproduction_evidence", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


evidence = _load()

_COMMIT = "0123456789abcdef0123456789abcdef01234567"
_CODE = {"code.src": "a" * 64, "code.uv_lock": "b" * 64}
_ENV = {"env.image_id": "sha256:" + "c" * 64, "env.probe.torch_threads": "6"}


def _started(**changes: object) -> dict[str, object]:
    return {
        "phase": "started",
        "attempt_id": "2026-10-23T08:47:58+00:00",
        "preregistration_ref": "plan-r3-0123456789ab",
        "commit": _COMMIT,
        "code": dict(_CODE),
        "environment": dict(_ENV),
        **changes,
    }


def _snapshot(**changes: str) -> dict[str, str]:
    return {
        "commit": _COMMIT,
        "code_dirty": "false",
        "preregistration_dirty": "false",
        **_CODE,
        **_ENV,
        **changes,
    }


def _files(
    tmp_path: Path, snapshot: dict[str, str], *lines: dict[str, object]
) -> tuple[Path, Path]:
    attempts = tmp_path / "ATTEMPTS.jsonl"
    attempts.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    photo = tmp_path / "environment.json"
    photo.write_text(json.dumps(snapshot), encoding="utf-8")
    return attempts, photo


_REF = "plan-r3-0123456789ab"


def _env_equal(attempts: Path, photo: Path) -> tuple[int, list[str]]:
    out = io.StringIO()
    code = evidence.main(
        ["env-equal", str(attempts), str(photo), "--preregistration-ref", _REF], out=out
    )
    return code, out.getvalue().splitlines()


def test_env_equal_passes_on_identical_keys_and_values(tmp_path: Path) -> None:
    assert _env_equal(*_files(tmp_path, _snapshot(), _started())) == (0, ["ENV_EQUAL"])


def test_env_equal_fails_listing_missing_extra_and_different_keys(tmp_path: Path) -> None:
    snapshot = _snapshot(
        commit="f" * 40,
        code_dirty="true",
        preregistration_dirty="true",
        **{"code.src": "d" * 64, "env.lib.torch": "2.5.1", "surprise": "x"},
    )
    del snapshot["env.probe.torch_threads"]

    code, lines = _env_equal(*_files(tmp_path, snapshot, _started()))

    assert code == 1
    assert lines == [
        f"different commit attempt {_COMMIT} snapshot {'f' * 40}",
        "dirty code_dirty true",
        "dirty preregistration_dirty true",
        f"different code.src attempt {'a' * 64} snapshot {'d' * 64}",
        "missing env.probe.torch_threads",
        "extra env.lib.torch",
        "unexpected surprise",
    ]


def test_env_equal_reads_the_started_line_only(tmp_path: Path) -> None:
    input_read: dict[str, object] = {
        "phase": "input_read",
        "attempt_id": "2026-10-23T08:47:58+00:00",
        "preregistration_ref": "plan-r3-0123456789ab",
        "commit": "e" * 40,
        "code": {"code.src": "e" * 64},
        "environment": {},
    }
    older = _started(commit="9" * 40)

    assert _env_equal(*_files(tmp_path, _snapshot(), older, _started(), input_read)) == (
        0,
        ["ENV_EQUAL"],
    )
    with pytest.raises(ValueError, match="no started line"):
        _env_equal(*_files(tmp_path, _snapshot(), input_read))


def test_env_equal_filters_by_preregistration_ref(tmp_path: Path) -> None:
    """CC2-2: com `--preregistration-ref`, a última `started` DAQUELA referência."""
    other = _started(preregistration_ref="plan-r9-ffffffffffff", commit="9" * 40)
    attempts, photo = _files(tmp_path, _snapshot(), _started(), other)
    ref = ["--preregistration-ref", "plan-r3-0123456789ab"]

    out = io.StringIO()
    assert evidence.main(["env-equal", str(attempts), str(photo), *ref], out=out) == 0
    assert out.getvalue() == "ENV_EQUAL\n"
    with pytest.raises(SystemExit):  # CC3-1: sem a referência, erro de uso
        evidence.main(["env-equal", str(attempts), str(photo)], out=io.StringIO())
    with pytest.raises(ValueError, match="no started line of plan-r0-000000000000"):
        evidence.main(
            [
                "env-equal",
                str(attempts),
                str(photo),
                "--preregistration-ref",
                "plan-r0-000000000000",
            ],
            out=io.StringIO(),
        )


def test_ast_equal_ignores_docstrings_and_joined_fstrings() -> None:
    evidence.self_test()
    left = (
        'class A:\n    """doc a."""\n\n'
        '    def f(self):\n        """x."""\n        return f"a" f"b{1}"\n'
    )
    right = 'class A:\n    def f(self):\n        return f"ab{1}"\n'

    assert evidence.normalized_dump(left) == evidence.normalized_dump(right)


def test_ast_equal_flags_code_change() -> None:
    assert evidence.normalized_dump("x = 1\n") != evidence.normalized_dump("x = 2\n")
    assert evidence.normalized_dump('"""d."""\n') == evidence.normalized_dump("pass\n")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    files = {
        "src/pkg/same.py": '"""Old docstring."""\nx = 1\n',
        "src/pkg/changed.py": "y = 1\n",
        "src/pkg/deleted.py": "z = 1\n",
        "src/pkg/moved.py": "w = 1\nv = 2\nu = 3\n",
        "docs/outside.py": "a = 1\n",
    }
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "a")
    monkeypatch.chdir(root)
    return root


def _commit(repo: Path) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "b")


def _ast_equal(*args: str) -> tuple[int, list[str]]:
    out = io.StringIO()
    code = evidence.main(["ast-equal", *args], out=out)
    return code, out.getvalue().splitlines()


def test_ast_equal_passes_on_docstring_only_diff(repo: Path) -> None:
    (repo / "src/pkg/same.py").write_text('"""New docstring."""\nx = 1\n', encoding="utf-8")
    (repo / "docs/outside.py").write_text("a = 2\n", encoding="utf-8")
    _commit(repo)

    assert _ast_equal("HEAD~1", "HEAD") == (0, ["AST_EQUAL src/pkg/same.py", "files 1 ast_diff 0"])


def test_ast_equal_lists_added_or_deleted_files_apart(repo: Path) -> None:
    (repo / "src/pkg/same.py").write_text('"""New docstring."""\nx = 1\n', encoding="utf-8")
    (repo / "src/pkg/changed.py").write_text("y = 2\n", encoding="utf-8")
    (repo / "src/pkg/deleted.py").unlink()
    (repo / "src/pkg/added.py").write_text("n = 1\n", encoding="utf-8")
    (repo / "src/pkg/moved.py").rename(repo / "src/pkg/renamed.py")
    _commit(repo)

    code, lines = _ast_equal("HEAD~1", "HEAD", "--paths", "src/")

    assert code == 1
    assert lines[-1] == "files 2 ast_diff 1"
    assert set(lines[:-1]) == {
        "AST_DIFF src/pkg/changed.py",
        "AST_EQUAL src/pkg/same.py",
        "ADDED src/pkg/added.py",
        "DELETED src/pkg/deleted.py",
        "RENAMED src/pkg/moved.py -> src/pkg/renamed.py",
    }


def test_ast_equal_added_file_alone_still_exits_1(repo: Path) -> None:
    (repo / "src/pkg/added.py").write_text("n = 1\n", encoding="utf-8")
    _commit(repo)

    assert _ast_equal("HEAD~1", "HEAD") == (1, ["ADDED src/pkg/added.py", "files 0 ast_diff 0"])
