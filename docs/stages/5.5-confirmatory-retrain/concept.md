---
title: Concept — Stage 5.5 — Re-treino confirmatório do cohort AAPL
description: Orquestração do cohort confirmatório AAPL sobre dado real — pré-requisitos (leitura única do dataset com corte do aquecimento, gravação atômica no silver), sweeps exploratórios simétricos isolados do OOS, congelamento+hash do cohort com âncora publicada, e re-treino retomável do candidato TFT (seeds × folds), do GBM e das 5 baselines
when-use: Consultar ao iniciar a Fase 3B (technical) da Stage 5.5; revisar antes de executar ou de mudar a composição/identidade do cohort confirmatório, a leitura do dataset de treino ou a regra de cegamento
keywords: [concept, confirmatory-retrain, cohort, seeds, folds, sweep, freeze, hash, blinding, resumable, materialization, cli, warmup, nan, atomic-write, tft, gbm, baselines]
status: done
created_at: 2026-09-26
updated_at: 2026-09-27
stage_id: 5.5-confirmatory-retrain
stage_title: Re-treino confirmatório do cohort AAPL
step_id: 5
step_title: Modelagem, baselines e treino
depends_on: [5.2-baselines-naive-statistical, 5.3-gbm-quantile-baseline, 5.4-tft-trainer]
---

# Concept — Stage 5.5 — Re-treino confirmatório do cohort AAPL

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.
>
> **Stage é a unidade de ciclo concept→technical→execução.** Sobre
> hierarquia (Step → Stage → Task) e critérios de atomicidade, ver
> [`PIPELINE.md`](../../PIPELINE.md) §4.

## 1. Escopo

### Dentro do escopo

