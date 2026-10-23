"""Contract test do port `EvaluationEnvironment` — suíte ÚNICA para o fake e o real (A8).

Prova (concept 8.1 A8, D6; ADR 8.1.0003 item 6) que toda implementação devolve a foto com
as chaves do `evaluation` — `commit` de 40 hex, `code_dirty` e `preregistration_dirty`
em `"true"`/`"false"`, `code.*`, `env.image_id`, `env.cpu_capability`, `env.lib.<dist>`
das `GOLD_LIBRARIES` — e, na perna real, que sem o id da imagem a foto é recusada, que
arquivo não rastreado em `config/preregistration` suja a foto, que as chaves do probe da
5.5 são mapeadas sem o módulo do real importar o `modeling`, e que o probe da 5.5 segue
com as mesmas `REQUIRED_KEYS`.

Pernas: `fake` (`InMemoryEvaluationEnvironment`) e `real` (`GitEvaluationEnvironment`
sobre um `git init` em `tmp_path` com um commit de `config/preregistration/x.toml`, probe
= `InMemoryRuntimeEnvironmentProbe` do `modeling`). As fixtures são TIPADAS pelo Protocol
do `evaluation`.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from financial_forecasting.features.evaluation.adapters.out.runtime import (
    git_evaluation_environment as real_module,
)
from financial_forecasting.features.evaluation.adapters.out.runtime.git_evaluation_environment import (  # noqa: E501
    GitEvaluationEnvironment,
)
from financial_forecasting.features.evaluation.application.ports.out.evaluation_environment import (
    CODE_DIRTY_KEY,
    COMMIT_KEY,
    CPU_CAPABILITY_KEY,
    IMAGE_ID_KEY,
    PREREGISTRATION_DIRTY_KEY,
    REQUIRED_KEYS,
    EvaluationEnvironment,
    MissingImageIdError,
    probe_key,
)
from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    CODE_KEYS,
    DIRTY_KEY,
)
from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    REQUIRED_KEYS as PROBE_REQUIRED_KEYS,
)
from tests.fakes.features.evaluation.in_memory_evaluation_environment import (
    InMemoryEvaluationEnvironment,
)
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)

pytestmark = pytest.mark.contract

_PREREGISTRATION = "config/preregistration"
_IMAGE = "sha256:" + "e" * 64
_CODE = {"code.src", "code.uv_lock", "code.cohort_file"}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    plan = repo / _PREREGISTRATION / "x.toml"
    plan.parent.mkdir(parents=True)
    plan.write_text('name = "x"\n', encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _real(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    image_id: str | None = _IMAGE,
    probe: InMemoryRuntimeEnvironmentProbe | None = None,
) -> GitEvaluationEnvironment:
    # O `make check` roda com GIT_DIR/GIT_WORK_TREE da worktree; o repo do teste é outro.
    for variable in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(variable, raising=False)
    repo = _repo(tmp_path)
    return GitEvaluationEnvironment(
        repo_root=repo,
        probe=InMemoryRuntimeEnvironmentProbe() if probe is None else probe,
        probe_keys={key: key for key in CODE_KEYS},
        probe_dirty_key=DIRTY_KEY,
        image_id=image_id,
        cpu_capability=lambda: "AVX2",
        preregistration_dir=repo / _PREREGISTRATION,
    )


ENVIRONMENTS: dict[str, Callable[[Path, pytest.MonkeyPatch], EvaluationEnvironment]] = {
    "fake": lambda _root, _patch: InMemoryEvaluationEnvironment(),
    "real": _real,
}


@pytest.fixture(params=list(ENVIRONMENTS), ids=list(ENVIRONMENTS))
def environment(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> EvaluationEnvironment:
    return ENVIRONMENTS[request.param](tmp_path, monkeypatch)


def test_snapshot_has_every_key(environment: EvaluationEnvironment) -> None:
    snapshot = environment.snapshot()

    assert set(REQUIRED_KEYS) <= set(snapshot)
    assert set(snapshot) >= _CODE
    assert snapshot[IMAGE_ID_KEY]
    assert snapshot[CPU_CAPABILITY_KEY]
    assert all(isinstance(value, str) for value in snapshot.values())
    assert all(
        key.startswith(("code.", "env."))
        for key in set(snapshot)
        - {
            COMMIT_KEY,
            CODE_DIRTY_KEY,
            PREREGISTRATION_DIRTY_KEY,
        }
    )


def test_commit_is_40_hex(environment: EvaluationEnvironment) -> None:
    commit = environment.snapshot()[COMMIT_KEY]

    assert len(commit) == 40  # noqa: PLR2004 — sha-1 do git
    assert set(commit) <= set("0123456789abcdef")


def test_dirty_flags_are_true_or_false(environment: EvaluationEnvironment) -> None:
    snapshot = environment.snapshot()

    assert snapshot[CODE_DIRTY_KEY] in {"true", "false"}
    assert snapshot[PREREGISTRATION_DIRTY_KEY] in {"true", "false"}


# --- só a perna real -------------------------------------------------------------------


@pytest.mark.parametrize("image_id", [None, ""])
def test_without_image_id_refuses_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, image_id: str | None
) -> None:
    with pytest.raises(MissingImageIdError, match="image id"):
        _real(tmp_path, monkeypatch, image_id=image_id).snapshot()


def test_untracked_file_in_preregistration_dir_is_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = _real(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    assert environment.snapshot()[PREREGISTRATION_DIRTY_KEY] == "false"

    (repo / "notes.txt").write_text("outside\n", encoding="utf-8")
    assert environment.snapshot()[PREREGISTRATION_DIRTY_KEY] == "false"

    (repo / _PREREGISTRATION / "x-r3.judged.toml").write_text("x = 1\n", encoding="utf-8")
    assert environment.snapshot()[PREREGISTRATION_DIRTY_KEY] == "true"


def test_probe_keys_mapped_without_importing_modeling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = InMemoryRuntimeEnvironmentProbe(**{DIRTY_KEY: "true", "code.src": "tree-src"})
    snapshot = _real(tmp_path, monkeypatch, probe=probe).snapshot()

    assert snapshot["code.src"] == "tree-src"
    assert snapshot[CODE_DIRTY_KEY] == "true"
    for key in set(PROBE_REQUIRED_KEYS) - set(CODE_KEYS) - {DIRTY_KEY}:
        assert snapshot[probe_key(key)] == f"fake-{key}"
    assert DIRTY_KEY not in {k.removeprefix("env.probe.") for k in snapshot if "probe" in k}
    imported = {
        node.module or ""
        for node in ast.walk(ast.parse(inspect.getsource(real_module)))
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(ast.parse(inspect.getsource(real_module)))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(".modeling" in module for module in imported), imported


def test_probe_key_mapping_must_target_code_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match=r"must map to a code\.\* key"):
        GitEvaluationEnvironment(
            repo_root=tmp_path,
            probe=InMemoryRuntimeEnvironmentProbe(),
            probe_keys={"code.src": "env.src"},
            probe_dirty_key=DIRTY_KEY,
            image_id=_IMAGE,
            cpu_capability=lambda: "AVX2",
            preregistration_dir=_PREREGISTRATION,
        )


def test_modeling_probe_required_keys_unchanged() -> None:
    """A 8.1 não muda a foto da 5.5 (ADR 8.1.0003 item 6: "whose keys are not changed")."""
    assert PROBE_REQUIRED_KEYS == (
        "python",
        "torch",
        "lightning",
        "pytorch-forecasting",
        "lightgbm",
        "statsforecast",
        "optuna",
        "numpy",
        "pandas",
        "pyarrow",
        "exchange-calendars",
        "device",
        "torch_threads",
        "cpu",
        "code.src",
        "code.uv_lock",
        "code.cohort_file",
        "code_dirty",
    )


def test_unmapped_or_missing_code_key_refuses_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CC4-2: chave `code.*` fora do mapa ou chave mapeada ausente não passam caladas."""
    extra = InMemoryRuntimeEnvironmentProbe(**{"code.extra": "tree-extra"})
    with pytest.raises(RuntimeError, match=r"'code\.extra' is not mapped"):
        _real(tmp_path / "a", monkeypatch, probe=extra).snapshot()

    missing = _real(tmp_path / "b", monkeypatch)
    missing._probe_keys["code.gone"] = "code.gone"
    with pytest.raises(RuntimeError, match=r"lacks the mapped code keys \['code\.gone'\]"):
        missing.snapshot()


@pytest.mark.parametrize("dirty", ["True", "", "yes"])
def test_dirty_flag_outside_true_false_refuses_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dirty: str
) -> None:
    """CC4-2: sujeira do probe fora de "true"/"false" nunca vira "limpo"."""
    probe = InMemoryRuntimeEnvironmentProbe(**{DIRTY_KEY: dirty})
    with pytest.raises(RuntimeError, match="must be 'true' or 'false'"):
        _real(tmp_path, monkeypatch, probe=probe).snapshot()
