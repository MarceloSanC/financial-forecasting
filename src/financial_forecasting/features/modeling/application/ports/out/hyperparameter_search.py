"""Port-out `HyperparameterSearch` — busca de hiperparâmetros *ask-and-tell*.

Protocol estrutural (concept 5.4 §4 / ADR 5.4.0005): o chamador PEDE um trial
(`ask`), avalia por conta própria e INFORMA o resultado (`tell`). O laço de
trials vive no use case `RunTftSweep`, não no adapter.

**Por que ask-and-tell e não a API de alto nível.** A alternativa natural seria
passar a função-objetivo para o adapter (`study.optimize(objective, n_trials)`).
Isso faria uma *callable* atravessar a fronteira e moveria a orquestração — qual
fold, qual modo do trainer, o que é logado — para dentro do adapter, onde ela
deixa de ser testável com fake e deixa de ser auditável pelo gate de camadas. O
Optuna suporta *ask-and-tell* nativamente, então a escolha não cria mecanismo:
usa um que a biblioteca já oferece.

Contrato semântico:

- **`create_study`** devolve o identificador do estudo. A **semente é do port**;
  o adapter a traduz para o amostrador da biblioteca (no Optuna a semente vive
  no sampler, não no estudo).
- **`ask`** devolve um trial com um valor por dimensão declarada.
- **`tell`** recebe o **número** do trial, não o objeto — a fronteira troca só
  primitivos.
- **`fail`** marca um trial inviável sem lhe atribuir objetivo.
- **`best_trial`** devolve o de melhor objetivo informado; sobre estudo sem
  nenhum `tell` **ergue** (C9).
- **Fronteira sempre em `float`**: `SearchTrial.values` não carrega o tipo da
  dimensão. Reconverter por `SearchDimension.kind` é responsabilidade do use
  case — declarado aqui para os dois lados não suporem o contrário.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from typing import Protocol

from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)

_INT_KIND = "int"
_FLOAT_KIND = "float"
_VALID_KINDS = (_INT_KIND, _FLOAT_KIND)
_TUNABLE_FIELDS = frozenset(field.name for field in fields(TftTrainingParams))


@dataclass(frozen=True)
class SearchDimension:
    """Uma dimensão do espaço de busca (C11 validado na construção).

    `name` tem de ser um campo de `TftTrainingParams`: sem essa checagem, um
    nome errado só apareceria como `TypeError` opaco na hora de montar os params
    do trial, longe da causa.
    """

    name: str
    low: float
    high: float
    kind: str
    log: bool = False

    def __post_init__(self) -> None:
        if self.kind not in _VALID_KINDS:
            msg = f"kind deve ser um de {_VALID_KINDS}, recebido {self.kind!r} (C11)"
            raise ValueError(msg)
        if self.low >= self.high:
            msg = f"low deve ser < high; recebido low={self.low}, high={self.high} (C11)"
            raise ValueError(msg)
        if self.kind == _INT_KIND and self.log and self.low < 1:
            # Distribuição inteira em escala logarítmica exige piso >= 1 na
            # biblioteca; barrar aqui dá erro no lugar certo.
            msg = f"low deve ser >= 1 para kind='int' com log=True; recebido {self.low} (C11)"
            raise ValueError(msg)
        if self.name not in _TUNABLE_FIELDS:
            msg = (
                f"name {self.name!r} não é campo de TftTrainingParams; "
                f"campos válidos: {sorted(_TUNABLE_FIELDS)} (C11)"
            )
            raise ValueError(msg)


@dataclass(frozen=True)
class SearchTrial:
    """Um trial: número no estudo + valores amostrados (sempre `float`)."""

    number: int
    values: Mapping[str, float]


class HyperparameterSearch(Protocol):
    """Contrato de busca de hiperparâmetros no estilo *ask-and-tell*."""

    def create_study(self, *, seed: int, direction: str = "minimize") -> str:
        """Cria o estudo e devolve seu identificador.

        Args:
            seed: semente do amostrador (identidade reprodutível da busca).
            direction: `"minimize"` (default) ou `"maximize"`.

        Returns:
            Identificador do estudo criado.
        """
        ...

    def ask(self, space: Sequence[SearchDimension]) -> SearchTrial:
        """Pede o próximo trial, com um valor por dimensão de `space`."""
        ...

    def tell(self, *, trial_number: int, objective_value: float) -> None:
        """Informa o objetivo observado para o trial de número `trial_number`."""
        ...

    def fail(self, *, trial_number: int) -> None:
        """Marca o trial como FALHO, sem informar objetivo.

        Um trial inviável não pode receber um objetivo inventado — isso
        contaminaria o amostrador. Mas deixá-lo pendente também não serve: o
        estudo ficaria com trials zumbis. Marcar como falho preserva a garantia
        (amostradores só consideram trials completos) sem o zumbi.
        """
        ...

    def best_trial(self) -> SearchTrial:
        """Devolve o trial de melhor objetivo informado.

        Raises:
            ValueError: nenhum trial foi informado ainda (C9).
        """
        ...