**Pré-requisitos em Stages fechadas** (achados do Checkpoint A; decisão do
humano de mantê-los nesta Stage — issue #102, 2026-09-27):

- **Leitura única do dataset de treino** (absorve a issue #99): as 4 cópias de
  `_load_dataset` (`run_baselines.py`, `train_gbm_quantile.py`, `train_tft.py`,
  `run_tft_sweep.py`) viram um ponto único, com teste de caracterização antes.
- **Corte das linhas sem valor** nesse ponto único: todos os modelos treinam e
  decidem sobre o **mesmo grid**, começando na primeira linha em que todas as
  colunas de modelagem (features habilitadas, calendário e `target_return`) são
  finitas (D11).
- **Gravação atômica no silver**: `ParquetAnalyticsRepository` passa a gravar
  cada partição por arquivo temporário + `os.replace` (D12).

**Máquina do cohort:**

- **Arquivo de cohort versionado** (`config/cohorts/aapl_confirmatory.toml`),
  congelado e hasheado, com revisão, proveniência dos sweeps e âncora publicada
  antes do `run` (D1, D3).
- **Sweeps exploratórios simétricos**: TFT **e** GBM, mesmo orçamento de trials,
  na geometria do fold 0, que não toca nenhuma observação pontuada pelo
  confirmatório (D2, D13). O port de busca deixa de ser exclusivo do TFT.
- **Use case `RunConfirmatoryCohort`**: TFT em seeds × folds, GBM em uma
  execução por fold (D4), 5 baselines — chamando os use cases existentes,
  **retomável** por unidade com verificação por contagem (D5).
- **Runner executável**: `materialize` (sequencia ingestão ×3 → `BuildDataset`)
  no ponto de entrada da raiz; `sweep` e `run` no adapter CLI do slice modeling
  (D10).

**Execução real:**

- Materialização do dado AAPL, medições (grid útil, NaN interior, custo), sweeps,
  congelamento, publicação da âncora e corrida confirmatória completa, com
  **regra de cegamento** (D14): esta Stage reporta **só contagens**.
- **Prova de determinismo do GBM** (teste de contrato "duas seeds → predições
  idênticas").
- **Runbook** reprodutível e **roadmap** (DoD da 5.5, mudanças pedidas pela
  #78 no PR #98).

### Fora do escopo (explicitamente)

- **Métricas, testes pareados, agregação entre seeds e pré-registro** — Step 6.
  Nenhuma métrica é calculada sobre o cohort nesta Stage (D14).
- **Horizonte h+30** — fora do cohort por decisão do humano (2026-09-26);
  corrida suplementar em issue própria.
- **Outros ativos** — non_goals do roadmap.
- **Redesenho da PK do silver para reaproveitar run entre cohorts**
  (ADR 5.2.0004 D5) — avaliado e não implementado (registrado na #99).
- **Chave de alinhamento OOS como value object** (#64, itens 1–3): o dedup
  continua **por use case**, sem buffer único entre modelos; um buffer
  compartilhado colapsaria predições de modelos diferentes pela chave de 4
  campos (comentário na #102). Leitores do Step 6 devem ler por `run_id`.
- **Tracking MLflow do GBM e das baselines** e **artefato de modelo do GBM**
  (5.3 D7): o GBM é determinístico (D4) — as predições persistidas e o
  `gbm_params` congelado reproduzem o modelo; o ledger registra o resumo de cada
  unidade. Sem consumidor para MLflow/artefato não-TFT.
- **Troca do oráculo de `test_build_dataset_aapl.py`** por lista de colunas
  versionada — `[finding]` com issue própria (R4); nesta Stage o dado do cohort
  fica num `data_root` isolado para não tornar o teste vácuo.

### Vínculo com o roadmap

Fecha o Step 5 (`docs/roadmap.md`, Stage `5.5-confirmatory-retrain`): produz o
insumo do Step 6 — predições OOS alinhadas por `target_timestamp` do candidato e
de todos os comparadores, sob um único `parent_sweep_id` de cohort congelado.
Materializa as premissas de overview §3/§4 (candidato único all-features, zero
seleção por OOS) e a disciplina do doc de domínio
[`quantile-model-training.md`](../../domain/modeling/quantile-model-training.md)
§5.4 e §6.

## 2. Objetivo da Stage

Ao fechar esta Stage, o silver contém as predições OOS do cohort confirmatório
AAPL — candidato TFT em todas as seeds × folds, GBM e 5 baselines em todos os
folds, todos sobre o mesmo grid de decisão — sob um `parent_sweep_id` que
carrega o hash de um arquivo de cohort publicado **antes** da execução, com
nenhuma métrica calculada, e um único comando reproduz a corrida (ou a retoma
do ponto em que parou).

## 3. Contexto e premissas

### Contexto

- Os três treinadores (5.2, 5.3, 5.4) existem, testados com dado sintético; cada
  chamada percorre **todos os folds** de uma configuração; a seed vive nos
  `params` (TFT, GBM) e é nula nas baselines.
- Não existe `data/` neste checkout nem runner executável: `main.py` só sobe a
  API; os use cases de ingestão não estão no composition root.
- O sweep exploratório (5.4) **nunca rodou sobre dado real**. Decisão do humano:
  roda nesta Stage; o GBM (zero tuning na 5.3) ganha sweep simétrico (B3).
- `RunTftSweep` treina no **último** fold da geometria recebida
  (`run_tft_sweep.py:185`); com janelas expansivas, esse fold contém os testes
  dos folds anteriores. Tratado em D2.
- **As linhas de aquecimento são NaN no dataset** (ADR 3.5.0002 mantém o NaN no
  armazenamento). O maior `warmup_count` do registry é 252
  (`revenue_yoy_growth`/`net_income_yoy_growth`, `feature_registry.py:611,620`),
  contado a partir do primeiro relatório as-of (fundamentals começam em 2010-03),
  então o prefixo esperado é de ~300–330 linhas — medido na materialização. O
  `TimeSeriesDataSet` do pytorch-forecasting recusa NaN
  (`_timeseries.py:128-146`, conferido na imagem `financial_forecasting-app:dev`).
  O adapter do TFT fatia o frame a partir da linha 0 (`pf_tft_trainer.py:412-448`),
  então todo treino do TFT falharia; o LightGBM aceita NaN e treinaria sobre
  outro conjunto. Tratado em D11.
- **A gravação Parquet não é atômica**: `_write_partition` lê, concatena e chama
  `pq.write_table` no próprio caminho (`parquet_analytics_repository.py:109-112,
  226-250`); `fact_oos_predictions` tem um arquivo por ano com linhas de todas
  as unidades. Tratado em D12.

### Medição do dado bruto (skill `data-shape-evidence`, 2026-09-26)

Arquivos do projeto anterior montados **read-only** em `/app/data` no container
(`docker compose run --rm --no-deps -v <old>/data:/app/data:ro app …`):

| Arquivo | Linhas | Período | Adapter atual lê? |
|---|---|---|---|
| `raw/market/candles/AAPL/candles_AAPL_1d.parquet` | 4024 | 2010-01-04 → 2025-12-31 | sim |
| `raw/news/AAPL/news_AAPL.parquet` | 6921 | 2010-01-05 → 2025-12-31 | sim |
| `processed/fundamentals/AAPL/fundamentals_AAPL.parquet` | 81 (17 `reported_date` NaT; 1 linha sem valores) | 2010-03 → 2025-12 | sim |

- `pytest tests/integration/features/market_data/adapters/out/parquet` com o
  dado montado: **12 passed, 0 skipped** → importar como está, sem remodelar.
- O `dataset_tft` antigo tem **4023 × 30** colunas; o registry atual produz
  55 features + 7 colunas base/cauda = **62**; com o arquivo antigo montado,
  `test_build_dataset_aapl.py` falha (`assert 30 == 62`). **O `dataset_tft`
  antigo não é importado** (R4).
- O pipeline real até o dataset precisa do extra `sentiment` (`transformers`),
  ausente no venv do container.

### Premissas

- **P1.** Os arquivos brutos do projeto anterior são a fonte do dado real (não
  há ingestão ao vivo: Alpha Vantage exige chave inexistente no `.env`).
- **P2.** O custo em CPU é compatível com o cohort — **medido** antes das
  decisões [P] (D8). Isto **diverge** do overview ASSUM-2 e do ADR 5.4.0003, que
  previam o ambiente confirmatório em ROCm; a divergência foi apresentada no
  alinhamento (#102) e é registrada aqui. Se o custo medido inviabilizar o
  cohort, a Stage **para** e o humano decide com o número (ROCm exige mudar o
  adapter, que fixa `accelerator="cpu"` em `pf_tft_trainer.py:325,523`).
- **P3.** A janela de falha parcial difere por tipo de unidade: o TFT treina
  todos os folds antes de escrever (`train_tft.py:309-397`); o GBM grava
  `dim_run` dentro do laço de treino (`train_gbm_quantile.py:255-282`) e as
  baselines por spec (`run_baselines.py:221-301`) — nelas uma falha de treino
  deixa `dim_run` órfão (upsert, sem predições), que D5 trata como retentável.
- **P4.** O conteúdo do dataset materializado (inclusive o sentimento do FinBERT
  em CPU) é estável **na mesma máquina e ambiente**; reproduzir em outra máquina
  pode mudar a impressão digital e exige nova revisão do cohort (D3).

### Dependências

- `5.1-walk-forward-harness`: `WalkForwardSplitter` — geometria
  `TRAIN | gap | early_stop | gap | calib | gap | TEST`, testes ladrilhados a
  partir do fim da grade, `gap = max_horizon + embargo`.
- `5.2`: `RunBaselines`, `BaselineSpec.canonical_five`.
- `5.3`: `TrainGbmQuantile`, `GbmTrainingParams`.
- `5.4`: `TrainTft`, `RunTftSweep`, `HyperparameterSearch` (ask-and-tell).
- `4.2`: `ParquetAnalyticsRepository`, schemas `dim_run`/`fact_oos_predictions`.
- `3.5` `BuildDataset`; `2.2/2.3` ingestão; `1.4` `Hasher` e VOs de identidade.

## 4. Contratos

### Introduzidos

- **`CohortHash`** (`value-object`, `shared/domain/value_objects/cohort_hash.py`)
  — única chamada de `hash_mapping` para o cohort (regra 6 do `check_layout`:
  identidade só pelos VOs de `shared/domain/value_objects/`; precedente
  ADR 5.2.0004).
  ```python
  @dataclass(frozen=True)
  class CohortHash:
      value: str
      @classmethod
      def compute(cls, *, hasher: Hasher, payload: Mapping[str, object]) -> "CohortHash": ...
  ```
- **`DatasetContentFingerprint`** (`value-object`, `shared/domain/value_objects/`)
  — impressão digital do **conteúdo** do dataset de treino já cortado:
  `hash_mapping` sobre `{asset, columns: [nomes em ordem], timestamps: [ISO-8601],
  values: {coluna: [floats]}}` das colunas de modelagem, com o arredondamento a
  10 casas do `CanonicalJsonHasher` (diferenças abaixo de 1e-10 não mudam o
  hash — declarado). Independe dos bytes do Parquet (versão do pyarrow,
  metadados). Coexiste com o `DatasetFingerprint` da 1.4 (soma de close/volume +
  hash do arquivo), que não serve ao dataset de treino (sem `close`/`volume`) e
  segue sem consumidor; LAYOUT §7 passa a listar o VO novo.
- **Payload hasheável:** `CohortSpec.hash_payload()` converte cada dataclass
  (`TftTrainingParams`, `GbmTrainingParams`, `SearchDimension`, `BaselineSpec`,
  `CohortGeometry`) em dict por `dataclasses.asdict`, só com tipos que o hasher
  aceita (str, int, float finito, bool, None, list, dict).
- **`CohortGeometry`** (`value-object`, `modeling/domain/value_objects/cohort_geometry.py`)
  ```python
  @dataclass(frozen=True)
  class CohortGeometry:
      n_folds: int; test_size: int; val_size: int; calib_size: int; embargo: int
      def exploratory(self) -> "CohortGeometry": ...      # n_folds=1, test_size=n_folds*test_size (D2)
      def expected_prediction_rows(self, *, fold_index: int, horizons: tuple[int, ...],
                                   n_levels: int) -> int: ...  # base da verificação por contagem (D5)
  ```
- **`usable_start`** (`domain-service`, `modeling/domain/services/`) — regra
  pura: índice da primeira linha em que todas as colunas pedidas são finitas;
  NaN **interior** (depois dessa linha) é erro com a contagem por feature (D11).
- **Leitura única do dataset de treino** (`modeling`, forma decidida no
  technical sob LAYOUT §3/§5) — lê `("processed", "dataset_tft")` via
  `MedallionStore`, filtra o ativo, ordena, aplica `usable_start` sobre o
  **conjunto fixo de colunas de modelagem** — todas as features habilitadas do
  registry, as de calendário e `target_return` (hoje é o mesmo conjunto que GBM
  e TFT consomem: `train_gbm_quantile.py:198-206`, `train_tft.py:181-205`) — e
  devolve as linhas mais a `DatasetContentFingerprint` dessas colunas. O
  conjunto não depende do cohort, então nenhum comando das Stages fechadas muda.
  Substitui as 4 cópias; comportamento observável preservado fora do corte (teste
  de caracterização). **Mudança declarada:** as baselines, que não usam
  features, passam a começar no mesmo ponto que os modelos — o prefixo de treino
  delas encolhe (necessário para I9).
- **Extensão do port `QuantileModelTrainer` (5.3):** o resultado passa a trazer
  a perda de early_stop (pinball média na grade, na iteração escolhida —
  a mesma quantidade que o early stopping por média da grade já calcula,
  ADR 5.3.0002), e o adapter aceita `test_rows=()` (modo fit-only). É o
  objetivo do `RunGbmSweep`; sem ela o sweep não teria o que minimizar.
- **`CohortSpec`** (`dto`, `modeling/application/dtos/cohort_spec.py` —
  aplicação, porque carrega `TftTrainingParams`/`GbmTrainingParams`, que vivem
  em `application/ports/out/`)
  ```python
  @dataclass(frozen=True)
  class SweepPlan:
      tft_space: tuple[SearchDimension, ...]; tft_base_params: TftTrainingParams
      gbm_space: tuple[SearchDimension, ...]; gbm_base_params: GbmTrainingParams
      n_trials: int                                   # [P], o mesmo para os dois (B3)
      sampler_seed: int

  @dataclass(frozen=True)
  class SweepProvenance:                             # preenchido no congelamento
      tft_study_id: str; tft_best_trial: int; tft_best_objective: float
      gbm_study_id: str; gbm_best_trial: int; gbm_best_objective: float
      dataset_fingerprint: str                        # dataset sobre o qual os sweeps rodaram

  @dataclass(frozen=True)
  class CohortSpec:
      name: str; revision: int                        # revisão hasheada: remediação sem editar conteúdo
      asset_id: str; feature_set_name: str; feature_set_hash: str; pipeline_version: str
      horizons: tuple[int, ...]                       # (1, 7); max_horizon = max(horizons)
      quantile_levels: tuple[float, ...]
      geometry: CohortGeometry
      device: str                                     # "cpu" (D8)
      seeds: tuple[int, ...]                          # TFT; ordem declarada — [P]
      sweep: SweepPlan
      tft_params: TftTrainingParams | None            # congelado; seed normalizada (fora do hash)
      gbm_params: GbmTrainingParams | None            # congelado; seed única declarada
      baseline_specs: tuple[BaselineSpec, ...]
      provenance: SweepProvenance | None
      dataset_fingerprint: str | None                 # do dataset do `run`

      def is_frozen(self) -> bool: ...
      def hash_payload(self) -> Mapping[str, object]: ...   # payload canônico (tft_params sem seed)
      def cohort_id(self, cohort_hash: CohortHash) -> str: ...        # f"{name}-r{revision}-{hash[:12]}"
      def exploratory_scope_id(self, draft_hash: CohortHash) -> str: ...  # f"{name}-r{revision}-sweep-{hash[:12]}"
  ```
- **`RunGbmSweep`** (use case, `modeling/application/use_cases/run_gbm_sweep.py`)
  — espelho de `RunTftSweep` para o GBM: fit-only, objetivo na partição
  early_stop, nada gravado no silver, `phase='exploratory'` (ADR 5.4.0005).
  `SearchDimension` deixa de validar contra `TftTrainingParams` fixo: cada use
  case de sweep valida as dimensões contra o **seu** tipo de params.
- **`RunConfirmatoryCohort`** (use case, `modeling/application/use_cases/run_confirmatory_cohort.py`)
  ```python
  @dataclass(frozen=True)
  class RunConfirmatoryCohortCommand:
      spec: CohortSpec

  @dataclass(frozen=True)
  class CohortUnitOutcome:
      unit_key: str            # "baselines" | "gbm" | "tft:seed=<s>"
      status: str              # "ran" | "skipped_completed" | "verified_completed"
      run_ids: tuple[str, ...]
      rows_written: int

  @dataclass(frozen=True)
  class RunConfirmatoryCohortResult:
      cohort_id: str; cohort_hash: str
      outcomes: tuple[CohortUnitOutcome, ...]
  ```
- **Ports-out consumer-owned** (`modeling/application/ports/out/`, ADR 0.0.0053 —
  o slice consumidor define o port; `analytics_store` satisfaz por duck typing,
  sem o use case receber o `AnalyticsRepository` alheio):
  ```python
  class CohortProgressLedger(Protocol):         # JSON atômico (D5)
      def acquire_writer(self, *, break_stale: bool = False) -> None: ...   # lock único por data_root (I12)
      def release_writer(self) -> None: ...
      def completed_units(self, cohort_id: str) -> Mapping[str, Mapping[str, int]]: ...  # unit → {run_id: rows}
      def mark_completed(self, cohort_id: str, unit_key: str, rows_by_run: Mapping[str, int]) -> None: ...
      def environment(self, cohort_id: str) -> Mapping[str, str] | None: ...
      def record_environment(self, cohort_id: str, env: Mapping[str, str]) -> None: ...

  class CohortRunIndex(Protocol):               # lê dim_run + fact_oos_predictions do cohort
      def recorded_runs(self, *, asset_id: str, feature_set_name: str, cohort_id: str
                        ) -> Mapping[tuple[str, int | None], Mapping[str, tuple[str, int]]]: ...
      # (model_version, seed) → {run_id: (fold, nº de linhas de predição)}
  # Implementado por uma classe nova do analytics_store (adapter de leitura sobre
  # o repositório Parquet), sem mudar o port AnalyticsRepository.

  class RuntimeEnvironmentProbe(Protocol):      # fora do domínio/aplicação: importa as libs
      def snapshot(self) -> Mapping[str, str]: ...
      # python, torch, lightning, pytorch-forecasting, lightgbm, statsforecast, optuna,
      # numpy, pandas, pyarrow, exchange-calendars, device, torch threads, CPU,
      # e a identidade do código: hash de conteúdo git de `src/`, `uv.lock` e do
      # arquivo do cohort (`git rev-parse HEAD:<path>`) + se esses caminhos têm
      # mudança rastreada não commitada — commits só de docs não alteram o snapshot
  ```
- **Runner** — ponto de entrada fino `financial_forecasting/cli.py` (análogo a
  `main.py`; LAYOUT §2 é emendado): monta `wire_dependencies()` e expõe
  `materialize` (sequencia os use cases de ingestão e `BuildDataset`, fora de
  qualquer slice — sem aresta nova entre slices) e despacha `sweep`/`run` para
  `modeling/adapters/in/cli/` (carga por `importlib`, LAYOUT §8), que faz o
  parse do TOML (`tomllib`) para `CohortSpec` e grava o congelamento.

### Consumidos

- **`TrainTft`, `RunTftSweep`, `HyperparameterSearch`** — Stage 5.4.
- **`TrainGbmQuantile`** — Stage 5.3. **`RunBaselines`** — Stage 5.2.
- **`IngestCandles`, `IngestNews`, `IngestFundamentals`** — Stages 2.2/2.3.
- **`BuildDataset`** — Stage 3.5. **`MedallionStore`** — shared.
- **`Hasher`** — Stage 1.4.

## 5. Invariantes e regras

- **I1 — Congelado antes de rodar.** `RunConfirmatoryCohort` recusa spec sem
  `tft_params`, `gbm_params`, `provenance`, `dataset_fingerprint` ou `seeds`.
- **I2 — Hash cobre tudo o que define a corrida.** `CohortHash` sobre
  `hash_payload()`: revisão, ativo, feature set (nome **e** hash),
  `pipeline_version`, horizontes, `quantile_levels`, geometria, device, seeds,
  plano dos sweeps, HPs congelados (sem a seed do TFT, que é por unidade),
  proveniência dos sweeps e impressão digital do dataset. Mudar qualquer campo
  muda o `cohort_id`.
- **I3 — Um `parent_sweep_id` por cohort.** Toda unidade roda com
  `ScopeSpec(cohort_id=spec.cohort_id(hash), max_horizon=max(horizons))`.
- **I4 — Declarado = observado.** Antes da primeira unidade, `run` confere
  quatro igualdades: impressão digital do dataset lido = `dataset_fingerprint`;
  `provenance.dataset_fingerprint` = `dataset_fingerprint` (os HPs foram
  escolhidos no mesmo dado); `feature_set_hash()` do registry =
  `feature_set_hash`; `PIPELINE_VERSION` = `pipeline_version`. Qualquer
  divergência aborta. O dado não muda entre essa conferência e as leituras dos
  use cases porque o `run` detém o lock de escrita do `data_root` (I12).
- **I5 — Ambiente único.** Na primeira execução o `snapshot()` é gravado no
  ledger; retomada com qualquer campo diferente aborta. A identidade do código é
  o hash de conteúdo git de `src/`, `uv.lock` e do arquivo do cohort — commits
  só de documentação (runbook, §7) **não** mudam o snapshot. `run` recusa
  mudança rastreada não commitada nesses caminhos; arquivos não rastreados não
  contam (`artifacts/` passa a ser ignorado pelo git; ledger, lock e checkpoints
  vivem lá).
- **I6 — Retomada por unidade.** Unidade no ledger é pulada **depois** de
  reconferir que as contagens por `run_id` no silver batem com as do ledger; a
  marcação só acontece depois de o use case retornar.
- **I7 — Estado de unidade fora do ledger, pelo silver** (atribuição por
  `(model_version, seed)`; baselines por `model_version` com seed nula; runs
  esperados por unidade: `n_folds` para TFT e GBM, `5 × n_folds` para
  baselines): (a) sem `dim_run` → roda; (b) só `dim_run` órfão, zero predições
  → roda (upsert seguro); (c) todos os runs esperados presentes, cada um com
  `expected_prediction_rows` do seu fold (o último fold tem menos linhas: as
  últimas `h` decisões não têm alvo) → marca `verified_completed` sem treinar;
  (d) qualquer outro estado → `PartialCohortUnitError(unit_key)`.
- **I8 — Sweeps isolados do OOS.** Os dois sweeps usam
  `spec.geometry.exploratory()`; seus treino e early_stop são **idênticos** aos
  do fold 0 confirmatório; o bloco TEST exploratório (toda a cauda OOS) nunca é
  lido nem pontuado.
- **I9 — Mesmo grid para todos os modelos.** Todas as unidades e os dois sweeps
  recebem as linhas da leitura única, cortadas por `usable_start` sobre o
  conjunto fixo de colunas de modelagem (features habilitadas + calendário +
  `target_return`).
- **I10 — Zero seleção por OOS.** Nenhum campo do spec é função de predição OOS;
  os únicos insumos vindos de treino são `best_params` e o objetivo em
  early_stop exploratório dos dois sweeps (registrados em `provenance`).
- **I11 — Cegamento.** Nenhuma métrica sobre as **predições OOS** do
  `parent_sweep_id` do cohort é calculada até o hash do pré-registro da 6.5
  estar publicado; esta Stage reporta contagens de linhas e conjuntos de
  `target_timestamp`. Isentos: os diagnósticos de ajuste que o treino já emite
  (perda de early_stop por época/fold do TFT no MLflow, `best_iteration` do
  GBM) — são perdas da partição de monitoramento de cada fold, parte do
  procedimento de treino, não avaliação do cohort; não são lidos nem reportados
  nesta Stage.
- **I12 — Escritor único por `data_root`.** `materialize` e `run` adquirem o
  mesmo lock exclusivo (`O_EXCL`) no `data_root` — não por cohort —, porque os
  arquivos anuais de
  `fact_oos_predictions` são compartilhados entre cohorts e revisões e a
  gravação atômica não isola escritores concorrentes. O lock registra pid, host
  e início; lock órfão (queda) só é quebrado explicitamente
  (`--break-stale-lock`, runbook).

## 6. Casos de erro e exceções

| Caso | Comportamento | Critério |
|---|---|---|
| Spec não congelado (I1) | `CohortNotFrozenError` antes de qualquer treino | A2 |
| Declarado ≠ observado: dataset, dataset dos sweeps, `feature_set_hash` ou `pipeline_version` (I4) | `DatasetMismatchError` / `CohortDeclarationMismatchError` antes de qualquer treino | A2 |
| Ambiente ou identidade do código diverge; mudança rastreada não commitada em `src/`, `uv.lock` ou no arquivo do cohort (I5) | `EnvironmentMismatchError` antes de qualquer treino | A2 |
| Unidade em estado parcial (I7-d) | `PartialCohortUnitError(unit_key)`; nada escrito; remediação: `revision += 1` | A2 |
| Contagens de unidade concluída não batem na retomada (I6) | `CompletedUnitCorruptedError(unit_key)` | A2 |
| Lock de escrita já adquirido no `data_root` (I12) | `CohortRunLockedError` com pid/host/início do dono; `--break-stale-lock` o remove explicitamente | A4 |
| `BuildDataset` rejeitado pelo gate de qualidade no dado real (ex.: check (d) — primeiro valor não-nulo depois do aquecimento declarado, provável nos fundamentos com defasagem de publicação) | propaga o erro do gate com a feature; medido e decidido na Task de materialização | A6 |
| Falha dentro de um use case | propaga; unidade não marcada | A2 |
| Geometria não cabe no grid útil (conhecido só com o dataset) | `GeometryDoesNotFitError` com o tamanho do fold 0 | A1, A2 |
| NaN interior após o corte (D11) | `InteriorMissingValuesError` com contagem por feature | A1 |
| Todos os trials de um sweep falham | propaga C9 da 5.4 (`RunTftSweep`/`RunGbmSweep`) | A5 |
| TOML inválido (campo ausente, tipo errado, seed repetida, revisão negativa) | erro na borda nomeando o campo | A6 |
| Arquivos brutos ausentes em `materialize` | erro dos fetchers com o caminho esperado | A6 |
| Extra `sentiment` ausente em `materialize` | erro explícito com a instrução `uv sync --extra sentiment` | A6 |

## 7. Decisões técnicas relevantes

> Registro de evidência no formato da skill `evidence-resolution` §5.
> [P] = decidido pelo humano; [E]/[C] = decidido por evidência/convenção.

### D1 — Cohort em arquivo TOML versionado, lido só na borda

- **O quê:** `config/cohorts/aapl_confirmatory.toml` (não `.yaml` como o roadmap
  previa), parseado com `tomllib` pelo adapter CLI para `CohortSpec`.
- **Por quê:** [decision:C] degrau 1 — o projeto já lê TOML versionado
  (`pyproject.toml`; `scripts/arch_baseline.toml` via `tomllib`); PyYAML é só
  transitivo em `uv.lock`; degrau 5 — mais simples. Roadmap ajustado na Stage.
- **ADR:** [`5_5_0001`](../../adr/5_5_0001-frozen-hashed-cohort-spec.md)

### D2 — Sweeps na geometria do fold 0, não do último fold

- **O quê:** os sweeps recebem `CohortGeometry.exploratory()` (`n_folds=1`,
  `test_size = n_folds × test_size`, demais iguais). Como o splitter ladrilha os
  testes a partir do fim (`walk_forward_splitter.py:106-112`), o fold único tem
  treino e early_stop idênticos aos do fold 0 confirmatório; o TEST exploratório
  (toda a cauda OOS) nunca é lido (fit-only, `run_tft_sweep.py:212`).
- **Por quê:** [decision:E] — Raschka (2018, §3–4); doc de domínio §5.4. Com a
  geometria confirmatória, o último fold treinaria sobre os testes dos folds
  0..n-2. Limitação declarada: HPs escolhidos no menor treino do cohort e numa
  única HPO (Bouthillier et al. 2021, App. C.1).
- **ADR:** [`5_5_0002`](../../adr/5_5_0002-exploratory-sweep-on-fold-zero-geometry.md)

### D3 — Identidade do cohort e âncora publicada

- **O quê:** `cohort_id = f"{name}-r{revision}-{CohortHash[:12]}"`. O congelamento
  é commitado; antes do `run`: (1) tag `cohort/<cohort_id>` publicada no remoto
  apontando para o commit do congelamento; (2) comentário na issue #102 com
  `cohort_id` e hash completo (carimbo de tempo do servidor). O `run` grava no
  ledger a identidade do código (hash de conteúdo git de `src/`, `uv.lock` e do
  arquivo do cohort) e recusa mudança rastreada não commitada nesses caminhos
  (I5). A ordem que importa cientificamente
  — spec fixado antes de qualquer métrica — é garantida pelo cegamento (D14) e
  pelo pré-registro da 6.5, que prova sua data pelo mesmo tipo de âncora.
- **Por quê:** [decision:E] — congelar antes (Nosek et al. 2018); integridade por
  hash (NIST FIPS 180-4 §1); integridade ≠ anterioridade: datas do git e
  `created_at` do silver são locais e retrodatáveis (Haber & Stornetta 1991); o
  comentário na issue tem carimbo do servidor e a tag sobrevive ao rebase da
  branch exigido pelo GIT-WORKFLOW. `revision` dá à remediação (I7-d) um caminho
  sem editar conteúdo. Device entra no hash (declarado); versões e identidade do
  código ficam no ledger (observados) — desvio consciente do fork (3) da #102, porque o hash
  precisa existir antes da execução e o ambiente só é observável nela.
- **ADR:** [`5_5_0001`](../../adr/5_5_0001-frozen-hashed-cohort-spec.md)

### D4 — GBM: uma execução por fold; só o TFT roda seeds × folds

- **O quê:** GBM com seed única declarada; baselines com seed nula; TFT uma
  unidade por seed.
- **Por quê:** [decision:E] — o adapter LightGBM fixa `deterministic=True`,
  `feature_fraction=1.0`, `bagging_fraction=1.0`, `bagging_freq=0`
  (`lightgbm_quantile_trainer.py:163-177`): a seed não tem onde agir; cada seed do
  TFT pareia exatamente com o único run do GBM. Prova: A3, com os `gbm_params`
  congelados do cohort. Variância de seed nula não é variância de configuração
  nula — o Step 6 declara isso ao comparar.
- **Fonte:** código citado; PR #98; issue #102.

### D5 — Retomada por unidade: ledger atômico, verificação por contagem, lock

- **O quê:** unidades `baselines` → `gbm` → `tft:seed=<s>` (baratas primeiro).
  Ledger JSON por cohort sob `artifacts_root/cohorts/<cohort_id>/`, gravado por
  temporário + `os.replace`, com `{run_id: linhas}` por unidade; lock de
  escritor único por `data_root` (`O_EXCL`, I12). Estado de unidade fora do ledger decidido por I7 com o
  `CohortRunIndex`; unidade concluída reconferida por contagem (I6).
- **Por quê:** [decision:E] — commit atômico por tarefa e reexecução só do que
  não concluiu (Dean & Ghemawat 2008, §3.3); DVC `repro` pula por hash e limpa
  saída parcial. O silver não tem deleção cirúrgica, então parcial verdadeiro
  falha fechado; órfão de `dim_run` é retentável porque `dim_run` é upsert
  (`dim_run_schema.py:60`); completa-não-marcada é reconhecida pela contagem
  esperada, derivável da geometria (por fold e horizonte: decisões de teste com
  `t+h` dentro do painel × níveis).
- **ADR:** [`5_5_0003`](../../adr/5_5_0003-resumable-cohort-units-atomic-ledger.md)

### D6 — Grade de quantis e geometria pela regra τ·n ≥ 30

- **O quê:** grade `(0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98)`; `n_folds = 6`,
  `test_size = 252`, `val_size = 252`, `calib_size = 252`, `embargo` por D7.
  OOS por horizonte = `6 × 252 − h` = 1511 (h=1) / 1505 (h=7) ≥ 30/0.02 = 1500
  (folga de 5 decisões; o corte do início não move os testes). Linhas de
  predição esperadas por run: folds 0–4 → 252 × 2 horizontes × 7 níveis = 3528;
  fold 5 → (251 + 245) × 7 = 3472; por run-set de modelo → 21.112.
- **Por quê:** [decision:C] — degrau 1: grade densa ratificada (overview §1; doc
  de domínio §2.3); degrau 2: default da lib do candidato (pytorch-forecasting
  `QuantileLoss`); regra τ·n ≥ 30 (Chernozhukov, Fernández-Val & Kaji 2016,
  §3.2.3; ADR 5.3.0002) — **transferida** de estimação para o tamanho da amostra
  de avaliação, o que se declara. Treino do fold 0 (4023 linhas, gap 14): teste
  em 2511, calib 2245–2497, early_stop 1979–2231, treino até 1965 antes do
  corte; com ~300–330 linhas de aquecimento, ~1640 úteis → τ·n_treino ≈ 33 ≥ 30.
  **Limiar de revisão (antes do
  congelamento):** a geometria é revista se, medido na materialização, o fold 0
  tiver τ·n_treino < 30 (menos de 1500 linhas úteis). **Limitações declaradas:**
  calib (252) e early_stop (252) por fold têm τ·n ≈ 5 nos extremos — afeta o
  CQR da 7.2 nesses níveis, não a avaliação. **Sensibilidade pré-registrável:**
  par 0.1/0.9 (τ·n ≫ 30) para o Step 6.
- **Alternativas:** 0.05/0.95 (neuralforecast `MQLoss(level=[80,90])`) — perde a
  cauda estudada; M5 (0.005/0.995) — τ·n = 7,5.

### D7 — Embargo igual ao horizonte máximo

- **O quê:** `embargo = max_horizon = 7`; `gap = 14`.
- **Por quê:** [decision:C] — a purga (`max_horizon`) já impede vazamento de
  rótulo, porque as partições avançam no tempo e o alvo é o retorno de um dia em
  `t+h` (ADR 4.3.0001); o embargo aqui é **folga contra dependência serial**, não
  requisito de vazamento. A recomendação de ≈1% da amostra (López de Prado 2018,
  cap. 7) protege observações de treino **posteriores** ao teste na validação
  k-fold, situação que não existe no walk-forward, e o trecho não pôde ser
  conferido (fonte paga). Degrau 4 (mais conservador que zero para o claim) com
  custo limitado: 21 linhas por fold, e o calib fica a 14 pregões do teste
  (recência do ADR 5.1.0002). `[SEM-FONTE-PRIMÁRIA]` para o valor.

### D8 — Custo medido antes das decisões [P]; CPU; cohort num único device

- **O quê:** após a materialização, mede-se o tempo de **um trial** de cada
  sweep (`n_trials=1`, fit-only, geometria exploratória — nada gravado no
  silver). Esse número ancora as decisões **[P]** do humano, tomadas antes dos
  sweeps: (a) `n_trials`, o mesmo para TFT e GBM (B3); (b) número e lista de
  seeds do TFT (5 ou 10). O diagnóstico estatístico sugerido pela #78 **não** é
  usado: exigiria pontuar o TEST exploratório, que é a cauda OOS confirmatória
  (violaria I10). `device = "cpu"` entra no hash.
- **Por quê:** compute é preferência do humano (`evidence-resolution` §1); a
  literatura não fixa N de seeds (Henderson et al. 2018; Bouthillier et al. 2021
  App. C.3; Agarwal et al. 2021 §4.1). Device único: PyTorch *Reproducibility* —
  "results may not be reproducible between CPU and GPU executions, even when
  using identical seeds". CPU em vez do ROCm previsto (overview ASSUM-2,
  ADR 5.4.0003): alternativa registrada no ADR 5.5.0001; overview e ADR 5.4.0003
  anotados em A9.
- **ADR:** [`5_5_0001`](../../adr/5_5_0001-frozen-hashed-cohort-spec.md)

### D9 — Espaços de busca

- **O quê:** TFT sobre `hidden_size`, `dropout`, `learning_rate`,
  `batch_size`, com faixas tiradas da lista de Lim et al. (2021, §6.2, p. 13),
  mapeadas para o port (que só aceita faixas `int`/`float`, sem conjunto
  categórico): state size {10…320} → `int` log [10, 320]; dropout
  {0.1…0.9} → `float` [0.1, 0.9]; learning rate {1e-4, 1e-3, 1e-2} → `float`
  log [1e-4, 1e-2]; minibatch {64, 128, 256} → `int` [64, 256]. Heads {1, 4}
  **não** é buscado — uma faixa inteira [1, 4] sortearia 2 e 3, fora do
  conjunto do paper — e fica fixo em 4 nos `tft_base_params` (valor do paper
  para a maioria dos datasets, Tabela 1). As faixas são limitadas pela escala
  do problema (uma série, ~1640 linhas no fold 0). GBM sobre `num_leaves`,
  `learning_rate`, `min_data_in_leaf`, com faixas da documentação oficial do
  LightGBM (guia de *parameter tuning*), conferidas no technical. TPE com seed
  declarada (ADR 5.4.0005).
- **Por quê:** [decision:C] degrau 3 — paper de origem / documentação oficial.
  Trecho do TFT **conferido** pelo `evidence-verifier` (Checkpoint A): "Full
  search ranges for all hyperparameters are below: State size – 10, 20, 40, 80,
  160, 240, 320; Dropout rate – 0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 0.9; Minibatch
  size – 64, 128, 256; Learning rate – 0.0001, 0.001, 0.01 … Num. heads – 1, 4";
  o paper usou random search com 60 iterações nos datasets não-volatilidade.

### D10 — Runner: raiz para `materialize`, slice modeling para `sweep`/`run`

- **O quê:** `financial_forecasting/cli.py` na raiz do pacote, ao lado de
  `main.py` e `composition_root.py` (LAYOUT §2 emendado), com `materialize`;
  `sweep`/`run` em `modeling/adapters/in/cli/`. Dado do cohort num `data_root`
  isolado (`data/cohorts/<name>/`), passado ao `wire_dependencies`.
- **Por quê:** o contrato `bc-independence` do `.importlinter` reprova aresta
  nova modeling↔feature_engineering; `materialize` precisa dos requests de
  ingestão e de `BuildDatasetRequest`, então vive fora de qualquer slice, como o
  composition root. LAYOUT §2/§6/§8; skill `orchestrator-design` (runner só
  sequencia). `data_root` isolado mantém `test_build_dataset_aapl.py` pulado em
  vez de vácuo (R4).

### D11 — Grid único: corte das linhas sem valor na leitura única

- **O quê:** a leitura única aplica `usable_start` sobre o conjunto fixo de
  colunas de modelagem (features habilitadas do registry + calendário +
  `target_return`, que o TFT também recusa com NaN): descarta o prefixo até a
  primeira linha com todas essas colunas finitas. NaN **interior** (após o
  prefixo) é
  `InteriorMissingValuesError` com a contagem por feature — medida na
  materialização; se ocorrer, a política é decidida com a medição
  (skill `data-shape-evidence`), nunca imputada em silêncio. O armazenamento do
  dataset não muda (ADR 3.5.0002).
- **Por quê:** [decision:E] — o TFT não aceita NaN (`_timeseries.py:128-146`) e o
  GBM aceita; sem regra única os modelos treinariam sobre conjuntos diferentes e
  a comparação pareada do Step 6 perderia a base comum. Cortar o **prefixo** não
  move os blocos de teste (ladrilhados a partir do fim) — só encurta os treinos.
  Onde: na leitura única, porque o concern recorre nos 4 consumidores (teste da
  solução mais direta); por isso a #99 foi absorvida (decisão do humano).
- **ADR:** [`5_5_0004`](../../adr/5_5_0004-single-training-grid-warmup-trim.md)

### D12 — Gravação atômica de partição no silver

- **O quê:** `_write_partition` grava em arquivo temporário no mesmo diretório,
  com sufixo que **não** casa com o glob de leitura
  (`<arquivo>.parquet.tmp-<pid>`; `read()` usa `**/*.parquet` e a checagem de
  vazio usa `rglob("*.parquet")`), e troca por `os.replace`; temporário
  remanescente de queda anterior é removido antes de gravar.
  Leitura-concatenação continua igual.
- **Por quê:** [decision:E] — mesmo princípio de D5 (Dean & Ghemawat 2008 §3.3):
  uma queda no meio da regravação de um arquivo anual truncaria linhas de
  unidades já concluídas, que nem o ledger nem I7 detectariam. `os.replace` é
  atômico no mesmo sistema de arquivos (documentação do Python).
- **ADR:** [`5_5_0003`](../../adr/5_5_0003-resumable-cohort-units-atomic-ledger.md)

### D13 — Sweep simétrico do GBM

- **O quê:** `RunGbmSweep` com o mesmo orçamento `n_trials` e a mesma geometria
  exploratória do TFT; objetivo = média aritmética, entre os horizontes do
  cohort, da perda de early_stop por horizonte que o port `QuantileModelTrainer`
  passa a devolver (extensão declarada em §4; por horizonte é a quantidade que o
  early stopping por média da grade já calcula, ADR 5.3.0002). [decision:C]
  degrau 5: peso igual aos horizontes declarados, espelhando o objetivo único do
  TFT (`best_val_loss`, perda média do decoder multi-horizonte);
  `SearchDimension` validada contra o tipo de params de cada use case.
- **Por quê:** [P] decidido pelo humano (B3, #102): tuning só no TFT favoreceria
  o TFT em H2 (overview §3). Comparação justa exige esforço de ajuste comparável
  (skill `dmls-ch05`, "fair comparisons").
- **ADR:** [`5_5_0002`](../../adr/5_5_0002-exploratory-sweep-on-fold-zero-geometry.md)

### D14 — Cegamento até o pré-registro da 6.5

- **O quê:** a corrida acontece nesta Stage; nenhuma métrica é calculada sobre o
  `parent_sweep_id` do cohort até o hash do pré-registro da 6.5 estar publicado.
  Esta Stage reporta só contagens (linhas por modelo/horizonte, conjunto de
  `target_timestamp`). O runbook e a DoD da 6.5 registram a regra; a 6.5 prova
  que seu pré-registro precede a primeira métrica.
- **Por quê:** [P] decidido pelo humano (B2, #102). Evita o *garden of forking
  paths* (Gelman & Loken 2014) e cumpre "pré-registro antes do confirmatório"
  (overview) no sentido que importa: antes de qualquer resultado ser visto.
- **ADR:** [`5_5_0001`](../../adr/5_5_0001-frozen-hashed-cohort-spec.md)

## 8. Integrações

### Internas

- **market_data / feature_engineering:** só via use cases montados pelo
  composition root e sequenciados no `cli.py` da raiz.
- **analytics_store:** escrita só pelos use cases de treino; leitura do cohort
  pelo port consumer-owned `CohortRunIndex`; correção de atomicidade (D12).
- **Step 6 (#77/#78, 6.2–6.5):** consome predições por `parent_sweep_id` e por
  `run_id` (não pela chave de 4 campos, #64), as seeds (S), o `cohort_hash` e a
  regra de cegamento (D14), que entra na DoD da 6.5.
- **Tracking (1.5):** TFT registra no MLflow (`phase="confirmatory_ready"`);
  sweeps com `phase="exploratory"`.

### Externas

- **Hugging Face Hub:** FinBERT na revisão fixada (ADR 3.2.0001), na primeira
  materialização.
- **GitHub:** tag `cohort/<cohort_id>` e comentário na #102 (âncora, D3) —
  operação manual do runbook, não do código.
- **Sistema de arquivos:** `data_root` isolado do cohort; `artifacts_root`
  (checkpoints, ledger, lock).

## 9. Modelo de dados

Nenhuma tabela nova no silver. Artefatos novos, fora do silver:

- `config/cohorts/aapl_confirmatory.toml` (versionado) — espelho de `CohortSpec`.
- `<data_root>/.writer.lock` (não versionado) — lock de escritor único (I12): pid, host, início.
- `artifacts/cohorts/<cohort_id>/progress.json` (não versionado) —
  `{cohort_id, cohort_hash, environment{…}, units{unit_key: {completed_at, rows_by_run{run_id: n}}}}`.

## 10. Riscos e mitigações

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| R1 — Custo em CPU inviável | M | A | D8: medir antes; parar e decidir com o número; ROCm exige mudar o adapter |
| R2 — Falha parcial deixa unidade inconsistente | B | M | I7 (órfão retentável; completa verificada por contagem; parcial falha fechado); D12 |
| R3 — Orçamento pequeno de sweep → HPs fracos | M | M | mesmo orçamento para TFT e GBM (D13); limitação declarada (D2) |
| R4 — Oráculo de `test_build_dataset_aapl.py` vácuo se o dataset for reconstruído em `data/` | A | M | `data_root` isolado (D10); `[finding]` + issue para lista de colunas versionada |
| R5 — Fold 0 curto após o corte | M | M | limiar numérico de D6, medido antes do congelamento |
| R6 — NaN interior no dataset real | M | M | D11: erro com contagem; política decidida com a medição |
| R7 — Impressão digital muda em outra máquina | M | B | P4; nova revisão; declarado no runbook |
| R8 — Stage acima do alarme (≥ 14 Tasks) | A | M | decisão do humano de mantê-la inteira (#102, B1); checkpoints por bloco |
| R9 — Gate de qualidade do `BuildDataset` rejeita o dado real (check (d) nos fundamentos com defasagem de publicação) | M | A | medido na Task de materialização; decisão com a medição (skill `data-shape-evidence`) antes de seguir |

## 11. Critérios de aceitação

- [ ] **A1 — Domínio e leitura única.** `CohortGeometry.exploratory()` produz, com o `WalkForwardSplitter` real, tuplas de treino e early_stop **iguais** às do fold 0 confirmatório; `expected_prediction_rows` bate com o persister/splitter reais em todos os folds/horizontes (3528 nos folds 0–4 e 3472 no último, na geometria do cohort); `usable_start` corta o prefixo (incluindo `target_return` na checagem) e ergue `InteriorMissingValuesError` com contagem em NaN interior; a leitura única preserva, fora do corte, o frame entregue por cada um dos 4 use cases (teste de caracterização escrito **antes** da extração) e os 4 passam a começar na mesma linha — inclusive `RunBaselines`; `GeometryDoesNotFitError` quando o fold 0 não cabe.
- [ ] **A2 — `RunConfirmatoryCohort` com fakes:** ordem baselines → GBM → TFT por seed; `ScopeSpec` com `cohort_id` do spec e `max_horizon = max(horizons)`; recusa spec não congelado; aborta em cada uma das quatro divergências de I4 e em ambiente/identidade de código divergentes (I5); I7 (a)–(d) com runs esperados por unidade, incluindo colisão da seed do GBM com uma seed do TFT e baselines de seed nula; I6 com contagem divergente → `CompletedUnitCorruptedError`; não marca unidade cujo use case falhou.
- [ ] **A3 — Determinismo do GBM:** contrato com o adapter LightGBM real e os `gbm_params` do cohort — duas seeds → predições exatamente iguais.
- [ ] **A4 — Ports novos e atomicidade:** contratos `[fake, real]` de `CohortProgressLedger` (persiste entre instâncias; falha injetada antes do `os.replace` deixa o arquivo anterior intacto; segunda aquisição do lock de escrita recusada com o dono identificado; `break_stale=True` remove lock órfão), `CohortRunIndex` (fold e contagem por `run_id` sobre silver real) e `RuntimeEnvironmentProbe` (commit só em `docs/` não muda o snapshot; mudança rastreada em `src/` muda); gravação atômica do silver com a mesma injeção de falha, e temporário remanescente ignorado pela leitura; `CohortHash` e `DatasetContentFingerprint` estáveis para o mesmo conteúdo e sensíveis a qualquer campo/valor.
- [ ] **A5 — Sweeps:** `RunGbmSweep` fit-only (`test_rows=()` aceito pelo adapter real), objetivo = perda de early_stop devolvida pelo port estendido, sem escrita no silver, `phase='exploratory'`, C9 quando todos os trials falham; `SearchDimension` validada contra o tipo de params de cada use case; os dois sweeps recebem a geometria exploratória.
- [ ] **A6 — Runner, integração:** sem `skip` (roda no CI, que instala `--extra dev`; torch é dependência core): fixture de dado bruto dimensionada (≥ aquecimento + 3 gaps + early_stop + calib + n_folds × test) com `horizons=(1, 7)`, sentimento pelo fake injetado no composition root; cobre `materialize` → `sweep` (`n_trials=1`, TFT e GBM) → congelamento → `run` → segunda execução, **com o ledger e os checkpoints já no disco**, pula tudo; TOML inválido, brutos ausentes, extra `sentiment` ausente e rejeição do gate de qualidade erguem os erros de §6.
- [ ] **A7 — Congelamento real publicado:** `config/cohorts/aapl_confirmatory.toml` com revisão, seeds e `n_trials` decididos [P], HPs e proveniência dos dois sweeps, impressão digital do dataset real; commit + tag `cohort/<cohort_id>` no remoto + comentário na #102 **antes** do `run`.
- [ ] **A8 — Corrida real completa, cega:** script de verificação (não número colado) confere no silver, por `parent_sweep_id`: para cada run-set de modelo, h=1 → 1511 × 7 = 10.577 linhas e h=7 → 1505 × 7 = 10.535 (21.112 por run-set); baselines 5 × 21.112; GBM 21.112; TFT S × 21.112; conjuntos de `target_timestamp` iguais entre modelos por horizonte; ledger com todas as unidades. Nenhuma métrica calculada.
- [ ] **A9 — Documentação:** runbook `docs/runbooks/confirmatory-cohort-aapl.md` executado de ponta a ponta nesta Stage (dado bruto, materialize, medição, decisões [P], sweeps, congelamento, âncora, run, retomada, remediação por revisão, quebra de lock órfão, cegamento); `.gitignore` com `artifacts/`; LAYOUT §2 (`cli.py`) e §7 (`CohortHash`, `DatasetContentFingerprint`) emendados; overview ASSUM-2 e ADR 5.4.0003 anotados com o desvio para CPU (D8/ADR 5.5.0001); roadmap com a DoD da 5.5 ajustada (GBM 1×fold, `.toml`, h+1/h+7, #99 absorvida), a regra de cegamento na DoD da 6.5 e as mudanças da #78 aplicadas; Stage `done`.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? — §4; forma da leitura única fica para o technical, com contrato de comportamento em A1.
- [x] Toda decisão em §7 tem fonte rastreável? — D1–D14; D7 declara `[SEM-FONTE-PRIMÁRIA]` para o valor.
- [x] Toda integração externa tem contrato definido? — HF Hub (adapter existente, revisão fixada); GitHub é operação manual do runbook.
- [x] Decisões com alternativa real descartada têm ADR escrito? — 5_5_0001 (D1, D3, D14), 5_5_0002 (D2, D13), 5_5_0003 (D5, D12), 5_5_0004 (D11).
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? — 5.2, 5.3, 5.4 `done`.
- [ ] Stage cabe em ~3–12 Tasks? — **não**: ~19 Tasks; mantida inteira por decisão do humano (#102, B1), registrada em R8.
- [x] Riscos críticos têm mitigação plausível? — §10.
- [x] Teste da solução mais direta — o corte do aquecimento recorre nos 4 consumidores do dataset, então vive no ponto único de leitura (a #99 foi absorvida em vez de tocar 4 cópias); a atomicidade é corrigida na gravação do silver (a montante) em vez de compensada no runner; a retomada fica no runner porque o concern geral (replay/PK do silver) não compensa com um único cohort (#99); o isolamento dos sweeps sai da geometria passada, sem mudar o código da 5.4.
- [x] Os sweeps não tocam dado OOS confirmatório? — I8/D2, provado em A1.
- [x] Nenhuma métrica antes do pré-registro? — I11/D14, conferido em A8.

## 13. Questões em aberto

- [ ] **[P] `n_trials` dos sweeps (o mesmo para TFT e GBM)** — humano, após a medição de custo (D8).
- [ ] **[P] Número e lista de seeds do TFT (5 ou 10)** — humano, no congelamento (D8).
- [ ] **[P] ROCm** — só se a medição de custo inviabilizar o cohort em CPU (P2).

Nenhuma bloqueia a Fase 3B: são valores do arquivo de cohort decididos na
execução, depois da Task de medição.

## 14. Referências

- [`../../overview.md`](../../overview.md) — §1, §3/§4, ASSUM-2
- [`../../roadmap.md`](../../roadmap.md) — Stage `5.5-confirmatory-retrain`, 6.5
- [`../../domain/modeling/quantile-model-training.md`](../../domain/modeling/quantile-model-training.md) — §2.3, §5.4, §6
- ADRs: [3.5.0002](../../adr/3_5_0002-regime-features-nan-warmup-dtype.md), [5.1.0001](../../adr/5_1_0001-expanding-window-walk-forward.md), [5.1.0002](../../adr/5_1_0002-dedicated-calibration-partition.md), [5.2.0004](../../adr/5_2_0004-canonical-run-identity-via-run-id-and-config-signature.md), [5.3.0002](../../adr/5_3_0002-grid-mean-early-stopping.md), [5.4.0003](../../adr/5_4_0003-torch-core-dependency-cpu-index.md), [5.4.0005](../../adr/5_4_0005-ask-and-tell-sweep-port-and-isolation.md), [0.0.0053](../../adr/0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md); desta Stage: `5_5_0001`–`5_5_0004`
- Issues #102 (alinhamento, medição, referências, decisões [P]), #99 (absorvida), #64 (chave de alinhamento), PR #98 (mudanças de roadmap da #78)
- Raschka, S. (2018). *Model Evaluation, Model Selection, and Algorithm Selection in Machine Learning*. arXiv:1811.12808, §3–4.
- Bouthillier, X. et al. (2021). *Accounting for Variance in Machine Learning Benchmarks*. MLSys. arXiv:2103.03098.
- Henderson, P. et al. (2018). *Deep Reinforcement Learning That Matters*. AAAI. doi:10.1609/aaai.v32i1.11694.
- Agarwal, R. et al. (2021). *Deep RL at the Edge of the Statistical Precipice*. NeurIPS. arXiv:2108.13264.
- Nosek, B. A. et al. (2018). *The preregistration revolution*. PNAS. doi:10.1073/pnas.1708274114.
- Gelman, A.; Loken, E. (2014). The statistical crisis in science. *American Scientist* 102(6).
- NIST (2015). *FIPS 180-4 Secure Hash Standard*. doi:10.6028/NIST.FIPS.180-4.
- Haber, S.; Stornetta, W. S. (1991). *How to time-stamp a digital document*. J. Cryptology. doi:10.1007/BF00196791.
- Dean, J.; Ghemawat, S. (2008). *MapReduce*. CACM 51(1). doi:10.1145/1327452.1327492.
- Chernozhukov, V.; Fernández-Val, I.; Kaji, T. (2016). *Extremal Quantile Regression*. arXiv:1612.06850.
- López de Prado, M. (2018). *Advances in Financial Machine Learning*, cap. 7.
- Lim, B. et al. (2021). *Temporal Fusion Transformers for interpretable multi-horizon time series forecasting*. IJF 37(4). arXiv:1912.09363, §6.2.
- PyTorch docs — *Reproducibility*; *HIP (ROCm) semantics*. Python docs — `os.replace`.
