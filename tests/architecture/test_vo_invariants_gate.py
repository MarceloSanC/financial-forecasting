"""Regressão do gate `scripts/check_vo_invariants.py` (issue #61).

O gate nasce com baseline cheio (10 VOs → #160); o teste prova que um VO NOVO sem
invariante reprova e que a regra é a estrita decidida na sessão: só `__post_init__` conta —
factory validadora não fecha o construtor cru da dataclass.

Cobre:

- VO congelado sem `__post_init__` reprova, com `@dataclass(frozen=True)` e
  `@dataclasses.dataclass(frozen=True, ...)`;
- factory classmethod que valida NÃO isenta (o caso `QuantileForecast.from_raw`);
- passa: `__post_init__` próprio ou herdado de base do mesmo módulo, dataclass não
  congelada, `frozen=False`, classe comum, `StrEnum`;
- opt-out: marcador com motivo isenta; marcador sem motivo reprova; marcador longe da
  classe não vale;
- só `domain/value_objects/` é varrido;
- o repo real casa exatamente com o baseline; `main()` devolve 1 com VO novo.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
_HEADER = "import dataclasses\nfrom dataclasses import dataclass\nfrom enum import StrEnum\n\n"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_{name}_under_test", _SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gate() -> ModuleType:
    return _load("check_vo_invariants")


@pytest.fixture
def baseline_lib() -> ModuleType:
    return _load("arch_baseline_lib")


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("@dataclass(frozen=True)\nclass Vo:\n    value: str\n", id="dataclass"),
        pytest.param(
            "@dataclasses.dataclass(frozen=True, slots=True)\nclass Vo:\n    value: str\n",
            id="dataclasses-dataclass",
        ),
        pytest.param(
            "@dataclass(frozen=True)\nclass Vo:\n    value: str\n\n"
            "    @classmethod\n    def from_raw(cls, raw: str) -> 'Vo':\n"
            "        if not raw:\n            raise ValueError('vazio')\n"
            "        return cls(value=raw)\n",
            id="factory-validadora-nao-isenta",
        ),
        pytest.param(
            "@dataclass(frozen=True)\nclass Vo:  # vo-invariant: none\n    value: str\n",
            id="marcador-sem-motivo",
        ),
        pytest.param(
            "# vo-invariant: none — longe demais\n\nx = 1\n\n"
            "@dataclass(frozen=True)\nclass Vo:\n    value: str\n",
            id="marcador-fora-da-janela",
        ),
    ],
)
def test_frozen_vo_without_post_init_is_a_violation(gate: ModuleType, body: str) -> None:
    assert list(gate.vo_violations(_HEADER + body)) == ["Vo"]


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            "@dataclass(frozen=True)\nclass Vo:\n    value: str\n\n"
            "    def __post_init__(self) -> None:\n        pass\n",
            id="post-init",
        ),
        pytest.param(
            "@dataclass(frozen=True)\nclass Base:\n    value: str\n\n"
            "    def __post_init__(self) -> None:\n        pass\n\n"
            "@dataclass(frozen=True)\nclass Vo(Base):\n    extra: int\n",
            id="post-init-herdado",
        ),
        pytest.param("@dataclass\nclass Vo:\n    value: str\n", id="nao-congelada"),
        pytest.param("@dataclass(frozen=False)\nclass Vo:\n    value: str\n", id="frozen-false"),
        pytest.param("class Vo:\n    value: str\n", id="classe-comum"),
        pytest.param("class Kind(StrEnum):\n    A = 'a'\n", id="strenum"),
        pytest.param(
            "# vo-invariant: none — rótulo opaco, qualquer string é válida\n"
            "@dataclass(frozen=True)\nclass Vo:\n    value: str\n",
            id="marcador-acima-do-decorador",
        ),
        pytest.param(
            "@dataclass(frozen=True)\nclass Vo:  # vo-invariant: none: wrapper de exibição\n"
            "    value: str\n",
            id="marcador-na-linha-da-classe",
        ),
    ],
)
def test_vo_with_invariant_or_justified_opt_out_passes(gate: ModuleType, body: str) -> None:
    assert gate.vo_violations(_HEADER + body) == {}


def test_marker_without_motivo_is_reported_as_such(gate: ModuleType) -> None:
    body = "@dataclass(frozen=True)\nclass Vo:  # vo-invariant: none —\n    value: str\n"

    assert "sem motivo" in gate.vo_violations(_HEADER + body)["Vo"]


def test_scan_reads_only_domain_value_objects(gate: ModuleType, tmp_path: Path) -> None:
    src = tmp_path / "src" / "financial_forecasting"
    body = _HEADER + "@dataclass(frozen=True)\nclass Vo:\n    value: str\n"
    for rel in (
        "features/x/domain/value_objects/vo.py",
        "shared/domain/value_objects/vo.py",
        "features/x/domain/entities/vo.py",
        "features/x/application/dtos/value_objects/vo.py",
    ):
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    violations = gate.scan(src_root=src, root=tmp_path)

    assert sorted(violations) == [
        "src/financial_forecasting/features/x/domain/value_objects/vo.py::Vo",
        "src/financial_forecasting/shared/domain/value_objects/vo.py::Vo",
    ]


def test_real_repo_matches_the_declared_baseline(
    gate: ModuleType, baseline_lib: ModuleType
) -> None:
    """A dívida medida é exatamente a declarada (#160): nada novo, nada morto."""
    baseline = baseline_lib.load_baseline(gate.GATE)

    new, dead = baseline_lib.reconcile(gate.scan(), baseline)

    assert (new, dead) == ([], [])
    assert {entry.issue for entry in baseline.values()} == {160}


def test_main_exit_code_follows_the_baseline_verdict(
    gate: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main()`: 0 no repo real (baseline casado); 1 com VO novo injetado."""
    monkeypatch.setattr(sys, "argv", ["check_vo_invariants.py", "--list"])
    assert gate.main() == 0
    assert "[vo_invariants] PASSOU" in capsys.readouterr().out

    real = gate.scan()
    monkeypatch.setattr(gate, "scan", lambda: {**real, "src/vo.py::Vo": "sem __post_init__ (L3)"})
    assert gate.main() == 1
    out = capsys.readouterr().out
    assert "src/vo.py::Vo: sem __post_init__ (L3)" in out
    assert "[vo_invariants] REPROVOU" in out
