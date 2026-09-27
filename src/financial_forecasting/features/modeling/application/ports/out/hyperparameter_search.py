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
from dataclasses import dataclass, fields, is_dataclass
from typing import Protocol

_INT_KIND = "int"
_FLOAT_KIND = "float"
_VALID_KINDS = (_INT_KIND, _FLOAT_KIND)
_SEED_FIELD = "seed"
_OBJECTIVE_SIGNIFICANT_DIGITS = 12


@dataclass(frozen=True)
class SearchDimension:
    """Uma dimensão do espaço de busca (forma validada na construção — C11).

    A dimensão valida só a FORMA (kind, faixa, escala log). O nome é validado
    contra o tipo de params de quem usa o espaço — `validate_dimension_names` —,
    porque o mesmo port serve ao sweep do TFT e ao do GBM (Stage 5.5, D13).
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


def validate_dimension_names(space: Sequence[SearchDimension], params_type: type) -> None:
    """C11 — todo nome do espaço tem de ser campo do dataclass de params do sweep.

    Sem essa checagem, um nome errado só apareceria como `TypeError` opaco na hora
    de montar os params do trial, longe da causa. Chamado pelo use case de cada
    sweep, antes de qualquer I/O, com o seu tipo (`TftTrainingParams`,
    `GbmTrainingParams`).
    """
    if not is_dataclass(params_type):
        raise TypeError(f"params_type must be a dataclass; got {params_type!r}")
    # `seed` nunca é hiperparâmetro de busca: no GBM não age (D4) e no TFT
    # buscar seed é escolher sorte — o cohort roda cada seed à parte.
    tunable = frozenset(field.name for field in fields(params_type)) - {_SEED_FIELD}
    names = [dimension.name for dimension in space]
    if len(set(names)) != len(names):
        raise ValueError(f"search space has repeated dimension names: {names} (C11)")
    for dimension in space:
        if dimension.name not in tunable:
            msg = (
                f"name {dimension.name!r} não é campo de {params_type.__name__}; "
                f"campos válidos: {sorted(tunable)} (C11)"
            )
            raise ValueError(msg)


def stable_objective(value: float) -> float:
    """Objetivo arredondado a 12 dígitos significativos antes do `tell`.

    A perda de early_stop do LightGBM varia no último ulp entre execuções (soma
    paralela da métrica), mesmo com a mesma seed; sem o arredondamento, um empate
    entre trials viraria sorteio e uma reexecução poderia congelar outro melhor
    trial. Com ele, empates são exatos e o estudo desempata pelo menor número de
    trial (Stage 5.5, Checkpoint C).
    """
    return float(f"{value:.{_OBJECTIVE_SIGNIFICANT_DIGITS}g}")


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

        Raises:
            HyperparameterSearchError: o backend de busca falhou (issue #84).
        """
        ...

    def ask(self, space: Sequence[SearchDimension]) -> SearchTrial:
        """Pede o próximo trial, com um valor por dimensão de `space`.

        Raises:
            HyperparameterSearchError: o backend de busca falhou (issue #84).
        """
        ...

    def tell(self, *, trial_number: int, objective_value: float) -> None:
        """Informa o objetivo observado para o trial de número `trial_number`.

        Raises:
            ValueError: `trial_number` não foi pedido a este estudo (bug do
                chamador).
            HyperparameterSearchError: o backend de busca falhou (issue #84).
        """
        ...

    def fail(self, *, trial_number: int) -> None:
        """Marca o trial como FALHO, sem informar objetivo.

        Um trial inviável não pode receber um objetivo inventado — isso
        contaminaria o amostrador. Mas deixá-lo pendente também não serve: o
        estudo ficaria com trials zumbis. Marcar como falho preserva a garantia
        (amostradores só consideram trials completos) sem o zumbi.

        Raises:
            ValueError: `trial_number` não foi pedido a este estudo (bug do
                chamador).
            HyperparameterSearchError: o backend de busca falhou (issue #84).
        """
        ...

    def best_trial(self) -> SearchTrial:
        """Devolve o trial de melhor objetivo informado.

        Raises:
            ValueError: nenhum trial foi informado ainda (C9).
            HyperparameterSearchError: o backend de busca falhou (issue #84).
        """
        ...
