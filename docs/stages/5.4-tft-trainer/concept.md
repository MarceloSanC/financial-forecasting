---
title: Concept — Trainer do TFT quantílico
description: Treino do candidato TFT sob o harness walk-forward — decodificador multi-horizonte único, tipagem known/unknown, normalizador ajustado só no treino, parada antecipada com restauração de checkpoint, artefato + MLflow, e varredura Optuna exploratória isolada do confirmatório
when-use: Consultar ao iniciar Fase 3B (technical) desta Stage; revisar antes de executar
keywords: [concept, tft-trainer, pytorch-forecasting, quantile-loss, known-unknown, early-stopping, checkpoint, target-normalizer, optuna, exploratorio, artefato, mlflow]
status: done
created_at: 2026-08-09
updated_at: 2026-08-09
stage_id: 5.4-tft-trainer
stage_title: Trainer do TFT quantílico
step_id: 5
step_title: Modelagem e harness de walk-forward
depends_on: [5.1-walk-forward-harness]
---

# Concept — Stage 5.4 — Trainer do TFT quantílico

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes. O plano executável fica no
> [`technical.md`](./technical.md). Teoria pré-registrada do treino do TFT:
> [`quantile-model-training.md`](../../domain/modeling/quantile-model-training.md)
> §5 (+ §2 e §7).

## 1. Escopo

### Dentro do escopo

- Port-out **`TftTrainer`** — contrato de treino + emissão da grade crua de
  quantis por um modelo **sequencial** multi-horizonte, com fronteira só de
  primitivos (`Sequence`/`Mapping`/`float`/`str`), incluindo a **tipagem
  known/unknown** das colunas e as fronteiras de índice das partições.
- Use case **`TrainTft`** — orquestra: leitura do dataset (3.5), splits
  walk-forward (5.1), montagem do painel completo + índices por partição,
  chamada do port, guardrail de monotonicidade (ADR 4.3.0002), dedup
  operationally-latest, `dim_run`, persistência em `fact_oos_predictions` via
  `PersistPredictions` (4.3) com `model_version='tft_quantile'`, e registro do
  run no `ExperimentTracker` (1.5) incluindo o **artefato do modelo**.
- Adapter **`PfTftTrainer`** — única fronteira do BC `modeling` com
  `torch`/`lightning`/`pytorch_forecasting` (e a única do projeto inteiro com
  as duas últimas; `torch` já é importado pelo adapter FinBERT em
  `feature_engineering`, ADR 3.2.0002): `TimeSeriesDataSet` com tipagem
  known/unknown e **normalizador do alvo explícito ajustado no treino** (D10),
  `TemporalFusionTransformer` com `QuantileLoss` na grade densa, parada
  antecipada por época com **restauração explícita do melhor checkpoint**,
  **callback de histórico de perda por época** (D11), artefato salvo em disco,
  predição em modo quantílico com recorte por comprimento de decodificador.
- Port-out **`HyperparameterSearch`** (interface *ask-and-tell*) + adapter
  **`OptunaSearch`** + use case **`RunTftSweep`** — varredura **exploratória**
  cujo objetivo é medido exclusivamente na partição de parada antecipada,
  jamais em `calib` ou `test`, e que **não recebe** porta de persistência de
  resultados (isolamento estrutural, I14).
- Fakes in-memory dos dois ports + suites de contrato (fake ↔ real), testes
  unit, integração e e2e via `wire_dependencies`.
- `torch` (CPU), `lightning`, `pytorch-forecasting` e `optuna` em
  `dependencies` + gates import-linter `modeling-no-torch-leak` (torch,
  lightning, pytorch_forecasting) e `modeling-no-optuna-leak` (optuna), cada um
  com prova de quebra intencional **e** caso em `_REAL_VIOLATION_CASES`
  (guarda anti-contrato-míope já existente na suite de arquitetura).
- **Caminho de instalação alinhado ao índice CPU.** `Makefile` e `Dockerfile`
  instalam hoje com a interface `uv pip`, que **ignora** `[tool.uv.sources]`, e
  o `Dockerfile` sequer copia o `uv.lock`. Sem corrigir isso, a declaração do
  índice CPU não alcançaria o ambiente em que o projeto de fato roda (Docker) e
  a imagem instalaria a variante CUDA — a decisão D3 valeria só no papel.
- Correção dos comentários que a mudança de dependência torna falsos:
  `pyproject.toml` e `.importlinter` (ambos afirmam hoje que o CI roda sem
  `torch`), mais a nota retroativa nos ADRs estreitados (3.2.0002 e 5.1.0002).

### Fora do escopo (explicitamente)

- **Re-treino confirmatório com seeds × folds e congelamento/hash do cohort** —
  Stage 5.5. Esta Stage treina o candidato; a composição confirmatória é lá.
- **Métricas de avaliação** (pinball reportada, DM/MCS/Holm, calibração,
  conformal) — Steps 6/7. A pinball aparece aqui **só** como perda de treino e
  critério interno de parada, computada pela própria biblioteca; nenhuma
  fórmula de avaliação é implementada.
- **Motor de inferência / superfície de runtime (API/CLI)** — Stage 7.1, que
  consome o artefato produzido aqui.
- **Treino em GPU (ROCm)** — o desenho resolve `torch` do índice CPU por
  padrão (D3); habilitar ROCm no ambiente de treino real é operação da 5.5,
  registrada como fronteira, não implementada aqui.
- **Ablação por família de features (H3)** e qualquer seleção de candidato
  olhando o out-of-sample — o desenho confirmatório tem candidato único
  pré-declarado (overview §3/§4).

### Vínculo com o roadmap

Stage `5.4-tft-trainer` do Step 5 (BC `modeling`, camada multi
`application + adapters/out`, `depends_on: [5.1]` — `done`). É o **objeto de
estudo** do projeto: o modelo cuja calibração probabilística é a pergunta do
overview §1. Fecha o Step 5 no eixo do candidato, deixando para a 5.5 apenas a
composição do cohort. Consome os contratos declarados no roadmap:
`WalkForwardSplitter` (5.1), `FeatureRegistry` (3.4),
`MultiHorizonPredictionPersister` (4.3) e `ExperimentTracker` (1.5).

**Divergência declarada em relação ao bloco YAML do roadmap.** O bloco lista
`contratos_introduzidos: [TftTrainer, TrainTft]` e quatro arquivos de origem.
Esta Stage introduz **quatro** contratos — os dois do roadmap mais
`HyperparameterSearch` (port-out) e `RunTftSweep` (use case) — e toca também
fakes, suites de contrato, `composition_root`, `Settings`, `pyproject.toml` e
`.importlinter`. Não é escopo novo: a varredura Optuna está no
`definition_of_done` do próprio roadmap, e o bloco YAML apenas não a
desdobrou em contratos e arquivos. O bloco é atualizado dentro desta Stage
(precedente: a 5.2 ajustou o texto do roadmap na própria Stage).

## 2. Objetivo da Stage

Ao fechar esta Stage, o cohort AAPL terá predições quantílicas out-of-sample do
TFT persistidas em `fact_oos_predictions` com `model_version='tft_quantile'`, na
**mesma grade densa de níveis**, no **mesmo grão** (`target_timestamp` por
indexação de sessões), no **mesmo conjunto de pontos alinhados** e no **mesmo
cohort** dos comparadores das Stages 5.2/5.3 — treinadas sob o harness da 5.1
com tipagem known/unknown, parada antecipada na partição dedicada, artefato do
modelo persistido e run registrado no MLflow, reprodutível por semente.

## 3. Contexto e premissas

### Contexto

O doc de domínio §5 fixa a teoria: o TFT (Lim et al. 2021) treina minimizando a
**soma da pinball sobre a grade de quantis e todos os horizontes** (Eq. 24), com
saídas quantílicas que **não** têm restrição de não-cruzamento — o guardrail do
§2.4 (rearranjo, ADR 4.3.0002) vale igual ao GBM. A Seção 3 do paper separa as
entradas em **estáticas**, **observadas** (medidas a cada passo, desconhecidas de
antemão) e **conhecidas** (predetermináveis); a assimetria de indexação
(observadas e alvo em `t−k:t`, isto é até `t` **inclusive**; conhecidas até
`t+τ`) é a base formal do anti-vazamento, e casa com o campo `tft_typing`
validado na `FeatureSpec` (ADR 3.4.0002). O §5.3 fixa que a parada antecipada é
**seleção de hiperparâmetro** (Goodfellow et al. §7.8) e por isso o sub-split
monitorado nunca pode virar calibração conformal (ADR 5.1.0002); registra também
que, no PyTorch Lightning, restaurar o melhor checkpoint **não** é automático. O
§5.4 fixa a disciplina de Raschka (2018): varredura é exploratória,
hiperparâmetros congelados antes do confirmatório.

