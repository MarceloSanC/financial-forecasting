"""Guard: número de ADR é único e o `adr_id` bate com o nome do arquivo.

Plugado em `make docs-check`. Enforça a numeração de CONVENTIONS.md §1:
o ADR vive em `docs/adr/N_M_NNNN-<slug>.md` com `adr_id: N.M.NNNN` no
frontmatter, e `NNNN` é sequencial dentro do prefixo `N_M` — sem reciclar,
portanto sem dois ADRs com o mesmo número.

Por que existe (issue #190): duas branches em voo podem escolher o mesmo
número de ADR e nada percebia. Em 2026-10-18 a #161 mergeou a
`0_0_0058-architecture-harness-gate-hook-agent.md` enquanto a #185 tinha
a `0_0_0058-planned-full-gate-budget-per-stage.md`; os demais scripts do
`docs-check` passaram com os dois `0_0_0058-*` lado a lado e só o rebase
manual revelou a colisão.

Regras (cada violação aponta os arquivos envolvidos):

1. o nome do arquivo segue `N_M_NNNN-<slug>.md` (sem o prefixo não há
   número a comparar, e a colisão passaria despercebida);
2. o frontmatter declara `adr_id` e ele é o prefixo do nome com pontos
   (`0_0_0058-x.md` -> `0.0.0058`); aspas YAML em volta são aceitas;
3. dois arquivos não compartilham o mesmo prefixo `N_M_NNNN`;
4. dois arquivos não compartilham o mesmo `adr_id`.

Só o bloco de frontmatter é inspecionado — um `adr_id:` citado no corpo
(ex.: um exemplo de frontmatter) não é a declaração.

Exit codes:
  0  numeração válida
  1  violações encontradas (arquivos + motivo em stderr)
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = REPO_ROOT / "docs" / "adr"

# `N_M_NNNN-<slug>.md` — N e M inteiros, NNNN com 4 dígitos (CONVENTIONS §1).
_FILENAME = re.compile(r"^(?P<n>\d+)_(?P<m>\d+)_(?P<seq>\d{4})-[^/]+\.md$")


def _display(path: Path) -> str:
    """Caminho relativo ao repo quando possível (mensagem legível)."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _frontmatter(text: str) -> list[str] | None:
    """Linhas entre as duas primeiras cercas `---`, ou None se ausente."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i]
    return None


def expected_adr_id(path: Path) -> str | None:
    """`adr_id` que o nome do arquivo impõe, ou None se o nome foge do padrão."""
    match = _FILENAME.match(path.name)
    if match is None:
        return None
    return f"{match['n']}.{match['m']}.{match['seq']}"


def declared_adr_id(path: Path) -> str | None:
    """`adr_id` declarado no frontmatter (sem aspas), ou None se ausente."""
    fm = _frontmatter(path.read_text(encoding="utf-8-sig"))
    if fm is None:
        return None
    for line in fm:
        if line.startswith("adr_id:"):
            value = line.split(":", 1)[1].strip()
            return value.strip("'\"").strip() or None
    return None


def _duplicates(groups: dict[str, list[Path]], what: str) -> list[str]:
    return [
        f"{what} {key} repetido em: " + ", ".join(_display(p) for p in sorted(paths))
        for key, paths in sorted(groups.items())
        if len(paths) > 1
    ]


def check_paths(paths: list[Path]) -> list[str]:
    """Todas as violações de numeração do conjunto de ADRs dado."""
    violations: list[str] = []
    by_prefix: dict[str, list[Path]] = defaultdict(list)
    by_adr_id: dict[str, list[Path]] = defaultdict(list)

    for path in sorted(paths):
        expected = expected_adr_id(path)
        declared = declared_adr_id(path)
        if expected is None:
            violations.append(
                f"{_display(path)}: nome fora do padrao `N_M_NNNN-<slug>.md` (CONVENTIONS §1)"
            )
        else:
            by_prefix[expected].append(path)
            if declared != expected:
                violations.append(
                    f"{_display(path)}: adr_id={declared!r} nao bate com o "
                    f"prefixo do nome do arquivo (esperado {expected!r})"
                )
        if declared is not None:
            by_adr_id[declared].append(path)

    violations.extend(_duplicates(by_prefix, "numero de ADR"))
    violations.extend(_duplicates(by_adr_id, "adr_id"))
    return violations


def main(adr_dir: Path = ADR_DIR) -> int:
    violations = check_paths(list(adr_dir.glob("*.md")))
    if violations:
        print("check_adr_numbering: numeracao de ADR invalida", file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
