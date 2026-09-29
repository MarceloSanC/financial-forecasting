"""Check `degeneracy_check` (WARN) — taxa de degeneração por série na `model_full` (6.4).

Concept 6.4 I13, C8; ADR `6_4_0002` item 5. Roda o `DegeneracyGate` (6.1) sobre a
série **completa** (amostra `model_full`) de cada (modelo, seed, horizonte), com a
tolerância do refresh, e reporta a taxa em `value` — sem limiar e sem excluir linhas
(o limiar é da 6.5). Sem montagem não há série: um `SKIPPED` com o motivo.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.domain.services.degeneracy_gate import (
    DegeneracyGate,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.registry import (
    QualityCheckContext,
    result_of,
)
from financial_forecasting.features.evaluation.domain.value_objects.quality_check_result import (
    CheckOutcome,
    CheckSeverity,
    QualityCheckResult,
)

DEGENERACY_CHECK = "degeneracy_check"
DEGENERACY_RATE = "degeneracy_rate"
ASSEMBLY_FAILED = "assembly_failed"


class DegeneracyCheck:
    """Taxa de linhas colapsadas por (modelo, seed, horizonte), sempre reportada."""

    name = DEGENERACY_CHECK
    severity = CheckSeverity.WARN

    def run(self, context: QualityCheckContext) -> tuple[QualityCheckResult, ...]:
        """REPORTED por série `full`, ou um SKIPPED quando a montagem falhou."""
        assembled = context.assembled
        if assembled.alignment.findings:
            return (
                result_of(
                    self,
                    CheckOutcome.SKIPPED,
                    ASSEMBLY_FAILED,
                    detail=(
                        f"series assembly reported {len(assembled.alignment.findings)} "
                        "finding(s); no series to measure"
                    ),
                ),
            )
        results: list[QualityCheckResult] = []
        for samples in assembled.horizons:
            for model in samples.models:
                for seed, series in zip(samples.seeds[model], samples.full[model], strict=True):
                    report = DegeneracyGate.evaluate(series, tolerance=context.tolerance)
                    results.append(
                        result_of(
                            self,
                            CheckOutcome.REPORTED,
                            DEGENERACY_RATE,
                            horizon=samples.horizon,
                            model=model,
                            seed=seed,
                            value=report.rate,
                            detail=(
                                f"{report.n_degenerate}/{report.n_points} degenerate rows "
                                f"(model_full, tolerance {report.tolerance!r})"
                            ),
                        )
                    )
        return tuple(results)
