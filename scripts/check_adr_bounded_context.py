"""Guard: todo ADR declara um `bounded_context` do conjunto do roadmap.

Plugado em `make docs-check`. Enforça o campo de rastreabilidade de
CONVENTIONS.md §2: cada frontmatter de ADR carrega um `bounded_context`
cujo valor é um dos BCs que o projeto de fato declara em
`docs/roadmap.md` — não se cunha keyword de BC nova dentro de um ADR.

Por que existe: "ADRs do mesmo bounded context" é uma etapa de carga de
contexto do fluxo de Stage (`PROMPT-stage-single-session.md`). Sem um
campo de primeira classe, essa recuperação é julgamento frágil em prosa;
com ele, o conjunto do mesmo BC é um `grep` só. O conjunto válido é
**extraído do roadmap** (token inicial de cada linha YAML
`bounded_context:`), nunca hardcoded aqui, para que os dois não divirjam.

Único valor aceito fora do roadmap: `transversal`, reservado a ADR de
**numeração global** (`0_0_*`, `1_1_*`), cuja decisão não pertence a BC
nenhum. Não confundir com `shared`, que é o BC do código transversal
(`src/*/shared/`) e vem do roadmap como qualquer outro.

Regra de backfill (CONVENTIONS §2): ADR global carrega `transversal`;
todo outro herda o BC da sua `context_stage` conforme o roadmap.

Só o bloco de frontmatter é inspecionado — uma menção a
`bounded_context:` no corpo do ADR (ex.: um *exemplo* de frontmatter
dentro do ADR 0.0.0003) não é a declaração.

Exit codes:
  0  todos os ADRs válidos
  1  violações encontradas (arquivo + motivo em stderr)
  2  não foi possível derivar o conjunto de BCs do roadmap (fail closed)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROADMAP = REPO_ROOT / "docs" / "roadmap.md"
ADR_GLOB = "docs/adr/*.md"

# Valor reservado a ADR de numeração global — não vem do roadmap porque
# a decisão global não pertence a BC nenhum (CONVENTIONS §2).
GLOBAL_BC = "transversal"

# Token inicial de uma linha YAML `bounded_context:` (ex.
# "shared (fundação)" -> "shared").
_BC_LINE = re.compile(r"^bounded_context:\s*([a-z_]+)", re.MULTILINE)


def valid_bounded_contexts() -> set[str]:
    """Conjunto de BCs que o roadmap declara, mais o global reservado."""
    # utf-8-sig: alguns docs carregam BOM; remover de forma transparente.
    text = ROADMAP.read_text(encoding="utf-8-sig")
    return set(_BC_LINE.findall(text)) | {GLOBAL_BC}


def _frontmatter(text: str) -> list[str] | None:
    """Linhas entre as duas primeiras cercas `---`, ou None se ausente."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i]
    return None


def check_adr(path: Path, valid: set[str]) -> str | None:
    """Retorna a mensagem de violação, ou None se o ADR está válido."""
    fm = _frontmatter(path.read_text(encoding="utf-8-sig"))
    rel = path.relative_to(REPO_ROOT)
    if fm is None:
        return f"{rel}: frontmatter YAML ausente ou malformado"
    declared = [line for line in fm if line.startswith("bounded_context:")]
    if not declared:
        return f"{rel}: falta `bounded_context` no frontmatter"
    value = declared[0].split(":", 1)[1].strip()
    if value not in valid:
        return (
            f"{rel}: bounded_context='{value}' nao esta no conjunto do "
            f"roadmap ({', '.join(sorted(valid))})"
        )
    return None


def main() -> int:
    valid = valid_bounded_contexts()
    if valid == {GLOBAL_BC}:
        print(
            "check_adr_bounded_context: nenhum `bounded_context` no roadmap "
            "— nao ha conjunto valido para validar (fail closed)",
            file=sys.stderr,
        )
        return 2

    violations = [
        msg
        for path in sorted(REPO_ROOT.glob(ADR_GLOB))
        if (msg := check_adr(path, valid)) is not None
    ]

    if violations:
        print(
            "check_adr_bounded_context: ADRs com bounded_context invalido",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
