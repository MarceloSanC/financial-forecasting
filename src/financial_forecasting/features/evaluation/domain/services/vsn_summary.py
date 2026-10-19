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
from collections.abc import Sequence
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


class VsnAccumulator:
    """A média nas seeds por decisão, acumulada run a run (C8-5a; I19).

    O `RefreshGold` reduz cada run (`reduce_vsn_run`), soma os pesos por (decisão,
    variável) aqui e descarta a redução: o que fica na memória é uma soma por decisão e
    variável e o conjunto de decisões de cada seed — nunca os pesos crus de todos os runs.
    """

    def __init__(self) -> None:
        self._sums: dict[str, dict[str, float]] = {}
        self._decisions: dict[int, set[str]] = {}
        self._variables: frozenset[str] | None = None
        self._failure: str | None = None

    def add(self, run: VsnRunWeights) -> None:
        """Soma os pesos de um run; incoerência vira o motivo do resumo `undefined`."""
        if self._failure is not None:
            return
        decisions = self._decisions.setdefault(run.seed, set())
        overlap = sorted(decisions & set(run.weights))
        if overlap:
            self._failure = f"seed {run.seed}: decision {overlap[0]} in two folds"
            return
        for decision, row in run.weights.items():
            names = frozenset(row)
            if self._variables is None:
                self._variables = names
            elif names != self._variables:
                self._failure = "the vsn variables differ between decisions or seeds"
                return
            sums = self._sums.setdefault(decision, dict.fromkeys(names, 0.0))
            for variable, weight in row.items():
                sums[variable] += weight
        decisions.update(run.weights)

    def means(self, seeds: tuple[int, ...]) -> dict[str, dict[str, float]]:
        """Decisão → variável → média nas seeds.

        Raises:
            _Undefined: run incoerente, seed ausente ou extra, decisões diferentes.
        """
        if self._failure is not None:
            raise _Undefined(self._failure)
        missing = sorted(set(seeds) - set(self._decisions))
        if missing:
            raise _Undefined(f"seed {missing[0]} has no vsn weights")
        extra = sorted(set(self._decisions) - set(seeds))
        if extra:
            raise _Undefined(f"seed {extra[0]} is not a seed of the candidate")
        if len({frozenset(self._decisions[s]) for s in seeds}) != 1:
            raise _Undefined("the vsn decisions differ between seeds")
        return {
            decision: {variable: total / len(seeds) for variable, total in row.items()}
            for decision, row in self._sums.items()
        }


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
        accumulator = VsnAccumulator()
        for reduction in sorted(reductions, key=lambda r: (r.seed, r.fold_index)):
            accumulator.add(reduction)
        return VsnSummary.from_accumulator(accumulator, parameters=parameters, seeds=seeds)

    @staticmethod
    def from_accumulator(
        accumulator: VsnAccumulator, *, parameters: H3Parameters, seeds: tuple[int, ...]
    ) -> VsnSummaryReport:
        """O resumo a partir das médias acumuladas run a run (o caminho do refresh)."""
        try:
            mean_by_decision = accumulator.means(seeds)
        except _Undefined as exc:
            return VsnSummaryReport(entries=(), status=UNDEFINED, reason=exc.reason)
        decisions = sorted(mean_by_decision)
        variables = sorted(mean_by_decision[decisions[0]])
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
            (decision, variable): mean_by_decision[decision][variable]
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
