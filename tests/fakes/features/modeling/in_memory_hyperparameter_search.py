"""Fake in-memory do port `HyperparameterSearch` — amostrador determinístico.

Aplica a MESMA semântica observável do adapter real (`OptunaSearch`): numera os
trials a partir de 0, respeita os limites de cada dimensão, acumula os objetivos
informados e ergue em `best_trial` sobre estudo sem nenhum `tell` (C9).

**A amostragem é uma grade regular, não aleatória, de propósito.** A suite de
contrato compara fake e real em COMPORTAMENTO observável — limites respeitados,
numeração, melhor trial —, nunca em convergência: o real usa TPE, que é
estocástico por desenho. Um fake que tentasse imitar o TPE tornaria o contrato
refém do amostrador da biblioteca sem provar nada a mais.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    SearchTrial,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (  # noqa: E501
        SearchDimension,
    )

_INT_KIND = "int"
# Passos da grade determinística: o k-ésimo trial cai na fração
# `(k % _GRID_STEPS) / (_GRID_STEPS - 1)` do intervalo de cada dimensão.
_GRID_STEPS = 5


class InMemoryHyperparameterSearch:
    """Fake determinístico que satisfaz o port por duck-typing."""

    def __init__(self) -> None:
        self.study_id: str | None = None
        self.seed: int | None = None
        self.direction = "minimize"
        self.trials: list[SearchTrial] = []
        self.objectives: dict[int, float] = {}

    def create_study(self, *, seed: int, direction: str = "minimize") -> str:
        self.seed = seed
        self.direction = direction
        self.study_id = f"fake-study-{seed}"
        return self.study_id

    def ask(self, space: Sequence[SearchDimension]) -> SearchTrial:
        number = len(self.trials)
        position = number % _GRID_STEPS
        fraction = position / (_GRID_STEPS - 1)
        values: dict[str, float] = {}
        for dimension in space:
            raw = dimension.low + fraction * (dimension.high - dimension.low)
            values[dimension.name] = (
                float(round(raw)) if dimension.kind == _INT_KIND else float(raw)
            )
        trial = SearchTrial(number=number, values=values)
        self.trials.append(trial)
        return trial

    def tell(self, *, trial_number: int, objective_value: float) -> None:
        if trial_number not in {trial.number for trial in self.trials}:
            msg = f"trial {trial_number} não foi pedido a este estudo"
            raise ValueError(msg)
        self.objectives[trial_number] = objective_value

    def best_trial(self) -> SearchTrial:
        if not self.objectives:
            msg = "nenhum trial informado — não há melhor trial (C9)"
            raise ValueError(msg)
        pick = min if self.direction == "minimize" else max
        best_number = pick(self.objectives, key=lambda number: self.objectives[number])
        return next(trial for trial in self.trials if trial.number == best_number)
