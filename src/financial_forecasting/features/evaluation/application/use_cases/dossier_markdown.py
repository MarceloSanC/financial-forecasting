"""Markdown dos dois dossiês — dono único (Stage 8.3, technical §1 "Markdown dos dossiês").

`render(dossier, visibility)` é puro: o sink real e os testes chamam a mesma função (o fake
não a duplica — `check_fake_parity`). Forma: título; o parágrafo de como regenerar (o
comando literal do bloco `REGENERATE_HEADING`); um `##` por seção na ordem do dossiê; um
`###` por bloco; tabela `| campo | valor |`; `Fonte:` com o ponteiro como link relativo a
`docs/reports/`. Valor de várias linhas, com `|` ou com crase sai **literal** num bloco
cercado, fora da tabela — o `blinding_statement` é transcrito byte a byte (D9). LF;
termina em `\\n`. O interno começa (título) com o aviso "Interno, fora do texto do TCC".
"""

from __future__ import annotations

import re
from typing import Final

from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    INTERNAL_SECTION,
    DossierBlock,
    TraceabilityDossier,
    Visibility,
)
from financial_forecasting.features.evaluation.application.use_cases.report_dossier import (
    REGENERATE_HEADING,
)

CITABLE_FILE: Final = "final_traceability_dossier.md"
INTERNAL_FILE: Final = "final_traceability_dossier_internal.md"
REPORTS_DIR: Final = "docs/reports/"
_TITLES: Final = {
    Visibility.CITABLE: "Dossiê final de rastreabilidade",
    Visibility.INTERNAL: f"{INTERNAL_SECTION[1]} — dossiê final de rastreabilidade",
}
_BACKTICKS = re.compile(r"`+")


def link_target(pointer: str) -> str:
    """O ponteiro (relativo ao repo) como caminho relativo a `docs/reports/`."""
    if pointer.startswith(REPORTS_DIR):
        return pointer.removeprefix(REPORTS_DIR)
    if pointer.startswith("docs/"):
        return "../" + pointer.removeprefix("docs/")
    return "../../" + pointer


def _is_verbatim(value: str) -> bool:
    """Valor que uma célula de tabela não transcreve byte a byte (D9; CC3-2)."""
    return "\n" in value or "|" in value or "`" in value


def _fence(value: str) -> str:
    longest = max((len(run) for run in _BACKTICKS.findall(value)), default=0)
    return "`" * max(3, longest + 1)


def _block_lines(block: DossierBlock) -> list[str]:
    lines = [f"### {block.heading}", ""]
    table = [(field, value) for field, value in block.rows if not _is_verbatim(value)]
    verbatim = [(field, value) for field, value in block.rows if _is_verbatim(value)]
    if table:
        lines += ["| campo | valor |", "|---|---|"]
        lines += [f"| {field} | {value} |" for field, value in table]
        lines.append("")
    for field, value in verbatim:
        fence = _fence(value)
        lines += [f"**{field}:**", "", f"{fence}text", value, fence, ""]
    if block.pointer is not None:
        lines += [f"Fonte: [`{block.pointer}`]({link_target(block.pointer)})", ""]
    return lines


def _regenerate(dossier: TraceabilityDossier) -> str:
    for section in dossier.sections:
        for block in section.blocks:
            if block.heading == REGENERATE_HEADING:
                rows = dict(block.rows)
                return f"{rows['regra']}: `{rows['comando']}`."
    raise ValueError(f"the dossier has no {REGENERATE_HEADING!r} block")


def render(dossier: TraceabilityDossier, visibility: Visibility) -> str:
    """O Markdown do arquivo citável ou do interno (LF, termina em `\\n`)."""
    lines = [f"# {_TITLES[visibility]}", ""]
    lines += [f"Como regenerar: {_regenerate(dossier)}", ""]
    for section in dossier.sections_of(visibility):
        lines += [f"## {section.title}", ""]
        if not section.blocks:
            lines += ["Nenhuma entrada.", ""]
        for block in section.blocks:
            lines += _block_lines(block)
    return "\n".join(lines).rstrip("\n") + "\n"
