"""Guard contra padrões conhecidos de drift na documentação normativa.

Plugado em `make docs-check`. Varre os docs normativos **vivos** — a raiz
de `docs/` (não recursivo), `docs/runbooks/` e `docs/templates/` — atrás
de padrões que já causaram drift pelo menos uma vez.

Por que existe: "fonte única" declarada num doc **não** protege contra
paráfrase dessincronizada em outro. O ponto de consumo é o texto que o
agente executor lê, não o que se autodeclara canônico. Cada padrão aqui
nasceu de uma divergência real observada — a lista é evidência, não
imaginação (mesmo critério de manutenção de `check_concept_directness.py`).

Docs históricos (`docs/stages/`, `docs/adr/`, `docs/audits/`) ficam **fora
de escopo de propósito**: eles registram o que era verdade na época.

Manutenção de `VIOLATION_PATTERNS`:

- **Gatilho = evidência.** A entrada nasce quando uma auditoria (ou um
  sync de processo) acha de fato a frase defasada sobrevivendo num doc.
- **Alargar antes de adicionar.** Se um padrão existente *deveria* ter
  pego, o conserto é alargar o regex.
- **O limite é precisão, não token.** Padrão frouxo dispara em prosa
  legítima e treina todo mundo a ignorar o gate.

Exit codes:
  0  nenhuma violação
  1  violações encontradas (arquivo:linha em stderr)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCANNED_GLOBS = ("docs/*.md", "docs/runbooks/*.md", "docs/templates/*.md")

# En dash (U+2013), a grafia de faixa usada nos docs. Construído via chr()
# para não carregar unicode ambíguo no fonte (RUF001).
EN_DASH = chr(0x2013)

VIOLATION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        # Achado no sync #55: 6 docs ainda mandavam escrever a nota de
        # handoff manual meses depois de o workflow `audit-gate` existir.
        re.compile(r"precisa de auditoria", re.IGNORECASE),
        "handoff de auditoria em prosa: o canônico é o label "
        "`> **Auditoria:** <status>` (CONVENTIONS §3.6), lido pelo audit-gate",
    ),
    (
        # Cobre en dash (grafia dos docs) e o hífen ASCII.
        # Achado no sync #55 nos dois templates de Stage.
        re.compile("3[" + EN_DASH + "-]8 Tasks"),
        "faixa de Tasks defasada (3-8): a canônica é 3-12 (CONVENTIONS §6)",
    ),
    (
        # Links para as variantes de PROMPT-stage removidas pela #55.
        re.compile(r"\]\([^)]*PROMPT-stage-single-session-(autonomous|interactive)"),
        "link para variante de PROMPT-stage removida (#55): a versão "
        "oficial única é PROMPT-stage-single-session.md",
    ),
    (
        # Caminhos que só existem no repo-template de origem; prosa em
        # backticks (proveniência) é permitida, link de navegação não.
        re.compile(r"\]\([^)]*boilerplate/layout-files"),
        "link para boilerplate/layout-files (caminho do repo-template; quebrado aqui)",
    ),
)


def scan_file(path: Path) -> list[str]:
    violations: list[str] = []
    text = path.read_text(encoding="utf-8-sig")
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern, reason in VIOLATION_PATTERNS:
            if pattern.search(line):
                rel = path.relative_to(REPO_ROOT)
                violations.append(f"{rel}:{lineno}: {reason}")
    return violations


def main() -> int:
    violations: list[str] = []
    for glob_pattern in SCANNED_GLOBS:
        for path in sorted(REPO_ROOT.glob(glob_pattern)):
            violations.extend(scan_file(path))

    if violations:
        print("check_docs_pointers: padroes de drift encontrados", file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
