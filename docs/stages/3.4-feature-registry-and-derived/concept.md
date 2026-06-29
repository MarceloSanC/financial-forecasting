---
title: Concept — Stage 3.4 — Registro de features e derivadas causais (feature_engineering, domínio puro)
description: Registry rico de features como domínio puro stdlib-only — FeatureSpec value-object frozen (família de 4, tag de causalidade obrigatória, tipagem TFT known/unknown), FeatureRegistry domain service (fonte da verdade, rejeita feature sem contrato de causalidade, feature_set_hash determinístico) e DerivedFeatures domain service (as ~38 derivadas em Python puro como oráculo causal que a 3.5 valida)
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; revisar antes de executar o VO/registry/derivadas/testes
keywords: [concept, feature-registry, feature-spec, derived-features, feature-engineering, anti-leakage, causalidade, tft-typing, known-unknown, family, feature-set-hash, oracle, pure-domain, stdlib-only, log-return, momentum, volatility, parkinson, garman-klass, regime, sentiment, yoy, pct-change, rolling, ewm, shift, ddof]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 3.4-feature-registry-and-derived
stage_title: Registro de features e derivadas causais
step_id: 3
step_title: Camada de features (silver)
depends_on: [3.1-technical-indicators]
---

# Concept — Stage 3.4 — Registro de features e derivadas causais (`feature_engineering`)

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.

## 1. Escopo

### Dentro do escopo

- **`FeatureSpec`** (`domain/value_objects/feature_spec.py`): value-object de
  **domínio puro stdlib-only** (`dataclass` frozen) — o **superset rico** do
  `FeatureSpec` do old. Campos: `name` (não-vazio), `family ∈ {price, technical,
  sentiment, fundamental}`, `source_cols: tuple[str,...]`, `formula_desc: str`,
  `anti_leakage_tag` (**obrigatória**, em vocabulário fixo), `warmup_count: int>=0`,
  `null_policy: str` (default `"allow"`), `dtype: str`, `enabled_by_default: bool`
  (default `True`), e o **novo** `tft_typing ∈ {known, unknown}` (promovido do use
  case de treino do old). `__post_init__` valida os invariantes → `ValueError` de
  domínio.
- **`FeatureRegistry`** (`domain/services/feature_registry.py`): domain service que
  é a **fonte única da verdade das features**. Constrói/expõe `FEATURE_SPECS`
  (`Mapping[str, FeatureSpec]` imutável via `MappingProxyType`) com **todas** as
  features (baseline/preço, técnico, sentimento, fundamento e derivadas), cada uma
  com tag de causalidade + `tft_typing`. **Rejeita com erro de domínio** qualquer
  feature sem tag válida ou sem `tft_typing` (garantido por `FeatureSpec`).
  Getters `get_feature_spec`/`list_feature_specs` análogos ao old.
- **`feature_set_hash(specs|None) -> str`** (mesmo módulo): `sha256` determinístico
  sobre os specs **ordenados por nome** — postura **idêntica** a
  `indicator_registry_hash` (3.1). Mesmo set → mesmo hash (ordem de inserção
  irrelevante); perturbar qualquer campo de qualquer spec muda o hash. Aceita um
  registry alternativo para teste.
- **`DerivedFeatures`** (`domain/services/derived_features.py`): domain service com
  as **~38 derivadas em Python puro** (`math` stdlib, sobre tuplas/sequências) —
  recebe sequências (`close`, `high`, `low`, `open`, `volume`, `sentiment`,
  fundamentos as-of) e devolve tuplas alinhadas 1:1 com `None` nos warmups.
  Replica fórmulas/warmups **verbatim** do old (ledger §B 3.4), incluindo YoY
  (`revenue_yoy_growth`/`net_income_yoy_growth = pct_change(252, fill_method=None)`)
  deferido da 3.3 (ADR 3.3.0002). É o **oráculo causal** que a 3.5 (pandas) valida.
- **Testes unit:** `test_feature_registry.py` (hash determinístico/sensível,
  rejeição de feature sem contrato, cobertura de families/tft_typing) e
  `test_derived_features_causal.py` (invariância a barras futuras, shift positivo,
  ranges de flags/regimes, paridade lag==shift, YoY=None antes de 252).

