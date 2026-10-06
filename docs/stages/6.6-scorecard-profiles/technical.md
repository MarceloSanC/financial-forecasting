---
title: Technical — Stage 6.6 — Perfis do scorecard com séries novas
description: Plano de execução da Stage 6.6 — primitivos de domínio (variância do DM pública, bloco ⌈√T⌉, perdas por τ e janela, fold na amostra comum, pares adjacentes), regras de perfil no pré-registro, diagnóstico de estacionariedade de d_t contra oráculo, DM por recorte, composição dos perfis com isolamento de falha, RefreshParameters/RefreshGold estendidos, oito builders gold, leitura pelo ScorecardProfile, emenda cega r1 e âncora
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem arquivos, critério de aceite e comando de verificação
keywords: [technical, plano de execução, scorecard-profiles, evaluation, profile, r1, stationarity, dm-subsets, gold-builders]
status: done
created_at: 2026-10-06
updated_at: 2026-10-06
stage_id: 6.6-scorecard-profiles
stage_title: Perfis do scorecard com séries novas
step_id: 6
step_title: Núcleo estatístico confirmatório
depends_on: [6.5-preregistration-and-scorecard]
concept_ref: ./concept.md
issue_id: 129
branch: feat/129-6-6-scorecard-profiles
tasks_count: 22
---

