"""Contrato do port `RuntimeEnvironmentProbe` (Stage 5.5, A4 / I5).

Nas duas pernas (a `real` entra na Task 23): a foto traz todas as
`REQUIRED_KEYS` como texto e `code_dirty` é `"true"`/`"false"`; duas fotos do
mesmo estado são iguais.

Stage 7.3 (Task 04; CA5, I5): com `cpu`, a foto tem exatamente as chaves de hoje; com
outro device, ganha as `GPU_KEYS` observadas. Na perna real, `torch.cuda.is_available`,
`torch.cuda.get_device_name` e `torch.version.hip` vêm por `monkeypatch`.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
import torch

from financial_forecasting.features.modeling.adapters.out.runtime.git_runtime_environment_probe import (  # noqa: E501
    GitRuntimeEnvironmentProbe,
)
from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    DIRTY_KEY,
    GPU_KEYS,
    REQUIRED_KEYS,
    RuntimeEnvironmentProbe,
)
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)

_COHORT_FILE = "config/cohorts/test.toml"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _repo(tmp_path: Path) -> Path:
    """Repositório git descartável com `src/`, `uv.lock`, o arquivo do cohort e `docs/`."""
    repo = tmp_path / "repo"
    for rel, text in {
        "src/pkg/module.py": "x = 1\n",
        "uv.lock": "lock\n",
        _COHORT_FILE: "name = 'test'\n",
        "docs/notes.md": "notes\n",
    }.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


@pytest.fixture
def isolated_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """O `make check` roda com GIT_DIR/GIT_WORK_TREE da worktree; o repo do teste é outro."""
    for variable in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture(params=["fake", "real"])
def probe(
    request: pytest.FixtureRequest, tmp_path: Path, isolated_git: None
) -> RuntimeEnvironmentProbe:
    if request.param == "fake":
        return InMemoryRuntimeEnvironmentProbe()
    return GitRuntimeEnvironmentProbe(
        repo_root=_repo(tmp_path), cohort_file=_COHORT_FILE, device="cpu"
    )


@pytest.mark.contract
def test_snapshot_has_every_required_key_as_text(probe: RuntimeEnvironmentProbe) -> None:
    snapshot = probe.snapshot()

    assert set(REQUIRED_KEYS) <= set(snapshot)
    assert all(isinstance(value, str) and value for value in snapshot.values())
    assert snapshot[DIRTY_KEY] in {"true", "false"}


@pytest.mark.contract
def test_two_snapshots_of_the_same_state_are_equal(probe: RuntimeEnvironmentProbe) -> None:
    assert probe.snapshot() == probe.snapshot()


# -- só o adapter real: identidade do código ---------------------------------------


def _real(repo: Path) -> GitRuntimeEnvironmentProbe:
    return GitRuntimeEnvironmentProbe(repo_root=repo, cohort_file=_COHORT_FILE, device="cpu")


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_docs_only_commit_does_not_change_the_snapshot(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = _real(repo).snapshot()

    (repo / "docs/notes.md").write_text("more notes\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "docs")

    assert _real(repo).snapshot() == before


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_tracked_change_in_src_marks_dirty_then_changes_identity(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = _real(repo).snapshot()

    (repo / "src/pkg/module.py").write_text("x = 2\n", encoding="utf-8")
    dirty = _real(repo).snapshot()
    _git(repo, "commit", "-q", "-am", "code")
    after = _real(repo).snapshot()

    assert dirty["code_dirty"] == "true"
    assert after["code_dirty"] == "false"
    assert after["code.src"] != before["code.src"]


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_untracked_file_in_src_counts_as_dirty(tmp_path: Path) -> None:
    """Módulo novo não ignorado em `src/` seria importado: conta (decisão do Checkpoint C)."""
    repo = _repo(tmp_path)
    (repo / "src/pkg/new_untracked.py").write_text("y = 1" + chr(10), encoding="utf-8")

    assert _real(repo).snapshot()["code_dirty"] == "true"


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_untracked_file_outside_tracked_paths_does_not_count(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "docs/new_untracked.md").write_text("z" + chr(10), encoding="utf-8")

    assert _real(repo).snapshot()["code_dirty"] == "false"


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_staged_uncommitted_change_counts_as_dirty(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "uv.lock").write_text("lock v2" + chr(10), encoding="utf-8")
    _git(repo, "add", "uv.lock")

    assert _real(repo).snapshot()["code_dirty"] == "true"


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_cohort_file_outside_the_repo_is_an_explicit_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    with pytest.raises(RuntimeError, match="outside the repository"):
        GitRuntimeEnvironmentProbe(
            repo_root=repo, cohort_file=tmp_path / "elsewhere.toml", device="cpu"
        )


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_uncommitted_cohort_file_is_an_explicit_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    probe = GitRuntimeEnvironmentProbe(
        repo_root=repo, cohort_file="config/cohorts/missing.toml", device="cpu"
    )

    with pytest.raises(RuntimeError, match="code identity"):
        probe.snapshot()


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_repo_root_below_the_repository_root_is_an_explicit_error(tmp_path: Path) -> None:
    """F1/G2 (Checkpoint C 24-31): num subdiretório, os pathspecs do `git status`
    não casariam `src` e `code_dirty` sairia sempre "false" — recusa em vez disso."""
    repo = _repo(tmp_path)
    (repo / "src/pkg/module.py").write_text("x = 2" + chr(10), encoding="utf-8")
    probe = GitRuntimeEnvironmentProbe(
        repo_root=repo / "docs", cohort_file="../" + _COHORT_FILE, device="cpu"
    )

    with pytest.raises(RuntimeError, match="not the repository root"):
        probe.snapshot()


@pytest.mark.contract
@pytest.mark.usefixtures("isolated_git")
def test_real_tracked_change_in_the_cohort_file_marks_dirty_then_changes_identity(
    tmp_path: Path,
) -> None:
    """Auditoria de testes (mutação k): o arquivo do cohort entra na identidade e
    no `code_dirty` — editar o spec sem commitar não pode passar por árvore limpa."""
    repo = _repo(tmp_path)
    before = _real(repo).snapshot()

    (repo / _COHORT_FILE).write_text("name = 'changed'" + chr(10), encoding="utf-8")
    dirty = _real(repo).snapshot()
    _git(repo, "commit", "-q", "-am", "cohort")
    after = _real(repo).snapshot()

    assert dirty["code_dirty"] == "true"
    assert after["code_dirty"] == "false"
    assert after["code.cohort_file"] != before["code.cohort_file"]
    assert after["code.src"] == before["code.src"]


# -- Stage 7.3, Task 04: GPU e HIP observados fora do device cpu --------------------

# (gpu disponível, nome do dispositivo 0, torch.version.hip) -> probe com device "rocm"
_GpuProbeFactory = Callable[[bool, str, "str | None"], RuntimeEnvironmentProbe]


@pytest.fixture(params=["fake", "real"])
def gpu_probe(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    isolated_git: None,
    monkeypatch: pytest.MonkeyPatch,
) -> _GpuProbeFactory:
    def build(available: bool, name: str, hip: str | None) -> RuntimeEnvironmentProbe:
        if request.param == "fake":
            return InMemoryRuntimeEnvironmentProbe.with_gpu(available=available, name=name, hip=hip)
        monkeypatch.setattr(torch.cuda, "is_available", lambda: available)
        monkeypatch.setattr(torch.cuda, "get_device_name", lambda index=0: name)
        monkeypatch.setattr(torch.version, "hip", hip)
        return GitRuntimeEnvironmentProbe(
            repo_root=_repo(tmp_path), cohort_file=_COHORT_FILE, device="rocm"
        )

    return build


@pytest.mark.contract
def test_cpu_snapshot_has_exactly_todays_keys(probe: RuntimeEnvironmentProbe) -> None:
    assert set(probe.snapshot()) == set(REQUIRED_KEYS)
    assert not set(GPU_KEYS) & set(REQUIRED_KEYS)


@pytest.mark.contract
def test_non_cpu_snapshot_adds_the_observed_gpu_keys(gpu_probe: _GpuProbeFactory) -> None:
    observed = gpu_probe(True, "AMD Radeon RX 7700 XT", "6.4.43482").snapshot()

    assert set(observed) == {*REQUIRED_KEYS, *GPU_KEYS}
    assert observed["device"] == "rocm"
    assert observed["gpu.available"] == "true"
    assert observed["gpu.name"] == "AMD Radeon RX 7700 XT"
    assert observed["gpu.hip_version"] == "6.4.43482"


@pytest.mark.contract
def test_gpu_keys_are_observed_not_echoed(gpu_probe: _GpuProbeFactory) -> None:
    """Device `rocm` declarado, GPU ausente: a foto diz o que o torch vê."""
    snapshot = gpu_probe(False, "never-read", "6.4.43482").snapshot()

    assert snapshot["device"] == "rocm"
    assert snapshot["gpu.available"] == "false"
    assert snapshot["gpu.name"] == ""


@pytest.mark.contract
def test_absent_hip_is_empty_string(gpu_probe: _GpuProbeFactory) -> None:
    snapshot = gpu_probe(True, "some-gpu", None).snapshot()

    assert snapshot["gpu.hip_version"] == ""
    assert snapshot["gpu.available"] == "true"


@pytest.mark.contract
def test_fake_with_gpu_refuses_the_cpu_device() -> None:
    """O fake não monta uma foto `cpu` com chaves de GPU (o real nunca a produz)."""
    with pytest.raises(ValueError, match="other than cpu"):
        InMemoryRuntimeEnvironmentProbe.with_gpu(device="cpu")
