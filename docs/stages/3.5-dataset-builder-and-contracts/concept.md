---
title: Concept — Stage 3.5 — Dataset builder e contratos
description: Integração do Step 3 — BuildDataset junta as 4 famílias sobre a grade de pregão, alvo backward log-return (dono único), validadores anti-leakage in-process, schema pandera e gate de qualidade
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; revisar antes de executar a montagem do dataset TFT e o wiring do BC feature_engineering
keywords: [concept, dataset-builder, build-dataset, target-definition, anti-leakage, pandera, quality-gate, warmup, feature-registry, as-of, composition-root, feature_engineering]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 3.5-dataset-builder-and-contracts
stage_title: Dataset builder e contratos
step_id: 3
step_title: Feature engineering e dataset
depends_on: [3.1-technical-indicators, 3.2-sentiment-finbert, 3.3-fundamentals-asof-join, 3.4-feature-registry-and-derived]
---

# Concept — Stage 3.5 — Dataset builder e contratos

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes. O plano executável fica no
> [`technical.md`](./technical.md).

## 1. Escopo

### Dentro do escopo

Esta é a **Stage de integração do Step 3** no BC `feature_engineering`. Ela
faz convergir os quatro produtos das Stages 3.1–3.4 num único dataset TFT
causal, auditável e validado:

1. **`BuildDataset`** (use case, `application`) — orquestra o join das 4
   famílias (preço+técnico 3.1, sentimento 3.2, fundamentos as-of 3.3,
   derivadas 3.4) sobre a **grade densa de dias de pregão** (`TradingCalendar`
   2.4), anexa o alvo e persiste via `MedallionStore` (2.1). Recebe e devolve
   **DTO frozen**; depende **só de ports** (Protocol). Nunca devolve entidade
   nem `DataFrame` para fora.
2. **`TargetDefinition`** (domain-service **puro**, stdlib-only) — **dono único**
   do alvo `target_return[t] = log(close_t/close_{t-1})` (convenção backward,
   primeira linha cai). Alinhado na origem com a convenção `target_timestamp`
   que a Stage 4.3 consome (`timestamp_utc = decision_day`).
3. **`dataset_schema`** (pandera, `adapters/out/parquet/schemas/`) — valida o
   `DataFrame` montado: colunas-base obrigatórias, dtypes, nullability,
   presença e ordem do set de features do `FeatureRegistry`. **Sem** regras de
   negócio (unicidade/monotonia/warmup ficam no domain gate).
4. **Validadores anti-leakage in-process** — re-derivam **cada feature** via
   `DerivedFeatures` (3.4) + indicadores canônicos (3.1) como **oráculo puro** e
   conferem contra o valor montado (tolerância float `atol ~1e-12`); divergência
   = `AntiLeakageError` (não warning). Segunda implementação independente
   (ADR 0.0.0021 / 3.4.0001), **sem** re-implementar a fórmula inline em pandas.
5. **`DatasetQualityGate`** (domain-service) — gate de qualidade warmup-aware:
   dropa linhas antes do warmup máximo do registry, mede NaN-ratio por feature
   **após** descontar o warmup de cada uma, exige timestamps únicos+monótonos e
   cobertura temporal mínima.
6. **Wiring** em `composition_root.py` — instancia os 3 adapters concretos do
   BC (`PandasTaIndicatorCalculator` 3.1, `FinbertSentimentModel` 3.2,
   `AsofJoinDuckdbAdapter` 3.3) + `BuildDataset`, expostos via
   `ApplicationDependencies` tipado pelos **ports**. **Resolve os findings F2 de
   wiring deferido** — sem isso, 3.1/3.2/3.3 seriam dead-code.

### Fora do escopo (explicitamente)

- **Treino do modelo** (Step 5) — esta Stage só monta e persiste o dataset.
- **Seleção de features** — banida por design confirmatório (overview `0_0_0003`).
- **Unificação física `IndicatorSpec` ↔ `FeatureSpec`** — deferida pela
  ADR 3.4.0002; mantemos a coexistência. 3.5 deriva set/ordem do `FeatureRegistry`
  e não toca em `IndicatorSpec` (D6).
- **Re-treino ou bit-identidade do oráculo** — o parquet em
  `data/processed/dataset_tft/AAPL/` é oráculo de **regressão por colunas/contagem**
  (4023 linhas × 62 colunas), não de bytes.
- **Commit `stage 3.5: complete` e marcar roadmap `done`** — feitos pelo
  orquestrador, pós-auditoria independente.

