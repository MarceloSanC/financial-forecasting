"""Serviço de domínio `JointContribution` — o bootstrap conjunto dos dois métodos de H3 (7.3).

Stdlib-only (concept 7.3 §4, I12; ADR 7.3.0005 H3-BLOCK, id
`max_7_ceil_max_bsb_joint_16_series_v1`). A política do bloco mora aqui; o `RefreshGold`
só orquestra (C8-15):

- o bloco é CONJUNTO: `block_length_rule(horizon=7, max_estimate=max b̂)` sobre as 16
  séries d_t (2 métodos x 4 famílias x 2 horizontes), e uma chamada de
  `bootstrap_indices` serve aos dois métodos, às 4 famílias e aos 2 horizontes;
- sem um dos métodos não há bloco conjunto: nenhum bootstrap roda e os dois relatórios
  saem `undefined` (o método montado com `JOINT_BLOCK_NEEDS_BOTH`; o outro com o motivo
  da montagem) — C8-1;
- série que não serve ao b̂ (`validate_block_length_request`) ou `ArithmeticError` do
  backend deixam os dois relatórios `undefined` ("bootstrap undefined: …"); qualquer
  outra exceção propaga (erro de programação).

O backend é recebido por um `Protocol` local (o mesmo contrato do port `McsBackend` da
application), para que o domain não importe a application.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from financial_forecasting.features.evaluation.domain.services.family_contribution import (
    UNDEFINED,
    FamilyContribution,
    FamilyContributionReport,
    FamilyShare,
)
from financial_forecasting.features.evaluation.domain.services.model_confidence_set import (
    block_length_rule,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapIndices,
    BootstrapScheme,
    validate_block_length_request,
)
from financial_forecasting.features.evaluation.domain.value_objects.family_loss_differentials import (  # noqa: E501
    H3_HORIZONS,
    LOCO,
    PERMUTATION,
    FamilyLossDifferentials,
)
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3_FAMILIES,
)

JOINT_BLOCK_NEEDS_BOTH: Final = "bootstrap undefined: joint block needs both methods (16 series)"


class BlockBackend(Protocol):
    """O que o bootstrap conjunto usa do backend (o contrato do port `McsBackend`)."""

    def optimal_block_length(self, *, series: Sequence[float]) -> float: ...

    def bootstrap_indices(
        self, *, n_obs: int, block_size: int, reps: int, seed: int, scheme: BootstrapScheme
    ) -> BootstrapIndices: ...


@dataclass(frozen=True)
class JointContributionResult:
    """Os relatórios dos dois métodos e o bloco do bootstrap conjunto (`None` sem ele)."""

    permutation: FamilyContributionReport
    ablation: FamilyContributionReport
    block_length: int | None
    max_block_estimate: float | None


class _BootstrapUndefined(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def undefined_report(
    method: str,
    reason: str,
    level: float,
    differentials: FamilyLossDifferentials | None = None,
) -> FamilyContributionReport:
    """O relatório de um método sem bootstrap: 4 famílias `undefined` com o motivo.

    Com as séries d_t do método, a importância I_f(h) continua calculada (a média em t),
    para que a tabela de importância não perca o ponto (C8-11).
    """
    importance = (
        {}
        if differentials is None
        else {
            key: math.fsum(values) / len(values)
            for key, values in differentials.differentials.items()
        }
    )
    return FamilyContributionReport(
        method=method,
        importance=importance,
        shares=tuple(
            FamilyShare(f, None, None, None, None, None, None, None, UNDEFINED, reason)
            for f in H3_FAMILIES
        ),
        level=level,
        nonpositive_replicas={},
        status=UNDEFINED,
        reason=reason,
        heterogeneous=None,
    )


def _max_block_estimate(methods: Sequence[FamilyLossDifferentials], backend: BlockBackend) -> float:
    """O maior b̂ das 16 séries, na ordem método → família → horizonte."""
    estimates: list[float] = []
    for differentials in methods:
        for family in H3_FAMILIES:
            for horizon in H3_HORIZONS:
                series = differentials.differentials[(family, horizon)]
                try:
                    validate_block_length_request(series)
                except ValueError as exc:
                    raise _BootstrapUndefined(
                        f"{differentials.method} ({family}, {horizon}): invalid series ({exc})"
                    ) from None
                try:
                    estimates.append(backend.optimal_block_length(series=series))
                except ArithmeticError as exc:
                    raise _BootstrapUndefined(
                        f"{differentials.method} ({family}, {horizon}): {type(exc).__name__}: {exc}"
                    ) from None
    return max(estimates)


class JointContribution:
    """Os dois relatórios de H3 sobre um bootstrap conjunto (ver docstring do módulo)."""

    @staticmethod
    def evaluate(  # noqa: PLR0913 — as séries, os motivos e o plano do bootstrap
        *,
        permutation: FamilyLossDifferentials | None,
        ablation: FamilyLossDifferentials | None,
        permutation_reason: str | None,
        ablation_reason: str | None,
        backend: BlockBackend,
        reps: int,
        seed: int,
        level: float,
    ) -> JointContributionResult:
        """Bloco conjunto, uma chamada de índices e os dois `FamilyContribution`."""
        if permutation is None or ablation is None:
            return JointContributionResult(
                permutation=undefined_report(
                    PERMUTATION,
                    str(permutation_reason) if permutation is None else JOINT_BLOCK_NEEDS_BOTH,
                    level,
                    permutation,
                ),
                ablation=undefined_report(
                    LOCO,
                    str(ablation_reason) if ablation is None else JOINT_BLOCK_NEEDS_BOTH,
                    level,
                    ablation,
                ),
                block_length=None,
                max_block_estimate=None,
            )
        try:
            max_estimate = _max_block_estimate((permutation, ablation), backend)
        except _BootstrapUndefined as exc:
            reason = f"bootstrap undefined: {exc.reason}"
            return JointContributionResult(
                permutation=undefined_report(PERMUTATION, reason, level, permutation),
                ablation=undefined_report(LOCO, reason, level, ablation),
                block_length=None,
                max_block_estimate=None,
            )
        block = block_length_rule(horizon=max(H3_HORIZONS), max_estimate=max_estimate)
        indices = backend.bootstrap_indices(
            n_obs=len(permutation.decision_timestamps),
            block_size=block,
            reps=reps,
            seed=seed,
            scheme=BootstrapScheme.STATIONARY,
        )
        return JointContributionResult(
            permutation=FamilyContribution.evaluate(permutation, bootstrap=indices, level=level),
            ablation=FamilyContribution.evaluate(ablation, bootstrap=indices, level=level),
            block_length=block,
            max_block_estimate=max_estimate,
        )
