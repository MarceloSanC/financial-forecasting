"""Comandos `infer` (7.1) e `attribute` (7.3) da CLI — adapter primário fino do `inference`.

    python -m financial_forecasting.cli infer --data-root <dir> --cohort <toml>
        [--break-stale-lock] [--cross-environment "<justificativa>"]
    python -m financial_forecasting.cli attribute --data-root <dir> --cohort <toml>
        --ablation-cohort <toml> [--break-stale-lock] [--cross-environment "<just.>"]

Carregado pelo `cli.py` por `importlib` (o pacote `in` é keyword, LAYOUT §8). Traduz
os argumentos em `RunInferenceCommand`, chama o `RunInference` montado pela fábrica
do composition root e imprime uma linha por run e uma de resumo (o contrato de saída
da Etapa E, technical 7.1 §1). Erros (`ApplicationError`, `ValueError`) sobem para o
`main`, que os traduz em mensagem e exit 2.

`infer_with_summary` (Stage 8.1, D1) é o corpo do `infer`: imprime as mesmas linhas e
devolve o resumo como dado (`runs`, `strict`, `tolerance`, `max_abs_diff` = o maior
|Δ| dos runs, `calib_rows_written`, `calib_rows_verified`), que o `cli.py` passa à
corrida confirmatória do `evaluation` sem que um slice importe o outro. O `infer` a
chama e devolve `0`: o contrato do comando não muda.

O `attribute` recebe a partição de famílias já lida pelo `cli.py` (o `[partition]` do
arquivo de ablação, pelo loader do `modeling`): este slice nunca importa o loader do
`modeling` (technical 7.3 §1). Saída: uma linha por run e uma de resumo (technical 7.3
§1 "Saída do `attribute`").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from financial_forecasting.features.inference.application.use_cases.run_inference import (
    RunInferenceCommand,
)
from financial_forecasting.features.inference.application.use_cases.run_permutation_inference import (  # noqa: E501
    RunPermutationInferenceCommand,
)
from financial_forecasting.features.inference.domain.services.reproduction_policy import STRICT

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path
    from typing import TextIO

    from financial_forecasting.features.inference.application.use_cases.run_inference import (
        RunInference,
    )
    from financial_forecasting.features.inference.application.use_cases.run_permutation_inference import (  # noqa: E501
        RunPermutationInference,
    )
    from financial_forecasting.features.modeling.application.dtos.cohort_spec import (
        CohortSpec,
    )


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
    infer_with_summary(
        run_inference_for,
        spec,
        cohort_path,
        out=out,
        break_stale_lock=break_stale_lock,
        cross_environment=cross_environment,
    )
    return 0


def infer_with_summary(  # noqa: PLR0913 — as mesmas opções do `infer`
    run_inference_for: Callable[[Path, str], RunInference],
    spec: CohortSpec,
    cohort_path: Path,
    *,
    out: TextIO,
    break_stale_lock: bool = False,
    cross_environment: str | None = None,
) -> Mapping[str, object]:
    """O `infer` que devolve o resumo da inferência (ver docstring do módulo)."""
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
    strict = sum(1 for outcome in result.outcomes if outcome.reproduction_mode == STRICT)
    written = sum(outcome.calib_rows_written for outcome in result.outcomes)
    verified = sum(outcome.calib_rows_verified for outcome in result.outcomes)
    total = len(result.outcomes)
    out.write(
        f"inference {result.cohort_id}: {total} runs ({strict} strict, "
        f"{total - strict} tolerance); calib rows written {written}, verified {verified}\n"
    )
    return {
        "runs": total,
        "strict": strict,
        "tolerance": total - strict,
        "max_abs_diff": max((outcome.max_abs_diff for outcome in result.outcomes), default=0.0),
        "calib_rows_written": written,
        "calib_rows_verified": verified,
    }


_VERIFIED = "verified"


def attribute(  # noqa: PLR0913 — opções coesas do subcomando
    permutation_inference_for: Callable[[Path], RunPermutationInference],
    spec: CohortSpec,
    cohort_path: Path,
    family_partition: Mapping[str, tuple[str, ...]],
    base_cohort_hash: str,
    *,
    out: TextIO,
    break_stale_lock: bool = False,
    cross_environment: str | None = None,
) -> int:
    """Roda a atribuição do candidato e imprime o desfecho de cada run; devolve 0."""
    run_permutation_inference = permutation_inference_for(cohort_path)
    result = run_permutation_inference(
        RunPermutationInferenceCommand(
            spec=spec,
            family_partition=family_partition,
            base_cohort_hash=base_cohort_hash,
            break_stale_lock=break_stale_lock,
            cross_environment_justification=cross_environment,
        )
    )
    for outcome in result.outcomes:
        if outcome.status == _VERIFIED:
            counts = (
                f"permuted verified {outcome.permuted_rows_verified} "
                f"vsn verified {outcome.vsn_rows_verified}"
            )
        else:
            counts = (
                f"permuted written {outcome.permuted_rows_written} "
                f"vsn written {outcome.vsn_rows_written}"
            )
        out.write(
            f"run {outcome.run_id} fold {outcome.fold_index} seed {outcome.seed}: "
            f"{outcome.reproduction_mode} identity compared {outcome.identity_values_compared} "
            f"max|d| {outcome.max_abs_diff:.3e} max|d|/s {outcome.max_normalized_diff:.3e} "
            f"{counts}\n"
        )
    outcomes = result.outcomes
    total = len(outcomes)
    strict = sum(1 for outcome in outcomes if outcome.reproduction_mode == STRICT)
    out.write(
        f"attribution {result.cohort_id}: {total} runs ({strict} strict, "
        f"{total - strict} tolerance); "
        f"permuted rows written {sum(o.permuted_rows_written for o in outcomes)}, "
        f"verified {sum(o.permuted_rows_verified for o in outcomes)}; "
        f"vsn rows written {sum(o.vsn_rows_written for o in outcomes)}, "
        f"verified {sum(o.vsn_rows_verified for o in outcomes)}\n"
    )
    return 0
