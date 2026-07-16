---
title: Concept — Stage 5.2 — Baselines naive e estatísticos (5 specs emitindo a grade densa de quantis)
description: Use case RunBaselines orquestra as 5 specs de baseline pré-registradas (zero_return ≡ RW sem drift, historical_mean, AR(1) gaussiano, EWMA-vol μ=0 λ=0.94, historical_quantiles tipo 7) sob o harness walk-forward da 5.1, emitindo a mesma grade densa de quantis do candidato e persistindo via o caminho 4.3 com model_version='baseline_*'
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; revisar antes de executar as Tasks 5.2
keywords: [concept, baselines, quantile-emission, zero-return, historical-mean, ar1, ewma, riskmetrics, historical-quantiles, type-7, degenerate-grid, statsforecast, run-baselines, walk-forward, modeling]
status: done
created_at: 2026-07-15
updated_at: 2026-07-15
stage_id: 5.2-baselines-naive-statistical
stage_title: Baselines naive e estatísticos
step_id: 5
step_title: Modelagem, baselines e treino
depends_on: [5.1-walk-forward-harness]
---

# Concept — Stage 5.2 — Baselines naive e estatísticos

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.
>
> **Stage é a unidade de ciclo concept→technical→execução.** Sobre
> hierarquia (Step → Stage → Task), ver [`PIPELINE.md`](../../PIPELINE.md) §4.
>
> **Fonte teórica desta Stage:** o doc de domínio
> [`quantile-model-training.md`](../../domain/modeling/quantile-model-training.md)
> (accepted, gate do Step 5) — §3 (baselines), §2 (fundamentos), §7 (fronteira
> com a avaliação). Este concept **consome** aquele doc por referência de
> seção; nenhuma fórmula é re-derivada aqui.

## 1. Escopo

### Dentro do escopo

- **Value object `BaselineSpec`**
  (`features/modeling/domain/value_objects/baseline_spec.py`): identidade
  validada de uma spec de baseline — família canônica + parâmetros
  pré-registrados — com a fábrica das **5 specs canônicas** (doc de domínio
  §3.8; [ADR 0.0.0052](../../adr/0_0_0052-baseline-quantile-emission-conventions.md)):
  `zero_return` (≡ RW sem drift do log-preço), `historical_mean`, `ar1`,
  `ewma_vol` (λ = 0.94, μ = 0), `historical_quantiles` (tipo 7, janela rolante
  **W = 252 sessões** — decisão humana de 2026-07-15,
  [ADR 5.2.0003](../../adr/5_2_0003-historical-quantiles-window-252.md)).
- **Serviços de domínio puros de emissão/estatística de baseline**
  (`features/modeling/domain/services/`): as fórmulas pré-registradas do doc de
  domínio §3 como funções stdlib-only — grade degenerada (§3.4), conversão
  gaussiana locação-escala via `statistics.NormalDist.inv_cdf` (§3.5/§3.6),
  quantil amostral tipo 7 (§3.7), recursão de variância EWMA (§3.6, RMTD
  Eq. [5.3]) e média/variância h-step fechadas do AR(1) (§3.5) — ver §7 D1 e
  [ADR 5.2.0001](../../adr/5_2_0001-baseline-math-in-domain-statsforecast-ar1-fit.md).
- **Port-out `BaselineForecaster`**
  (`features/modeling/application/ports/out/baseline_forecaster.py`): Protocol
  que, dado `(spec, retornos, fronteira de estimação, decisões, horizontes,
  grade de quantis)`, devolve os valores crus da grade por decisão × horizonte
  — **dados** trafegam como primitivos/`collections.abc` (nunca DataFrame); o
  VO de domínio `BaselineSpec` cruza o port (precedente
  `IndicatorCalculator`/`Candle`, 3.1). Com **contract test único** (fake +
  adapter real na mesma suite — skill `pytest-with-fakes`).
- **Use case `RunBaselines`**
  (`features/modeling/application/use_cases/run_baselines.py`): orquestra —
  lê o dataset TFT via `MedallionStore`, gera folds via `WalkForwardSplitter`
  (5.1), invoca o `BaselineForecaster` por (spec × fold), aplica o guardrail
  via `QuantileForecast.from_raw` (4.3), aplica o dedup operationally-latest
  (5.1) como enforcement, registra 1 `RunRecord` por (spec × fold) em
  `dim_run` e persiste as predições LONG via `PersistPredictions` (4.3) com
  `model_version='baseline_<family>'`, `split="test"`.
- **Adapter `StatsforecastBaselineForecaster`**
  (`features/modeling/adapters/out/statsforecast/statsforecast_baseline_forecaster.py`):
  implementa o port com dispatch exaustivo pelas 5 famílias; usa
  `statsforecast` **para a estimação do AR(1)** (`ARIMA(order=(1,0,0))`,
  port do `arima` do R) e delega toda a matemática de emissão aos serviços de
  domínio (§7 D1). Dependência `statsforecast` declarada no `pyproject.toml`
  (pin por minor, postura de `exchange-calendars`/`pandas-ta-classic`).
- **Leitura do dataset TFT pelo `MedallionStore`**: expor
  `("processed", "dataset_tft")` como par legível no adapter Parquet do store
  (caminho físico já existente de `data/processed/dataset_tft/` — 3.5),
  read-only (§7 D3).
