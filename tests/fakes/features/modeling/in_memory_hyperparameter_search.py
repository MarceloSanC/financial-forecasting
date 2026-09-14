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
from financial_forecasting.features.modeling.domain.exceptions.backend import (
    HyperparameterSearchError,
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
    """Fake determinístico que satisfaz o port por duck-typing.

    `simulate_backend_failure`: quando informado, o fake ergue a exceção do contrato
    (`HyperparameterSearchError`) com essa mensagem no MESMO ponto em que o adapter real chama a
    biblioteca — DEPOIS da regra do port (issue #84). É o que permite ao contract
    test provar que fake e real erguem o mesmo tipo quando "a lib falhou".
    """

    # Default de CLASSE: subclasses de teste que redefinem `__init__` sem chamar
    # `super().__init__()` continuam sem falha simulada.
    _simulate_backend_failure: str | None = None

    def __init__(self, *, simulate_backend_failure: str | None = None) -> None:
        self._simulate_backend_failure = simulate_backend_failure
        self.study_id: str | None = None
        self.seed: int | None = None
        self.direction = "minimize"
        self.trials: list[SearchTrial] = []
        self.objectives: dict[int, float] = {}
        self.failed: set[int] = set()

    def create_study(self, *, seed: int, direction: str = "minimize") -> str:
        self.seed = seed
        self.direction = direction
        self.study_id = f"fake-study-{seed}"
        return self.study_id

    def _backend(self, operation: str) -> None:
        """Ponto em que o real toca o estudo do Optuna: falha simulada, se pedida."""
        if self._simulate_backend_failure is not None:
            msg = f"{operation}: {self._simulate_backend_failure}"
            raise HyperparameterSearchError(msg) from RuntimeError("simulated backend failure")

    def ask(self, space: Sequence[SearchDimension]) -> SearchTrial:
        self._backend("ask")
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
        self._backend("tell")
        self.objectives[trial_number] = objective_value

    def fail(self, *, trial_number: int) -> None:
        if trial_number not in {trial.number for trial in self.trials}:
            msg = f"trial {trial_number} não foi pedido a este estudo"
            raise ValueError(msg)
        self._backend("fail")
        self.failed.add(trial_number)

    def best_trial(self) -> SearchTrial:
        if not self.objectives:
            msg = "nenhum trial informado — não há melhor trial (C9)"
            raise ValueError(msg)
        pick = min if self.direction == "minimize" else max
        best_number = pick(self.objectives, key=lambda number: self.objectives[number])
        return next(trial for trial in self.trials if trial.number == best_number)
