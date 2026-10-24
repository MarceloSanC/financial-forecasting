"""Comando `evaluate` da CLI — adapter primário fino da corrida confirmatória (Stage 8.1).

    python -m financial_forecasting.cli evaluate --data-root <dir> --cohort <toml>
        --preregistration <nome> --revision <r> --preregistration-ref <ref>
        [--break-stale-lock] [--deviation "<justificativa com [deviation]>"]

Carregado pelo `cli.py` por `importlib` (o pacote `in` é keyword, LAYOUT §8). O `cli.py`
roda antes o `infer` da 7.1 e só chama este comando se ele terminou sem exceção (concept
8.1 D1); o resumo do `infer` chega aqui como dado — este módulo não importa o
`inference`. Traduz os argumentos em `RunConfirmatoryEvaluationCommand`, chama o
`RunConfirmatoryEvaluation` montado pelo composition root e imprime (contrato da Etapa R,
technical 8.1 §1 "Saída do `evaluate`"; `<ref>` = a `preregistration_ref`):

    evaluation <ref>: <STATUS> generation_digest <64 hex> partition <asset>/<parent_sweep_id>
    --- attestation ---
    <corpo de atestação até o fim>

`BLOCKED` e `ALREADY_JUDGED` são desfechos (exit 0); erros (`ApplicationError`,
`ValueError`) sobem para o `main`, que os traduz em mensagem e exit 2.

Stage 8.2: `audit-reproduction` (só leitura; ADR 8.2.0002 item 4) — lê o scorecard
reproduzido de `<reproduzida>/reproduction/scorecard.json` (gravado pelo driver da
reprodução; **nunca recalcula**), chama o `AuditReproduction` e imprime (contrato da E3,
technical 8.2 §1):

    reproduction <ref>: bit_identical <true|false> partition <asset>/<parent_sweep_id>
    result_digest judged <hex> reproduced <hex> expected <hex>
    identity <campo> judged <v> reproduced <v> equal <true|false>      (4 linhas)
    class <R1|R2|R3> compared <n> different <n> max_abs_diff <repr>     (totais)
    table <nome> rows <n>/<n> keys_equal <bool> R1 <c>/<d>/<m> R2 <c>/<d>/<m> R3 <c>/<d>/<m>
    scorecard equal <bool> leaves <n> different <n> max_abs_diff <repr>

Exit 0 só com `bit_identical`, 1 com diferença (como o `EXIT_MISMATCH` do `verify`); erro
sobe para o `main` (exit 2).

Stage 8.3: `report-artifacts` — parseia o registro curado (`dossier_register`, fronteira),
chama o `GenerateReportArtifacts` e imprime a ref, o `generation_digest`, o `data_digest`
de cada figura e os nomes dos dois dossiês (contrato da Etapa R, technical 8.3 §1).
"""

from __future__ import annotations

import importlib
import json
from typing import TYPE_CHECKING, Final