O que o doc de domínio **não** fixa — e esta Stage decide, com o humano na
sessão de alinhamento de 2026-08-09 (issue #57) e com os achados do Checkpoint A
— é a postura de dependência do `torch` (§7-D3), o recorte multi-horizonte
(§7-D2), o estatuto da janela de contexto que cruza fronteiras de partição
(§7-D1), a forma dos dois ports (§7-D5/§7-D7), o isolamento da varredura
(§7-D8), o normalizador do alvo (§7-D10) e a origem do histórico de perda por
época (§7-D11).

### Premissas

- O dataset `processed/dataset_tft` do ativo do escopo está materializado
  (Stage 3.5) com `target_return` (retorno log backward de 1 dia,
  ADR 3.5.0001), as **55** features da registry, `day_of_week`/`month`,
  `time_idx` e `timestamp` tz-aware, **uma linha por sessão de pregão** e sem
  buracos.
- `torch` resolvido do índice CPU baixa ~200 MB comprimidos (mais de 1 GB
  instalado); `pytorch-forecasting` 1.8 traz `lightning`, `scipy`,
  `scikit-learn` e `scikit-base` junto, somando ~250–300 MB de download —
  risco R1, mitigado por cache do `uv` no workflow.
- Cada treino de fumaça (painel sintético curto, modelo mínimo, 2 épocas) custa
  ~10–20 s de CPU, dominado pelo custo fixo de importar `torch`/`lightning` e
  instanciar o `Trainer`. A suite real do adapter, que faz da ordem de vinte
  treinos, fica **na casa dos minutos** — o orçamento e o gatilho de marcador
  `slow` são do agregado, não de um teste isolado (R2).
- `pytorch-forecasting` 1.8 mantém a API `TimeSeriesDataSet` /
  `TemporalFusionTransformer.from_dataset` / `QuantileLoss` da linha 1.x, com o
  comportamento verificado em 2026-08 contra a documentação e o código:
  decodificador encurta de fato na cauda; a saída de predição é retangular e
  **precisa** de `return_decoder_lengths` para separar passo real de padding;
  `target_normalizer="auto"` escolhe `EncoderNormalizer` quando
  `max_encoder_length > 20`.

### Dependências

- `5.1-walk-forward-harness`: `WalkForwardSplitter` + `FoldSplit` (partição
  quádrupla `train < early_stop < calib < test`, com `gap = max_horizon +
  embargo` em cada fronteira; blocos **contíguos** no índice de sessões),
  `ScopeSpec`, `SplitFingerprint`, dedup `deduplicate_operationally_latest`.
- `5.3-gbm-quantile-baseline` (mesmo BC, não é dependência formal): precedente
  direto de forma do port, de payloads de identidade, de invariantes de dedup e
  de gate de vazamento de biblioteca. As entradas `[deviation]`/`[finding]` da
  §7 da 5.3 foram lidas; nenhuma traz Stage candidata apontando para a 5.4, mas
  o `[finding]` sobre o caso C5 ser inatingível na perna fake é **herdado como
  restrição de redação** dos critérios de aceite (A11/A4c).
- `4.3-prediction-persister`: `PersistPredictions`, `QuantileForecast.from_raw`
  (guardrail), `MultiHorizonPredictionPersister` (dono do `target_timestamp`;
  condição de pulo `decision_idx + horizon >= len(dataset_timestamps)`).
- `3.4-feature-registry-and-derived`: `list_feature_specs` como fonte canônica
  do conjunto, da ordem **e da tipagem** (`spec.tft_typing`) das features.
- `3.5-dataset-builder-and-contracts`: layout físico do dataset lido via
  `MedallionStore.read` (par read-only `processed/dataset_tft`).
- `1.5-config-and-tracking`: `ExperimentTracker` (ADR 1.5.0002) — primeiro
  consumidor real do port, exatamente o consumidor que o ADR antecipava.
- `1.4-identity-and-fingerprints`: `Hasher` para `run_id`/`config_signature`.

## 4. Contratos

### Introduzidos

- **`TftTrainer`** (`port-out`) — treino de um fold e emissão da grade crua por
  decisão de teste. Fronteira só de primitivos/`collections.abc`; NaN
  (`float('nan')`) é o marcador de valor ausente nas matrizes.

  ```python
  GridByHorizon = Mapping[int, tuple[float, ...]]  # reuso do alias da 5.2/5.3

  @dataclass(frozen=True)
  class TftTrainingParams:
      seed: int
      max_encoder_length: int = 60       # janela de contexto, em sessões, terminando em t
      hidden_size: int = 16
      attention_head_size: int = 4
      dropout: float = 0.1
      hidden_continuous_size: int = 8
      learning_rate: float = 0.03
      max_epochs: int = 50
      patience: int = 8                  # paciência da parada antecipada
      batch_size: int = 64

  @dataclass(frozen=True)
  class TftTrainingResult:
      grids: Mapping[int, GridByHorizon]   # decision_idx -> horizon -> grade crua
      best_epoch: int                      # argmin de val_loss_by_epoch (0-based)
      best_val_loss: float
      val_loss_by_epoch: tuple[float, ...] # uma entrada por época EXECUTADA (D11)
      fitted_decision_count: int           # decisões de treino EFETIVAMENTE ajustadas
      monitored_decision_count: int        # decisões de early_stop EFETIVAMENTE monitoradas
      normalizer_center: float             # parâmetros ajustados do normalizador (D10/I4b)
      normalizer_scale: float
      artifact_path: str                   # checkpoint da época `best_epoch` ('' se fit-only)

  class TftTrainer(Protocol):
      def train_and_predict(
          self,
          *,
          params: TftTrainingParams,
          feature_names: Sequence[str],
          known_feature_names: Sequence[str],   # subconjunto de feature_names
          rows: Sequence[Sequence[float]],      # painel COMPLETO, ordenado por sessão
          target: Sequence[float],              # painel COMPLETO
          train_decision_indices: Sequence[int],
          early_stop_decision_indices: Sequence[int],
          test_decision_indices: Sequence[int],
          max_horizon: int,
          horizons: Sequence[int],
          quantile_levels: Sequence[float],
          artifact_dir: str,
      ) -> TftTrainingResult: ...
  ```

  Semântica:

  - **Janela.** A janela de contexto da decisão `t` é o bloco de
    `max_encoder_length` sessões **terminando em `t` inclusive**
    (`[t − L + 1, t]`, a indexação `t−k:t` da Eq. (1)). Uma decisão tem janela
    completa sse `t >= max_encoder_length - 1`.
  - **Índices contíguos.** Cada conjunto de índices de decisão deve ser uma
    faixa **contígua e crescente** (é o que o `FoldSplit` produz). A biblioteca
    só expressa piso de decisão (`min_prediction_idx`), então o teto é obtido
    recortando o quadro; conjunto não contíguo não é honrável e ergue (C4).
  - **Ajuste e monitor.** Ajustar **um** modelo com decodificador de
    `max_horizon` passos (D2), usando como decisões de treino apenas
    `train_decision_indices` e como monitor apenas
    `early_stop_decision_indices`. Nas duas partições só entram decisões com
    janela completa **e** decodificador completo; as demais são descartadas pela
    própria construção do conjunto de amostras, e as contagens efetivas voltam
    em `fitted_decision_count`/`monitored_decision_count` (I17 — o descarte é
    declarado, nunca silencioso).
  - **Parada e restauração.** Parar pela paciência sobre a perda de validação e
    **restaurar o melhor checkpoint** antes de predizer. `artifact_path` é o
    caminho do checkpoint da época `best_epoch` — definido pelo arquivo salvo,
    não pelos pesos que por acaso estavam em memória —, e `val_loss_by_epoch`
    traz uma entrada por época executada (sem a passagem de sanidade, D11).
  - **Emissão.** Para cada decisão de teste `t` e cada `h` em `horizons`, emitir
    a grade crua **se e somente se** `t + h <= len(target) - 1`. Como a saída de
    predição da biblioteca é retangular e preenchida na cauda, a emissão é
    **recortada pelo comprimento real do decodificador** de cada amostra e
    chaveada pelo índice devolvido junto com a predição; a checagem de finitude
    (C5) ocorre **depois** do recorte, senão a cauda legítima erguria sempre.
  - **Modo fit-only.** `test_decision_indices` vazio significa fit-only: `grids`
    vem vazio, `artifact_path` vem vazio, **nenhum checkpoint é escrito** e só a
    perda de validação é reportada. É o modo que a varredura usa (D8).
  - A grade emitida é **crua** (pode cruzar); o guardrail é aplicado pelo use
    case (I5).

- **`HyperparameterSearch`** (`port-out`) — busca *ask-and-tell*, sem callback
  atravessando a fronteira (D7):

  ```python
  @dataclass(frozen=True)
  class SearchDimension:
      name: str          # DEVE ser um campo de TftTrainingParams
      low: float
      high: float
      kind: str          # 'int' | 'float'
      log: bool = False
      # __post_init__: kind válido; low < high; low >= 1 quando kind=='int' e log;
      # name pertencente aos campos de TftTrainingParams (C11)

  @dataclass(frozen=True)
  class SearchTrial:
      number: int                     # número do trial no estudo
      values: Mapping[str, float]     # sempre float na fronteira; o use case
                                      # reconverte por SearchDimension.kind

  class HyperparameterSearch(Protocol):
      def create_study(self, *, seed: int, direction: str = "minimize") -> str: ...
      def ask(self, space: Sequence[SearchDimension]) -> SearchTrial: ...
      def tell(self, *, trial_number: int, objective_value: float) -> None: ...
      def best_trial(self) -> SearchTrial: ...
  ```

  `create_study(seed=...)` é a forma **do port**: o adapter a traduz para o
  amostrador semeado da biblioteca (a semente do Optuna vive no sampler, não no
  estudo).

- **`TrainTft`** (use case) — portas injetadas: `MedallionStore`,
  `WalkForwardSplitter`, `TftTrainer`, `PersistPredictions`,
  `AnalyticsRepository`, `ExperimentTracker`, `Hasher`; mais o valor de
  configuração `artifacts_root` (raiz de artefatos, no padrão de `data_root`),
  a partir do qual o use case compõe `artifact_dir = <artifacts_root>/tft/<run_id>`
  e o passa ao port (D9 — é a origem do parâmetro `artifact_dir`, que de outro
  modo não teria dono). DTOs:

  ```python
  @dataclass(frozen=True)
  class TrainTftCommand:
      scope: ScopeSpec
      params: TftTrainingParams
      horizons: tuple[int, ...]
      quantile_levels: tuple[float, ...]
      n_folds: int
      test_size: int
      val_size: int
      calib_size: int
      embargo: int
      schema_version: int

  @dataclass(frozen=True)
  class TftRunSummary:
      run_id: str
      model_version: str          # 'tft_quantile'
      fold_index: int
      rows_written: int
      rows_skipped: int
      best_epoch: int
      best_val_loss: float
      fitted_decision_count: int
      monitored_decision_count: int
      artifact_path: str
      tracking_run_id: str

  @dataclass(frozen=True)
  class TrainTftResult:
      runs: tuple[TftRunSummary, ...]
  ```

- **`RunTftSweep`** (use case) — portas injetadas: `MedallionStore`,
  `WalkForwardSplitter`, `TftTrainer`, `HyperparameterSearch`,
  `ExperimentTracker`; mais `artifacts_root` (usado apenas para compor o
  diretório passado ao port — no modo fit-only nenhum arquivo é escrito lá).
  **Nenhuma porta que grave resultados** —
  `PersistPredictions` e `AnalyticsRepository` não aparecem no construtor
  (I14/D8). O `MedallionStore` entra apenas para a leitura do par read-only
  `(processed, dataset_tft)`, e nenhuma escrita passa por ele (asserção em A10).
  DTOs:

  ```python
  @dataclass(frozen=True)
  class RunTftSweepCommand:
      scope: ScopeSpec
      base_params: TftTrainingParams
      space: tuple[SearchDimension, ...]
      n_trials: int
      seed: int
      horizons: tuple[int, ...]
      quantile_levels: tuple[float, ...]
      n_folds: int
      test_size: int
      val_size: int
      calib_size: int
      embargo: int

  @dataclass(frozen=True)
  class SweepTrialSummary:
      trial_number: int
      values: Mapping[str, float]
      objective_value: float

  @dataclass(frozen=True)
  class RunTftSweepResult:
      study_id: str
      trials: tuple[SweepTrialSummary, ...]
      best_trial_number: int
      best_params: TftTrainingParams
  ```

### Consumidos

- **`WalkForwardSplitter`** / **`FoldSplit`** / **`ScopeSpec`** — Stage 5.1.
- **`MedallionStore.read`** (par read-only `processed/dataset_tft`) — 2.1/3.5.
- **`list_feature_specs`** (nome, ordem e `tft_typing`) — Stage 3.4.
- **`PersistPredictions`** / **`QuantileForecast`** — Stage 4.3.
- **`AnalyticsRepository`** (escrita de `dim_run`) + **`RunRecord`** — 4.1/4.2.
- **`ExperimentTracker`** (`start_run`/`log_params`/`log_metrics`/`set_tags`/
  `log_artifact`/`end_run`) — Stage 1.5 / ADR 1.5.0002.
- **`Hasher`** (`run_id`/`config_signature`) — Stage 1.4.
- **`deduplicate_operationally_latest`** — Stage 5.1.

## 5. Invariantes e regras

- **I1 — alinhamento do alvo:** a previsão do passo `h` do decodificador para a
  decisão `t` é `target_return[t + h]` — o retorno log de **um** dia realizado
  na sessão `t+h`, indexado por posição no array de sessões (ADR 4.3.0001),
  nunca por timedelta. Nenhuma regra √h se aplica (doc de domínio §2.1). É o
  mesmo rótulo que a 5.3 monta em `_labels_from_full_grid`.
- **I2 — tipagem known/unknown:** toda coluna do painel é declarada como
  conhecida ou desconhecida. Desconhecidas = features da registry com
  `spec.tft_typing == 'unknown'`; conhecidas = features da registry com
  `spec.tft_typing == 'known'` **∪** as colunas de calendário (`day_of_week`,
  `month`). A regra é essa, não a fotografia de hoje (em que a registry só tem
  `unknown`). Nenhuma coluna entra sem tipagem explícita; `time_idx` não é
  covariável (D4).
- **I3 — anti-vazamento por assimetria de indexação:** covariáveis
  desconhecidas e o próprio alvo entram no codificador em `[t − L + 1, t]` —
  **até `t` inclusive**; covariáveis conhecidas entram no decodificador até
  `t+max_horizon`. É a Eq. (1) do paper e a razão de I2 existir.
- **I4 — contexto passado × ajuste e seleção (duas cláusulas, D1):**
  (a) a janela de contexto de uma decisão pode alcançar sessões de partições
  anteriores, restrita a sessões **`≤ t`** — nada em `> t` entra no codificador;
  (b) `calib` não entra em **ajuste** nem em **monitor** — não alimenta nenhum
  conjunto de treino nem a perda de validação — e a transformação **ajustada**
  do fluxo (o normalizador do alvo; não há codificador categórico ajustado
  porque todas as covariáveis são contínuas e o grupo é constante) é estimada
  **apenas sobre o quadro de treino** e herdada pelas demais partições.

  *Quadro de treino* é o bloco `train` **mais** as `max_horizon` sessões
  seguintes — que são de purga, nunca decisões, e existem no quadro porque são
  os **rótulos** das últimas decisões de treino (o decodificador de `t` cobre
  `t+1..t+max_horizon`). A distinção importa: essas sessões estão estritamente
  antes de `early_stop`, `calib` e `test`, então incluí-las não é vazamento —
  mas dizer "apenas o bloco `train`" tornaria a verificação numérica do
  normalizador insatisfazível, porque a biblioteca ajusta sobre o quadro que
  recebe. A cláusula
  (b) é o canal de vazamento real: normalizar sobre a série inteira antes de
  particionar é o erro que Hewamalage, Ackermann & Bergmeir (2023) nomeiam.

  **Alcance é condicional, não incondicional.** Com `L = max_encoder_length`,
  `gap = max_horizon + embargo` e a geometria real do splitter (o último índice
  de `calib` é `test_start − gap − 1`), a decisão de teste de offset `j` alcança
  `calib` sse `j <= L − gap − 2`; alcança `early_stop` sse
  `j <= L − 2·gap − calib_size − 2`; alcança `train` sse
  `j <= L − 3·gap − calib_size − val_size − 2`. As provas de mutação (A4) usam
  `j = 0` e declaram a geometria que garante o alcance.
- **I5 — grade crua no port, guardrail no use case:** o port emite valores
  possivelmente cruzados; `QuantileForecast.from_raw` (rearranjo CFG 2010, ADR
  4.3.0002) é aplicado por (decisão × horizonte) antes de persistir — simetria
  exata com 5.2/5.3.
- **I6 — melhor checkpoint restaurado:** a predição de teste usa os pesos da
  época de **menor** perda de validação. A restauração é explícita (o callback
  de parada antecipada do Lightning não a faz), e `artifact_path` aponta para o
  arquivo daquela época — o vínculo é contratual, não incidental, para que a
  mutação "não restaurar" seja detectável comparando a predição com a de um
  modelo recarregado do artefato.
- **I7 — `early_stop` monitora, `calib` não ajusta nem seleciona:** a seleção da
  época usa exclusivamente as decisões de `early_stop` do fold (papel desenhado
  no ADR 5.1.0002); `calib` permanece reservada ao conformal (Step 7). O
  invariante é sobre **ajuste e seleção**, não sobre leitura como contexto —
  ver I4 e ADR 5.4.0001.
- **I8 — um modelo, um artefato por fold:** um único ajuste por fold, com
  decodificador de `max_horizon` passos, do qual saem todos os horizontes
  pedidos (D2). Nenhum ajuste por horizonte.
- **I9 — determinismo por semente, no mesmo processo e ambiente:** com a mesma
  semente, o mesmo painel e o mesmo comando, duas chamadas no **mesmo processo**
  emitem predições idênticas. Exige re-semear **a cada chamada** (o gerador
  global avança entre elas), carregadores sem processos paralelos e treinador em
  modo determinístico; a flag global de algoritmos determinísticos do `torch`,
  se usada, é restaurada ao valor anterior ao sair (é estado de processo e
  contaminaria o resto da suite). Reprodutibilidade entre processos, plataformas
  ou versões de biblioteca **não** é afirmada — e a verificação (A9) tem
  exatamente o escopo da afirmação.
- **I10 — identidade persistida:** `model_version='tft_quantile'`;
  `dim_run.seed = command.params.seed`; `fold`, `split_fingerprint`,
  `config_signature` e `parent_sweep_id` seguem o padrão de 5.2/5.3; o payload
  do `run_id` inclui a tupla ordenada de `feature_names` **e** a tupla de
  `known_feature_names` (auditabilidade da tipagem, não só do conjunto).
- **I11 — dedup de zero remoção:** dedup operationally-latest com chave
  estrutural `(split, horizon, decision_idx + horizon, quantile_level)` aplicado
  e **obrigatoriamente** removendo zero linhas (mesma asserção de 5.2/5.3).
- **I12 — rastreamento por run:** cada fold abre um run no `ExperimentTracker`,
  registra parâmetros (semente, hiperparâmetros, geometria do fold, grade,
  impressão do split), métricas (perda de validação por época e a da melhor
  época), tags (`model_version`, `phase='confirmatory_ready'`, `fold`) e o
  **artefato** do checkpoint; fecha o run ao final. Falha do tracker **não**
  invalida a persistência das predições (C8).
- **I13 — biblioteca só no adapter:** `torch`, `lightning`, `pytorch_forecasting`
  e `optuna` vivem exclusivamente em `features/modeling/adapters/out/`; os gates
  `modeling-no-torch-leak` e `modeling-no-optuna-leak` reprovam vazamento para
  application/domain.
- **I14 — varredura isolada estruturalmente (D8):** `RunTftSweep` **não recebe**
  porta que grave resultados; roda o port em modo fit-only
  (`test_decision_indices` vazio), mede o objetivo **apenas** na perda de
  validação, não emite nenhuma escrita pelo `MedallionStore` e marca todo run
  com `phase='exploratory'`. Nenhum hiperparâmetro é escolhido olhando `calib`
  ou `test`.
- **I15 — janela incompleta não fabrica alvo:** decisões cujo `t+h` cai além da
  grade de sessões nunca recebem predição fabricada, nem por padding da
  biblioteca (daí o recorte por comprimento de decodificador na emissão).
- **I16 — regra de emissão na cauda:** o par (decisão `t`, horizonte `h`) é
  emitido sse `t + h <= len(target) - 1`. É **exatamente** a condição de pulo do
  4.3 (`decision_idx + horizon >= len(dataset_timestamps)`), logo o conjunto de
  pontos alinhados persistidos pelo TFT é **idêntico** ao de 5.2/5.3 no mesmo
  fold. A cláusula de janela completa (`t >= L - 1`) não recorta nada no teste:
  como C3 exige ao menos uma decisão de treino com janela e decodificador
  completos, `test_start > L - 1` sempre — a cláusula é guarda, não filtro.
- **I17 — descarte declarado (treino e monitor):** decisões de treino ou de
  monitor sem janela de contexto completa ou sem decodificador completo são
  descartadas pela construção do conjunto de amostras; as contagens efetivas
  voltam no resultado (`fitted_decision_count`, `monitored_decision_count`) e
  são conferidas contra a aritmética esperada. Descarte silencioso é defeito.

## 6. Casos de erro e exceções

- **C1 — dataset vazio para o ativo** → `ValueError` antes de qualquer treino
  (paridade com C1 da 5.3).
- **C2 — comando inválido** → `ValueError` antes de qualquer I/O: `horizons`
  vazio/duplicado/não positivo ou com `max(horizons) > scope.max_horizon`;
  `quantile_levels` vazio, fora de (0,1), não estritamente crescente; `params`
  fora de faixa (`max_encoder_length < 1`, `hidden_size < 1`,
  `attention_head_size < 1`, `dropout` fora de [0,1), `learning_rate <= 0`,
  `max_epochs < 1`, `patience < 1`, `batch_size < 1`).
- **C3 — histórico insuficiente** → `ValueError` no port (fake e real, mesma
  regra) quando, após aplicar a regra de janela e decodificador completos (I17),
  **nenhuma** decisão de treino ou **nenhuma** decisão de monitor sobra. Limiar
  observável, paridade fake↔real na suite de contrato.
- **C4 — estrutura inconsistente no port** → `ValueError`: largura de linha ≠
  `len(feature_names)`; `len(target) != len(rows)`; `known_feature_names` não
  contido em `feature_names`; índice de decisão fora do painel; **conjunto de
  índices de decisão não contíguo ou não crescente**; `horizons` não contido em
  `1..max_horizon`; `early_stop_decision_indices` vazio (sem monitor não há
  seleção de época).
- **C5 — grade emitida não finita** → `ValueError` no adapter real, avaliado
  **após** o recorte por comprimento de decodificador: NaN/inf numa posição
  realmente prevista nunca é emitido silenciosamente (paridade com C5 de
  5.2/5.3; o caso é inatingível na perna fake por construção — finding herdado
  da 5.3).
- **C6 — colunas esperadas ausentes do dataset** → `ValueError` nomeando as
  colunas faltantes (drift registry × dataset, risco R6).
- **C7 — rerun idêntico** → `DuplicateKeyError` propaga do `AnalyticsRepository`
  (append-only; semântica de replay é desenho da 5.5, finding herdado da 5.2).
- **C8 — falha do `ExperimentTracker`** → **absorvida**, não propagada: o erro é
  registrado em log e o fold segue, com `TftRunSummary.tracking_run_id` vazio.
  Propagar destruiria o resultado de um trabalho já concluído e persistido —
  tracking é observabilidade, não fonte da verdade (a fonte é
  `fact_oos_predictions`). A ordem é obrigatória: **persistir primeiro,
  rastrear depois**, para que a absorção nunca esconda uma persistência
  incompleta.
- **C9 — varredura sem trials válidos** → `ValueError` em `RunTftSweep` quando
  `n_trials < 1` ou quando todo trial falhou; `best_trial` sobre estudo vazio
  ergue no port (fake e real).
- **C10 — treino sem checkpoint utilizável** → `ValueError` no adapter quando a
  perda de validação nunca é finita ou o caminho do melhor checkpoint volta
  vazio após o ajuste. É cenário plausível nesta Stage (painel sintético curto
  com taxa de aprendizado default pode divergir na primeira época, e a parada
  antecipada com checagem de finitude interrompe antes de qualquer salvamento);
  falhar em silêncio produziria um `artifact_path` inválido que só quebraria na
  Stage 7.1.
- **C11 — dimensão de busca inválida** → `ValueError` na construção de
  `SearchDimension`: `kind` fora de `{int, float}`, `low >= high`, `low < 1` com
  `kind='int'` e escala logarítmica, ou `name` que não é campo de
  `TftTrainingParams` (sem isso o erro só apareceria como `TypeError` opaco na
  hora de montar os params do trial).

## 7. Decisões técnicas relevantes

### D1 — A janela de contexto cruza fronteiras de partição; o que não cruza é o ajuste

- **O quê:** I4, nas duas cláusulas. O codificador de uma decisão de teste
  consome sessões que podem pertencer a `early_stop`, `calib` e ao gap de purga
  — todas `≤ t`, e apenas nas decisões cujo offset satisfaz a condição
  paramétrica de I4. Em contrapartida, nenhuma decisão fora de `train` entra no
  ajuste, nenhuma fora de `early_stop` entra no monitor, e o normalizador é
  estimado só sobre o **quadro de treino** — no sentido preciso de I4(b), que é
  a formulação autoritativa.
- **Por quê:** purga e embargo (López de Prado 2018 §7.4) operam sobre o
  **treino** e sobre **rótulos** — removem observações de treino cuja janela de
  formação do rótulo invade o teste. Nunca restringem a janela de features de
  uma observação de teste, que naquele arcabouço é móvel por construção. A
  avaliação com origem móvel (Tashman 2000; Bergmeir & Benítez 2012) pressupõe
  que tudo até a origem está disponível como entrada. O split conformal (Lei et
  al. 2018; Barber et al. 2023) exige que o **preditor ajustado** seja
  independente da calibração — ler contexto passado não reajusta nem
  re-seleciona nada, ao contrário da parada antecipada, que é exatamente o que
  o ADR 5.1.0002 mantém separado. Para forecasters sequenciais, a "feature" de
  um exemplo **é** a janela de retrospecto (Stankevičiūtė et al. 2021). A
  cláusula (b) existe porque o vazamento real desse desenho é o
  pré-processamento ajustado sobre a série inteira (Hewamalage, Ackermann &
  Bergmeir 2023), que a construção derivada do conjunto de treino evita.
- **Fonte:** bloco B3 do alinhamento (issue #57), respondido com levantamento
  de literatura em 2026-08-09; doc de domínio §5.2/§5.3; correção de aritmética
  do Checkpoint A rodada 2.
- **ADR:** [`5_4_0001-encoder-context-across-partitions.md`](../../adr/5_4_0001-encoder-context-across-partitions.md)

### D2 — Um modelo com decodificador de `max_horizon` passos, com emissão variável na cauda

- **O quê:** um ajuste por fold, decodificador de `max_horizon` passos no treino
  e no monitor, do qual se extraem os horizontes pedidos (h+1 e h+7 no piloto).
  Na **predição**, o comprimento do decodificador é o que a cauda do painel
  permite, e o par (decisão, horizonte) só é emitido quando existe (I16), com a
  saída recortada pelo comprimento real de cada amostra.
- **Por quê:** é o uso canônico do TFT e a perda do paper (soma da pinball sobre
  grade **e** horizontes, Lim et al. 2021 Eq. 24). Partir em um modelo por
  horizonte dobraria custo de treino e artefatos e afastaria o candidato do
  desenho publicado — sem ganho, já que o alvo de cada passo é o mesmo retorno
  de um dia. A emissão variável existe porque o bloco de teste do último fold
  termina na última sessão do painel: com decodificador fixo, as últimas
  `max_horizon` decisões seriam impredizíveis e o candidato perderia pontos de
  h+1 que os comparadores têm — quebrando a paridade da base amostral que a
  inferência pareada do Step 6 pressupõe. Como a saída da biblioteca é
  retangular e preenchida, o recorte por comprimento de decodificador é o que
  impede o padding de virar predição fabricada (I15). Assimetria consciente com
  o GBM (5.3, ADR 5.3.0001): lá o direto por horizonte foi adotado porque
  árvores não têm decodificador sequencial; a comparabilidade que o Step 6 exige
  é do **alvo, do grão e do conjunto de pontos** (I1/I16), não do mecanismo.
- **Fonte:** bloco B2 do alinhamento (issue #57); achados do Checkpoint A sobre
  a cauda do último fold e sobre o padding da saída.
- **ADR:** [`5_4_0002-single-multi-horizon-decoder.md`](../../adr/5_4_0002-single-multi-horizon-decoder.md)

### D3 — `torch` (CPU) e `pytorch-forecasting` em `dependencies`, com teste de fumaça real na CI

- **O quê:** `torch`, `lightning`, `pytorch-forecasting` e `optuna` entram nas
  dependências principais; `torch` é resolvido de um índice CPU explícito
  (`[[tool.uv.index]]` + `[tool.uv.sources]`), e o teste de fumaça do adapter
  real roda na CI, sem `skipif`.
- **Por quê:** diverge conscientemente do ADR 3.2.0002 (FinBERT como extra
  opcional). Lá a lógica que importava era pura e testável sem `torch`. Aqui o
  TFT **é** o objeto de estudo e "treina em modo quantílico com a grade densa" é
  o critério de aceite central: verificá-lo só por execução manual tira a rede
  de segurança automática justamente do candidato do projeto. O índice CPU é o
  que torna isso viável — a resolução padrão do `torch` no PyPI para Linux traz
  a variante CUDA, de vários GB. Consequência assumida: a cláusula operativa do
  3.2.0002 ("o CI nunca instala `torch`") deixa de valer, e os comentários que a
  repetem em `pyproject.toml` e `.importlinter` são corrigidos nesta Stage,
  junto com uma nota retroativa no próprio 3.2.0002.
- **Fonte:** bloco B1 do alinhamento (issue #57); documentação do `uv` sobre
  índices do PyTorch; achados do Checkpoint A.
- **ADR:** [`5_4_0003-torch-core-dependency-cpu-index.md`](../../adr/5_4_0003-torch-core-dependency-cpu-index.md)

### D4 — Tipagem das entradas: registry para as features, calendário declarado localmente, índice temporal relativo

- **O quê:** as features da registry entram tipadas por `spec.tft_typing`
  (regra, não fotografia — I2); `day_of_week` e `month` entram como conhecidas,
  declaradas em constante do próprio use case; `time_idx` é o **índice** do
  painel e não entra como covariável — a posição relativa dentro da janela entra
  pelo mecanismo de índice relativo da biblioteca.
- **Por quê:** derivar a tipagem das features do campo validado da spec é o que
  o ADR 3.4.0002 estabeleceu. O calendário fica local porque não é feature da
  registry — registrá-lo lá mudaria `feature_set_hash` e o conjunto que alimenta
  o dataset (3.5) e o GBM (5.3), atravessando três Stages fechadas. **Piso
  declarado + issue #58** para o tratamento geral. O índice temporal absoluto
  fica fora pela mesma razão do ADR 5.3.0003: sob janela expansiva, todo índice
  de teste está fora da faixa vista no treino, então ele não discrimina fora da
  amostra e memoriza dentro dela — e, ao contrário das árvores, aqui ainda
  passaria pelo normalizador, produzindo extrapolação silenciosa.
- **Fonte:** ADR 3.4.0002 (Alternativa B), ADR 5.3.0003, issue #58.
- **ADR:** [`5_4_0004-tft-input-typing-and-relative-time-index.md`](../../adr/5_4_0004-tft-input-typing-and-relative-time-index.md)

### D5 — Forma do port: painel completo + faixas de índice contíguas por partição

- **O quê:** o port recebe o painel inteiro (matriz de linhas + alvo, ordenados
  por sessão) e três **faixas contíguas** de índices de decisão; não recebe
  recortes por partição. O painel é de **um ativo** (o do `ScopeSpec`), então
  não há identidade de grupo atravessando a fronteira: o agrupamento constante é
  detalhe interno do adapter.
- **Por quê:** consequência direta de D1 — a janela de contexto de uma decisão
  precisa de sessões anteriores à sua partição, então recortar o painel por
  partição tornaria o contrato impossível de cumprir. Passar índices em vez de
  recortes mantém o controle do anti-vazamento **no use case** (que os deriva do
  `FoldSplit`) e torna a fronteira auditável. A exigência de contiguidade não é
  arbitrária: a biblioteca só expressa **piso** de decisão, então um conjunto
  arbitrário de índices não seria honrável pelo adapter real — e um port que
  aceita o que o adapter não honra produz divergência fake↔real silenciosa,
  justamente no monitor, onde ela significaria `calib` entrando na perda de
  validação. Como as partições do `FoldSplit` são blocos contíguos, a restrição
  não custa nada ao chamador.
- **Fonte:** D1; concept 5.3 §7-D4 (precedente de forma); achados do
  Checkpoint A (identidade de grupo fora do port; ausência de teto de decisão na
  biblioteca).

### D6 — Parada antecipada por época com restauração explícita do melhor checkpoint

- **O quê:** treinar até `max_epochs` com parada por paciência sobre a perda de
  validação; salvar o melhor checkpoint e **recarregá-lo** antes de predizer;
  devolver `best_epoch`, `best_val_loss`, o histórico por época e o caminho do
  checkpoint **daquela** época.
- **Por quê:** o doc de domínio §5.3 fixa que o modelo retido é o de menor erro
  de validação visto (Prechelt 1998) e registra a mecânica: no Lightning a
  restauração não vem do callback de parada. Amarrar `artifact_path` ao
  checkpoint da melhor época é o que torna a mutação "não restaurar" detectável
  por identidade (predição igual à do modelo recarregado do artefato), sem
  depender de um cenário de treino que só ocorre por sorte. A alternativa
  registrada como **não adotada** pelo doc de domínio — re-treinar em
  treino+validação com o número de épocas selecionado — apagaria a fronteira que
  o ADR 5.1.0002 garante.
- **Fonte:** doc de domínio §5.3; ADR 5.1.0002; achados do Checkpoint A sobre a
  verificabilidade do critério e sobre o checkpoint vazio (C10).

### D7 — Busca de hiperparâmetros como interface *ask-and-tell*

- **O quê:** o port expõe `create_study`/`ask`/`tell`/`best_trial`; o laço de
  trials vive no use case `RunTftSweep`, não no adapter.
- **Por quê:** a alternativa natural — passar a função-objetivo para o adapter,
  como faz a API de alto nível do Optuna — faria uma *callable* atravessar a
  fronteira e moveria a orquestração (qual fold, qual modo do trainer, o que é
  logado) para dentro do adapter, onde ela deixa de ser testável com fake e
  deixa de ser auditável pelo gate de camadas. O Optuna suporta *ask-and-tell*
  nativamente, então a escolha não cria mecanismo. Efeito colateral desejado: o
  fake é um amostrador determinístico, e a suite de contrato compara as duas
  pernas sem depender de convergência.
- **Fonte:** doc de domínio §5.4; documentação oficial de *ask-and-tell*;
  postura de ports do ADR 1.5.0002.
- **ADR:** [`5_4_0005-ask-and-tell-sweep-port-and-isolation.md`](../../adr/5_4_0005-ask-and-tell-sweep-port-and-isolation.md)

### D8 — A varredura é exploratória e não recebe porta que grave resultados

- **O quê:** I14. O objetivo é a perda de validação em modo fit-only; o use case
  **não recebe** `PersistPredictions` nem `AnalyticsRepository`; o
  `MedallionStore` que recebe é usado só para leitura, e A10 assere zero
  chamadas de escrita; todo run leva `phase='exploratory'`.
- **Por quê:** o protocolo de Raschka (2018, §3–4) exige que a seleção de
  hiperparâmetros use apenas treino+validação e que a avaliação final aconteça
  uma única vez com hiperparâmetros congelados — sob pena de viés otimista. Se a
  varredura persistisse predições no mesmo armazém do confirmatório, a
  separação passaria a depender de filtrar por rótulo na leitura, e um erro de
  filtro contaminaria a inferência do Step 6. Não ter a dependência é a garantia
  que um teste consegue assertar sem depender da disciplina da implementação
  (asserção sobre um fake nunca injetado seria vácua); o modo fit-only e o
  rótulo são as camadas seguintes.
- **Fonte:** doc de domínio §5.4; overview §3/§4; achados do Checkpoint A.
- **ADR:** [`5_4_0005-ask-and-tell-sweep-port-and-isolation.md`](../../adr/5_4_0005-ask-and-tell-sweep-port-and-isolation.md)

### D9 — Artefato em disco sob raiz configurável, referenciado pelo tracker

- **O quê:** o checkpoint da melhor época é gravado em
  `<artifacts_root>/tft/<run_id>/` e registrado via `log_artifact`; nenhuma
  tabela silver nova é criada. `artifacts_root` entra em `Settings` com default
  relativo, no padrão de `data_root`.
- **Por quê:** o DoD da Stage pede artefato persistido e run logado; o port
  `ExperimentTracker` já tem `log_artifact` e foi desenhado (ADR 1.5.0002) com
  este consumidor em mente. Criar uma tabela `fact_model_artifacts` reproduziria
  o modelo do repositório antigo que aquele ADR rejeitou explicitamente. O
  caminho volta no `TftRunSummary` para a Stage 7.1 consumir.
- **Fonte:** ADR 1.5.0002 (Alternativa A rejeitada); roadmap §5.4 (DoD) e §7.1.

### D10 — Normalizador do alvo explícito, ajustado no bloco de treino

- **O quê:** o normalizador do alvo é fixado explicitamente como normalizador
  **por grupo com grupo único** (padronização global ajustada sobre o quadro de
  treino), nunca `"auto"`, e seus parâmetros ajustados (centro e escala) voltam
  no resultado do port para serem assertados.
- **Por quê:** a seleção automática da biblioteca escolhe um normalizador **por
  janela do codificador** quando `max_encoder_length > 20` — que é o caso do
  default desta Stage (60) e não é o caso das geometrias pequenas dos testes
  (~10). Duas consequências, ambas inaceitáveis: a suite validaria um caminho
  que a produção não usa, e a cláusula (b) de I4 ficaria sem objeto, porque não
  haveria transformação ajustada no treino para verificar. Fixar o normalizador
  também é o que torna A4(c) implementável: os parâmetros ficam inspecionáveis e
  a derivação do conjunto de predição os herda em vez de reajustá-los.
- **Fonte:** achado do Checkpoint A rodada 2 (código de seleção automática da
  `pytorch-forecasting` 1.8); ADR 5.4.0001 cláusula 2.
- **ADR:** [`5_4_0006-explicit-train-fitted-target-normalizer.md`](../../adr/5_4_0006-explicit-train-fitted-target-normalizer.md)

### D11 — Histórico de perda por época vem de um callback próprio

- **O quê:** o adapter registra um callback que acumula a perda de validação ao
  fim de cada época, ignorando a passagem de sanidade do treinador (ou
  desabilitando-a), e devolve o histórico em `val_loss_by_epoch`.
- **Por quê:** o Lightning expõe apenas o **último** valor das métricas; não há
  histórico por época em API pública. Como I6 e A5 verificam o mecanismo de
  parada por identidade (`best_epoch == argmin(histórico)`), o histórico é
  contrato, não conveniência — e precisa ser declarado como mecanismo desta
  Stage em vez de aparecer como detalhe no código. A ressalva da passagem de
  sanidade não é cosmética: ela dispara o mesmo gancho antes da primeira época e
  deslocaria todo o índice, quebrando exatamente a identidade que A5 usa como
  prova.
- **Fonte:** achado do Checkpoint A rodada 2 (API do Lightning; passagem de
  sanidade habilitada por default).

## 8. Integrações

### Internas (com outras Stages/módulos)

- `modeling.application → analytics_store.application` (`PersistPredictions`,
  `AnalyticsRepository`, `RunRecord`): fronteira cross-BC já sancionada em
  5.2/5.3. Vale para `TrainTft`; `RunTftSweep` **não** cria essa aresta (D8).
- `modeling.application → feature_engineering.domain` (`list_feature_specs`):
  consumo declarado no roadmap; import application→domain cross-BC preserva a
  direção para dentro.
- `modeling.application → shared.application.ports.out` (`ExperimentTracker`,
  `Hasher`, `MedallionStore`): portas compartilhadas, direção normal.
- `composition_root`: novos campos `train_tft` e `run_tft_sweep` em
  `ApplicationDependencies`, com proxies lazy (`_LazyPfTftTrainer`,
  `_LazyOptunaSearch`) no padrão de `_LazyLightgbmQuantileTrainer` — adiam
  `torch`/`optuna` até o primeiro uso (custo de import, não opcionalidade).

### Externas

- **`torch` (CPU) + `lightning` + `pytorch-forecasting` (>=1.8, <2.0):**
  consumidos exclusivamente por
  `features/modeling/adapters/out/pytorch_forecasting/`. Contrato de uso, com o
  nível de detalhe que as armadilhas exigem:
  - `TimeSeriesDataSet` com `time_idx`, `target`, `group_ids` (grupo constante),
    `max_encoder_length` = `min_encoder_length` (janela completa),
    `max_prediction_length = max_horizon`, `min_prediction_length` igual ao
    máximo no treino/monitor e `1` na predição (cauda variável),
    `time_varying_known_reals`, `time_varying_unknown_reals`, índice temporal
    relativo habilitado, e **`target_normalizer` explícito** (D10, nunca `auto`);
  - conjuntos de monitor e predição derivados do de treino (herdam o
    normalizador ajustado — I4b) e delimitados por piso de decisão + recorte do
    quadro (não há teto de decisão na biblioteca — D5);
  - `TemporalFusionTransformer.from_dataset(..., loss=QuantileLoss(quantiles=...))`
    com a grade do comando (o default da biblioteca são 7 níveis fixos e **não**
    é a grade do projeto);
  - `Trainer` com `accelerator` fixo em CPU, modo determinístico, sem passagem
    de sanidade (D11), com callbacks de parada antecipada, de checkpoint (melhor
    época) e o de histórico (D11); sem checkpoint no modo fit-only;
  - predição em modo quantílico pedindo **índice** e **comprimentos de
    decodificador** junto com a saída — sem eles não há como distinguir passo
    real de padding (I15/I16);
  - recarga do melhor checkpoint pelo caminho registrado, que é o
    `artifact_path` devolvido.
- **`optuna` (>=4.0, <5.0):** consumido exclusivamente por
  `features/modeling/adapters/out/optuna/`, apenas pela API *ask-and-tell*
  (`ask` com distribuições construídas a partir de `SearchDimension`, `tell` por
  número de trial) com amostrador semeado — a semente do port vira semente do
  amostrador.
- Gates `modeling-no-torch-leak` e `modeling-no-optuna-leak` reprovam vazamento
  para `application`/`domain` (dois contratos, seguindo a postura
  single-purpose do precedente `modeling-no-lightgbm-leak`), cada um com caso em
  `_REAL_VIOLATION_CASES`.

## 9. Modelo de dados

Nenhum schema novo. Reusa `silver/fact_oos_predictions` (formato LONG por nível,
ADR 4.1.0002) e `silver/dim_run` (upsert por `run_id`), com
`model_version='tft_quantile'` e `seed` preenchida. O artefato do modelo é
arquivo em disco referenciado pelo tracker (D9), fora do medalhão.

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| R1 — tempo/tamanho da instalação na CI (~250–300 MB de download, >1 GB instalado) | A | M | índice CPU (D3); cache do `uv` habilitado no workflow; medição do tempo do job registrada na Task de dependências, com o número no relatório |
| R2 — **suite** do adapter lenta (da ordem de vinte treinos reais, ~10–20 s cada) | A | M | painel sintético mínimo e modelo mínimo; reuso de um modelo treinado por sessão de teste onde o critério não exige treino próprio; orçamento medido no agregado e marcador `slow` decidido sobre ele, com o número no relatório |
| R3 — API da `pytorch-forecasting` 1.8 divergir do esperado | M | A | Task do adapter começa por um teste de mecânica que exercita construção do dataset, uma época, emissão quantílica com índice e comprimentos, e recarga de checkpoint; divergência vira ajuste local do adapter, nunca mudança de contrato do port |
| R4 — não determinismo residual do treino em CPU | M | M | re-semear por chamada, sem paralelismo de carregamento, modo determinístico do treinador, flag global restaurada ao sair; I9 e A9 têm o mesmo escopo (mesmo processo) |
| R5 — descarte por janela incompleta reduzir demais o treino do 1º fold | M | M | I17 devolve as contagens efetivas e A12 as confere; C3 ergue se sobrar zero; a geometria dos testes usa janela pequena |
| R6 — drift registry × colunas do dataset | B | A | C6: validação nominal das colunas antes do treino |
| R7 — índice CPU conflitar com o ambiente ROCm da 5.5 | M | B | fronteira declarada em §1; o ADR 5.4.0003 registra o caminho e a alternativa (extras conflitantes do `uv`) |
| R8 — off-by-one entre passo do decodificador e horizonte | M | A | A15: na perna real, asserção sobre o índice devolvido pela predição (caixa-branca, não depende de o modelo ter aprendido); na perna fake, oráculo de proximidade. É a classe de bug que o ADR 4.3.0001 registra como a mais cara do repositório antigo |
| R9 — divergência numérica na primeira época com painel sintético | M | M | C10 ergue nomeando a condição em vez de devolver caminho de artefato vazio; taxa de aprendizado das fixtures escolhida para não divergir |

## 11. Critérios de aceitação

- [ ] A1 — `TftTrainer`, `HyperparameterSearch`, `TrainTft` e `RunTftSweep`
  existem com as assinaturas de §4 e passam `make check` (mypy strict, layout,
  import-linter).
- [ ] A2 — para cada fold, o adapter ajusta **um** modelo com decodificador de
  `max_horizon` passos e emite a grade completa por (decisão de teste ×
  horizonte emitido), alinhada 1:1 a `quantile_levels` (suite de contrato,
  pernas fake e real).
- [ ] A3 — tipagem (I2 como **regra**): teste prova que a lista de
  desconhecidas é exatamente `{spec.name : spec.tft_typing == 'unknown'}` da
  registry e que a de conhecidas é
  `{spec.name : spec.tft_typing == 'known'} ∪ {day_of_week, month}`, com uma
  spec `known` injetada no teste para provar que a regra move a coluna de lista
  sozinha; `time_idx` não aparece em nenhuma das duas. Mutação que reclassifique
  uma feature de preço como conhecida é detectada.
- [ ] A4 — anti-vazamento, três provas com canais **separados**:
  (a) **ajuste/monitor** — mutar o alvo em `calib` e em `test` deixa
  `best_epoch` e `val_loss_by_epoch` idênticos. A invariância é verdadeira e
  não vácua: pela aritmética do splitter, para a última decisão de treino
  `t* = train_end − 1` vale `early_stop_start − (t* + max_horizon) = embargo + 1
  ≥ 1`, e a mesma identidade vale entre `early_stop` e `calib`;
  (b) **contexto não é vácuo** — mutar sessões `≤ t` dentro da janela da decisão
  de teste de offset `j = 0` **altera** a predição daquela decisão, com a
  geometria escolhida para satisfazer `j <= L − gap − 2` (I4);
  (c) **normalizador ajustado só no quadro de treino** — `normalizer_center` e
  `normalizer_scale` devolvidos pelo port batem com a média e o desvio amostral
  (com epsilon) do alvo sobre as **sessões do quadro de treino** definido em
  I4(b). A mutação que isso detecta é **construir o conjunto de treino a partir
  do painel inteiro** — aí os parâmetros mudam. Mutar o quadro de *predição*
  não serve como prova: ele é derivado do de treino e herda os parâmetros sem
  reajustar, então a asserção passaria de qualquer jeito. Verificado **no
  adapter real** — inatingível na perna fake, que não tem normalizador, na
  mesma linha do C5.
- [ ] A5 — melhor checkpoint (I6), verificado por **mecanismo**:
  `best_epoch == argmin(val_loss_by_epoch)`; `len(val_loss_by_epoch)` igual ao
  número de épocas executadas (prova que a passagem de sanidade não contaminou o
  histórico — D11); `artifact_path` não vazio, existente em disco e
  correspondente à época `best_epoch`; e a predição de teste idêntica à de um
  modelo recarregado desse arquivo — de modo que a mutação "predizer com os
  pesos da última época" é detectada.
- [ ] A6 — `calib` não entra em ajuste nem em monitor (I7): nenhum índice de
  `calib` é passado ao port como decisão de treino ou de monitor — asserção
  sobre os argumentos da chamada no use case — e, no port, A4(a).
- [ ] A7 — predições persistidas em `fact_oos_predictions` com
  `model_version='tft_quantile'`, guardrail aplicado por (decisão × horizonte),
  `target_timestamp` por indexação de sessões (via 4.3), e `dim_run` com `seed`
  preenchida — teste de integração com store real em `tmp_path`.
- [ ] A8 — rastreamento (I12) com **fake** do `ExperimentTracker`: cada fold
  abre e fecha um run, registra parâmetros/métricas/tags e chama `log_artifact`
  com um caminho existente em disco; tracker que ergue **não** derruba a
  execução — o `TftRunSummary` volta com `tracking_run_id` vazio e as linhas
  persistidas permanecem (C8).
- [ ] A9 — determinismo (I9): duas chamadas idênticas ao port no mesmo processo
  produzem grades, `best_epoch` e `best_val_loss` idênticos (fake e real) — o
  que também prova que a semente é reaplicada por chamada; e o use case
  completo, executado duas vezes contra stores isolados, produz as mesmas
  predições. Reprodutibilidade entre processos não é afirmada nem testada.
- [ ] A10 — varredura isolada (I14/D8): teste **estrutural** prova que
  `RunTftSweep` não recebe `PersistPredictions` nem `AnalyticsRepository` (a
  assinatura do construtor é o gate), que o fake do `MedallionStore` recebe zero
  chamadas de escrita, que o trainer é chamado com `test_decision_indices == ()`
  e sem escrever checkpoint, que o objetivo vem da perda de validação e que os
  runs levam `phase='exploratory'`; a suite de contrato do
  `HyperparameterSearch` cobre fake e Optuna real.
- [ ] A11 — casos de erro C1–C11 cobertos por testes dedicados; **C3/C4 nas duas
  pernas** da suite de contrato do `TftTrainer` e **C5/C10 no adapter real**
  (inatingíveis na perna fake por construção — finding herdado da 5.3).
- [ ] A12 — descarte declarado (I17): as contagens
  `fitted_decision_count`/`monitored_decision_count` batem com a aritmética
  esperada a partir dos índices passados, de `max_encoder_length` e de
  `max_horizon`; um caso com janela maior que o bloco de treino é exercitado.
- [ ] A13 — paridade de base amostral com os comparadores (I16): no mesmo fold e
  para cada horizonte, o conjunto de `target_timestamp` persistido pelo TFT é
  **igual** ao que a 5.3 persiste — igualdade exata, porque a condição de
  emissão do port e a condição de pulo do 4.3 são a mesma desigualdade. Um fold
  é construído com o bloco de teste terminando na última sessão do painel, para
  que a cauda seja exercitada.
- [ ] A14 — gates `modeling-no-torch-leak` e `modeling-no-optuna-leak` ativos,
  registrados em `_EXPECTED_CONTRACTS` **e** com caso em
  `_REAL_VIOLATION_CASES` (guarda contra contrato míope — sem ele um contrato
  apontando para o pacote errado passa verde), cada um com prova de quebra
  intencional revertida (saídas literais no relatório).
- [ ] A15 — alinhamento decodificador ↔ horizonte ↔ alvo (R8), em duas pernas
  com métodos distintos: na perna **real**, asserção de caixa-branca de que a
  chave de decisão usada para montar `grids` vem do índice devolvido pela
  predição e que o passo `h` corresponde a `t + h` — não depende de o modelo ter
  aprendido, portanto sobrevive ao modelo de fumaça; na perna **fake**, a grade
  codifica `(decision_idx, horizon)` e o oráculo de proximidade contra um alvo
  sintético injetivo discrimina `g(t+h)` de `g(t+h±1)`. Uma mutação que desloque
  o mapeamento em um passo falha em ambas.
- [ ] A16 — e2e: `TrainTft` executado via `wire_dependencies` de ponta a ponta
  (dataset semente → predições no parquet → artefato em disco), CPU-only, com o
  adapter **real** e sem `skipif` (D3); e com o `MlflowTracker` **real**
  apontando para `sqlite:///<tmp_path>/mlruns.db`, assertando que o run existe,
  tem os parâmetros/tags e o artefato registrado (fecha o item "runs logados no
  MLflow" do DoD com o adapter real, não só com o fake).
- [ ] A17 — cobertura ≥ 90% em cada arquivo tocado da Stage, **medida e
  reportada** no relatório da Stage a partir do `term-missing` (o gate
  automático do projeto é agregado, `fail_under = 90`; a medição por arquivo é
  do relatório). Qualquer arquivo abaixo disso é coberto ou justificado por
  escrito.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? (§4 — inclusive
  as portas injetadas em cada use case, cuja ausência é o que sustenta A10)
- [x] Toda decisão em §7 tem fonte rastreável? (blocos B1–B4 do alinhamento na
  issue #57, achados das duas rodadas do Checkpoint A, doc de domínio §5, ADRs)
- [x] Toda integração externa tem contrato definido? (§8 — as chamadas exatas,
  incluindo as três armadilhas verificadas: normalizador automático, padding da
  saída e ausência de histórico por época)
- [x] Decisões com alternativa real descartada têm ADR escrito?
  (D1→5.4.0001, D2→5.4.0002, D3→5.4.0003, D4→5.4.0004, D7/D8→5.4.0005,
  D10→5.4.0006; D5/D6/D9/D11 seguem precedente, doc de domínio ou mecânica sem
  alternativa viva)
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)?
  (5.1 `done`; 3.4/3.5/4.3/1.5/1.4 `done` transitivos)
- [x] Stage cabe em ~3–12 Tasks? (plano fechado em 15; o humano dispensou o limite
  de Tasks como restrição de desenho no alinhamento — bloco B4, issue #57 —
  preferindo separação a compressão)
- [x] Riscos críticos têm mitigação plausível? (§10)
- [x] Cada mecanismo novo passou pelo **teste da solução mais direta**? —
  **sim, com um piso declarado.** O concern transversal aqui é o
  **anti-vazamento**, e a pergunta foi feita em dois pontos. (a) Janela de
  contexto: a tentação era criar um caso especial local ("truncar o codificador
  na fronteira da partição"); a solução direta é declarar o invariante correto
  em duas cláusulas (I4) e deixar o mecanismo geral — purga/embargo do harness
  5.1 — fazer o trabalho que já faz, sem tipo nem parâmetro novo. (b) Tipagem
  known/unknown: o tratamento geral é a `FeatureSpec` (ADR 3.4.0002), e as
  features da registry o usam de fato (`spec.tft_typing`, como **regra**); só o
  calendário fica declarado localmente, porque registrá-lo a montante mudaria
  `feature_set_hash` e o conjunto de features de três Stages fechadas. Isso é
  **piso declarado + issue #58**, não captura silenciosa do concern.
- [x] O canal de emissão da Stage já existe? (sim — `fact_oos_predictions` e
  `dim_run`; nenhuma métrica nova é produzida: a pinball é perda de treino
  computada pela biblioteca, nunca reportada como métrica do projeto)

## 13. Questões em aberto

Nenhuma crítica. R3 (divergência de API da biblioteca) tem mitigação por teste
de mecânica na primeira Task do adapter e não bloqueia o Technical.

## 14. Referências

- [`../../overview.md`](../../overview.md) — TFT como objeto de estudo, grade densa, hierarquia H2
- [`../../roadmap.md`](../../roadmap.md) — Stage `5.4-tft-trainer`
- [`../../domain/modeling/quantile-model-training.md`](../../domain/modeling/quantile-model-training.md) — §5 (treino do TFT), §2 (fundamentos), §7 (fronteira com a avaliação)
- ADRs desta Stage: [`../../adr/`](../../adr/) (prefixo `5_4_`)
- ADRs consumidos: 5.1.0002 (calib dedicada — estreitado por 5.4.0001),
  5.1.0001 (janela expansiva), 4.3.0001 (`target_timestamp`), 4.3.0002
  (guardrail), 4.1.0002 (formato LONG), 3.4.0002 (tipagem na spec),
  5.3.0003 (sem índice temporal absoluto), 5.3.0001 (direto por horizonte no
  GBM — assimetria consciente), 1.5.0002 (forma do `ExperimentTracker`),
  3.2.0002 (extra de ML — estreitado por 5.4.0003), 0.0.0021 (contract tests
  com oráculo), 0.0.0018 (anti-leakage inegociável)
- Issues: #57 (esta Stage), #58 (calendário na registry — piso declarado em D4)
- Externos (rastreabilidade de D1–D4; citações completas nos ADRs):
  Lim, Arık, Loeff & Pfister (2021, IJF 37(4):1748–1764); Prechelt (1998, LNCS 1524);
  Goodfellow, Bengio & Courville (2016) §7.8; Lei, G'Sell, Rinaldo, Tibshirani &
  Wasserman (2018, JASA 113(523):1094–1111); Barber, Candès, Ramdas & Tibshirani
  (2023, Ann. Statist. 51(2):816–845); Stankevičiūtė, Alaa & van der Schaar
  (2021, NeurIPS 34); Tashman (2000, IJF 16(4):437–450); Bergmeir & Benítez
  (2012, Inf. Sci. 191:192–213); Hewamalage, Ackermann & Bergmeir (2023, DMKD
  37(2):788–832); López de Prado (2018) §7.4; Raschka (2018, arXiv:1811.12808)
  §3–4; Akiba, Sano, Yanase, Ohta & Koyama (2019, KDD)
