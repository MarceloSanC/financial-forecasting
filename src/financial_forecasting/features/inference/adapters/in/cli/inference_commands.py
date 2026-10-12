"""Comando `infer` da CLI — adapter primário fino do slice `inference` (Stage 7.1).

    python -m financial_forecasting.cli infer --data-root <dir> --cohort <toml>
        [--break-stale-lock] [--cross-environment "<justificativa>"]

Carregado pelo `cli.py` por `importlib` (o pacote `in` é keyword, LAYOUT §8). Traduz
os argumentos em `RunInferenceCommand`, chama o `RunInference` montado pela fábrica
do composition root e imprime uma linha por run e uma de resumo (o contrato de saída
da Etapa E, technical 7.1 §1). Erros (`ApplicationError`, `ValueError`) sobem para o
`main`, que os traduz em mensagem e exit 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from financial_forecasting.features.inference.application.use_cases.run_inference import (
    RunInferenceCommand,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from typing import TextIO

    from financial_forecasting.features.inference.application.use_cases.run_inference import (
        RunInference,
    )
    from financial_forecasting.features.modeling.application.dtos.cohort_spec import (
        CohortSpec,
    )

_STRICT = "strict"


def infer(  # noqa: PLR0913 — opções coesas do subcomando
    run_inference_for: Callable[[Path, str], RunInference],
    spec: CohortSpec,
    cohort_path: Path,
    *,
    out: TextIO,
    break_stale_lock: bool = False,
    cross_environment: str | None = None,
) -> int:
    """Roda a inferência do cohort e imprime o desfecho de cada run; devolve 0."""
    run_inference = run_inference_for(cohort_path, spec.device)
    result = run_inference(
        RunInferenceCommand(
            spec=spec,
            break_stale_lock=break_stale_lock,
            cross_environment_justification=cross_environment,
        )
    )
    for outcome in result.outcomes:
        out.write(
            f"run {outcome.run_id} fold {outcome.fold_index} seed {outcome.seed}: "
            f"{outcome.reproduction_mode} compared {outcome.test_values_compared} "
            f"max|d| {outcome.max_abs_diff:.3e} max|d|/s {outcome.max_normalized_diff:.3e} "
            f"calib written {outcome.calib_rows_written} verified {outcome.calib_rows_verified}\n"
        )
    strict = sum(1 for outcome in result.outcomes if outcome.reproduction_mode == _STRICT)
    written = sum(outcome.calib_rows_written for outcome in result.outcomes)
    verified = sum(outcome.calib_rows_verified for outcome in result.outcomes)
    total = len(result.outcomes)
    out.write(
        f"inference {result.cohort_id}: {total} runs ({strict} strict, "
        f"{total - strict} tolerance); calib rows written {written}, verified {verified}\n"
    )
    return 0
