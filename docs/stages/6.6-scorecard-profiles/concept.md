---
title: Concept — Stage 6.6 — Perfis do scorecard com séries novas (DM por fold/seed/τ, blocos do MCS, estacionariedade de d_t, degeneração parcial por par, Monte Carlo de Christoffersen)
description: Os sete perfis que o pré-registro declara e o gold da 6.4 não guarda, calculados no RefreshGold pelos serviços da 6.1–6.3 sobre recortes da série montada pelo SeriesAssembly (fold carregado, perda por τ, série por seed), mais um diagnóstico de estacionariedade de d_t novo (ACF + CUSUM escalado pela variância do DM primário); as regras de perfil que o r0 não nomeia entram por uma emenda cega r1 ancorada; cada perfil vira tabela gold na mesma geração, coberta pelo manifesto; nenhuma falha de perfil aborta o refresh, e o ScorecardProfile as lê sem que o veredito as leia
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; ao perguntar onde mora cada perfil do scorecard, de onde vêm os parâmetros dos perfis, por que a r1 existe, o que o diagnóstico de estacionariedade de d_t calcula, ou por que o veredito não muda com as tabelas de perfil
keywords: [concept, scorecard-profiles, evaluation, profile, dm-per-fold, dm-per-seed, dm-per-tau, mcs-block-sensitivity, christoffersen-monte-carlo, partial-degeneracy, stationarity, acf, cusum, amendment, r1, blinding, gold]
status: done
created_at: 2026-10-06
updated_at: 2026-10-06
stage_id: 6.6-scorecard-profiles
stage_title: Perfis do scorecard com séries novas
step_id: 6
step_title: Núcleo estatístico confirmatório
depends_on: [6.5-preregistration-and-scorecard]
---

# Concept — Stage 6.6 — Perfis do scorecard com séries novas

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.
>
> **Camada teórica.** A teoria é do doc de domínio
> [`probabilistic-forecast-evaluation.md`](../../domain/evaluation/probabilistic-forecast-evaluation.md)
> (`accepted`): §5.1 (degeneração parcial "diagnóstico por par"), §6.2 e §6.8
> (Assumption DM, diagnóstico de d_t, B-FOLDS, DM por fold), §6.4 (DM por τ é
> perfil "sem inferência corrigida"), §6.5 (B-MCS, sensibilidade l = h e
> l = √T), §6.9 (B-SEEDS, DM por seed e fração que rejeita), §7.6 (Monte Carlo
> em h+1) e §8.6 (perfil nunca troca o veredito). Este concept não reabre
> nenhuma delas: fixa onde cada perfil é calculado e gravado, como entra no
> scorecard e as regras que a teoria deixou abertas.
>
> **Alinhamento (Passo 1b, 2026-10-06), decisões do humano:** B1 = as regras de
> perfil que o r0 não congela entram por **emenda cega r1** (caminho
> sustentado pela literatura); B2 = Stage única, mesmo passando de ~14 Tasks.
> Entendimento validado registrado no corpo da issue #129. **B1 supera o
> critério 3 da #129** ("sem emenda ao pré-registro") e o "no amendment needed"
> do ADR 6.5.0008 item 3 — ambos escritos antes da auditoria F7, que mostrou
> regras de perfil sem valor no r0; a nota datada no ADR 6.5.0008 e o PR
> registram a substituição.

## 1. Escopo

### Dentro do escopo

1. **Série montada carrega o fold.** O `SeriesAssembly` passa a entregar, na
   amostra comum de cada horizonte, o fold de cada ponto (o `fold` do run que
   produziu a previsão) quando todas as séries concordam; quando discordam, o
   rótulo fica indefinido com o motivo — **sem achado de alinhamento**, porque o
   fold só serve ao perfil (I3).
2. **Perdas por recorte (domínio).** Perda pinball por ponto num nível τ só
   (hoje só a média da grade); a `PairedLossSeries` recortada numa janela
   contígua (um fold); e a série pareada com **uma** seed do candidato (hoje só a
   média entre seeds).
3. **DM por fold, por seed e por τ** — `DieboldMariano.compare` (6.2) com o
   estimador primário, candidato × cada comparador, sobre cada recorte;
   **perfil descritivo**: p bruto e rejeição à α bruta, **sem correção de
   multiplicidade** (D3, doc §6.4). Por seed, a **fração de seeds que rejeitam
   a α** por (horizonte, comparador).
4. **MCS com bloco l = h e l = ⌈√T⌉** — `ModelConfidenceSet.evaluate` (6.2) no
   esquema primário do plano (`mcs.primary_scheme`; regra nomeada na r1,
   D10), com o bloco **passado explicitamente** pelo use case (o default da
   `arch` trunca √T), `reps`/`seed`/`alpha` do plano.
5. **P-valor Monte Carlo de Christoffersen em h+1** —
   `ChristoffersenTest.monte_carlo_p_values` (6.3) com `draws`/`seed` do plano,
   para toda sequência de hits não-DGT de h+1 que o gold já testa pelo χ².
6. **Degeneração parcial por par** — por **par simétrico** (a taxa que o
   `DegeneracyGate` da 6.1 já calcula, `pair_collapse_rates`) **e por par
   adjacente** da grade ordenada (função pública nova do módulo do gate,
   chamada só pelo perfil — fora do caminho do veredito —, mesmo denominador:
   linhas não-degeneradas; mesma tolerância do r0) (D5).
7. **Diagnóstico de estacionariedade de d_t** (estatística nova, domínio
   stdlib-only, validada contra oráculo): por horizonte e par de modelos da
   série pareada da leitura primária, a ACF amostral de d_t até L lags e um
   teste de quebra na média por CUSUM escalado pela **variância de longo prazo
   do DM primário** (retangular h−1, mesmo fallback), p-valor pela distribuição
   de Kolmogorov; mais a série d_t por ponto (insumo do plot da 8.3) (D2).
