"""Gate de paridade fake ↔ adapter — reprova bloco de LÓGICA idêntico (issue #62).

Uso:
    python scripts/check_fake_parity.py
    python scripts/check_fake_parity.py --threshold 15 --list   # mostra os maiores blocos

O que reprova: um bloco contíguo de `>= threshold` (default 15) linhas NORMALIZADAS
idêntico entre um arquivo de `tests/fakes/**` e um adapter de `src/**/adapters/**`
(inclui `shared/adapters`). Um fake que carrega a mesma regra do adapter faz a suíte
de contrato `[fake, real]` executar duas cópias do mesmo código — estruturalmente
incapaz de detectar o drift que existe para detectar (issues #66/#70/#71/#75). A
correção que o gate força é a certa: a regra compartilhada sobe para
`domain/services/`, o adapter fica só com a chamada à lib e o fake só com a
aritmética stdlib.

Normalização (o que NÃO conta como lógica):

- comentários (via `tokenize`) e docstrings (via `ast`) removidos; linhas vazias
  descartadas; indentação ignorada;
- **assinatura e passagem de argumentos** descartadas — `def nome(`, `self,`, `*,`,
  `nome: tipo,`, `nome: tipo = default,`, `) -> tipo:`, `)`, `nome=nome,` e
  `Nome,` (item de import/tuple). A assinatura de um `Protocol` é idêntica no fake e
  no adapter POR OBRIGAÇÃO (o contrato), e a lista de kwargs de uma delegação também;
  contá-las mediria o mecanismo errado (F2 da auditoria do PR #87: a assinatura de
  `TftTrainer.train_and_predict` sozinha ocupa 16 linhas não vazias no port);
- linhas de `import`/`from` descartadas.

Blocos são procurados em QUALQUER ordem (não só a subsequência comum mais longa):
um `_validate_contiguous` definido no topo do fake e no meio do adapter é o mesmo
bloco. Mede-se o bloco MÁXIMO por par e reporta-se cada par acima do limiar.

Baseline: `scripts/arch_baseline.toml`, seção `[fake_parity]`, entradas
`[[fake_parity.allow]]` com `key = "<fake rel> <-> <adapter rel>"`, `motivo` e
`issue` — mecanismo em `scripts/arch_baseline_lib.py` (violação fora do baseline
reprova; entrada morta reprova; entrada sem motivo/issue reprova).

Exit codes: 0 sem violação nova; 1 violação nova ou baseline morto; 2 baseline malformado.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import io
import re
import sys
import tokenize
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAKES_ROOT = ROOT / "tests" / "fakes"
SRC_ROOT = ROOT / "src" / "financial_forecasting"
DEFAULT_THRESHOLD = 15
GATE = "fake_parity"

# Linhas de assinatura / passagem de argumentos / import — não são lógica.
_NON_LOGIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(async\s+)?def\s+\w+\($"),  # `def nome(` (assinatura multilinha)
    re.compile(r"^(self|cls),?$"),
    re.compile(r"^\*(\w+)?,?$"),  # `*,` / `*args,`
    re.compile(r"^\*\*\w+,?$"),
    re.compile(r"^\w+:\s*[^=]+?(=\s*[^,]+)?,$"),  # `nome: tipo,` / `nome: tipo = default,`
    re.compile(r"^\)(\s*->\s*.+)?:$"),  # `) -> tipo:` / `):`
    re.compile(r"^\)\s*,?$"),
    re.compile(r"^\w+=\w+(\.\w+)*,?$"),  # `nome=nome,` (kwargs de delegação)
    re.compile(r"^\w+,$"),  # `Nome,` (item de import/tuple)
    re.compile(r"^(from|import)\s"),
    re.compile(r"^@\w+"),  # decorador
    re.compile(r"^\"\"\"|^'''"),  # resíduo de docstring
)


def normalized_lines(path: Path) -> list[tuple[int, str]]:
    """Linhas de LÓGICA de `path`: `(nº da linha original, texto normalizado)`."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
                and body[0].end_lineno is not None
            ):
                docstring_lines.update(range(body[0].lineno, body[0].end_lineno + 1))
    comment_start: dict[int, int] = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            comment_start[token.start[0]] = token.start[1]
    out: list[tuple[int, str]] = []
    for number, raw in enumerate(source.splitlines(), start=1):
        if number in docstring_lines:
            continue
        line = raw[: comment_start[number]] if number in comment_start else raw
        text = line.strip()
        if not text or any(pattern.match(text) for pattern in _NON_LOGIC_PATTERNS):
            continue
        out.append((number, text))
    return out


