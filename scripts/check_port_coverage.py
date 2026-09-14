"""Gate de cobertura por port — todo port-out tem fake e suíte `[fake, real]` (issue #62).

Uso:
    python scripts/check_port_coverage.py
    python scripts/check_port_coverage.py --list     # imprime o inventário port → fake → contrato

O que reprova: um `Protocol` definido em `src/**/application/ports/out/*.py` sem
(a) um fake em `tests/fakes/**` **ou** (b) um teste de contrato em `tests/contract/**`
parametrizado sobre as duas pernas. Sem (a) o use case só é testável com mock ou
com o adapter real; sem (b) o fake pode responder diferente do real sem que nada
reprove (LAYOUT §7 "a fake e a implementação real devem passar nos mesmos testes";
ADR 0.0.0021). A #72 é o caso que motivou o gate: o `DatasetAssemblerPort` tinha
fake e não tinha suíte, e o fake emitia `feature_rows` sem missing — o ramo "gate
reprova o dataset" era inalcançável pelo caminho wireado.

Detecção (heurísticas declaradas, todas verificáveis por `--list`):

- **port**: `class X(Protocol)` (base chamada `Protocol`) num módulo de `ports/out/`.
- **fake**: uma classe `FakeX` ou `InMemoryX` em `tests/fakes/**`, onde `X` é o nome do
  port sem o sufixo `Port` (`DatasetAssemblerPort` → `InMemoryDatasetAssembler`). É a
  convenção de nome de todos os 15 fakes do repo.
- **adapter real**: uma classe PÚBLICA definida em `src/**/adapters/**` cujo módulo
  cita o nome do port (todo adapter do repo declara "satisfaz o port `X`" no
  docstring). Classes privadas (`_TftDatasets`, `_LossHistory`…) são auxiliares do
  módulo, não adapters. A heurística é por citação, não por análise de tipos: uma
  classe de adapter que CONSOME o port (o `DatasetAssembler` cita
  `IndicatorCalculator`) também entra na lista — sem falso positivo no gate, porque
  a lista só serve para exigir que o contrato cite ao menos uma delas.
- **contrato `[fake, real]`**: um módulo em `tests/contract/**` que IMPORTA a classe
  do fake E cita (por nome) uma classe de adapter real do port E parametriza
  (`params=`/`parametrize`). O id da perna real é livre (`"real"`, `"duckdb"`…); a
  parametrização condicional (perna real sob `skipif` com `importlib.import_module`,
  como a do `SentimentModel`) conta: o nome da classe real está no arquivo. Havendo
  mais de um módulo candidato, `--list` mostra o que tem o nome do port no arquivo
  (`test_<port>_contract.py`) — o gate só precisa de UM.

Baseline: `scripts/arch_baseline.toml`, seção `[port_coverage]`, entradas
`[[port_coverage.allow]]` com `key = "<Nome do port>"`, `motivo` e `issue`
(mecanismo em `scripts/arch_baseline_lib.py`).

Exit codes: 0 sem violação nova; 1 violação nova ou baseline morto; 2 baseline malformado.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = ROOT / "src" / "financial_forecasting"
FAKES_ROOT = ROOT / "tests" / "fakes"
CONTRACT_ROOT = ROOT / "tests" / "contract"
GATE = "port_coverage"
_FAKE_PREFIXES = ("Fake", "InMemory")
_PARAMETRIZATION = re.compile(r"params=|parametrize")
_IMPORT_STATEMENT = re.compile(r"from\s+[\w.]+\s+import\s+(\([^)]*\)|[^\n]+)", re.MULTILINE)


@dataclass(frozen=True)
class PortCoverage:
    """Inventário de um port: onde está definido, fake, adapters reais e contrato."""

    name: str
    module: Path
    fake: Path | None
    adapters: tuple[str, ...]
    contract: Path | None

    @property
    def violation(self) -> str | None:
        if self.fake is None:
            return "sem fake em tests/fakes/** (esperado Fake<X>/InMemory<X>)"
        if not self.adapters:
            return "nenhum adapter em src/**/adapters/** cita o port"
        if self.contract is None:
            return (
                "fake existe mas nenhum tests/contract/** importa fake + adapter real "
                f"({', '.join(self.adapters)}) com parametrização"
            )
        return None


def find_ports(src_root: Path) -> list[tuple[str, Path]]:
    """`(nome, módulo)` de cada `class X(Protocol)` sob `application/ports/out/`."""
    ports: list[tuple[str, Path]] = []
    for path in sorted(src_root.rglob("*.py")):
        parts = path.parts
        if "ports" not in parts or "out" not in parts or path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                (isinstance(base, ast.Name) and base.id == "Protocol")
                or (isinstance(base, ast.Attribute) and base.attr == "Protocol")
                for base in node.bases
            ):
                ports.append((node.name, path))
    return ports


def class_index(root: Path, *, only_adapters: bool = False) -> dict[str, Path]:
    """`{nome da classe: arquivo}` para toda classe definida sob `root`."""
    index: dict[str, Path] = {}
    for path in sorted(root.rglob("*.py")):
        if path.name == "__init__.py" or (only_adapters and "adapters" not in path.parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                index[node.name] = path
    return index


def fake_names(port: str) -> tuple[str, ...]:
    """Nomes de fake aceitos para `port` (`Fake<X>`, `InMemory<X>`, X sem sufixo `Port`)."""
    stem = port.removesuffix("Port")
    return tuple(f"{prefix}{stem}" for prefix in _FAKE_PREFIXES)


def real_adapter_classes(port: str, adapter_classes: dict[str, Path]) -> tuple[str, ...]:
    """Classes PÚBLICAS de adapter cujo módulo cita `port` (nome inteiro, fronteira de palavra)."""
    pattern = re.compile(rf"\b{re.escape(port)}\b")
    return tuple(
        name
        for name, path in adapter_classes.items()
        if not name.startswith("_") and pattern.search(path.read_text(encoding="utf-8"))
    )


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def imports_class(source: str, class_name: str) -> bool:
    """`True` se `source` importa `class_name` (import simples ou entre parênteses)."""
    return any(
        re.search(rf"\b{re.escape(class_name)}\b", match.group(1))
        for match in _IMPORT_STATEMENT.finditer(source)
    )


def mentions_class(source: str, class_name: str) -> bool:
    """`True` se `source` cita `class_name` (import, `module.Classe` via importlib ou uso)."""
    return re.search(rf"\b{re.escape(class_name)}\b", source) is not None


def inventory(
    src_root: Path = SRC_ROOT,
    fakes_root: Path = FAKES_ROOT,
    contract_root: Path = CONTRACT_ROOT,
) -> list[PortCoverage]:
    """Inventário completo port → fake → adapters reais → contrato."""
    fakes = class_index(fakes_root)
    adapter_classes = class_index(src_root, only_adapters=True)
    contracts = {
        path: path.read_text(encoding="utf-8") for path in sorted(contract_root.rglob("test_*.py"))
    }
    out: list[PortCoverage] = []
    for name, module in find_ports(src_root):
        fake_class = next((candidate for candidate in fake_names(name) if candidate in fakes), None)
        fake_path = fakes.get(fake_class) if fake_class else None
        adapters = real_adapter_classes(name, adapter_classes)
        contract_path: Path | None = None
        if fake_class is not None and adapters:
            stem = _snake(name.removesuffix("Port"))
            # Preferência só de LISTAGEM: o módulo com o nome do port primeiro.
            for path in sorted(contracts, key=lambda p: (stem not in p.name, p)):
                source = contracts[path]
                if (
                    imports_class(source, fake_class)
                    and any(mentions_class(source, adapter) for adapter in adapters)
                    and _PARAMETRIZATION.search(source)
                ):
                    contract_path = path
                    break
        out.append(
            PortCoverage(
                name=name, module=module, fake=fake_path, adapters=adapters, contract=contract_path
            )
        )
    return out


def _load_baseline_lib() -> object:
    spec = importlib.util.spec_from_file_location(
        "_arch_baseline_lib", Path(__file__).resolve().parent / "arch_baseline_lib.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses com annotations adiadas precisam disto
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", action="store_true", help="imprime o inventário")
    args = parser.parse_args()

    ports = inventory()
    if args.list:
        for port in ports:
            fake = port.fake.relative_to(ROOT).as_posix() if port.fake else "-"
            contract = port.contract.relative_to(ROOT).as_posix() if port.contract else "-"
            print(f"{port.name}: fake={fake} adapters={list(port.adapters)} contract={contract}")
    lib: object = _load_baseline_lib()
    baseline = lib.load_baseline(GATE)  # type: ignore[attr-defined]
    violations = {
        port.name: f"{port.violation} [{port.module.relative_to(ROOT).as_posix()}]"
        for port in ports
        if port.violation is not None
    }
    new, dead = lib.reconcile(violations, baseline)  # type: ignore[attr-defined]
    return int(lib.report(GATE, new, dead, len(baseline)))  # type: ignore[attr-defined]


if __name__ == "__main__":
    sys.exit(main())
