"""Regenera tree.txt com a árvore do repositório (estrutura visível ao agent).

Uso:
    uv run python scripts/regen_tree.py

Caminha a raiz do projeto e emite a árvore completa, ignorando caches, venv,
build artifacts e o próprio tree.txt. Cobre diretórios principais (src/,
tests/, scripts/, migrations/, docs/, .github/, config/ etc.) e arquivos de
configuração da raiz (pyproject.toml, Makefile, README.md, CLAUDE.md,
.pre-commit-config.yaml, .python-version, .gitignore etc.) automaticamente —
não há lista hardcoded: qualquer dir/arquivo novo na raiz aparece sem
modificar o script.

O tree.txt gerado pode ser colado no CLAUDE.md para dar ao agent uma visão
rápida da estrutura atual sem precisar navegar o repo.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "tree.txt"

# Nomes ignorados em qualquer profundidade da árvore.
IGNORE = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".venv",
    "htmlcov",
    "dist",
    "build",
    "node_modules",
    "tree.txt",   # evita auto-referência ao próprio output
    ".DS_Store",
}


def _should_ignore(path: Path) -> bool:
    if path.name in IGNORE:
        return True
    return path.name.endswith(".egg-info")


def _tree(path: Path, prefix: str = "", is_last: bool = True) -> list[str]:
    connector = "└── " if is_last else "├── "
    lines = [f"{prefix}{connector}{path.name}"]

    if path.is_dir():
        children = sorted(
            [c for c in path.iterdir() if not _should_ignore(c)],
            key=lambda p: (p.is_file(), p.name),
        )
        child_prefix = prefix + ("    " if is_last else "│   ")
        for i, child in enumerate(children):
            lines.extend(_tree(child, child_prefix, is_last=(i == len(children) - 1)))

    return lines


def _force_utf8_stdio() -> None:
    """Garante UTF-8 em stdout/stderr (Windows defaulta cp1252).

    Sem isso, o `print(content)` crasha com UnicodeEncodeError ao tentar
    emitir os caracteres da árvore (├── └── │) no console padrão do
    Windows. O arquivo já foi escrito em UTF-8 antes desse ponto, mas o
    crash do print é assustador para o usuário.
    """
    for stream in (sys.stdout, sys.stderr):
        if stream.encoding and stream.encoding.lower() == "utf-8":
            continue
        with contextlib.suppress(AttributeError, OSError):
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


def main() -> None:
    _force_utf8_stdio()

    lines: list[str] = [f"{ROOT.name}/"]

    children = sorted(
        [c for c in ROOT.iterdir() if not _should_ignore(c)],
        key=lambda p: (p.is_file(), p.name),
    )
    for i, child in enumerate(children):
        lines.extend(_tree(child, prefix="", is_last=(i == len(children) - 1)))

    content = "\n".join(lines) + "\n"
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Escrito: {OUTPUT.relative_to(ROOT)}")
    print(content)


if __name__ == "__main__":
    sys.exit(main())
