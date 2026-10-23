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
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from financial_forecasting.features.evaluation.application.dtos.confirmatory_run import (
    InferenceSummary,
    RunConfirmatoryEvaluationCommand,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import TextIO

    from financial_forecasting.features.evaluation.application.use_cases.run_confirmatory_evaluation import (  # noqa: E501
        RunConfirmatoryEvaluation,
    )

ATTESTATION_SEPARATOR: Final = "--- attestation ---"


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