### Fora do escopo (explicitamente)

- **Seleção de features por OOS** — **banida** (White 2000 / Romano-Wolf 2005;
  overview §11 `0.0.0003`). O design é confirmatório all-features + contribuição
  descritiva por família (H3); não há feature selection guiada por resultado OOS.
- **Persistência** (Parquet/DuckDB/schema `pandera`) — é da Stage 3.5.
- **Qualquer cálculo em pandas** — a 3.5 detém pandas; o domínio é stdlib-only. As
  derivadas aqui são Python puro (o oráculo); a implementação pandas vive na 3.5.
- **Montagem do dataset/grade densa diária, join das 4 famílias, alvo
  log-retorno, validadores anti-leakage in-process** — tudo 3.5.
- **Unificação física dos registries** (`IndicatorSpec` 3.1 ↔ `FeatureSpec` 3.4) —
  deferida para a integração (3.5), registrada como trabalho aceito (ADR 3.4.0002).
- **Fechamento da Stage** (commit `stage 3.4: complete`, marcar roadmap `done`) —
  é do orquestrador, após auditoria independente.

### Vínculo com o roadmap

Esta Stage implementa o `3.4-feature-registry-and-derived` do **Step 3 — Camada de
features (silver)**: o registry é a fonte da verdade das features e as derivadas
causais alimentam (na 3.5) o dataset TFT. Realiza a DoD do roadmap §3.4 ("toda
feature tem tag de causalidade e tipagem known/unknown; feature sem contrato de
causalidade é rejeitada pelo registry; derivadas causais testadas; `feature_set_hash`
determinístico") e recebe a absorção rica que a 3.1 deferiu (ADR 3.1.0001
§Consequences) e o YoY que a 3.3 deferiu (ADR 3.3.0002).

## 2. Objetivo da Stage

Existir um **registry de features de domínio puro** que é a fonte única da verdade:
toda feature tem família, tag de causalidade e tipagem TFT known/unknown validadas;
o registry rejeita qualquer feature sem contrato de causalidade; expõe um
`feature_set_hash` determinístico; e as ~38 derivadas estão implementadas em Python
puro como oráculo causal testado (invariância a barras futuras, shift positivo).

## 3. Contexto e premissas

### Contexto

- A 3.1 criou o BC `feature_engineering` como container layered e o `IndicatorSpec`
  **mínimo** (`name`/`family`/`source_cols`/`warmup`/`anti_leakage_tag`/`dtype`),
  deferindo o registry rico para esta Stage (ADR 3.1.0001 §Decision 2).
- A 3.3 entregou os 3 ratios point-in-time (`net_margin`/`leverage_ratio`/
  `cashflow_efficiency`) e deferiu o YoY (`pct_change(252)`) para cá (ADR 3.3.0002),
  porque YoY é função da grade densa diária, não de um único report.
- O old guardava a tipagem known/unknown **hardcoded** no use case de treino
  (`train_tft_model_use_case.py:1216`); a 3.4 centraliza isso no spec.

### Premissas

- As fórmulas/warmups do old são corretas e estáveis (em uso de produção); a tarefa
  é **traduzir** semântica pandas → Python puro, não reinventar.
- A 3.5 montará a grade densa diária forward-filled sobre a qual `pct_change(252)`
  (YoY) e as janelas trailing fazem sentido; o oráculo puro opera sobre sequências
  já alinhadas no tempo (uma barra por timestamp).

### Dependências

- `3.1-technical-indicators`: postura de hash (`indicator_registry_hash`), o molde
  reduzido `IndicatorSpec` que `FeatureSpec` faz superset, e o BC layered com prova
  de pureza (import-linter `domain-purity`).

## 4. Contratos

### Introduzidos

