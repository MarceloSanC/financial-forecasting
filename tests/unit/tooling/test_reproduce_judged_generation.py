"""Smoke test de `scripts/reproduce_judged_generation.py` (Stage 8.2, Task 06; concept A3b).

Dependências falsas (objeto com `hasher`, `refresh_gold`, `build_confirmatory_scorecard` e
`run_confirmatory_evaluation_for` devolvendo um objeto com `_environment.snapshot`), o
`InMemoryPreregistrationSource` com a revisão 0 ancorada e um registro de chamadas em ordem.
Prova só a lógica do driver (ordem, bytes gravados, recusas) — não o wiring de `060537fc`,
que o `--check` naquele commit prova (E2).
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import sys
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    BuildConfirmatoryScorecardCommand,
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    document_bytes,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.ports.out.evaluation_environment import (
    MissingImageIdError,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    PreregistrationAnchor,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
    PreregistrationHash,
)
from tests.fakes.features.evaluation.in_memory_preregistration_source import (
    InMemoryPreregistrationSource,
)
from tests.unit.features.evaluation._preregistration_payload import (
    FloatRefusingHasher,
    valid_payload,
)
from tests.unit.features.evaluation._scorecard_factory import STARTED_AT

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "reproduce_judged_generation.py"
_NAME = "test_plan"
_COHORT = Path("config/cohorts/aapl_confirmatory.toml")
_SNAPSHOT = {"commit": "0" * 40, "code.src": "a" * 64, "env.image_id": "sha256:" + "c" * 64}
_SCORECARD = {"verdict": {"h1": "sustained", "p": 0.25}}


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("reproduce_judged_generation", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


driver = _load()


@dataclass
class _Deps:
    """O `ApplicationDependencies` falso, com o registro de chamadas em ordem."""

    status: RefreshStatus = RefreshStatus.COMPLETED
    snapshot_error: Exception | None = None
    calls: list[tuple[str, object]] = field(default_factory=list)
    hasher: FloatRefusingHasher = field(default_factory=FloatRefusingHasher)

    def snapshot(self) -> dict[str, str]:
        self.calls.append(("snapshot", None))
        if self.snapshot_error is not None:
            raise self.snapshot_error
        return dict(_SNAPSHOT)

    def refresh_gold(self, command: object) -> object:
        self.calls.append(("refresh", command))
        return SimpleNamespace(status=self.status, rows_by_table={"a": 1, "b": 0, "c": 2})

    def build_confirmatory_scorecard(self, command: object) -> object:
        self.calls.append(("scorecard", command))
        return SimpleNamespace(as_mapping=lambda: dict(_SCORECARD))

    def run_confirmatory_evaluation_for(self, cohort: Path, device: str) -> object:
        self.calls.append(("run_for", (cohort, device)))
        return SimpleNamespace(_environment=SimpleNamespace(snapshot=self.snapshot))


def _plan() -> tuple[InMemoryPreregistrationSource, Preregistration, str]:
    payload = valid_payload()
    plan = Preregistration.from_mapping(payload)
    ref = plan.reference(
        PreregistrationHash.compute(hasher=FloatRefusingHasher(), payload=plan.as_payload())
    )
    source = InMemoryPreregistrationSource()
    source.add(
        _NAME,
        0,
        payload,
        PreregistrationAnchor(
            tag=f"preregistration/{ref}",
            commit="0123456789abcdef0123456789abcdef01234567",
            comment_url="https://github.com/example/repo/issues/1#issuecomment-1",
            anchored_at=STARTED_AT - timedelta(days=1),
        ),
    )
    return source, plan, ref


def _reproduce(
    deps: _Deps, root: Path, *, check: bool = False
) -> tuple[int, bytes, str, Preregistration, str]:
    source, plan, ref = _plan()
    out, err = io.BytesIO(), io.StringIO()
    code = driver.reproduce(
        deps=deps,
        source=source,
        data_root=root,
        cohort=_COHORT,
        name=_NAME,
        revision=0,
        preregistration_ref=ref,
        snapshot=deps.snapshot,
        check=check,
        out=out,
        err=err,
    )
    return code, out.getvalue(), err.getvalue(), plan, ref


def _files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")) if root.exists() else []


def test_calls_snapshot_then_refresh_then_scorecard(tmp_path: Path) -> None:
    deps = _Deps()

    code, _, _, plan, ref = _reproduce(deps, tmp_path / "disposable")

    assert code == 0
    assert [name for name, _ in deps.calls] == ["snapshot", "refresh", "scorecard"]
    assert deps.calls[1][1] == refresh_command_from(plan, ref)
    assert deps.calls[2][1] == BuildConfirmatoryScorecardCommand(
        name=_NAME, revision=0, preregistration_ref=ref
    )


def test_writes_environment_before_refresh_and_document_bytes_of_scorecard(
    tmp_path: Path,
) -> None:
    root = tmp_path / "disposable"
    deps = _Deps()
    seen: list[bool] = []
    real_refresh = deps.refresh_gold

    def refresh(command: object) -> object:
        seen.append((root / "reproduction" / "environment.json").is_file())
        return real_refresh(command)

    deps.refresh_gold = refresh  # type: ignore[method-assign]

    code, out, _, _, ref = _reproduce(deps, root)

    assert code == 0
    assert seen == [True]
    environment = (root / "reproduction" / "environment.json").read_bytes()
    scorecard = (root / "reproduction" / "scorecard.json").read_bytes()
    assert environment == document_bytes(_SNAPSHOT)
    assert scorecard == document_bytes(_SCORECARD)
    assert out.decode().splitlines() == [
        f"reproduction {ref}: refresh COMPLETED tables 3",
        f"reproduction {ref}: scorecard sha256 {hashlib.sha256(scorecard).hexdigest()}",
    ]


def test_check_mode_prints_snapshot_and_writes_nothing_nor_refreshes(tmp_path: Path) -> None:
    root = tmp_path / "disposable"
    deps = _Deps()

    code, out, _, _, _ = _reproduce(deps, root, check=True)

    assert code == 0
    assert out == document_bytes(_SNAPSHOT)
    assert [name for name, _ in deps.calls] == ["snapshot"]
    assert _files(root) == []


def test_check_stdout_equals_environment_json_bytes(tmp_path: Path) -> None:
    _, checked, _, _, _ = _reproduce(_Deps(), tmp_path / "check", check=True)
    _reproduce(_Deps(), tmp_path / "normal")

    assert checked == (tmp_path / "normal" / "reproduction" / "environment.json").read_bytes()


@pytest.mark.parametrize("spelling", ["direct", "dotdot", "symlink"])
def test_refuses_data_root_under_data_cohorts(spelling: str, tmp_path: Path) -> None:
    live = tmp_path / "repo" / "data" / "cohorts" / "aapl"
    live.mkdir(parents=True)
    if spelling == "direct":
        root = live
    elif spelling == "dotdot":
        root = tmp_path / "repo" / "data" / "x" / ".." / "cohorts" / "aapl"
    else:
        root = tmp_path / "link"
        root.symlink_to(Path("repo") / "data" / "cohorts" / "aapl")
    deps = _Deps()

    with pytest.raises(driver.RefusedDataRootError, match="data/cohorts"):
        _reproduce(deps, root)
    assert deps.calls == []
    assert _files(live) == []


def _argv(root: Path, *extra: str) -> list[str]:
    return [
        "--data-root",
        str(root),
        "--cohort",
        str(_COHORT),
        "--preregistration",
        _NAME,
        "--revision",
        "0",
        "--preregistration-ref",
        "test_plan-r0-0123456789ab",
        *extra,
    ]


@pytest.mark.parametrize("existing", ["gold", "reproduction"])
@pytest.mark.parametrize("check", [False, True], ids=["normal", "check"])
def test_refuses_existing_gold_or_reproduction(existing: str, check: bool, tmp_path: Path) -> None:
    root = tmp_path / "disposable"
    (root / existing).mkdir(parents=True)
    wired: list[object] = []

    with pytest.raises(driver.RefusedDataRootError, match=existing):
        driver.main(_argv(root, *(["--check"] if check else [])), wire=wired.append)

    assert wired == []  # antes do wiring
    assert _files(root) == [existing]


def test_refresh_not_completed_exits_1_without_scorecard(tmp_path: Path) -> None:
    root = tmp_path / "disposable"
    deps = _Deps(status=RefreshStatus.BLOCKED)

    code, out, err, _, ref = _reproduce(deps, root)

    assert code == driver.EXIT_NOT_COMPLETED
    assert [name for name, _ in deps.calls] == ["snapshot", "refresh"]
    assert _files(root) == ["reproduction", "reproduction/environment.json"]
    assert out.decode() == f"reproduction {ref}: refresh BLOCKED tables 3\n"
    assert "BLOCKED, no scorecard" in err


def test_snapshot_error_propagates_before_any_write(tmp_path: Path) -> None:
    root = tmp_path / "disposable"
    deps = _Deps(snapshot_error=MissingImageIdError("no IMAGE_ID"))

    with pytest.raises(MissingImageIdError):
        _reproduce(deps, root)

    assert [name for name, _ in deps.calls] == ["snapshot"]
    assert _files(root) == []


def test_main_wires_snapshot_from_run_confirmatory_evaluation_for_cpu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfdbinary: pytest.CaptureFixture[bytes]
) -> None:
    source, _, ref = _plan()
    deps = _Deps()
    settings: list[Any] = []
    roots: list[object] = []

    def wire(value: Any) -> _Deps:  # noqa: ANN401 — o `Settings` do driver
        settings.append(value)
        return deps

    def toml_source(*, root: Path) -> InMemoryPreregistrationSource:
        roots.append(root)
        return source

    monkeypatch.setattr(driver, "TomlPreregistrationSource", toml_source)
    argv = _argv(tmp_path / "disposable", "--check")
    argv[argv.index("test_plan-r0-0123456789ab")] = ref

    code = driver.main(argv, wire=wire)

    assert code == 0
    assert deps.calls[0] == ("run_for", (_COHORT, "cpu"))
    assert [name for name, _ in deps.calls] == ["run_for", "snapshot"]
    assert settings[0].data_root == tmp_path / "disposable"
    assert roots == [Path("config/preregistration")]
    assert capfdbinary.readouterr().out == document_bytes(_SNAPSHOT)
