"""`attestation_body` — o corpo do comentário de atestação da corrida (Stage 8.1, D7).

Função de aplicação pura (concept 8.1 D7; ADR `8_1_0003` item 7): o texto que a CLI
imprime e o runbook posta na issue, montado **só** da cópia selada — o
`JudgedGeneration` que o `preserve` devolve (`JUDGED`/`BLOCKED`) ou que o `find` relê
(`ALREADY_JUDGED`). A mesma cópia dá o mesmo texto (A5, A15). Lê três coisas e nenhum
valor de tabela do gold:

- o manifesto copiado — status do refresh, `started_at`/`finished_at` e as contagens de
  `rows_by_table` das tabelas de H3 (rotuladas "descritiva") e conformais (rotuladas
  "cobertura empírica (não garantida)");
- o `run_record.json` — o `commit` da foto do ambiente e, com `BLOCKED`, os checks que
  falharam (no lugar do veredito);
- o JSON do scorecard (`ScorecardResult.as_mapping()`, só com `COMPLETED`) — a prontidão
  com as razões e o veredito por horizonte.

Texto em português (vai para a issue), Markdown, LF, com um LF final.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from financial_forecasting.features.evaluation.application.dtos.confirmatory_run import (
    RUN_RECORD_ENVIRONMENT,
    RUN_RECORD_FAILED_CHECKS,
    sealed_status,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CONFORMAL_CORRECTIONS,
    GOLD_CONFORMAL_COVERAGE,
    GOLD_H3_IMPORTANCE,
    GOLD_H3_READING,
    GOLD_H3_SHARES,
    GOLD_H3_VSN,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    RUN_RECORD_DOCUMENT,
    SCORECARD_DOCUMENT,
    JudgedGeneration,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.ports.out.evaluation_environment import (
    COMMIT_KEY,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    JUDGED_TAG_PREFIX,
)

H3_TABLES: Final = (
    GOLD_H3_IMPORTANCE.name,
    GOLD_H3_SHARES.name,
    GOLD_H3_READING.name,
    GOLD_H3_VSN.name,
)
CONFORMAL_TABLES: Final = (GOLD_CONFORMAL_CORRECTIONS.name, GOLD_CONFORMAL_COVERAGE.name)
H3_TITLE: Final = "### Leitura de H3 (descritiva)"
CONFORMAL_TITLE: Final = "### Conformal — cobertura empírica (não garantida)"
_NONE: Final = "—"
_VERDICT_HEADER: Final = (
    "| horizonte | H1 | vence o ingênuo | vence ou empata o forte | no MCS | H2 "
    "| vencedor primário |",
    "|---|---|---|---|---|---|---|",
)


def _field(document: Mapping[str, object], key: str, *, where: str) -> object:
    if not isinstance(document, Mapping) or key not in document:
        raise ValueError(f"the judged copy's {where} has no {key!r}")
    return document[key]


def _mapping(value: object, *, where: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"the judged copy's {where} must be a mapping, got {value!r}")
    return value


def _sequence(value: object, *, where: str) -> Sequence[object]:
    if not isinstance(value, list | tuple):
        raise ValueError(f"the judged copy's {where} must be a list, got {value!r}")
    return value


def _flag(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"expected a bool in the scorecard, got {value!r}")
    return value


def _yes_no(value: object) -> str:
    return "sim" if _flag(value) else "não"


def _code(value: object) -> str:
    return _NONE if value is None else f"`{value}`"


def attestation_body(judged: JudgedGeneration) -> str:
    """O corpo determinístico da atestação da cópia selada (ver docstring do módulo).

    Raises:
        ValueError: documento da cópia sem a chave que o corpo lê (ou de forma errada).
    """
    manifest = judged.manifest
    record = _mapping(judged.documents[RUN_RECORD_DOCUMENT], where=RUN_RECORD_DOCUMENT)
    environment = _mapping(
        _field(record, RUN_RECORD_ENVIRONMENT, where=RUN_RECORD_DOCUMENT),
        where=f"{RUN_RECORD_DOCUMENT} {RUN_RECORD_ENVIRONMENT}",
    )
    commit = _field(environment, COMMIT_KEY, where=f"{RUN_RECORD_DOCUMENT} environment")
    ref = judged.preregistration_ref
    partition = judged.partition
    lines = [
        f"## Corrida confirmatória — `{ref}`",
        "",
        f"- status: `{sealed_status(judged.refresh_status).value}` "
        f"(refresh `{judged.refresh_status.value}`)",
        f"- generation_digest: `{judged.generation_digest}`",
        f"- commit: `{commit}`",
        f"- tag: `{JUDGED_TAG_PREFIX}{ref}`",
        f"- partição: `{partition.asset}/{partition.parent_sweep_id}`",
        f"- started_at: `{manifest.started_at.isoformat()}`",
        f"- finished_at: `{manifest.finished_at.isoformat()}`",
        "",
    ]
    if judged.refresh_status is RefreshStatus.COMPLETED:
        lines += _verdict_lines(judged)
    else:
        lines += _failed_check_lines(record)
    lines += _table_lines(H3_TITLE, H3_TABLES, manifest.rows_by_table)
    lines += _table_lines(CONFORMAL_TITLE, CONFORMAL_TABLES, manifest.rows_by_table)
    return "\n".join(lines).rstrip("\n") + "\n"


def _verdict_lines(judged: JudgedGeneration) -> list[str]:
    if SCORECARD_DOCUMENT not in judged.documents:
        raise ValueError(f"a COMPLETED judged copy needs {SCORECARD_DOCUMENT}")
    scorecard = _mapping(judged.documents[SCORECARD_DOCUMENT], where=SCORECARD_DOCUMENT)
    reasons = _sequence(
        _field(scorecard, "readiness_reasons", where=SCORECARD_DOCUMENT),
        where="readiness_reasons",
    )
    ready = _field(scorecard, "academic_decision_ready", where=SCORECARD_DOCUMENT)
    verdict = _mapping(_field(scorecard, "verdict", where=SCORECARD_DOCUMENT), where="verdict")
    lines = [
        "### Prontidão para decisão acadêmica",
        "",
        f"- academic_decision_ready: {_yes_no(ready)}",
        "- razões: " + (", ".join(f"`{reason}`" for reason in reasons) or "nenhuma"),
        "",
        "### Veredito por horizonte",
        "",
        *_VERDICT_HEADER,
    ]
    for item in _sequence(_field(verdict, "horizons", where="verdict"), where="verdict horizons"):
        horizon = _mapping(item, where="verdict horizon")
        h1 = _mapping(_field(horizon, "h1", where="verdict horizon"), where="verdict h1")
        cells = (
            str(_field(horizon, "horizon", where="verdict horizon")),
            "passa" if _flag(_field(h1, "passed", where="verdict h1")) else "falha",
            _yes_no(_field(horizon, "beats_naive", where="verdict horizon")),
            _yes_no(_field(horizon, "beats_or_ties_strong", where="verdict horizon")),
            _yes_no(_field(horizon, "in_mcs", where="verdict horizon")),
            _code(_field(horizon, "h2", where="verdict horizon")),
            _code(_field(horizon, "primary_winner", where="verdict horizon")),
        )
        lines.append("| " + " | ".join(cells) + " |")
    success = _field(verdict, "study_success_h1", where="verdict")
    lines += ["", f"- sucesso do estudo (H1 em ≥ 1 horizonte): {_yes_no(success)}", ""]
    return lines


def _failed_check_lines(record: Mapping[str, object]) -> list[str]:
    checks = _sequence(
        _field(record, RUN_RECORD_FAILED_CHECKS, where=RUN_RECORD_DOCUMENT),
        where=RUN_RECORD_FAILED_CHECKS,
    )
    lines = ["### Checks que falharam (refresh BLOCKED, sem veredito)", ""]
    for item in checks:
        check = _mapping(item, where="failed check")
        scope = ", ".join(
            f"{label} {_NONE if check.get(key) is None else check[key]}"
            for label, key in (("horizonte", "horizon"), ("modelo", "model"), ("seed", "seed"))
        )
        lines.append(
            f"- `{_field(check, 'check', where='failed check')}` "
            f"(`{_field(check, 'kind', where='failed check')}`; {scope}): "
            f"{_field(check, 'occurrences', where='failed check')} ocorrência(s) — "
            f"{_field(check, 'detail', where='failed check') or _NONE}"
        )
    if not checks:
        lines.append("- nenhum check registrado")
    return [*lines, ""]


def _table_lines(title: str, tables: Sequence[str], rows_by_table: Mapping[str, int]) -> list[str]:
    lines = [title, "", "| tabela | linhas |", "|---|---|"]
    for name in tables:
        count = rows_by_table.get(name)
        lines.append(f"| `{name}` | {'não publicada' if count is None else count} |")
    return [*lines, ""]