- **`FeatureSpec`** (`value-object`, frozen, domínio):

  ```python
  @dataclass(frozen=True)
  class FeatureSpec:
      name: str                          # não-vazio
      family: str                        # {price, technical, sentiment, fundamental}
      source_cols: tuple[str, ...]
      formula_desc: str
      anti_leakage_tag: str              # vocabulário fixo (ver abaixo)
      warmup_count: int                  # >= 0
      tft_typing: str                    # {known, unknown}
      null_policy: str = "allow"
      dtype: str = "float64"
      enabled_by_default: bool = True
      # __post_init__ -> ValueError de domínio se invariante violado
  ```

  Vocabulário fixo de `anti_leakage_tag` (superset das 2 tags da 3.1):
  `{point_in_time_ohlcv, same_timestamp_ohlc_derived, trailing_window_causal,
  lagged_causal, publication_cutoff_asof, reported_date_asof}`.

- **`FeatureRegistry`** (`domain-service`): `FEATURE_SPECS: Mapping[str,
  FeatureSpec]` (read-only, `MappingProxyType`) + `get_feature_spec(name)` +
  `list_feature_specs(*, family=None, enabled_only=False)` +
  `feature_set_hash(specs: Mapping | None = None) -> str` (sha256 sobre specs
  ordenados por nome).

- **`DerivedFeatures`** (`domain-service`): funções puras `seq -> tuple` que
  recebem sequências alinhadas e devolvem tuplas alinhadas com `None` nos warmups,
  replicando semântica pandas em Python puro: `rolling(min_periods=n)` → `None` nos
  `n-1` primeiros; `std` com `ddof=0` (variância populacional); `ewm(adjust=False)`
  recursiva `alpha=2/(span+1)`; `pct_change(fill_method=None)`; `shift(n>0)` sempre
  positivo; `clip(lower=0)` antes de `sqrt`; `_safe_ratio` (denom `None`/`0`/`NaN`
  → `None`).

### Consumidos

- **`IndicatorSpec`** (`value-object`) — declarado na Stage `3.1-technical-indicators`.
  É o molde reduzido; `FeatureSpec` é o superset e **não** o reescreve nesta Stage
  (ADR 3.4.0002). O roadmap não lista contrato consumido; `IndicatorSpec` entra só
  como referência de postura/molde.

## 5. Invariantes e regras

- **I1 — Pureza de domínio.** Os três módulos importam **só stdlib**
  (`math`/`dataclasses`/`hashlib`/`typing`/`collections.abc`/`types`). SEM
  numpy/pandas/pyarrow/torch/pydantic/sqlalchemy. O contrato `domain-purity` do
  import-linter (`.importlinter`) + `scripts/check_layout.py` **reprovam** se vazar
  (padrão provado por quebra revertida na 3.1 Task 08).
- **I2 — Tag de causalidade obrigatória.** Toda `FeatureSpec` tem `anti_leakage_tag`
  no vocabulário fixo; construir uma sem tag válida levanta `ValueError` de domínio.
  Logo o `FeatureRegistry` **não consegue** registrar uma feature sem contrato de
  causalidade (DoD novo vs o old, que era dict passivo). Fonte: ADR 0.0.0018 regra 3.
- **I3 — Tipagem known/unknown obrigatória.** Toda `FeatureSpec` tem `tft_typing ∈
  {known, unknown}`; calendário (`day_of_week`, `month`, `time_idx`) = `known`;
  preço/indicadores/sentimento/fundamento/derivadas = `unknown` (confirmado em
  `train_tft_model_use_case.py:1216`). Regra única no spec, não espalhada no use case.
- **I4 — Família de 4 valores.** `family ∈ {price, technical, sentiment,
  fundamental}` (ADR 0.0.0016); `baseline`/`derived` do old NÃO são família —
  OHLCV cru e derivadas de preço → `price`.
- **I5 — Hash determinístico.** `feature_set_hash` é função **pura** do conteúdo dos
  specs ordenados por nome; mesmo set → mesmo hash independentemente da ordem de
  inserção; perturbar qualquer campo de qualquer spec **muda** o hash (ADR 1.4.0001 /
  postura 3.1).
- **I6 — Causalidade das derivadas (testável).** Anexar barras **futuras** não altera
  valores passados (prefixo estável); `shift` sempre `n>0` (nunca negativo);
  flags/regimes derivam de janelas trailing **shiftadas** (`volume_zscore` usa
  `volume.shift(1)` na janela de 20; `volatility_regime`/`trend_regime`/
  `stress_tail_return_flag` usam `.shift(1).rolling(63)`). Fonte: ADR 0.0.0018 regra 1.
