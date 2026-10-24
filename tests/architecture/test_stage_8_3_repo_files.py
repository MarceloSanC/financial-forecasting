"""O registro curado `docs/reports/dossier_register.toml` no arquivo real (Stage 8.3, Task 15).

A12 (concept 8.3): o registro tem os itens herdados obrigatórios e todo `[finding]` aberto
da cadeia citável (a varredura é o `[measurement]` Task 15 do §7 do technical da 8.3).
A17: a visibilidade é decidida pela fonte (1ª barreira no `DossierEntry`, exercida pelo
parser real) e o texto citável passa a 2ª barreira (`find_forbidden`, dono único em
`dtos/report_artifacts.py`, nunca copiado aqui). Todo ponteiro aponta um arquivo do repo e,
com âncora, um cabeçalho real dele (slug no estilo GitHub: minúsculas, pontuação fora,
espaço → `-`, acentos preservados, sufixo `-N` em cabeçalho repetido).
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable
from functools import cache
from pathlib import Path

from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    CITABLE_82_ANCHORS,
    DossierEntry,
    DossierEntryKind,
    Visibility,
    find_forbidden,
)

_REPO = Path(__file__).resolve().parents[2]
_REGISTER = _REPO / "docs" / "reports" / "dossier_register.toml"
_TECHNICAL_83 = _REPO / "docs" / "stages" / "8.3-plots-and-final-report" / "technical.md"
_SWEEP_HEADING = "[measurement] Task 15, varredura dos `[finding]` abertos"

_T81 = "docs/stages/8.1-confirmatory-run/technical.md"
_T82 = "docs/stages/8.2-equivalence-audit/technical.md"
_REPRO = "docs/reports/reproduction_audit.md"
_O1_O2 = (
    f"{_T81}#2026-10-23--finding-auditoria-da-stage--erratas-da-evidência-da-etapa-r-e-"
    "cobertura-por-arquivo--claude-auditoria-da-stage"
)
_CITABLE_REPRODUCTION = frozenset(
    {
        f"{_REPRO}#1-claim",
        f"{_REPRO}#2-identidade",
        f"{_REPRO}#3-result_digest",
        f"{_REPRO}#4-comparação-por-classe-e-por-tabela",
    }
)

# (kind, ponteiro) — lista fechada do concept §3 / A12 / technical Task 15.
_INHERITED_CITABLE: frozenset[tuple[DossierEntryKind, str]] = frozenset(
    {
        (DossierEntryKind.DEVIATION, _O1_O2),
        *(
            (DossierEntryKind.DEVIATION, anchor)
            for anchor in CITABLE_82_ANCHORS
            if "deviation" in anchor
        ),
        *((DossierEntryKind.REPRODUCTION, pointer) for pointer in _CITABLE_REPRODUCTION),
        (
            DossierEntryKind.PRE_ANCHOR,
            "docs/adr/6_5_0010-human-decisions-blinding-threshold-deviation-winner.md#decision",
        ),
        (
            DossierEntryKind.PRE_ANCHOR,
            "docs/adr/6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md#decision",
        ),
        (
            DossierEntryKind.ENVIRONMENT,
            "docs/runbooks/confirmatory-cohort-aapl.md#step-6--human-decisions-p-executed-for-real-task-33",
        ),
        (
            DossierEntryKind.ENVIRONMENT,
            "docs/adr/7_3_0004-device-per-trainer-instance-torch-build-declared.md#decision",
        ),
        (
            DossierEntryKind.ENVIRONMENT,
            "docs/stages/8.3-plots-and-final-report/concept.md#contexto",
        ),
    }
)

_INHERITED_INTERNAL: frozenset[str] = frozenset(
    {
        "docs/reports/prior_evidence_registry.toml",
        "docs/reports/equivalence_audit.md",
        "docs/adr/8_2_0004-a1-tolerance-by-effective-float32-storage-precision.md",
        f"{_T82}#2026-10-23--deviation-b3--emenda-do-a1-meio-ulp-de-float32-com-pré-condição-"
        "adr-820004--claude-executor-das-etapas",
        f"{_T82}#2026-10-23--deviation-b3-refinada--critério-float32-exato-fail-closed-e-"
        "rótulo-propagado--claude-executor-das-etapas",
        # [finding] PICP 80 % do candidato (embutido no [measurement] E4 refeita com B3)
        f"{_T82}#2026-10-24--measurement-e4-refeita-com-b3--tabela-de-equivalência--"
        "claude-executor-das-etapas",
        f"{_T82}#2026-10-24--finding-auditoria-da-stage--erratas-f2f5--claude-auditoria-da-stage",
        f"{_T82}#2026-10-23--finding-e4-passo-1--fail_audit_table-por-officialsilvermismatcherror-"
        "do-andaime--claude-executor-das-etapas",
        f"{_T82}#2026-10-23--deviation-e4--check_silver_units-só-com-as-unidades-do-cohort--"
        "claude-executor-das-etapas",
        f"{_T82}#2026-10-23--deviation-task-11-prior_candidate_labels-no-comparison_setpy--"
        "claude-executor",
        f"{_T82}#2026-10-23--deviation-checkpoint-c-final-bloco-4-cc4-1cc4-8-no-andaime--"
        "claude-executor",
        f"{_REPRO}#5-ambiente",
    }
)

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_SECTION_7 = re.compile(r"^##\s+7\.")
_TICKED = re.compile(r"`([^`]+)`")
_TOP_LEVEL = 2  # `#`/`##`: abre ou fecha a §7
_SWEEP_COLUMNS = 5  # Stage | [finding] | status | evidência | ponteiro


def github_slug(text: str) -> str:
    """O slug de âncora do GitHub para o texto de um cabeçalho (sem o sufixo de repetição)."""
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


@cache
def _headings(path: Path) -> tuple[tuple[str, str, bool], ...]:
    """(slug, texto, está na §7) de cada cabeçalho do arquivo, fora de blocos de código."""
    seen: dict[str, int] = {}
    out: list[tuple[str, str, bool]] = []
    fenced = False
    in_section_7 = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        match = None if fenced else _HEADING.match(line)
        if match is None:
            continue
        if len(match.group(1)) <= _TOP_LEVEL:
            in_section_7 = bool(_SECTION_7.match(line))
        base = github_slug(match.group(2))
        count = seen.get(base, 0)
        seen[base] = count + 1
        out.append((base if count == 0 else f"{base}-{count}", match.group(2), in_section_7))
    return tuple(out)


def _parse_register() -> Callable[[str], tuple[DossierEntry, ...]]:
    module = importlib.import_module(
        "financial_forecasting.features.evaluation.adapters.in.cli.dossier_register"
    )
    parse: Callable[[str], tuple[DossierEntry, ...]] = module.parse_register
    return parse


@cache
def _entries() -> tuple[DossierEntry, ...]:
    return _parse_register()(_REGISTER.read_text(encoding="utf-8"))


def _split(pointer: str) -> tuple[Path, str | None]:
    path, _, anchor = pointer.partition("#")
    return _REPO / path, anchor or None


def _sweep_open_pointers() -> frozenset[str]:
    """Os ponteiros das linhas `aberto` da tabela do `[measurement]` Task 15 (§7 da 8.3)."""
    lines = _TECHNICAL_83.read_text(encoding="utf-8").splitlines()
    start = next(
        i for i, line in enumerate(lines) if line.startswith("### ") and _SWEEP_HEADING in line
    )
    pointers: set[str] = set()
    for line in lines[start + 1 :]:
        if line.startswith("### ") or line.startswith("<!-- END"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) == _SWEEP_COLUMNS and cells[2] == "aberto":
            ticked = _TICKED.findall(cells[4])
            assert len(ticked) == 1, f"open row without exactly one pointer: {line}"
            pointers.add(ticked[0])
    return frozenset(pointers)


def test_register_parses() -> None:
    entries = _entries()
    assert entries
    assert {entry.kind for entry in entries} == set(DossierEntryKind)


def test_register_has_inherited_citable_items() -> None:
    present = {(entry.kind, entry.pointer) for entry in _entries()}
    missing = sorted((kind.value, pointer) for kind, pointer in _INHERITED_CITABLE - present)
    assert not missing, missing
    errata = {entry.title for entry in _entries() if entry.pointer == _O1_O2}
    assert any("O1" in title for title in errata)
    assert any("O2" in title for title in errata)
    assert any(
        entry.kind is DossierEntryKind.ENVIRONMENT and "code.src" in entry.title
        for entry in _entries()
    )
    claim = next(entry for entry in _entries() if entry.pointer == f"{_REPRO}#1-claim")
    for fact in ("R1", "R2", "R3", "060537fc", "sha256:"):
        assert fact in claim.summary, fact


def test_register_has_inherited_internal_items() -> None:
    internal = {entry.pointer for entry in _entries() if entry.kind is DossierEntryKind.INTERNAL}
    missing = sorted(_INHERITED_INTERNAL - internal)
    assert not missing, missing


def test_every_pointer_resolves_to_a_file_and_a_real_heading() -> None:
    problems: list[str] = []
    for entry in _entries():
        path, anchor = _split(entry.pointer)
        if not path.is_file():
            problems.append(f"missing file: {entry.pointer}")
        elif anchor is not None and anchor not in {slug for slug, _, _ in _headings(path)}:
            problems.append(f"anchor without heading: {entry.pointer}")
    assert not problems, problems


def test_every_open_finding_entry_points_to_an_existing_section_7_heading() -> None:
    findings = [entry for entry in _entries() if entry.kind is DossierEntryKind.FINDING]
    assert findings
    for entry in findings:
        path, anchor = _split(entry.pointer)
        assert path.name == "technical.md", entry.pointer
        matched = [(text, in_7) for slug, text, in_7 in _headings(path) if slug == anchor]
        assert len(matched) == 1, entry.pointer
        text, in_section_7 = matched[0]
        assert in_section_7 and "[finding]" in text, entry.pointer


def test_every_open_finding_of_the_sweep_is_in_the_register() -> None:
    swept = _sweep_open_pointers()
    assert swept, "the Task 15 sweep lists no open finding"
    registered = {entry.pointer for entry in _entries() if entry.kind is DossierEntryKind.FINDING}
    assert swept == registered


def test_citable_entries_pass_the_second_barrier() -> None:
    hits = {
        entry.title: find_forbidden(f"{entry.title}\n{entry.summary}\n{entry.pointer}")
        for entry in _entries()
        if entry.visibility is Visibility.CITABLE
    }
    assert not {title: found for title, found in hits.items() if found}


def test_citable_reproduction_audit_pointers_only_to_sections_1_to_4() -> None:
    citable = {
        entry.pointer
        for entry in _entries()
        if entry.visibility is Visibility.CITABLE and entry.pointer.startswith(_REPRO)
    }
    assert citable == _CITABLE_REPRODUCTION


def test_github_slug_keeps_accents_and_drops_punctuation() -> None:
    assert github_slug("2026-10-23 — [finding] Ação: `x_y.py` — Fim (z)") == (
        "2026-10-23--finding-ação-x_ypy--fim-z"
    )
