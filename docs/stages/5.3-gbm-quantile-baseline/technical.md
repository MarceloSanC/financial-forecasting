---
title: Technical — GBM quantílico (LightGBM)
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, gbm-quantile-baseline, lightgbm]
status: done
created_at: 2026-07-19
updated_at: 2026-07-19
stage_id: 5.3-gbm-quantile-baseline
stage_title: GBM quantílico (LightGBM)
step_id: 5
step_title: Modelagem e harness de walk-forward
depends_on: [5.1-walk-forward-harness]
concept_ref: ./concept.md
issue_id: 53
branch: feat/53-5-3-gbm-quantile-baseline
tasks_count: 6
---

# Technical — Stage 5.3 — GBM quantílico (LightGBM)

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [5.3/task-NN]`
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, perguntar ao humano com opções e recomendação, e
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done).
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage),
>    fazer commit `stage 5.3: complete` e atualizar `roadmap.md`.

## 1. Contexto e estratégia de execução

### Resumo

Implementar o baseline-modelo GBM quantílico: port-out `QuantileModelTrainer`
(fronteira só de primitivos), use case `TrainGbmQuantile` (lê dataset 3.5,
splits 5.1, monta matrizes, aplica guardrail 4.3, persiste em
`fact_oos_predictions`/`dim_run` com `model_version='gbm_quantile'`) e
adapter `LightgbmQuantileTrainer` (um booster por nível × horizonte,
seleção de `m*` pela pinball média da grade em `early_stop`, contagem
1-based, predição truncada). Contratos e invariantes: `concept.md` §4–§6;
decisões D1–D7 (ADRs 5.3.0001–0003).

### Estratégia

TDD inside-out com fitness function primeiro (skill `task-ordering-hex`):

1. **Gate antes do código** (Task 01): dependência `lightgbm` + contrato
   import-linter `modeling-no-lightgbm-leak` com prova de quebra — o
   guard-rail arquitetural existe antes do primeiro import da lib.
2. **Contrato antes da implementação** (Task 02): o port e seus DTOs, com
   validação de params testável sem lib.
3. **Aplicação com fakes** (Task 03): use case + fake do trainer — toda a
   orquestração (matrizes, labels I1/I12, anti-leakage A7, guardrail,
   dedup, persistência) testada sem LightGBM.
4. **Adapter real** (Task 04): mecânica LightGBM isolada + oráculos de
   mecânica (histórico, truncamento 1-based, determinismo).
5. **Equivalência fake↔real** (Task 05): suite de contrato — mesma
   validação, mesma política de NaN, oráculo tipo-7 nas duas pernas.
6. **Wiring + e2e** (Task 06): composition root com proxy lazy + fluxo
   completo via `wire_dependencies` contra store em `tmp_path`.

Cada commit deixa `make check` verde. Checkpoint C após Task 03 (bloco 1)
e após Task 06 (bloco 2).

### Pré-condições

- Stage `5.1-walk-forward-harness` em `done` e mergeada em `develop`
  (splitter, `FoldSplit`, dedup); 4.3/3.4/3.5 `done` (transitivas).
- Issue #53 aberta; branch `feat/53-5-3-gbm-quantile-baseline` ativa.
- `libgomp.so.1` presente no ambiente (verificado: presente no devcontainer;
  wheel manylinux do LightGBM exige em runtime — risco R2 do concept).

### Premissas técnicas

- Python 3.12 + uv; `make check` = lint + typecheck + layout + lint-imports
  + docs-check + test.
- `lightgbm >= 4.7, < 5.0` (wheel ~3.5 MB; 4.7.0 corrige percentil da folha
  com pesos — concept D5).
- Dataset físico `processed/dataset_tft/<asset>/*.parquet` com as 62
  colunas do schema 3.5; features de desenho = 55 da registry + `day_of_week`
  + `month` (57 colunas), excluídas `timestamp`/`asset_id`/
  `fundamentals_effective_date`/`target_return`/`time_idx` (ADR 5.3.0003).
- Registry hoje: 55 specs, todas `enabled_by_default=True` —
  `enabled_only=True` ≡ lista completa (verificado 2026-07-19); C6 protege
  contra drift futuro.

### Estrutura de pastas afetada

```
src/financial_forecasting/
├── composition_root.py                                      (Task 06 — modificar)
└── features/modeling/
    ├── application/
    │   ├── ports/out/quantile_model_trainer.py              (Task 02 — criar)
    │   └── use_cases/train_gbm_quantile.py                  (Task 03 — criar)
    └── adapters/out/lightgbm/
        ├── __init__.py                                      (Task 04 — criar)
        └── lightgbm_quantile_trainer.py                     (Task 04 — criar)
tests/
├── architecture/test_import_contracts.py                    (Task 01 — modificar)
├── fakes/features/modeling/in_memory_quantile_model_trainer.py   (Task 03 — criar)
├── unit/features/modeling/application/
│   ├── test_quantile_model_trainer_port.py                  (Task 02 — criar)
│   └── test_train_gbm_quantile.py                           (Task 03 — criar)
├── integration/features/modeling/
│   ├── test_lightgbm_quantile_trainer.py                    (Task 04 — criar)
│   └── test_train_gbm_quantile.py                           (Task 06 — criar)
└── contract/features/modeling/test_quantile_model_trainer_contract.py  (Task 05 — criar)
pyproject.toml, uv.lock, .importlinter                       (Task 01 — modificar)
```

> Nota de mapeamento vs `arquivos_a_criar` do roadmap: o unit
> `test_gbm_quantile_grid.py` (flat) materializa como
> `unit/features/modeling/application/test_*.py` (árvore aninhada — padrão
> real do repo desde a 5.1) + suite de contrato; o integration
> `test_train_gbm_quantile.py` mantém o nome do roadmap.

## 2. Tasks

### Task 01 — Dependência `lightgbm` + gate `modeling-no-lightgbm-leak`

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `pyproject.toml`
  - `uv.lock`
  - `.importlinter`
  - `tests/architecture/test_import_contracts.py`
- **O que fazer:**
  Adicionar `lightgbm>=4.7,<5.0` a `[project].dependencies` com comentário
  no padrão do bloco do `statsforecast` (por que core e não extra — concept
  D5; piso 4.7 pelo fix #7224 do percentil da folha). Regenerar lock no
  mesmo commit. Adicionar contrato import-linter
  `modeling-no-lightgbm-leak` (forbidden: `lightgbm` em
  `modeling.application` + `modeling.domain`; template:
  `modeling-no-statsforecast-leak`) e registrá-lo em `_EXPECTED_CONTRACTS`.
- **Detalhes técnicos:**
  - `numpy` já é proibido em application/domain pelo contrato statsforecast
    — o novo contrato cobre só `lightgbm` (single-purpose).
  - Prova de quebra intencional (registrar saída literal em §7): inserir
    `import lightgbm` em `run_baselines.py` → `uv run lint-imports`
    vermelho → reverter → verde.
- **Critério de aceite:**
  - `uv run python -c "import lightgbm; print(lightgbm.__version__)"`
    imprime 4.7+;
  - `uv run lint-imports` verde com o contrato novo listado como kept;
  - prova de quebra executada e revertida;
  - teste de arquitetura passa com o contrato registrado.
- **Comando de verificação:**
  ```bash
  uv run python -c "import lightgbm; print(lightgbm.__version__)"
  uv run lint-imports
  uv run pytest tests/architecture/ -q
  make check
  ```
- **Commit sugerido:** `build(modeling): adicionar lightgbm e gate de vazamento [5.3/task-01]`

---

### Task 02 — Port `QuantileModelTrainer` + DTOs

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/application/ports/out/quantile_model_trainer.py`
  - `tests/unit/features/modeling/application/test_quantile_model_trainer_port.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Criar o módulo do port com: `GbmTrainingParams` (frozen, defaults do
  concept §4, `__post_init__` validando C2-params), `QuantileTrainingResult`
  (frozen), `QuantileModelTrainer` (Protocol) com a assinatura exata do
  concept §4, reusando `GridByHorizon` de `baseline_forecaster`. Docstring
  do módulo fixa a semântica: seleção de `m*` 1-based (índice do argmin
  **+ 1**, `m* >= 1`), exclusão de labels não finitos do fit E do monitor
  (I11), labels do grid completo (I12), grade crua sem guardrail (I3),
  emissão só finita (C5).
- **Detalhes técnicos:**
  - Validações do `GbmTrainingParams.__post_init__` → `ValueError`:
    `num_boost_round_max < 1`, `learning_rate <= 0`, `num_leaves < 2`,
    `min_data_in_leaf < 1`.
  - Só `dataclasses`/`typing`/`collections.abc` no módulo (gate de leak).
- **Critério de aceite:**
  - Unit tests cobrem: params default válidos; cada violação de C2-params
    ergue `ValueError` com mensagem nomeando o campo; DTOs imutáveis
    (`FrozenInstanceError`).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/modeling/application/test_quantile_model_trainer_port.py -q
  make check
  ```
- **Commit sugerido:** `feat(modeling): port QuantileModelTrainer com params validados [5.3/task-02]`

---

### Task 03 — Use case `TrainGbmQuantile` + fake do trainer

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/application/use_cases/train_gbm_quantile.py`
  - `tests/fakes/features/modeling/in_memory_quantile_model_trainer.py`
  - `tests/unit/features/modeling/application/test_train_gbm_quantile.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Use case espelhando o fluxo do `run_baselines.py` (constantes de
  layer/table/split, leitura+parse, `index_by_session`, splits, dedup com
  asserção de remoção zero, `run_id`/`config_signature` via `Hasher`,
  `RunRecord` por fold, `PersistPredictions` por decisão), com as
  diferenças do GBM: seleção nominal de colunas de feature (C6), montagem
  de matrizes (linhas float com `None→nan`), labels por horizonte do grid
  completo (I1/I12, `target_return[idx+h]` com asserção de range),
  chamada única do port por fold, guardrail por (decisão × horizonte),
  `model_version='gbm_quantile'`, `seed` no `dim_run` e
  `best_iteration_by_horizon` no Result. Fake do trainer: mesmas validações
  C3/C4 do contrato, grade = `sample_quantiles_type7` dos labels finitos de
  treino (idêntica para toda decisão), `best_iteration = 1`.
- **Detalhes técnicos:**
  - Payload do `run_id` inclui `feature_names` ordenadas (I7) + params +
    horizons + levels + schema_version + fingerprint + fold.
  - Validações C1/C2/C6 antes de qualquer treino; C2 estendido no padrão
    da 5.2 (specs→params; horizons duplicados/vazios; levels).
  - Reusar fakes existentes de `MedallionStore`/`AnalyticsRepository`/
    `Hasher` de `tests/fakes/` (mesmos do `test_run_baselines.py` unit).
  - Fixture com `target_return[i]` codificando o índice (ex.: `i/1000`)
    para o teste de alinhamento A7 detectar mutação `t+h → t+h−1`.
- **Critério de aceite:**
  - Unit tests cobrem: C1, C2 (cada modo), C6 nomeando colunas faltantes;
    **I10** — fake capturador prova `feature_names` == lista exata
    esperada (registry `enabled_only` na ordem de inserção + `day_of_week`
    + `month`) e SEM nenhuma excluída (`target_return`, `time_idx`,
    `asset_id`, `fundamentals_effective_date`) — mata o mutante de
    leakage que inclui `target_return` como feature;
    A7 — fake capturador prova labels = `target_return[idx+h]` exatos,
    max índice de label de train/early_stop < início da partição seguinte,
    e partições passadas ao port == partições do fold (calib nunca);
    I6 — mutação de valores nas sessões de calib não altera o resultado;
    guardrail aplicado (grade crua desordenada → persistida ordenada,
    `guardrail_applied` verdadeiro); I8 dedup zero-removal; I7 —
    `dim_run` com seed/model_version/fingerprint corretos;
    `best_iteration_by_horizon` propagado ao Result; rows_written/skipped
    coerentes com janelas incompletas no fim do dataset.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/modeling/application/test_train_gbm_quantile.py -q
  make check
  ```
- **Commit sugerido:** `feat(modeling): use case TrainGbmQuantile [5.3/task-03]`

> **Checkpoint C — bloco 1 (Tasks 01–03)** após o commit da Task 03.

---

### Task 04 — Adapter `LightgbmQuantileTrainer`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/adapters/out/lightgbm/__init__.py`
  - `src/financial_forecasting/features/modeling/adapters/out/lightgbm/lightgbm_quantile_trainer.py`
  - `tests/integration/features/modeling/test_lightgbm_quantile_trainer.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Adapter com import eager de `lightgbm`/`numpy` (única fronteira — gate da
  Task 01). Por horizonte: filtrar pares de label finito (fit E monitor,
  I11), C3 (`< min_data_in_leaf` → `ValueError`), construir `lgb.Dataset`;
  por nível: `lgb.train` com params fixos do concept D6 (`objective=
  'quantile'`, `alpha=τ`, `metric='quantile'`, `deterministic=True`,
  `force_row_wise=True`, `seed`, `device_type='cpu'`,
  `feature_fraction=1.0`, `bagging_fraction=1.0`, `bagging_freq=0`,
  `verbosity=-1`, hiperparâmetros do `GbmTrainingParams`),
  `num_boost_round=num_boost_round_max`, `valid_sets` com early_stop,
  `callbacks=[lgb.record_evaluation(...)]`, **sem** callback de parada.
  Seleção `m* = 1 + argmin(média dos históricos por iteração)` (empate →
  menor; asserção `m* >= 1` e histórico comprimento == ceiling);
  `booster.predict(test_X, num_iteration=m*)`; montar grades por decisão
  com `float()` puro (nunca numpy atravessa o port), C5 (não finito →
  `ValueError`), C4 estrutural na entrada.
- **Detalhes técnicos:**
  - Chave do histórico: `evals_result['valid_0']['quantile']` — teste de
    mecânica cobre nome/forma (risco R3; se divergir: PARAR, aplicar
    fallback do ADR 5.3.0002 = Alternativa B, registrar deviation).
  - `_select_best_iteration(histories) -> int` como função pura do módulo
    (1-based), testável sem treinar.
- **Critério de aceite (integration, `pytestmark = integration`):**
  - mecânica: históricos não vazios, comprimento == ceiling, para todos os
    níveis;
  - A3-oráculo do truncamento: caso com ótimo conhecido na **iteração 1**
    (ruído + learning rate alto) → `best_iteration == 1` e grades ==
    grades de um re-treino com `num_boost_round_max=1` (mata o off-by-one:
    índice 0 = modelo cheio);
  - `_select_best_iteration`: argmin da média, empate → menor, 1-based
    (unit-style no arquivo de integração);
  - determinismo: duas chamadas idênticas → resultados idênticos;
  - I11-monitor: resultado com NaN em labels de early_stop == resultado com
    esses pares pré-removidos;
  - C3/C4/C5 erguem `ValueError`;
  - CPU: params efetivos com `device_type='cpu'` (I9).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/features/modeling/test_lightgbm_quantile_trainer.py -q
  make check
  ```
- **Commit sugerido:** `feat(modeling): adapter LightGBM quantílico com selecao 1-based [5.3/task-04]`

---

### Task 05 — Suite de contrato fake ↔ real

- **Arquivos a criar:**
  - `tests/contract/features/modeling/test_quantile_model_trainer_contract.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Suite parametrizada `[fake, real]` no padrão da 5.2 (`_FACTORIES`/`_IDS`
  + fixture `trainer`, `@pytest.mark.contract`), provando que as duas
  pernas honram o mesmo contrato observável.
- **Detalhes técnicos / casos:**
  - estrutura: uma grade por decisão de teste × horizonte, alinhada 1:1 a
    `quantile_levels`; chaves == `test_decision_indices` × horizontes;
  - `best_iteration_by_horizon` ∈ [1, ceiling] nas duas pernas;
  - determinismo (duas chamadas → idênticas) nas duas pernas;
  - C3 (train finito < `min_data_in_leaf`), C4 exatamente como no concept
    (larguras de linha, comprimento de labels, `test_decision_indices`,
    `early_stop` vazio — levels inválidos são C2 do use case, NÃO entram
    aqui) e I11-fit (resultado invariante à pré-remoção de pares de train
    com label NaN) nas duas pernas;
  - **A6-oráculo tipo 7:** features constantes, `min_data_in_leaf=1` →
    grade == `sample_quantiles_type7(labels finitos de train, levels)` em
    toda decisão, tolerância abs 1e-6 (labels float32 no `lgb.Dataset` —
    justificativa no concept A6), com caso discriminante de mutante
    (janela deslocada difere além da tolerância — padrão ADR 0.0.0021).
- **Critério de aceite:** todos os casos acima verdes nas duas pernas.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/modeling/test_quantile_model_trainer_contract.py -q
  make check
  ```
- **Commit sugerido:** `test(modeling): suite de contrato do QuantileModelTrainer [5.3/task-05]`

---

### Task 06 — Wiring no composition root + integração e2e

- **Arquivos a criar:**
  - `tests/integration/features/modeling/test_train_gbm_quantile.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/composition_root.py`
- **O que fazer:**
  `_LazyLightgbmQuantileTrainer` (proxy que satisfaz o port e adia o import
  da lib ao primeiro uso — precedente `_LazyStatsforecastBaselineForecaster`;
  `PLC0415` já ignorado para o arquivo), campo `train_gbm_quantile:
  TrainGbmQuantile` em `ApplicationDependencies`, wiring com store/splitter/
  persister/repository/hasher existentes. Integração: seed do dataset
  físico em `tmp_path` (57 colunas de feature com ruído determinístico +
  `timestamp` em sessões XNYS reais + `target_return` codificando índice),
  executar o use case via `wire_dependencies(Settings(...))` e validar
  persistência.
- **Detalhes técnicos:**
  - Geometria mínima: ~120 sessões, `n_folds=1`, `test_size=5`,
    `val_size=10`, `calib_size=10`, `embargo=1`, horizons `(1, 7)`,
    levels `(0.1, 0.5, 0.9)`, `num_boost_round_max=25`,
    `min_data_in_leaf` pequeno — 6 boosters, segundos de CPU.
  - O seed do dataset DEVE conter todas as colunas de feature esperadas
    (C6 falharia com seed parcial — o read do store é `SELECT *`).
  - Asserts: linhas em `fact_oos_predictions` com
    `model_version='gbm_quantile'`, grão LONG por nível, `target_timestamp`
    == sessão `decision_idx + h` (I1 via 4.3), guardrail monotônico,
    `dim_run` com `seed` preenchida e fingerprint do fold; janelas
    incompletas → `rows_skipped` > 0 quando aplicável.
  - **A5:** duas execuções com o mesmo comando contra dois `tmp_path`
    distintos → mesmas linhas persistidas (ordenadas) e mesmos
    `best_iteration_by_horizon`.
  - **C7:** reexecutar a MESMA invocação contra o MESMO store propaga
    `DuplicateKeyError` (espelho do teste da 5.2 em
    `test_run_baselines.py` — fecha A8 por completo).
  - **A10/e2e:** este teste é a verificação end-to-end da Stage (grafo real
    completo do `wire_dependencies`, sem entrypoint HTTP/CLI no BC).
- **Critério de aceite:** integração verde com os asserts acima; import do
  `composition_root` não importa `lightgbm` (lazy — assertar em teste que
  `sys.modules` não ganha `lightgbm` só por importar o módulo).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/features/modeling/test_train_gbm_quantile.py -q
  make check
  ```
- **Commit sugerido:** `feat(modeling): wiring do TrainGbmQuantile no composition root [5.3/task-06]`

> **Checkpoint C — bloco 2 (Tasks 04–06)** após o commit da Task 06.

## 3. Gate de saída da Stage

### Verificações automatizadas

```bash
make check                    # lint + typecheck + layout + lint-imports + docs-check + testes
uv run pytest tests/ -q       # suite completa
uv run pytest tests/ --cov=src/financial_forecasting --cov-report=term-missing  # ≥90% por arquivo da Stage
python scripts/check_technical_postexec.py docs/stages/5.3-gbm-quantile-baseline/technical.md
```

### Verificações funcionais

- [ ] Fluxo e2e exercitado: `TrainGbmQuantile` via `wire_dependencies`
      contra dataset físico seed → predições LONG + `dim_run` no parquet
      (Task 06 executada de verdade, saída colada no relatório).
- [ ] Critérios A1–A11 do concept §11 todos satisfeitos (mapa: A1→T02/T03,
      A2→T04/T05, A3→T03(calib)/T04, A4→T06, A5→T04/T05/T06, A6→T05,
      A7→T03, A8→T02(C2-params)/T03(C1/C2/C6)/T04(C3/C4/C5)/T05(C3/C4)/
      T06(C7), A9→T01, A10→T06, A11→cov focada).

### Checklist de fechamento da Stage

- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Auditoria de testes independente com mutação real executada
- [ ] Commit final `stage 5.3: complete` aplicado
- [ ] `roadmap.md` atualizado (status `done`, `updated_at`,
      `last_reviewed_at`)
- [ ] ADRs 5.3.0001–0003 em `accepted`
- [ ] `concept.md` sem retoque retrospectivo pendente

## 4. Ordem de dependência entre Tasks

```
Task 01 (dep+gate) ─► Task 04 (adapter) ─► Task 05 (contrato)
Task 02 (port) ──────► Task 03 (use case+fake) ─► Task 06 (wiring+e2e)
Task 02 ─────────────► Task 04
Task 03 ─────────────► Task 05   (a suite importa o fake da T03)
Task 04 ─────────────► Task 06
```

Sequência linear 01→06 satisfaz todas as arestas.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| R3 — `evals_result` sem a chave/forma esperada (`valid_0`/`quantile`) | PARAR; regredir à Alternativa B do ADR 5.3.0002 (`num_boost_round` fixo), deviation em §7 — nunca computar pinball manualmente (escopo §1 do concept) |
| A6-oráculo real divergir além de 1e-6 (init da lib ≠ tipo 7) | Investigar com probe isolado; se a mecânica do `boost_from_average` mudou, reformular A6 para equivalência com re-treino de referência e registrar deviation + errata no concept |
| Tempo de treino no CI estourar (Tasks 04–06) | Reduzir ceiling/nº de níveis das fixtures; `@pytest.mark.slow` só com medição colada (precedente F-T3 da 5.2) |
| Colunas do seed de integração divergirem do C6 | Gerar seed a partir de `list_feature_specs()` (fonte única) — nunca lista hardcoded |
| `libgomp` ausente em runner CI | `apt-get install libgomp1` no Dockerfile/workflow, deviation em §7 |

## 6. Referências

- [`./concept.md`](./concept.md) — contratos §4, invariantes §5, erros §6, decisões §7
- [`../../domain/modeling/quantile-model-training.md`](../../domain/modeling/quantile-model-training.md) — §2, §4
- ADRs: [`5_3_0001`](../../adr/5_3_0001-direct-per-level-horizon-boosters.md), [`5_3_0002`](../../adr/5_3_0002-grid-mean-early-stopping.md), [`5_3_0003`](../../adr/5_3_0003-feature-set-no-time-idx.md); herdados: 4.3.0001/0002, 5.1.0002/0003, 0.0.0021
- Precedentes de código: `run_baselines.py` (fluxo), `statsforecast_baseline_forecaster.py` (adapter), `test_baseline_forecaster_contract.py` (suite), `composition_root.py` (proxy lazy)
- Skills: `hex-arch-python`, `pytest-with-fakes`, `task-ordering-hex`, `import-linter-rules`, `composition-root`, `dmls-ch05-model-development-and-evaluation`

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas via
> `scripts/check_technical_postexec.py`. Cada entrada carrega data + autor.

<!-- END: post-execution -->
