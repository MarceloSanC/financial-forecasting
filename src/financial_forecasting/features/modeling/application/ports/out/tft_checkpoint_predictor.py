"""Port-out `TftCheckpointPredictor` — a grade crua a partir de um checkpoint (Stage 7.1).

A inferência prediz de novo com o modelo gravado pelo treino, pela MESMA receita
de dataset e pelo MESMO `_emit` do treinador (ADR 7.1.0001 item 3) — o teste
re-predito tem de reproduzir o silver, e a partição `calib` sai do mesmo caminho.
Os dados cruzam a fronteira como primitivos/`collections.abc`, como no
`TftTrainer`; o painel inteiro atravessa porque o contexto de uma decisão alcança
sessões anteriores à sua partição (ADR 5.4.0001).

Contrato (concept 7.1 §4; C4/C10; A2):

- **C10 — bytes lidos uma vez:** o sha256 dos bytes lidos é conferido contra
  `expected_sha256` e o modelo é carregado DESSES bytes; divergência ergue
  `ArtifactChangedError` antes de qualquer carga (não há janela entre o hash e o
  unpickle).
- **C4 — entradas declaradas:** reais conhecidas/desconhecidas, comprimento do
  decodificador (`max_horizon`) e níveis da `QuantileLoss` do checkpoint têm de
  ser os passados; senão `CheckpointMismatchError`.
- **Faixa de decisões** contígua e crescente (senão `ValueError`), como no
  `TftTrainer`; a emissão segue a regra I16 da cauda, só nos pares pedidos.
- **Execução:** modo eval, `num_threads` pedido e algoritmos determinísticos
  desligados (o estado em que o treinador emitiu o teste), restaurados depois;
  mesma entrada ⇒ mesma saída, independente do RNG global e do processo.
- **Saída:** `grids` (decisão → horizonte → tupla crua alinhada a
  `quantile_levels`), centro/escala do normalizador lidos do checkpoint (nunca
  reajustados) e `settings` — os parâmetros da inferência, em texto, com
  exatamente as chaves de `SETTINGS_KEYS` (concept 7.1 §4; ADR 7.1.0004 item 4,
  campos de settings do manifesto): `batch_size`, `num_workers` (`"0"`),
  `accelerator` (`"cpu"`), `num_threads`, `deterministic_algorithms`
  (`"false"`), `cpu_capability` (`torch.backends.cpu.get_cpu_capability()`),
  `platform` (`platform.platform()`) e `scikit-learn` (versão instalada).

**Predição de atribuição (Stage 7.3; ADR 7.3.0002 item 1; concept 7.3 I6-I8):**
`predict_attribution_from_checkpoint` faz, sobre o MESMO dataset de predição, a
passagem de identidade (pelo mesmo `_emit`: é igual a `predict_from_checkpoint` valor a
valor), uma passagem por (família, k) com a janela inteira do encoder das colunas da
família trocada no tensor pelo bloco da decisão doadora `donors[k][i]` (posições em
`decision_indices` ordenado; o doador pode estar em outro lote) e os pesos da VSN do
encoder por decisão (média nos passos do encoder, como a lib reduz). Erros a mais:

- `FamilyFeatureKnownError` (C5): alguma coluna de `permuted_columns` não é real
  `unknown` do encoder no checkpoint (é `known`, ou não está declarada) — nada emitido;
- `ValueError`: `donors` com permutação que não é de `range(len(decision_indices))`,
  decisão sem amostra de predição, ou comprimentos de encoder diferentes entre as
  decisões (o adapter nunca trunca nem completa).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
    GridByHorizon,
)
from financial_forecasting.shared.application.exceptions import ApplicationError

SETTINGS_KEYS = (
    "batch_size",
    "num_workers",
    "accelerator",
    "num_threads",
    "deterministic_algorithms",
    "cpu_capability",
    "platform",
    "scikit-learn",
)
"""Chaves de `TftCheckpointPrediction.settings` — o que o manifesto da inferência grava."""


class CheckpointMismatchError(ApplicationError):
    """O checkpoint declara entradas diferentes das passadas (C4): reais, decodificador, níveis."""


class ArtifactChangedError(ApplicationError):
    """O sha256 dos bytes do checkpoint difere do esperado (C10) — nada foi carregado."""


class FamilyFeatureKnownError(ApplicationError):
    """Coluna de família que não é real `unknown` do encoder no checkpoint (C5, I8)."""


@dataclass(frozen=True)
class TftCheckpointPrediction:
    """Grade crua por decisão pedida, normalizador do checkpoint e parâmetros da inferência."""

    grids: Mapping[int, GridByHorizon]
    normalizer_center: float
    normalizer_scale: float
    settings: Mapping[str, str]


@dataclass(frozen=True)
class TftAttributionPrediction:
    """Identidade, predições permutadas por (família, k) e pesos da VSN por decisão.

    `permuted` é indexado por `(família, k)` com k = 1..K_p (a identidade é a passagem
    `k = 0`, em `identity`); `encoder_weights` mapeia decisão → variável do encoder →
    peso (soma 1 por decisão).
    """

    identity: Mapping[int, GridByHorizon]
    permuted: Mapping[tuple[str, int], Mapping[int, GridByHorizon]]
    encoder_weights: Mapping[int, Mapping[str, float]]
    normalizer_center: float
    normalizer_scale: float
    settings: Mapping[str, str]


def check_donors(donors: Sequence[Sequence[int]], *, n_decisions: int) -> None:
    """Cada permutação de `donors` é de `range(n_decisions)` (senão `ValueError`).

    Regra única do contrato, usada pelo adapter real e pelo fake.
    """
    if not donors:
        raise ValueError("donors must hold at least one permutation")
    expected = list(range(n_decisions))
    for k, permutation in enumerate(donors, start=1):
        if sorted(permutation) != expected:
            raise ValueError(
                f"donors[{k - 1}] is not a permutation of range({n_decisions}): "
                f"{list(permutation)!r}"
            )


class TftCheckpointPredictor(Protocol):
    """Prediz a grade crua das decisões pedidas a partir de um checkpoint do TFT."""

    def predict_from_checkpoint(  # noqa: PLR0913 — espelha a assinatura do concept §4
        self,
        *,
        checkpoint_path: str,
        expected_sha256: str,
        feature_names: Sequence[str],
        known_feature_names: Sequence[str],
        rows: Sequence[Sequence[float]],
        target: Sequence[float],
        decision_indices: Sequence[int],
        max_horizon: int,
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
        batch_size: int,
        num_threads: int,
    ) -> TftCheckpointPrediction:
        """Grade das `decision_indices` x `horizons` (regra I16), sem reajustar nada.

        Raises:
            ArtifactChangedError: sha256 dos bytes != `expected_sha256` (antes da carga).
            CheckpointMismatchError: entradas declaradas pelo checkpoint != as passadas.
            ValueError: faixa de decisões não contígua ou não crescente.
        """
        ...

    def predict_attribution_from_checkpoint(  # noqa: PLR0913 — espelha a assinatura do concept 7.3 §4
        self,
        *,
        checkpoint_path: str,
        expected_sha256: str,
        feature_names: Sequence[str],
        known_feature_names: Sequence[str],
        rows: Sequence[Sequence[float]],
        target: Sequence[float],
        decision_indices: Sequence[int],
        max_horizon: int,
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
        batch_size: int,
        num_threads: int,
        permuted_columns: Mapping[str, Sequence[str]],
        donors: Sequence[Sequence[int]],
    ) -> TftAttributionPrediction:
        """Identidade, permutadas e VSN das `decision_indices` (ver docstring do módulo).

        Raises:
            ArtifactChangedError: sha256 dos bytes != `expected_sha256` (antes da carga).
            CheckpointMismatchError: entradas declaradas pelo checkpoint != as passadas.
            FamilyFeatureKnownError: coluna de família que não é real `unknown` (C5).
            ValueError: faixa de decisões, doadores ou comprimentos de encoder inválidos.
        """
        ...
