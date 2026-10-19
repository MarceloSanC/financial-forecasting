"""Serviço de domínio `ContributionAgreement` — a leitura mecânica de H3 (Stage 7.3).

Stdlib-only (concept 7.3 §4, I15; ADR 7.3.0005 H3-READ). Junta os relatórios dos dois
métodos: H3 é sustentada quando alguma família exclui 0 nos DOIS métodos com o mesmo
sinal de Δ̂. Um método `undefined` (total não positivo, bootstrap indefinido) deixa a
leitura `undefined` com o motivo e `sustained = False` — nunca "não sustentada" sem
motivo. O rótulo é fixo: a leitura é descritiva, sem claim causal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from financial_forecasting.features.evaluation.domain.services.family_contribution import (
    OK,
    UNDEFINED,
    FamilyContributionReport,
)

H3_LABEL: Final = "descritiva (sem claim causal)"


@dataclass(frozen=True)
class H3Reading:
    """A leitura de H3 sobre os dois métodos."""

    heterogeneous_permutation: bool | None
    heterogeneous_ablation: bool | None
    sustained: bool
    agreeing_families: tuple[str, ...]
    status: str
    reason: str | None
    label: str = H3_LABEL


class ContributionAgreement:
    """Leitura mecânica de H3 (ver docstring do módulo)."""

    @staticmethod
    def read(
        permutation: FamilyContributionReport, ablation: FamilyContributionReport
    ) -> H3Reading:
        """`sustained` ⇔ ∃ família `ok` que exclui 0 nos dois métodos com o mesmo lado."""
        undefined = [
            f"{report.method}: {report.reason}"
            for report in (permutation, ablation)
            if report.status != OK
        ]
        if undefined:
            return H3Reading(
                heterogeneous_permutation=(
                    permutation.heterogeneous if permutation.status == OK else None
                ),
                heterogeneous_ablation=ablation.heterogeneous if ablation.status == OK else None,
                sustained=False,
                agreeing_families=(),
                status=UNDEFINED,
                reason="; ".join(undefined),
            )
        by_family = {share.family: share for share in ablation.shares}
        agreeing = tuple(
            sorted(
                share.family
                for share in permutation.shares
                if share.status == OK
                and share.excludes_zero
                and (other := by_family.get(share.family)) is not None
                and other.status == OK
                and other.excludes_zero
                and other.side == share.side
            )
        )
        return H3Reading(
            heterogeneous_permutation=permutation.heterogeneous,
            heterogeneous_ablation=ablation.heterogeneous,
            sustained=bool(agreeing),
            agreeing_families=agreeing,
            status=OK,
            reason=None,
        )
