"""Guard: concept que toca um concern transversal declara o teste da solução
mais direta no §12.

Wired into `make docs-check`. É o **piso enforçável** do teste da solução mais
direta — o resto do mecanismo (Passo 1b, Passo 4, Passo 5 do
`RUNBOOK-STAGE-LIFECYCLE.md`) é prompt e gate humano, não lintável.

Por que existe: a especificação tende a criar caso especial/tipo/métrica novo
para tratar **local** um sintoma cujo tratamento direto seria geral ou a
montante — tipicamente um concern **compartilhado** (anti-leakage, as-of,
identidade/fingerprint, calendário de pregão, fuso horário, reuso de dado
bruto, tracking) capturado dentro de um bounded context. Isso passa em todos
os gates estruturais existentes (§4.2 Stage atômica, fronteiras,
rastreabilidade), que checam espalhamento/tamanho/deferimento dentro de um
frame **assumido correto**.

Regra aplicada:

  Se o corpo de um `concept.md` com `status: done` menciona um **suspeito
  transversal** (lista `SUSPECT_PATTERNS` abaixo), então o §12 (Checklist de
  validação interna) precisa ter a entrada do **teste da solução mais direta**
  marcada `[x]` **e justificada** — no estilo da casa, `— <justificativa>`.
  Marcar a boilerplate do template sem justificar não passa: checkbox sem
  conteúdo é exatamente o que a regra combate.

Escopo deliberado (**piso, não teto**): a lista de suspeitos é um subconjunto
por keyword. O julgamento semântico completo ("existe solução mais simples?")
é injulintável e continua no Passo 1b, no gate do Passo 5 e na skill
`stage-audit` (conceito de falso-verde "solução complexa onde cabia a
simples"). Um concept pode capturar um concern que nenhuma keyword pega —
este script não é a única defesa.

O gate também **não avalia a resposta**: exige que a entrada do §12 exista,
esteja marcada e tenha justificativa. Justificativa oca passa no lint — quem
julga o mérito é o gate humano do Passo 5 e a auditoria. O que este script
garante é que a pergunta foi feita e respondida por escrito.

Manutenção de `SUSPECT_PATTERNS` (loop recursivo, espelha o das skills de
auditoria):

- **Gatilho = evidência, não imaginação.** A entrada nasce quando uma
  auditoria pega de fato uma captura de concern que a lista deixou passar.
  Não pré-popular com concerns que talvez apareçam.
- **Alargar antes de adicionar.** Se um padrão existente *deveria* ter pego
  (o concept dizia "olhar para o futuro" e só havia `anti-leakage`), o
  conserto é alargar o regex — entrada nova só para classe de concern
  genuinamente nova. Mesma pergunta que a `stage-audit` faz com os conceitos
  de falso-verde.
- **No mesmo commit do caso.** A auditoria que pegou o vazamento registra a
  linha na tabela de casos históricos da skill; a keyword acompanha, senão o
  caso fica registrado e o piso segue com o mesmo furo.
- **O limite não é token, é precisão.** Lista é código, não contexto: palavra
  nova custa zero em runtime e custa **falso positivo**, pago por todo autor
  de concept seguinte. Lista frouxa dispara em tudo, é respondida com
  justificativa automática e vira o checkbox teatral que ela existe para
  impedir.

Grandfather: concepts com `created_at` anterior a `RULE_EFFECTIVE_DATE` são
pulados. A regra nasceu com a #55; cobrar retroativamente os concepts escritos
sob outra especificação do template produziria só ruído.

Modos de descoberta (mesmo contrato de `check_stage_issue.py`):

- **default (delta-only):** valida apenas os `concept.md` novos ou modificados
  vs o merge-base com `origin/develop` (+ untracked).
- **`--all`:** varredura completa de `docs/stages/*/concept.md`.
- **`<target>`:** valida um arquivo específico.

Fail-safe: se o delta não pode ser determinado (sem `git`, sem
`origin/develop`, merge-base falhou), cai na varredura completa com WARN — o
gate nunca sub-verifica por erro de ambiente.

Uso:
    python scripts/check_concept_directness.py
    python scripts/check_concept_directness.py --all
    python scripts/check_concept_directness.py docs/stages/2.3-s3-source/concept.md

Exit codes:
  0  nenhuma violação (ou nada no delta a checar)
  1  pelo menos um concept toca suspeito transversal sem a entrada preenchida
  2  erro interno (target inexistente)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

# A regra nasce com a issue #55. Concept anterior a esta data é grandfathered.
RULE_EFFECTIVE_DATE = date(2026, 8, 8)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_STATUS_RE = re.compile(r"^\s*status:\s*(\S+)\s*$", re.MULTILINE)
_CREATED_AT_RE = re.compile(r"^\s*created_at:\s*(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)

# §12 do template — "## 12. Checklist de validação interna" até o próximo H2.
_SECTION_12_RE = re.compile(r"^##\s*12\.\s.*?(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)

# A entrada do teste, em qualquer redação que contenha o nome do teste.
_DIRECTNESS_ENTRY_RE = re.compile(
    r"^-\s*\[(?P<mark>[ xX])\]\s*(?P<text>.*?)(?=^-\s*\[|\Z)",
    re.MULTILINE | re.DOTALL,
)
_DIRECTNESS_NAME_RE = re.compile(r"solu[çc][ãa]o\s+mais\s+direta", re.IGNORECASE)

# Justificativa no estilo da casa: `— <texto>` (ou `--`) após o enunciado.
_RATIONALE_RE = re.compile(r"(?:—|--)\s*(?P<why>\S.*)", re.DOTALL)
_MIN_RATIONALE_CHARS = 20

# Suspeitos transversais — concerns que recorrem em vários consumidores deste
# projeto e cujo tratamento natural é geral ou a montante. Cada entrada nasceu
# de evidência local (ADR/issue citada), não de imaginação — ver "Manutenção"
# no docstring. Palavra-limite deliberada: `erro` solto casaria com a seção
# "Casos de erro" de praticamente todo concept.
SUSPECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # ADR 0.0.0018 (anti-leakage inegociável) + issue #32: a checagem
    # causal recorre em indicadores, features derivadas e dataset builder.
    (
        "anti-leakage/causalidade",
        re.compile(r"\b(anti[- ]?leakage|vazamento|look[- ]?ahead|causalidade|causal)\b", re.I),
    ),
    # ADR 3.3.0001 (as-of backward join): todo dado de frequência menor
    # que a diária entra por as-of; regra local diverge fácil.
    (
        "as-of/point-in-time",
        re.compile(r"\b(as[- ]?of|point[- ]in[- ]time|backward\s+join|defasagem)\b", re.I),
    ),
    # ADR 1.4.0001 (canonicalização de hash) + 5.1.0003: fingerprint
    # atravessa split, dataset, modelo e run.
    (
        "identidade/fingerprint",
        re.compile(r"\b(fingerprint|canonicaliza\w*|hash\s+determin\w*)\b", re.I),
    ),
    # ADR 2.4.0001 (calendário no domínio) + 4.3.0001 (indexação por dia
    # de pregão): o que conta como "dia" é decisão de uma camada só.
    (
        "calendário de pregão",
        re.compile(
            r"\b(calend[áa]rio|pregão|trading\s+(day|calendar)|sess[ãa]o\s+de\s+mercado)\b", re.I
        ),
    ),
    # ADR 4.2.0002 (created_at UTC via clock injetado).
    ("fuso horário", re.compile(r"\b(fuso\s+hor[áa]rio|timezone|utc|tz[- ]aware)\b", re.I)),
    # ADRs 2.2.0002 e 2.3.0002 (reusar bruto como default vs buscar live).
    (
        "reuso/cache de dado bruto",
        re.compile(r"\b(cach(e|ing|eado)|reus(o|ar|ando)\s+.{0,20}bruto|refetch)\b", re.I),
    ),
    # ADRs 1.5.0001/1.5.0002 (tracking como port): o que se registra de um
    # run atravessa modelagem, avaliação e reprodução.
    (
        "tracking/observabilidade",
        re.compile(r"\b(observabilidade|telemetria|tracking|mlflow|logging\s+estruturado)\b", re.I),
    ),
)


def parse_frontmatter(text: str) -> dict[str, str]:
    """Extrai os campos do frontmatter YAML (apenas key: value flat)."""
    m = _FRONTMATTER_RE.match(text)
    if m is None:
        return {}
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("-"):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def body_after_frontmatter(text: str) -> str:
    m = _FRONTMATTER_RE.match(text)
    return text[m.end() :] if m is not None else text


def suspects_touched(body: str) -> list[str]:
    """Rótulos dos concerns transversais mencionados no corpo do concept."""
    return [label for label, pattern in SUSPECT_PATTERNS if pattern.search(body)]


def directness_entry_status(body: str) -> tuple[bool, bool]:
    """(entrada existe e está marcada, entrada tem justificativa).

    Uma entrada não encontrada devolve (False, False).
    """
    section = _SECTION_12_RE.search(body)
    if section is None:
        return False, False
    for entry in _DIRECTNESS_ENTRY_RE.finditer(section.group(0)):
        text = entry.group("text")
        if not _DIRECTNESS_NAME_RE.search(text):
            continue
        checked = entry.group("mark").lower() == "x"
        rationale = _RATIONALE_RE.search(text)
        why = rationale.group("why").strip() if rationale is not None else ""
        return checked, len(why) >= _MIN_RATIONALE_CHARS
    return False, False


def check_one(path: Path) -> tuple[str, str]:
    """Retorna (veredito, mensagem). Veredito: 'ok' | 'skip' | 'fail'."""
    text = path.read_text(encoding="utf-8-sig")
    fm = parse_frontmatter(text)

    status = fm.get("status")
    if status != "done":
        return "skip", f"status='{status}' (regra vale no gate do Passo 5, com `done`)"

    raw_created = fm.get("created_at", "")
    if _CREATED_AT_RE.search(f"created_at: {raw_created}"):
        created = date.fromisoformat(raw_created)
        if created < RULE_EFFECTIVE_DATE:
            return "skip", f"created_at={raw_created} anterior à regra (#55) — grandfathered"

    body = body_after_frontmatter(text)
    suspects = suspects_touched(body)
    if not suspects:
        return "ok", "nao toca suspeito transversal"

    checked, justified = directness_entry_status(body)
    joined = ", ".join(suspects)
    if not checked:
        return "fail", f"toca {joined} e o §12 nao tem a entrada do teste marcada `[x]`"
    if not justified:
        return "fail", (
            f"toca {joined} e a entrada do §12 esta marcada sem justificativa (`— <por que>`)"
        )
    return "ok", f"toca {joined}; §12 declara o teste"


_BASE_REF = "origin/develop"


def _git_lines(args: list[str]) -> list[str] | None:
    """Roda `git <args>` e devolve stdout em linhas; `None` em qualquer falha."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def discover_changed_concepts() -> list[Path] | None:
    """`concept.md` novos/modificados vs o merge-base com `origin/develop`."""
    merge_base = _git_lines(["merge-base", "HEAD", _BASE_REF])
    if not merge_base:
        return None
    changed = _git_lines(["diff", "--name-only", merge_base[0], "--", "docs/stages"])
    if changed is None:
        return None
    untracked = _git_lines(["ls-files", "--others", "--exclude-standard", "docs/stages"])
    if untracked is None:
        return None
    candidates = {Path(line) for line in changed + untracked}
    return sorted(path for path in candidates if path.name == "concept.md" and path.is_file())