### Vínculo com o roadmap

Esta Stage fecha o **Step 3 — Feature engineering e dataset** ("Dataset TFT
reconstruído com features causais + contratos anti-leakage"). É o nó de
convergência `3.1, 3.2, 3.3, 3.4 → 3.5` (roadmap §grafo, linha 42) e
desbloqueia `5.1-walk-forward-harness`. Ver `roadmap.md` §Stage 3.5 e overview
§ "Modelagem e dados" (ADRs `0_0_0016`, `0_0_0018`).

## 2. Objetivo da Stage

Ao final desta Stage, executar `BuildDataset` para AAPL produz e persiste um
dataset TFT causal — 4 famílias unidas sobre a grade de pregão, alvo backward
log-return como dono único, todas as features re-derivadas e conferidas contra o
oráculo puro, schema pandera validado e gate de qualidade aprovado — com os 3
adapters do BC efetivamente wirados no composition root.

## 3. Contexto e premissas

### Contexto

As Stages 3.1–3.4 entregaram peças isoladas: `IndicatorCalculator` (3.1),
`SentimentModel` + `ScoreAndAggregateSentiment` (3.2), `FundamentalsAsofPolicy` +
`AsofJoinAdapter` (3.3) e `FeatureRegistry` + `DerivedFeatures` (3.4). As
auditorias de 3.1/3.2/3.3 deixaram findings F2 explícitos: os ports/adapters não
têm consumidor até a integração — esta Stage é esse consumidor. O monólito do
old (`build_tft_dataset_use_case.py`, 418-624) misturava montagem física,
alvo inline, validação e gate; aqui decompomos em domain-service puro (alvo,
gate), adapter (montagem pandas/duckdb) e use case (orquestração).

### Premissas

- O `FeatureRegistry` (3.4) é a **fonte única** do set e da ordem das colunas de
  feature e do warmup por feature — sem lista `FEATURE_WARMUP_BARS` paralela.
- O oráculo `data/processed/dataset_tft/AAPL/dataset_tft_AAPL.parquet` reflete o
  contrato esperado (62 colunas, ordem confirmada via pyarrow).
- `DerivedFeatures` (3.4) é numericamente correto e serve como oráculo de
  re-derivação (validado contra paper/old na própria 3.4).

### Dependências

- `3.1-technical-indicators`: `IndicatorCalculator.calculate(asset, candles)`;
  indicadores canônicos como oráculo de re-derivação.
- `3.2-sentiment-finbert`: `ScoreAndAggregateSentiment` → `DailySentimentDTO`.
- `3.3-fundamentals-asof-join`: `FundamentalsAsofPolicy.effective_date` +
  `AsofJoinAdapter.asof_join_backward`; `AntiLeakageError`.
- `3.4-feature-registry-and-derived`: `FeatureRegistry` (set/ordem/warmup/hash) +
  `DerivedFeatures` (oráculo puro).
- `2.4-trading-calendar`: grade densa de dias de pregão.
- `2.1-medallion-storage-contracts`: `MedallionStore` para persistir.

## 4. Contratos

### Introduzidos

- **`BuildDataset`** (`use case`, application) — orquestrador.
  - `BuildDatasetRequest` (DTO frozen): `asset: str`, `start: date | None`,
    `end: date | None`.
  - `BuildDatasetResult` (DTO frozen): `asset: str`, `n_rows: int`,
    `start: date`, `end: date`, `feature_set_hash: str`, `n_features: int`.
  - Nunca devolve entidade nem `DataFrame`. Depende dos ports
    `IndicatorCalculator`, `SentimentModel` (via `ScoreAndAggregateSentiment`),
    `AsofJoinAdapter` (+ `FundamentalsAsofPolicy`), `TradingCalendar`,
    `MedallionStore`; usa `FeatureRegistry` (set/ordem) e `DerivedFeatures`
    (oráculo) através do `DatasetAssembler`.

- **`TargetDefinition`** (`domain-service`, `domain/services/target_definition.py`).
  - Função **pura** stdlib-only sobre `Sequence[float]` (closes ordenados por
    timestamp) → `tuple[float | None, ...]` alinhada, com
    `target[t] = log(close_t/close_{t-1})` e `target[0] = None`.
  - **Dono único** do alvo. Convenção backward (ADR 0.0.0018 regra 5; ledger
    B-4.3). Alinha na origem com `target_timestamp` da 4.3 (`timestamp_utc =
    decision_day`).

- **`DatasetQualityGate`** (`domain-service`,
  `domain/services/dataset_quality_gate.py`) + `DatasetQualityGateConfig`
  (frozen): `max_nan_ratio_per_feature`, `require_unique_timestamps`,
  `require_monotonic_timestamps`, `min_temporal_coverage_days`. Opera sobre
  `Sequence`/`Mapping` (não `DataFrame`); lê o warmup do `FeatureRegistry`.

- **`dataset_schema`** (pandera, `adapters/out/parquet/schemas/dataset_schema.py`).
  - Colunas-base + dtypes: `asset_id=string`;
    `timestamp`/`fundamentals_effective_date=timestamp[ns, UTC]`;
    `time_idx`/`day_of_week`/`month`/`news_volume`/`has_news`/
    `volume_spike_flag=int64`; `target_return` e demais features `=float64`.
    Presença e ordem do set do registry; **sem** regra de negócio.

- **`DatasetAssembler`** (adapter, `adapters/out/pandas/dataset_assembler.py`) —
  monta o `DataFrame` (pandas/duckdb confinados) na ordem
  candles→grade→indicadores→sentimento→derivadas→as-of→derivadas-de-fundamento→
  time-features; hospeda os validadores anti-leakage in-process. Confinado a
  adapters/out.

### Consumidos

- **`IndicatorCalculator.calculate(asset, candles) -> Sequence[Mapping[str, float]]`** — Stage 3.1.
- **`ScoreAndAggregateSentiment` → `DailySentimentDTO{effective_day, sentiment_score, news_volume, sentiment_std}`** — Stage 3.2.
- **`AsofJoinAdapter.asof_join_backward(*, grid_days, reports) -> Sequence[Row]`** + **`FundamentalsAsofPolicy.effective_date`** — Stage 3.3.
- **`FeatureRegistry` (`FEATURE_SPECS`, `list_feature_specs`, `feature_set_hash`)** e **`DerivedFeatures`** — Stage 3.4.
- **`TradingCalendar`** — Stage 2.4. **`MedallionStore`** — Stage 2.1.
- **`AntiLeakageError`** (domain) — já declarado em 3.3
  (`fundamentals_asof_policy.py`); reutilizado, não redefinido.

## 5. Invariantes e regras

- **I1 — alvo:** `target = log(close_t/close_{t-1})` backward, convenção **única**,
  dono único `TargetDefinition` (domain puro). `target[0] = None`; primeira linha
  dropada na montagem; alinhamento estrito por timestamp; compatível com
  `target_timestamp` da 4.3 (`timestamp_utc = decision_day`).
- **I2 — anti-leakage in-process:** re-derivar **cada** feature com
  `DerivedFeatures` (3.4) + indicadores canônicos (3.1) e conferir contra o valor
  montado; divergência além de `atol ~1e-12` ⇒ `AntiLeakageError`. Segunda
  implementação independente (ADR 0.0.0021 / 3.4.0001); o validador **não**
  re-implementa fórmula inline em pandas — usa o oráculo puro.
- **I3 — as-of backward (defense-in-depth):** após o merge, re-checar
  `fundamentals_effective_date <= day`; coluna `effective_date` renomeada para
  `fundamentals_effective_date` no boundary e **persistida** no dataset
  (auditabilidade); violação ⇒ `AntiLeakageError`.
- **I4 — causalidade das derivadas:** anexar barras futuras não muda o prefixo;
  shifts sempre `n > 0`; janelas trailing shiftadas. Derivadas de fundamento
  computadas **depois** do as-of (YoY/ratios precisam da série diária alinhada).
- **I5 — gate de qualidade:** (a) **warmup** — dropar linhas antes do warmup
  máximo do registry e medir NaN-ratio só **após** descontar o warmup por
  feature; (b) **monotonicidade** — timestamps únicos + ordenados (erro se
  duplicado/não-monótono); (c) **missing** — NaN-ratio por feature ≤ máximo
  declarado, `failing_features` ordenado desc.; (d) cobertura temporal mínima.
- **I6 — pureza/camadas:** pandas/duckdb/pyarrow **confinados** a `adapters/out`;
  `TargetDefinition`, `DatasetQualityGate` e `DerivedFeatures` stdlib-only; use
  case depende só de ports; DTO frozen; `check_layout.py` + import-linter verdes.
- **I7 — features:** `FeatureRegistry` é a fonte **única** do set e da ordem das
  colunas de feature; `feature_set_hash` registrado no result/metadados.
  Comparar colunas/contagem (62) contra o oráculo, não bit-identidade.
- **I8 — wiring:** `composition_root.py` instancia os 3 adapters concretos do BC
  + `BuildDataset`; `ApplicationDependencies` expõe campos tipados pelos
  **ports**, não pelos concretos (I9 do composition root). Sem isso, 3.1/3.2/3.3
  são dead-code.

## 6. Casos de erro e exceções

- **C1 — alvo indefinível:** menos de 2 closes válidos ou dataset vazio após
  dropar a primeira linha ⇒ erro de domínio (`ValueError`/`DomainError`)
  com mensagem clara ("not enough rows to compute target_return").
- **C2 — divergência anti-leakage:** valor montado de uma feature difere do
  oráculo re-derivado além de `atol` ⇒ `AntiLeakageError` nomeando a feature.
- **C3 — fundamento futuro:** `fundamentals_effective_date > day` após o merge
  ⇒ `AntiLeakageError` (re-checagem defense-in-depth, I3).
- **C4 — timestamps duplicados/não-monótonos:** gate levanta erro de domínio
  (não silencia).
- **C5 — NaN-ratio acima do limite:** após descontar warmup, alguma feature
  excede `max_nan_ratio_per_feature` ⇒ erro com `failing_features` ordenado desc.
- **C6 — cobertura temporal insuficiente:** span de dias < `min_temporal_coverage_days`
  ⇒ erro do gate.
- **C7 — schema pandera inválido:** coluna ausente, dtype divergente, ordem do
  set quebrada ⇒ `SchemaError` do pandera na fronteira do adapter (antes de
  persistir).
- **C8 — set de features incompleto:** adapter não produziu uma coluna declarada
  no registry (ou produziu coluna extra) ⇒ erro antes do schema (I7).

## 7. Decisões técnicas relevantes

### D1 — Convenção do alvo e dono único (`TargetDefinition`)

- **O quê:** Alvo = `log(close_t/close_{t-1})` **backward**, indexado por
  `decision_day`; primeira linha cai; `TargetDefinition` (domain puro) é o **dono
  único**. Alinhar na origem com a convenção `target_timestamp` que a 4.3 consome
  (`timestamp_utc = decision_day`), corrigindo o off-by-one que gerou bug no old
  (ADR-0003 / R-20).
- **Por quê:** Fechada no ledger B-4.3 e ADR 0.0.0018 regra 5; verbatim no old
  (`build_tft_dataset_use_case.py:563-572`). Materializar como domain-service
  puro decompõe o monólito (alvo era inline) e elimina a ambiguidade cross-stage.
- **Fonte:** ledger B-4.3 (linha 43); overview `0_0_0018`; old
  `build_tft_dataset_use_case.py:563-572`.
- **ADR:** [`../../adr/3_5_0001-target-definition-backward-log-return.md`](../../adr/3_5_0001-target-definition-backward-log-return.md)

### D2 — Dtype de regime/flag com NaN no warmup

- **O quê:** Manter `float64` com `NaN` nas linhas de warmup para
  `volatility_regime`/`trend_regime`/`stress_tail_return_flag` (paridade com o
  oráculo), apesar de o `FeatureRegistry` declarar `int64`.
- **Por quê:** O oráculo de regressão exige paridade de colunas/dtypes
  (4023×62). O old é inconsistente (registry diz `int64`, parquet grava
  `float64` porque o warmup carrega `NaN`, que força promoção a `float`).
  Escolher `float64` evita divergência de regressão e é simples-e-trocável;
  registrar a inconsistência como débito.
- **Fonte:** oráculo `data/processed/dataset_tft/AAPL/...parquet`;
  `feature_registry.py` (specs `int64` em :482/:494/:504 vs. parquet `float64`).
- **ADR:** [`../../adr/3_5_0002-regime-features-nan-warmup-dtype.md`](../../adr/3_5_0002-regime-features-nan-warmup-dtype.md)

### D3 — Validador anti-leakage usa `DerivedFeatures` como oráculo

- **O quê:** Re-derivar cada feature via `DerivedFeatures` (3.4) + indicadores
  canônicos (3.1) e comparar com o valor montado (`atol ~1e-12`); **não**
  re-implementar a fórmula inline em pandas como o old (`:346-372`).
- **Por quê:** Elimina a dupla-fórmula do old (derivação e validação repetiam a
  expressão) e dá oráculo único e testado; cumpre a segunda-implementação-
  independente de ADR 0.0.0021 / 3.4.0001. Sem alternativa real descartada.
- **Fonte:** overview `0_0_0021`; ADR 3.4.0001; old `:346-372`.
- **ADR:** não — registrar como `[decision]` no technical §7.

### D4 — Config do gate de qualidade portada do old

- **O quê:** Portar `DatasetQualityGateConfig`
  (`max_nan_ratio_per_feature`, `require_unique/monotonic_timestamps`,
  `min_temporal_coverage_days`) lendo o warmup do `FeatureRegistry` — sem lista
  `FEATURE_WARMUP_BARS` paralela.
- **Por quê:** Paridade validada contra o oráculo; o `FeatureRegistry` já é a
  fonte do warmup (3.4), eliminando a lista paralela que podia divergir no old.
  Limites inalterados.
- **Fonte:** old `dataset_quality_gate.py:87-99`; `feature_registry.py` (warmup).
- **ADR:** não — `[decision]` no technical §7.

### D5 — Engine de montagem (pandas + duckdb) confinada a adapter

- **O quê:** `DatasetAssembler` em `adapters/out/pandas` (pandas + duckdb);
  orquestração em `BuildDataset` (application) dependendo só de ports.
- **Por quê:** ADR 0.0.0022 (engine) + regra hexagonal. Separa montagem física
  (adapter) de orquestração (use case puro), decompondo o monólito não-hexagonal
  do old. Postura já consolidada no projeto.
- **Fonte:** overview `0_0_0022`; LAYOUT §3.
- **ADR:** não — postura consolidada.

### D6 — Unificação `IndicatorSpec` ↔ `FeatureSpec` (não nesta Stage)

- **O quê:** Manter coexistência; 3.5 deriva set/ordem de `FeatureSpec` e mantém
  `IndicatorSpec` separado.
- **Por quê:** ADR 3.4.0002 deferiu a unificação para a integração 3.5, mas o
  ganho é cosmético e o custo (refactor mecânico de blast radius amplo) não
  justifica inflar a Stage de integração. Simples-e-trocável: unificar depois é
  barato.
- **Fonte:** ADR 3.4.0002.
- **ADR:** não — registrar como `[decision]`/débito no technical §7.

## 8. Integrações

### Internas (com outras Stages/módulos)

- **3.1 (`IndicatorCalculator`):** consumido pelo assembler (indicadores) e como
  oráculo de re-derivação anti-leakage.
- **3.2 (`ScoreAndAggregateSentiment`):** consumido para a série diária de
  sentimento (`DailySentimentDTO`).
- **3.3 (`AsofJoinAdapter` + `FundamentalsAsofPolicy`):** as-of backward dos
  fundamentos; `AntiLeakageError` reutilizado.
- **3.4 (`FeatureRegistry` + `DerivedFeatures`):** set/ordem/warmup/hash e oráculo
  puro de derivadas.
- **2.4 (`TradingCalendar`):** grade densa. **2.1 (`MedallionStore`):** persistência.
- **`composition_root.py`:** wiring dos 3 adapters + `BuildDataset` (I8).

### Externas

- Nenhuma nova fronteira externa nesta Stage (FinBERT/AlphaVantage já encapsulados
  em 3.2/2.3). Persistência via `MedallionStore` em
  `data/processed/dataset_tft/<SYM>/`.

## 9. Modelo de dados

O dataset montado (oráculo: 4023 linhas × 62 colunas, ordem confirmada):
colunas-base (`timestamp`, OHLCV, `asset_id`), 11 indicadores técnicos (3.1),
sentimento (`sentiment_score`, `news_volume`, `sentiment_std`, `has_news`),
derivadas de preço/volatilidade/liquidez/regime/sentimento (3.4), fundamentos
as-of + derivadas de fundamento (`fundamentals_effective_date`, `revenue`, …,
`revenue_yoy_growth`), time-features (`day_of_week`, `month`), `target_return` e
`time_idx`. Set e ordem das colunas de feature governados pelo `FeatureRegistry`
(I7); colunas-base/identificadoras/alvo/`time_idx` fora do set de feature.

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Dtype de regimes diverge do oráculo (int64 vs float64) | M | M | D2 / ADR 3.5.0002: float64 com NaN no warmup; teste de schema cobre |
| Ordem de montagem produz ordem de colunas ≠ registry | M | A | Assembler reordena pelo registry antes do schema; teste de ordem (I7) |
| Validador anti-leakage com falso-negativo (re-shift inline) | B | A | D3: usar oráculo puro 3.4, não fórmula inline; teste injeta divergência sintética |
| Off-by-one do alvo (bug do old) reaparece | B | A | D1 / ADR 3.5.0001: convenção única documentada e alinhada com 4.3; teste de alinhamento |
| Adapters 3.1/3.2/3.3 continuam dead-code | M | A | I8: wiring no composition root + teste de wiring |
| Warmup paralelo diverge do registry | B | M | D4: gate lê warmup do `FeatureRegistry`, sem lista paralela |

## 11. Critérios de aceitação

- [ ] **A1:** `TargetDefinition` é stdlib-only (sem pandas/numpy), `target[0]=None`,
  `target[t]=log(c_t/c_{t-1})`; `check_layout.py` verde.
- [ ] **A2:** `BuildDataset` recebe/devolve **DTO frozen**, depende só de ports,
  não devolve entidade nem `DataFrame`; testado com **fakes** dos ports.
- [ ] **A3:** Validadores anti-leakage re-derivam cada feature via oráculo puro
  (3.4 + 3.1) com `atol ~1e-12`; teste injeta divergência sintética e espera
  `AntiLeakageError`; guarda as-of (`effective_date <= day`) testada.
- [ ] **A4:** `DatasetQualityGate` lê warmup do `FeatureRegistry`, mede NaN-ratio
  após warmup, erra em timestamp duplicado/não-monótono, `failing_features` desc;
  stdlib-only.
- [ ] **A5:** Schema pandera valida as **62 colunas** e dtypes do oráculo (regimes
  `float64` por D2) e está confinado a `adapters/out`.
- [ ] **A6:** Integração roda AAPL e bate **set + ordem de colunas + contagem (62)**
  contra o oráculo (não bit-identidade).
- [ ] **A7:** `composition_root.py` wira `PandasTaIndicatorCalculator`,
  `FinbertSentimentModel`, `AsofJoinDuckdbAdapter` + `BuildDataset`, expostos por
  campos tipados pelos **ports** (I8); teste de wiring.
- [ ] **A8:** pandas/duckdb/pyarrow só em `adapters/out`; import-linter +
  `check_layout.py` verdes; `make check` e `make test-cov ≥ 90%` verdes.
- [ ] **A9:** ADRs 3.5.0001 e 3.5.0002 `accepted`.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? (§4)
- [x] Toda decisão em §7 tem fonte rastreável? (§7 D1–D6)
- [x] Toda integração externa tem contrato definido? (sem nova fronteira externa; §8)
- [x] Decisões com alternativa real descartada têm ADR escrito? (D1→3.5.0001, D2→3.5.0002)
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? (3.1–3.4)
- [x] Stage cabe em ~3–8 Tasks? (9 Tasks — relaxado por ROADMAP-1 para Stages densas)
- [x] Riscos críticos têm mitigação plausível? (§10)
- [x] O wiring resolve os findings F2 de dead-code? (I8 / §8)

## 13. Questões em aberto

- Nenhuma `TODO` crítica. Débitos conscientes registrados como `[decision]` no
  technical §7 (D3/D4/D5/D6) e na ADR 3.5.0002 (dtype dos regimes).

## 14. Referências

- [`../../overview.md`](../../overview.md) — §"Modelagem e dados" (`0_0_0016`, `0_0_0018`), §"Arquitetura e ferramentas" (`0_0_0021`, `0_0_0022`).
- [`../../roadmap.md`](../../roadmap.md) — §Stage 3.5; grafo `3.1–3.4 → 3.5`.
- [`../../autonomous-run-decision-ledger.md`](../../autonomous-run-decision-ledger.md) — B-4.3 (target_timestamp), H-2, H-3.
- ADRs desta Stage: [`../../adr/3_5_0001-target-definition-backward-log-return.md`](../../adr/3_5_0001-target-definition-backward-log-return.md), [`../../adr/3_5_0002-regime-features-nan-warmup-dtype.md`](../../adr/3_5_0002-regime-features-nan-warmup-dtype.md).
- ADRs de fundação: `0_0_0018` (anti-leakage/alvo), `0_0_0021` (regressão por unidade + oráculo), `0_0_0022` (engine pandas+duckdb), `3_4_0001` (oráculo causal puro), `3_4_0002` (coexistência IndicatorSpec/FeatureSpec).
- Old: `src/use_cases/build_tft_dataset_use_case.py` (418-624), `src/domain/services/dataset_quality_gate.py` (87-99).
