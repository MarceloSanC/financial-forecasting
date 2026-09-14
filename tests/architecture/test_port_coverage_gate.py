"""Regressão do gate `scripts/check_port_coverage.py` (issue #62).

**Provar que o gate sabe reprovar** (mesma disciplina de `test_layout_rules.py`), em
árvore sintética:

- port sem fake → violação;
- port com fake mas sem contract test que importe o fake E cite o adapter real E
  parametrize → violação (um `tests/contract` que só importa o fake não conta);
- port com fake + contrato `[fake, real]` → coberto (id da perna real livre; adapter
  citado via `importlib` conta);
- o inventário do repo real: exatamente os 3 ports do baseline (`Clock`, `Hasher`,
  `IdGenerator`) e mais nenhum — é o que torna o baseline honesto (a #62 nasceu com o
  diagnóstico de que só o `DatasetAssemblerPort` faltava; a #72 fechou esse, e a
  correção pós-verificação da própria issue listou os três).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_{name}_under_test", _SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gate() -> ModuleType:
    return _load("check_port_coverage")


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


_PORT = (
    "from typing import Protocol\n\n\nclass ProbeFetcher(Protocol):\n"
    "    def fetch(self) -> int: ...\n"
)
_ADAPTER = (
    '"""Satisfaz o port `ProbeFetcher`."""\n\n\nclass _Helper:\n    pass\n\n\n'
    "class HttpProbeFetcher:\n    def fetch(self) -> int:\n        return 1\n"
)
_FAKE = "class FakeProbeFetcher:\n    def fetch(self) -> int:\n        return 1\n"


def _tree(tmp_path: Path, *, fake: bool, contract: str | None) -> tuple[Path, Path, Path]:
    src = tmp_path / "src" / "financial_forecasting"
    _write(src, "features/probe/application/ports/out/probe_fetcher.py", _PORT)
    _write(src, "features/probe/adapters/out/http/http_probe_fetcher.py", _ADAPTER)
    fakes = tmp_path / "tests" / "fakes"
    fakes.mkdir(parents=True)
    if fake:
        _write(fakes, "features/probe/in_memory_probe_fetcher.py", _FAKE)
    contracts = tmp_path / "tests" / "contract"
    contracts.mkdir(parents=True)
    if contract is not None:
        _write(contracts, "features/probe/test_probe_fetcher_contract.py", contract)
    return src, fakes, contracts


def test_port_without_fake_is_a_violation(gate: ModuleType, tmp_path: Path) -> None:
    src, fakes, contracts = _tree(tmp_path, fake=False, contract=None)

    [port] = gate.inventory(src, fakes, contracts)

    assert port.name == "ProbeFetcher"
    assert port.adapters == ("HttpProbeFetcher",)  # `_Helper` (privada) não é adapter
    assert "sem fake" in (port.violation or "")


def test_port_with_fake_but_no_two_leg_contract_is_a_violation(
    gate: ModuleType, tmp_path: Path
) -> None:
    """Um contract test que só importa o fake (sem o real, sem parametrizar) não conta."""
    only_fake = (
        "from tests.fakes.features.probe.in_memory_probe_fetcher import FakeProbeFetcher\n\n"
        "def test_x():\n    assert FakeProbeFetcher().fetch() == 1\n"
    )
    src, fakes, contracts = _tree(tmp_path, fake=True, contract=only_fake)

    [port] = gate.inventory(src, fakes, contracts)

    assert port.fake is not None
    assert port.contract is None
    assert "nenhum tests/contract/**" in (port.violation or "")


@pytest.mark.parametrize(
    "real_reference",
    [
        pytest.param(
            "from financial_forecasting.features.probe.adapters.out.http.http_probe_fetcher "
            "import (\n    HttpProbeFetcher,\n)\n",
            id="import-direto",
        ),
        pytest.param(
            "import importlib\n_m = importlib.import_module(\n"
            '    "financial_forecasting.features.probe.adapters.out.http.http_probe_fetcher"\n)\n'
            "HttpProbeFetcher = _m.HttpProbeFetcher\n",
            id="importlib-lazy",
        ),
    ],
)
def test_two_leg_contract_covers_the_port(
    gate: ModuleType, tmp_path: Path, real_reference: str
) -> None:
    contract = (
        "import pytest\n"
        "from tests.fakes.features.probe.in_memory_probe_fetcher import FakeProbeFetcher\n"
        + real_reference
        + '\n@pytest.fixture(params=[FakeProbeFetcher, HttpProbeFetcher], ids=["fake", "http"])\n'
        "def fetcher(request):\n    return request.param()\n"
    )
    src, fakes, contracts = _tree(tmp_path, fake=True, contract=contract)

    [port] = gate.inventory(src, fakes, contracts)

    assert port.violation is None
    assert port.contract is not None and port.contract.name == "test_probe_fetcher_contract.py"


def test_fake_name_convention_strips_the_port_suffix(gate: ModuleType) -> None:
    assert gate.fake_names("DatasetAssemblerPort") == (
        "FakeDatasetAssembler",
        "InMemoryDatasetAssembler",
    )
    assert gate.fake_names("Clock") == ("FakeClock", "InMemoryClock")


def test_real_repo_violations_are_exactly_the_declared_baseline(gate: ModuleType) -> None:
    """Os 3 ports sem fake hoje — e nenhum port coberto por engano."""
    ports = gate.inventory()
    violating = sorted(port.name for port in ports if port.violation is not None)

    assert violating == ["Clock", "Hasher", "IdGenerator"]
    assert len(ports) >= 18  # noqa: PLR2004 — os 18 ports-out do repo hoje
