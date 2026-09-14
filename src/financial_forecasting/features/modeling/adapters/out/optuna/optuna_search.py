"""Adapter `OptunaSearch` — implementa `HyperparameterSearch` com Optuna.

Única casa de `optuna` no projeto (concept 5.4 §8, I13). Usa exclusivamente a
API *ask-and-tell*: `study.ask(fixed_distributions=...)` e `study.tell(...)`.
A API de alto nível (`study.optimize(objective, n_trials)`) NÃO é usada — ela
exigiria que a função-objetivo atravessasse a fronteira do port, e com ela toda
a orquestração da varredura (ADR 5.4.0005).

**A semente vive no amostrador, não no estudo.** O port recebe `seed` em
`create_study` porque é lá que o chamador expressa a identidade reprodutível da
busca; o Optuna, porém, semeia o `TPESampler`. A tradução é responsabilidade
deste adapter — é exatamente o tipo de diferença de vocabulário que o port
existe para absorver.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import optuna
from optuna.distributions import FloatDistribution, IntDistribution
from optuna.exceptions import OptunaError
from optuna.samplers import TPESampler
from optuna.trial import TrialState

from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    SearchTrial,
)
from financial_forecasting.features.modeling.domain.exceptions.backend import (
    HyperparameterSearchError,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (  # noqa: E501
        SearchDimension,
    )

_INT_KIND = "int"
# Vocabulário de falha do Optuna 4.9 (issue #84), ENUMERADO: `OptunaError` (raiz
# própria da lib, subclasse direta de `Exception` — `StorageInternalError`,
# `DuplicatedStudyError`, `TrialPruned`…), `RuntimeError` (25 sítios — estado interno
# do estudo/storage) e `KeyError` (36 — lookups internos). `ValueError` fica FORA:
# no ask-and-tell ele é a resposta do estudo a uso indevido pelo CHAMADOR (trial
# desconhecido, `low > high`, dizer duas vezes) — o mesmo `ValueError` que o fake
# ergue, e é o contrato de `best_trial` (C9).
_BACKEND_ERRORS: tuple[type[BaseException], ...] = (OptunaError, RuntimeError, KeyError)
# A varredura roda dezenas de trials; o log padrão do Optuna imprime uma linha
# por trial e polui a saída dos testes e do fluxo autônomo.
optuna.logging.set_verbosity(optuna.logging.WARNING)


@contextmanager
def _translating_backend_errors(operation: str) -> Iterator[None]:
    """Falha ENUMERADA da lib numa operação do estudo → `HyperparameterSearchError`."""
    try:
        yield
    except _BACKEND_ERRORS as exc:
        msg = f"optuna failed in {operation}: {type(exc).__name__}: {exc}"
        raise HyperparameterSearchError(msg) from exc


def _distribution(dimension: SearchDimension) -> Any:  # noqa: ANN401 — tipo da lib
    """Traduz uma dimensão do port para a distribuição da biblioteca."""
    if dimension.kind == _INT_KIND:
        return IntDistribution(low=int(dimension.low), high=int(dimension.high), log=dimension.log)
    return FloatDistribution(
        low=float(dimension.low), high=float(dimension.high), log=dimension.log
    )


class OptunaSearch:
    """Busca *ask-and-tell* sobre Optuna (satisfaz o port por duck-typing)."""

    def __init__(self) -> None:
        self._study: optuna.Study | None = None

    def create_study(self, *, seed: int, direction: str = "minimize") -> str:
        """Cria o estudo com amostrador semeado e devolve seu nome."""
        with _translating_backend_errors("create_study"):
            self._study = optuna.create_study(
                direction=direction,
                sampler=TPESampler(seed=seed),
            )
        return str(self._study.study_name)

    def ask(self, space: Sequence[SearchDimension]) -> SearchTrial:
        """Pede o próximo trial com as distribuições fixadas pelo espaço."""
        study = self._require_study()
        distributions = {dimension.name: _distribution(dimension) for dimension in space}
        with _translating_backend_errors("ask"):
            trial = study.ask(fixed_distributions=distributions)
        # A fronteira devolve sempre `float` (contrato do port); reconverter por
        # `kind` é do use case.
        return SearchTrial(
            number=int(trial.number),
            values={name: float(value) for name, value in trial.params.items()},
        )

    def tell(self, *, trial_number: int, objective_value: float) -> None:
        """Informa o objetivo observado, identificando o trial pelo NÚMERO."""
        study = self._require_study()
        with _translating_backend_errors("tell"):
            study.tell(trial_number, float(objective_value))

    def fail(self, *, trial_number: int) -> None:
        """Marca o trial como falho no estudo (sem objetivo)."""
        study = self._require_study()
        with _translating_backend_errors("fail"):
            study.tell(trial_number, state=TrialState.FAIL)

    def best_trial(self) -> SearchTrial:
        """Melhor trial informado; ergue se nenhum foi (C9).

        O Optuna ergue `ValueError` com mensagem própria quando não há trial
        completo; a re-erguida aqui é para a mensagem carregar o marcador do
        caso de erro, que é o que a suite de contrato compara entre as pernas.
        """
        study = self._require_study()
        try:
            with _translating_backend_errors("best_trial"):
                best = study.best_trial
        except ValueError as error:
            msg = "nenhum trial informado — não há melhor trial (C9)"
            raise ValueError(msg) from error
        return SearchTrial(
            number=int(best.number),
            values={name: float(value) for name, value in best.params.items()},
        )

    def _require_study(self) -> optuna.Study:
        """Erro de WIRING (não da lib): `RuntimeError`, fora do contrato de propósito.

        Não é traduzido (issue #84): quem chama `ask`/`tell` sem `create_study` tem um
        bug de programação, e o sweep deixa esse tipo propagar em vez de o mascarar
        como "trial inviável".
        """
        if self._study is None:
            msg = "create_study precisa ser chamado antes de ask/tell/best_trial"
            raise RuntimeError(msg)
        return self._study
