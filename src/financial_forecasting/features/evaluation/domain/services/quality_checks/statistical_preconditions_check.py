"""Passo de pré-condições estatísticas e o check `statistical_preconditions` (ERROR, 6.4).

Concept 6.4 I11, C6; ADR `6_4_0002` item 4. O **passo de domínio** roda antes da
fábrica `paired_pinball_losses` e do `McsBackend`, que validariam as mesmas condições
erguendo:

- `models_suffice(models)`: k ≥ `MIN_MODELS` (constante pública do VO
  `PairedLossSeries`, o primeiro dono) — antes da fábrica;
- `block_request_defect(differential)`: por par, `is_constant` (diferencial constante)
  e `validate_block_length_request` (série que o backend recusaria) — os donos da 6.2;
  o par com defeito ganha estimativa indefinida **sem** chamar o backend.

O check traduz o resultado em linhas: montagem que falhou → um `SKIPPED`; por
horizonte, k < `MIN_MODELS` → `FAIL` `insufficient_models`; cada motivo de
`BlockEstimate` indefinida → `FAIL` com `kind` = o motivo, agregado por (motivo,
horizonte) com o primeiro par no detalhe; senão `PASS` por horizonte.
"""

from __future__ import annotations

from collections.abc import Sequence

from financial_forecasting.features.evaluation.domain.services.quality_checks.registry import (
    QualityCheckContext,
    result_of,
)
from financial_forecasting.features.evaluation.domain.value_objects._paired_inputs import (
    is_constant,
)
from financial_forecasting.features.evaluation.domain.value_objects.block_estimate import (
    BlockEstimate,
    UndefinedReason,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    validate_block_length_request,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    MIN_MODELS,
)
from financial_forecasting.features.evaluation.domain.value_objects.quality_check_result import (
    CheckOutcome,
    CheckSeverity,
    QualityCheckResult,
)

STATISTICAL_PRECONDITIONS = "statistical_preconditions"
INSUFFICIENT_MODELS = "insufficient_models"
PRECONDITIONS_MET = "preconditions_met"
ASSEMBLY_FAILED = "assembly_failed"


def models_suffice(models: Sequence[str]) -> bool:
    """k ≥ `MIN_MODELS`: a fábrica de L_t pareadas pode ser chamada."""
    return len(models) >= MIN_MODELS


def block_request_defect(differential: Sequence[float]) -> UndefinedReason | None:
    """Motivo pelo qual o b̂_sb do diferencial não pode ir ao backend, ou `None`.

    Diferencial constante → `CONSTANT_DIFFERENTIAL` (precede: a var > 0 é a
    pré-condição do MCS); série que `validate_block_length_request` recusa (curta
    demais, não-finita) → `INVALID_SERIES`.
    """
    if is_constant(differential):
        return UndefinedReason.CONSTANT_DIFFERENTIAL
    try:
        validate_block_length_request(differential)
    except ValueError:
        return UndefinedReason.INVALID_SERIES
    return None


class StatisticalPreconditionsCheck:
    """Resultados do passo de pré-condições por horizonte."""

    name = STATISTICAL_PRECONDITIONS
    severity = CheckSeverity.ERROR

    def run(self, context: QualityCheckContext) -> tuple[QualityCheckResult, ...]:
        """SKIPPED sem montagem; por horizonte FAIL (k, estimativas) ou PASS."""
        assembled = context.assembled
        if assembled.alignment.findings:
            return (
                result_of(
                    self,
                    CheckOutcome.SKIPPED,
                    ASSEMBLY_FAILED,
                    detail=(
                        f"series assembly reported {len(assembled.alignment.findings)} "
                        "finding(s); no paired sample to check"
                    ),
                ),
            )
        results: list[QualityCheckResult] = []
        for samples in assembled.horizons:
            horizon = samples.horizon
            if not models_suffice(samples.models):
                results.append(
                    result_of(
                        self,
                        CheckOutcome.FAIL,
                        INSUFFICIENT_MODELS,
                        horizon=horizon,
                        value=float(len(samples.models)),
                        detail=(
                            f"k={len(samples.models)} model(s) {samples.models}; the paired "
                            f"inference needs k >= {MIN_MODELS}"
                        ),
                    )
                )
                continue
            failures = _undefined_by_reason(context.block_estimates.get(horizon, ()))
            if not failures:
                results.append(
                    result_of(
                        self,
                        CheckOutcome.PASS,
                        PRECONDITIONS_MET,
                        horizon=horizon,
                        detail=f"k={len(samples.models)}; every pair has a block estimate",
                    )
                )
                continue
            for reason, estimates in failures:
                first = estimates[0]
                results.append(
                    result_of(
                        self,
                        CheckOutcome.FAIL,
                        reason.value,
                        horizon=horizon,
                        occurrences=len(estimates),
                        detail=f"pair {first.pair}: {reason.value} ({first.detail})",
                    )
                )
        return tuple(results)


def _undefined_by_reason(
    estimates: Sequence[BlockEstimate],
) -> list[tuple[UndefinedReason, list[BlockEstimate]]]:
    grouped: dict[UndefinedReason, list[BlockEstimate]] = {}
    for estimate in estimates:
        if estimate.reason is not None:
            grouped.setdefault(estimate.reason, []).append(estimate)
    return [(reason, grouped[reason]) for reason in UndefinedReason if reason in grouped]
