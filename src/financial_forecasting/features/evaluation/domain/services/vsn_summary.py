"""Serviço de domínio `VsnSummary` — o resumo dos pesos da VSN do candidato (Stage 7.3).

Stdlib-only (concept 7.3 §4; ADR 7.3.0005 H3-VSN, regra
`per_decision_seed_mean_p10_p50_p90_family_sum_v1`). Por decisão de teste, o peso de cada
variável é a média nas seeds; o peso de uma família é a soma das suas variáveis nessa
decisão. Sobre as decisões, p10, p50 e p90 (quantis tipo 7, `linear_quantile`). Variáveis
fora das quatro famílias (calendário, alvo passado, índice relativo de tempo) saem como
variáveis com família `"none"`, sem linha de família. O rótulo é fixo: o peso da VSN não
depende do horizonte e descreve quanto o modelo usa cada família.

Seed ausente, decisões diferentes entre as seeds, folds sobrepostos, variáveis
diferentes ou feature da partição sem peso deixam o resumo `undefined` com o motivo.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from financial_forecasting.features.evaluation.domain.services.family_contribution import (
    OK,
    UNDEFINED,
    linear_quantile,
)
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3Parameters,
)
from financial_forecasting.features.evaluation.domain.value_objects.vsn_run_weights import (
    VsnRunWeights,
)

VSN_LABEL: Final = "horizonte-invariante; descreve quanto o modelo usa cada família"
VARIABLE: Final = "variable"
FAMILY: Final = "family"
NO_FAMILY: Final = "none"
_PERCENTILES = (0.1, 0.5, 0.9)


@dataclass(frozen=True)
class VsnEntry:
    """Uma linha do resumo: uma variável ou uma família, com p10/p50/p90 nas decisões."""

    kind: str
    name: str
    family: str
    p10: float
    p50: float
    p90: float
    n_decisions: int


@dataclass(frozen=True)
class VsnSummaryReport:
    """O resumo da VSN, ou `undefined` com o motivo."""

    entries: tuple[VsnEntry, ...]
    status: str
    reason: str | None
    label: str = VSN_LABEL


class _Undefined(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _per_seed(
    reductions: Sequence[VsnRunWeights], seeds: tuple[int, ...]
) -> dict[int, dict[str, Mapping[str, float]]]:
    """Decisão → pesos de cada seed, unindo os folds (decisões disjuntas)."""
    by_seed: dict[int, dict[str, Mapping[str, float]]] = {}
    for reduction in sorted(reductions, key=lambda r: (r.seed, r.fold_index)):
        weights = by_seed.setdefault(reduction.seed, {})
        overlap = sorted(set(weights) & set(reduction.weights))
        if overlap:
            raise _Undefined(f"seed {reduction.seed}: decision {overlap[0]} in two folds")
        weights.update(reduction.weights)
    missing = sorted(set(seeds) - set(by_seed))
    if missing:
        raise _Undefined(f"seed {missing[0]} has no vsn weights")
    extra = sorted(set(by_seed) - set(seeds))
    if extra:
        raise _Undefined(f"seed {extra[0]} is not a seed of the candidate")
    decision_sets = {frozenset(by_seed[s]) for s in seeds}
    if len(decision_sets) != 1:
        raise _Undefined("the vsn decisions differ between seeds")
    variable_sets = {frozenset(row) for s in seeds for row in by_seed[s].values()}
    if len(variable_sets) != 1:
        raise _Undefined("the vsn variables differ between decisions or seeds")
    return by_seed


def _entry(kind: str, name: str, family: str, values: Sequence[float]) -> VsnEntry:
    p10, p50, p90 = (linear_quantile(values, p) for p in _PERCENTILES)
    return VsnEntry(kind, name, family, p10, p50, p90, len(values))


class VsnSummary:
    """Resumo da VSN por variável e por família (ver docstring do módulo)."""

    @staticmethod
    def summarize(
        reductions: Sequence[VsnRunWeights], *, parameters: H3Parameters, seeds: tuple[int, ...]
    ) -> VsnSummaryReport:
        """p10/p50/p90 nas decisões da média nas seeds, por variável e por família."""
        try:
            by_seed = _per_seed(reductions, seeds)
        except _Undefined as exc:
            return VsnSummaryReport(entries=(), status=UNDEFINED, reason=exc.reason)
        decisions = sorted(by_seed[seeds[0]])
        variables = sorted(by_seed[seeds[0]][decisions[0]])
        missing = sorted(
            feature
            for features in parameters.partition.values()
            for feature in features
            if feature not in variables
        )
        if missing:  # C7-5: família sem peso não é "peso zero"
            return VsnSummaryReport(
                entries=(),
                status=UNDEFINED,
                reason=f"partition features without a vsn weight: {missing[:3]}",
            )
        mean = {
            (decision, variable): math.fsum(by_seed[s][decision][variable] for s in seeds)
            / len(seeds)
            for decision in decisions
            for variable in variables
        }
        family_of = {
            feature: family
            for family, features in parameters.partition.items()
            for feature in features
        }
        entries = [
            _entry(
                VARIABLE,
                variable,
                family_of.get(variable, NO_FAMILY),
                [mean[(d, variable)] for d in decisions],
            )
            for variable in variables
        ]
        for family in parameters.families:
            members = [v for v in variables if family_of.get(v) == family]
            entries.append(
                _entry(
                    FAMILY,
                    family,
                    family,
                    [math.fsum(mean[(d, v)] for v in members) for d in decisions],
                )
            )
        return VsnSummaryReport(entries=tuple(entries), status=OK, reason=None)
