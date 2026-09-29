"""Check `realized_provenance` (WARN) — proveniência do realizado consumido (6.4).

Concept 6.4 I16; ADR `6_4_0002` item 6, ADR `6_4_0004` item 4. Um `REPORTED` com o
`math.fsum` dos `target_return` em `value` e, no `detail`, o `DatasetFingerprint` do
dataset lido, o número de sessões e a primeira e a última sessão — o resumo descritivo
que o `RealizedReturns` computa uma vez.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.domain.services.quality_checks.registry import (
    QualityCheckContext,
    result_of,
)
from financial_forecasting.features.evaluation.domain.value_objects.quality_check_result import (
    CheckOutcome,
    CheckSeverity,
    QualityCheckResult,
)

REALIZED_PROVENANCE = "realized_provenance"
TARGET_RETURN_FSUM = "target_return_fsum"


class RealizedProvenanceCheck:
    """Fingerprint do dataset e resumo do `target_return` consumido."""

    name = REALIZED_PROVENANCE
    severity = CheckSeverity.WARN

    def run(self, context: QualityCheckContext) -> tuple[QualityCheckResult, ...]:
        """Um REPORTED com `value = returns_fsum`."""
        realized = context.realized
        return (
            result_of(
                self,
                CheckOutcome.REPORTED,
                TARGET_RETURN_FSUM,
                value=realized.returns_fsum,
                detail=(
                    f"dataset_fingerprint={context.dataset_fingerprint.value}; "
                    f"n_sessions={realized.n_sessions}; first={realized.first_timestamp}; "
                    f"last={realized.last_timestamp}"
                ),
            ),
        )