def discover_all_concepts() -> list[Path]:
    stages_dir = Path("docs/stages")
    if not stages_dir.is_dir():
        return []
    return sorted(stages_dir.glob("*/concept.md"))


def discover_concepts(target: Path | None, *, scan_all: bool) -> list[Path]:
    if target is not None:
        if not target.is_file():
            print(f"check_concept_directness: file does not exist: {target}", file=sys.stderr)
            sys.exit(2)
        return [target]
    if scan_all:
        return discover_all_concepts()
    changed = discover_changed_concepts()
    if changed is None:
        print(
            "check_concept_directness: WARN — could not determine branch delta vs "
            f"'{_BASE_REF}'; falling back to full scan.",
            file=sys.stderr,
        )
        return discover_all_concepts()
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        nargs="?",
        type=Path,
        help=(
            "Caminho de um concept.md específico; se omitido, valida só os "
            "novos/modificados vs origin/develop (delta-only)."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Varre docs/stages/*/concept.md inteiro (auditoria ocasional).",
    )
    args = parser.parse_args()

    concepts = discover_concepts(args.target, scan_all=args.all)
    if not concepts:
        print("check_concept_directness: no new/changed concepts — nothing to check")
        return 0

    failures: list[tuple[Path, str]] = []
    for concept in concepts:
        verdict, msg = check_one(concept)
        if verdict == "fail":
            failures.append((concept, msg))
        print(f"  {verdict.upper():6} {concept}: {msg}")

    if failures:
        print("", file=sys.stderr)
        print(
            f"check_concept_directness: FAILED — {len(failures)} concept(s) tocam um "
            "concern transversal sem declarar o teste da solução mais direta:",
            file=sys.stderr,
        )
        for concept, msg in failures:
            print(f"  {concept}: {msg}", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "O concept menciona um concern que recorre em outros consumidores\n"
            "(anti-leakage, as-of, fingerprint, calendário, fuso...). Antes de seguir,\n"
            "responda no §12 do concept: existe solução mais simples ou a montante, ou\n"
            "o mecanismo novo está remendando local um concern compartilhado? Se for\n"
            "captura, a solução geral é o conserto — a local vira piso declarado +\n"
            "issue, nunca solução silenciosa (RUNBOOK-STAGE-LIFECYCLE.md Passo 1b/5).\n"
            "Marque a entrada `[x]` e justifique: `— <por que a local basta aqui>`.",
            file=sys.stderr,
        )
        return 1

    print(f"check_concept_directness: OK — {len(concepts)} concept(s) checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
