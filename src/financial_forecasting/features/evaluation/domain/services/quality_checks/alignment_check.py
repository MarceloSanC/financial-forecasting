"""Check `alignment_check` (ERROR) — traduz o `AlignmentReport` em resultados (6.4).

Concept 6.4 I2, C5; ADR `6_4_0002` item 3. Não re-deriva nada: as regras I3-I10 são do
`SeriesAssembly`. Com achados, um `FAIL` por (tipo, horizonte, modelo, seed) com o
número de ocorrências e o `detail` do primeiro achado (na ordem do relatório); sem
achado, um `PASS` por horizonte com o T da amostra comum em `value`.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.domain.services.quality_checks.registry import (
    QualityCheckContext,
    result_of,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    AlignmentFinding,
)
from financial_forecasting.features.evaluation.domain.value_objects.quality_check_result import (
    CheckOutcome,
    CheckSeverity,
    QualityCheckResult,
)

ALIGNMENT_CHECK = "alignment_check"
COMMON_SAMPLE_SIZE = "common_sample_size"

Scope = tuple[str, int | None, str | None, int | None]


class AlignmentCheck:
    """Tradução do relatório de alinhamento da montagem."""

    name = ALIGNMENT_CHECK
    severity = CheckSeverity.ERROR

    def run(self, context: QualityCheckContext) -> tuple[QualityCheckResult, ...]:
        """FAIL agregado por (tipo, escopo), ou PASS por horizonte com T."""
        alignment = context.assembled.alignment
        if not alignment.findings:
            return tuple(
                result_of(
                    self,
                    CheckOutcome.PASS,
                    COMMON_SAMPLE_SIZE,
                    horizon=horizon,
                    value=float(n_points),
                    detail=f"common sample of T={n_points} points",
                )
                for horizon, n_points in alignment.common_points
            )
        groups: dict[Scope, list[AlignmentFinding]] = {}
        for finding in alignment.findings:
            key = (finding.kind.value, finding.horizon, finding.model, finding.seed)
            groups.setdefault(key, []).append(finding)
        return tuple(
            result_of(
                self,
                CheckOutcome.FAIL,
                kind,
                horizon=horizon,
                model=model,
                seed=seed,
                occurrences=len(findings),
                detail=findings[0].detail,
            )
            for (kind, horizon, model, seed), findings in groups.items()
        )