- **I7 — Warmups verbatim e warmup efetivo documentado.** `warmup_count` de cada
  derivada = janela do old; o warmup **efetivo** é documentado quando difere
  (ex.: `vol_of_vol`=40 = 20 da `volatility_20d` + 20 da `rolling_std`;
  `volume_zscore` = numerador corrente + estatística trailing `t-20..t-1`). Sem
  off-by-one na tradução pandas → puro.

## 6. Casos de erro e exceções

- **C1 — `name` vazio** → `ValueError` ("FeatureSpec.name must be a non-empty string").
- **C2 — `warmup_count < 0`** → `ValueError`.
- **C3 — `family` fora de `{price, technical, sentiment, fundamental}`** → `ValueError`.
- **C4 — `anti_leakage_tag` ausente ou fora do vocabulário fixo** → `ValueError`
  (espinha do DoD: feature sem contrato de causalidade é rejeitada).
- **C5 — `tft_typing` fora de `{known, unknown}`** → `ValueError`.
- **C6 — Divisão por zero/None em derivadas** (`net_margin`, `leverage_ratio`,
  `cashflow_efficiency`, `volume_zscore`, `amihud`, `drawdown`): `_safe_ratio` /
  guarda explícita devolve `None` (não levanta, não produz `inf`/`NaN` propagado).
- **C7 — Posição em warmup** (menos de `n` observações disponíveis para a janela):
  a função devolve `None` naquela posição (paridade `rolling(min_periods=n)`), nunca
  um valor parcial.
- **C8 — `sqrt` de variância negativa** (ruído numérico em Parkinson/GK/downside):
  `clip(lower=0)` antes do `sqrt` (paridade com o old), nunca `NaN` de raiz negativa.

## 7. Decisões técnicas relevantes

### D1 — Computar as derivadas em domínio puro (oráculo) vs. só especificar
- **O quê:** Computar as ~38 derivadas em Python puro (`math` stdlib, sobre tuplas)
  no `DerivedFeatures`; a 3.5 (pandas) valida contra essa implementação como oráculo
  causal — em vez de um registry só-spec.
- **Por quê:** o roadmap lista `derived_features.py` como domain **service** (não VO);
  ADR 0.0.0021 (oráculo por unidade, não snapshot global) e o finding carregado pedem
  o oráculo puro; o old já provou as fórmulas estáveis. Custo real baixo (lógica
  existe, só traduzir pandas → puro); ganho alto (2ª implementação independente que
  pega divergência na 3.5). "Só spec" adia o oráculo e enfraquece o teste de
  causalidade.
- **Fonte:** Roadmap §3.4 (`derived_features.py` como service); ADR 0.0.0021; ledger
  §B 3.4; old `build_tft_dataset_use_case.py:146-285`.
- **ADR:** [`../../adr/3_4_0001-compute-derived-features-in-pure-domain-as-causal-oracle.md`](../../adr/3_4_0001-compute-derived-features-in-pure-domain-as-causal-oracle.md)

### D2 — Grau de absorção do `IndicatorSpec` (3.1) → `FeatureSpec` (3.4)
- **O quê:** `FeatureSpec` é o superset rico (adiciona `formula_desc`/`null_policy`/
  `enabled_by_default`/`tft_typing`/`family` de 4 valores) e **não** reescreve/remove
  `IndicatorSpec` nesta Stage; `feature_set_hash` cobre o registry de features,
  `indicator_registry_hash` (3.1) permanece. Absorção física fica para a integração
  (3.5), como trabalho aceito.
- **Por quê:** ADR 3.1.0001 §Consequences declara a absorção como trabalho da família
  mas aceita o custo; mexer no `IndicatorSpec`/3.1 agora arrasta testes/hash já verdes
  e amplia o blast radius sem necessidade. Simples-e-trocável: superset coexiste;
  unificação posterior é refactor mecânico.
- **Fonte:** ADR 3.1.0001 §Decision 2 / §Consequences; roadmap non_goal (não tocar
  integração/persistência).
- **ADR:** [`../../adr/3_4_0002-featurespec-superset-and-tft-typing-promotion.md`](../../adr/3_4_0002-featurespec-superset-and-tft-typing-promotion.md)

