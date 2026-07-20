"""Port-out `QuantileModelTrainer` — treino supervisionado + emissão da grade crua.

Protocol estrutural (concept 5.3 §4): dado `(params, matrizes de features,
labels por horizonte, grade de quantis)`, treina um modelo quantílico por
(nível x horizonte) e devolve os **valores crus** da grade por decisão de teste
x horizonte. Os **dados** cruzam a fronteira como primitivos/`collections.abc`
— NUNCA DataFrame/ndarray; `float('nan')` é o marcador de valor ausente. A
implementação real (`LightgbmQuantileTrainer`, adapters/out/lightgbm) e o fake
in-memory são validados pela MESMA suite de contrato
(`tests/contract/features/modeling/test_quantile_model_trainer_contract.py`,
parametrizada sobre `[fake, real]` — skill `pytest-with-fakes`).

Contrato semântico (concept 5.3 §4/§5/§6; ADRs 5.3.0001-0002):

- **I5 — um modelo por (nível x horizonte):** nenhum acoplamento entre níveis
  nem entre horizontes; as chaves dos mapas de labels definem os horizontes.
- **Seleção de `m*` (ADR 5.3.0002):** por horizonte, monitorar a pinball por
  iteração na partição `early_stop` e selecionar
  `m*_h = 1 + argmin_m média_níveis(história[m])` — contagem **1-based** de
  árvores (índice do argmin + 1; `m*_h >= 1` SEMPRE — `num_iteration=0`
  significaria "todas as árvores" e silenciaria o truncamento), empate
  resolvido pela menor iteração. Predições de teste usam `num_iteration=m*_h`.
- **I11 — labels não finitos excluem o par** tanto do fit quanto do monitor
  daquele horizonte (o eval nativo do LightGBM converteria NaN em 0 —
  observação-fantasma); features NaN atravessam e são tratadas nativamente.
- **I12 — labels vêm do grid completo de sessões:** o chamador constrói
  `labels[j] = target_return[idx_j + h]` do array completo; o port nunca
  recebe label NaN-padded na fronteira da partição.
- **I3 — grade crua:** os valores emitidos podem cruzar entre níveis; o
  rearranjo monótono (guardrail ADR 4.3.0002) é responsabilidade do chamador.
- **I4 — determinismo:** mesma entrada (+ mesma seed em `params`) => mesma
  saída, bit a bit, inclusive `best_iteration_by_horizon`.
- **C3 — treino insuficiente ergue:** pares de label finito de algum
  (nível x horizonte) abaixo de `min_data_in_leaf` => `ValueError`.
- **C4 — estrutura inconsistente ergue:** largura de linha diferente de
  `len(feature_names)`, comprimento de labels diferente do nº de linhas,
  `test_decision_indices` de comprimento diferente do teste, `early_stop`
  vazio (sem monitor não há seleção de `m*`) => `ValueError`.
- **C5 — emissão não finita ergue:** NaN/Inf em qualquer valor cru produzido
  => `ValueError`; nunca emitido silenciosamente.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
    GridByHorizon,
)

_MIN_NUM_LEAVES = 2


@dataclass(frozen=True)
class GbmTrainingParams:
    """Hiperparâmetros pré-registrados do GBM (concept D6 — zero tuning).

    `num_leaves`/`learning_rate`/`min_data_in_leaf` são os defaults da lib;
    `num_boost_round_max` é o teto generoso do mecanismo de parada (ADR
    5.3.0002 — `m*` trunca), não um default. `seed` não tem default: a
    identidade reprodutível do run é decisão explícita do chamador (I4/I7).
    """

    seed: int
    num_boost_round_max: int = 500
    num_leaves: int = 31
    learning_rate: float = 0.1
    min_data_in_leaf: int = 20

    def __post_init__(self) -> None:
        if self.num_boost_round_max < 1:
            msg = f"num_boost_round_max deve ser >= 1, recebido {self.num_boost_round_max}"
            raise ValueError(msg)
        if self.learning_rate <= 0:
            msg = f"learning_rate deve ser > 0, recebido {self.learning_rate}"
            raise ValueError(msg)
        if self.num_leaves < _MIN_NUM_LEAVES:
            msg = f"num_leaves deve ser >= {_MIN_NUM_LEAVES}, recebido {self.num_leaves}"
            raise ValueError(msg)
        if self.min_data_in_leaf < 1:
            msg = f"min_data_in_leaf deve ser >= 1, recebido {self.min_data_in_leaf}"
            raise ValueError(msg)


@dataclass(frozen=True)
class QuantileTrainingResult:
    """Saída do treino: grades cruas por decisão + iteração selecionada.

    `grids`: `decision_idx -> horizon -> tupla alinhada 1:1 a quantile_levels`
    (mesma forma do `BaselineForecaster` da 5.2). `best_iteration_by_horizon`:
    contagem 1-based de árvores selecionada pela regra do ADR 5.3.0002.
    """

    grids: Mapping[int, GridByHorizon]
    best_iteration_by_horizon: Mapping[int, int]


class QuantileModelTrainer(Protocol):
    """Contrato de treino e emissão da grade crua de um modelo quantílico."""

    def train_and_predict(  # noqa: PLR0913 — parâmetros coesos do contrato de treino
        self,
        *,
        params: GbmTrainingParams,
        feature_names: Sequence[str],
        train_rows: Sequence[Sequence[float]],
        train_labels_by_horizon: Mapping[int, Sequence[float]],
        early_stop_rows: Sequence[Sequence[float]],
        early_stop_labels_by_horizon: Mapping[int, Sequence[float]],
        test_rows: Sequence[Sequence[float]],
        test_decision_indices: Sequence[int],
        quantile_levels: Sequence[float],
    ) -> QuantileTrainingResult:
        """Treina por (nível x horizonte) e emite a grade crua das decisões de teste.

        Args:
            params: hiperparâmetros pré-registrados + seed (identidade do run).
            feature_names: ordem canônica das colunas (registry + calendário —
                ADR 5.3.0003); largura de toda linha.
            train_rows: matriz de treino (linhas alinhadas às sessões do train).
            train_labels_by_horizon: `h -> labels` 1:1 com `train_rows`
                (`target_return[idx + h]` — I1/I12); não finito exclui o par.
            early_stop_rows: matriz da partição dedicada de monitor (5.1).
            early_stop_labels_by_horizon: `h -> labels` 1:1 com
                `early_stop_rows`; não finito exclui o par do monitor.
            test_rows: matriz das decisões de teste (sempre preditas — janela
                incompleta é tratada na persistência, 4.3).
            test_decision_indices: índice de sessão de cada linha de teste
                (chaves do retorno), crescentes.
            quantile_levels: grade densa comum do cohort (crescente, em (0, 1)).

        Returns:
            `QuantileTrainingResult` com toda decisão pedida presente e
            `best_iteration_by_horizon[h] >= 1` para todo horizonte.

        Raises:
            ValueError: treino insuficiente (C3), estrutura inconsistente (C4)
                ou emissão não finita (C5).
        """
        ...