8. **Emenda cega r1** do pré-registro: `config/preregistration/aapl_confirmatory-r1.toml`
   = r0 + campos de emenda (`amends`, `justification`, `blind_status =
   "blinded"`) + bloco opcional `[profile_parameters]` com as regras nomeadas
   que o r0 não traz (multiplicidade dos recortes, pares da degeneração parcial,
   esquema da sensibilidade de bloco do MCS, ACF e teste de quebra de d_t e o
   α deste); o VO `Preregistration` aceita o
   bloco (opcional, ausente no r0, hash do r0 inalterado); espelho
   `docs/preregistration/aapl_confirmatory.md` com a seção da r1 e o hash
   completo; teste de consistência com a lista de revisões atualizada (F8e);
   âncora (tag + comentário na #129 + `.anchor.toml`, ADR 6.5.0003) **antes**
   do PR.
9. **Parâmetros pela derivação única (F8a).** `RefreshParameters` ganha
   `monte_carlo_draws`, `monte_carlo_seed`, `mcs_block_sensitivities` e
   `profile_parameters` (`ProfileParameters | None` — `None` quando a revisão
   não traz o bloco); `refresh_command_from` os preenche do plano;
   `check_manifest` os confere (compara o `as_mapping()` inteiro).
10. **Tabelas gold novas** (schema no `gold_schema`, um builder por tabela,
    mesma geração, manifesto por último): `gold_dm_profiles`,
    `gold_dm_seed_fraction`, `gold_mcs_block_sensitivity`,
    `gold_christoffersen_monte_carlo`, `gold_partial_degeneracy`,
    `gold_differential_acf`, `gold_differential_breaks`,
    `gold_loss_differentials` (D4).
11. **Perfil nunca aborta o refresh** — falha de uma unidade de perfil (recorte,
    rodada do MCS por bloco, sequência do Monte Carlo, par do diagnóstico) vira
    linha `undefined` com o motivo; o veredito não fica refém do perfil (I4).
12. **`ScorecardProfile` lê as tabelas novas** pelo `GoldGenerationReader`; os
    perfis entregues saem de `NOT_BUILT_HERE` (fica só `sharpness_diagram`,
    8.3); cada perfil declarado tem um estado (`built` | `not_frozen_in_revision`
    | `not_built_here`) (D7).
13. **Acessores tipados das células do gold (F6).** `col_int`, `col_float`,
    `col_str`, `col_bool` (e `*_or_none`), com política de tipo fixa (D9), que
    erguem `GoldGenerationCorruptError` em tipo divergente; os
    `type: ignore[arg-type]` sobre células do gold somem de
    `scorecard_evidence.py`, `scorecard_profile.py` e
    `build_confirmatory_scorecard.py` (os três módulos do registro F6 do
    technical 6.5 §7).
14. **Documentação:** nota datada no ADR 6.5.0008 (o follow-up virou a 6.6;
    item 3 "no amendment needed" e o "with its parameters" corrigidos: a
    tolerância da degeneração estava no r0, a definição do par e as regras de
    d_t e da multiplicidade não); roadmap (6.6 `done`, 8.1 com a dependência
    satisfeita e julgando pela r1, DoD da 6.6 reescrito pelo D5).

### Fora do escopo (explicitamente)

- **Plots** — diagrama de nitidez, distribuição de largura, gráfico de d_t e da
  ACF: **8.3** (ADR 6.5.0008 item 4). A 6.6 grava só os insumos.
- **Executar sobre o cohort AAPL real** e gravar o scorecard: **8.1**. Nenhum
  teste, script ou e2e desta Stage lê o `parent_sweep_id` do cohort real
  (cegamento confirmatório).
- **Mudar a regra do veredito** (H1/H2, árvore, Holm da família primária) ou
  qualquer valor já congelado no r0: a r1 copia o r0 e só **acrescenta** o
  bloco de perfis.
- Perfis que já saem do gold da 6.4 (6.5, ADR 6.5.0008 item 2).
- Teste de raiz unitária, espectro e teste de flutuação de Giacomini–Rossi
  sobre d_t (D2, alternativas descartadas).
- Compatibilidade de leitura de gerações gold antigas (6.5): o manifesto ganha
  campos obrigatórios; uma geração anterior a esta Stage deixa de ler como
  válida (D6) — não há gold confirmatório real gravado.

### Vínculo com o roadmap

Fecha o Step 6 ("núcleo estatístico confirmatório") e destrava a 8.1 (ADR
6.5.0008 §Consequences: "8.1 must not run before it"). O overview §4 fixa que o
perfil descreve e nunca decide; esta Stage completa o perfil que o pré-registro
promete. Roadmap §Stage 6.6 (pontos em aberto 1–4 fechados aqui: D1/D2, D7, D4 e
B2 = Stage única).

## 2. Objetivo da Stage

Ao fechar, um `RefreshGold` derivado da r1 publica, na mesma geração e sob o
mesmo manifesto, as tabelas dos sete perfis de séries novas, calculadas pelos
serviços da 6.1–6.3 (e pelo diagnóstico novo de d_t) com regras e valores só do
plano ancorado, e o `ScorecardResult` traz esses perfis sem que o
`ScorecardVerdict` dependa deles.

## 3. Contexto e premissas

### Contexto

A 6.5 declarou no r0 22 perfis e construiu os legíveis do gold (ADR 6.5.0008
item 2); os demais exigem séries que o gold não guarda (ADR 6.4.0001
§Negative: "não é só um builder"). A auditoria da 6.5 (comentário de
2026-09-30 na #129) acrescentou: F6 (células `object`), F7 (regras de perfil
sem valor no r0), F8a (`RefreshParameters` sem MC e blocos), F8e (lista de
revisões fixa no teste de consistência).

Leitura do código na abertura desta Stage (2026-10-06):

- `SeriesAssembly` agrupa por (h, (modelo, seed), alvo); o `fold` está no
  `CohortRun`/`ForecastRecord` mas não chega ao `HorizonSamples`; todo achado
  de alinhamento esvazia o `AssembledCohort` (sem horizontes → `BLOCKED`).
- `paired_pinball_losses` monta a série pareada com a média de L_t entre seeds
  (`PinballScore.per_point_losses` = média da grade por ponto).
- `DegeneracyGate.evaluate` já devolve `pair_collapse_rates` por par simétrico;
  o `CoverageReport` o carrega; o builder `metrics_by_run` não o grava.
- O DM ergue se o diferencial é constante após o fallback; o MCS ergue com
  diferencial constante; o `StatisticalPreconditionsCheck` só olha a amostra
  comum inteira.
- `diebold_mariano` calcula a variância de longo prazo de d̄ (retangular ou
  Bartlett até h−1; ≤ 0 com h > 1 → recalcula com h = 1) em código privado.
- `ChristoffersenTest.monte_carlo_p_values` existe, só para h = 1 e fora de DGT.
- `check_manifest` compara `parameters.as_mapping()` inteiro.
- Cohort r0: 6 folds × 252 pontos de teste (T por fold ≈ 252), TFT com 10 seeds,
  GBM com 1, 5 baselines sem seed, horizontes {1, 7}.

### Premissas

- Os folds de teste são blocos contíguos e disjuntos do índice de decisão,
  iguais para todos os modelos do cohort (concept 5.1 I7); a montagem e o
  `DmProfiles` **conferem** (rótulo divergente ou fold não contíguo → DM por
  fold `undefined`), não presumem.
- O custo do Monte Carlo (≈ 576 sequências de h+1 × 999 sorteios × T ≈ 1 500,
  com teto de 100·N tentativas nas sequências pouco aplicáveis) cabe num refresh
  confirmatório; **medido** numa Task sobre silver sintético com a forma do r0
  (CA17).
- Nenhum resultado confirmatório foi visto desde a âncora do r0: a r1 é cega
  (ADR 6.5.0002 item 5; ADR 6.5.0010 P1 para o que houve antes da âncora).

### Dependências

- `6.5-preregistration-and-scorecard`: `Preregistration` (+ `ProfileSpec`,
  `MonteCarloSpec`, `McsSpec.block_sensitivities`, emenda), `refresh_command_from`,
  `check_manifest`, `GoldGenerationReader`, `gold_schema`, `ScorecardProfile`,
  `NOT_BUILT_HERE`.
- `6.4`: `SeriesAssembly`, `HorizonSamples`, `RefreshGold`, `GoldInputs`,
  `GoldManifest`, `check_generation`, `GoldBuilder`.
- `6.2`: `DieboldMariano`, `ModelConfidenceSet`, `PairedLossSeries`,
  `McsBackend.bootstrap_indices`.
- `6.3`: `ChristoffersenTest.monte_carlo_p_values`, `HitSequences`.
- `6.1`: `PinballScore`, `DegeneracyGate`.

## 4. Contratos

Assinaturas finais (nomes de arquivo, tipos auxiliares) no technical; aqui o
contrato observável.

### Introduzidos

- **`HorizonSamples.common_folds`** (value-object, campo novo) —
  `tuple[str | None, ...] | None`: um rótulo por ponto da amostra comum, na
  ordem dos `target_timestamps`, quando todas as séries concordam alvo a alvo;
  `None` quando discordam (`HorizonSamples.fold_mismatch_detail` com o
  primeiro alvo divergente). Nunca é achado de alinhamento.
- **Perdas por recorte** (domain-services, funções puras):
  - `PinballScore.per_point_losses_at(series, level) -> tuple[float, ...]` —
    ρ_τ por ponto num nível da grade;
  - `paired_pinball_losses(..., level: float | None = None)` — `None` = média da
    grade (comportamento atual); um nível = perda daquele τ;
  - `PairedLossSeries.window(start, stop) -> PairedLossSeries` — fatia contígua.
- **`dm_long_run_variance(differences, horizon, estimator) -> (variance,
  horizon_used)`** (domain-service, público em `diebold_mariano.py`) — a
  variância de d̄ com o fallback do DM, extraída do primitivo (que passa a
  chamá-la); consumida pelo DM e pelo CUSUM (uma escrita só).
- **`DmProfiles`** (domain-service) — `DmProfiles.evaluate(samples, *,
  candidate, alpha, variance_estimator, rules) -> DmProfilesReport`: um
  `DieboldMarianoResult` por (recorte, comparador) — recortes por fold (ordem
  temporal), por seed do candidato e por τ —, cada recorte com status
  `computed` ou `undefined` (motivo: `too_short`, `constant_differential`,
  `fold_label_mismatch`, `fold_not_contiguous`, `error`), e a fração de seeds
  que rejeitam por comparador.
- **`adjacent_collapse_rates(series, *, tolerance)`** (função pública nova em
  `degeneracy_gate.py`, dono da regra) — `(τ_k, τ_{k+1}, taxa | None)` por par
  adjacente, mesmo denominador (linhas não-degeneradas pela mesma regra do
  gate) e tolerância; o `DegeneracyReport` e o `DegeneracyGate.evaluate` (caminho
  do veredito) **não mudam**.
- **`DifferentialStationarity`** (domain-service, stdlib) —
  `DifferentialStationarity.evaluate(series: PairedLossSeries, *, parameters:
  StationarityParameters, variance_estimator) -> tuple[StationarityReport, ...]` (um por par de
  `model_pairs()`): `differential`, `acf` (lags 1..L), `cusum_statistic`,
  `p_value`, `rejected`, `break_target_timestamp` (argmax de |S_k|),
  `horizon_used` (do fallback da variância); status `undefined` com d_t
  constante. Primitivos públicos `sample_acf(values, max_lag)` e
  `kolmogorov_sf(x)` (duas séries: a alternada para x grande e a teta para x
  pequeno, resultado em [0, 1]).
- **`ProfileParameters`** (value-object, campo opcional novo do
  `Preregistration`; vai ao `RefreshParameters`) — `subset_multiplicity`,
  `partial_degeneracy_pairs`, `mcs_block_sensitivity_scheme`, `stationarity:
  StationarityParameters` (`acf_max_lag`, `break_test`, `break_alpha`); todos
  obrigatórios dentro do bloco; cada identificador aceito só se o domínio o
  implementa (`PROFILE_RULE_CATALOG`, mesmo padrão do `RULE_CATALOG`); ausente
  no r0. O identificador `break_test` fixa "CUSUM escalado pela variância do DM
  com o estimador primário do plano"; o serviço recebe esse estimador do
  `RefreshParameters` (`dm_variance_estimators[0]`), nunca uma constante.
- **`ProfileReports`** (domain-service, análogo ao `HorizonReports`) — compõe,
  por horizonte, `DmProfiles`, `DifferentialStationarity`, o Monte Carlo de
  Christoffersen das sequências de h+1 e a degeneração parcial dos
  `SeriesReports`, isolando falha por unidade (I4).
- **`block_sensitivity_length(rule, *, horizon, n_points) -> int`**
  (domain-service, em `model_confidence_set.py`) — `"h"` → h; `"sqrt_T"` →
  ⌈√T⌉.
- **`RefreshParameters`** (dto, campos novos) — `monte_carlo_draws: int`,
  `monte_carlo_seed: int`, `mcs_block_sensitivities: tuple[str, ...]`,
  `profile_parameters: ProfileParameters | None`; `as_mapping`/`from_mapping`
  com as chaves novas (obrigatórias; `profile_parameters` pode ser `null`);
  `__post_init__` valida pelos donos (`validate_draws_and_seed`,
  `BLOCK_SENSITIVITIES`, o VO `ProfileParameters`).
- **`RefreshGoldResult.profile_error_units`** (dto, campo novo) — número de
  unidades de perfil com motivo `error` na geração (I4).
- **`GoldInputs`** (dto, campos novos) — `profile_reports` e
  `mcs_block_reports` (por (horizonte, regra de bloco): `McsReport` ou motivo
  `undefined`).
- **Oito `GoldTableSchema`** no `gold_schema` e oito builders (D4, §9).
- **`ScorecardProfile`** (dto) — por horizonte, as linhas copiadas das tabelas
  novas (`DmSubsetProfileRow`, `SeedFractionProfileRow`, `McsBlockProfileRow`,
  `MonteCarloProfileRow`, `PartialDegeneracyProfileRow`,
  `StationarityProfileRow`) e, por perfil declarado, `profile_states:
  tuple[(perfil, estado), ...]` com estado ∈ {`built`,
  `not_frozen_in_revision`, `not_built_here`}; `declared_not_built` mantido
  (= os `not_built_here`).
- **Acessores tipados** (`application/dtos/refresh_gold.py`, junto do
  `GoldGenerationCorruptError`) — `col_int`, `col_float`, `col_str`,
  `col_bool` e `*_or_none` (política em D9).
- **Arquivos do plano** — `aapl_confirmatory-r1.toml` e `.anchor.toml`.

### Consumidos

- `SeriesAssembly`, `HorizonSamples`, `RefreshGold`, `GoldInputs`,
  `GoldManifest`, `check_generation`, `GoldBuilder` — 6.4.
- `DieboldMariano`, `ModelConfidenceSet`, `McsBackend`, `PairedLossSeries`,
  `paired_pinball_losses` — 6.2.
- `ChristoffersenTest.monte_carlo_p_values`, `monte_carlo_defined_for`,
  `HitSequences` — 6.3.
- `PinballScore`, `DegeneracyGate`/`CoverageReport` — 6.1.
- `Preregistration`, `refresh_command_from`, `check_manifest`,
  `GoldGenerationReader`, `gold_schema`, `ScorecardProfile`,
  `BuildConfirmatoryScorecard` — 6.5.

## 5. Invariantes e regras

- **I1 — Reuso, não reimplementação.** DM, MCS e Christoffersen dos perfis são
  chamadas aos serviços da 6.2/6.3; a degeneração por par simétrico é o campo
  existente do `DegeneracyGate` e a adjacente mora no mesmo módulo; a variância
  do CUSUM é a `dm_long_run_variance` do DM; nenhum número tem segunda fórmula.
- **I2 — Mesma série da leitura primária.** Todo recorte parte da amostra comum
  do horizonte e das mesmas `CoverageSeries` que alimentam a
  `PairedLossSeries` primária; por fold = janela contígua dela; por τ = mesma
  amostra, perda de um nível; por seed = a seed s do candidato no lugar da
  média, os comparadores como na primária (média entre as suas seeds).
- **I3 — Fold não bloqueia.** O fold de um ponto é o `fold` do run que o previu;
  séries discordantes deixam `common_folds = None` e o DM por fold `undefined`
  (`fold_label_mismatch`); rótulo não contíguo na amostra comum →
  `fold_not_contiguous`. Nenhum dos dois é achado de alinhamento: o pareamento
  primário é por alvo e não depende do fold. Folds em ordem temporal (primeiro
  ponto); `fold = None` é um rótulo como outro (um fold só).
- **I4 — Perfil nunca aborta o refresh.** Cada unidade de perfil — recorte do
  DM, rodada do MCS por bloco, sequência do Monte Carlo, par do diagnóstico de
  d_t, série da degeneração adjacente — que não pode ser calculada vira linha
  `undefined` com motivo: pré-condições conhecidas nomeadas (`too_short`,
  `constant_differential`, ...) testadas **antes** da chamada, e
  `ValueError`/`ArithmeticError` erguido **pela chamada ao serviço ou ao
  backend** (só ela fica dentro da captura — a montagem do relatório e o
  mapeamento ficam fora, para que bug de contrato não vire linha) como `error`
  + mensagem. O `RefreshGoldResult` expõe `profile_error_units` (contagem das
  unidades `error`), visível ao operador. Os demais perfis e todo o caminho do
  veredito seguem.
- **I5 — Multiplicidade declarada.** Os recortes são descritivos: p bruto e
  `rejected` ⇔ p ≤ α, sem Holm nem outra correção dentro ou entre recortes;
  regra nomeada na r1 (`subset_multiplicity`) — ICH E9 §5.6.
- **I6 — Bloco explícito.** l = h e l = ⌈√T⌉ (T = pontos da amostra comum do
  horizonte, teto inteiro) saem de `block_sensitivity_length` e são passados ao
  backend; nenhuma chamada ao default de bloco da biblioteca.
- **I7 — Monte Carlo só onde definido.** Só h = 1, só sequências não-DGT;
  `draws`/`seed` do plano; uma `Random(seed)` por sequência (ADR 6.3.0006);
  status do `MonteCarloPValues` gravado como está (inclusive
  `not_applicable` com n_observado = 0 e o teto de tentativas).
- **I8 — Regras e valores só do plano.** Todo valor e toda regra nomeada dos
  perfis sai do `Preregistration` pela `refresh_command_from` e vai ao
  manifesto; nenhuma constante duplicada; `check_manifest` recusa divergência.
- **I9 — Perfil sem regra congelada não roda.** Revisão sem
  `[profile_parameters]` (r0) → `profile_parameters = None` → seis tabelas
  saem com zero linhas (`gold_dm_profiles`, `gold_dm_seed_fraction`,
  `gold_mcs_block_sensitivity`, `gold_partial_degeneracy`,
  `gold_differential_acf`, `gold_differential_breaks`) e sete perfis declarados
  ficam `not_frozen_in_revision` (`dm_per_fold`, `dm_per_seed`, `dm_per_tau`,
  `mcs_block_h`, `mcs_block_sqrt_t`, `partial_degeneracy_per_pair`,
  `dm_differential_stationarity`); só o Monte Carlo (draws/seed no r0) roda e
  fica `built`; a série d_t, que não é o diagnóstico e não tem regra, é gravada
  sempre (`gold_loss_differentials`). O estado vem **do plano lido**
  (`prereg.profile_parameters is None`), nunca de tabela vazia.
- **I10 — Mesma geração.** As oito tabelas são produzidas pelo mesmo
  `RefreshGold.__call__`, entram no `rows_by_table` do manifesto e no
  `check_generation`; refresh bloqueado não as constrói (não rodam bloqueadas);
  geração `COMPLETED` sem uma delas é corrupção (`GoldGenerationCorruptError`).
- **I11 — r0 intocado.** O hash do r0 não muda (o bloco novo é opcional e o
  r0 não o tem); a r1 é igual ao r0 em todo campo exceto `revision`, os campos
  de emenda e `[profile_parameters]` (teste).
- **I12 — Perfil nunca troca o veredito.** Nem `evidence_from_generation` nem
  `ConfirmatoryScorecard.decide` leem tabela nova (leitor espião); o
  `ScorecardVerdict` e `academic_decision_ready` são idênticos com as tabelas
  de perfil vazias, com conteúdo adversarial e (no nível evidência + decisão)
  sem elas; e uma falha de perfil não muda as tabelas do veredito (I4).
- **I13 — Builders são mapeamento puro.** Toda fórmula está no domínio
  (`ProfileReports` e serviços); a fração de seeds e o bloco ⌈√T⌉ inclusive.
- **I14 — Cegamento.** Nenhum teste/script lê o cohort real; e2e e integração só
  sobre silver sintético.

## 6. Casos de erro e exceções

| Situação | Comportamento |
|---|---|
| Séries discordam do fold de um alvo | `common_folds = None`; DM por fold `undefined` (`fold_label_mismatch`); refresh segue |
| Fold não contíguo na amostra comum | DM por fold `undefined` (`fold_not_contiguous`) |
| Recorte com T ≤ h ou T < 2 | recorte `undefined` (`too_short`); demais seguem |
| Diferencial constante num recorte | recorte `undefined` (`constant_differential`) |
| Serviço/backend de perfil ergue `ValueError`/`ArithmeticError` | unidade `undefined` (`error` + mensagem); refresh segue |
| d_t constante num par | diagnóstico do par `undefined`; ACF e CUSUM sem valor |
| T pequeno para a ACF | L = min(⌊10·log10 T⌋, T − 1); T < 2 → `undefined` |
| Sequência MC sem violação suficiente / teto | status do `MonteCarloPValues` gravado como está (6.3) |
| Revisão sem `[profile_parameters]` | seis tabelas com zero linhas, sete perfis `not_frozen_in_revision` (I9) |
| Fold não contíguo | uma linha `undefined` por (rótulo, comparador) — chave única |
| Rótulos de fold divergentes | uma linha `undefined` por comparador com `fold` nulo (nenhum rótulo legítimo coexiste) |
| Identificador/valor inválido em `RefreshParameters` (bloco, draws/seed, regras) | `ValueError` no `__post_init__` pelo validador dono (nunca chega ao perfil) |
| `[profile_parameters]` com regra fora do catálogo | `ValueError` no `Preregistration.from_mapping` (C1 da 6.5) |
| Manifesto sem os campos novos (geração anterior à 6.6) | `GoldGenerationCorruptError` na leitura (D6) |
| Parâmetro/regra de perfil do manifesto ≠ plano | `PreregistrationMismatchError` (`check_manifest`, campo `PARAMETERS`) |
| Geração `COMPLETED` sem uma tabela de perfil | `GoldGenerationCorruptError` (I10) |
| Célula do gold com tipo divergente da política | `GoldGenerationCorruptError` pelo acessor tipado (F6, D9) |

## 7. Decisões técnicas relevantes

> Formato dos forks E/C: skill `evidence-resolution` §5. Fontes da pesquisa do
> Passo 1c (corpo da #129, `## Referências`), conferidas por `evidence-verifier`
> em 2026-10-06 (statsmodels v0.15.0 `acf` l. 1002–1003, `S_hac_simple`
> l. 606–607, `breaks_cusumolsresid` l. 2152–2163; Diebold 2015 WP §2.2; ICH E9
> §5.6). Ploberger & Krämer (1992) **não foi acessado** (paywall): nada E se
> apoia nele. Checkpoint A (2 revisores, rodada 1) — disposições no technical §7.

### D1 — Regras de perfil faltantes: emenda cega r1 (decisão P do humano, B1)

- **O quê:** as regras que o r0 não congela — ACF e teste de quebra de d_t e o
  seu α, multiplicidade dos recortes do DM, pares da degeneração parcial,
  esquema de bootstrap da sensibilidade de bloco do MCS —
  entram por uma revisão r1 `blinded`, ancorada antes do PR (e portanto antes
  da 8.1), como identificadores de catálogo (o VO recusa regra não
  implementada) que vão ao `RefreshParameters` e ao manifesto.
- **Por quê:** ICH E9 §5.1 — o plano de análise "should be finalised before
  breaking the blind"; ADR 6.5.0002 materializa isso como revisão nova;
  rotular exploratório contrariaria a B-FOLDS ("diagnóstico de estacionariedade
  de d_t pré-registrado", doc §6.8). Sob o r0, os perfis dessas regras não
  rodam (I9) — o r0 nunca julga com regra que não nomeia.
- **Fonte:** pergunta B1 do Passo 1b (resposta do humano, 2026-10-06); technical
  6.5 §Riscos ("emenda cega r1 antes da 8.1"); comentário F7 da #129.
- **ADR:** [`6_6_0001`](../../adr/6_6_0001-stationarity-diagnostic-acf-and-dm-variance-cusum-frozen-by-blinded-r1.md).

### D2 — Diagnóstico de estacionariedade de d_t: ACF + CUSUM com a variância do DM (forks C)

```
[decision:C] 6.6-ST1 — lags da ACF de d_t
Escolha: L = min(⌊10·log10 T⌋, T − 1) · Alternativas: min(10, T/5) (FPP3 §5.4); h − 1; ⌈√T⌉; ln T · Degrau (C): 2
Base: statsmodels@0.15.0 tsa.stattools.acf: "if nlags is None: nlags = min(int(10 * np.log10(nobs)), nobs - 1)" (oráculo do teste) · Diebold 2015 §2.2 "examine its sample autocorrelations" (sem número)
Sensibilidade pré-registrada: nenhuma (diagnóstico descritivo; a ACF inteira até L é gravada) · Reversível: sim (nova revisão)

[decision:C] 6.6-ST2 — teste de quebra em d_t
Escolha: CUSUM da média (soma acumulada dos desvios de d_t) escalado pela variância de longo prazo; p-valor pela distribuição de Kolmogorov (sup |ponte browniana|) · Alternativas: OLS-CUSUM com σ iid (statsmodels breaks_cusumolsresid); sup-F de Andrews / Bai–Perron; teste de flutuação de Giacomini–Rossi · Degrau (C): 4 e 5
Base: Diebold 2015 §2.2 "test it for unit roots and other nonstationarities including trend, structural evolution, and structural breaks" (sem teste nomeado) · statsmodels@0.15.0 breaks_cusumolsresid: b = resid.cumsum() / np.sqrt((resid**2).sum()), crit 1.63/1.36/1.22 = kstwobign.isf (comentário "sup.abs of Brownian Bridge") — escala iid, inválida para d_t MA(h−1) (E: exclui a versão iid) · variante com variância de longo prazo: sob dependência fraca, S_⌊rT⌋/(σ_LR√T) ⇒ ponte browniana (FCLT; derivação) [SEM-FONTE-PRIMÁRIA]
Sensibilidade pré-registrada: nenhuma · Reversível: sim (nova revisão)

[decision:C] 6.6-ST3 — estimador da variância de longo prazo do CUSUM
Escolha: a do DM primário — retangular até h − 1 e, se ≤ 0 com h > 1, recalculada com h = 1 (`dm_long_run_variance`, a mesma regra `negative_variance_fallback` do r0) · Alternativas: Bartlett com m = max(h−1, ⌊4(T/100)^{2/9}⌋) (Newey–West; subestima a variância de um MA(h−1): com ρ_j = (7−j)/7 em h = 7, 5γ0 contra 7γ0, tamanho real ≈ 14 % a 5 % nominal — Checkpoint A D1); Bartlett h − 1 · Degrau (C): 1
Base: r0 rules.dm.kernel_lag = "rectangular_lag_h_minus_1" e rules.dm.negative_variance_fallback = "recompute_with_h_1_and_record" — o diagnóstico checa a premissa com a mesma variância que o DM primário usa; o retangular em h − 1 é consistente para a dependência MA(h−1) estrutural (DM 1995; doc §6.1)
Sensibilidade pré-registrada: nenhuma (`horizon_used` gravado) · Reversível: sim

[decision:C] 6.6-ST4 — α do teste de quebra
Escolha: 0,05 (= dm.alpha do r0), congelado na r1 · Alternativas: 0,10 (α do MCS) · Degrau (C): 1
Base: r0 `dm.alpha = 0.05` (o diagnóstico serve à premissa do DM)
Sensibilidade pré-registrada: nenhuma (o p-valor é gravado) · Reversível: sim
```

- **Escopo do diagnóstico:** todo par de `PairedLossSeries.model_pairs()` da
  amostra comum por horizonte — cobre a Assumption DM dos pares do DM e a
  estacionariedade dos d_ij que o MCS pressupõe (HLN 2011 Assumption 2, doc
  §6.5).
- **Fonte:** doc §6.1, §6.2, §6.8; pesquisa Passo 1c (#129); D1.
- **ADR:** [`6_6_0001`](../../adr/6_6_0001-stationarity-diagnostic-acf-and-dm-variance-cusum-frozen-by-blinded-r1.md).

### D3 — DM por recorte: descritivo, fold do run, sem correção

```
[decision:C] 6.6-DM1 — multiplicidade dos recortes
Escolha: p bruto e rejeição à α bruta; nenhuma correção dentro ou entre recortes; regra nomeada na r1 · Alternativas: Holm dentro de cada recorte; Holm sobre todos os recortes de uma dimensão · Degrau (C): 1
Base: doc §6.4 "DM por nível τ é perfil descritivo, sem inferência corrigida"; doc §6.8 "DM por fold reportado como perfil descritivo"; ICH E9 §5.6 "the details of any adjustment procedure or an explanation of why adjustment is not thought to be necessary should be set out in the analysis plan"
Sensibilidade pré-registrada: nenhuma · Reversível: sim (nova revisão)

[decision:E] 6.6-DM2 — de onde vem o fold de um ponto
Escolha: o `fold` do run que produziu a previsão, conferido entre séries (sem bloquear) · Alternativas: inferir o fold pela data do alvo; recortar pelo índice de decisão · Degrau (C): —
Base: concept 5.1 I7 (blocos de teste contíguos, disjuntos, comuns ao cohort); doc §6.8 (DM por fold = estabilidade entre re-estimações)

[decision:C] 6.6-DM3 — série do candidato no DM por seed
Escolha: a série da seed s do candidato; comparadores pela média das suas seeds (como na primária) · Alternativas: média de todas as outras seeds · Degrau (C): 1
Base: doc §6.9 B-SEEDS "o DM por seed e a fração de seeds que rejeita"

[decision:C] 6.6-DM4 — denominador da fração de seeds
Escolha: n_rejecting / (n_seeds − n_undefined), com n_undefined gravado; nulo se todas indefinidas · Alternativas: n_rejecting / n_seeds · Degrau (C): 4
Base: seed indefinida não é evidência de não-rejeição (a mais conservadora quanto a não inflar o denominador com não-testes); issue #129 item 2 "fração de seeds que rejeitam a α"
```

- **Estimador:** só o primário do plano (`dm.primary_estimator`); α =
  `dm.alpha`.
- **ADR:** [`6_6_0003`](../../adr/6_6_0003-dm-subsets-fold-from-run-raw-p-descriptive.md).

### D4 — Uma tabela gold por perfil; DM por recorte numa tabela com dimensão

- **O quê:** oito tabelas novas (§9). Fold/seed/τ numa só (`gold_dm_profiles`,
  coluna `dimension` ∈ {`fold`, `seed`, `tau`} e colunas tipadas `fold`,
  `seed`, `level`, nulas fora da dimensão); a fração de seeds em tabela à parte
  (outro grão). MCS por bloco em tabela própria, sem tocar a chave de
  `gold_mcs_results` (que a 6.5 lê). Monte Carlo em tabela própria (definido só
  em h = 1; colunas na `gold_calibration_table` ficariam nulas em metade das
  linhas e mudariam um schema lido pelo veredito).
- **Por quê:** as tabelas da 6.5 que o veredito lê não mudam; grão próprio por
  perfil mantém builders como mapeamento puro.
- **Fonte:** roadmap §Stage 6.6 ponto 3; issue #129 item 7 ("tabela gold ou
  colunas"); ADR 6.4.0001; ADR 6.5.0005.
- **ADR:** [`6_6_0002`](../../adr/6_6_0002-profile-tables-isolated-from-the-verdict.md).

### D5 — Degeneração parcial: pares simétricos (já calculados) e adjacentes, no mesmo gate

```
[decision:C] 6.6-T2 — que pares a degeneração parcial reporta
Escolha: simétricos (τ, 1−τ) — o `pair_collapse_rates` da 6.1 — e adjacentes (τ_k, τ_{k+1}) da grade ordenada, função pública nova do módulo do gate (fora do caminho do veredito), mesmo denominador (linhas não-degeneradas) e tolerância (`h1_gate.degeneracy_tolerance` do r0) · Alternativas: só simétricos; só adjacentes · Degrau (C): 1
Base: doc §5.1 — exemplo simétrico "q_0.25 = q_0.75 com q_0.02 < q_0.98" e motivação adjacente "boosters por nível podem empatar após a ordenação" (Zamo & Naveau 2018 §3.2.3); as taxas simétricas não determinam as adjacentes (q_0.25 = q_0.5 < q_0.75 não aparece em par simétrico) e, com tolerância > 0, gaps internos ≤ tol podem somar > tol (Checkpoint A D2)
Sensibilidade pré-registrada: nenhuma · Reversível: sim (nova revisão)
```

- **Desvio do roadmap:** o DoD da 6.6 diz "a degeneração por par [é] serviço de
  domínio novo validado por oráculo"; validado no Passo 1b com o humano
  (sem serviço novo: os pares simétricos já existem, os adjacentes entram no
  mesmo módulo dono da regra, validados por fixture analítica como os da 6.1), o
  DoD é reescrito no PR desta Stage.
- **Fonte:** código `degeneracy_gate.py` (`_pair_collapse_rates`); Passo 1b;
  Checkpoint A.
- **ADR:** [`6_6_0002`](../../adr/6_6_0002-profile-tables-isolated-from-the-verdict.md).

### D6 — Regras e valores de perfil no `RefreshParameters`; sem compatibilidade com manifesto antigo

- **O quê:** campos novos obrigatórios (`profile_parameters` aceita `None`) em
  `RefreshParameters`, serializados no manifesto; `from_mapping` exige as
  chaves novas.
- **Por quê:** ADR 6.4.0006 (parâmetros explícitos, sem default de domínio) e
  ADR 6.5.0004 item 3 (derivação única); manter leitura de manifesto antigo
  exigiria default — exatamente o que o ADR proíbe. Não há gold confirmatório
  gravado a preservar (cegamento). Alternativa descartada: chaves opcionais
  com default na leitura.
- **Fonte:** F8a (#129); ADR 6.4.0006; ADR 6.5.0004.
- **ADR:** [`6_6_0002`](../../adr/6_6_0002-profile-tables-isolated-from-the-verdict.md).

### D7 — `ScorecardProfile` lê as tabelas novas (perfil completo no `ScorecardResult`)

- **O quê:** `build_profile` lê as tabelas novas pelo `GoldGeneration` (schema
  do `gold_schema`), copia linhas para os DTOs do perfil e dá a cada perfil
  declarado um estado (`built` | `not_frozen_in_revision` | `not_built_here`);
  `NOT_BUILT_HERE` = `{"sharpness_diagram"}`. Tabela ausente numa geração
  `COMPLETED` é corrupção (I10), não perfil omitido.
- **Por quê:** o roadmap lista `scorecard_profile.py` a modificar ("deixa de
  listar os perfis entregues"); um artefato único gravado pela 8.1 (ADR 6.5.0008
  item 5); "tabela ausente" é corrupção pelo dono (`GoldGenerationCorruptError`,
  ADR 6.5.0005 item 5) e esconderia um builder não registrado.
- **Fonte:** roadmap §Stage 6.6 `arquivos_a_modificar`; ADR 6.5.0008; ADR
  6.5.0005; Checkpoint A (A6).
- **ADR:** [`6_6_0002`](../../adr/6_6_0002-profile-tables-isolated-from-the-verdict.md).

### D8 — ⌈√T⌉ explícito

```
[decision:E] 6.6-MCS1 — arredondamento de √T
Escolha: ⌈√T⌉ (teto), T = pontos da amostra comum do horizonte · Alternativas: int(sqrt(T)) (default da arch) · Degrau (C): —
Base: roadmap §Stage 6.5/6.6 e espelho do pré-registro: "l = ⌈√T⌉"; arch@8.0 MCS block_size default int(np.sqrt(T)) (trunca) — por isso o bloco é passado sempre
```

### D10 — Esquema de bootstrap da sensibilidade de bloco do MCS

```
[decision:C] 6.6-MCS2 — em que esquema rodam l = h e l = ⌈√T⌉
Escolha: só no esquema primário do plano (`mcs.primary_scheme`), um fator por vez em torno da leitura primária; regra nomeada na r1 (`mcs_block_sensitivity_scheme = "primary_scheme"`) · Alternativas: nos dois esquemas (primário e moving-block); só no moving-block · Degrau (C): 1 e 5
Base: doc §6.5 — a leitura primária é o estacionário com l = max(h, ⌈max b̂_sb⌉) e a "sensibilidade a l = h e l = √T" é sobre essa leitura; o moving-block já é a sensibilidade de esquema (r0 `sensitivity_schemes`); HLN 2011 fn. 14 varia só l mantendo o resto
Sensibilidade pré-registrada: nenhuma · Reversível: sim (nova revisão)
```

- **Consequência:** sob o r0 o MCS por bloco também fica `not_frozen_in_revision`
  (o r0 não diz o esquema; Checkpoint A rodada 2, N3).

### D9 — Política de tipo dos acessores do gold (F6)

- **O quê:** `col_int` aceita `int` não-`bool`; `col_float` aceita `int`
  não-`bool` ou `float` (devolve `float`); `col_bool` só `bool`; `col_str` só
  `str`; `*_or_none` aceitam `None`. Fora disso → `GoldGenerationCorruptError`
  nomeando tabela, coluna e tipo. Coluna fora do schema continua `KeyError`
  (regra do `col`).
- **Por quê:** é o que `_cell_ok` aceita e o que os builders gravam (contagens
  `int`, métricas `float`, flags `bool`); recusar `int` num `float` erguiria em
  dado válido (ex. 0 gravado por um parquet). O veredito das fixtures da 6.5
  fica inalterado (regressão).
- **Fonte:** F6 (#129); `refresh_gold.py` `_cell_ok`; Checkpoint A (D12).

## 8. Integrações

### Internas (com outras Stages/módulos)

- **modeling (5.5):** só via silver (`fact_oos_predictions`, `dim_run.fold`) —
  nada novo cruza a fronteira de BC.
- **8.1:** chama `refresh_command_from(r1, ref)` e grava o `ScorecardResult`
  (agora com o perfil completo).
- **8.3:** lê `gold_loss_differentials` e `gold_differential_acf` para os plots.

### Externas

- **GitHub** (âncora da r1): push da tag `preregistration/<ref-r1>` e
  comentário na #129 (procedimento do ADR 6.5.0003); nenhuma outra.

## 9. Modelo de dados

Toda tabela leva `asset`, `parent_sweep_id` e `preregistration_ref`
(confirmatória, não roda bloqueada). Chave = grão; colunas finais no technical.

| Tabela | Chave | Conteúdo principal |
|---|---|---|
| `gold_dm_profiles` | horizon, dimension, fold, seed, level, comparator | status, undefined_reason, n_points, janela, mean_differential, statistic, p_value, rejected, fallback_applied, alpha, variance_estimator |
| `gold_dm_seed_fraction` | horizon, comparator | n_seeds, n_rejecting, n_undefined, fraction_rejecting, alpha |
| `gold_mcs_block_sensitivity` | horizon, block_rule, model | status, undefined_reason, block_size e as colunas do `gold_mcs_results` (rank, p, included, reps, seed, scheme) |
| `gold_christoffersen_monte_carlo` | model, seed, horizon, sample, kind, level_low, level_high, includes_degenerate | status, mc_p_uc, mc_p_ind, mc_p_cc, draws, mc_seed, attempts |
| `gold_partial_degeneracy` | model, seed, horizon, sample, pair_kind, level_low, level_high | collapse_rate (nula sem linha não-degenerada), tolerance |
| `gold_differential_acf` | horizon, model_a, model_b, lag | acf, n_points, max_lag |
| `gold_differential_breaks` | horizon, model_a, model_b | status, cusum_statistic, p_value, rejected, alpha, horizon_used, break_target_timestamp, n_points |
| `gold_loss_differentials` | horizon, model_a, model_b, target_timestamp | fold, differential |

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Custo do Monte Carlo deixa o refresh lento | M | M | medir em silver com a forma do r0 (CA17); registrar tempo em §7; o MC é stdlib e por sequência |
| r1 ancorada com regra errada (achado posterior) | B | A | âncora é a **última** Task antes do PR, depois da Auditoria de Testes; o VO só aceita regras implementadas |
| Fold divergente ou não contíguo no cohort real | B | B | DM por fold `undefined`, visível no perfil; veredito intocado (I3) |
| `gold_loss_differentials` grande | B | B | 21 pares × ~1 500 × 2 horizontes ≈ 63 mil linhas — parquet comporta |
| CUSUM com tamanho distorcido em h = 7 | M | B | variância do DM primário (consistente para MA(h−1)); diagnóstico descritivo; ACF inteira gravada; variante `[SEM-FONTE-PRIMÁRIA]` |
| Perfil captura um bug real como `undefined` | B | M | motivo `error` grava a mensagem; testes dos serviços cobrem os caminhos; o `undefined` é visível no perfil |
| Tocar o hash do r0 ao estender o VO | B | A | I11 + teste de consistência recalcula o hash do r0 contra o espelho |

## 11. Critérios de aceitação

- [ ] **CA1** — `HorizonSamples.common_folds` alinhado à amostra comum; teste
  unit com folds de tamanhos distintos e `fold = None`; séries discordantes →
  `None` + detalhe, **sem achado** e com refresh `COMPLETED`.
- [ ] **CA2** — Perdas por τ (`per_point_losses_at`, `paired_pinball_losses(level=)`),
  `PairedLossSeries.window` e a série pareada por seed testadas em unit
  (inclusive: média dos τ ≡ perda da grade; janela preserva timestamps).
- [ ] **CA3** — `DmProfiles` chama `DieboldMariano.compare` por (recorte,
  comparador), sem fórmula própria: o recorte "fold único = amostra inteira"
  reproduz `statistic`/`p_value` da família primária; `rejected` ⇔ p ≤ α (sem
  Holm); recortes `undefined` por T curto, diferencial constante, rótulo
  divergente (uma linha por comparador, `fold` nulo) e fold não contíguo (uma
  linha por (rótulo, comparador)) — os dois passando pelo builder sem chave
  repetida; fração de seeds com uma seed indefinida (denominador
  n_seeds − n_undefined) e com todas indefinidas (nula).
- [ ] **CA4** — MCS por bloco: `block_sensitivity_length` (√T não-inteiro →
  teto); l passado ao backend (fake de `McsBackend` registra o `block_size`);
  falha do MCS numa regra → linha `undefined`, a outra regra e o MCS primário
  intactos.
- [ ] **CA5** — Monte Carlo só em h = 1 e não-DGT, `draws`/`seed` do plano;
  tabela sem linha de h = 7; célula a célula igual a
  `ChristoffersenTest.monte_carlo_p_values` chamado direto; status
  `not_applicable` (n_observado = 0, baseline pontual) gravado como está.
- [ ] **CA6** — `gold_partial_degeneracy`: linhas `symmetric` = `pair_collapse_rates`
  (igualdade célula a célula); `adjacent_collapse_rates` contra fixture
  analítica (inclusive q_0,25 = q_0,5 < q_0,75 e gaps internos ≤ tol somando
  > tol); taxa nula sem linha não-degenerada.
- [ ] **CA7** — `DifferentialStationarity` contra oráculo:
  ACF vs `statsmodels.tsa.stattools.acf(adjusted=False, fft=False, nlags=L)`;
  variância vs `dm_long_run_variance` e vs HAC retangular do statsmodels
  (`kernel='uniform'`, `maxlags=h−1` explícito, `use_correction=False`);
  estatística e p-valor em h = 1 vs
  `statsmodels.stats.diagnostic.breaks_cusumolsresid(d − d̄, ddof=0)` (`sup_b`,
  `pval`); estatística composta em h = 7 vs composição no teste a partir do
  statsmodels (`cumsum` dos desvios e HAC retangular com `maxlags=6`), inclusive
  com o fallback para h = 1 forçado; `kolmogorov_sf` vs `scipy.stats.kstwobign.sf` numa grade com
  x ∈ {0,05; 0,1; 0,2; 0,3; 1; 1,36; 3}, sempre em [0, 1]; local da quebra num
  degrau de média feito à mão; d_t constante → `undefined`; T pequeno
  (T = 3 → L = min(⌊10·log10 3⌋, 2) = 2).
- [ ] **CA8** — r1: arquivo válido pelo VO; igual ao r0 em todo campo exceto
  `revision`, `amends`, `justification`, `blind_status` e `profile_parameters`
  (teste); hash do r0 inalterado; regra fora do `PROFILE_RULE_CATALOG` →
  `ValueError`; espelho com o hash completo da r1;
  `test_every_revision_hash_quoted` cobre r0 e r1; `.anchor.toml` da r1 com
  `anchored_at` posterior ao do r0.
- [ ] **CA9** — `refresh_command_from(r1)` preenche os campos novos; com r0,
  `profile_parameters is None`; `check_manifest` recusa divergência em cada
  campo novo (teste por campo); manifesto sem as chaves novas →
  `GoldGenerationCorruptError`; `RefreshParameters` recusa no `__post_init__`
  bloco fora de `BLOCK_SENSITIVITIES` (ex. `"sqrt_t"`), draws/seed inválidos e
  regra de perfil fora do catálogo.
- [ ] **CA10** — As oito tabelas têm schema no `gold_schema`, builders
  registrados no composition root, saem na mesma geração, entram no
  `rows_by_table` e passam no `check_generation`; refresh bloqueado não as
  publica; geração `COMPLETED` sem uma delas → `GoldGenerationCorruptError`.
- [ ] **CA11** — I12: leitor espião prova que `evidence_from_generation` e
  `decide` não acessam nenhum dos oito schemas; `ScorecardVerdict` e
  `academic_decision_ready` idênticos com as tabelas de perfil vazias, com
  conteúdo adversarial (MCS por bloco excluindo o candidato, nenhum DM por fold
  rejeitando) e, no nível evidência + `decide`, sem elas; com uma falha
  injetada numa unidade de cada tipo de perfil (serviço substituído por um que
  ergue `ValueError`), as cinco tabelas do veredito saem idênticas às de uma
  geração sem a falha e `profile_error_units` conta as unidades.
- [ ] **CA12** — `ScorecardProfile` pela r1: perfis com estado `built` e linhas
  copiadas; `declared_not_built` = `("sharpness_diagram",)`. Pelo r0: os sete
  perfis do I9 em `not_frozen_in_revision`, `christoffersen_monte_carlo_h1`
  `built`, estado tirado do plano (teste com tabela vazia legítima sob a r1 →
  `built`).
- [ ] **CA13** — F6: acessores com a política do D9 (int/float/bool/str e
  `None`, testes de cada recusa); nenhum `type: ignore` (de qualquer código:
  `arg-type`, `misc`, `operator`) sobre linha que lê célula do gold (`col(`) em
  `scorecard_evidence.py`, `scorecard_profile.py` e
  `build_confirmatory_scorecard.py`; testes da 6.5 do veredito verdes sem
  alteração.
- [ ] **CA14** — e2e: `RefreshGold` real (adapters de arquivo) sobre silver
  sintético com 2 folds, 2 seeds do candidato e h ∈ {1, 7} publica as oito
  tabelas com a r1 (e com o r0: as seis do I9 vazias); com a r1, **zero**
  unidades `error` (`profile_error_units == 0`) e toda unidade `computed` salvo
  as forçadas pelo teste; `BuildConfirmatoryScorecard` pela r1 devolve o perfil
  completo. Nenhum teste referencia o `parent_sweep_id` do cohort real (grep).
- [ ] **CA15** — Nota datada no ADR 6.5.0008 (follow-up = 6.6; item 3 e "with
  its parameters" corrigidos); roadmap: 6.6 `done`, DoD reescrito (D5), 8.1
  com a 6.6 satisfeita e "julga pela r1".
- [ ] **CA16** — `make check` verde.
- [ ] **CA17** — Custo medido: `ProfileReports` sobre silver sintético com a
  forma do r0 (6 × 252 pontos, 10 seeds do candidato, 7 modelos, h ∈ {1, 7}),
  tempo total e do Monte Carlo registrados no technical §7, com zero unidades
  `error`; se o Monte Carlo passar de 30 min, é problema de desenho — parar e
  perguntar antes de seguir.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? — §4; tipos
  auxiliares finais no technical.
- [x] Toda decisão em §7 tem fonte rastreável? — D1–D10 com fonte e registro E/C.
- [x] Toda integração externa tem contrato definido (interface, formato, auth)?
  — só a âncora no GitHub, pelo procedimento do ADR 6.5.0003.
- [x] Decisões com alternativa real descartada têm ADR escrito? — 6.6.0001
  (D1, D2, D10), 6.6.0002 (D4, D5, D6, D7), 6.6.0003 (D3); D8 é E sem alternativa
  viável; D9 é política de tipo sem alternativa material.
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? — 6.5 `done`.
- [x] Stage cabe em ~3–12 Tasks (ver [`CONVENTIONS.md`](../../CONVENTIONS.md) §6)?
  — não: ~22 Tasks; decisão do humano (B2) de manter Stage única.
- [x] Riscos críticos têm mitigação plausível? — §10.
- [x] Cada mecanismo novo passou pelo **teste da solução mais direta**: não é caso especial/tipo/métrica novo remendando, local, um sintoma que recorre em outros consumidores e teria tratamento mais simples/geral em outra camada (concern compartilhado). Captura assim → piso declarado + issue, não solução local. — sim: a degeneração parcial fica no gate da 6.1, dono da regra (os simétricos já existem; os adjacentes são uma função a mais no mesmo módulo, chamada só pelo perfil, não serviço novo — D5); o fold vem do run já lido pela montagem, dona do alinhamento, não de uma inferência por data num consumidor; os recortes reusam `DieboldMariano.compare` e `PairedLossSeries`; a variância do CUSUM é a do DM, extraída para uma escrita só; o bloco ⌈√T⌉ é regra do domínio passada ao backend, não ajuste no adapter; o isolamento de falha de perfil é uma regra única no `ProfileReports`, não tratamento caso a caso; o único serviço novo (estacionariedade) é estatística que não existe em lugar nenhum do código.
- [x] A r1 é cega e só acrescenta? — I11 e CA8; nenhum resultado confirmatório
  visto desde a âncora do r0.
- [x] O veredito está isolado do perfil nos dois lados (escrita e leitura)? —
  I3 e I4 (escrita: fold e falha de perfil não bloqueiam), I12 e CA11
  (leitura: leitor espião, conteúdo adversarial).

## 13. Questões em aberto

Nenhuma crítica. Detalhes de forma (nomes de tipos auxiliares, colunas finais)
são do technical.

## 14. Referências

- [`../../overview.md`](../../overview.md) — §4 (perfil não decide)
- [`../../roadmap.md`](../../roadmap.md) — Stage `6.6-scorecard-profiles`, 6.5 e 8.1
- ADRs desta Stage: [`../../adr/`](../../adr/) (prefixo `6_6_`)
- ADRs consumidos: 6.4.0001, 6.4.0005, 6.4.0006, 6.5.0002, 6.5.0003, 6.5.0004,
  6.5.0005, 6.5.0008, 6.3.0006, 6.2.0005, 6.1.0003
- Doc de domínio §5.1, §6.1, §6.2, §6.4, §6.5, §6.8, §6.9, §7.6, §8.6, §11.3
- Diebold (2015), doi:10.1080/07350015.2014.983236, §2.2
- Ploberger & Krämer (1992), doi:10.2307/2951597 (não acessado; contexto)
- HLN (2011), doi:10.3982/ECTA5771, fn. 14 p. 484
- Dufour (2006), doi:10.1016/j.jeconom.2005.06.007
- ICH E9 (1998) §5.1, §5.6
- Issue [#129](https://github.com/MarceloSanC/financial-forecasting/issues/129) (corpo + comentário F6–F8)