### D3 — Mecanismo do `feature_set_hash`: sha256 puro no domínio vs. port `Hasher`
- **O quê:** `sha256` inline no domínio (postura idêntica a `indicator_registry_hash`:
  join `|`/`\n` canônico sobre specs ordenados por nome), **não** injetar o port
  `Hasher`.
- **Por quê:** o port `Hasher` vive em `adapters/out` (`canonical_json_hasher`) e o
  domínio não pode importá-lo sem virar container/quebrar pureza; `hashlib` é stdlib
  (permitido). A 3.1 fixou esse padrão e passou nos gates; reusar mantém consistência
  e evita injeção num domain service que deve ser função pura. ADR 1.4.0001 cobre a
  semântica canônica; o hash de registry é texto ordenado determinístico (mesmo
  espírito de `hash_text`).
- **Fonte:** 3.1 `indicator_spec.py:123-152`; ADR 1.4.0001; LAYOUT §3 (domínio não
  importa adapters).
- **ADR:** não (postura já consolidada na 3.1; sem alternativa nova descartada).

### D4 — Promover `tft_typing` (known/unknown) e `family` de 4 valores para a `FeatureSpec`
- **O quê:** Adicionar `tft_typing ∈ {known, unknown}` e `family ∈ {price, technical,
  sentiment, fundamental}` como campos obrigatórios validados; calendário=`known`,
  resto=`unknown`; regra única no spec, não hardcoded no use case.
- **Por quê:** no old a classificação known/unknown morava hardcoded no use case de
  treino (`:1216`), espalhando a decisão; a Stage exige tipagem TFT por feature como
  contrato (DoD). Centralizar no spec é melhoria estrita: fonte única, validável,
  habilita o teste de invariante I3. `family` de 4 valores alinha ADR 0.0.0016
  (old usava `group` de 5 valores; mapear `baseline`+derivadas de preço → `price`).
- **Fonte:** old `train_tft_model_use_case.py:1216`; ADR 0.0.0018 regra 3; ADR
  0.0.0016; roadmap §3.4 DoD.
- **ADR:** [`../../adr/3_4_0002-featurespec-superset-and-tft-typing-promotion.md`](../../adr/3_4_0002-featurespec-superset-and-tft-typing-promotion.md)
  (tft_typing + family) e [`../../adr/0_0_0016-four-feature-families.md`](../../adr/0_0_0016-four-feature-families.md)
  (taxonomia das 4 famílias, oficializada por esta Stage).

## 8. Integrações

### Internas (com outras Stages/módulos)

- **3.1 `IndicatorSpec`/`indicator_registry_hash`:** molde e postura de hash reusados;
  coexistência sem reescrita (D2).
- **3.5 dataset-builder (pandas):** consumirá `FeatureRegistry` como fonte da verdade
  e validará a implementação pandas das derivadas contra `DerivedFeatures` (oráculo).
- **3.3 `FundamentalsAsofPolicy`:** os 3 ratios point-in-time já vivem lá; o YoY
  (`pct_change(252)`) entra aqui sobre a série diária (ADR 3.3.0002).

### Externas

- Nenhuma (domínio puro stdlib-only).

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Off-by-one na tradução pandas → puro (shift/min_periods/ddof) | M | A | Warmup efetivo documentado por feature (I7); teste de paridade contra valores conhecidos do old; teste de causalidade (append-future-bars) |
| Vazamento de lib no domínio (numpy/pandas) | B | A | import-linter `domain-purity` + `check_layout.py` (I1); revisão de imports |
| Divergência silenciosa 3.5 (pandas) vs oráculo | M | A | A 3.5 roda teste de paridade contra `DerivedFeatures`; qualquer drift fica vermelho (D1/ADR 0.0.0021) |
| Hash não-determinístico (ordem de inserção) | B | M | Ordenação por nome no `feature_set_hash` + teste "ordem irrelevante" (I5) |

## 11. Critérios de aceitação

- [ ] **A1 —** `FeatureSpec` é `dataclass` frozen; `__post_init__` levanta `ValueError`
  para `name` vazio (C1), `warmup_count<0` (C2), `family` fora do set (C3),
  `anti_leakage_tag` fora do vocabulário (C4), `tft_typing` fora de `{known,unknown}`
  (C5).