# Technical — Stage 6.6 — Perfis do scorecard com séries novas

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [6.6/task-NN]`
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, perguntar ao humano com opções e recomendação, e
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done).
> 7. Ao fim da última Task, validar [§3 Gate de saída](#3-gate-de-saída-da-stage),
>    fazer commit `stage 6.6: complete` e atualizar `roadmap.md`.
>
> **Stage = 1 branch:** `feat/129-6-6-scorecard-profiles` (worktree paralela).

## 1. Contexto e estratégia de execução

### Resumo

Sete perfis do scorecard que o gold da 6.4 não guarda, calculados dentro do
`RefreshGold` sobre recortes da série pareada primária e gravados em oito
tabelas gold novas, lidas pelo `ScorecardProfile` e nunca pelo veredito
(concept §1–§5). As regras de perfil que o r0 não nomeia entram por uma emenda
cega r1 (ADR 6.6.0001), ancorada como última Task antes do PR.

### Estratégia

TDD inside-out (skill `task-ordering-hex`), sem port novo: nenhum port é
criado ou estendido (o `McsBackend` e o `GoldBuilder` são consumidos como
estão). Ordem:

1. **Primitivos de domínio** (Tasks 01–06): acessores tipados (F6, na
   application, porque desobstruem os módulos que as Tasks 13 e 18 tocam);
   variância do DM pública; bloco de sensibilidade; perdas por τ e janela; fold
   na amostra comum; pares adjacentes.
2. **Regras do plano** (07–08): VO `ProfileParameters` e o bloco opcional no
   `Preregistration` (hash do r0 inalterado).
3. **Serviços de perfil** (09–11): diagnóstico de d_t contra oráculo; DM por
   recorte; composição `ProfileReports` com isolamento de falha.
4. **Application** (12–13): `RefreshParameters` (F8a) e o `RefreshGold`
   calculando os perfis (com `FakeGoldBuilder`).
5. **Adapters out** (14–16): oito builders + schemas, contract test.
6. **Wiring** (17) e **leitura** pelo `ScorecardProfile` + I12 (18).
7. **Plano e validação** (19–20): r1 + espelho; e2e e medição de custo.
8. **Docs** (21) e **âncora** (22), depois da Auditoria de Testes.

Exceções ao teto de ~5 arquivos por Task, declaradas (todas mecânicas,
forçadas por construtor `kw_only` sem default ou por teste que fixa um
conjunto exato): Task 12 (o `RefreshParameters` é construído em 7 arquivos de
teste, ADR 6.4.0006, + o teste do `check_manifest`), Task 13 (o `GoldInputs`
no use case e na fixture do contract test), Tasks 14–16 (o
`test_refresh_gold_dtos.py` fixa `set(GOLD_SCHEMAS)`; a 16 tem quatro builders
triviais), Task 17 (dois helpers de teste montam geração `COMPLETED` por
`from_stored` e quebram com a regra nova), Task 18 (o `ScorecardProfile` é
construído num teste do use case).

**Divergências declaradas do concept (forma, não contrato):**
- Os identificadores de regra são conferidos **só** pelo VO `ProfileParameters`
  (dono único do catálogo, construído na leitura do plano e do manifesto); os
  serviços recebem o VO já válido e não reconferem — `DmProfiles` não recebe
  `rules` (há uma regra só, `none_raw_p_descriptive_v1`).
- O isolamento de falha do MCS por bloco fica no use case `RefreshGold` (o
  backend é port da application, fora do alcance do domínio); as demais
  unidades ficam no `ProfileReports`. A regra é a mesma (só a chamada dentro da
  captura; `ValueError`/`ArithmeticError` → `error`).
- `ProfileParameters` tem **uma** serialização (`as_payload`, a forma do TOML,
  JSON-safe: tabelas de `str`/`float`), usada também no manifesto; `from_mapping`
  é a inversa dela.

**Testes contra oráculo** (statsmodels, scipy, numpy, arch) ficam em
`tests/integration/features/evaluation/` — o gate
`tests/architecture/test_unit_evaluation_purity.py` proíbe esses imports em
`tests/unit/features/evaluation/**` (precedente: `test_mcs_vs_arch.py`). Esse
gate e o `tests/unit/shared` não rodam no T1 (`check-task SLICE=evaluation`):
por isso as Tasks que tocam o composition root rodam `check-block`.

### Pré-condições

- Stage `6.5-preregistration-and-scorecard` em `done` e mergeada em `develop`.
- `concept.md` desta Stage `done`; issue #129 aberta.
- Imagem `financial_forecasting-app:dev` e volume `financial-forecasting_app-venv`
  presentes (host Windows, fluxo Docker-only).

### Premissas técnicas

- Python 3.12+, domínio stdlib-only; `statsmodels`/`scipy`/`arch` só em testes
  (oráculos) e no adapter `arch` já existente.
- **Comandos rodam no container** (worktree montada à parte). Abreviação usada
  nos comandos de verificação:

  ```bash
  WT=C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/feat-129-6-6-scorecard-profiles
  DRUN="MSYS_NO_PATHCONV=1 docker run --rm -v $WT:/app \
    -v C:/Users/Marcelo/Documents/Code/financial-forecasting/.git:/main.git \
    -v financial-forecasting_app-venv:/app/.venv \
    -e GIT_DIR=/main.git/worktrees/feat-129-6-6-scorecard-profiles -e GIT_WORK_TREE=/app \
    -w /app financial_forecasting-app:dev sh -c"
  # ex.: eval "$DRUN \"git config --global --add safe.directory '*'; make check-task SLICE=evaluation\""
  ```

- Gate por Task (T1): `make check-task SLICE=evaluation` + o pytest da Task;
  Checkpoint C a cada 2–3 Tasks com `make check-block` (T2); `make check` (T3) no
  gate de saída (RUNBOOK §Gates em camadas).
- **Cegamento (I14):** nenhum teste, script ou comando lê o `parent_sweep_id`
  do cohort real; todo dado é sintético.

### Estrutura de pastas afetada

```
config/preregistration/
├── aapl_confirmatory-r1.toml                                   # NOVO (19)
└── aapl_confirmatory-r1.anchor.toml                            # NOVO (22)
docs/
├── preregistration/aapl_confirmatory.md                        # MODIFICADO (19, 22)
├── adr/6_5_0008-*.md                                           # MODIFICADO (21)
└── roadmap.md                                                  # MODIFICADO (stage complete)
src/financial_forecasting/
├── composition_root.py                                         # MODIFICADO (17)
└── features/evaluation/
    ├── domain/
    │   ├── services/
    │   │   ├── diebold_mariano.py                              # MODIFICADO (02)
    │   │   ├── model_confidence_set.py                         # MODIFICADO (03)
    │   │   ├── pinball_score.py                                # MODIFICADO (04)
    │   │   ├── paired_pinball_losses.py                        # MODIFICADO (04)
    │   │   ├── series_assembly.py                              # MODIFICADO (05)
    │   │   ├── degeneracy_gate.py                              # MODIFICADO (06)
    │   │   ├── differential_stationarity.py                    # NOVO (09)
    │   │   ├── dm_profiles.py                                  # NOVO (10)
    │   │   ├── horizon_reports.py                              # MODIFICADO (11: hit_sequences público)
    │   │   └── profile_reports.py                              # NOVO (11)
    │   └── value_objects/
    │       ├── paired_loss_series.py                           # MODIFICADO (04)
    │       ├── assembled_cohort.py                             # MODIFICADO (05)
    │       ├── profile_parameters.py                           # NOVO (07)
    │       └── preregistration.py                              # MODIFICADO (08)
    ├── application/
    │   ├── dtos/
    │   │   ├── refresh_gold.py                                 # MODIFICADO (01, 12, 13)
    │   │   ├── gold_schema.py                                  # MODIFICADO (14, 15, 16)
    │   │   └── confirmatory_scorecard.py                       # MODIFICADO (12, 18)
    │   └── use_cases/
    │       ├── refresh_gold.py                                 # MODIFICADO (13)
    │       ├── scorecard_evidence.py                           # MODIFICADO (01)
    │       ├── scorecard_profile.py                            # MODIFICADO (01, 18)
    │       └── build_confirmatory_scorecard.py                 # MODIFICADO (01)
    └── adapters/out/duckdb/gold_builders/
        ├── dm_profiles.py, dm_seed_fraction.py                 # NOVOS (14)
        ├── mcs_block_sensitivity.py, christoffersen_monte_carlo.py  # NOVOS (15)
        └── partial_degeneracy.py, differential_acf.py,
            differential_breaks.py, loss_differentials.py       # NOVOS (16)
tests/
├── unit/features/evaluation/
│   ├── test_gold_cell_accessors.py                             # NOVO (01)
│   ├── test_dm_long_run_variance.py                            # NOVO (02)
│   ├── test_block_sensitivity_length.py                        # NOVO (03)
│   ├── test_paired_pinball_losses.py, test_paired_loss_series.py  # MODIFICADOS (04)
│   ├── test_adjacent_collapse_rates.py                         # NOVO (06)
│   ├── test_profile_parameters.py                              # NOVO (07)
│   ├── test_preregistration_value_object.py                    # MODIFICADO (08)
│   ├── test_differential_stationarity.py                       # NOVO (09)
│   ├── test_dm_profiles.py                                     # NOVO (10)
│   ├── test_profile_reports.py                                 # NOVO (11, 20)
│   ├── test_refresh_command_from.py                            # MODIFICADO (12)
│   ├── test_scorecard_profile.py                               # MODIFICADO (18)
│   └── gold/
│       ├── test_series_assembly.py, test_gold_value_objects.py # MODIFICADOS (05)
│       ├── test_refresh_gold_dtos.py                           # MODIFICADO (12, 13)
│       └── test_refresh_gold_use_case.py                       # MODIFICADO (12, 13)
├── contract/features/evaluation/
│   ├── _gold_inputs.py                                         # MODIFICADO (12, 13)
│   ├── test_gold_builder_contract.py                           # MODIFICADO (14, 15, 16)
│   └── test_profile_gold_builders.py                           # NOVO (14, 15, 16)
└── integration/features/evaluation/
    ├── test_refresh_gold.py                                    # MODIFICADO (12, 17)
    ├── test_dm_long_run_variance_vs_statsmodels.py             # NOVO (02)
    ├── test_differential_stationarity_vs_statsmodels.py        # NOVO (09)
    ├── test_profile_cost_measurement.py                        # NOVO (20, opt-in)
    ├── test_scorecard_profile_isolation.py                     # NOVO (18)
    ├── test_preregistration_consistency.py                     # MODIFICADO (19)
    └── test_profiles_end_to_end.py                             # NOVO (20)
```

## 2. Tasks

### Task 01 — Acessores tipados das células do gold (F6)

- **Arquivos a criar:**
  - `tests/unit/features/evaluation/test_gold_cell_accessors.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/refresh_gold.py`
  - `src/financial_forecasting/features/evaluation/application/use_cases/scorecard_evidence.py`
  - `src/financial_forecasting/features/evaluation/application/use_cases/scorecard_profile.py`
  - `src/financial_forecasting/features/evaluation/application/use_cases/build_confirmatory_scorecard.py`
- **O que fazer:** em `refresh_gold.py` (junto do `GoldGenerationCorruptError`),
  `col_int`, `col_float`, `col_str`, `col_bool` e as variantes `*_or_none`, com
  assinatura `(row, schema, column) -> T`. Cada uma confere a coluna contra o
  schema (mesma regra do `col`, que **passa a morar aqui**; os três use cases
  importam `col`/`col_*` direto de `application/dtos/refresh_gold.py`, sem
  reexport — mypy `no_implicit_reexport`) e o tipo pela política D9 do concept. Migrar toda leitura de célula
  dos três use cases para o acessor do tipo do schema.
- **Detalhes técnicos:**
  - `col_int`: `int` não-`bool`; `col_float`: `int` não-`bool` ou `float` →
    `float`; `col_bool`: `bool`; `col_str`: `str`; `*_or_none`: + `None`.
  - Tipo divergente → `GoldGenerationCorruptError(f"{schema.name}.{column}: expected
    <tipo>, got <tipo>")`; coluna fora do schema → `KeyError` (inalterado).
  - Remover todo `# type: ignore` dos três módulos (inclusive leituras por tupla
    de chave, ex. `model=key[0]`, e chamadas quebradas em várias linhas) e
    atualizar as docstrings que os justificavam.
- **Critério de aceite:**
  - Testes de cada aceite e de cada recusa (bool em `col_int`, int em
    `col_bool`, str em `col_float`, None sem `_or_none`), com o nome da tabela e
    da coluna na mensagem.
  - Suítes da 6.5 (`test_scorecard_*`, `test_build_confirmatory_scorecard*`)
    verdes sem alteração (regressão do veredito).
  - `grep -n "type: ignore" <3 módulos>` vazio (CA13).
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/unit/features/evaluation/test_gold_cell_accessors.py tests/unit/features/evaluation/test_scorecard_profile.py tests/unit/features/evaluation/test_scorecard_evidence.py tests/integration/features/evaluation/test_build_confirmatory_scorecard.py -q && make check-task SLICE=evaluation\""
  cd "$WT" && ! grep -n "type: ignore" src/financial_forecasting/features/evaluation/application/use_cases/{scorecard_evidence,scorecard_profile,build_confirmatory_scorecard}.py
  ```
- **Commit sugerido:** `refactor(evaluation): acessores tipados das células do gold [6.6/task-01]`

---

### Task 02 — `dm_long_run_variance` pública, compartilhada pelo DM e pelo CUSUM

- **Arquivos a criar:**
  - `tests/unit/features/evaluation/test_dm_long_run_variance.py`
  - `tests/integration/features/evaluation/test_dm_long_run_variance_vs_statsmodels.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/services/diebold_mariano.py`
- **O que fazer:** extrair do primitivo `diebold_mariano` a variância de d̄ com
  o fallback para `dm_long_run_variance(differences, *, horizon,
  variance_estimator) -> tuple[float, int]` (variância, `horizon_used`); o
  primitivo passa a chamá-la (uma escrita só — I1).
- **Detalhes técnicos:**
  - Comportamento idêntico ao atual: constante → 0,0 (sem calcular) e, com
    h > 1, o fallback leva a `horizon_used = 1`; ≤ 0 com h > 1 → recalcula com
    h = 1; devolve `(variância, horizon_used)`, **não** ergue
    (quem decide erguer é o primitivo, como hoje).
  - `_long_run_variance`/`_autocovariance` seguem privados e chamados só daqui.
- **Critério de aceite:**
  - `test_dm_vs_r_oracle.py`, `test_holm_vs_statsmodels.py` e
    `test_dm_r_oracle_fixtures.py` verdes sem alteração.
  - Unit (analítico): série com variância retangular negativa → `horizon_used
    == 1`; constante com h = 7 → `(0.0, 1)`; constante com h = 1 → `(0.0, 1)`.
  - Integração (oráculo): igualdade com
    `OLS(d, 1).fit().get_robustcov_results(cov_type="HAC", kernel="uniform",
    maxlags=h−1, use_correction=False).cov_params()[0, 0]` (já é var̂(d̄), divisor
    T aplicado — como no `statsmodels_hac.py`).
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/unit/features/evaluation/test_dm_long_run_variance.py tests/integration/features/evaluation/test_dm_long_run_variance_vs_statsmodels.py tests/unit/features/evaluation/test_dm_vs_r_oracle.py tests/integration/features/evaluation/test_dm_r_oracle_fixtures.py -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `refactor(evaluation): variância de longo prazo do DM como função pública [6.6/task-02]`

---

### Task 03 — `block_sensitivity_length`

- **Arquivos a criar:**
  - `tests/unit/features/evaluation/test_block_sensitivity_length.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/services/model_confidence_set.py`
- **O que fazer:** `block_sensitivity_length(rule: str, *, horizon: int,
  n_points: int) -> int`: `"h"` → `horizon`; `"sqrt_T"` → `math.isqrt` com teto
  (⌈√T⌉ exato, sem float); regra fora de `BLOCK_SENSITIVITIES` → `ValueError`.
- **Detalhes técnicos:** importar `BLOCK_SENSITIVITIES` do dono (hoje no
  `preregistration.py`) cria ciclo VO→serviço→VO; **mover** a constante para
  `model_confidence_set.py` e reexportá-la em `preregistration.py` (o VO já
  importa deste módulo).
- **Critério de aceite:** T ∈ {1500 → 39, 1521 → 39, 1522 → 40, 11 → 4}; h = 7;
  regra desconhecida (`"sqrt_t"`) → `ValueError`; horizonte/T inválidos →
  `ValueError` pelos validadores donos.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/unit/features/evaluation/test_block_sensitivity_length.py tests/unit/features/evaluation/test_preregistration_value_object.py -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): comprimento de bloco das sensibilidades do MCS [6.6/task-03]`

---

### Task 04 — Perda por τ, `paired_pinball_losses(level=)` e `PairedLossSeries.window`

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/services/pinball_score.py`
  - `src/financial_forecasting/features/evaluation/domain/services/paired_pinball_losses.py`
  - `src/financial_forecasting/features/evaluation/domain/value_objects/paired_loss_series.py`
  - `tests/unit/features/evaluation/test_paired_pinball_losses.py`
  - `tests/unit/features/evaluation/test_paired_loss_series.py`
- **O que fazer:**
  - `PinballScore.per_point_losses_at(series, level)`: ρ_τ por ponto (`pinball_loss`)
    sobre `scored_values`; nível fora da grade → `ValueError`.
  - `paired_pinball_losses(series_by_model, *, level: float | None = None)`:
    `None` mantém a média da grade; um nível usa `per_point_losses_at` (média
    entre seeds igual).
  - `PairedLossSeries.window(start, stop)`: fatia `[start, stop)` das colunas e
    dos timestamps (o VO revalida T ≥ 2 e T > h).
- **Critério de aceite:** média dos ρ_τ por ponto ≡ `per_point_losses` (igualdade
  com `math.fsum`/K); série por seed = `paired_pinball_losses({cand: (s,), ...})`
  sem mudança de código (teste documenta); janela preserva timestamps e perdas;
  janela curta → `ValueError` do VO.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/unit/features/evaluation/test_paired_pinball_losses.py tests/unit/features/evaluation/test_paired_loss_series.py tests/unit/features/evaluation/test_pinball_vs_oracle.py -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): perda por nível e janela da série pareada [6.6/task-04]`

---

### Task 05 — Fold na amostra comum (`HorizonSamples.common_folds`)

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/assembled_cohort.py`
  - `src/financial_forecasting/features/evaluation/domain/services/series_assembly.py`
  - `tests/unit/features/evaluation/gold/test_series_assembly.py`
  - `tests/unit/features/evaluation/gold/test_gold_value_objects.py`
- **O que fazer:** `HorizonSamples` ganha `common_folds: tuple[str | None, ...] |
  None` e `fold_mismatch_detail: str | None` (exatamente um dos dois "presente":
  `common_folds is None` ⇔ detalhe não-vazio; `common_folds` com `n_common`
  elementos). `_Point` passa a carregar o fold (de `ForecastRecord.fold`; um ponto
  com folds distintos entre níveis é o mesmo caso de divergência). Em
  `_build_samples`, para cada alvo da amostra comum, o fold de todas as séries
  (todos os modelos e seeds) — iguais → rótulo; senão `common_folds = None` e o
  detalhe com o primeiro alvo divergente. **Nenhum achado novo**; `AlignmentKind`
  inalterado.
- **Critério de aceite:** (CA1) folds de tamanhos distintos; `fold = None` em
  todos os runs → tupla de `None`; um modelo com rótulo trocado num alvo →
  `common_folds is None`, `alignment.findings == ()` e horizontes montados;
  VO recusa tamanho errado e a combinação incoerente.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/unit/features/evaluation/gold -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): montagem carrega o fold da amostra comum [6.6/task-05]`

---

### Task 06 — `adjacent_collapse_rates` no módulo do gate

- **Arquivos a criar:**
  - `tests/unit/features/evaluation/test_adjacent_collapse_rates.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/services/degeneracy_gate.py`
- **O que fazer:** função pública `adjacent_collapse_rates(series, *, tolerance)
  -> tuple[tuple[float, float, float | None], ...]`: para cada (τ_k, τ_{k+1}) da
  grade, a fração das linhas **não-degeneradas** (mesma regra do gate:
  `max − min ≤ tolerance`, extraída para um helper privado usado pelos dois) com
  `q_{k+1} − q_k ≤ tolerance`; `None` sem linha não-degenerada. `DegeneracyReport`
  e `DegeneracyGate.evaluate` **não mudam** (caminho do veredito).
- **Critério de aceite:** (CA6) fixtures analíticas: `q_0,25 = q_0,5 < q_0,75`
  (colapso adjacente, nenhum simétrico); gaps internos ≤ tol somando > tol
  (adjacentes colapsados, simétrico não); série 100 % degenerada → todos `None`;
  `test_degeneracy_gate.py` inalterado e verde.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/unit/features/evaluation/test_adjacent_collapse_rates.py tests/unit/features/evaluation/test_degeneracy_gate.py -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): taxa de colapso por par adjacente da grade [6.6/task-06]`

---

### Task 07 — VO `ProfileParameters` e catálogo de regras de perfil

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/profile_parameters.py`
  - `tests/unit/features/evaluation/test_profile_parameters.py`
- **O que fazer:** `PROFILE_RULE_CATALOG` (chave pontuada → único identificador
  implementado) e os VOs frozen `StationarityParameters(acf_max_lag, break_test,
  break_alpha)` e `ProfileParameters(subset_multiplicity, partial_degeneracy_pairs,
  mcs_block_sensitivity_scheme, stationarity)`, com `as_payload` (forma do TOML,
  JSON-safe; a **única** serialização, usada também no manifesto) e
  `from_mapping` (a inversa).
- **Detalhes técnicos — identificadores (fonte: concept D2, D3, D5, D10):**
  - `subset_multiplicity = "none_raw_p_descriptive_v1"`
  - `partial_degeneracy_pairs = "symmetric_and_adjacent_non_degenerate_rows_v1"`
  - `mcs_block_sensitivity_scheme = "primary_scheme"`
  - `stationarity.acf_max_lag = "min_floor_10_log10_T_T_minus_1"`
  - `stationarity.break_test = "cusum_mean_dm_primary_variance_kolmogorov_v1"`
  - `break_alpha` pelo `validate_alpha`.
  - Chave ausente/desconhecida → `ValueError` com o caminho pontuado
    (`profile_parameters.stationarity.acf_max_lag`), mesmo padrão do
    `Preregistration`; identificador ≠ catálogo → `ValueError` "only rule the
    domain implements".
- **Critério de aceite:** `from_mapping(as_payload()) == vo`; cada recusa; float de
  `break_alpha` aceita `int` não-`bool` e guarda `float`.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/unit/features/evaluation/test_profile_parameters.py -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): regras nomeadas dos perfis do scorecard [6.6/task-07]`

---

### Task 08 — `Preregistration` aceita `[profile_parameters]` (opcional)

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/preregistration.py`
  - `tests/unit/features/evaluation/test_preregistration_value_object.py`
  - `tests/unit/features/evaluation/test_preregistration_immutable_hash.py`
- **O que fazer:** campo `profile_parameters: ProfileParameters | None`; chave de
  topo opcional `profile_parameters` em `_OPTIONAL_KEYS` (conferida pelo
  `ProfileParameters.from_mapping`); `as_payload` só a escreve quando presente
  (como `blinding_statement`).
- **Critério de aceite:** (I11) hash do r0 (arquivo versionado) idêntico ao
  citado no espelho; plano com o bloco tem hash diferente e ida e volta
  `from_mapping(as_payload())`; regra fora do catálogo no bloco → `ValueError`;
  qualquer campo do bloco alterado muda o hash.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/unit/features/evaluation/test_preregistration_value_object.py tests/unit/features/evaluation/test_preregistration_immutable_hash.py tests/integration/features/evaluation/test_preregistration_consistency.py -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): pré-registro aceita o bloco de regras de perfil [6.6/task-08]`

---

### Task 09 — `DifferentialStationarity` contra oráculo

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/differential_stationarity.py`
  - `tests/unit/features/evaluation/test_differential_stationarity.py`
  - `tests/integration/features/evaluation/test_differential_stationarity_vs_statsmodels.py`
- **O que fazer:** primitivos `sample_acf(values, max_lag)`,
  `acf_max_lag(n_points)` (= min(⌊10·log10 T⌋, T − 1), inteiro exato),
  `kolmogorov_sf(x)` e `cusum_mean_break(differences, *, horizon,
  variance_estimator)`; o serviço `DifferentialStationarity.evaluate(series, *,
  parameters, variance_estimator) -> tuple[StationarityReport, ...]` (um por par
  de `model_pairs()`), com `StationarityReport` frozen (par, horizon, n_points,
  status `computed`|`undefined`, undefined_reason, differential, acf, max_lag,
  statistic, p_value, rejected, alpha, horizon_used, break_target_timestamp).
- **Detalhes técnicos:**
  - CUSUM: S_k = Σ_{t≤k}(d_t − d̄); B = max_k |S_k| / (T·√var), `var` de
    `dm_long_run_variance` (Task 02); argmax → `break_target_timestamp` (primeiro
    em empate).
  - `kolmogorov_sf`: x ≤ 0 → 1; x < 1,18 → 1 − (√(2π)/x)·Σ_{j≥1} e^{−(2j−1)²π²/(8x²)};
    senão 2Σ_{j≥1}(−1)^{j−1}e^{−2j²x²}; soma até termo < 1e-17; clamp em [0, 1].
  - d_t constante → `undefined` (`constant_differential`); T < 2 impossível
    (o VO já garante T ≥ 2).
  - `parameters` chega já válido (o VO é o dono do catálogo — §1).
- **Critério de aceite (CA7):** oráculos no teste `_vs_statsmodels`:
  ACF vs `acf(adjusted=False, fft=False, nlags=L)`; em h = 1 `statistic`/`p_value`
  vs `breaks_cusumolsresid(d − d̄, ddof=0)`; em h = 7 vs composição no teste,
  B = max|cumsum(d − d̄)| / (T·√v), v = `cov_params()[0, 0]` do HAC uniforme
  `maxlags=6`, `use_correction=False` (já é var̂(d̄)), inclusive com
  série que força o fallback; `kolmogorov_sf` vs `kstwobign.sf` na grade
  {0,05; 0,1; 0,2; 0,3; 1; 1,18; 1,36; 3}, tolerância 1e-12. Unit: degrau de
  média → quebra no alvo do degrau; T = 3 → L = 2; constante → `undefined`.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/unit/features/evaluation/test_differential_stationarity.py tests/integration/features/evaluation/test_differential_stationarity_vs_statsmodels.py -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): diagnóstico de estacionariedade do diferencial de perdas [6.6/task-09]`

---

### Task 10 — `DmProfiles` (DM por fold, seed e τ)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/dm_profiles.py`
  - `tests/unit/features/evaluation/test_dm_profiles.py`
- **O que fazer:** `DmProfiles.evaluate(samples: HorizonSamples, *, candidate,
  alpha, variance_estimator) -> DmProfilesReport`, com VOs frozen
  `DmSubsetRow` (dimension `fold`|`seed`|`tau`, fold, seed, level, comparator,
  status, undefined_reason, detail, `DieboldMarianoResult | None`, rejected) e
  `SeedFractionRow` (comparator, n_seeds, n_rejecting, n_undefined, fraction).
- **Detalhes técnicos:**
  - Base: `paired_pinball_losses({m: samples.common[m]})` (a mesma da primária).
  - Fold: `common_folds is None` → uma linha por comparador, `fold = None`,
    `fold_label_mismatch`; senão runs contíguos de rótulo em ordem temporal;
    rótulo em > 1 run → uma linha por (rótulo, comparador) `fold_not_contiguous`;
    cada run → `window` e um `DieboldMariano.compare` por comparador.
  - Seed: para cada seed s do candidato, `paired_pinball_losses` com
    `{candidate: (common[candidate][i],), outros: common[outros]}`.
  - τ: `paired_pinball_losses(..., level=τ)` para cada nível da grade.
  - Pré-checagens antes da chamada: `check_points` → `too_short`; `is_constant` do
    diferencial → `constant_differential` (o recorte inteiro fica `undefined` se
    algum comparador cai aqui? **não**: a unidade é (recorte, comparador));
    `ValueError`/`ArithmeticError` **da chamada** `DieboldMariano.compare` →
    `error` + mensagem (só a chamada dentro do `try`).
  - `rejected` ⇔ `p_value ≤ alpha`; fração = n_rejecting / (n_seeds −
    n_undefined), `None` se o denominador é 0.
- **Critério de aceite (CA3):** fold único = amostra inteira reproduz
  `statistic`/`p_value` da `HolmCorrection.family` primária; nenhum Holm
  (rejeição com p entre α/m e α é `True`); os quatro motivos `undefined`; fração
  com uma seed indefinida e com todas.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/unit/features/evaluation/test_dm_profiles.py -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): DM por fold, seed e nível como perfil descritivo [6.6/task-10]`

---

### Task 11 — `ProfileReports` (composição, Monte Carlo, degeneração, isolamento)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/profile_reports.py`
  - `tests/unit/features/evaluation/test_profile_reports.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/services/horizon_reports.py`
- **O que fazer:** `ProfileReports.evaluate(samples, *, horizon_report, paired,
  candidate, alpha, variance_estimator, min_violations, tolerance, draws, seed,
  profile_parameters: ProfileParameters | None) -> HorizonProfileReport` com:
  `differentials` (d_t por par de `paired.model_pairs()`, sempre, com o fold do
  ponto quando `common_folds` existe), `monte_carlo` (h = 1 só: para cada
  (modelo, seed, amostra) e cada sequência não-DGT de `hit_sequences(series,
  tolerance)`, `ChristoffersenTest.monte_carlo_p_values`), e — só com
  `profile_parameters` — `dm_profiles`, `stationarity`, `partial_degeneracy`
  (simétricos de `horizon_report.series[*].coverage.degeneracy.pair_collapse_rates`
  + adjacentes de `adjacent_collapse_rates`); `error_units` (contagem).
- **Detalhes técnicos:**
  - Tornar público em `horizon_reports.py` o gerador `_hit_sequences` →
    `hit_sequences` (mesma ordem; `HorizonReports` passa a chamar o público) —
    uma escrita só das sequências testadas.
  - Isolamento (I4): helper único `_guarded(call) -> (valor | None, detalhe)` que
    envolve **só** a chamada ao serviço (`monte_carlo_p_values`,
    `DifferentialStationarity.evaluate` por par, `adjacent_collapse_rates`);
    `DmProfiles` já isola as suas. Unidade que falha vira linha com status
    `error`.
  - Sem `profile_parameters`: `dm_profiles`, `stationarity` e
    `partial_degeneracy` são `None` (estado "não congelado", I9).
- **Critério de aceite:** MC só em h = 1 e sem DGT, célula a célula igual à
  chamada direta (CA5); `not_applicable` de série 100 % degenerada repassado;
  simétricos = `pair_collapse_rates` (CA6); falha injetada (serviço substituído
  por um que ergue `ValueError`) em cada tipo de unidade → linha `error`;
  sequência que atinge o teto de tentativas → status do `MonteCarloPValues`
  repassado (`ind_status` de teto);
  `error_units` contado, demais unidades intactas; com `None` só MC e
  diferenciais; `HorizonReports` inalterado (suíte verde).
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/unit/features/evaluation/test_profile_reports.py tests/unit/features/evaluation/gold/test_horizon_reports.py -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): composição dos perfis por horizonte com isolamento de falha [6.6/task-11]`

---

### Task 12 — `RefreshParameters` com MC, blocos e regras de perfil (F8a)

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/refresh_gold.py`
  - `src/financial_forecasting/features/evaluation/application/dtos/confirmatory_scorecard.py`
  - `tests/unit/features/evaluation/test_refresh_command_from.py`
  - `tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py`
  - `tests/unit/features/evaluation/test_scorecard_evidence_mapper.py` (testes do `check_manifest` por campo)
  - construções de `RefreshParameters` nos testes: `tests/contract/features/evaluation/{_gold_inputs,test_gold_generation_reader_contract,test_gold_store_contract}.py`, `tests/integration/features/evaluation/test_refresh_gold.py`, `tests/unit/features/evaluation/gold/test_refresh_gold_use_case.py` (exceção ao teto de arquivos — §1)
- **O que fazer:** campos `monte_carlo_draws`, `monte_carlo_seed`,
  `mcs_block_sensitivities`, `profile_parameters`; `__post_init__` pelos donos
  (`validate_draws_and_seed`, `BLOCK_SENSITIVITIES`, tipo `ProfileParameters`);
  `as_mapping`/`from_mapping` com as chaves novas (obrigatórias;
  `profile_parameters` `null` ou o `as_payload()` do VO); `refresh_command_from`
  preenche do plano (`prereg.monte_carlo`, `prereg.mcs.block_sensitivities`,
  `prereg.profile_parameters`). Na fixture `_gold_inputs.py`, `PARAMETERS`
  ganha `profile_parameters` com a forma da r1 (para que os builders das Tasks
  14–16 produzam linhas no contract test).
- **Critério de aceite (CA9):** r0 → `profile_parameters is None` e MC/blocos
  do r0; plano com bloco → o bloco; `check_manifest` recusa divergência em cada
  campo novo (um teste por campo, `MismatchField.PARAMETERS`); manifesto sem uma
  chave nova → `GoldGenerationCorruptError` via `GoldGeneration.from_stored`;
  `"sqrt_t"`, draws/seed inválidos e regra fora do catálogo recusados no
  `__post_init__`.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/unit/features/evaluation tests/contract/features/evaluation tests/integration/features/evaluation/test_refresh_gold.py -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): parâmetros de perfil na derivação única do refresh [6.6/task-12]`

---

### Task 13 — `RefreshGold` calcula perfis e MCS por bloco

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/refresh_gold.py`
  - `src/financial_forecasting/features/evaluation/application/use_cases/refresh_gold.py`
  - `tests/unit/features/evaluation/gold/test_refresh_gold_use_case.py`
  - `tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py`
  - `tests/contract/features/evaluation/_gold_inputs.py`
- **O que fazer:**
  - DTOs: `McsBlockRun` (horizon, block_rule, block_size, `McsReport | None`,
    status, undefined_reason, detail); `GoldInputs` ganha `profile_reports:
    tuple[HorizonProfileReport, ...]` e `mcs_block_reports: tuple[McsBlockRun, ...]`
    (vazios se `BLOCKED`, coerência no `__post_init__`); `RefreshGoldResult` ganha
    `profile_error_units: int`.
  - Fixture `_gold_inputs.py`: `completed_inputs()` passa a trazer
    `profile_reports` e `mcs_block_reports` (com a r1 de `PARAMETERS`, todos os
    perfis com linhas); nova `completed_inputs_r0()` (sem `profile_parameters`)
    para os critérios "r0 → zero linhas".
  - Use case: etapa `profiles` depois de `reports`/`mcs` (só não-bloqueado):
    `ProfileReports.evaluate` por horizonte; etapa `mcs_blocks`: com
    `profile_parameters`, para cada regra de `mcs_block_sensitivities`,
    `block_sensitivity_length` → `bootstrap_indices` no `mcs_primary_scheme`
    (o primeiro de `mcs_schemes`, regra `primary_scheme`) → `ModelConfidenceSet.evaluate`,
    só a chamada ao backend e ao `evaluate` dentro da captura (`ValueError`/
    `ArithmeticError` → `McsBlockRun` `error`). Uma linha `INFO` por etapa
    (padrão `_timed`). `profile_error_units` = soma.
- **Critério de aceite:** com o `_SpyBackend` local do teste (estendido para
  registrar `block_size` e erguer para um `block_size` escolhido — o
  `FakeMcsBackend` **não** muda, fake-parity intacto) e o `FakeGoldBuilder`:
  blocos h e ⌈√T⌉ chegam ao backend; falha do backend numa regra →
  `McsBlockRun` `error`, a outra regra e o MCS primário intactos; r0 (sem bloco)
  → `mcs_block_reports == ()` e só MC/diferenciais nos perfis; `BLOCKED` →
  perfis vazios. **Falha injetada por tipo** (parametrizado: Monte Carlo,
  estacionariedade, colapso adjacente, DM por recorte — `monkeypatch` do serviço
  no módulo `profile_reports`/`dm_profiles` — e MCS por bloco pelo spy): os
  relatórios do veredito nos `GoldInputs` (`horizon_reports`, `mcs_reports`,
  `check_results`, `block_estimates`) idênticos aos de uma execução sem falha e
  `profile_error_units` = unidades afetadas (CA11, lado da escrita). A asserção
  de chamadas ao backend (`len(calls)`) é atualizada para incluir as rodadas por
  bloco.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/unit/features/evaluation/gold tests/contract/features/evaluation -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): refresh do gold calcula os perfis de séries novas [6.6/task-13]`

---

### Task 14 — Builders `dm_profiles` e `dm_seed_fraction`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/dm_profiles.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/dm_seed_fraction.py`
  - `tests/contract/features/evaluation/test_profile_gold_builders.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/gold_schema.py`
  - `tests/contract/features/evaluation/test_gold_builder_contract.py`
  - `tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py` (conjunto exato de `GOLD_SCHEMAS`/`CONFIRMATORY_TABLES`)
- **O que fazer:** `GOLD_DM_PROFILES` (key horizon, dimension, fold, seed, level,
  comparator; read_columns status, undefined_reason, detail, n_points,
  first_target_timestamp, last_target_timestamp, variance_estimator,
  mean_differential, statistic, p_value, rejected, fallback_applied,
  horizon_used, alpha) e `GOLD_DM_SEED_FRACTION`
  (key horizon, comparator; read n_seeds, n_rejecting, n_undefined,
  fraction_rejecting, alpha); ambos em `GOLD_SCHEMAS` e `CONFIRMATORY_TABLES`;
  builders `depends_on = {QUALITY_CHECKS}`, `runs_when_blocked = False`,
  mapeando `inputs.profile_reports`.
- **Critério de aceite:** contract test parametrizado com os dois ids novos;
  mapeamento célula a célula; casos `fold_label_mismatch` e
  `fold_not_contiguous` sem chave repetida (passam pelo `GoldTable`);
  `completed_inputs_r0()` → zero linhas.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/contract/features/evaluation tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): tabelas gold do DM por recorte e da fração de seeds [6.6/task-14]`

---

### Task 15 — Builders `mcs_block_sensitivity` e `christoffersen_monte_carlo`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/mcs_block_sensitivity.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/christoffersen_monte_carlo.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/gold_schema.py`
  - `tests/contract/features/evaluation/test_gold_builder_contract.py`
  - `tests/contract/features/evaluation/test_profile_gold_builders.py`
  - `tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py`
- **O que fazer:** `GOLD_MCS_BLOCK_SENSITIVITY` (key horizon, block_rule, model;
  read status, undefined_reason, detail, scheme, block_size, elimination_rank,
  step_p_value, mcs_p_value, included, alpha, reps, seed, n_points; run
  `undefined` → uma linha com `model = None` e as colunas do MCS nulas) e
  `GOLD_CHRISTOFFERSEN_MONTE_CARLO` (key model, seed, horizon, sample, kind,
  level_low, level_high, includes_degenerate; read status (`computed`|`error`
  da unidade), detail, uc_status, ind_status (os dois status do
  `MonteCarloPValues`, pelo valor), mc_p_uc, mc_p_ind, mc_p_cc, draws, mc_seed,
  uc_attempts, ind_attempts); builders como na Task 14.
- **Critério de aceite:** contract test com os ids novos; MC sem linha de h = 7;
  célula a célula com os relatórios (inclusive `uc_status`/`ind_status`); run
  `undefined` mapeado.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/contract/features/evaluation tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): tabelas gold do MCS por bloco e do Monte Carlo de Christoffersen [6.6/task-15]`

---

### Task 16 — Builders de degeneração parcial e de d_t

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/partial_degeneracy.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/differential_acf.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/differential_breaks.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/loss_differentials.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/gold_schema.py`
  - `tests/contract/features/evaluation/test_gold_builder_contract.py`
  - `tests/contract/features/evaluation/test_profile_gold_builders.py`
  - `tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py`
- **O que fazer:** `GOLD_PARTIAL_DEGENERACY` (key model, seed, horizon, sample,
  pair_kind, level_low, level_high; read status, detail, collapse_rate,
  tolerance; série cuja taxa adjacente falhou → uma linha `error` por
  (modelo, seed, amostra) com `pair_kind = "adjacent"` e níveis nulos),
  `GOLD_DIFFERENTIAL_ACF` (key horizon, model_a, model_b, lag; read acf,
  n_points, max_lag), `GOLD_DIFFERENTIAL_BREAKS` (key horizon, model_a,
  model_b; read status, undefined_reason, detail, statistic, p_value, rejected,
  alpha, horizon_used, break_target_timestamp, n_points, max_lag) e `GOLD_LOSS_DIFFERENTIALS` (key horizon,
  model_a, model_b, target_timestamp; read fold, differential); quatro builders.
  (Exceção declarada: 8 arquivos — quatro builders triviais, mapeamento puro.)
- **Critério de aceite:** contract test com os quatro ids; simétricos célula a
  célula com `pair_collapse_rates`; `completed_inputs_r0()` →
  `partial_degeneracy`, `acf` e `breaks` vazias e `loss_differentials` cheia.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/contract/features/evaluation tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): tabelas gold da degeneração parcial e do diferencial de perdas [6.6/task-16]`

---

### Task 17 — Composition root e integração do refresh (CA10)

- **Arquivos a modificar:**
  - `src/financial_forecasting/composition_root.py`
  - `src/financial_forecasting/features/evaluation/application/dtos/refresh_gold.py`
  - `tests/unit/shared/test_composition_root.py` (fixa `refresh.build_order` — passa a 13 builders)
  - `tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py`
  - `tests/integration/features/evaluation/test_refresh_gold.py`
  - `tests/unit/features/evaluation/_scorecard_factory.py` (`make_stored()` passa a gerar as 13 tabelas coerentes; docstring atualizada)
  - `tests/contract/features/evaluation/test_gold_generation_reader_contract.py` (`_generation()` monta COMPLETED com subconjunto)
  (Exceção declarada: 7 arquivos — os dois helpers montam geração `COMPLETED`
  por `from_stored` e quebram com a regra nova.)
- **O que fazer:** registrar os oito builders no `RefreshGold` do composition
  root; em `GoldGeneration.from_stored` (dono da montagem da geração lida), regra
  nova: manifesto `COMPLETED` precisa listar **toda** tabela de `GOLD_SCHEMAS`,
  senão `GoldGenerationCorruptError`; manifesto `BLOCKED` não pode listar tabela
  de `CONFIRMATORY_TABLES` (as que rodam bloqueadas = `set(GOLD_SCHEMAS) −
  set(CONFIRMATORY_TABLES)`, sem o DTO conhecer builders); integração (silver sintético, adapters reais de arquivo):
  as oito tabelas na mesma geração, no `rows_by_table` e passando no
  `check_generation`; refresh `BLOCKED` sem elas; geração gravada e depois
  podada de uma tabela (manifesto + arquivo) → `read_generation` ergue
  `GoldGenerationCorruptError`.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/integration/features/evaluation/test_refresh_gold.py -q && make check-block\""
  ```
- **Commit sugerido:** `feat(evaluation): builders de perfil no composition root [6.6/task-17]`

---

### Task 18 — `ScorecardProfile` lê os perfis; estados; I12

- **Arquivos a criar:**
  - `tests/integration/features/evaluation/test_scorecard_profile_isolation.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/confirmatory_scorecard.py`
  - `src/financial_forecasting/features/evaluation/application/use_cases/scorecard_profile.py`
  - `tests/unit/features/evaluation/test_scorecard_profile.py`
  - `tests/unit/features/evaluation/_scorecard_factory.py`
  - `tests/unit/features/evaluation/test_build_confirmatory_scorecard_use_case.py` (constrói `ScorecardProfile`)
- **O que fazer:** DTOs de linha de perfil (§4 do concept) e `profile_states`
  em `ScorecardProfile`; `build_profile` lê as oito tabelas pelos acessores
  tipados (exceto `gold_loss_differentials`, insumo de plot) e copia as linhas
  por horizonte; estado por perfil declarado: `not_built_here` se em
  `NOT_BUILT_HERE` (= `{"sharpness_diagram"}`), `not_frozen_in_revision` se
  `prereg.profile_parameters is None` e o perfil é um dos sete do I9, senão
  `built`; `declared_not_built` = os `not_built_here`; `as_mapping` serializa tudo.
- **Critério de aceite (CA11, CA12):** leitor espião (`GoldGeneration` que
  registra `table(schema)`) prova que `evidence_from_generation` e
  `ConfirmatoryScorecard.decide` não leem nenhum schema novo; veredito idêntico
  com tabelas de perfil vazias, com conteúdo adversarial (MCS por bloco excluindo
  o candidato; nenhum DM por fold rejeitando) e, na camada evidência + `decide`,
  sem elas (`GoldGeneration(manifest=..., tables=...)` construído direto, sem
  `from_stored`, que recusaria a geração incompleta); r1 → `built` (inclusive com tabela vazia legítima) e
  `declared_not_built == ("sharpness_diagram",)`; r0 → sete
  `not_frozen_in_revision` e MC `built`.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/unit/features/evaluation/test_scorecard_profile.py tests/integration/features/evaluation -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): perfil do scorecard lê as tabelas de séries novas [6.6/task-18]`

---

### Task 19 — Emenda cega r1, espelho e consistência (F8e)

- **Arquivos a criar:**
  - `config/preregistration/aapl_confirmatory-r1.toml`
- **Arquivos a modificar:**
  - `docs/preregistration/aapl_confirmatory.md`
  - `tests/integration/features/evaluation/test_preregistration_consistency.py`
- **O que fazer:** r1 = cópia do r0 com `revision = 1`, `amends` = referência
  do r0 (`aapl_confirmatory-r0-4526c437c296`), `justification` (as regras de
  perfil que o r0 não nomeia — auditoria F7, ADR 6.6.0001), `blind_status =
  "blinded"` e `[profile_parameters]` com os identificadores da Task 07 e
  `break_alpha = 0.05`. Espelho: seção "Revisão r1" com o hash completo, o que
  muda e a declaração de cegamento. Teste: lista de revisões `[r0, r1]`;
  `test_r1_equals_r0_except_amendment` (todo campo igual exceto `revision`,
  `amends`, `justification`, `blind_status`, `profile_parameters`); a cadeia
  r0 → r1 lida pelo `TomlPreregistrationSource`.
- **Critério de aceite (CA8, menos a âncora):** os testes acima; hash do r0
  inalterado.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/integration/features/evaluation/test_preregistration_consistency.py -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `feat(evaluation): emenda cega r1 com as regras dos perfis [6.6/task-19]`

---

### Task 20 — e2e sobre silver sintético e medição de custo (CA14, CA17)

- **Arquivos a criar:**
  - `tests/integration/features/evaluation/test_profiles_end_to_end.py`
  - `tests/integration/features/evaluation/test_profile_cost_measurement.py`
- **Arquivos a modificar:**
  - `tests/unit/features/evaluation/test_profile_reports.py`
- **O que fazer:** e2e: silver sintético (2 folds, 2 seeds do candidato,
  h ∈ {1, 7}) → `RefreshGold` com adapters reais de arquivo pela
  `refresh_command_from(r1)` (plano sintético com o bloco) → oito tabelas,
  `profile_error_units == 0`, toda unidade `computed` → `BuildConfirmatoryScorecard`
  devolve o perfil completo; repetir com o plano sem bloco (as seis tabelas do I9
  vazias). Medição **opt-in**
  (`tests/integration/features/evaluation/test_profile_cost_measurement.py`,
  `skipif` sem a variável `MEASURE_PROFILE_COST=1` — fora de `check-block`,
  `make check` e CI, cujo job tem timeout de 30 min): `ProfileReports` sobre
  amostras sintéticas com a forma do r0 (6 × 252, 10 seeds, 7 modelos,
  h ∈ {1, 7}), tempo total e do MC impressos, **zero unidades `error`**;
  resultado registrado em §7. Um smoke pequeno do mesmo caminho fica na suíte
  normal (`test_profile_reports.py`).
- **Critério de aceite:** e2e verde; zero `error`; tempo do MC registrado (> 30 min
  → parar e perguntar); `grep -rn "aapl_confirmatory-r0-665f45d9169a" tests/` sem
  uso como `parent_sweep_id` de leitura (só nos testes de consistência do plano).
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/integration/features/evaluation/test_profiles_end_to_end.py -q && MEASURE_PROFILE_COST=1 uv run --no-sync pytest tests/integration/features/evaluation/test_profile_cost_measurement.py -s -q && make check-task SLICE=evaluation\""
  cd "$WT" && ! grep -rn "aapl_confirmatory-r0-665f45d9169a" tests/ --include=*.py | grep -v test_preregistration_consistency
  ```
- **Commit sugerido:** `test(evaluation): e2e dos perfis e custo do Monte Carlo [6.6/task-20]`

---

### Task 21 — Nota datada no ADR 6.5.0008

- **Arquivos a modificar:**
  - `docs/adr/6_5_0008-profiles-declared-in-preregistration-built-where-inputs-exist.md`
- **O que fazer:** nota datada (2026-10-06) no topo do `## Status`: o follow-up
  do item 3 virou a Stage 6.6 (#129); "with its parameters" e "no amendment
  needed" corrigidos — a tolerância da degeneração e os valores do MC/blocos
  estavam no r0, as regras do diagnóstico de d_t, da multiplicidade dos
  recortes, dos pares da degeneração e do esquema da sensibilidade de bloco não;
  congeladas pela r1 (ADR 6.6.0001). `updated_at` atualizado.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; make docs-check\""
  ```
- **Commit sugerido:** `docs(evaluation): nota datada no ADR 6.5.0008 sobre a Stage 6.6 [6.6/task-21]`

---

### Task 22 — Âncora da r1 (última antes do PR)

- **Arquivos a criar:**
  - `config/preregistration/aapl_confirmatory-r1.anchor.toml`
- **Arquivos a modificar:**
  - `docs/preregistration/aapl_confirmatory.md`
  - `tests/integration/features/evaluation/test_preregistration_consistency.py`
- **O que fazer (ADR 6.5.0003, depois da Auditoria de Testes e com a r1
  inalterada desde a Task 19):** `git tag preregistration/<ref-r1> <commit da
  Task 19>`; `git push origin <tag>`; comentário na #129 com `preregistration_ref`,
  hash completo, tag, commit, `cohort_id` e hash do cohort; ler `created_at` do
  comentário pela API (`gh api`) e gravar `.anchor.toml` (tag, commit,
  comment_url, anchored_at); seção "Âncora r1" no espelho; teste: âncora da r1
  existe e `anchored_at(r1) > anchored_at(r0)`.
- **Critério de aceite:** CA8 completo; em `test_preregistration_consistency.py`,
  `test_r1_anchor_after_r0`: o `TomlPreregistrationSource` lê r0 e r1 com âncora
  (o insumo que o `BuildConfirmatoryScorecard` confere para não erguer
  `PreregistrationNotAnchoredError`) e `anchored_at(r1) > anchored_at(r0)`.
- **Comando de verificação:**
  ```bash
  eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/integration/features/evaluation/test_preregistration_consistency.py -q && make check-task SLICE=evaluation\""
  ```
- **Commit sugerido:** `chore(evaluation): âncora da revisão r1 do pré-registro [6.6/task-22]`

## 3. Gate de saída da Stage

### Verificações automatizadas
```bash
eval "$DRUN \"git config --global --add safe.directory '*'; make check\""
eval "$DRUN \"git config --global --add safe.directory '*'; uv run --no-sync pytest tests/ --cov=src/financial_forecasting --cov-report=term-missing -q\""
python scripts/check_technical_postexec.py docs/stages/6.6-scorecard-profiles/technical.md
```

### Verificações funcionais
- [ ] e2e da Task 20: `RefreshGold` real sobre silver sintético publica as oito
  tabelas e o `BuildConfirmatoryScorecard` pela r1 devolve o perfil completo.
- [ ] Custo do MC medido e registrado em §7 (CA17).

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch; cobertura ≥ 90 % global e por arquivo tocado
- [ ] Checkpoints A/B/C e Auditoria de Testes com achados dispostos
- [ ] r1 ancorada (Task 22)
- [ ] Commit final `stage 6.6: complete` com o `roadmap.md` (6.6 `done`, DoD
      reescrito pelo D5, 8.1 com a 6.6 satisfeita e "julga pela r1",
      `updated_at`/`last_reviewed_at`)
- [ ] ADRs 6.6.0001–0003 `accepted`
- [ ] `concept.md` sem retoque retrospectivo pendente

## 4. Ordem de dependência entre Tasks

```
01 ─────────────────────────────────────────────► 18
02 ─► 09 ─┐
03 ───────┼─► 13 ─► 14 ─► 15 ─► 16 ─► 17 ─► 18 ─► 20 ─► 21 ─► (auditoria) ─► 22
04 ─► 10 ─┤
05 ─► 10  │
06 ─► 11 ─┤
07 ─► 08 ─┼─► 12 ─► 13
07 ─► 09, 07 ─► 11
09,10 ─► 11
08 ─► 19 ─► 20
```

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Mover `BLOCK_SENSITIVITIES` quebra import do VO (ciclo) | reexportar no `preregistration.py`; se o ciclo persistir, constante num módulo `_block_rules.py` em `value_objects` |
| `kolmogorov_sf` diverge do `kstwobign` perto do corte 1,18 | ajustar o ponto de troca (ambas as séries convergem ali); registrar `[deviation]` |
| MC lento demais na forma do r0 (> 30 min) | parar e perguntar (problema de desenho — concept CA17) |
| `HorizonSamples` com campo novo quebra fixtures de outros slices | só o slice evaluation constrói `HorizonSamples` (grep na Task 05) |
| Comentário da âncora falha (rede/permissão) | não gravar `.anchor.toml`; repetir; nunca inventar `anchored_at` |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage
- [`../../overview.md`](../../overview.md), [`../../roadmap.md`](../../roadmap.md)
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — branches, commits, status
- ADRs desta Stage: [`6.6.0001`](../../adr/6_6_0001-stationarity-diagnostic-acf-and-dm-variance-cusum-frozen-by-blinded-r1.md), [`6.6.0002`](../../adr/6_6_0002-profile-tables-isolated-from-the-verdict.md), [`6.6.0003`](../../adr/6_6_0003-dm-subsets-fold-from-run-raw-p-descriptive.md)
- Skills aplicáveis: ddd-tactical-patterns, hex-arch-python, composition-root, orchestrator-design, evidence-resolution, dmls-ch05-model-development-and-evaluation, task-ordering-hex, pytest-with-fakes

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

### 2026-10-06 — [decision] Checkpoints A e B — disposições — Claude (Opus 5.5)
**Contexto:** revisão por subagentes independentes do concept (A, 3 rodadas, 2
revisores na 1ª) e deste technical (B, 3 rodadas, 2 revisores na 1ª, escalada
por Stage pesada). Todos os achados foram **corrigidos** antes dos commits
`stage 6.6: conceptual approved` (5be02b8) e `stage 6.6: technical approved`;
nenhum refutado nem escalado.
**Decisão:** registrar as correções materiais (detalhe no relatório final):
- A/D1: variância do CUSUM = a do DM primário (retangular h−1 + fallback);
  Bartlett ~h−1 sobre-rejeitaria (~14 % a 5 %) em h = 7.
- A/D2: degeneração parcial por pares simétricos **e** adjacentes.
- A/D3, A/N6: fold e pares adjacentes fora do caminho do veredito (nada de perfil
  bloqueia o refresh).
- A/A3: DM por recorte descritivo (p bruto, sem Holm), doc §6.4.
- A/A1, A/N3: toda regra de perfil não nomeada no r0 vai à r1 e ao manifesto;
  sob r0 sete perfis ficam "não congelados".
- A/A2, A/N5: critério 3 da #129 e item 3 do ADR 6.5.0008 superados por B1;
  corpo da issue atualizado.
- B/V1: oráculos em `tests/integration` (gate de pureza do unit).
- B/V5, B/N1: geração `COMPLETED` sem tabela = corrupção, no `from_stored`, com os
  helpers de teste listados na Task 17.
**Razão:** ver §2 e concept §7; nenhum achado mudou o escopo validado no 1b
além da extensão da r1 às demais regras de perfil, que segue o mesmo princípio
de B1 (congelar antes do cego) e foi registrada na issue.

### 2026-10-06 — [decision] Task 11: parâmetros do `ProfileReports` num DTO e unidade da estacionariedade — Claude (Opus 5.5)
**Contexto:** a Task 11 previa `ProfileReports.evaluate` com dez argumentos keyword
(candidato, α, estimador, mínimo de violações, tolerância, draws, seed, regras...), e
isolamento de falha "por par" do diagnóstico de d_t.
**Decisão:** (a) os parâmetros do plano viajam num DTO de domínio frozen
`ProfileSettings` (montado pelo use case a partir do `RefreshParameters` na Task 13) —
reversível-barato, mesma informação, evita `noqa: PLR0913`; (b) a unidade isolada da
estacionariedade é a **chamada do horizonte** (`DifferentialStationarity.evaluate`): uma
falha vira linha `error` para cada par, sem tocar o módulo da Task 09 fora do escopo da
Task 11. O motivo `error` continua por par na tabela, como o concept I4 pede.
**Razão:** sem âncora de princípio específica (escolhas locais de forma); registradas
aqui como suposição de alinhamento, auditável.

### 2026-10-06 — [decision] Checkpoint C bloco 3 (L5): `profile_parameters` proibido na revisão 0 — Claude (Opus 5.5)
**Contexto:** o VO aceitava o bloco num plano r0 sem emenda; o ADR 6.6.0001 item 5 diz
que só a r1 (emenda cega) o carrega, e o estado `not_frozen_in_revision` (I9) sai de
`profile_parameters is None`.
**Decisão:** `Preregistration.__post_init__` recusa `profile_parameters` com
`revision == 0` (commit 6b1c175), como já recusa os campos de emenda.
**Razão:** âncora no ADR 6.6.0001 item 5 e no ADR 6.5.0002 (regra nova do plano só por
revisão nova); reversível-barato.

### 2026-10-06 — [deviation] Task 15: uma coluna `attempts` no Monte Carlo — Claude (Opus 5.5)
O technical listava `uc_attempts` e `ind_attempts` em `gold_christoffersen_monte_carlo`;
o `MonteCarloPValues` da 6.3 (ADR 6.3.0006) tem **um** contador `attempts` (o LR_uc usa
os N primeiros sorteios do mesmo laço). A tabela grava `attempts` como o VO o define —
nenhuma informação perdida; abaixo do limiar de pergunta (forma, não contrato).

<!-- END: post-execution -->
