"""Regressão do gate `scripts/check_use_case_deps.py` (issue #61).

Mesma disciplina de `test_layout_rules.py` (`_REAL_VIOLATION_CASES`): **provar que o gate
sabe reprovar**. O repo real nasce verde (a anotação `PersistPredictions` que motivou a
issue já virou o port `PredictionPersister`), então só a violação injetada distingue "os
use cases estão limpos" de "o gate não sabe olhar".

Cobre:

- use case de OUTRO slice anotado — por import direto, sob `if TYPE_CHECKING:`, em string,
  dentro de `X | None` e de `Callable[...]`, e por reexport do pacote `use_cases`;
- classe de `adapters/` (do slice e de `shared/adapters/`) e de `shared/infrastructure/`;
- import relativo resolvido;
- o que NÃO reprova: port, serviço de domínio concreto, use case do mesmo slice, stdlib;
- o repo real, hoje, passa com baseline vazio; `main()` devolve 0 / 1.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
_UC = "src/financial_forecasting/features/modeling/application/use_cases"
_PKG = "financial_forecasting.features"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_{name}_under_test", _SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gate() -> ModuleType:
    return _load("check_use_case_deps")


def _scan(gate: ModuleType, tmp_path: Path, body: str, rel: str = f"{_UC}/train_x.py") -> dict:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return gate.scan(src_root=tmp_path / "src", root=tmp_path)


def _use_case(imports: str, annotation: str) -> str:
    return (
        "from __future__ import annotations\n"
        f"{imports}\n\n"
        "class TrainX:\n"
        f"    def __init__(self, *, collaborator: {annotation}) -> None:\n"
        "        self._c = collaborator\n"
    )


_PERSIST = f"from {_PKG}.analytics_store.application.use_cases.persist_predictions"


@pytest.mark.parametrize(
    ("imports", "annotation", "reason"),
    [
        pytest.param(
            f"{_PERSIST} import PersistPredictions",
            "PersistPredictions",
            "use case do slice `analytics_store`",
            id="use-case-outro-slice",
        ),
        pytest.param(
            f"from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n"
            f"    {_PERSIST} import PersistPredictions",
            "PersistPredictions",
            "use case do slice `analytics_store`",
            id="sob-type-checking",
        ),
        pytest.param(
            f"{_PERSIST} import PersistPredictions as Persist",
            "'Persist'",
            "use case do slice `analytics_store`",
            id="anotacao-em-string-com-alias",
        ),
        pytest.param(
            f"{_PERSIST} import PersistPredictions",
            "PersistPredictions | None",
            "use case do slice `analytics_store`",
            id="uniao-com-none",
        ),
        pytest.param(
            f"from collections.abc import Callable\n{_PERSIST} import PersistPredictions",
            "Callable[[int], PersistPredictions]",
            "use case do slice `analytics_store`",
            id="dentro-de-callable",
        ),
        pytest.param(
            f"from {_PKG}.analytics_store.application import use_cases",
            "use_cases.PersistPredictions",
            "use case do slice `analytics_store`",
            id="reexport-do-pacote",
        ),
        pytest.param(
            f"from {_PKG}.modeling.adapters.out.lightgbm.trainer import LightGbmTrainer",
            "LightGbmTrainer",
            "classe concreta de adapter/infraestrutura",
            id="adapter-do-proprio-slice",
        ),
        pytest.param(
            "from financial_forecasting.shared.adapters.out.store import ParquetStore",
            "ParquetStore",
            "classe concreta de adapter/infraestrutura",
            id="shared-adapters",
        ),
        pytest.param(
            "from financial_forecasting.shared.infrastructure.clock import SystemClock",
            "SystemClock",
            "classe concreta de adapter/infraestrutura",
            id="shared-infrastructure",
        ),
        pytest.param(
            "from ...adapters.out.tft.trainer import TftAdapter",
            "TftAdapter",
            "classe concreta de adapter/infraestrutura",
            id="import-relativo",
        ),
    ],
)
def test_forbidden_collaborator_annotation_is_a_violation(
    gate: ModuleType, tmp_path: Path, imports: str, annotation: str, reason: str
) -> None:
    violations = _scan(gate, tmp_path, _use_case(imports, annotation))

    key = f"{_UC}/train_x.py::TrainX.__init__(collaborator)"
    assert list(violations) == [key]
    assert reason in violations[key]


@pytest.mark.parametrize(
    ("imports", "annotation"),
    [
        pytest.param(
            f"from {_PKG}.modeling.application.ports.out.tft_trainer import TftTrainer",
            "TftTrainer",
            id="port-do-slice",
        ),
        pytest.param(
            f"from {_PKG}.modeling.domain.services.walk_forward_splitter import "
            "WalkForwardSplitter",
            "WalkForwardSplitter",
            id="servico-de-dominio-concreto",
        ),
        pytest.param(
            f"from {_PKG}.modeling.application.use_cases.run_baselines import RunBaselines",
            "RunBaselines",
            id="use-case-do-mesmo-slice",
        ),
        pytest.param(
            "from financial_forecasting.shared.application.ports.out.clock import Clock",
            "Clock",
            id="port-shared",
        ),
        pytest.param("from pathlib import Path", "Path", id="stdlib"),
    ],
)
def test_allowed_collaborator_annotation_passes(
    gate: ModuleType, tmp_path: Path, imports: str, annotation: str
) -> None:
    assert _scan(gate, tmp_path, _use_case(imports, annotation)) == {}


def test_every_parameter_kind_is_inspected(gate: ModuleType, tmp_path: Path) -> None:
    body = (
        f"{_PERSIST} import PersistPredictions as P\n\n"
        "class TrainX:\n"
        "    def __init__(self, a: P, /, b: P, *args: P, c: P, **kw: P) -> None:\n"
        "        pass\n"
    )

    violations = _scan(gate, tmp_path, body)

    assert sorted(key.rsplit("(", 1)[1].rstrip(")") for key in violations) == [
        "a",
        "args",
        "b",
        "c",
        "kw",
    ]


def test_files_outside_use_cases_are_not_scanned(gate: ModuleType, tmp_path: Path) -> None:
    body = _use_case(f"{_PERSIST} import PersistPredictions", "PersistPredictions")

    rel = "src/financial_forecasting/features/modeling/adapters/out/x/runner.py"

    assert _scan(gate, tmp_path, body, rel=rel) == {}


@pytest.mark.parametrize("decorator", ["@dataclass", "@dataclass(frozen=True)", "@dc.dataclass"])
def test_dataclass_use_case_fields_are_constructor_params(
    gate: ModuleType, tmp_path: Path, decorator: str
) -> None:
    body = (
        "import dataclasses as dc\nfrom dataclasses import dataclass\n"
        f"{_PERSIST} import PersistPredictions\n\n"
        f"{decorator}\nclass TrainX:\n    persist: PersistPredictions\n    seed: int = 0\n"
    )

    assert list(_scan(gate, tmp_path, body)) == [f"{_UC}/train_x.py::TrainX.__init__(persist)"]


def test_plain_class_attributes_are_not_constructor_params(
    gate: ModuleType, tmp_path: Path
) -> None:
    body = (
        f"{_PERSIST} import PersistPredictions\n\nclass TrainX:\n    persist: PersistPredictions\n"
    )

    assert _scan(gate, tmp_path, body) == {}


def test_real_repo_passes_with_an_empty_baseline(gate: ModuleType) -> None:
    """Estado de hoje: todo colaborador de use case é port, domínio ou stdlib."""
    assert gate.scan() == {}


def test_main_exit_code_follows_the_baseline_verdict(
    gate: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main()` (o que `make arch-ast` roda): 0 no repo real; 1 com violação injetada."""
    monkeypatch.setattr(sys, "argv", ["check_use_case_deps.py", "--list"])
    assert gate.main() == 0
    assert "[use_case_deps] PASSOU" in capsys.readouterr().out

    injected = {"src/x.py::TrainX.__init__(c)": "anota `y` (use case do slice `z`), L3"}
    monkeypatch.setattr(gate, "scan", lambda: injected)
    assert gate.main() == 1
    out = capsys.readouterr().out
    assert "src/x.py::TrainX.__init__(c): anota `y`" in out
    assert "[use_case_deps] REPROVOU" in out
