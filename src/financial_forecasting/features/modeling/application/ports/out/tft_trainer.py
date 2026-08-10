"""Port-out `TftTrainer` — treino do TFT quantílico + emissão da grade crua.

Protocol estrutural (concept 5.4 §4): dado `(params, painel completo, faixas de
índices por partição, grade de quantis)`, ajusta **um** modelo sequencial com
decodificador de `max_horizon` passos e devolve os **valores crus** da grade por
decisão de teste x horizonte. Os **dados** cruzam a fronteira como
primitivos/`collections.abc` — NUNCA DataFrame/tensor; `float('nan')` é o
marcador de valor ausente. A implementação real (`PfTftTrainer`,
adapters/out/pytorch_forecasting) e o fake in-memory são validados pela MESMA
suite de contrato
(`tests/contract/features/modeling/test_tft_trainer_contract.py`, parametrizada
sobre `[fake, real]` — skill `pytest-with-fakes`).

**Por que o painel INTEIRO atravessa a fronteira** (concept D5): o TFT é
sequencial, então a predição de uma decisão `t` consome uma janela de contexto
que alcança sessões anteriores à própria partição de `t` (ADR 5.4.0001). Recortar
o painel por partição tornaria o contrato impossível de cumprir. O que delimita
ajuste e monitor são as **faixas de índices de decisão**, não o recorte — e é
por isso que elas são o ponto auditável do anti-vazamento.

Contrato semântico (concept 5.4 §4/§5/§6; ADRs 5.4.0001-0006):

- **Janela (I3/I4a):** a janela de contexto da decisão `t` é o bloco de
  `max_encoder_length` sessões **terminando em `t` inclusive** (`[t - L + 1, t]`
  — a indexação `t-k:t` da Eq. (1) de Lim et al. 2021). Uma decisão tem janela
  completa sse `t >= max_encoder_length - 1`. Nada em `> t` entra no codificador.
- **Faixas contíguas (C4/D5):** cada conjunto de índices de decisão deve ser uma
  faixa **contígua e crescente** — é o que o `FoldSplit` produz. A biblioteca do
  adapter só expressa piso de decisão, e o teto vem de recortar o quadro; um
  conjunto não contíguo não é honrável pelo real, e um port que aceita o que o
  adapter não honra produz divergência fake<->real silenciosa **no monitor**,
  onde ela significaria `calib` entrando na perda de validação.
- **I8 — um modelo por fold:** um único ajuste, com decodificador de
  `max_horizon` passos (ADR 5.4.0002), do qual saem todos os horizontes pedidos.
  Nenhum ajuste por horizonte.
- **I17 — descarte declarado:** em `train`/`early_stop` só entram decisões com
  janela completa **e** decodificador completo; as demais são descartadas pela
  construção do conjunto de amostras, e as contagens efetivas voltam em
  `fitted_decision_count`/`monitored_decision_count`. Descarte silencioso é
  defeito, não detalhe.
- **I6 — melhor checkpoint restaurado:** a predição usa os pesos da época de
  MENOR perda de validação. `best_epoch` é o argmin de `val_loss_by_epoch`, e
  `artifact_path` aponta para o arquivo **daquela** época — o vínculo é
  contratual, não incidental: é o que torna a mutação "predizer com os pesos da
  última época" detectável por identidade contra um modelo recarregado.
- **I16 — regra de emissão na cauda:** o par (decisão `t`, horizonte `h`) é
  emitido **sse** `t + h <= len(target) - 1`. É exatamente a condição de pulo do
  persister 4.3, logo o conjunto de pontos alinhados coincide com o de 5.2/5.3
  por construção. Como a saída de predição da biblioteca é retangular e
  preenchida na cauda, a emissão é recortada pelo comprimento real do
  decodificador de cada amostra — sem isso o padding viraria predição fabricada.
- **Modo fit-only:** `test_decision_indices` vazio => `grids` vazio,
  `artifact_path` vazio, **nenhum checkpoint escrito**; só a perda de validação
  é reportada. É o modo da varredura exploratória (ADR 5.4.0005).
- **I5 — grade crua:** os valores emitidos podem cruzar entre níveis; o rearranjo
  monótono (guardrail ADR 4.3.0002) é responsabilidade do chamador.
- **I9 — determinismo:** mesma entrada (+ mesma seed) => mesma saída no MESMO
  processo. Reprodutibilidade entre processos/plataformas não é afirmada.
- **I4b — normalizador ajustado no quadro de treino:** `normalizer_center` e
  `normalizer_scale` são os parâmetros AJUSTADOS (não recalculados), expostos
  para que o invariante seja verificável por número em vez de por
  comportamento — mutar `calib` muda a predição pelo canal do contexto, então
  invariância de predição não provaria nada aqui.
- **C3 — histórico insuficiente ergue:** após a regra de janela/decodificador,
  nenhuma decisão de treino OU nenhuma decisão de monitor => `ValueError`.
- **C4 — estrutura inconsistente ergue:** largura de linha != `len(feature_names)`,
  `len(target) != len(rows)`, `known_feature_names` não contido em
  `feature_names`, índice fora do painel, faixa não contígua/não crescente,
  `horizons` não contido em `1..max_horizon`, monitor vazio => `ValueError`.
- **C5 — emissão não finita ergue** (adapter real): NaN/Inf em posição
  realmente prevista => `ValueError`, avaliado DEPOIS do recorte por
  comprimento de decodificador — senão a cauda legítima erguiria sempre.
- **C10 — treino sem checkpoint utilizável ergue** (adapter real): perda de
  validação nunca finita ou caminho do melhor checkpoint vazio => `ValueError`.
  Falhar em silêncio produziria um `artifact_path` inválido que só quebraria na
  Stage 7.1.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
    GridByHorizon,
)


@dataclass(frozen=True)
class TftTrainingParams:
    """Hiperparâmetros pré-registrados do TFT + semente.

    Os defaults são o ponto de partida pré-registrado do candidato; a varredura
    exploratória (ADR 5.4.0005) pode variá-los, mas o cohort confirmatório (5.5)
    os congela. `seed` não tem default: a identidade reprodutível do run é
    decisão explícita do chamador (I9/I10).

    `max_encoder_length` é a janela de contexto EM SESSÕES, contada terminando na
    própria decisão (`[t - L + 1, t]`).
    """

    seed: int
    max_encoder_length: int = 60
    hidden_size: int = 16
    attention_head_size: int = 4
    dropout: float = 0.1
    hidden_continuous_size: int = 8
    learning_rate: float = 0.03
    max_epochs: int = 50
    patience: int = 8
    batch_size: int = 64

    def __post_init__(self) -> None:
        if self.max_encoder_length < 1:
            msg = f"max_encoder_length deve ser >= 1, recebido {self.max_encoder_length}"
            raise ValueError(msg)
        if self.hidden_size < 1:
            msg = f"hidden_size deve ser >= 1, recebido {self.hidden_size}"
            raise ValueError(msg)
        if self.attention_head_size < 1:
            msg = f"attention_head_size deve ser >= 1, recebido {self.attention_head_size}"
            raise ValueError(msg)
        if self.hidden_continuous_size < 1:
            msg = (
                f"hidden_continuous_size deve ser >= 1, recebido {self.hidden_continuous_size}"
            )
            raise ValueError(msg)
        if not 0.0 <= self.dropout < 1.0:
            msg = f"dropout deve estar em [0, 1), recebido {self.dropout}"
            raise ValueError(msg)
        if self.learning_rate <= 0:
            msg = f"learning_rate deve ser > 0, recebido {self.learning_rate}"
            raise ValueError(msg)
        if self.max_epochs < 1:
            msg = f"max_epochs deve ser >= 1, recebido {self.max_epochs}"
            raise ValueError(msg)
        if self.patience < 1:
            msg = f"patience deve ser >= 1, recebido {self.patience}"
            raise ValueError(msg)
        if self.batch_size < 1:
            msg = f"batch_size deve ser >= 1, recebido {self.batch_size}"
            raise ValueError(msg)


@dataclass(frozen=True)
class TftTrainingResult:
    """Saída do treino: grades cruas + mecanismo de parada + contagens efetivas.

    `grids`: `decision_idx -> horizon -> tupla alinhada 1:1 a quantile_levels`
    (mesma forma do `QuantileModelTrainer` da 5.3), contendo APENAS os pares que
    a regra de emissão I16 autoriza — ausência de chave significa "não existe no
    painel", nunca "falhou".

    `val_loss_by_epoch` tem uma entrada por época EXECUTADA, sem a passagem de
    sanidade do treinador (concept D11): é sobre ele que `best_epoch` é o argmin,
    e essa identidade é a prova de mecanismo de I6.

    `fitted_decision_count`/`monitored_decision_count` são as decisões que de
    fato viraram amostra (I17) — o descarte por janela incompleta é declarado
    aqui, não silenciado.

    `normalizer_center`/`normalizer_scale` são os parâmetros ajustados do
    normalizador do alvo (ADR 5.4.0006), expostos para verificação numérica de
    I4b. No modo fit-only, `artifact_path` é `""`.
    """

    grids: Mapping[int, GridByHorizon]
    best_epoch: int
    best_val_loss: float
    val_loss_by_epoch: tuple[float, ...]
    fitted_decision_count: int
    monitored_decision_count: int
    normalizer_center: float
    normalizer_scale: float
    artifact_path: str


class TftTrainer(Protocol):
    """Contrato de treino e emissão da grade crua do TFT quantílico."""

    def train_and_predict(  # noqa: PLR0913 — parâmetros coesos do contrato de treino
        self,
        *,
        params: TftTrainingParams,
        feature_names: Sequence[str],
        known_feature_names: Sequence[str],
        rows: Sequence[Sequence[float]],
        target: Sequence[float],
        train_decision_indices: Sequence[int],
        early_stop_decision_indices: Sequence[int],
        test_decision_indices: Sequence[int],
        max_horizon: int,
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
        artifact_dir: str,
    ) -> TftTrainingResult:
        """Ajusta um TFT no fold e emite a grade crua das decisões de teste.

        Args:
            params: hiperparâmetros pré-registrados + seed (identidade do run).
            feature_names: ordem canônica das colunas do painel; largura de toda
                linha de `rows`.
            known_feature_names: subconjunto de `feature_names` que são
                covariáveis CONHECIDAS (calendário) — entram no decodificador
                até `t + max_horizon`. As demais são desconhecidas e entram no
                codificador só até `t` (I2/I3).
            rows: painel COMPLETO de features, uma linha por sessão, ordenado.
            target: painel COMPLETO do alvo, 1:1 com `rows`
                (`target_return[i]` — ADR 3.5.0001).
            train_decision_indices: faixa contígua e crescente das decisões que
                podem ajustar o modelo. NENHUMA decisão fora daqui entra no fit.
            early_stop_decision_indices: faixa contígua e crescente das decisões
                que monitoram a parada. `calib` NUNCA aparece aqui (I7).
            test_decision_indices: faixa contígua e crescente das decisões a
                predizer; vazia => modo fit-only.
            max_horizon: comprimento do decodificador (passos à frente).
            horizons: horizontes a emitir, contidos em `1..max_horizon`.
            quantile_levels: grade densa comum do cohort (crescente, em (0, 1)).
            artifact_dir: diretório onde o checkpoint da melhor época é gravado;
                composto pelo chamador a partir de `artifacts_root` (D9).

        Returns:
            `TftTrainingResult` com `grids` contendo exatamente os pares que I16
            autoriza, `best_epoch == argmin(val_loss_by_epoch)` e
            `artifact_path` apontando para o checkpoint dessa época (ou `""` no
            modo fit-only).

        Raises:
            ValueError: histórico insuficiente (C3), estrutura inconsistente
                (C4), emissão não finita (C5) ou treino sem checkpoint
                utilizável (C10).
        """
        ...
