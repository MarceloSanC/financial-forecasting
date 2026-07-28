---
title: Concept — GBM quantílico (LightGBM)
description: Baseline-modelo forte — LightGBM quantílico com um booster por (nível × horizonte), early stopping agregado na grade sobre a partição dedicada, emitindo a grade densa no mesmo grão/cohort do candidato
when-use: Consultar ao iniciar Fase 3B (technical) desta Stage; revisar antes de executar
keywords: [concept, gbm-quantile-baseline, lightgbm, quantile, pinball, booster-por-nivel, early-stopping, direct-multi-horizon]
status: done
created_at: 2026-07-19
updated_at: 2026-07-19
stage_id: 5.3-gbm-quantile-baseline
stage_title: GBM quantílico (LightGBM)
step_id: 5
step_title: Modelagem e harness de walk-forward
depends_on: [5.1-walk-forward-harness]
---

# Concept — Stage 5.3 — GBM quantílico (LightGBM)

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes. O plano executável fica no
> [`technical.md`](./technical.md). Teoria pré-registrada do GBM quantílico:
> [`quantile-model-training.md`](../../domain/modeling/quantile-model-training.md) §4 (+ §2 e §7).

## 1. Escopo

### Dentro do escopo

- Port-out **`QuantileModelTrainer`** — contrato de treino+emissão de grade
  crua de quantis por um modelo supervisionado tabular, com fronteira só de
  primitivos (`Sequence`/`Mapping`/`float`).
- Use case **`TrainGbmQuantile`** — orquestra: leitura do dataset (3.5),
  splits walk-forward (5.1), montagem de matrizes por fold, chamada do port,
  guardrail de monotonicidade (ADR 4.3.0002), dedup operationally-latest,
  registro em `dim_run` e persistência em `fact_oos_predictions` via
  `PersistPredictions` (4.3), com `model_version='gbm_quantile'`.
- Adapter **`LightgbmQuantileTrainer`** — única fronteira do BC com
  `lightgbm`/`numpy`: um booster independente por (nível × horizonte),
  seleção da iteração ótima pela pinball média da grade na partição
  `early_stop`, predição truncada nessa iteração.
- Fake in-memory do port + suite de contrato (fake ↔ real), testes unit,
  integração e e2e via `wire_dependencies`.
- `lightgbm` em `dependencies` + gate import-linter
  `modeling-no-lightgbm-leak` com prova de quebra intencional.

### Fora do escopo (explicitamente)

- **NGBoost** (cogitado no roadmap) e **tuning agressivo** de
  hiperparâmetros — não-objetivos declarados no roadmap §5.3. Os
  hiperparâmetros de estrutura/regularização são fixos e pré-registrados
  nos **defaults da lib** (§7-D6); a única exceção é o teto
  `num_boost_round_max=500`, decisão do mecanismo de parada (ADR 5.3.0002),
  não tuning.
- **Persistência de artefato de modelo e logging MLflow** — o DoD da 5.3
  exige apenas predições persistidas; artefato+MLflow entram com o TFT (5.4)
  e a orquestração confirmatória (5.5).
- **Métricas de avaliação** (pinball como métrica reportada, DM/MCS,
  calibração) — Step 6. A pinball aparece aqui **só** como critério interno
  de parada, computada pela própria lib (nenhuma fórmula de avaliação é
  implementada nesta Stage).
- **Re-treino confirmatório com seeds × folds** — Stage 5.5.
- **Sweeps exploratórios (Optuna)** — Stage 5.4.

### Vínculo com o roadmap

Stage `5.3-gbm-quantile-baseline` do Step 5 (BC `modeling`, camada multi
`application + adapters/out`, `depends_on: [5.1]` — `done`). É o
baseline-**modelo** da hierarquia H2 (overview §3): mais forte que os
baselines estatísticos da 5.2, comparador direto do candidato TFT (5.4).
Consome os contratos declarados no roadmap: `WalkForwardSplitter` (5.1),
`FeatureRegistry` (3.4), `MultiHorizonPredictionPersister` (4.3).

## 2. Objetivo da Stage

Ao fechar esta Stage, o cohort AAPL terá predições quantílicas out-of-sample
de um gradient boosting quantílico (LightGBM, CPU) persistidas em
`fact_oos_predictions` com `model_version='gbm_quantile'`, na **mesma grade
densa de níveis**, no **mesmo grão** (`target_timestamp` por indexação de
sessões) e no **mesmo cohort** dos baselines da 5.2 — treinado sob o harness
da 5.1 com early stopping na partição dedicada e reprodutível por seed.