@dataclass(frozen=True)
class Block:
    """Bloco idêntico: posição inicial em cada arquivo (linha original) + tamanho."""

    fake_line: int
    adapter_line: int
    size: int


def identical_blocks(
    fake: list[tuple[int, str]], adapter: list[tuple[int, str]], min_size: int
) -> list[Block]:
    """Blocos idênticos MÁXIMOS de `>= min_size` linhas, em qualquer ordem."""
    positions: dict[str, list[int]] = defaultdict(list)
    for index, (_, text) in enumerate(adapter):
        positions[text].append(index)
    found: dict[tuple[int, int], int] = {}
    covered: set[tuple[int, int]] = set()  # toda posição (i, j) dentro de um bloco já medido
    for i in range(len(fake)):
        for j in positions.get(fake[i][1], []):
            if (i, j) in covered:  # continuação de um bloco já contado, não um bloco novo
                continue
            size = 0
            while (
                i + size < len(fake)
                and j + size < len(adapter)
                and fake[i + size][1] == adapter[j + size][1]
            ):
                covered.add((i + size, j + size))
                size += 1
            if size >= min_size:
                found[(i, j)] = size
    return [
        Block(fake_line=fake[i][0], adapter_line=adapter[j][0], size=size)
        for (i, j), size in found.items()
    ]


def scan(
    threshold: int,
    *,
    fakes_root: Path = FAKES_ROOT,
    src_root: Path = SRC_ROOT,
    root: Path = ROOT,
) -> dict[str, tuple[Block, ...]]:
    """`{chave do par: blocos >= threshold}` para todo par fake x adapter em violação."""
    fakes = sorted(p for p in fakes_root.rglob("*.py") if p.name != "__init__.py")
    adapters = sorted(
        p for p in src_root.rglob("*.py") if "adapters" in p.parts and p.name != "__init__.py"
    )
    normalized = {path: normalized_lines(path) for path in (*fakes, *adapters)}
    violations: dict[str, tuple[Block, ...]] = {}
    for fake in fakes:
        for adapter in adapters:
            blocks = identical_blocks(normalized[fake], normalized[adapter], threshold)
            if blocks:
                violations[pair_key(fake, adapter, root)] = tuple(
                    sorted(blocks, key=lambda b: -b.size)
                )
    return violations


def pair_key(fake: Path, adapter: Path, root: Path = ROOT) -> str:
    """Chave do par no baseline: caminhos relativos ao repo, separados por ` <-> `."""
    return f"{fake.relative_to(root).as_posix()} <-> {adapter.relative_to(root).as_posix()}"


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
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--list", action="store_true", help="lista o maior bloco de cada par (diagnóstico)"
    )
    args = parser.parse_args()

    violations = scan(args.threshold)
    if args.list:
        for key, blocks in violations.items():
            biggest = blocks[0]
            print(
                f"{key}: {biggest.size} linhas (fake:L{biggest.fake_line} / "
                f"adapter:L{biggest.adapter_line})"
            )
    lib: object = _load_baseline_lib()
    baseline = lib.load_baseline(GATE)  # type: ignore[attr-defined]
    details = {
        key: f"{blocks[0].size} linhas idênticas (fake:L{blocks[0].fake_line} / "
        f"adapter:L{blocks[0].adapter_line})"
        for key, blocks in violations.items()
    }
    new, dead = lib.reconcile(GATE, details, baseline)  # type: ignore[attr-defined]
    return int(lib.report(GATE, new, dead, len(baseline)))  # type: ignore[attr-defined]


if __name__ == "__main__":
    sys.exit(main())