- **Registro de `modeling.{application,domain}` no contrato
  `store-no-storage-leak`** do `.importlinter` — finding escalado da 5.1
  ([`technical.md` da 5.1 §7](../5.1-walk-forward-harness/technical.md)),
  critério de aceite da issue [#51](https://github.com/MarceloSanC/financial-forecasting/issues/51),
  provado por quebra intencional revertida.
- **Ajuste do texto "6 baselines" → 5 specs no `docs/roadmap.md`**, nas DoDs
  das Stages **5.2 e 5.5** (as duas ocorrências, linhas com
  `definition_of_done`) — item de escopo desta Stage por decisão do
  [ADR 0.0.0052](../../adr/0_0_0052-baseline-quantile-emission-conventions.md)
  (Implementation notes). No mesmo retoque, a **descrição humana da 5.2**
  ("via `statsforecast`") é atualizada para refletir a decisão D1 — ex.:
  "via `statsforecast` (fit do AR(1)) + fórmulas canônicas no domínio
  validadas por oráculo (ADR 5.2.0001)" — para não ficar stale.
- **Novo contrato de fitness `modeling-no-statsforecast-leak`** no
  `.importlinter` (padrão `tracker-no-mlflow-leak`/`sentiment-no-ml-leak`):
  proíbe `statsforecast`, `numba` e `numpy` em
  `modeling.{domain,application}` (o `domain-purity` cobre numpy só no
  domain; este contrato fecha a camada application), provado por quebra
  intencional revertida.

### Fora do escopo (explicitamente)

- **GBM quantílico** (Stage 5.3) e **TFT trainer** (Stage 5.4) — roadmap
  `non_goals` da 5.2.
- **Re-treino confirmatório / cohort seeds × folds** (Stage 5.5) — aqui as
  specs rodam avulsas (`parent_sweep_id` opcional via `ScopeSpec.cohort_id`);
  o congelamento/hash do cohort é da 5.5.
- **Métricas e testes estatísticos** (Step 6) — inclusive o **gate de
  degeneração**: grades degeneradas dos baselines pontuais passam intactas
  pelo guardrail (empate não viola ordenação fraca) e são detectadas/tratadas
  só na Stage 6.1 (doc de domínio §3.4/§7; ADR 4.3.0002).
- **Qualquer tuning** de baseline (não há hiperparâmetro a buscar: toda
  convenção é pré-registrada — ADR 0.0.0052).
- **Variantes especulativas** (EWMA t-Student, quantil tipo 8) — issue
  especulativa [#48](https://github.com/MarceloSanC/financial-forecasting/issues/48),
  gatilho só após o Step 6.
- **Emissão para o split `calib`** — o conformal (7.2) consome o calib do
  **candidato** via `RunInference` (roadmap 7.2), não dos baselines; a DoD da
  5.2 exige predições alinhadas ao candidato no OOS (`test`). O comando aceita
  extensão futura barata (§4), mas nada além de `test` é emitido nesta Stage
  (skill `project-scope-principles`: não construir o que nenhuma DoD atual
  exige).
- **Naive-sobre-retornos** como sexta spec — rejeitado no ADR 0.0.0052
  (Alternative D); reintroduzível só por ADR.

### Vínculo com o roadmap

Segunda Stage do Step 5 e primeira **fatia vertical** do BC `modeling`
(domain + application + adapters/out). Entrega os **comparadores da hipótese
H2** (hierarquia de baselines — overview §3/§4) corrigindo a lacuna do projeto
antigo (baseline documentado sem implementação), na disciplina simple-first da
skill `dmls-ch05` (baseline antes do modelo). Tudo emite a **mesma grade densa
de quantis** do candidato, no mesmo grão LONG (ADR 4.1.0002) e sob o mesmo
protocolo temporal (5.1) — pré-condição do contrato com a avaliação (doc de
domínio §7: grade comum, 1 obs por `target_timestamp`, pinball pareável nível
a nível).

## 2. Objetivo da Stage

Ao fechar esta Stage, uma única invocação de `RunBaselines` produz, para as
**5 specs canônicas pré-registradas**, predições quantílicas na grade densa
comum do cohort, para todo dia de decisão dos blocos `test` do walk-forward
(5.1), alinhadas por `target_timestamp` à convenção do candidato (4.3),
monotônicas pós-guardrail, com 1 observação por ponto alinhado, persistidas em
`fact_oos_predictions` com `model_version='baseline_*'` e rastreadas em
`dim_run` — sem nenhum baseline documentado sem implementação.

## 3. Contexto e premissas

### Contexto

O doc de domínio [`quantile-model-training.md`](../../domain/modeling/quantile-model-training.md)
§3 fixa a hierarquia científica dos baselines (réguas de locação vs valor
distribucional — GKX 2020) e as **convenções de emissão pré-registradas** de
cada spec ([ADR 0.0.0052](../../adr/0_0_0052-baseline-quantile-emission-conventions.md)):

| Spec | Emissão (doc de domínio §3) | Comportamento em h |
|---|---|---|
| `zero_return` ≡ RW sem drift do log-preço | grade **degenerada** em 0 (§3.2, §3.4) | flat |
| `historical_mean` | grade **degenerada** em μ̂ da janela de treino (§3.3) | flat |
| `ar1` | paramétrico gaussiano: μ̂ + φ̂^h(r_t − μ̂) + σ̂_h·z_τ, σ̂_h fechada (§3.5) | variância cresce até a incondicional |
| `ewma_vol` | paramétrico gaussiano μ = 0: σ̂_{t+1\|t}·z_τ, λ = 0.94 (§3.6) | variância flat (RMTD [5.18]) |
| `historical_quantiles` | quantil empírico **tipo 7** da janela rolante W = 252 (§3.7; ADR 5.2.0003) | flat (incondicional) |

Pontos estruturais herdados: o alvo em h é o retorno de **um** dia realizado
em t+h — nenhuma regra √h se aplica (§2.1; ADRs 3.5.0001 + 4.3.0001); a grade
é **dado, não schema** (LONG, nível na PK — ADR 4.1.0002); o guardrail
`sorted()` corrige monotonicidade, não calibração, e **deixa passar** empates
degenerados (§2.4/§3.4; ADR 4.3.0002).

O harness 5.1 fornece o protocolo temporal (folds expansivos, purga+embargo,
partição quádrupla) e dois contratos que esta Stage consome: `ScopeSpec`
(identidade do cohort) e o dedup operationally-latest (1 obs por ponto
alinhado — doc de domínio §7 item 2).

O roadmap nomeia `statsforecast` como lib dos baselines (ratificação no
overview §6 — restrições/stack — e §7 — abordagem). A verificação da oferta
real da lib (modelos: AutoARIMA/ARIMA/
AutoRegressive, HistoricAverage, Naive, RandomWalkWithDrift, SES, GARCH/ARCH,
Theta, Croston…) mostra que **nenhum modelo dela implementa** o EWMA
RiskMetrics de λ fixo, o quantil rolante tipo 7 nem a grade degenerada em 0 —
e os intervalos dos seus modelos naive seguem a semântica √h do
nível/acumulado (FPP3 Table 5.2), **incompatível** com o nosso alvo (§2.1).
Só o AR(1) tem correspondência exata (`ARIMA(order=(1,0,0))`, port do `arima`
do R, com a variância h-step por pesos ψ — Box-Jenkins Eq. (5.1.16)). A
resolução desse conflito é a decisão D1 (§7; ADR 5.2.0001).

### Premissas

- O dataset TFT (3.5) existe em `data/processed/dataset_tft/{asset}/`, é uma
  grade densa de dias de pregão com `timestamp` e `target_return` backward
  não-nulo em toda linha (primeira linha já descartada — ADR 3.5.0001).
- O `target_return[t]` do dataset é exatamente o `r_t` das fórmulas do doc de
  domínio §3 (retorno log backward de 1 dia na sessão t).
- A grade densa de quantis (~7–9 níveis, overview §11 `0_0_0012`) chega como
  **entrada** do comando; a escolha concreta dos níveis é pré-registro do
  cohort (5.4/5.5), não desta Stage — os contratos daqui são grid-agnósticos.
- `statistics.NormalDist().inv_cdf` (stdlib, algoritmo AS241) tem precisão
  suficiente para z_τ na grade usada (validado por fixture contra valores
  tabulados no teste).

### Dependências

- `5.1-walk-forward-harness` (`done`): `WalkForwardSplitter`, `FoldSplit`,
  `ScopeSpec`, `deduplicate_operationally_latest`.
- `4.3-prediction-persister` (`done`): `PersistPredictions` (use case),
  `MultiHorizonPredictionPersister` (convenção `target_timestamp`),
  `QuantileForecast` (grade densa + guardrail).
- `4.2-silver-repository` (`done`): `AnalyticsRepository` (escrita de
  `dim_run`).
- `4.1-silver-schema-per-table` (`done`): schema LONG de
  `fact_oos_predictions`; `RunRecord`/`dim_run`.
- `2.1-medallion-store` (`done`): port `MedallionStore` (leitura do dataset).
- `1.4-identity-and-fingerprints` (`done`): `Hasher` (run_id/config_signature
  determinísticos).
- `3.5-dataset-builder-and-contracts` (`done`): o dataset TFT persistido.

## 4. Contratos

### Introduzidos

- **`BaselineSpec`** (`value-object`, frozen, stdlib-only):

  ```python
  BASELINE_FAMILIES: Final = (
      "zero_return", "historical_mean", "ar1", "ewma_vol", "historical_quantiles",
  )

  @dataclass(frozen=True)
  class BaselineSpec:
      family: str                        # uma das 5 famílias canônicas
      window: int | None = None          # W da janela rolante (historical_quantiles)
      decay_lambda: float | None = None  # λ do EWMA (ewma_vol)

      @property
      def model_version(self) -> str:    # f"baseline_{family}" → casa 'baseline_*'
          ...

      @staticmethod
      def canonical_five(*, historical_quantiles_window: int = 252) -> tuple["BaselineSpec", ...]:
          """As 5 specs pré-registradas (ADR 0.0.0052 + ADR 5.2.0003), ordem do doc §3.8.

          W = 252 sessões é a convenção pré-registrada (decisão humana
          2026-07-15, ADR 5.2.0003); o parâmetro existe só para testes/sensibilidade.
          """
  ```

  Construção valida: `family` canônica; `ewma_vol` exige
  `decay_lambda ∈ (0, 1)` (canônico 0.94) e proíbe `window`;
  `historical_quantiles` exige `window >= 20` (canônico **252** — ADR
  5.2.0003) e proíbe `decay_lambda`; as demais famílias proíbem ambos os
  parâmetros.

- **Serviços de domínio de emissão/estatística** (`domain-service`, funções
  puras stdlib-only; fórmulas por referência ao doc de domínio §3):

  ```python
  # domain/services/quantile_grid_emission.py
  def degenerate_grid(*, value: float, levels: Sequence[float]) -> tuple[float, ...]: ...
  def gaussian_grid(*, mean: float, std: float, levels: Sequence[float]) -> tuple[float, ...]: ...
      # mean + std * NormalDist().inv_cdf(tau)  — QRM Eq. (2.19), doc §3.5/§3.6
  def sample_quantiles_type7(*, values: Sequence[float], levels: Sequence[float]) -> tuple[float, ...]: ...
      # h = (n-1)p + 1 — Hyndman & Fan 1996 tipo 7, doc §3.7

  # domain/services/baseline_statistics.py
  def ewma_variance_path(*, returns: Sequence[float], decay_lambda: float) -> tuple[float, ...]: ...
      # sigma2[t] = var. prevista para t+1 dado returns[..t] — RMTD Eq. [5.3], doc §3.6
  def ar1_step_forecast(*, mu: float, phi: float, sigma2_eps: float,
                        last_return: float, horizon: int) -> tuple[float, float]: ...
      # (média, desvio) h-step fechados — Hamilton §4.2 / Box-Jenkins (5.1.16), doc §3.5
  ```

- **`BaselineForecaster`** (`port-out`, Protocol; **dados** cruzam a
  fronteira como primitivos/`collections.abc` — nunca DataFrame; o VO de
  domínio `BaselineSpec` cruza o port, como `Candle` cruza o
  `IndicatorCalculator` em 3.1):

  ```python
  GridByHorizon = Mapping[int, tuple[float, ...]]   # horizon -> valores crus da grade

  class BaselineForecaster(Protocol):
      def forecast(
          self,
          *,
          spec: BaselineSpec,
          returns: Sequence[float],          # target_return na grade densa de pregão
          train_end_idx: int,                # último índice da partição train (fronteira de estimação)
          decision_indices: Sequence[int],   # dias de decisão (bloco test), crescentes
          horizons: Sequence[int],
          quantile_levels: Sequence[float],  # grade densa comum do cohort
      ) -> Mapping[int, GridByHorizon]:      # decision_idx -> horizon -> grade crua
          ...
  ```

  Contrato semântico: parâmetros estimados **só** com
  `returns[: train_end_idx + 1]` (§7 D2); a grade crua na decisão `t` é função
  apenas de `returns[: t + 1]` (causalidade, I3); valores não-finitos **erguem**
  (C5), nunca são emitidos.

- **`RunBaselines`** (`use case`; DTOs frozen in/out — nunca entidades de
  domínio para fora da camada application):

  ```python
  @dataclass(frozen=True)
  class RunBaselinesCommand:
      scope: ScopeSpec                     # asset_id, feature_set_name, max_horizon, cohort_id
      specs: tuple[BaselineSpec, ...]      # default: BaselineSpec.canonical_five(...)
      horizons: tuple[int, ...]            # ex.: (1, 7); max(horizons) <= scope.max_horizon
      quantile_levels: tuple[float, ...]   # grade densa comum (crescente, em (0,1))
      n_folds: int
      test_size: int
      val_size: int
      calib_size: int
      embargo: int
      schema_version: int

  @dataclass(frozen=True)
  class BaselineRunSummary:
      run_id: str
      model_version: str
      fold_index: int
      rows_written: int
      rows_skipped: int

  @dataclass(frozen=True)
  class RunBaselinesResult:
      runs: tuple[BaselineRunSummary, ...]

  class RunBaselines:
      def __init__(
          self,
          *,
          store: MedallionStore,                     # leitura do dataset (shared, 2.1)
          splitter: WalkForwardSplitter,             # domínio 5.1 (construído no composition root)
          forecaster: BaselineForecaster,            # port-out desta Stage
          persist_predictions: PersistPredictions,   # use case 4.3 (analytics_store)
          analytics_repository: AnalyticsRepository, # escrita de dim_run (4.2)
          hasher: Hasher,                            # identidade determinística (1.4)
      ) -> None: ...
      def __call__(self, command: RunBaselinesCommand) -> RunBaselinesResult: ...
  ```

  Fluxo: lê `("processed", "dataset_tft")` filtrado por
  `{"asset": scope.asset_id}` → extrai `(timestamps, target_return)` →
  `splitter.split(...)` → por (spec × fold): `forecaster.forecast(...)` com
  `decision_indices` = índices do bloco `test`; monta
  `QuantileForecast.from_raw(levels, raw)` (guardrail); resolve
  `run_id = hasher(payload canônico: scope + spec + fingerprint do fold +
  horizons + levels + schema_version)`; grava 1 `RunRecord` em `dim_run`
  (`fold=str(fold_index)`, `split_fingerprint`, `seed=None`,
  `parent_sweep_id=scope.cohort_id`, `config_signature`); aplica
  `deduplicate_operationally_latest` sobre a emissão da spec com **chave
  estrutural** `(split, horizon, decision_idx + horizon, quantile_level)` —
  aritmética de inteiros sobre índices, **sem resolver timestamp** (o
  `target_timestamp` continua exclusivo do persister 4.3, I2) — rank =
  `decision_idx`, e **asserta remoção-zero**: se o dedup colapsar qualquer
  entrada (`len` antes ≠ depois), **ergue** — duplicata de ponto alinhado é
  bug de geometria a montante, nunca silenciável (I6); por fim persiste via
  `PersistPredictions` (`split="test"`, `model_version=spec.model_version`).

### Consumidos

- **`WalkForwardSplitter` / `FoldSplit` / `ScopeSpec`** — declarados em
  `5.1-walk-forward-harness` (concept 5.1 §4). O `ScopeSpec` é a identidade do
  cohort; `max_horizon` já fixa a purga que protege os horizontes daqui.
- **`deduplicate_operationally_latest`** — declarado em 5.1 (D5); aqui é
  invocado com a **chave estrutural** `(split, horizon, decision_idx +
  horizon, quantile_level)` (índices — sem resolver timestamp, I2) e rank =
  `decision_idx`, seguido da asserção de remoção-zero (I6).
- **`PersistPredictions` / `MultiHorizonPredictionPersister` / `QuantileForecast`**
  — declarados em `4.3-prediction-persister`. O persister continua **dono
  único** do `target_timestamp` (ADR 4.3.0001); janela incompleta →
  `rows_skipped` (nunca fabrica).
- **`AnalyticsRepository` / `RunRecord`** — declarados em
  `4.2-silver-repository` / `4.1-silver-schema-per-table` (escrita append-only
  de `dim_run`).
- **`MedallionStore`** — declarado em `2.1-medallion-store` (shared). Novo par
  legível `("processed", "dataset_tft")` no adapter Parquet (§7 D3).
- **`Hasher`** — declarado em `1.4-identity-and-fingerprints`
  (run_id/config_signature canônicos).

## 5. Invariantes e regras

- **I1 — Grade comum.** As 5 specs de uma mesma invocação emitem exatamente os
  mesmos `quantile_levels` (validados: estritamente crescentes, únicos, em
  (0,1)) — pré-condição da pinball pareável nível a nível (doc de domínio §7
  item 1).
- **I2 — Alinhamento por sessão.** `target_timestamp_utc =
  dataset_timestamps[decision_idx + h]` resolvido exclusivamente pelo
  persister 4.3 (indexação por dia de pregão; PROIBIDO timedelta de
  calendário — ADR 4.3.0001).
- **I3 — Causalidade da emissão.** A grade crua na decisão `t` é função apenas
  de `returns[: t + 1]` — testado por invariância a truncamento (mutar
  retornos depois de `t` não muda a previsão em `t`). Concretiza o ADR
  0.0.0018 no BC modeling.
- **I4 — Estimação congelada no train.** Parâmetros estimados (μ̂, φ̂, σ̂_ε de
  `ar1`; μ̂ de `historical_mean`) usam só `returns[: train_end_idx + 1]`;
  estado condicionante (r_t, recursão EWMA, conteúdo da janela rolante)
  atualiza causalmente até cada decisão (§7 D2; ADR 5.2.0002).
- **I5 — Monotonicidade pós-guardrail; degenerada passa.** Toda grade persiste
  via `QuantileForecast.from_raw` (rearranjo CFG 2010 na leitura discreta —
  doc §2.4); `q_low == q_high` dos baselines pontuais **não** é erro aqui
  (gate de degeneração é Step 6 — doc §3.4/§7 item 4).
- **I6 — 1 obs por ponto alinhado, com remoção-zero assertada.** O dedup usa
  a **chave estrutural** `(split, horizon, decision_idx + horizon,
  quantile_level)` (índices inteiros; o timestamp não é recomputado — I2) com
  rank = `decision_idx`. Com blocos `test` disjuntos e `t + h` injetivo em
  `t` por horizonte, **nenhuma** duplicata pode existir: o `RunBaselines`
  asserta `len(antes) == len(depois)` e **ergue** se o dedup remover qualquer
  entrada (colapso silencioso mascararia o bug de geometria que ele existe
  para detectar); empate de rank já ergue no próprio serviço (5.1 I9).
- **I7 — 5 specs, dispatch exaustivo.** `BaselineSpec.canonical_five()` ↔
  famílias implementadas no adapter, verificado por teste (parametrizado sobre
  `BASELINE_FAMILIES`); família desconhecida ergue. "Nenhum baseline
  documentado sem implementação" vira propriedade testada, não convenção.
- **I8 — Pureza de camadas, com fitness function.** `modeling.domain`
  continua stdlib-only (`domain-purity`); `modeling.{application,domain}`
  entram em `store-no-storage-leak` (pandas/pyarrow/duckdb/pandera
  proibidos) **e** no novo contrato `modeling-no-statsforecast-leak`
  (`statsforecast`/`numba`/`numpy` proibidos — padrão
  `tracker-no-mlflow-leak`/`sentiment-no-ml-leak`); essas libs vivem só em
  `adapters/out/statsforecast/`. Ambos provados por quebra intencional
  revertida.
- **I11 — Grade comum entre execuções: dono nomeado (fronteira).** Os
  `quantile_levels` entram como **input da config do cohort** (os contratos
  desta Stage são grid-agnósticos e apenas validam/propagam); quem **congela**
  a grade entre candidato, GBM e baselines é o cohort da **5.5** (DoD "cohort
  congelado e hasheado" — o hash deve incluir `quantile_levels`); quem
  **valida** a igualdade de grade no pareamento é o **Step 6** (doc de
  domínio §7 item 1). Esta Stage garante I1 dentro da execução; a garantia
  entre execuções tem esses dois donos.
- **I9 — Determinismo.** Baselines não têm semente: mesma entrada → mesmas
  linhas, byte a byte (`seed=None` no `RunRecord`); `run_id` é hash canônico
  reprodutível (1.4).
- **I10 — Rastreabilidade.** Toda linha de `fact_oos_predictions` referencia
  um `run_id` registrado em `dim_run` na mesma execução, com
  `split_fingerprint` do fold e `config_signature` da spec.

## 6. Casos de erro e exceções

- **C1 — Janela insuficiente ergue.** `historical_quantiles` com menos de
  `window` retornos disponíveis até a decisão, ou partição `train` menor que o
  mínimo para estimar `ar1`/`historical_mean` → `ValueError` (**erguer, não
  fabricar** — ADR 0.0.0018 alt. B; espelha 5.1 §6 "janela insuficiente").
- **C2 — Comando inválido ergue.** `quantile_levels` não crescentes/fora de
  (0,1); `horizons` vazio, não positivo ou `max(horizons) >
  scope.max_horizon`; specs duplicadas (mesmo `model_version`) →
  `ValueError` antes de qualquer I/O.
- **C3 — Spec inválida ergue na construção.** Família fora do canônico,
  parâmetro obrigatório ausente ou parâmetro proibido presente →
  `ValueError` no `__post_init__` (invariante verificada, não assumida).
- **C4 — Fit degenerado ergue.** `ar1` com |φ̂| ≥ 1, σ̂²_ε ≤ 0 ou coeficiente
  não-finito → erro do adapter (fail-fast; um AR(1) não estacionário em
  retornos diários é sintoma de dado ruim, não caso a acomodar). Como o
  contrato público do adapter real dificilmente produz esse estado, o fit da
  lib fica atrás de um **seam testável** — wrapper fino injetável/
  monkeypatchável (`_fit_ar1(returns) -> (mu, phi, sigma2_eps)`) — para o
  teste exercitar C4 com um fit forjado.
- **C5 — Emissão não-finita ergue.** NaN/Inf em qualquer valor cru da grade →
  erro do adapter antes do VO (o pass-through defensivo do `QuantileForecast`
  existe para modelos ML; num baseline determinístico, não-finito = bug).
- **C6 — Janela de predição incompleta pula, não fabrica.**
  `IncompletePredictionWindowError` do persister → linha pulada e contada em
  `rows_skipped` (comportamento herdado do use case 4.3, C1/I4 de lá).
- **C7 — Dataset ausente/vazio ergue.** `read` devolvendo vazio para o
  `asset` do escopo → `ValueError` explícito no use case (não há o que
  prever; silêncio mascararia configuração errada).
- **C8 — Colisão de PK propaga.** `DuplicateKeyError` no write não é
  capturado (reprocessamento consciente é decisão do caller — postura 4.3 C5).
- **C9 — Empate no dedup ergue.** Herdado de 5.1 (ambiguidade de "mais
  recente" é bug de geometria).

## 7. Decisões técnicas relevantes

> Cada decisão tem fonte rastreável; as três com alternativa real descartada
> viram ADR (prefixo `5_2_`).

### D1 — Matemática pré-registrada no domínio puro; `statsforecast` confinado à estimação do AR(1)

- **O quê:** as fórmulas de emissão do doc de domínio §3 (grade degenerada,
  conversão gaussiana, tipo 7, recursão EWMA, formas fechadas h-step do AR(1))
  são **serviços de domínio stdlib-only** (z_τ via
  `statistics.NormalDist.inv_cdf`); o adapter usa `statsforecast`
  (`ARIMA(order=(1,0,0))`, port do `arima` do R) **apenas** para estimar
  (μ̂, φ̂, σ̂²_ε) do `ar1`, e despacha as 5 famílias delegando a emissão ao
  domínio. Cada unidade é validada contra **oráculo** (fixture analítica +
  lib independente: `numpy.quantile` para o tipo 7, `pandas.ewm` para a
  recursão EWMA, recuperação de parâmetros em série sintética + fixture
  fechada para o AR(1), z_τ tabulado para a NormalDist).
- **Por quê:** o roadmap diz "via statsforecast", mas a verificação da lib
  mostra que ela **não implementa** as convenções pré-registradas (sem EWMA
  RiskMetrics de λ fixo, sem quantil rolante tipo 7, sem grade degenerada; os
  intervalos dos modelos naive seguem √h do nível — semântica incompatível
  com o alvo de 1 dia, doc §2.1). A âncora resolve: a **fórmula
  pré-registrada é o contrato** (doc §3 + ADR 0.0.0052); a metodologia
  estatística do projeto é "domínio puro testável apoiado em bibliotecas
  reconhecidas validadas contra oráculo" (overview §1/§7); e onde não existe
  lib canônica da unidade, a postura é implementação própria fina + oráculo
  (ADR 0.0.0021, rejeição da Alternative B). `statsforecast` permanece onde
  ratificado (overview §6/§7) e onde é fiel à convenção (AR(1)).
- **Fonte:** overview §1/§6/§7; doc de domínio §3; ADRs 0.0.0021 e 0.0.0052;
  verificação da oferta do statsforecast (docs oficiais Nixtla, 2026-07-15).
- **ADR:** [`../../adr/5_2_0001-baseline-math-in-domain-statsforecast-ar1-fit.md`](../../adr/5_2_0001-baseline-math-in-domain-statsforecast-ar1-fit.md)

### D2 — Parâmetros congelados no train por fold; estado condicionante causal até a decisão

- **O quê:** por fold, os parâmetros estimados usam só a partição `train`
  (fronteira `train_end_idx`); o **estado** que as fórmulas condicionam
  (r_t do AR(1), recursão σ̂²_{t+1|t} do EWMA, conteúdo da janela rolante)
  avança causalmente até cada dia de decisão do bloco `test`. Sem re-fit por
  origem dentro do test.
- **Por quê:** é o **mesmo protocolo de informação** do GBM/TFT (pesos
  congelados no train, entradas observadas até a decisão) — comparação justa
  de H2 exige protocolo idêntico no cohort (overview §3/§7; skill
  `project-scope-principles`, lente 3); o harness define `train` como região
  de estimação e a purga protege exatamente essa fronteira (concept 5.1
  §4/§5); e as próprias fórmulas do doc §3 condicionam em r_t na decisão (a
  recursão EWMA é definida sobre o retorno do dia). Re-fit por origem
  (Tashman 2000) é protocolo defensável, mas quebraria a simetria com os
  modelos ML e o significado do `split_fingerprint`.
- **Fonte:** doc de domínio §2.5/§3.5/§3.6/§5.4 (Raschka); concept 5.1 §4–§7;
  overview §7.
- **ADR:** [`../../adr/5_2_0002-frozen-train-estimation-causal-state.md`](../../adr/5_2_0002-frozen-train-estimation-causal-state.md)

### D3 — Dataset lido pelo `MedallionStore` com par read-only `("processed", "dataset_tft")`

- **O quê:** `RunBaselines` lê o dataset TFT pelo port compartilhado
  `MedallionStore.read` com `filters={"asset": ...}`; o adapter Parquet ganha
  o par **read-only** `("processed", "dataset_tft")` resolvendo o caminho
  físico já existente (`data/processed/dataset_tft/{asset}/dataset_tft_{asset}.parquet`,
  escrito pela 3.5).
- **Por quê:** direção já registrada no projeto — o finding da 5.1 aponta o
  `MedallionStore` como o caminho quando a application do `modeling` nascer, e
  a issue #51 amarra o registro no `store-no-storage-leak` a esse consumo. Um
  port dedicado (`DatasetSource`) duplicaria a fronteira de storage para o
  mesmo dado sem ganho para nenhuma DoD atual. A extensão é read-only e não
  toca a semântica de escrita bronze do store.
- **Fonte:** technical 5.1 §7 (finding `modeling.application`); issue #51
  (critérios de aceite); ADR 0.0.0022 (DuckDB como engine de leitura). (Sem
  ADR próprio — decisão derivada de direção já registrada.)

### D4 — `historical_mean` na janela de treino expansiva; `ewma_vol` com semente numericamente irrelevante

- **O quê:** `historical_mean` usa μ̂ da **partição train inteira** do fold
  (janela de treino, expansiva); a recursão EWMA inicializa em
  σ̂²₁ = r₁² na primeira sessão do dataset e roda até a decisão.
- **Por quê:** o doc §3.3 diz literalmente "média amostral dos retornos da
  janela de treino" — a janela de treino do protocolo é a partição `train`
  (5.1, expansiva por ADR 5.1.0001). Para o EWMA, qualquer convenção de
  semente decai como λⁿ (0.94ⁿ < 10⁻¹³ para n > 500); com o train ancorado em
  `sessions[0]` e blocos test na cauda de ~4000 pregões, a escolha **não muda
  número reportado** — logo não é convenção a pré-registrar (critério do ADR
  0.0.0052), apenas a documentar. σ̂²₁ = r₁² é a semente mais simples e sem
  parâmetro novo.
- **Fonte:** doc de domínio §3.3/§3.6; ADR 5.1.0001; ADR 0.0.0052 (critério
  "muda número reportado"). (Sem ADR — sem alternativa material.)

### D5 — Emissão só para `split="test"`; `run_id` por (spec × fold)

- **O quê:** as predições persistem com `split="test"`; cada (spec × fold)
  ganha `run_id` próprio (hash canônico 1.4) e uma linha em `dim_run` com o
  `split_fingerprint` do fold, `fold=str(fold_index)`, `seed=None` e
  `parent_sweep_id=scope.cohort_id`.
- **Por quê:** o contrato com a avaliação é sobre o OOS pareado (doc §7); o
  conformal 7.2 consome o calib **do candidato** via `RunInference` (roadmap
  7.2 `contratos_consumidos`), não dos baselines — emitir calib aqui seria
  construir sem DoD (skill `project-scope-principles`). O grão (spec × fold)
  do `run_id` espelha o `RunRecord` (4.1: `fold`, `split_fingerprint` por
  linha) e mantém cada fato auditável até o fold que o produziu.
- **Fonte:** doc de domínio §7; roadmap §Stage 7.2; VO `RunRecord`
  (`run_record.py`); ADR 4.1.0002. (Sem ADR — derivação de contratos
  existentes; reversível por parâmetro de comando.)

### D6 — Janela rolante do `historical_quantiles`: W = 252 sessões (decisão humana, fork F1)

- **O quê:** o baseline `historical_quantiles` calcula os quantis tipo 7
  sobre os **252 últimos retornos de pregão** (~1 ano) disponíveis até cada
  decisão. Fixado como convenção pré-registrada na fábrica
  `canonical_five(historical_quantiles_window=252)`.
- **Por quê:** o doc de domínio §3.7 fixa o estimador (tipo 7) e o caráter
  "janela rolante", mas não a largura — e W muda os números reportados
  (mesmo critério do ADR 0.0.0052 → pré-registro obrigatório). W = 252 é o
  piso da convenção regulatória de Historical Simulation (framework de risco
  de mercado de Basel, observação mínima de ~250 dias úteis), casa com a
  nota "n ≳ 250" do ADR 0.0.0052 (região onde tipo 7 ≈ tipo 8) e mantém a
  reatividade a regime que o contraste com o EWMA condicional pressupõe.
  Alternativas rejeitadas: W = 500 (mais estável, sem âncora citável, lenta
  a regime) e janela expansiva (zero parâmetro, mas contradiz o "rolante" do
  doc §3.7 e apaga o contraste da hierarquia). **Decisão humana (Marcelo),
  2026-07-15** — resolução do fork F1 deste concept.
- **Fonte:** doc de domínio §3.7; ADR 0.0.0052 (nota n ≳ 250); QRM §2.3.2
  (Historical Simulation); decisão de sessão 2026-07-15.
- **ADR:** [`../../adr/5_2_0003-historical-quantiles-window-252.md`](../../adr/5_2_0003-historical-quantiles-window-252.md)

## 8. Integrações

### Internas (com outras Stages/módulos)

- **`modeling.domain` (5.1):** `WalkForwardSplitter` injetado no use case já
  construído no composition root (o construtor recebe **só** o
  `TradingCalendar`; o `Hasher` é parâmetro de `split(...)`, repassado pelo
  `RunBaselines`); dedup invocado com chave/rank concretos.
- **Cross-BC `modeling.application → analytics_store.application`
  (decisão consciente e rastreada):** `RunBaselines` importa
  `PersistPredictions` (+ `Command`) e os VOs `QuantileForecast`/`RunRecord`.
  É o **primeiro import use case→use case entre BCs** do repo — o precedente
  `feature_engineering → market_data` cruza só entidade de domínio e não o
  cobre por analogia. Justificativa própria: (i) nenhum contrato do
  LAYOUT/`.importlinter` proíbe import cross-BC na mesma camada
  (`hexagonal-layers` é por container; a direção inward é preservada);
  (ii) a alternativa — `modeling` falar direto com o `AnalyticsRepository` e
  remontar as linhas LONG — **duplicaria a resolução do `target_timestamp`**,
  violando o dono único do ADR 4.3.0001 (exatamente o bug Gap 6 que o 4.3
  existe para impedir). O wiring é exclusivo do `composition_root` (regra 5
  do CLAUDE.md).
- **`shared` (2.1/1.4):** `MedallionStore` (leitura, D3) e `Hasher`
  (identidades).
- **`.importlinter`:** `modeling.{application,domain}` entram em
  `store-no-storage-leak` (finding 5.1) **e** no novo contrato
  `modeling-no-statsforecast-leak` (forbidden: `statsforecast`, `numba`,
  `numpy` — fecha na camada application o que `domain-purity` só cobre no
  domain; M1 do Checkpoint A, padrão dos contratos 5/8); `modeling` já está
  em `hexagonal-layers`/`domain-purity` — o novo diretório
  `adapters/out/statsforecast/` passa a existir sob o container.
- **Testes de contrato do port (skill `pytest-with-fakes`):** suite única
  `tests/contract/features/modeling/test_baseline_forecaster_contract.py`
  parametrizada sobre **fake e adapter real**, cobrindo as invariantes do
  port: causalidade por truncamento (I3), congelamento de parâmetros (I4) e
  recusa de emissão não-finita (C5).
- **`docs/roadmap.md`:** ajuste "6 baselines" → "5 specs de baseline
  (zero_return ≡ RW sem drift)" nas DoDs 5.2 (linha do
  `definition_of_done`, que também diz "triplet degenerado" → "grade
  degenerada") e 5.5; **e** retoque da descrição humana da 5.2 — "via
  `statsforecast`" → "via `statsforecast` (fit do AR(1)) + fórmulas
  canônicas no domínio validadas por oráculo (ADR 5.2.0001)" — para o texto
  não ficar stale frente à decisão D1.
- **Nota [finding] para a 5.5 (Stage candidata):** o congelamento/hash do
  cohort confirmatório (DoD 5.5 "cohort congelado e hasheado") **deve
  incluir `quantile_levels`** no payload hasheado — é o que fecha a garantia
  de grade comum **entre execuções** (I11); registrar no concept/technical
  da 5.5.
- **`pyproject.toml`:** + `statsforecast` (pin por minor; arrasta `numba` —
  ver risco em §10).

### Externas

- **`statsforecast` (Nixtla):** só no adapter; contrato usado:
  `ARIMA(order=(1, 0, 0), include_mean=True).fit(y).model_` expõe
  coeficientes e σ² (port do `arima` do R), atrás do seam `_fit_ar1` (C4).
  Validado por teste-oráculo (recuperação de parâmetros em série sintética
  com tolerância declarada) — a lib é o meio, o oráculo é a autoridade (ADR
  0.0.0021). **Desenho do oráculo:** a série sintética fixa μ ≠ 0 material e
  φ alto o suficiente para distinguir, dentro da tolerância, a **média** μ do
  **intercepto** c = μ(1−φ) da parametrização do R — desalinhamento
  média/intercepto é exatamente o bug de wiring que o oráculo deve pegar.

## 9. Modelo de dados

Nenhum schema novo — é o ponto: a grade é **dado, não schema** (ADR 4.1.0002).

- `silver/fact_oos_predictions` (4.1): +N linhas LONG por
  `(run_id, split="test", horizon, timestamp_utc, target_timestamp_utc,
  quantile_level)`, com `model_version ∈ {baseline_zero_return,
  baseline_historical_mean, baseline_ar1, baseline_ewma_vol,
  baseline_historical_quantiles}`.
- `silver/dim_run` (4.1): 1 linha por (spec × fold) — `run_id`,
  `config_signature`, `split_fingerprint`, `fold`, `seed=None`,
  `parent_sweep_id`.
- Leitura: `processed/dataset_tft` (3.5) — somente `timestamp` e
  `target_return` são consumidos.

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Emissão diverge silenciosamente da convenção pré-registrada (ex.: interpolação tipo 7 errada num nível extremo) | M | A | Oráculo por unidade (numpy.quantile / pandas.ewm / fixture fechada AR(1) / z_τ tabulado) com tolerância declarada — ADR 0.0.0021 |
| Off-by-one entre `decision_idx`, r_t condicionante e `target_timestamp` | M | A | Persister 4.3 é o dono único do alinhamento; teste de causalidade por truncamento (I3) + fixture com grade curta verificando r_t = `returns[decision_idx]` |
| `statsforecast` (numba) pesa no CI / falha de build | M | M | Pin por minor + `uv.lock`; uso confinado ao AR(1) — fallback barato (trocar a estimação por implementação própria + oráculo) sem tocar port/domínio (ADR 5.2.0001) |
| `statsforecast` sem stubs quebra mypy strict | A | B | Wrapper fino tipado no adapter com fronteira `float`/tuplas; ignore localizado e comentado |
| Loops stdlib no domínio lentos demais (~4k sessões × ~800 decisões) | B | M | Recursões O(n) por caminho (`ewma_variance_path`); janela rolante O(W log W) por decisão; medido no teste de integração — se estourar, mover o cálculo para o adapter numpy mantendo o domínio como oráculo (reversão local, sem mudar contrato) |
| Par `("processed","dataset_tft")` read-only bagunçar a semântica do store | B | M | Entrada de registry read-only (write para o par ergue), layout físico inalterado; contract test do store cobre o novo par |
| Grade degenerada tratada como erro a montante do Step 6 | B | M | I5 explícito + teste: pontuais persistem com `q_low == q_high` e `guardrail_applied=False` |
| Amplificação de escrita: 1 `write` por decisão × spec × fold, e o adapter Parquet faz read-merge-rewrite por chamada | M | M | Aceito na escala piloto (~milhares de writes, arquivo pequeno por partição); um seam de batch no caminho 4.3 é **mudança de contrato fora do escopo** desta Stage — se doer na execução, vira `[finding]` no §7 do technical (Stage candidata: 4.x/5.5) em vez de mudança silenciosa |

## 11. Critérios de aceitação

- [ ] `BaselineSpec.canonical_five()` devolve exatamente as 5 specs
      pré-registradas (doc §3.8 / ADR 0.0.0052); spec inválida ergue (C3) —
      testado.
- [ ] `zero_return` e `historical_mean` emitem **grade degenerada** (0 e μ̂ do
      train) que atravessa o guardrail com `guardrail_applied=False` (I5) —
      testado.
- [ ] `ar1` emite μ̂ + φ̂^h(r_t − μ̂) + σ̂_h·z_τ com σ̂_h fechada (variância
      crescente em h); `ewma_vol` emite σ̂_{t+1|t}·z_τ com μ = 0, λ = 0.94
      (variância flat em h); `historical_quantiles` emite tipo 7 da janela
      rolante de 252 sessões (flat em h) — cada um validado contra **oráculo/fixture
      analítica** com tolerância declarada (ADR 0.0.0021).
- [ ] Causalidade: truncar/mutar retornos após a decisão `t` não muda a
      emissão em `t` (I3); parâmetros insensíveis a dados fora do train (I4)
      — testado.
- [ ] Predições alinhadas por `target_timestamp` (persister 4.3, único a
      resolver timestamps — o dedup usa chave estrutural de índices, I2/I6),
      persistidas em `fact_oos_predictions` com `model_version='baseline_*'`
      e `run_id` registrado em `dim_run` (I10) — teste de integração
      `RunBaselines` ponta-a-ponta com store/repositório reais em `tmp_path`.
- [ ] Enforcement de remoção-zero do dedup: com folds sintéticos
      **sobrepostos** (duplicata de ponto alinhado fabricada), o
      `RunBaselines` **ergue** em vez de colapsar silenciosamente (I6) —
      testado.
- [ ] Contract test único do `BaselineForecaster` (fake + adapter real na
      mesma suite — skill `pytest-with-fakes`) cobrindo I3/I4/C5 — verde nas
      duas implementações.
- [ ] Janela insuficiente / comando inválido / fit degenerado / emissão
      não-finita **erguem** (C1–C5); janela de predição incompleta **pula** e
      conta (C6) — testado.
- [ ] `modeling.{application,domain}` verdes em `store-no-storage-leak` **e**
      no novo contrato `modeling-no-statsforecast-leak`
      (`statsforecast`/`numba`/`numpy` proibidos fora do adapter) — ambos
      provados por quebra intencional revertida; `modeling.domain` segue
      stdlib-only (I8).
- [ ] Roadmap ajustado: "6 baselines" → 5 specs nas DoDs **5.2 e 5.5**
      (as duas ocorrências) + descrição humana da 5.2 retocada ("via
      `statsforecast` (fit do AR(1)) + fórmulas canônicas no domínio
      validadas por oráculo, ADR 5.2.0001").
- [ ] `make check` verde; coverage ≥ 90% nos arquivos da Stage; unit (specs,
      emissão, use case com fakes) + integration (`RunBaselines`, adapter
      statsforecast).

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? (§4)
- [x] Toda decisão em §7 tem fonte rastreável? (doc de domínio §3, ADRs
      0.0.0021/0.0.0052, overview §6/§7 — §11 só para a grade `0_0_0012` —,
      finding 5.1, issue #51)
- [x] Toda integração externa tem contrato definido? (statsforecast: modelo,
      chamada e oráculo — §8)
- [x] Decisões com alternativa real descartada têm ADR escrito? (D1/D2/D6 →
      5.2.0001/5.2.0002/5.2.0003)
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? (5.1,
      4.1–4.3, 3.5, 2.1, 1.4)
- [x] Stage cabe em ~3–8 Tasks? (estimativa: 8 — VO, serviços de emissão,
      serviços de estatística, port+fake+use case+contract test,
      adapter+oráculos, leitura do dataset, fitness functions
      (`store-no-storage-leak` + `modeling-no-statsforecast-leak`),
      roadmap+integração e2e)
- [x] Riscos críticos têm mitigação plausível? (§10)
- [x] A largura W da janela rolante do `historical_quantiles` foi decidida
      pelo humano? (sim — W = 252, decisão de 2026-07-15; §7 D6 / ADR
      5.2.0003 / §13)

## 13. Questões em aberto

- Nenhuma. O único fork material deste concept (**F1 — largura W da janela
  rolante do `historical_quantiles`**) foi **decidido pelo humano (Marcelo)
  em 2026-07-15: W = 252 sessões** (~1 ano de pregão), com âncora no piso
  regulatório de Historical Simulation (framework de risco de mercado de
  Basel, observação mínima de ~250 dias úteis) e na nota "n ≳ 250" do ADR
  0.0.0052. Alternativas rejeitadas (W = 500; janela expansiva) registradas
  em §7 D6 e no
  [ADR 5.2.0003](../../adr/5_2_0003-historical-quantiles-window-252.md).

## 14. Referências

- [`../../domain/modeling/quantile-model-training.md`](../../domain/modeling/quantile-model-training.md)
  — §2 (fundamentos), §3 (baselines, fórmulas e fontes primárias), §7
  (contrato com a avaliação), §8 (convenções decididas).
- [`../../roadmap.md`](../../roadmap.md) — Stage `5.2-baselines-naive-statistical`
  e vizinhas (5.1, 5.3–5.5, 7.2).
- ADRs desta Stage: [`5_2_0001`](../../adr/5_2_0001-baseline-math-in-domain-statsforecast-ar1-fit.md),
  [`5_2_0002`](../../adr/5_2_0002-frozen-train-estimation-causal-state.md),
  [`5_2_0003`](../../adr/5_2_0003-historical-quantiles-window-252.md).
- ADRs relacionados: [0.0.0052](../../adr/0_0_0052-baseline-quantile-emission-conventions.md)
  (convenções de emissão), [0.0.0021](../../adr/0_0_0021-per-unit-contract-tests-with-oracle.md)
  (oráculo por unidade), [0.0.0018](../../adr/0_0_0018-anti-leakage-non-negotiable.md)
  (erguer, não fabricar), [0.0.0022](../../adr/0_0_0022-data-engine-pandas-duckdb.md)
  (engine de leitura), [4.1.0002](../../adr/4_1_0002-fact-oos-predictions-long-quantile-format.md)
  (LONG, PK), [4.3.0001](../../adr/4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md)
  (target_timestamp), [4.3.0002](../../adr/4_3_0002-quantile-forecast-dense-grid-guardrail.md)
  (guardrail), 5.1.0001–5.1.0003 (harness).
- Stage anterior: [`../5.1-walk-forward-harness/concept.md`](../5.1-walk-forward-harness/concept.md)
  §4 (contratos consumidos) e [`technical.md §7`](../5.1-walk-forward-harness/technical.md)
  (finding `store-no-storage-leak`).
- Issue: [#51](https://github.com/MarceloSanC/financial-forecasting/issues/51).
- Externas: fontes primárias citadas no doc de domínio §9 (RMTD 1996;
  McNeil-Frey-Embrechts 2005; Hamilton 1994; Box-Jenkins 2015; Hyndman & Fan
  1996; Campbell-Lo-MacKinlay 1997; GKX 2020; Gneiting 2011; CFG 2010);
  documentação oficial `statsforecast` (Nixtla) — inventário de modelos
  verificado em 2026-07-15.
