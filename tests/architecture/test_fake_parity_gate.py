"""Regressão do gate `scripts/check_fake_parity.py` (issue #62).

Mesma disciplina de `test_layout_rules.py`: **provar que o gate sabe reprovar**. Um
gate que nunca foi visto reprovando não distingue "os fakes estão limpos" de "eu não
sei olhar" — e este nasce com baseline VAZIO (os #66/#70/#71/#75 já consertaram os
pares do repo), o que torna a prova por violação injetada obrigatória.

Cobre:

- bloco de LÓGICA idêntico `>= threshold` entre um fake e um adapter em árvore
  sintética → violação nomeando o par e o tamanho; em QUALQUER ordem (o bloco no topo
  do fake e no meio do adapter);
- assinatura do port + kwargs de delegação idênticos (o contrato) NÃO contam — é o
  que torna o limiar 15 honesto (F2 da auditoria do PR #87);
- comentários/docstrings/imports não contam;
- bloco abaixo do limiar não reprova;
- baseline: entrada casada tolera; entrada morta reprova; entrada sem motivo/issue
  reprova (`exit 2`);
- o repo real, hoje, passa com baseline vazio (a asserção que fixa o estado que os
  #66/#70/#71/#75 conquistaram).
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
    return _load("check_fake_parity")


@pytest.fixture
def baseline_lib() -> ModuleType:
    return _load("arch_baseline_lib")


_LOGIC_BLOCK = "\n".join(
    f"    if value_{i} > threshold_{i}:\n        total += weight_{i} * value_{i}" for i in range(9)
)  # 18 linhas de lógica normalizada


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_identical_logic_block_is_a_violation_in_any_order(
    gate: ModuleType, tmp_path: Path
) -> None:
    fake = _write(
        tmp_path,
        "tests/fakes/features/probe/in_memory_probe.py",
        "def rule(value_0=0, threshold_0=0, total=0):\n" + _LOGIC_BLOCK + "\n    return total\n\n"
        "class InMemoryProbe:\n    pass\n",
    )
    adapter = _write(
        tmp_path,
        "src/financial_forecasting/features/probe/adapters/out/lib/probe_adapter.py",
        "class ProbeAdapter:\n    pass\n\n\ndef _rule(value_0=0, threshold_0=0, total=0):\n"
        + _LOGIC_BLOCK
        + "\n    return total\n",
    )

    blocks = gate.identical_blocks(gate.normalized_lines(fake), gate.normalized_lines(adapter), 15)

    assert len(blocks) == 1
    assert blocks[0].size >= 18  # noqa: PLR2004 — as 18 linhas do bloco injetado (+ `return`)


def test_port_signature_and_delegation_kwargs_do_not_count(
    gate: ModuleType, tmp_path: Path
) -> None:
    """A assinatura de um Protocol é idêntica por obrigação: 16 linhas dela não são lógica."""
    signature = (
        "class Impl:\n"
        "    def train_and_predict(\n        self,\n        *,\n"
        + "".join(f"        param_{i}: int,\n" for i in range(12))
        + "    ) -> int:\n"
        "        return run(\n"
        + "".join(f"            param_{i}=param_{i},\n" for i in range(12))
        + "        )\n"
    )
    fake = _write(tmp_path, "tests/fakes/x/in_memory_x.py", signature)
    adapter = _write(tmp_path, "src/financial_forecasting/x/adapters/out/y/x_adapter.py", signature)

    lines = gate.normalized_lines(fake)

    assert [text for _, text in lines] == ["class Impl:", "return run("]
    assert gate.identical_blocks(lines, gate.normalized_lines(adapter), 15) == []


def test_comments_docstrings_and_imports_do_not_count(gate: ModuleType, tmp_path: Path) -> None:
    docstring = '"""Docstring com muitas linhas\n' + ("linha\n" * 20) + '"""\n'
    imports = "from a import (\n" + "".join(f"    Name{i},\n" for i in range(16)) + ")\n"
    comments = "# comentário\n" * 16
    body = docstring + imports + comments + "x = 1  # trailing\n"
    path = _write(tmp_path, "tests/fakes/z/in_memory_z.py", body)

    assert [text for _, text in gate.normalized_lines(path)] == ["x = 1"]


def test_block_below_threshold_is_not_a_violation(gate: ModuleType, tmp_path: Path) -> None:
    small = "\n".join(f"total += value_{i}" for i in range(14)) + "\n"
    fake = _write(tmp_path, "tests/fakes/w/in_memory_w.py", small)
    adapter = _write(tmp_path, "src/financial_forecasting/w/adapters/out/v/w_adapter.py", small)

    assert (
        gate.identical_blocks(gate.normalized_lines(fake), gate.normalized_lines(adapter), 15) == []
    )
    assert (
        len(gate.identical_blocks(gate.normalized_lines(fake), gate.normalized_lines(adapter), 14))
        == 1
    )


def test_scan_reports_violating_pairs_by_key(gate: ModuleType, tmp_path: Path) -> None:
    fake = _write(
        tmp_path,
        "tests/fakes/p/in_memory_p.py",
        "def rule(value_0=0, threshold_0=0, total=0):\n" + _LOGIC_BLOCK + "\n",
    )
    adapter = _write(
        tmp_path,
        "src/financial_forecasting/p/adapters/out/q/p_adapter.py",
        "def rule(value_0=0, threshold_0=0, total=0):\n" + _LOGIC_BLOCK + "\n",
    )
    _write(tmp_path, "src/financial_forecasting/p/domain/clean.py", "x = 1\n")

    violations = gate.scan(
        15,
        fakes_root=tmp_path / "tests" / "fakes",
        src_root=tmp_path / "src" / "financial_forecasting",
        root=tmp_path,
    )

    assert list(violations) == [
        f"{fake.relative_to(tmp_path).as_posix()} <-> {adapter.relative_to(tmp_path).as_posix()}"
    ]


def test_baseline_tolerates_matching_entry_and_flags_dead_entry(
    baseline_lib: ModuleType, tmp_path: Path
) -> None:
    toml = tmp_path / "arch_baseline.toml"
    toml.write_text(
        '[[fake_parity.allow]]\nkey = "a <-> b"\nmotivo = "débito medido"\nissue = 62\n'
        '[[fake_parity.allow]]\nkey = "morta <-> morta"\nmotivo = "já consertado"\nissue = 75\n',
        encoding="utf-8",
    )
    baseline = baseline_lib.load_baseline("fake_parity", toml)

    new, dead = baseline_lib.reconcile(
        "fake_parity", {"a <-> b": "18 linhas", "c <-> d": "20 linhas"}, baseline
    )

    assert new == ["c <-> d: 20 linhas"]
    assert dead == ["morta <-> morta (motivo: já consertado; issue #75)"]
    assert baseline_lib.report("fake_parity", new, dead, len(baseline)) == 1
    assert baseline_lib.report("fake_parity", [], [], 1) == 0


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param('key = "a <-> b"\nissue = 62\n', id="sem-motivo"),
        pytest.param('key = "a <-> b"\nmotivo = "x"\n', id="sem-issue"),
        pytest.param('key = "a <-> b"\nmotivo = "x"\nissue = 0\n', id="issue-zero"),
        pytest.param('motivo = "x"\nissue = 62\n', id="sem-key"),
        pytest.param(
            'key = "a <-> b"\nmotivo = "x"\nissue = 62\n[[fake_parity.allow', id="toml-invalido"
        ),
    ],
)
def test_baseline_entry_without_motivo_or_issue_is_rejected(
    baseline_lib: ModuleType, tmp_path: Path, entry: str
) -> None:
    toml = tmp_path / "arch_baseline.toml"
    toml.write_text("[[fake_parity.allow]]\n" + entry, encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        baseline_lib.load_baseline("fake_parity", toml)
    assert raised.value.code == 2  # noqa: PLR2004 — exit 2 = baseline malformado


def test_baseline_allow_that_is_not_a_list_of_tables_is_rejected(
    baseline_lib: ModuleType, tmp_path: Path
) -> None:
    toml = tmp_path / "arch_baseline.toml"
    toml.write_text('[fake_parity]\nallow = "a <-> b"\n', encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        baseline_lib.load_baseline("fake_parity", toml)
    assert raised.value.code == 2  # noqa: PLR2004 — exit 2 = baseline malformado


def test_real_repo_passes_with_an_empty_baseline(gate: ModuleType) -> None:
    """Estado conquistado pelos #66/#70/#71/#75: nenhum par com lógica idêntica >= 15."""
    assert gate.scan(gate.DEFAULT_THRESHOLD) == {}


def test_main_exit_code_follows_the_baseline_verdict(
    gate: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main()` (o que `make fake-parity` roda): 0 no repo real; 1 com violação injetada."""
    monkeypatch.setattr(sys, "argv", ["check_fake_parity.py", "--list"])
    assert gate.main() == 0
    assert "[fake_parity] PASSOU" in capsys.readouterr().out

    injected = {
        "tests/fakes/x.py <-> src/y.py": (gate.Block(fake_line=1, adapter_line=1, size=20),)
    }
    monkeypatch.setattr(gate, "scan", lambda threshold: injected)
    assert gate.main() == 1
    out = capsys.readouterr().out
    assert "tests/fakes/x.py <-> src/y.py: 20 linhas" in out
    assert "[fake_parity] REPROVOU" in out