from financial_forecasting.features.evaluation.application.dtos.confirmatory_run import (
    InferenceSummary,
    RunConfirmatoryEvaluationCommand,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    DossierEntry,
    GenerateReportArtifactsCommand,
    ReportArtifactsResult,
)
from financial_forecasting.features.evaluation.application.dtos.reproduction_comparison import (
    AuditReproductionCommand,
    ClassComparison,
    ReproductionComparison,
)
from financial_forecasting.features.evaluation.application.use_cases.audit_reproduction import (
    ReproductionAuditError,
)
from financial_forecasting.features.evaluation.application.use_cases.dossier_markdown import (
    CITABLE_FILE,
    INTERNAL_FILE,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path
    from typing import TextIO

    from financial_forecasting.features.evaluation.application.use_cases.run_confirmatory_evaluation import (  # noqa: E501
        RunConfirmatoryEvaluation,
    )

ATTESTATION_SEPARATOR: Final = "--- attestation ---"
REPRODUCTION_DIR: Final = "reproduction"
"""O diretório fixo do driver da reprodução no `data_root` descartável (ADR 8.2.0001)."""
REPRODUCTION_SCORECARD: Final = "scorecard.json"
"""O scorecard reproduzido (`document_bytes(scorecard.as_mapping())`) em `REPRODUCTION_DIR`."""
EXIT_DIFFERENT: Final = 1


def evaluate(  # noqa: PLR0913 — opções coesas do subcomando
    run_confirmatory_evaluation: RunConfirmatoryEvaluation,
    *,
    name: str,
    revision: int,
    preregistration_ref: str,
    inference_summary: Mapping[str, object],
    break_stale_lock: bool,
    deviation: str | None,
    out: TextIO,
) -> int:
    """Roda a corrida confirmatória e imprime o desfecho e o corpo de atestação; devolve 0."""
    result = run_confirmatory_evaluation(
        RunConfirmatoryEvaluationCommand(
            name=name,
            revision=revision,
            preregistration_ref=preregistration_ref,
            inference_summary=InferenceSummary.from_mapping(inference_summary),
            break_stale_lock=break_stale_lock,
            deviation=deviation,
        )
    )
    partition = result.partition
    out.write(
        f"evaluation {result.preregistration_ref}: {result.status.value} "
        f"generation_digest {result.generation_digest} "
        f"partition {partition.asset}/{partition.parent_sweep_id}\n"
    )
    out.write(f"{ATTESTATION_SEPARATOR}\n")
    out.write(result.attestation_body)
    return 0


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _counts(item: ClassComparison) -> str:
    return f"{item.compared}/{item.different}/{item.max_abs_diff!r}"


def _report_lines(comparison: ReproductionComparison) -> list[str]:
    partition = comparison.partition
    lines = [
        f"reproduction {comparison.preregistration_ref}: bit_identical "
        f"{_bool(comparison.bit_identical)} partition "
        f"{partition.asset}/{partition.parent_sweep_id}",
        f"result_digest judged {comparison.judged_result_digest} reproduced "
        f"{comparison.reproduced_result_digest} expected {comparison.expected_result_digest}",
    ]
    lines += [
        f"identity {item.field} judged {item.judged} reproduced {item.reproduced} "
        f"equal {_bool(item.equal)}"
        for item in comparison.identity
    ]
    lines += [
        f"class {item.reproduction_class.value} compared {item.compared} different "
        f"{item.different} max_abs_diff {item.max_abs_diff!r}"
        for item in comparison.totals
    ]
    lines += [
        f"table {table.name} rows {table.judged_rows}/{table.reproduced_rows} keys_equal "
        f"{_bool(table.keys_equal)} "
        + " ".join(f"{item.reproduction_class.value} {_counts(item)}" for item in table.classes)
        for table in comparison.tables
    ]
    scorecard = comparison.scorecard
    lines.append(
        f"scorecard equal {_bool(scorecard.equal)} leaves {scorecard.leaves} different "
        f"{scorecard.different} max_abs_diff {scorecard.max_abs_diff!r}"
    )
    return lines


def read_reproduced_scorecard(reproduced_data_root: Path) -> Mapping[str, object]:
    """O JSON de `<reproduzida>/reproduction/scorecard.json`, gravado pelo driver.

    Raises:
        ReproductionAuditError: arquivo ausente ou JSON que não é objeto.
    """
    path = reproduced_data_root / REPRODUCTION_DIR / REPRODUCTION_SCORECARD
    if not path.is_file():
        raise ReproductionAuditError(f"no reproduced scorecard at {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ReproductionAuditError(f"{path} is not a JSON object")
    return document


def audit_reproduction(  # noqa: PLR0913 — opções coesas do subcomando
    audit: Callable[[AuditReproductionCommand], ReproductionComparison],
    *,
    reproduced_data_root: Path,
    name: str,
    revision: int,
    preregistration_ref: str,
    out: TextIO,
) -> int:
    """Compara a reprodução com a cópia julgada e imprime; 0 só com `bit_identical`, senão 1."""
    comparison = audit(
        AuditReproductionCommand(
            name=name,
            revision=revision,
            preregistration_ref=preregistration_ref,
            reproduced_scorecard=read_reproduced_scorecard(reproduced_data_root),
        )
    )
    out.write("".join(f"{line}\n" for line in _report_lines(comparison)))
    return 0 if comparison.bit_identical else EXIT_DIFFERENT


# --- Stage 8.3: report-artifacts ----------------------------------------------------------

_DOSSIER_REGISTER = "dossier_register"
"""Módulo irmão do parser do registro curado (o pacote `in` é keyword: `importlib`)."""


def report_artifacts(  # noqa: PLR0913 — opções coesas do subcomando
    generate: Callable[[GenerateReportArtifactsCommand], ReportArtifactsResult],
    *,
    register_path: Path,
    name: str,
    revision: int,
    preregistration_ref: str,
    cohort_seeds: tuple[int, ...],
    out: TextIO,
) -> int:
    """Parseia o registro curado (fronteira), gera figuras e dossiê e imprime; devolve 0.

    Saída (contrato do technical 8.3 §1 "Subcomando"):

        report <ref>: generation_digest <64 hex> figures 10 register_entries <n>
        figure <id> data_digest <64 hex>                  (10 linhas, ordem do catálogo)
        dossier citable final_traceability_dossier.md internal (o arquivo _internal.md)

    Registro malformado ergue `ValueError` antes do use case (o `main` traduz em exit 2).
    """
    parser = importlib.import_module(f"{__package__}.{_DOSSIER_REGISTER}")
    register: tuple[DossierEntry, ...] = parser.load_register(register_path)
    result = generate(
        GenerateReportArtifactsCommand(
            name=name,
            revision=revision,
            preregistration_ref=preregistration_ref,
            cohort_seeds=tuple(cohort_seeds),
            register=register,
        )
    )
    lines = [
        f"report {result.preregistration_ref}: generation_digest {result.generation_digest} "
        f"figures {len(result.figures)} register_entries {result.register_entries}",
        *(f"figure {figure_id} data_digest {digest}" for figure_id, digest in result.figures),
        f"dossier citable {CITABLE_FILE} internal {INTERNAL_FILE}",
    ]
    out.write("".join(f"{line}\n" for line in lines))
    return 0