- [ ] **A2 —** `FEATURE_SPECS` é `MappingProxyType` imutável com todas as features
  (baseline/preço, técnico, sentimento, fundamento, derivadas); cada spec tem
  `anti_leakage_tag` válida + `tft_typing`; construir o registry não levanta erro
  (toda feature tem contrato).
- [ ] **A3 —** Tentar registrar/instanciar uma `FeatureSpec` sem tag válida ou sem
  `tft_typing` levanta `ValueError` de domínio (teste em `test_feature_registry.py`).
- [ ] **A4 —** `feature_set_hash` é estável (mesmo set → mesmo hash), independente da
  ordem de inserção, e muda quando qualquer campo de qualquer spec é perturbado.
- [ ] **A5 —** As ~38 derivadas estão implementadas em `DerivedFeatures` em Python
  puro com fórmulas/warmups verbatim do old, incluindo `revenue_yoy_growth`/
  `net_income_yoy_growth` via `pct_change(252, fill_method=None)`.
- [ ] **A6 —** Teste de causalidade: anexar barras futuras NÃO muda o prefixo passado;
  nenhum shift negativo; `volume_zscore`/regimes/stress usam janelas trailing
  shiftadas; `volatility_regime ∈ {0,1,2}`, `trend_regime ∈ {-1,0,1}`,
  `stress_tail_return_flag ∈ {0,1}`, volatilidades `>= 0`; YoY `None` antes de 252.
- [ ] **A7 —** `tft_typing`: calendário (`day_of_week`/`month`/`time_idx`) = `known`;
  preço/indicador/sentimento/fundamento/derivada = `unknown` (coberto por teste).
- [ ] **A8 —** Pureza: import-linter `domain-purity` + `check_layout.py` verdes;
  nenhum import de numpy/pandas/torch/pydantic/sqlalchemy nos três módulos.
- [ ] **A9 —** Gates verdes: `make check` (ruff + mypy --strict), `make test-cov`
  com cobertura `>= 90%` dos módulos de 3.4.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? (§4)
- [x] Toda decisão em §7 tem fonte rastreável? (§7 D1-D4)
- [x] Toda integração externa tem contrato definido? (não há externa — domínio puro)
- [x] Decisões com alternativa real descartada têm ADR escrito? (D1→3.4.0001,
  D2/D4→3.4.0002, D4→0.0.0016; D3 sem ADR pois sem alternativa nova)
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? (3.1 `done`)
- [x] Stage cabe em ~3–8 Tasks? (11 Tasks no technical, das quais ~9 de
  código/testes; derivadas fatiadas por família — dentro da faixa por coesão)
- [x] Riscos críticos têm mitigação plausível? (§10)
- [x] O `feature_set_hash` é genuinamente função pura do conteúdo? (I5, D3)

## 13. Questões em aberto

- Nenhuma crítica. (A unificação física dos registries é deferida e rastreada por
  ADR 3.4.0002, não bloqueia esta Stage.)

## 14. Referências

- [`../../overview.md`](../../overview.md) — §3 escopo, §11 ADRs de fundação
  (`0.0.0016` 4 famílias, `0.0.0018` anti-leakage, `0.0.0003` seleção banida).
- [`../../roadmap.md`](../../roadmap.md) — Stage `3.4-feature-registry-and-derived`
  e vizinhas (3.1, 3.3, 3.5).
- ADRs desta Stage: [`../../adr/`](../../adr/) — `3_4_0001`, `3_4_0002`, `0_0_0016`.
- ADRs relacionados: `3.1.0001` (BC + IndicatorSpec mínimo), `3.3.0002` (YoY
  deferido), `0.0.0018` (anti-leakage), `0.0.0021` (oráculo por unidade),
  `1.4.0001` (hash determinístico).
- Old: `src/infrastructure/schemas/feature_registry.py` (FeatureSpec + hash),
  `src/use_cases/build_tft_dataset_use_case.py:146-285` (derivadas),
  `src/use_cases/train_tft_model_use_case.py:1216` (known/unknown hardcoded).
