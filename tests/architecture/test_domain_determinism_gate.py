"""Regressão do gate `scripts/check_domain_determinism.py` (issue #61).

Gate puramente preventivo: o domínio real nasce limpo, então a única prova de que ele
reprova é a violação injetada (disciplina de `_REAL_VIOLATION_CASES`).

Cobre:

- cada família proibida (relógio, id aleatório, acaso global, sistema operacional,
  arquivo — inclusive `pathlib.Path`, o vizinho moderno de `open`), por
  import direto, com alias e por `from x import y`;
- `random.Random()` sem semente reprova; `random.Random(seed)` e a anotação
  `random.Random` passam (decisão do gate: semente explícita é pura);
- falsos positivos que o gate NÃO pode ter: campo `open: float` de dataclass, parâmetro
  `open`, método `.open()` de objeto local, variável local chamada `time`;
- o sombreamento de `open` é léxico: religado numa função, não esconde o builtin lido em
  outra;
- módulos fora de `domain/` não são varridos;
- o repo real passa com baseline vazio; `main()` devolve 0 / 1.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
_DOMAIN = "src/financial_forecasting/features/evaluation/domain/services"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_{name}_under_test", _SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gate() -> ModuleType:
    return _load("check_domain_determinism")


def _uses(gate: ModuleType, source: str) -> dict[str, list[int]]:
    return gate.forbidden_uses(ast.parse(source), "financial_forecasting.features.x.domain.y")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("import datetime\nx = datetime.datetime.now()", "datetime.datetime.now"),
        pytest.param(
            "from datetime import datetime as dt\nx = dt.utcnow()", "datetime.datetime.utcnow"
        ),
        pytest.param("from datetime import date\nx = date.today()", "datetime.date.today"),
        pytest.param("import time\nx = time.time()", "time.time"),
        pytest.param("from time import perf_counter\nx = perf_counter()", "time.perf_counter"),
        pytest.param("import uuid\nx = uuid.uuid4()", "uuid.uuid4"),
        pytest.param("from uuid import uuid1\nx = uuid1()", "uuid.uuid1"),
        pytest.param("import secrets\nx = secrets.token_hex()", "secrets.token_hex"),
        pytest.param("import random\nx = random.random()", "random.random"),
        pytest.param("import random\nrandom.seed(1)", "random.seed"),
        pytest.param("from random import choice\nx = choice([1])", "random.choice"),
        pytest.param("import random\nx = random.SystemRandom()", "random.SystemRandom"),
        pytest.param("import random\nx = random.Random()", "random.Random()"),
        pytest.param("from random import Random\nx = Random()", "random.Random()"),
        pytest.param("import os\nx = os.environ['X']", "os.environ"),
        pytest.param("import os\nx = os.environ.get('X')", "os.environ", id="environ-get"),
        pytest.param("from os import environ\nx = environ.get('X')", "os.environ"),
        pytest.param("import secrets as s\nx = s.SystemRandom().random()", "secrets.SystemRandom"),
        pytest.param("from os import getenv\nx = getenv('X')", "os.getenv"),
        pytest.param("import os\nx = os.urandom(8)", "os.urandom"),
        pytest.param("x = open('f').read()", "open"),
        pytest.param("import io\nx = io.open('f')", "io.open"),
        pytest.param("from pathlib import Path\nx = Path('a').read_text()", "pathlib.Path"),
        pytest.param("import pathlib\nwith pathlib.Path('a').open() as f: ...", "pathlib.Path"),
        pytest.param("import os\nx = os.listdir('.')", "os.listdir"),
        pytest.param("import os.path\nx = os.path.exists('a')", "os.path"),
        pytest.param("import shutil\nshutil.copy('a', 'b')", "shutil.copy"),
        pytest.param("import subprocess\nsubprocess.run(['ls'])", "subprocess.run"),
        pytest.param(
            "from socket import create_connection as c\nc(('h', 1))", "socket.create_connection"
        ),
        pytest.param("import tempfile\nx = tempfile.mkdtemp()", "tempfile.mkdtemp"),
        pytest.param("from glob import glob\nx = glob('*')", "glob.glob"),
        pytest.param("import datetime\nagora = datetime.datetime.now\n", "datetime.datetime.now"),
    ],
)
def test_nondeterministic_source_is_a_violation(
    gate: ModuleType, source: str, expected: str
) -> None:
    assert list(_uses(gate, source)) == [expected]


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("import random\nrng = random.Random(42)\nx = rng.random()", id="seeded"),
        pytest.param("import random\nrng = random.Random(seed=7)", id="seeded-kw"),
        pytest.param("import random\ndef f(rng: random.Random) -> None: ...", id="annotation"),
        pytest.param("from datetime import datetime\ndef f(t: datetime) -> None: ...", id="tipo"),
        pytest.param(
            "from dataclasses import dataclass\n@dataclass\nclass C:\n    open: float\n",
            id="campo-open",
        ),
        pytest.param("def body(open: float, close: float) -> float:\n    return close - open\n"),
        pytest.param("def f(handle) -> None:\n    handle.open()\n", id="metodo-open"),
        pytest.param("def f(time) -> int:\n    return time.time\n", id="local-time"),
        pytest.param("from datetime import timedelta\nx = timedelta(days=1)", id="timedelta"),
        pytest.param(
            "from pathlib import PurePosixPath\nx = PurePosixPath('a') / 'b'", id="pure-path"
        ),
    ],
)
def test_deterministic_code_passes(gate: ModuleType, source: str) -> None:
    assert _uses(gate, source) == {}


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            "def body(open: float, close: float) -> float:\n    return close - open\n\n"
            "def load() -> str:\n    return open('cfg.json').read()\n",
            id="parametro-open-em-outra-funcao",
        ),
        pytest.param(
            "from dataclasses import dataclass\n@dataclass\nclass C:\n    open: float\n\n"
            "x = open('f')\n",
            id="campo-open-nao-sombreia-o-modulo",
        ),
        pytest.param(
            "f = lambda open: open\nx = open('f')\n",
            id="lambda-open-sombreia-so-a-lambda",
        ),
    ],
)
def test_open_shadowing_is_lexical_not_module_wide(gate: ModuleType, source: str) -> None:
    """Um `open` religado num escopo não esconde o builtin lido em outro."""
    assert list(_uses(gate, source)) == ["open"]


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("open = print\nopen('x')\n", id="religado-no-modulo"),
        pytest.param("def f(open):\n    return [open(1) for _ in ()]\n", id="dentro-da-funcao"),
        pytest.param("from io import StringIO as open\nx = open('s')\n", id="import-como-open"),
    ],
)
def test_open_rebound_in_the_same_scope_is_not_the_builtin(gate: ModuleType, source: str) -> None:
    assert _uses(gate, source) == {}


def test_scan_only_reads_domain_modules(gate: ModuleType, tmp_path: Path) -> None:
    body = "import time\nx = time.time()\n"
    for rel in (
        f"{_DOMAIN}/clocky.py",
        "src/financial_forecasting/shared/domain/value_objects/clocky.py",
        "src/financial_forecasting/features/evaluation/application/use_cases/clocky.py",
        "src/financial_forecasting/shared/infrastructure/clocky.py",
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    violations = gate.scan(src_root=tmp_path / "src", root=tmp_path)

    assert violations == {
        f"{_DOMAIN}/clocky.py::time.time": "linhas L2",
        "src/financial_forecasting/shared/domain/value_objects/clocky.py::time.time": "linhas L2",
    }


def test_real_repo_passes_with_an_empty_baseline(gate: ModuleType) -> None:
    """Estado de hoje: o domínio não lê relógio, acaso global, ambiente nem arquivo."""
    assert gate.scan() == {}


def test_main_exit_code_follows_the_baseline_verdict(
    gate: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main()` (o que o `make check` roda): 0 no repo real; 1 com violação injetada."""
    monkeypatch.setattr(sys, "argv", ["check_domain_determinism.py", "--list"])
    assert gate.main() == 0
    assert "[domain_determinism] PASSOU" in capsys.readouterr().out

    monkeypatch.setattr(gate, "scan", lambda: {"src/d.py::time.time": "linhas L3"})
    assert gate.main() == 1
    out = capsys.readouterr().out
    assert "src/d.py::time.time: linhas L3" in out
    assert "[domain_determinism] REPROVOU" in out