## 3. Contexto e premissas

### Contexto

O doc de domínio §4 fixa a mecânica: no LightGBM, `objective` é um enum
escalar e `alpha` um único double — não existe modo multi-quantil nativo
(verificado contra o repositório oficial em 2026-07: feature requests
abertos #2302/#5727, sem implementação). Uma grade de K níveis exige K
boosters independentes; sem acoplamento entre níveis, os quantis previstos
podem cruzar, e a correção é o rearranjo monótono (guardrail `sorted()` do
ADR 4.3.0002) — **não** `monotone_constraints`, que atua sobre features de
entrada.

O que o doc de domínio **não** fixa — e esta Stage decide (com o humano,
sessão de 2026-07-19) — é o recorte multi-horizonte (§7-D1), o critério de
parada (§7-D2), o conjunto de features (§7-D3) e a forma do port (§7-D4).

### Premissas

- O dataset `processed/dataset_tft` do asset do escopo está materializado
  (Stage 3.5) com `target_return` (retorno log backward de 1 dia,
  ADR 3.5.0001), as features da registry, `day_of_week`/`month` e
  `timestamp` tz-aware.
- `lightgbm >= 4.7` instala como wheel pré-compilado (~3.5 MB) no ambiente
  de CI/dev; `libgomp` presente na imagem (risco R2 se não).
- O fit em CPU dos K×H boosters por fold cabe no orçamento de tempo do CI
  com os tamanhos de teste (ceiling de iterações baixo nos testes).

### Dependências

- `5.1-walk-forward-harness`: `WalkForwardSplitter` + `FoldSplit`
  (partição quádrupla com `early_stop` dedicada — consumida aqui pela
  primeira vez), `ScopeSpec`, `SplitFingerprint`, dedup
  `deduplicate_operationally_latest`.
- `4.3-prediction-persister` (via `done` transitivo): `PersistPredictions`,
  `QuantileForecast.from_raw` (guardrail), `MultiHorizonPredictionPersister`
  (dono do `target_timestamp`).
- `3.4-feature-registry-and-derived`: `list_feature_specs` como fonte
  canônica do conjunto e da ordem das features (§7-D3).
- `3.5-dataset-builder-and-contracts`: layout físico do dataset lido via
  `MedallionStore.read` (par read-only `processed/dataset_tft`).

## 4. Contratos

### Introduzidos

- **`QuantileModelTrainer`** (`port-out`) — contrato de treino e emissão da
  grade crua por fold. Fronteira só com primitivos/`collections.abc`; NaN
  (`float('nan')`) é o marcador de valor ausente nas matrizes.

  ```python
  GridByHorizon = Mapping[int, tuple[float, ...]]  # reuso do alias da 5.2

  @dataclass(frozen=True)
  class GbmTrainingParams:
      seed: int
      num_boost_round_max: int = 500   # teto do D2 (não é default da lib): generoso de propósito, m* trunca
      num_leaves: int = 31             # default da lib
      learning_rate: float = 0.1       # default da lib
      min_data_in_leaf: int = 20       # default da lib

  @dataclass(frozen=True)
  class QuantileTrainingResult:
      grids: Mapping[int, GridByHorizon]           # decision_idx -> horizon -> grade crua
      best_iteration_by_horizon: Mapping[int, int]

  class QuantileModelTrainer(Protocol):
      def train_and_predict(
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
      ) -> QuantileTrainingResult: ...
  ```

  Semântica: para cada horizonte `h` (chaves dos mapas de labels), treinar
  um booster por nível τ com os pares de treino cujo label é finito;
  monitorar a pinball por iteração na partição `early_stop`; selecionar
  `m*_h` = argmin da **média da pinball sobre os níveis da grade**,
  convertido para **contagem 1-based de árvores** (`m*_h` = índice do
  argmin no histórico **+ 1**, com asserção `m*_h >= 1` — em
  `predict(num_iteration=0)` o LightGBM usa TODAS as árvores, então o
  off-by-one silenciaria o truncamento); emitir, para cada linha de teste,
  a grade crua predita com `num_iteration=m*_h`. A grade emitida é
  **crua** — pode cruzar; o guardrail é aplicado pelo use case (I3).

- **`TrainGbmQuantile`** (use case) — DTOs:

  ```python
  @dataclass(frozen=True)
  class TrainGbmQuantileCommand:
      scope: ScopeSpec
      params: GbmTrainingParams
      horizons: tuple[int, ...]
      quantile_levels: tuple[float, ...]
      n_folds: int
      test_size: int
      val_size: int
      calib_size: int
      embargo: int
      schema_version: int

  @dataclass(frozen=True)
  class GbmRunSummary:
      run_id: str
      model_version: str          # 'gbm_quantile'
      fold_index: int
      rows_written: int
      rows_skipped: int
      best_iteration_by_horizon: Mapping[int, int]

  @dataclass(frozen=True)
  class TrainGbmQuantileResult:
      runs: tuple[GbmRunSummary, ...]
  ```

### Consumidos

- **`WalkForwardSplitter`** / **`FoldSplit`** / **`ScopeSpec`** — Stage 5.1.
- **`MedallionStore.read`** (par read-only `processed/dataset_tft`) — 2.1/3.5.
- **`list_feature_specs`** (FeatureRegistry) — Stage 3.4.
- **`PersistPredictions`** / **`QuantileForecast`** — Stage 4.3.
- **`AnalyticsRepository`** (escrita de `dim_run`) + **`RunRecord`** — 4.1/4.2.
- **`Hasher`** (run_id/config_signature) — Stage 1.4.
- **`deduplicate_operationally_latest`** — Stage 5.1.

## 5. Invariantes e regras

- **I1 — alinhamento do label:** o par de treino do horizonte `h` na decisão
  `t` é (features conhecidas em `t`, `target_return[t+h]`) — retorno de
  **um** dia realizado na sessão `t+h`, indexado por posição no array de
  sessões (ADR 4.3.0001), nunca por timedelta. Nenhuma regra √h se aplica
  (doc de domínio §2.1).
- **I2 — anti-leakage:** features em `t` só carregam informação ≤ `t`
  (garantido pela 3.5); labels de treino alcançam no máximo
  `partition_end + max_horizon`, que o gap `max_horizon + embargo` do
  harness (5.1) mantém estritamente antes do início da partição seguinte —
  o monitor de early stopping nunca vê informação de `calib`/`test`.
- **I3 — grade crua no port, guardrail no use case:** o port emite valores
  possivelmente cruzados; `QuantileForecast.from_raw` (rearranjo CFG 2010,
  ADR 4.3.0002) é aplicado por (decisão × horizonte) antes de persistir —
  simetria exata com a 5.2.
- **I4 — determinismo:** com a mesma seed, mesmo dataset e mesmo comando, o
  fluxo inteiro emite predições idênticas (params LightGBM
  `deterministic=true`, `force_row_wise=true`, sem subamostragem; seleção de
  `m*` é argmin determinístico com desempate pela menor iteração).
- **I5 — um booster por (nível × horizonte):** nenhum acoplamento entre
  níveis nem entre horizontes (ADR 5.3.0001); K×H boosters por fold.
- **I6 — `early_stop` monitora, `calib` intocada:** a seleção de `m*_h` usa
  exclusivamente a partição `early_stop` do fold (papel desenhado no ADR
  5.1.0002); `calib` permanece reservada ao conformal (Step 7).
- **I7 — identidade persistida:** `model_version='gbm_quantile'`;
  `dim_run.seed = command.params.seed` (Int64 preenchido — baselines da 5.2
  usam `None`); `fold`, `split_fingerprint`, `config_signature` e
  `parent_sweep_id` seguem o padrão da 5.2; o payload do `run_id` inclui a
  tupla ordenada de `feature_names` (auditabilidade do conjunto de
  features).
- **I8 — dedup de zero remoção:** o dedup operationally-latest com chave
  estrutural `(split, horizon, decision_idx + horizon, quantile_level)` é
  aplicado e **deve** remover zero linhas (mesma asserção da 5.2).
- **I9 — CPU:** `device_type='cpu'` fixado no adapter; nenhum código desta
  Stage toca GPU.
- **I10 — conjunto de features fixo e derivado da registry:** colunas =
  features da registry (`enabled_only=True`, ordem de inserção) +
  `day_of_week` + `month` (ordinais inteiros); excluídas: `timestamp`,
  `asset_id`, `fundamentals_effective_date`, `target_return`, `time_idx`
  (ADR 5.3.0003).
- **I11 — política de NaN:** features ausentes atravessam o port como NaN e
  são tratadas nativamente pelo LightGBM (missing handling); labels não
  finitos excluem o par **tanto do fit quanto do monitor de early stopping**
  daquele horizonte (fake e real com a mesma regra — o eval nativo do
  LightGBM converte label NaN silenciosamente em 0, corrompendo a seleção
  de `m*` com observações-fantasma; a exclusão explícita no adapter fecha
  esse canal); linhas de teste são sempre preditas (janela incompleta é
  tratada na persistência, via skip do 4.3).
- **I12 — labels do grid completo:** o use case constrói os labels sempre
  do array completo de sessões (`target_return[t+h]` existe para todo par
  de treino/early_stop porque `t+h` cai no máximo dentro do gap de purga —
  aritmética do splitter 5.1); labels **nunca** são NaN-padded na fronteira
  da partição. Consequência: nenhum par é perdido por borda (o "edge
  effect" de h−1 linhas da literatura não se aplica a este desenho).

## 6. Casos de erro e exceções

- **C1 — dataset vazio para o asset** → `ValueError` antes de qualquer
  treino (paridade com C7 da 5.2).
- **C2 — comando inválido** → `ValueError` antes de qualquer I/O:
  `horizons` vazio/duplicado/não positivo; `quantile_levels` vazio, fora de
  (0,1), não estritamente crescente; `params` fora de faixa
  (`num_boost_round_max < 1`, `learning_rate <= 0`, `num_leaves < 2`,
  `min_data_in_leaf < 1`).
- **C3 — treino insuficiente** → `ValueError` no adapter (e no fake, mesma
  regra) quando os pares de label finito de algum (nível × horizonte) ficam
  abaixo de `min_data_in_leaf` — limiar observável, paridade fake↔real via
  suite de contrato.
- **C4 — estrutura inconsistente no port** → `ValueError`: largura de linha
  ≠ `len(feature_names)`; comprimento de labels ≠ nº de linhas;
  `test_decision_indices` com comprimento ≠ nº de linhas de teste;
  `early_stop` vazio (sem monitor não há seleção de `m*`).
- **C5 — grade emitida não finita** → `ValueError` no adapter: NaN/inf na
  predição nunca é emitido silenciosamente (paridade com C5 da 5.2).
- **C6 — colunas esperadas ausentes do dataset** → `ValueError` nomeando as
  colunas faltantes (registry × dataset drift, risco R4).
- **C7 — rerun idêntico** → `DuplicateKeyError` propaga do
  `AnalyticsRepository` (append-only; semântica de replay é desenho da 5.5,
  finding herdado da 5.2).

## 7. Decisões técnicas relevantes

### D1 — Multi-horizonte direto: um booster por (nível × horizonte)

- **O quê:** para h ∈ {1, 7}, treinar conjuntos independentes de boosters
  com o label deslocado para `t+h`; sem recursão, sem `horizon` como
  feature.
- **Por quê:** horizontes não adjacentes tornam a recursão estruturalmente
  inviável (exigiria simular o vetor de features em t+1..t+6); com H=2 o
  custo do direto não pesa. Custo do direto declarado e aceito: variância
  por isolamento de horizonte. (O "edge effect" de h−1 linhas da literatura
  **não se aplica** aqui — I12: labels vêm do grid completo dentro do gap
  de purga, nenhum par é perdido.)
- **Fonte:** pergunta B1 respondida na sessão (2026-07-19); doc de domínio
  §2.1.
- **ADR:** [`5_3_0001-direct-per-level-horizon-boosters.md`](../../adr/5_3_0001-direct-per-level-horizon-boosters.md)

### D2 — Early stopping: iteração única por (fold × horizonte), pinball média da grade

- **O quê:** treinar cada booster até `num_boost_round_max` **sem** callback
  de parada; registrar o histórico por iteração da pinball (métrica nativa
  `quantile`, no α do próprio booster) sobre `early_stop`; `m*_h` = argmin
  da média dos históricos dos K níveis; predizer `test` com
  `num_iteration=m*_h`.
- **Por quê:** a parada por booster individual é vulnerável à patologia
  documentada (LightGBM #4870: parada na iteração 1 com objetivo quantílico
  e validação pequena, sem correção desde 2021) e à escassez de amostra
  efetiva nos níveis extremos (τ·n ≈ 4 no nível 0.02 com val ≈ 200);
  o teto fixo desperdiçaria a partição dedicada. A média na grade agrega
  ~K× mais sinal e é paralela à loss do TFT (soma da pinball na grade,
  Lim et al. 2021 Eq. 24) — comparabilidade candidato × comparador.
- **Fonte:** pergunta B3 respondida na sessão (2026-07-19); ADR 5.1.0002.
- **ADR:** [`5_3_0002-grid-mean-early-stopping.md`](../../adr/5_3_0002-grid-mean-early-stopping.md)

### D3 — Feature set: registry + calendário ordinal, sem `time_idx`

- **O quê:** I10. Calendário (`day_of_week`, `month`) entra como inteiro
  ordinal; `time_idx` excluído.
- **Por quê:** árvores são constantes por partes e não extrapolam — sob
  walk-forward expansivo todo índice temporal de teste está fora do range de
  treino por construção (discriminação zero out-of-sample, memorização
  in-sample). Calendário entra por **paridade com o TFT** (known covariates,
  ADR 3.4.0002), não por expectativa de efeito (literatura de anomalias de
  calendário: efeito atenuado/desaparecido pós-1980 em large caps).
- **Fonte:** pergunta B4 respondida na sessão (2026-07-19).
- **ADR:** [`5_3_0003-feature-set-no-time-idx.md`](../../adr/5_3_0003-feature-set-no-time-idx.md)

### D4 — Forma do port: matriz densa em linhas + `feature_names`

- **O quê:** `rows: Sequence[Sequence[float]]` + `feature_names` com ordem
  canônica; retorno espelha o `Mapping[decision_idx, GridByHorizon]` da 5.2.
- **Por quê:** simetria com o precedente `BaselineForecaster` (fronteira só
  de primitivos, gate de leak trivialmente verde); no volume do piloto
  (~540 mil valores) a diferença de eficiência entre os formatos é
  desprezível — variante colunar com `array.array` registrada como
  alternativa equivalente, não adotada.
- **Fonte:** pergunta B2 respondida na sessão (2026-07-19); docstring §8 do
  `run_baselines.py` (5.2).

### D5 — `lightgbm >= 4.7, < 5.0` em `dependencies` principais

- **O quê:** dependência core (não extra), pin por minor, lock no mesmo
  commit.
- **Por quê:** precedente F-T2 da 5.2 (statsforecast): a perna real da suite
  de contrato e a prova de quebra do import-linter rodam no CI; wheel de
  ~3.5 MB não justifica extra (o extra `sentiment` existe para libs de
  centenas de MB, ADR 3.2.0002). O piso 4.7 importa: corrige o cálculo de
  percentil da folha com pesos (fix #7224) — abaixo disso, objetivo
  quantílico com `sample_weight` é silenciosamente incorreto.
- **Fonte:** §7 do technical da 5.2 (F-T2); release notes LightGBM 4.7.0.

### D6 — API nativa `lgb.train` + bloco de reprodutibilidade

- **O quê:** usar `lightgbm.train` (Booster API) com
  `{objective='quantile', alpha=τ, deterministic=True, force_row_wise=True,
  seed, num_threads fixo, device_type='cpu', feature_fraction=1.0,
  bagging desabilitado, verbosity=-1}`; hiperparâmetros de estrutura/
  regularização nos defaults da lib (`num_leaves=31`, `learning_rate=0.1`,
  `min_data_in_leaf=20`), pré-registrados em `GbmTrainingParams` — zero
  tuning; o teto `num_boost_round_max=500` é decisão do D2 (ADR 5.3.0002),
  não default da lib.
- **Por quê:** o wrapper sklearn exigiria o extra `lightgbm[scikit-learn]`;
  a API nativa dá `valid_sets` + `record_evaluation` + `num_iteration` na
  predição — exatamente o mecanismo do D2. Sem subamostragem, a iteração de
  parada é determinística (LightGBM #5758 afeta apenas fluxos com bagging).
- **Fonte:** doc oficial de parâmetros do LightGBM; não-objetivo "tuning
  agressivo" (roadmap §5.3).

### D7 — Sem artefato de modelo e sem MLflow nesta Stage

- **O quê:** nenhum booster é serializado; nenhum run é logado no MLflow.
- **Por quê:** DoD da 5.3 exige apenas predições persistidas; artefato e
  tracking entram no TFT (5.4, que declara `ExperimentTracker`) e na
  orquestração (5.5). `best_iteration_by_horizon` retorna no Result para
  auditabilidade imediata; a reprodutibilidade vem de I4 (dado + comando).
- **Fonte:** roadmap §5.3 vs §5.4 (contratos consumidos); skill
  project-scope-principles (anti-overengineering).

## 8. Integrações

### Internas (com outras Stages/módulos)

- `modeling.application → analytics_store.application` (`PersistPredictions`,
  `AnalyticsRepository`, `RunRecord`): fronteira cross-BC já sancionada na
  5.2 (docstring §8 do use case).
- `modeling.application → feature_engineering.domain` (`list_feature_specs`):
  consumo declarado no roadmap (FeatureRegistry, 3.4); import
  application→domain cross-BC permitido pelos contratos de camadas.
- `composition_root`: novo campo `train_gbm_quantile` em
  `ApplicationDependencies`, com proxy lazy
  (`_LazyLightgbmQuantileTrainer`) no padrão do
  `_LazyStatsforecastBaselineForecaster`.

### Externas

- **LightGBM (>= 4.7, < 5.0):** consumido exclusivamente pelo adapter
  `features/modeling/adapters/out/lightgbm/`; contrato de uso: objetivo
  `quantile` com `alpha` escalar, `valid_sets` + `record_evaluation` para
  históricos, `predict(num_iteration=m*)` para truncar. Gate
  `modeling-no-lightgbm-leak` reprova vazamento para application/domain.

## 9. Modelo de dados

Nenhum schema novo. Reusa `silver/fact_oos_predictions` (formato LONG por
nível, ADR 4.1.0002) e `silver/dim_run` (upsert por `run_id`), com
`model_version='gbm_quantile'` e `seed` preenchido (primeiro produtor com
seed não nula — o caminho nullable `Int64` foi corrigido na 5.2).

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| R1 — tempo de treino no CI (K×H boosters × folds) | M | M | ceiling de iterações baixo nos testes (`num_boost_round_max` pequeno); dataset sintético mínimo; sem marker `slow` a menos que medição prove necessário |
| R2 — `libgomp` ausente na imagem (wheel exige em runtime) | B | A | verificar import no início da Task do adapter; fallback: instalar `libgomp1` no Dockerfile (deviation documentada) |
| R3 — histórico de avaliação da lib não expõe a métrica `quantile` como esperado (nome/forma) | B | M | Task do adapter valida o mecanismo com teste de mecânica (histórico não vazio, comprimento = iterações); fallback: regredir à Alternativa B do ADR 5.3.0002 (`num_boost_round` fixo pré-registrado, partição ociosa documentada como deviation) — **não** computar pinball manualmente, o que violaria o escopo declarado em §1 (nenhuma fórmula de avaliação nesta Stage) |
| R4 — drift registry × colunas do dataset (feature esperada ausente) | B | A | C6: validação nominal das colunas antes do treino, erro nomeando faltantes |
| R5 — folha em nível extremo instável com `early_stop` pequena | M | B | informativo, não defeito: seleção de `m*` agrega a grade (D2); leitura de calibração é papel do Step 6 |

## 11. Critérios de aceitação

- [ ] A1 — `QuantileModelTrainer` e `TrainGbmQuantile` existem com as
  assinaturas de §4 e passam `make check` (mypy strict, layout,
  import-linter).
- [ ] A2 — para cada fold e horizonte, o adapter treina K boosters
  (`objective='quantile'`, `alpha=τ_k`) e emite a grade completa por decisão
  de teste, alinhada 1:1 a `quantile_levels` (suite de contrato, pernas
  fake e real).
- [ ] A3 — `m*_h` é selecionado pelo argmin da média dos históricos de
  pinball dos K níveis sobre `early_stop`, convertido para contagem
  1-based (`m*_h >= 1` assertado), com desempate pela menor iteração;
  predições de teste usam `num_iteration=m*_h`; o mapeamento índice→
  iteração é provado por caso em que o ótimo conhecido é a **iteração 1**
  (truncamento observável — off-by-one detectado); `calib` não é lida pelo
  use case nem pelo adapter (I6) — verificado por teste de invariância à
  mutação dos valores de `calib`.
- [ ] A4 — predições persistidas em `fact_oos_predictions` com
  `model_version='gbm_quantile'`, guardrail aplicado por (decisão ×
  horizonte), `target_timestamp` por indexação de sessões (via 4.3), e
  `dim_run` com `seed` preenchida — teste de integração com store real em
  `tmp_path`.
- [ ] A5 — determinismo: duas execuções com o mesmo comando, cada uma
  contra um store isolado (tmp_path próprio — evita o `DuplicateKeyError`
  do append-only, C7), produzem predições e `best_iteration_by_horizon`
  idênticos; na fronteira do port, duas chamadas idênticas produzem grades
  idênticas (fake e real).
- [ ] A6 — oráculo de emissão: com features constantes (nenhum split
  possível), a predição do adapter real colapsa no quantil empírico tipo 7
  dos labels de treino — comparado a `sample_quantiles_type7` do domínio
  com tolerância absoluta 1e-6, justificada: o `lgb.Dataset` armazena
  labels em float32, então desvios ~1e-8–1e-7 são esperados por
  quantização (ADR 0.0.0021 — tolerância declarada e justificada; medido
  ~1.6e-8 no probe do checkpoint A).
- [ ] A7 — anti-leakage do label: teste prova que o label de treino usa
  `target_return[t+h]` (mutação `t+h-1`/`t` detectada) e que nenhum label de
  treino/early_stop referencia sessão ≥ início da partição seguinte.
- [ ] A8 — casos de erro C1–C7 cobertos por testes dedicados (C3/C4/C5 nas
  duas pernas da suite de contrato).
- [ ] A9 — gate `modeling-no-lightgbm-leak` ativo, registrado em
  `_EXPECTED_CONTRACTS`, com prova de quebra intencional revertida
  (saídas literais no relatório).
- [ ] A10 — e2e: `TrainGbmQuantile` executado via `wire_dependencies` de
  ponta a ponta (dataset seed → predições no parquet), CPU-only.
- [ ] A11 — coverage ≥ 90% em cada arquivo tocado da Stage.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? (§4)
- [x] Toda decisão em §7 tem fonte rastreável? (perguntas B1–B4 da sessão,
  docs citados)
- [x] Toda integração externa tem contrato definido? (§8 — LightGBM com
  parâmetros e mecanismo declarados)
- [x] Decisões com alternativa real descartada têm ADR escrito?
  (D1→5.3.0001, D2→5.3.0002, D3→5.3.0003; D4–D7 seguem precedente/escopo,
  sem alternativa viva)
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)?
  (5.1 `done`; 3.4/3.5/4.3 `done` transitivos)
- [x] Stage cabe em ~3–8 Tasks? (estimativa: 7–8)
- [x] Riscos críticos têm mitigação plausível? (§10)
- [x] Nenhuma métrica nova é produzida? (canal de emissão existente —
  `fact_oos_predictions`; pinball interna ao treino, computada pela lib,
  nunca reportada como métrica do projeto)

## 13. Questões em aberto

Nenhuma crítica. (R3 tem fallback definido; não bloqueia Technical.)

## 14. Referências

- [`../../overview.md`](../../overview.md) — hierarquia H2, grade densa
- [`../../roadmap.md`](../../roadmap.md) — Stage `5.3-gbm-quantile-baseline`
- [`../../domain/modeling/quantile-model-training.md`](../../domain/modeling/quantile-model-training.md) — §2 (fundamentos), §4 (GBM), §7 (fronteira)
- ADRs desta Stage: [`../../adr/`](../../adr/) (prefixo `5_3_`)
- ADRs consumidos: 4.3.0001 (target_timestamp), 4.3.0002 (guardrail),
  5.1.0002 (partição calib dedicada), 5.1.0003 (fingerprint), 3.4.0002
  (tipagem known/unknown), 0.0.0021 (contract tests com oráculo)
- Externos (rastreabilidade das decisões D1–D3; citações completas nos ADRs):
  Ben Taieb & Atiya (2016, IEEE TNNLS); Ben Taieb, Huser, Hyndman & Genton
  (2016, IEEE Trans. Smart Grid); Chernozhukov, Fernández-Val & Kaji (2016,
  arXiv:1612.06850) §3.2.3; LightGBM issues #4870/#5758 e Parameters.rst;
  scikit-learn User Guide §1.10 (árvores não extrapolam); Schwert (2003,
  Handbook ch. 15); Robins & Smith (2016, CFR); Plastun et al. (2019, NAJEF)
