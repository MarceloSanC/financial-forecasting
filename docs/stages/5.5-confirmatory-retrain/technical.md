---
title: Technical — Stage 5.5 — Re-treino confirmatório do cohort AAPL
description: Plano de execução da Stage 5.5 — pré-requisitos (escrita atômica no silver, grid único de treino em 4 use cases), máquina do cohort (VOs, sweep simétrico, ports e adapters em pares, use case, wiring, CLI) e execução real cega, em 38 Tasks (1 Task = 1 commit)
when-use: Consultar durante a Fase 4 (execução) da Stage 5.5; cada Task tem arquivos, critério de aceite e comando de verificação
keywords: [technical, plano de execução, confirmatory-retrain, cohort, sweep, ledger, cli, training-grid, atomic-write, port-coverage]
status: done
created_at: 2026-09-27
updated_at: 2026-09-27
stage_id: 5.5-confirmatory-retrain
stage_title: Re-treino confirmatório do cohort AAPL
step_id: 5
step_title: Modelagem, baselines e treino
depends_on: [5.2-baselines-naive-statistical, 5.3-gbm-quantile-baseline, 5.4-tft-trainer]
concept_ref: ./concept.md
issue_id: 102
branch: feat/102-5-5-confirmatory-retrain
tasks_count: 38
---

# Technical — Stage 5.5 — Re-treino confirmatório do cohort AAPL

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro §1. 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz arquivos, o que fazer, critério de aceite (o que o teste
>    prova) e verificação. 4. **`make check` verde antes de todo commit**
>    (no container). 5. Commit: `<type>(<scope>): <descrição> [5.5/task-NN]` +
>    `Refs #102`. 6. Algo não previsto → pausar, perguntar, registrar em §7.
>
> **Stage = 1 branch:** `feat/102-5-5-confirmatory-retrain` (worktree própria),
> rebaseada em `origin/develop` em 2026-09-27 (`864eef4`) antes deste plano.

## 1. Contexto e estratégia de execução

### Resumo

**(A) Pré-requisitos** em Stages fechadas: gravação atômica de partição no
silver (D12) e grid único de treino — serviço de domínio puro chamado pelos 4
use cases que hoje têm cópia própria da leitura (absorve a #99), cortando o
prefixo sem valor (D11). **(B) Máquina do cohort:** geometria, VOs de
identidade, extensão do port do GBM, sweep simétrico (D13), DTO do cohort, três
ports consumer-owned em pares port→adapter, use case `RunConfirmatoryCohort`,
wiring e CLI. **(C) Execução real:** rascunho do cohort, materialização e
medições com parada [P], sweeps, congelamento com âncora, corrida cega,
verificação por contagem e documentação.

### Estratégia e decisões de forma (fixadas aqui; o concept deixou em aberto)

- **Ordem:** inside-out (skill `task-ordering-hex`) com exceções declaradas:
  (1) o bloco A começa por **testes de caracterização** (Task 04) — ordem guiada
  pelo risco de regressão em 3 Stages fechadas; (2) a extensão do port
  `QuantileModelTrainer` (Task 13) muda port, fake, adapter, contrato e as
  construções de resultado nos testes no mesmo commit — estender `Protocol`
  existente obriga todos os implementadores juntos (exceção prevista na skill);
  (3) cada port novo vem em **par** port→adapter em Tasks consecutivas, com a
  entrada temporária do baseline do `port-coverage`.
- **Leitura única sem port novo:** `build_training_grid(rows, *, asset_id,
  columns)` é serviço de domínio puro, **totalmente parametrizado** — não
  importa o registry. Cada use case lê `("processed", "dataset_tft")` pelo
  `MedallionStore` (uma linha) e chama o serviço. **Desvio de forma declarado
  em relação ao concept §4 e ao ADR 5.5.0004** ("a leitura devolve as linhas
  mais a impressão digital"): o serviço de domínio devolve as linhas; a
  impressão digital é calculada pelo chamador de aplicação via
  `DatasetContentFingerprint.compute` (regra 6 do `check_layout`: hash só em VOs
  de `shared/domain/value_objects/`). O ADR 5.5.0004 recebe nota na Task 06.
- **Colunas de modelagem sem aresta nova entre slices:** a função
  `modeling_columns()` fica em `train_gbm_quantile.py` —
  `expected_feature_names()` (registry habilitado + calendário) +
  `target_return` — módulo que **já** tem a aresta declarada para o registry
  (`.importlinter`, `bc-independence`); `train_tft`, `run_tft_sweep` e
  `run_baselines` também já têm aresta declarada ou importam de `train_tft` /
  `train_gbm_quantile` (precedente: `run_tft_sweep` importa de `train_tft`).
  `RunConfirmatoryCohort` **recebe injetados** pelo composition root as colunas
  e o `feature_set_hash` observado (I4) — nenhum `ignore_imports` novo.
- **Impressão digital dos sweeps (I4, igualdade 2):** `RunTftSweepResult` e
  `RunGbmSweepResult` passam a trazer a impressão digital do grid sobre o qual
  treinaram; `freeze` copia esse valor para `provenance` — nunca de uma
  releitura.
- **Gravação do TOML congelado sem dependência nova:** `cohort_file.dump`
  escreve só o schema conhecido do cohort (tabelas e escalares), validado por
  ida e volta com `tomllib` (`parse(dump(spec)) == spec`). Alternativa
  descartada: `tomli-w`/`tomlkit` (dependência nova para um schema fechado).
- **Lock de escritor único:** `materialize`, `sweep` e `freeze` adquirem o lock
  do `data_root` no comando do CLI, via `CohortProgressLedger.acquire_writer`
  recebido do composition root (regra 3 do `check_layout`: `adapters/in` não
  importa `adapters/out`); no `run`, o **dono único** do lock é o use case
  `RunConfirmatoryCohort` — o comando `run` não o adquire (evita auto-bloqueio
  com `O_EXCL`).
- **`--data-root` obrigatório em todos os subcomandos** (`materialize`, `sweep`,
  `freeze`, `run`, `verify`), sem default: o `cli.py` monta `Settings` com esse
  `data_root` e chama `wire_dependencies(settings)` (concept D10/R4 — dado
  isolado em `data/cohorts/<nome>/`).
- **Resultados dos sweeps entre processos:** `sweep` grava cada resultado
  (`best_params`, study id, melhor trial e objetivo, impressão digital) pelo
  ledger (`record_sweep_result` / `sweep_results`, arquivo
  `artifacts/cohorts/<exploratory_scope_id>/sweeps.json`, atômico); `freeze`
  lê de lá. Rodadas de medição (`--n-trials 1`, Task 33) ficam sob outro scope
  id (o `n_trials` entra no hash do rascunho) — intencional: não se misturam
  com o sweep real.
- **Git no container:** a worktree aponta para `.git` do checkout principal com
  caminho Windows, invisível no container. O `GitRuntimeEnvironmentProbe` usa o
  `git` do ambiente; para a execução real, o runbook monta o `.git` principal
  **somente leitura** e exporta `GIT_DIR=<montagem>/worktrees/<nome>`,
  `GIT_WORK_TREE=/app` e `safe.directory` (verificado na Task 33 antes de
  qualquer treino). Testes usam repositório git descartável ou o fake do probe.
- **Probe por caminho do cohort:** o composition root expõe uma fábrica
  `runtime_probe_for(cohort_path)`; o CLI a chama depois de ler os argumentos.
- **Hash no DTO:** `cohort_id`/`exploratory_scope_id` recebem um `CohortHash`
  já calculado — `hash_mapping` só dentro do VO (regra 6).
- **Rebase:** proibido entre a Task 34 (congelamento) e o fim da Task 35
  (corrida) — a identidade do código (hash de conteúdo de `src/`) mudaria e I5
  abortaria uma retomada. Depois da corrida, o rebase exigido pelo PR é livre: a
  tag `cohort/<id>` mantém o commit do congelamento vivo no remoto, e o hash
  cobre o conteúdo, não o commit.
- **Checkpoint C** nas fronteiras do §4.
- **Paradas [P] previstas:** Task 33 (após a medição de custo: `n_trials`,
  seeds; ROCm se o custo inviabilizar — resposta "ROCm" abre Tasks novas de
  adapter/`device`, nunca continua em silêncio).

### Pré-condições

- 5.2, 5.3, 5.4 `done`; concept `done` (`2f6f1e6` após rebase); ADRs 5.5.0001–0004.
- Docker no ar, imagem `financial_forecasting-app:dev`.
- Bloco C: brutos do projeto anterior no host; extra `sentiment` no venv do
  container; acesso ao Hugging Face Hub; `gh` autenticado (âncora).

### Premissas técnicas

- Python 3.12, `tomllib`; mypy strict; `.importlinter` com `bc-independence`
  (quatro slices, arestas declaradas, `unmatched_ignore_imports_alerting = error`);
  `scripts/check_layout.py` (regra 3: `adapters/in` não importa `adapters/out`;
  regra 6: hash só em VOs de shared); `scripts/check_port_coverage.py` (fake
  com prefixo `Fake`/`InMemory`; real = adapter que **cita** o nome do port;
  baseline morto reprova).
- Comandos sempre no container (fluxo Docker-only).

### Estrutura de pastas afetada

```
.gitignore                                                           (mod)
config/cohorts/aapl_confirmatory.toml                                (novo)
scripts/arch_baseline.toml                                           (mod, temporário)
src/financial_forecasting/
├── cli.py                                                           (novo)
├── composition_root.py                                              (mod)
├── shared/domain/value_objects/{cohort_hash.py, dataset_content_fingerprint.py}
├── shared/infrastructure/config/settings.py                         (mod)
└── features/
    ├── analytics_store/adapters/out/parquet/{parquet_analytics_repository.py (mod), parquet_cohort_run_index.py}
    └── modeling/
        ├── domain/exceptions/cohort.py                              (novo)
        ├── domain/services/training_grid.py                         (novo)
        ├── domain/value_objects/cohort_geometry.py                  (novo)
        ├── application/dtos/{__init__.py, cohort_spec.py}           (novos)
        ├── application/ports/out/{cohort_progress_ledger.py, cohort_run_index.py, runtime_environment_probe.py}
        ├── application/ports/out/{quantile_model_trainer.py, hyperparameter_search.py}  (mod)
        ├── application/use_cases/{run_gbm_sweep.py, run_confirmatory_cohort.py}         (novos)
        ├── application/use_cases/{run_baselines, train_gbm_quantile, train_tft, run_tft_sweep}.py (mod)
        ├── adapters/out/lightgbm/lightgbm_quantile_trainer.py       (mod)
        ├── adapters/out/filesystem/{__init__.py, json_cohort_progress_ledger.py}
        ├── adapters/out/runtime/{__init__.py, git_runtime_environment_probe.py}
        └── adapters/in/{__init__.py, cli/{__init__.py, cohort_file.py, cohort_commands.py}}
tests/ unit/ contract/ integration/ e2e/ fakes/ (por Task)
docs/runbooks/confirmatory-cohort-aapl.md                            (novo)
```

## 2. Tasks

> Faixa saudável: 3–12. **Esta Stage tem 38**, mantida inteira por decisão do
> humano (#102, B1; concept R8); o número cresceu de ~19 para 38 no Checkpoint B
> por atomicidade (1 port = 1 Task, 1 escopo = 1 commit, ≤ ~5 arquivos).

### Bloco A — Pré-requisitos

### Task 01 — Roadmap: DoD da 5.5, pedidos da #78, cegamento na 6.5
- **Modificar:** `docs/roadmap.md`
- **Fazer:** 5.5 — descrição e YAML (arquivos reais; `config/cohorts/aapl_confirmatory.toml`;
  DoD: TFT seeds × folds, GBM 1×fold, 5 baselines, h+1/h+7, grid único, cohort
  congelado+hasheado+ancorado, cegamento; #99 absorvida); status `in_progress`.
  Pedidos da #78 (corpo do PR #98): aresta `S61 --> S72`; `CoverageMetrics (6.1)`
  em `contratos_consumidos` da 7.2; DoD 6.1 (gate de degeneração invalida só
  métricas de calibração da linha); DoD 6.3 (LR_uc de 3 estados do par primário
  com fixture analítica). DoD 6.5: regra de cegamento.
- **Aceite:** 5.5 sem `.yaml`; 4 pedidos presentes; cegamento na 6.5.
- **Verificação:** `make docs-check`
- **Commit:** `docs(roadmap): DoD da 5.5, pedidos da #78 e cegamento na 6.5 [5.5/task-01]`

### Task 02 — `artifacts/` fora do git
- **Modificar:** `.gitignore`
- **Fazer:** ignorar `artifacts/` (checkpoints do TFT desde a 5.4; ledger desta Stage).
- **Verificação:** `git check-ignore artifacts/cohorts/x/progress.json artifacts/tft/x/ckpt` (exit 0)
- **Commit:** `chore(gitignore): ignora artifacts/ [5.5/task-02]`

### Task 03 — Gravação atômica de partição no silver (D12)
- **Modificar:** `src/.../analytics_store/adapters/out/parquet/parquet_analytics_repository.py`;
  `tests/unit/features/analytics_store/adapters/out/parquet/test_parquet_analytics_repository_write.py`,
  `…/test_parquet_analytics_repository_read.py`
- **Fazer:** `_write_partition` grava `<arquivo>.parquet.tmp-<pid>` e `os.replace`;
  remove temporários remanescentes do diretório antes de gravar.
- **Aceite:** falha injetada em `os.replace` deixa o arquivo anterior intacto e
  legível; temporário remanescente não aparece em `read()` nem na checagem de
  vazio; suítes existentes verdes.
- **Verificação:** `pytest tests/unit/features/analytics_store/adapters/out/parquet -q`; `make check`
- **Commit:** `fix(analytics-store): gravação atômica de partição Parquet [5.5/task-03]`

### Task 04 — Caracterização das 4 leituras do dataset
- **Criar:** `tests/unit/features/modeling/application/test_dataset_loading_characterization.py`
- **Fazer:** para `RunBaselines`, `TrainGbmQuantile`, `TrainTft`, `RunTftSweep`,
  com `MedallionStore` fake servindo dataset de fixture **sem NaN** (linhas fora
  de ordem, dois ativos, **todas** as colunas de modelagem), capturar sessões,
  ordem e colunas que chegam ao splitter/trainer via fakes existentes.
  Registrar em §7 as divergências entre as cópias (diff) e a disposição de cada
  uma (parâmetro explícito vs convergir).
- **Aceite:** 4 testes verdes **no código atual**.
- **Verificação:** `pytest tests/unit/features/modeling/application/test_dataset_loading_characterization.py -v`
- **Commit:** `test(modeling): caracterização das leituras do dataset de treino [5.5/task-04]`

### Task 05 — `usable_start` e exceções de domínio do cohort
- **Criar:** `src/.../modeling/domain/services/training_grid.py` (parte 1);
  `src/.../modeling/domain/exceptions/cohort.py` (`InteriorMissingValuesError`,
  `NoUsableRowsError`, `GeometryDoesNotFitError`);
  `tests/unit/features/modeling/domain/services/test_usable_start.py`
- **Fazer:** `usable_start(values: Mapping[str, Sequence[float | None]]) -> int`.
- **Aceite:** prefixos com aquecimentos diferentes por coluna; NaN/None/inf
  interior → erro com `{coluna: contagem}`; `target_return` NaN no prefixo e no
  interior; tudo finito → 0; nenhuma linha utilizável → `NoUsableRowsError`.
- **Verificação:** `pytest tests/unit/features/modeling/domain/services/test_usable_start.py -v`; `make check`
- **Commit:** `feat(modeling): regra de primeira linha utilizável do grid [5.5/task-05]`

### Task 06 — `build_training_grid` (+ nota no ADR 5.5.0004)
- **Modificar:** `…/modeling/domain/services/training_grid.py`;
  `docs/adr/5_5_0004-single-training-grid-warmup-trim.md` (nota: o serviço devolve
  linhas; a impressão digital é do chamador)
- **Criar:** `tests/unit/features/modeling/domain/services/test_training_grid.py`
- **Fazer:** `build_training_grid(rows, *, asset_id, columns) -> TrainingGrid(rows,
  timestamps, trimmed_prefix)` — filtra ativo, ordena, valida (duplicata, vazio),
  aplica `usable_start` sobre `columns`. Sem import de registry.
- **Aceite:** em dataset sem NaN, mesmo resultado fixado na Task 04; prefixo
  cortado com aquecimento; mesmos erros de ativo ausente/vazio de hoje.
- **Verificação:** `pytest tests/unit/features/modeling/domain/services -v`; `lint-imports`; `make check`
- **Commit:** `feat(modeling): grid único de treino como serviço de domínio [5.5/task-06]`

### Task 07 — `TrainGbmQuantile` no grid único + `modeling_columns()`
- **Modificar:** `…/use_cases/train_gbm_quantile.py`; `test_dataset_loading_characterization.py`;
  conferir e, se mudarem, incluir: `tests/unit/features/modeling/application/{test_train_gbm_quantile.py, test_train_gbm_quantile_identity.py, test_identity_golden.py}`,
  `tests/integration/features/modeling/test_train_gbm_quantile.py`
- **Fazer:** remover `_load_dataset`; `modeling_columns()` =
  `expected_feature_names()` + `target_return`; ler e chamar `build_training_grid`.
- **Aceite:** caracterização verde (sem NaN); novo caso com prefixo NaN → começa
  na primeira linha utilizável; suítes do GBM verdes.
- **Verificação:** `pytest tests -q -k "gbm or characterization"`; `make check`
- **Commit:** `refactor(modeling): TrainGbmQuantile lê pelo grid único [5.5/task-07]`

### Task 08 — `TrainTft` no grid único
- **Modificar:** `…/use_cases/train_tft.py`; caracterização; conferir e, se
  mudarem, incluir: `tests/unit/features/modeling/application/{test_train_tft.py, test_train_tft_identity.py, test_identity_golden.py}`,
  `tests/integration/features/modeling/test_train_tft.py`
- **Fazer:** idem, com `modeling_columns()`.
- **Aceite:** caracterização verde; com prefixo NaN, mesma primeira linha do GBM.
- **Verificação:** `pytest tests -q -k "train_tft or characterization"`; `make check`
- **Commit:** `refactor(modeling): TrainTft lê pelo grid único [5.5/task-08]`

### Task 09 — `RunTftSweep` no grid único + impressão digital no resultado
- **Modificar:** `…/use_cases/run_tft_sweep.py`; `tests/unit/features/modeling/application/test_run_tft_sweep.py`; caracterização
- **Fazer:** idem; `RunTftSweepResult.dataset_fingerprint` via
  `DatasetContentFingerprint.compute` sobre o grid (depende da Task 12 — ver §4:
  esta Task roda **depois** da 12).
- **Aceite:** caracterização verde; com prefixo NaN, o sweep começa na mesma
  primeira linha dos treinadores (I9); resultado traz a impressão digital do
  grid usado (muda se o dataset muda).
- **Verificação:** `pytest tests -q -k "sweep or characterization"`; `make check`
- **Commit:** `refactor(modeling): RunTftSweep lê pelo grid único e reporta o dado [5.5/task-09]`

### Task 10 — `RunBaselines` no grid único
- **Modificar:** `…/use_cases/run_baselines.py`;
  `tests/unit/features/modeling/application/test_run_baselines.py`,
  `tests/unit/features/modeling/application/test_run_baselines_identity.py`,
  `tests/integration/features/modeling/test_run_baselines.py` (fixtures ganham as
  colunas de modelagem); caracterização; conferir e, se mudar,
  `tests/unit/features/modeling/application/test_identity_golden.py`
- **Fazer:** idem; mudança de comportamento declarada (concept §4): as baselines
  começam na mesma linha dos modelos.
- **Aceite:** com prefixo NaN, a primeira linha das baselines = a dos outros 3
  use cases; suítes das baselines verdes.
- **Verificação:** `pytest tests -q -k "baselines or characterization"`; `grep -rn "_load_dataset" src/` vazio; `make check`
- **Commit:** `refactor(modeling): RunBaselines lê pelo grid único [5.5/task-10]`

### Bloco B — Máquina do cohort

### Task 11 — `CohortGeometry`
- **Criar:** `…/modeling/domain/value_objects/cohort_geometry.py`;
  `tests/unit/features/modeling/domain/value_objects/test_cohort_geometry.py`
- **Fazer:** validação; `exploratory()`; `expected_prediction_rows(fold_index,
  horizons, n_levels)`; `expected_runs(n_units_per_fold)`; `fits(n_sessions,
  max_horizon)`.
- **Aceite (A1):** com o `WalkForwardSplitter` real, tuplas de treino e
  early_stop do fold exploratório **iguais** às do fold 0; contagem esperada =
  persister real num fixture (último fold com `h` a menos); na geometria do
  cohort, 3528 (folds 0–4) e 3472 (fold 5); `fits` ergue
  `GeometryDoesNotFitError` com o tamanho do treino do fold 0.
- **Verificação:** `pytest tests/unit/features/modeling/domain/value_objects/test_cohort_geometry.py -v`; `make check`
- **Commit:** `feat(modeling): geometria do cohort e geometria exploratória [5.5/task-11]`

### Task 12 — VOs `CohortHash` e `DatasetContentFingerprint`
- **Criar:** `src/.../shared/domain/value_objects/{cohort_hash.py, dataset_content_fingerprint.py}`;
  `tests/unit/shared/domain/value_objects/{test_cohort_hash.py, test_dataset_content_fingerprint.py}`
- **Fazer:** `CohortHash.compute(*, hasher, payload: Mapping[str, object])`;
  `DatasetContentFingerprint.compute(*, hasher, asset_id: str, timestamps:
  Sequence[str], columns: Mapping[str, Sequence[float]])` — chamado **só** com as
  colunas de modelagem do grid já cortado (finitas); colunas desabilitadas e
  `fundamentals_effective_date` ficam fora.
- **Aceite (A4):** estáveis para o mesmo conteúdo; mudam com qualquer
  campo/valor/ordem de coluna; NaN recusado; `check_layout` verde.
- **Verificação:** `pytest tests/unit/shared/domain/value_objects -q`; `python scripts/check_layout.py`; `make check`
- **Commit:** `feat(shared): hash do cohort e impressão digital de conteúdo do dataset [5.5/task-12]`

### Task 13 — Port `QuantileModelTrainer`: perda de early_stop e fit-only
- **Modificar:** `…/ports/out/quantile_model_trainer.py`;
  `…/adapters/out/lightgbm/lightgbm_quantile_trainer.py`;
  `tests/fakes/features/modeling/in_memory_quantile_model_trainer.py`;
  `tests/contract/features/modeling/test_quantile_model_trainer_contract.py`;
  `tests/unit/features/modeling/application/test_quantile_model_trainer_port.py`;
  `tests/unit/features/modeling/application/test_train_gbm_quantile.py`
- **Fazer:** resultado ganha `early_stop_loss_by_horizon: Mapping[int, float]`
  (obrigatório, sem default); `test_rows=()` aceito. Exceção declarada (§1).
- **Aceite:** contrato `[fake, real]` — perda finita por horizonte, igual ao
  mínimo da média da grade no histórico do adapter real; `test_rows=()` → grades
  vazias sem erro.
- **Verificação:** `pytest tests/contract/features/modeling tests/integration/features/modeling/test_lightgbm_quantile_trainer.py tests/unit/features/modeling -q`; `make check`
- **Commit:** `feat(modeling): perda de early-stop e modo fit-only no treinador quantílico [5.5/task-13]`

### Task 14 — Determinismo do GBM (A3)
- **Criar:** `tests/contract/features/modeling/test_quantile_model_trainer_determinism.py`
- **Fazer:** adapter real, fixture pequena, **parametrizado** por um conjunto de
  params (default do 5.3 + pontos das faixas D9 do GBM) **e**, quando
  `config/cohorts/aapl_confirmatory.toml` estiver congelado, pelos `gbm_params`
  lidos dele (o teste lê o arquivo; enquanto não congelado, esse caso é
  omitido, não pulado em silêncio — o id do parâmetro diz qual conjunto rodou);
  seeds 0 e 12345 → grades iguais com `==`. Depois da Task 34 o `make check`
  cobre os params congelados automaticamente.
- **Verificação:** `pytest tests/contract/features/modeling/test_quantile_model_trainer_determinism.py -v`; `make check`
- **Commit:** `test(modeling): predições do GBM independem da seed [5.5/task-14]`

### Task 15 — `SearchDimension` valida por tipo de params
- **Modificar:** `…/ports/out/hyperparameter_search.py`; `…/use_cases/run_tft_sweep.py`;
  `tests/unit/features/modeling/application/test_hyperparameter_search_port.py`,
  `test_run_tft_sweep.py`
- **Fazer:** `SearchDimension` valida só a forma; `RunTftSweep` valida os nomes
  contra `TftTrainingParams` (mesmo erro C11).
- **Aceite:** nome inválido para o TFT ainda rejeitado, agora no use case; forma
  inválida rejeitada no VO.
- **Verificação:** `pytest tests/unit/features/modeling/application -q`; `make check`
- **Commit:** `refactor(modeling): validação de dimensão de busca por tipo de params [5.5/task-15]`

### Task 16 — `RunGbmSweep`
- **Criar:** `…/use_cases/run_gbm_sweep.py`; `tests/unit/features/modeling/application/test_run_gbm_sweep.py`
- **Fazer:** espelho do `RunTftSweep`: grid único (`modeling_columns()`), fold
  único da geometria recebida, `test_rows=()`, objetivo = média aritmética
  entre horizontes de `early_stop_loss_by_horizon`, nomes validados contra
  `GbmTrainingParams`, nada gravado, `phase='exploratory'`, C9;
  `RunGbmSweepResult.dataset_fingerprint`.
- **Aceite (A5):** objetivo correto com fake; zero escrita no store; tracker
  com `phase='exploratory'`; C9 quando todos falham; nome inválido rejeitado;
  impressão digital presente; com prefixo NaN, mesma primeira linha dos
  treinadores (I9).
- **Verificação:** `pytest tests/unit/features/modeling/application/test_run_gbm_sweep.py -v`; `make check`
- **Commit:** `feat(modeling): sweep exploratório do GBM simétrico ao do TFT [5.5/task-16]`

### Task 17 — DTO `CohortSpec`
- **Criar:** `…/modeling/application/dtos/{__init__.py, cohort_spec.py}`;
  `tests/unit/features/modeling/application/test_cohort_spec.py`
- **Fazer:** `SweepPlan` (`n_trials: int | None` — nulo no rascunho), `SweepProvenance`,
  `CohortSpec` (concept §4): validação, `is_frozen`, `hash_payload` (`asdict`,
  seed do TFT removida), `cohort_id`, `exploratory_scope_id` (hash do payload
  sem os campos de congelamento: `tft_params`, `gbm_params`, `provenance`,
  `dataset_fingerprint`, `seeds`), `max_horizon`.
- **Aceite (A1/I2/I10):** tabela paramétrica — o hash muda com cada campo e não
  muda com a seed dentro de `tft_params`; payload aceito pelo
  `CanonicalJsonHasher` real; teste estrutural: nenhum campo de
  `SweepProvenance`/`CohortSpec` carrega predição ou métrica OOS (só HPs,
  objetivos de early_stop, ids, impressões digitais).
- **Verificação:** `pytest tests/unit/features/modeling/application/test_cohort_spec.py -v`; `make check`
- **Commit:** `feat(modeling): especificação congelável do cohort confirmatório [5.5/task-17]`

### Task 18 — Port `CohortProgressLedger` + fake
- **Criar:** `…/ports/out/cohort_progress_ledger.py` (Protocol + `CohortRunLockedError`);
  `tests/fakes/features/modeling/in_memory_cohort_progress_ledger.py` (`InMemoryCohortProgressLedger`);
  `tests/contract/features/modeling/test_cohort_progress_ledger_contract.py` (`[fake]`)
- **Modificar:** `scripts/arch_baseline.toml` (entrada temporária, `issue = 102`)
- **Fazer:** `acquire_writer(break_stale)`, `release_writer`, `completed_units`,
  `mark_completed`, `environment`, `record_environment` (grava também
  `run_started_at` na primeira vez), `record_sweep_result(scope_id, model,
  result: Mapping[str, object])` e `sweep_results(scope_id)` (resultados dos
  sweeps entre processos, §1).
- **Verificação:** `pytest tests/contract/features/modeling/test_cohort_progress_ledger_contract.py -v`; `make check`
- **Commit:** `feat(modeling): port de progresso do cohort [5.5/task-18]`

### Task 19 — `JsonCohortProgressLedger`
- **Criar:** `…/modeling/adapters/out/filesystem/{__init__.py, json_cohort_progress_ledger.py}`
- **Modificar:** contrato (lado `real`); `scripts/arch_baseline.toml` (remove a entrada)
- **Fazer:** JSON em `artifacts_root/cohorts/<cohort_id>/progress.json` via
  temporário + `os.replace`; lock `O_EXCL` em `<data_root>/.writer.lock` com
  pid/host/início; `break_stale=True` remove.
- **Aceite (A4):** `[fake, real]`: persiste entre instâncias; falha injetada
  antes do `os.replace` mantém o anterior; segunda aquisição recusada nomeando o
  dono; `break_stale` remove; `run_started_at` gravado uma vez; resultados de
  sweep persistem entre instâncias (`artifacts/cohorts/<scope>/sweeps.json`, atômico).
- **Verificação:** `pytest tests/contract/features/modeling/test_cohort_progress_ledger_contract.py -v`; `python scripts/check_port_coverage.py`; `make check`
- **Commit:** `feat(modeling): ledger JSON atômico e lock de escritor do cohort [5.5/task-19]`

### Task 20 — Port `CohortRunIndex` + fake
- **Criar:** `…/ports/out/cohort_run_index.py`;
  `tests/fakes/features/modeling/in_memory_cohort_run_index.py`;
  `tests/contract/features/modeling/test_cohort_run_index_contract.py` (`[fake]`)
- **Modificar:** `scripts/arch_baseline.toml` (entrada temporária)
- **Fazer:** `recorded_runs(*, asset_id, feature_set_name, cohort_id)` (nome do
  concept §4) → `Mapping[tuple[str, int | None], Mapping[str, tuple[str, int,
  Mapping[int, frozenset[str]]]]]` — `(model_version, seed) → {run_id: (fold,
  linhas, {horizonte: target_timestamps ISO})}`. **Só tipos builtin** na
  assinatura: o adapter do analytics_store não pode importar tipo do modeling,
  e o mypy precisa casar a estrutura no composition root. Desvio declarado em
  relação ao concept §4: o valor ganha o terceiro elemento (conjuntos de
  `target_timestamp`), que o `verify` usa.
- **Verificação:** contrato `[fake]`; `make check`
- **Commit:** `feat(modeling): port do índice de runs do cohort [5.5/task-20]`

### Task 21 — `ParquetCohortRunIndex`
- **Criar:** `src/.../analytics_store/adapters/out/parquet/parquet_cohort_run_index.py`
  (docstring cita literalmente o port `CohortRunIndex` — o `port-coverage`
  reconhece o real por citação; não importa o modeling)
- **Modificar:** contrato (lado `real`, silver real em `tmp_path` com os persisters
  reais); `scripts/arch_baseline.toml` (remove)
- **Aceite (A4):** órfão (dim_run sem fatos) → rows 0; contagens e conjuntos de
  `target_timestamp` corretos; outro cohort no mesmo arquivo anual não contamina.
- **Verificação:** contrato `[fake, real]`; `lint-imports`; `python scripts/check_port_coverage.py`; `make check`
- **Commit:** `feat(analytics-store): índice de runs do cohort sobre o silver [5.5/task-21]`

### Task 22 — Port `RuntimeEnvironmentProbe` + fake
- **Criar:** `…/ports/out/runtime_environment_probe.py`;
  `tests/fakes/features/modeling/in_memory_runtime_environment_probe.py` (`InMemoryRuntimeEnvironmentProbe`);
  `tests/contract/features/modeling/test_runtime_environment_probe_contract.py` (`[fake]`)
- **Modificar:** `scripts/arch_baseline.toml` (temporária)
- **Fazer:** `snapshot() -> Mapping[str, str]` com chave `code_dirty` ("true"/"false").
- **Verificação:** contrato `[fake]`; `make check`
- **Commit:** `feat(modeling): port de snapshot do ambiente [5.5/task-22]`

### Task 23 — `GitRuntimeEnvironmentProbe`
- **Criar:** `…/modeling/adapters/out/runtime/{__init__.py, git_runtime_environment_probe.py}`
- **Modificar:** contrato (lado `real`); `scripts/arch_baseline.toml` (remove — baseline volta ao estado do `develop`)
- **Fazer:** construtor `(repo_root, tracked_paths)`; versões
  (`importlib.metadata`), device, threads do torch, CPU,
  `git rev-parse HEAD:<path>` para `src`, `uv.lock` e o arquivo do cohort,
  `git status --porcelain --untracked-files=no -- <paths>`; usa o `git` do
  ambiente (respeita `GIT_DIR`/`GIT_WORK_TREE`, §1). Git indisponível → erro
  explícito, nunca snapshot parcial.
- **Aceite (A4):** repo git temporário: commit só em `docs/` não muda o
  snapshot; mudança rastreada em `src/` muda e marca `code_dirty`; arquivo não
  rastreado não conta.
- **Verificação:** contrato `[fake, real]`; `python scripts/check_port_coverage.py`; `git diff origin/develop -- scripts/arch_baseline.toml` vazio; `make check`
- **Commit:** `feat(modeling): snapshot do ambiente e da identidade do código [5.5/task-23]`

### Task 24 — `RunConfirmatoryCohort`
- **Criar:** `…/use_cases/run_confirmatory_cohort.py`;
  `tests/unit/features/modeling/application/test_run_confirmatory_cohort.py`
- **Exceções** declaradas neste módulo (aplicação): `CohortNotFrozenError`,
  `DatasetMismatchError`, `CohortDeclarationMismatchError`,
  `EnvironmentMismatchError`, `PartialCohortUnitError`,
  `CompletedUnitCorruptedError`.
- **Fazer:** construtor recebe use cases, ports, hasher, store, `modeling_columns`
  e `observed_feature_set_hash` (injetados). O use case é o **dono único** do
  lock no `run`. Fluxo: I1 → `acquire_writer` → grid
  + impressão digital → I4 (4 igualdades) → `fits` → ambiente (I5: recusa
  `code_dirty` **já na 1ª execução**; grava na 1ª; compara depois) → unidades
  (I6/I7) com `ScopeSpec(cohort_id, max_horizon)` e seed por unidade → marca →
  `release_writer` em `finally`.
- **Aceite (A2):** todos os casos do concept A2 com fakes, mais: 1ª execução com
  `code_dirty` → recusa sem treinar; `fits` falho antes de qualquer treino; lock
  liberado em erro; I9 — as unidades recebem dataset que produz a mesma primeira
  linha que os use cases da Task 10.
- **Verificação:** `pytest tests/unit/features/modeling/application/test_run_confirmatory_cohort.py -v`; `make check`
- **Commit:** `feat(modeling): orquestração retomável do cohort confirmatório [5.5/task-24]`

### Task 25 — Wiring da ingestão no composition root
- **Modificar:** `src/financial_forecasting/composition_root.py`; `tests/unit/shared/test_composition_root.py`
- **Fazer:** `IngestCandles/News/Fundamentals` com fetchers Parquet sob
  `settings.data_root` (`raw/market/candles`, `raw/news`, `processed/fundamentals`).
- **Verificação:** `pytest tests/unit/shared/test_composition_root.py -v`; `lint-imports`; `make check`
- **Commit:** `feat(market-data): wiring da ingestão local no composition root [5.5/task-25]`

### Task 26 — Wiring de sweeps, cohort e adapters
- **Modificar:** `composition_root.py`; `src/.../shared/infrastructure/config/settings.py`
  (`repo_root: Path`, para o probe); `tests/unit/shared/test_composition_root.py`
- **Fazer:** `RunGbmSweep`, `RunConfirmatoryCohort` (com `modeling_columns()` e
  `feature_set_hash()` injetados), `JsonCohortProgressLedger`,
  `ParquetCohortRunIndex`; fábrica `runtime_probe_for(cohort_path)` que monta o
  `GitRuntimeEnvironmentProbe` (o caminho do cohort só existe depois do parse
  dos argumentos); parâmetros opcionais de `wire_dependencies` para injetar o
  modelo de sentimento e a fábrica do probe (fakes nos testes e no e2e), sem
  condicional de produção.
- **Verificação:** idem Task 25
- **Commit:** `feat(modeling): wiring de sweeps e cohort no composition root [5.5/task-26]`

### Task 27 — Arquivo do cohort: parse e dump
- **Criar:** `…/modeling/adapters/in/{__init__.py, cli/__init__.py, cli/cohort_file.py}`
  (docstring com o aviso da keyword `in`, LAYOUT §8);
  `tests/unit/features/modeling/adapters/{__init__.py, in_/__init__.py, in_/test_cohort_file.py}`
  (pasta de teste sem keyword; `__init__.py` por convenção do repo)
- **Aceite:** `parse(dump(spec)) == spec` (rascunho e congelado); campo ausente,
  tipo errado, seed repetida, revisão negativa → erro nomeando o campo.
- **Verificação:** `pytest tests/unit/features/modeling/adapters -v`; `make check`
- **Commit:** `feat(modeling): leitura e escrita do arquivo do cohort [5.5/task-27]`

### Task 28 — Comandos do cohort (`sweep`, `freeze`, `run`, `verify`)
- **Criar:** `…/adapters/in/cli/cohort_commands.py`;
  `tests/unit/features/modeling/adapters/in_/test_cohort_commands.py`
- **Fazer:** tudo recebido do composition root (regra 3). `sweep`: exige
  `n_trials` (ou `--n-trials`), adquire o lock, passa `spec.geometry.exploratory()`
  e `ScopeSpec(exploratory_scope_id)` aos dois sweeps e grava os resultados pelo
  ledger. `freeze`: adquire o lock, lê os resultados do ledger e grava
  `best_params`, proveniência (impressões digitais **dos resultados**) e
  `dataset_fingerprint` (do grid atual; I4 exige igualdade com a proveniência).
  `run`: chama o use case (que detém o lock). `verify`: calcula o
  esperado (`expected_prediction_rows` × unidades × S), compara com o
  `CohortRunIndex`, confere igualdade dos conjuntos de `target_timestamp` por
  horizonte; exit ≠ 0 em divergência; **não importa nada de evaluation**.
- **Aceite:** com fakes: geometria recebida pelos sweeps = `exploratory()`
  (espião nos limites do fold); scope id do sweep; `--n-trials` sobrepõe;
  `sweep` e `freeze` com lock já detido → `CohortRunLockedError`; `run` não
  adquire o lock no comando; proveniência vem dos resultados gravados pelo
  `sweep` (não de releitura); `verify` exit 0/≠0; teste de import proíbe
  `features.evaluation` no módulo (preventivo: o pacote ainda não existe em
  `src/`).
- **Verificação:** `pytest tests/unit/features/modeling/adapters -v`; `make check`
- **Commit:** `feat(modeling): comandos de sweep, congelamento, corrida e verificação do cohort [5.5/task-28]`

### Task 29 — Ponto de entrada `cli.py` e `materialize`
- **Criar:** `src/financial_forecasting/cli.py`; `tests/unit/test_cli.py`
- **Fazer:** argparse; `--data-root` obrigatório em todos os subcomandos →
  `Settings(data_root=…)` → `wire_dependencies`; `main(argv, *, wiring=None)`
  aceita dependências injetadas (e2e). `materialize` (lock via ledger; checa o
  extra `sentiment` **só quando nenhum modelo de sentimento foi injetado**;
  ingestão ×3 → `BuildDataset`); despacha os comandos do cohort via `importlib`
  (LAYOUT §8).
- **Aceite:** `materialize` com lock já detido → `CohortRunLockedError` nomeando o
  dono, e vice-versa com `run`; extra ausente sem injeção → erro com a instrução;
  com modelo injetado, sem checagem; subcomando sem `--data-root` → erro de uso.
- **Verificação:** `pytest tests/unit/test_cli.py -v`; `make check`
- **Commit:** `feat(cli): ponto de entrada da linha de comando e materialização [5.5/task-29]`

### Task 30 — LAYOUT: `cli.py` e VOs de identidade
- **Modificar:** `docs/LAYOUT.md` (§2 `cli.py`; §7 `CohortHash`, `DatasetContentFingerprint`)
- **Verificação:** `make docs-check`
- **Commit:** `docs(layout): cli.py e VOs de identidade do cohort [5.5/task-30]`

### Task 31 — Ponta a ponta do runner (A6)
- **Criar:** `tests/e2e/test_cohort_cli.py`; fixtures de dado bruto mínimo em `tests/e2e/fixtures/cohort/`
- **Fazer:** o teste cria um repositório git descartável em `tmp_path` com o
  arquivo do cohort e um `src/` mínimo, commita depois do `freeze` (o probe real
  vê árvore limpa) e injeta via `main(argv, wiring=…)` o modelo de sentimento
  fake e os overrides de `Settings` — `repo_root` e `artifacts_root` apontando
  para o `tmp_path` (em produção vêm de variável de ambiente/default; nada
  depende do diretório corrente do processo). Cohort da fixture mínimo e fixado: `n_folds = 2`,
  1 seed, `max_epochs` baixo, `n_trials = 1`; tempo medido registrado em §7
  (limite do job de CI: 30 min).
- **Aceite (A6):** sem `skip`; fixture ≥ aquecimento + 3 gaps + early_stop +
  calib + n_folds × test, `horizons=(1, 7)`: `materialize` → `sweep`
  (`--n-trials 1`) → `freeze` → commit → `run` → `verify` exit 0 → segunda
  execução com ledger e checkpoints no disco pula tudo; lock órfão →
  `run` recusa, `--break-stale-lock` libera; unidade parcial simulada (fatos
  apagados de um run) → `PartialCohortUnitError` → `revision += 1` → `run`
  conclui; TOML inválido, brutos ausentes, gate de qualidade rejeitando → erros
  de §6.
- **Verificação:** `pytest tests/e2e/test_cohort_cli.py -v`; `make check`
- **Commit:** `test(modeling): ponta a ponta do runner do cohort [5.5/task-31]`

### Task 32 — Rascunho do arquivo do cohort
- **Criar:** `config/cohorts/aapl_confirmatory.toml`
- **Fazer:** `revision = 0`; AAPL; feature set + `feature_set_hash` + `pipeline_version`
  atuais; horizontes (1, 7); grade e geometria (D6, D7); `device = "cpu"`; espaços
  D9 (faixas do GBM conferidas na documentação oficial do LightGBM pelo
  `evidence-verifier` e registradas em §7); base params; `sampler_seed`;
  baselines canônicas; `n_trials` e `seeds` vazios [P].
- **Verificação:** `python -m financial_forecasting.cli run --data-root data/cohorts/aapl --cohort config/cohorts/aapl_confirmatory.toml` (container) → `CohortNotFrozenError`
- **Commit:** `feat(modeling): rascunho do arquivo do cohort AAPL [5.5/task-32]`

### Bloco C — Execução real

### Task 33 — Materialização real e medições → **PARADA [P]**
- **Modificar:** `technical.md` §7
- **Fazer:** copiar os brutos para os três caminhos que o wiring da Task 25 lê:
  `data/cohorts/aapl/raw/market/candles/AAPL/candles_AAPL_1d.parquet`,
  `data/cohorts/aapl/raw/news/AAPL/news_AAPL.parquet`,
  `data/cohorts/aapl/processed/fundamentals/AAPL/fundamentals_AAPL.parquet`;
  instalar o extra `sentiment`; preparar o git no container (montagem
  read-only do `.git` principal, `GIT_DIR`, `GIT_WORK_TREE`, `safe.directory`)
  e conferir `git status` dentro do container; `materialize --data-root
  data/cohorts/aapl`. Medir (skill `data-shape-evidence`,
  consultas coladas): gate de qualidade (R9), prefixo cortado, NaN interior,
  linhas úteis do fold 0 e τ·n (limiar D6), tempo de um trial de cada sweep
  (`sweep --n-trials 1`). **Parar** e perguntar [P]: `n_trials` e seeds (e ROCm
  se o custo inviabilizar → Tasks novas).
- **Verificação:** comandos e saídas colados em §7; respostas [P] em §7 e na #102.
- **Commit:** `docs(modeling): medições do dado real e decisões do cohort [5.5/task-33]`
  (mudança de geometria, se o limiar exigir, vai em commit `feat(modeling)` próprio antes do 34)

### Task 34 — Sweeps reais, congelamento e âncora (A7)
- **Modificar:** `config/cohorts/aapl_confirmatory.toml`; `technical.md` §7
- **Fazer:** preencher `n_trials`/`seeds`; `sweep` → `freeze`; reexecutar A3 com
  os `gbm_params` congelados; commit; `git push`; tag `cohort/<cohort_id>` no
  remoto; comentário na #102 com `cohort_id` + hash completo. **Sem rebase daqui
  até o fim da Task 35.**
- **Comandos:** `cli sweep --data-root data/cohorts/aapl --cohort config/cohorts/aapl_confirmatory.toml`;
  `cli freeze --data-root … --cohort …`; `pytest tests/contract/features/modeling/test_quantile_model_trainer_determinism.py -v`.
- **Verificação:** `git ls-remote --tags origin "cohort/*"`;
  `gh api --paginate repos/{owner}/{repo}/issues/102/comments --jq '.[] | select(.body | contains("cohort/")) | .created_at'`;
  saída de A3 com os params congelados em §7
- **Commit:** `feat(modeling): cohort AAPL congelado [5.5/task-34]`

### Task 35 — Corrida real, cega, e verificação por contagem (A8)
- **Modificar:** `technical.md` §7
- **Fazer:** `run` (em segundo plano; retomar se cair); `verify`. Colar em §7 a
  saída do `verify` (exit 0), o `run_started_at` do ledger e a comparação com o
  `created_at` do comentário da #102. **Nenhuma métrica.**
- **Comandos:** `cli run --data-root data/cohorts/aapl --cohort config/cohorts/aapl_confirmatory.toml` (segundo plano).
- **Verificação:** `python -m financial_forecasting.cli verify --data-root data/cohorts/aapl --cohort config/cohorts/aapl_confirmatory.toml` exit 0
- **Commit:** `docs(modeling): evidência da corrida confirmatória AAPL [5.5/task-35]`

### Task 36 — Runbook
- **Criar:** `docs/runbooks/confirmatory-cohort-aapl.md` (template `docs/templates/runbook.md`)
- **Aceite:** cada passo marcado como **executado de verdade** (Tasks 33–35, com
  referência a §7) ou **coberto pela Task 31** (retomada, `--break-stale-lock`,
  remediação por `revision` — todos no aceite da Task 31).
- **Verificação:** `make docs-check`
- **Commit:** `docs(runbook): runbook do cohort confirmatório AAPL [5.5/task-36]`

### Task 37 — Nota no ADR 5.4.0003
- **Modificar:** `docs/adr/5_4_0003-torch-core-dependency-cpu-index.md`
- **Verificação:** `make docs-check`
- **Commit:** `docs(adr): ambiente confirmatório em CPU por decisão da 5.5 [5.5/task-37]`

### Task 38 — Nota no overview (ASSUM-2)
- **Modificar:** `docs/overview.md`
- **Verificação:** `make docs-check`
- **Commit:** `docs(overview): ASSUM-2 anotada com o desvio para CPU [5.5/task-38]`

## 3. Gate de saída da Stage

### Verificações automatizadas
```bash
make check
make test-cov
python scripts/check_technical_postexec.py docs/stages/5.5-confirmatory-retrain/technical.md
git diff origin/develop -- scripts/arch_baseline.toml   # vazio
```

### Verificações funcionais
- [ ] `verify` exit 0 sobre o cohort real (Task 35).
- [ ] Segunda execução de `run` pula todas as unidades.
- [ ] Tag `cohort/<cohort_id>` no remoto e comentário da #102 anteriores ao `run_started_at`.

### Checklist de fechamento
- [ ] Todas as Tasks commitadas com check verde; coverage ≥ 90% global e por arquivo tocado
- [ ] `stage 5.5: complete`; roadmap 5.5 `done` com datas
- [ ] ADRs 5.5.0001–0004 `accepted`; runbook criado
- [ ] PR com `Closes #102` e `Closes #99`
- [ ] `concept.md` sem retoque pendente

## 4. Ordem de dependência entre Tasks

```
01, 02, 03 (independentes)
04 ─► 05 ─► 06 ─► 07 ─► 08 ─► 10
12 ─► 09 (09 precisa do VO de impressão digital)   07 ─► 09
11, 12 ─► 17
13 ─► 14, 16 ; 15 ─► 16 ; 07, 12 ─► 16
18 ─► 19 ; 20 ─► 21 ; 22 ─► 23
06, 10, 11, 12, 17, 18, 20, 22 ─► 24
03, 19, 21, 23, 24 ─► 25 ─► 26 ─► 27 ─► 28 ─► 29 ─► 30 ─► 31 ─► 32 ─► 33 ─[P]─► 34 ─► 35 ─► 36 ─► 37 ─► 38
```

Ordem de execução: 01, 02, 03, 04, 05, 06, 07, 08, **12, 09**, 10, 11, 13, 14,
15, 16, 17, 18–23, 24, 25–32, 33, [P], 34–38.

Checkpoint C após: 04, 10, 12/11, 16, 17, 23, 24, 29, 31, 35.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Caracterização revela divergência intencional que não cabe em parâmetro | parar antes da Task 07 e perguntar |
| Entrada do baseline esquecida → "baseline morto" | cada par port→adapter remove a sua; Task 23 confere `git diff` vazio contra o develop |
| Gate de qualidade rejeita o dado real (R9) | medir e decidir com a medição (Task 33) |
| Custo em CPU inviável (R1) | parar na Task 33; "ROCm" abre Tasks novas |
| Queda longa do `run` | retomar pelo ledger; `--break-stale-lock` |
| `develop` avança durante a execução | rebase livre até a Task 33 e depois da 35; proibido entre 34 e 35 |
| Git indisponível no container (worktree com `.git` em caminho Windows) | montagem read-only do `.git` principal + `GIT_DIR`/`GIT_WORK_TREE` (§1), conferida na Task 33 antes de qualquer treino |
| e2e (Task 31) estoura o tempo do job de CI | cohort da fixture mínimo e fixado; tempo medido em §7; reduzir épocas antes de reduzir cobertura |

## 6. Referências

- [`./concept.md`](./concept.md); ADRs [5.5.0001](../../adr/5_5_0001-frozen-hashed-cohort-spec.md)–[5.5.0004](../../adr/5_5_0004-single-training-grid-warmup-trim.md)
- [`../../LAYOUT.md`](../../LAYOUT.md); [`../../CONVENTIONS.md`](../../CONVENTIONS.md); [`../../PIPELINE.md`](../../PIPELINE.md) §4.3
- Skills: `hex-arch-python`, `composition-root`, `orchestrator-design`, `pytest-with-fakes`, `task-ordering-hex`, `data-shape-evidence`, `dmls-ch05-model-development-and-evaluation`
- Issues #102, #99, #64; PR #98; ADR 0.0.0010 (seeds devolvidas à 5.5)

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

### 2026-09-27 — [decision] Tasks 02–04 — verificação em lote do `make check` — Claude (Opus 5.5)
**Contexto:** o `make check` completo leva ~10 min no container; as Tasks 02 (`.gitignore`), 03 (escrita atômica + testes) e 04 (só testes de caracterização) foram preparadas em sequência na mesma árvore.
**Decisão:** um `make check` verde sobre a árvore com as três mudanças valida os três commits, aplicados em ordem: cada estado intermediário é um subconjunto que só **remove testes novos** ou a mudança do `.gitignore` (sem efeito em código), e a cobertura continua acima do gate. Testes focados de cada Task rodaram antes (82 do repositório Parquet; 15 de caracterização).
**Razão:** o rigor do gate é o mesmo; o custo cai de 30 para 10 min. Não se aplica a Tasks que mudam código de produção em sequência — cada uma dessas tem o seu `make check`.

### 2026-09-27 — [decision] Task 04 — divergências entre as 4 leituras do dataset — Claude (Opus 5.5)
**Contexto:** diff das cópias de `_load_dataset` (`run_baselines.py`, `train_gbm_quantile.py`, `train_tft.py`, `run_tft_sweep.py`) e das auxiliares `_timestamp_of`/`_target_return_of`/`_feature_value_of` (idênticas nas 4).
**Divergências e disposição:**
- Código do erro de dataset vazio — `C7` nas baselines, `C1` nos três treinadores (fixado nos testes de cada use case): **intencional**, cada use case mantém a própria checagem de vazio e o seu código; o grid único não repete essa checagem.
- Baselines não leem nem checam colunas de feature: **muda por decisão da Stage** (concept §4, grid único): na Task 10 passam a checar as colunas de modelagem (C6) e a cortar o prefixo.
- `RunTftSweep` não devolve os timestamps: **acidental** (não precisava deles); converge ao usar o grid, que devolve tudo.
- Texto das mensagens (C6, tipos): idêntico; vira uma só no grid.
**Razão:** preservar os contratos de erro que os testes existentes fixam e convergir só o que não carrega significado.
- Derivação das colunas — GBM por `expected_feature_names()`, TFT/sweep por `unknown_feature_names() + known_feature_names()`: caminhos distintos, **mesmo conjunto** hoje; fixado por teste (Checkpoint C) para o grid único cortar pelo mesmo conjunto (I9).

### 2026-09-27 — [deviation] Tasks 06–10 — `_load_dataset` fica como método fino; grid sem `asset_id` — Claude (Opus 5.5)
**O que mudou:** (1) em vez de apagar `_load_dataset` (critério "`grep` vazio" das Tasks 07–10), cada use case mantém um `_load_dataset` fino que lê o store, faz a checagem de vazio com o seu código e delega ao `build_training_grid`; o critério passa a ser "`_load_dataset` não tem lógica de parsing — só leitura, checagem de vazio e delegação". (2) `build_training_grid(rows, *, columns)` não recebe `asset_id`: o filtro de ativo é da leitura do store (partição), como a caracterização mostrou.
**Por quê:** Checkpoint C — a caracterização da Task 04 chama `_load_dataset`; apagar o método obrigaria reescrever os testes no mesmo commit do refactor, e eles deixariam de proteger a extração. A duplicação que a #99 ataca é a lógica (~55 linhas × 4), não o nome.

### 2026-09-27 — [deviation] Task 07 — I11 da 5.3 substituído pelo grid único — Claude (Opus 5.5)
**O que mudou:** o invariante I11 da Stage 5.3 ("feature ausente atravessa o port como NaN") deixa de valer para o GBM: ausente no **prefixo** é cortado do treino; ausente no **interior** ergue `InteriorMissingValuesError` antes de o port ser chamado. O teste `test_i11_none_feature_value_reaches_the_port_as_nan` foi reescrito como dois testes do comportamento novo; o caso "alvo não numérico" da caracterização passou a usar string (o `None` de alvo agora é ausente, coberto pelos testes do grid).
**Por quê:** decisão já tomada no concept (D11) e no ADR 5.5.0004 — sem regra única, TFT (recusa NaN) e GBM (aceita) treinariam sobre conjuntos diferentes; imputar em silêncio foi descartado.
**Task 08 (TFT):** mesma substituição para a política de ausência da 5.4 ("`None` vira NaN na fronteira do port"): `test_none_feature_reaches_the_port_as_nan` virou dois testes (prefixo cortado; interior ergue antes do treino).

### 2026-09-27 — [deviation] Tasks 09–10 — teste do conjunto de colunas apagado na 09 e restaurado na 10 — Claude (Opus 5.5)
**O que houve:** na Task 09, ao remover o teste legado "`None` vira NaN" (nenhum use case restava no caminho antigo), o recorte do arquivo levou junto `test_gbm_and_tft_consume_the_same_modeling_columns` (correção C1 do Checkpoint C), e o `ruff --fix` de F401 removeu os imports que ficaram órfãos. Detectado na Task 10 (F821 ao reusar `expected_feature_names`) e restaurado byte a byte a partir de `ec8c05d` no commit da Task 10.
**Task 10 — mudanças previstas:** as baselines passam a exigir as colunas de modelagem (C6) e a começar na mesma linha dos modelos; as fixtures de `test_run_baselines.py` (unit e integração) e o golden de identidade ganharam as colunas; o golden de `run_id` das baselines **não** mudou (a identidade delas não depende das features), o que confirma que só o grid mudou.

### 2026-09-27 — Checkpoint C (bloco 01–04) — disposições — Claude (Opus 5.5)
- C1 (médio) caracterização presa a método que seria apagado → **corrigido** pelo desvio acima + teste do conjunto de colunas GBM = TFT (`task-04-fix`).
- C2 (médio) fixture com `None` na 1ª linha contrariava "sem NaN" → **corrigido**: fixture sem ausentes; `None`→NaN em teste próprio marcado como mudança prevista (`task-04-fix`).
- C3 (médio) temporário válido ao lado da partição, lido pelo DuckDB, sem teste → **corrigido** (`task-03-fix`).
- C4 (baixo) limpeza na primeira gravação sem teste → **corrigido** (`task-03-fix`).
- C5 (baixo) queda no meio do `write_table` → **corrigido** (`task-03-fix`).
- C6 (baixo) sem `fsync` → **corrigido** como escopo declarado na docstring (atomicidade contra queda do processo; energia coberta pela reconferência de contagens do ADR 5.5.0003).
- C7 (baixo) limpeza silenciosa → **refutado**: o lock de escritor único impede apagar temporário de outro processo em voo (artefato: ADR 5.5.0003 §Decision "Single writer per `data_root`"); o adapter não tem logger e incluir um só para isso não muda comportamento.

### 2026-09-27 — Checkpoint C (bloco 05–10 + 12) — disposições — Claude (Opus 5.5)
- F1 (médio) TFT/sweep cortam e (no sweep) calculam a impressão digital na ordem do TFT; o cohort usará a de `modeling_columns()` — hoje coincidem só porque o registry não tem spec `known`; I4 falharia sem mudança real no dado → **corrigido** canonizando a ordem no VO (`DatasetContentFingerprint` ordena os nomes: colunas nomeadas são o mesmo conteúdo em qualquer ordem) + teste de igualdade sweep × `modeling_columns()` com ordem invertida; mutação real (remover a ordenação) derruba 2 testes (`task-12-fix`, `task-09-fix`).
- F2 (baixo) filtro de `None` morto após o corte, que desalinharia a coluna → **corrigido**: ausente após o corte ergue (`_finite_tail`).
- F3 (baixo) `TrainingGrid.columns` mutável → **corrigido** com `MappingProxyType`.
- F4 (baixo) sweep sem teste de ausente no interior → **corrigido**.
- F5 (info) baselines passam a falhar com ausente no interior → já declarado (concept §4, R6); medido na Task 33.
- F6 (info) mover `modeling_columns()` para módulo neutro → **refutado**: um módulo novo importando o registry é aresta nova que o `bc-independence` reprova (`.importlinter`, `ignore_imports` lista só `train_gbm_quantile`, `run_baselines`, `train_tft`); a função fica no módulo que já tem a aresta declarada.

### 2026-09-27 — [finding] Task 14 — perda de early_stop do LightGBM não é bit a bit reprodutível — Claude (Opus 5.5)
**Contexto:** no contrato de determinismo, com `num_leaves=63, learning_rate=0.2, min_data_in_leaf=40`, duas seeds deram grades e `best_iteration` **idênticas**, mas `early_stop_loss_by_horizon` diferente no último ulp (0.004482447927849784 × …783).
**Leitura:** a métrica de avaliação do LightGBM é reduzida em paralelo (ordem de soma não fixa); `deterministic=True` fixa o treino, não essa soma. A D4 (GBM uma execução por fold) se mantém: o que o cohort persiste — as predições — é exato.
**Disposição:** o teste exige igualdade exata de grades e iteração e `rel=1e-12` na perda. **Direção sugerida:** o sweep do GBM (Task 16) compara objetivos que podem diferir em ~1e-18 entre execuções; empate exato é irrelevante na prática, mas o `best_trial` do Optuna pode divergir entre reexecuções num empate — anotar no runbook que a reprodução do sweep é "mesmo melhor trial até ruído de ulp". **Stage candidata:** esta (Task 36, runbook).

### 2026-09-27 — [finding] Task 14 — correção do diagnóstico da perda não reprodutível — Claude (Opus 5.5)
**Correção (não reescreve a entrada anterior):** o Checkpoint C mediu que a perda de early_stop do LightGBM varia no último ulp **entre execuções com a mesma seed** (seed 0: `…394309` em três rodadas e `…394308` na quarta), não entre seeds. A causa segue sendo a soma paralela da métrica; o efeito relevante é outro: com a perda como objetivo do sweep, um empate entre trials viraria sorteio e uma reexecução poderia congelar outro `gbm_params`. **Disposição:** os dois sweeps arredondam o objetivo a 12 dígitos significativos antes do `tell` (`stable_objective`); empates ficam exatos e o estudo desempata pelo menor número de trial. O contrato de chamadas idênticas passa a conferir a perda (`rel=1e-12`). A direção "anotar no runbook" da entrada anterior fica substituída por esta correção de código.

### 2026-09-27 — Checkpoint C (bloco 11–16) — disposições — Claude (Opus 5.5)
- F1 (alto) teste de determinismo vácuo — rótulos de ruído puro davam `best_iteration = 1` e comparavam uma árvore só → **corrigido**: rótulos com sinal e `max(best_iteration) > 1` asserido (`task-14-fix`).
- F2 (médio) perda não reprodutível entre execuções → **corrigido** (entrada acima; `task-14-fix` e `task-16-fix`).
- F3 (médio) `expected_runs` prometido na Task 11 e ausente → **corrigido** (`task-11-fix`).
- F4 (médio) contagem esperada conferida por regra reimplementada → **corrigido**: o teste conta pelo `MultiHorizonPredictionPersister.build` real (`task-11-fix`).
- F5 (baixo) `h > test_size` e horizontes repetidos → **corrigido**: contagem por deslocamento a partir do fim da grade; repetidos recusados (`task-11-fix`).
- F6 (médio) sweep do GBM aceitava `h < 1` (vazaria rótulos do fim da série) e horizontes repetidos → **corrigido** nos dois sweeps (`task-16-fix`).
- F7 (baixo-médio) exigir fold único nos sweeps → **refutado**: o ADR 5.5.0002 descartou mudar o `RunTftSweep` (Alternativa B) e manteve a garantia na geometria passada pelo runner, verificada na Task 28 (espião nos limites do fold); exigir `n_folds == 1` quebraria `TestFoldChoice` da 5.4 contra a decisão registrada.
- F8 (baixo) docstring do `RunTftSweep` ("o último fold é o mais representativo") contradizia o D2 → **corrigido** (`task-16-fix`).
- F9 (baixo-médio) impressão digital calculada em cópias nos sweeps e sem teste de igualdade GBM × TFT → **corrigido**: `TrainingGrid.content_fingerprint` como caminho único + teste de igualdade entre os dois sweeps (`task-16-fix`).
- F10 (baixo) `seed` buscável, nomes repetidos e espaço validado só ao rodar → **corrigido**: `seed` fora, repetidos recusados, `SweepPlan` valida na carga (`task-16-fix`).
- F11 (baixo) igualdade perda = mínimo da média testada só no helper → **aceito como limitação**: o helper `_grid_mean_at` é o único caminho de cálculo do adapter e o LightGBM não expõe as histórias fora dele; o contrato confere finitude, positividade e estabilidade.
- F12 (baixo) import de função privada → **corrigido**: `labels_from_full_grid` público (`task-16-fix`).
- F13 (baixo) texto da Task 12 desatualizado quanto à ordem das colunas → **refutado como edição**: fora de §7 o technical `done` não é editável (`check_technical_postexec.py`); a mudança está registrada no Checkpoint C do bloco 05–10 + 12, acima.

### 2026-09-27 — [deviation] Task 18 — commit com o gate vermelho, corrigido no commit seguinte — Claude (Opus 5.5)
**O que houve:** o commit da Task 18 (`6a3f01f`) foi feito com o `make check` falhando em `tests/architecture/test_port_coverage_gate.py::test_real_repo_violations_are_exactly_the_declared_baseline`, que fixa a lista exata de ports em violação (`["Hasher"]`). A entrada temporária do baseline, prevista no plano, precisava entrar também nesse teste — o plano não previa. A falha passou porque o comando de verificação imprimia o código de saída do `echo`, não o do `make`.
**Correção:** `task-18-fix` inclui `CohortProgressLedger` na lista fixada (sai na Task 19, com a entrada do baseline); as Tasks 20–23 seguem o mesmo par (entrada no port, saída no adapter). A verificação passa a imprimir `MAKE_EXIT` e o commit só roda com `MAKE_EXIT=0`.

### 2026-09-27 — [decision:E] Checkpoint C (bloco 17–23) — arquivo não rastreado em `src/` conta como mudança — Claude (Opus 5.5)
**Contexto:** concept I5 e A4 dizem "arquivos não rastreados não contam"; a foto usava `--untracked-files=no`. Um módulo novo, não ignorado, dentro de `src/` é importado e muda o código que roda sem aparecer em `code.src` (hash do que está commitado) nem em `code_dirty`.
**Decisão:** `code_dirty` passa a usar `git status --porcelain --untracked-files=all` restrito a `src/`, `uv.lock` e o arquivo do cohort. O objetivo da regra original — não contar `artifacts/` (ledger, checkpoints) — continua atendido, porque `artifacts/` e `data/` são ignorados pelo git e nunca aparecem no porcelain.
**Base:** fato verificável sobre o código (E): Python importa qualquer módulo presente em `src/`, rastreado ou não. Registrada aqui como `[decision]` (CONVENTIONS §3.2: depois de iniciada a Fase 4, sem regredir o concept). A redação de I5/A4 no concept fica mais frouxa que o comportamento; a DoD da 5.5 não muda.

### 2026-09-27 — Checkpoint C (bloco 17–23) — disposições — Claude (Opus 5.5)
- F1 (médio) `release_writer` apagava lock de outro dono após `break_stale` → **corrigido**: token único no lock; libera só com o token próprio + teste real.
- F2 (médio) resultados de sweep mudavam de forma no JSON só no real → **corrigido**: fake faz a mesma ida e volta; contrato com valor aninhado.
- F3 (médio) `TrainingGrid.content_fingerprint` no domínio importava port de aplicação (sob `TYPE_CHECKING`) → **corrigido**: helper `grid_fingerprint` na aplicação (`train_gbm_quantile.py`, ao lado de `modeling_columns`), usado pelos dois sweeps e pelo cohort.
- F4 (médio) não rastreado em `src/` fora da identidade → **corrigido** (decisão acima).
- F5 (baixo) `dim_run` sem filtro de feature set; `fold` nulo virava `"None"`; `rows` opcional no fake → **corrigido** + teste com seeds do TFT (inclusive 2**40) e baseline de seed nula no mesmo cohort.
- F6 (baixo) leitura de todos os fatos do ativo na retomada → **aceito** na escala piloto (~230 mil linhas por revisão); projeção por `run_id` fica para quando a memória pesar.
- F7 (baixo) adapter tipado com a classe irmã → **corrigido**: tipado pelo port `AnalyticsRepository`.
- F8 (baixo) atomicidade do ledger sem escopo declarado; JSON vazio após queda de SO ergueria erro cru → **corrigido**: docstring com escopo (queda do processo) e erro nomeando o arquivo.
- F9 (baixo) texto de `environment()` prometia "primeira execução" → **corrigido**: redação alinhada (o use case grava só na primeira).
- F10 (baixo) construtor do probe `(repo_root, cohort_file, device)` diferente do plano `(repo_root, tracked_paths)` → **registrado** aqui como desvio: os caminhos rastreados são fixos (`src`, `uv.lock`) mais o arquivo do cohort; `device` é o declarado (o adapter do TFT fixa CPU). Caminho de cohort fora do repositório → erro explícito.
- F11 (baixo) testes: mudança em stage, variáveis de git isoladas, `commit.gpgsign=false`, `n_trials` no rascunho → **corrigidos**.
- F12 (baixo) "empates exatos" exagerava o efeito do arredondamento → **corrigido**: "reduz", com o limite declarado.

### 2026-09-27 — [finding] Task 28 — hash do cohort dependia de `8` vs `8.0` — Claude (Opus 5.5)
**O que houve:** o teste dos comandos calculou o scope id do sweep sobre o spec em memória (`SearchDimension(low=8)`), e o comando, sobre o spec lido do arquivo, que converte para o tipo declarado (`low: float` → `8.0`). Os dois specs são iguais pela igualdade do dataclass (`8 == 8.0`), mas o JSON canônico distingue `8` de `8.0`, então o mesmo cohort teria dois hashes.
**Correção:** `CohortSpec.hash_payload` troca float inteiro por int, recursivamente (`task-17-fix`). Specs iguais passam a ter o mesmo hash, e um float não inteiro continua mudando o hash (dois testes novos em `test_cohort_spec.py`). Nenhum cohort tinha sido congelado antes da correção, então nenhum `cohort_id` publicado muda.

### 2026-09-27 — [deviation] Tasks 28–29 — `--break-stale-lock` no use case, helpers públicos e `materialize --cohort` — Claude (Opus 5.5)
- **`RunConfirmatoryCohortCommand.break_stale_lock`:** o aceite da Task 31 exige `run --break-stale-lock`, e no `run` quem detém o lock é só o use case (o comando não o adquire). O sinalizador entra no comando do use case e segue para `acquire_writer(break_stale=...)`. A alternativa, o comando do CLI adquirir e soltar o lock antes do use case, deixaria uma janela de corrida.
- **`cohort_model_keys(spec)` e `load_training_grid(...)` públicos em `run_confirmatory_cohort.py`:** o `verify` e o `freeze` usam a mesma enumeração de modelos e a mesma leitura do grid da corrida, em vez de copiá-las no adapter.
- **`materialize` recebe `--cohort`:** o comando da Task 33 no plano (`materialize --data-root …`) não diz de onde vem o ativo, e ele passa a vir do arquivo do cohort, fonte única do `asset_id`. A janela de ingestão é a mesma janela ampla e fixa do calendário do composition root; o que entra no dataset é decidido pelos brutos em `data_root`.
- **`sweep` retomável por modelo:** um resultado já gravado sob o mesmo scope id não roda de novo. Se o processo cair entre o sweep do TFT e o do GBM, o do TFT não é refeito.

### 2026-09-27 — [measurement] Task 31 — tempo do ponta a ponta (A6) — Claude (Opus 5.5)
**Fixture:** 560 sessões XNYS sintéticas a partir de 2019-01-02 (`tests/e2e/fixtures/cohort/raw_cohort_fixture.py`). Materializadas, dão 559 linhas de dataset e 308 sessões no grid útil, depois de cortado o prefixo de aquecimento de 251 linhas. O cohort usa `n_folds = 2`, teste/early_stop/calib de 20 sessões, `embargo = 1`, `horizons = (1, 7)`, 1 seed, `n_trials = 1` e TFT com `max_epochs = 1`.
**Tempo:** `test_cohort_runner_end_to_end` levou 100,4 s, 80,0 s e 168,6 s em três execuções no container (CPU dividida com outros jobs na terceira). Os três testes de erro somam cerca de 3 s. Folga grande contra o limite de 30 min do job de CI.
**Comando:** `uv run --no-sync pytest tests/e2e/test_cohort_cli.py -q -p no:warnings --durations=4` → `4 passed in 104.42s`. Dentro do `make check` (com cobertura), a suíte inteira passou a levar ~20 min (antes ~9–14 min).

### 2026-09-27 — [decision:C] Task 32 — faixas do sweep do GBM: a documentação oficial do LightGBM não traz faixa — Claude (Opus 5.5)
**Contexto:** o D9 diz "faixas da documentação oficial do LightGBM (guia de *parameter tuning*), conferidas no technical". A pesquisa (`evidence-researcher`) e a verificação (`evidence-verifier`), ambas no texto cru da versão pinada no `uv.lock` (LightGBM v4.7.0; optuna-integration v4.9.0), mostram que a premissa é falsa: nem `docs/Parameters-Tuning.rst` nem `docs/Parameters.rst` dão faixa numérica de busca para `num_leaves`, `learning_rate` ou `min_data_in_leaf`.
**Evidência conferida pelo verificador** (itens 1–7 sustentados; item 8 parcial):
- Defaults e restrições (`Parameters.rst`):
  - `num_leaves`: "default = ``31``" e "``1 < num_leaves <= 131072``" (l. 227);
  - `learning_rate`: "default = ``0.1``" e "``learning_rate > 0.0``" (l. 221);
  - `min_data_in_leaf`: "default = ``20``" e "``min_data_in_leaf >= 0``" (l. 352); "Can be used to deal with over-fitting" (l. 354).
- Orientação (`Parameters-Tuning.rst`):
  - `num_leaves` "is the main parameter to control the complexity" (l. 22); "setting ``num_leaves`` to ``127`` may cause over-fitting, and setting it to ``70`` or ``80`` may get better accuracy" (l. 28);
  - o ótimo de `min_data_in_leaf` "depends on the number of training samples and ``num_leaves``", e "hundreds or thousands is enough for a large dataset" (l. 31, 33);
  - "Use small ``learning_rate`` with large ``num_iterations``" (l. 188);
  - contra over-fitting: "Use small ``num_leaves``" (l. 201) e "Use ``min_data_in_leaf``" (l. 203).
- Única faixa numérica achada, em implementação T2 (`optuna_integration/lightgbm/_lightgbm_tuner/optimize.py`):
  - `num_leaves`: `suggest_int("num_leaves", 2, max_num_leaves)` (l. 218), linear, com `max_num_leaves = 2**8` só quando `max_depth` não está definido (l. 216–217);
  - `min_child_samples` (alias de `min_data_in_leaf`): grade `[5, 10, 25, 50, 100]` (l. 581–582);
  - `learning_rate` não é ajustado.
**Decisão** (degrau 4: conservadora, ancorada nos defaults e nas restrições da doc oficial; nenhuma faixa atribuída à doc):
- `num_leaves` `int` log [8, 64]: contém o default 31, fica abaixo do exemplo de over-fitting (127) e respeita a orientação de folhas poucas para dado pequeno (~1640 linhas úteis no fold 0);
- `learning_rate` `float` log [0.03, 0.3]: simétrica em log em torno do default 0.1. O piso fica em 0.03, não 0.01, porque o teto `num_boost_round_max = 500` mais uma taxa pequena levaria trials ao teto (a regra "small learning_rate with large num_iterations" pede as duas coisas juntas);
- `min_data_in_leaf` `int` log [5, 100]: contém o default 20 e coincide com os extremos da grade do tuner do Optuna; a orientação de "centenas ou milhares" vale só para dataset grande.
**Vigiar na Task 34:** quantos trials do GBM param no teto de 500 rounds (`best_iteration`); se forem muitos, é sinal de que o piso de `learning_rate` ainda restringe.
**Rascunho e verificação da Task 32:** `config/cohorts/aapl_confirmatory.toml`, revisão 0:
- `feature_set_name = "fs_all"` (o registry inteiro, mesmo nome que os testes usam com esse sentido);
- `feature_set_hash = 7df0e1b4…09e0` e `pipeline_version = "2"`, lidos do código;
- `sampler_seed = 2026`; GBM com `seed = 0`; `n_trials` ausente e `seeds = []` (decisões [P]).

`python -m financial_forecasting.cli run --data-root data/cohorts/aapl --cohort config/cohorts/aapl_confirmatory.toml` → `error: CohortNotFrozenError: cohort 'aapl_confirmatory' r0 is not frozen — run sweep and freeze first (seeds, n_trials, params, provenance and dataset fingerprint)`, exit 2.

### 2026-09-27 — Checkpoint C (bloco 24–31) — disposições — Claude (Opus 5.5)
Dois revisores de contexto zerado sobre `371d4f5..HEAD`: um com a lente de comportamento/contrato (F1–F9), outro com a de arquitetura e testes (G1–G11). Não houve blocker; os médios foram F1, F2, G1, G2 e G3.
- **F1/G2** (médio) — identidade do código dependente do diretório corrente → **corrigido**:
  - o probe resolve `repo_root` e recusa quando ele não é `git rev-parse --show-toplevel`; num subdiretório os pathspecs do `git status` não casariam `src` e `code_dirty` sairia sempre "false";
  - a fábrica do composition root passa ao probe o caminho do cohort resolvido contra o diretório corrente, o mesmo arquivo que o CLI leu;
  - testes: probe num subdiretório e caminho relativo resolvido.

  O `artifacts_root` relativo continua dependendo do diretório corrente: **aceito**, com o runbook fixando a invocação (`docker run -w /app`). Um ledger em outro lugar não reaproveita nada em silêncio: as unidades são reconferidas pelo silver (`verified_completed`) e o ambiente é gravado de novo.
- **F2** (médio) — `verify` não conferia o ledger (o A8 pede "ledger com todas as unidades") → **corrigido**: toda unidade tem de estar marcada, com as mesmas contagens do silver, mais dois testes.
- **G1** (médio) — comandos das unidades montados com `**dict` e `type: ignore`, de modo que uma troca `val_size`/`calib_size` passaria em tudo → **corrigido**: campos nomeados um a um e checados pelo mypy, um teste que confere a geometria de cada unidade (spec de teste com val 8 ≠ calib 6) e o e2e com `calib_size = 16 ≠ val_size = 20`.
- **G3** (médio) — duas definições de "unidade completa" (classificação da corrida × `verify`) → **corrigido**: fonte única `recorded_run_problems(spec, model_keys, recorded)` no módulo do use case, usada na classificação (I7-c), depois de executar a unidade (F6) e no `verify`. Ela confere: um run por fold; fold legível; contagem; horizontes; alvos iguais entre modelos no mesmo fold. Runs órfãos (0 linhas) são ignorados.

  A parte "o `freeze` repete I4" foi **refutada**: o `freeze` chama as mesmas funções (`load_training_grid`, `grid_fingerprint`) e precisa conferir antes de gravar o arquivo, porque o `run` só confere depois (artefato: `cohort_commands.py`, bloco `freeze`, e `run_confirmatory_cohort.py::_check_declarations`, que usam as duas funções).
- **F3** (baixo/médio) — `freeze` podia gravar um arquivo que o `parse` recusa (dimensão `kind="float"` em campo int) e publicar um hash que não é o do arquivo → **corrigido**:
  - `validate_dimension_names` confere o `kind` contra o tipo do campo;
  - o `freeze` refaz a ida e volta e só grava se ela fechar, com o hash calculado sobre o spec relido;
  - o temporário é removido em falha;
  - testes nos dois pontos.
- **F4** (baixo) — U+007F cru é TOML inválido → **corrigido**: `ensure_ascii=True` no `dump` + teste de ida e volta.
- **F5/G7** (baixo) — exit 1 ambíguo (MISMATCH do `verify` × exceção não capturada) e nenhum log por unidade → **corrigido**:
  - `RuntimeError`, `OSError` e `TypeError` saem com 2, e a divergência do `verify` sai com `EXIT_MISMATCH = 1`;
  - cada unidade loga início, desfecho, runs, linhas e tempo (`logging`, configurado no `cli.main`);
  - teste do código de saída.
- **F6** (baixo) — unidade marcada sem conferir o que o use case gravou → **corrigido**: `UnitOutputMismatchError` quando o silver não confirma a unidade, que não é marcada + teste.
- **F7** (baixo) — família de baseline repetida quebraria a contagem por modelo → **corrigido**: `CohortSpec` recusa + teste.
- **F8/G10** (baixo) — fold nulo (`""` no índice) virava `ValueError` cru → **corrigido**: vira problema ("unreadable fold") → `PartialCohortUnitError` / MISMATCH + teste.
- **F9** (baixo) — e2e sem asserção dos status depois do `--break-stale-lock` e sem o caminho `verified_completed` com o índice real → **corrigido**: as duas asserções entraram no fluxo do e2e.
- **G4** (baixo) — `model_version` das baselines montado à mão → **corrigido**: `BaselineSpec.model_version`, e o harness também o usa. O teste `test_cohort_model_keys_lists_every_unit_in_run_order` fixa o literal `baseline_<família>`.
- **G5** (baixo):
  - `modeling_columns()` injetado em dois pontos → **corrigido**: campo único `ApplicationDependencies.modeling_columns`, usado pelo `run` e pelo `freeze` + teste;
  - `cli.py` fora dos contratos do import-linter → **aceito como limitação**. Um contrato `forbidden` exigiria `allow_indirect_imports` (o `cli.py` importa o composition root, que por desenho importa `adapters/out`) mais um caso de violação real no teste de contratos. O arquivo tem um só import de produção fora da aplicação (`Settings`) e a revisão G1 confirmou que ele não instancia concreto.
- **G6** (baixo) — `cohort_commands` carregado por `importlib` fica `Any` para o mypy → **aceito como limitação** da keyword `in` (LAYOUT §8). Coberto em runtime pelos testes de despacho do `test_cli.py` e pelo e2e, que passam pelos quatro comandos.
- **G8** (baixo) — o teste "missing fold" não tirava fold nenhum → **corrigido**: renomeado para o que testa (modelo não declarado), mais um teste de fold ausente num modelo declarado.
- **G9** (baixo) — faltava teste do I9 ligando o leitor do cohort ao dos use cases → **corrigido**: `test_the_cohort_reader_starts_on_the_same_row_as_the_use_cases` (grid do cohort, GBM e baselines começam na mesma sessão com aquecimento).
- **G11** (baixo) — a invariante "libera só o próprio lock" existia só no adapter → **corrigido no port** (docstring de `release_writer`). O fake, de processo único, não tem outro dono possível; o `[real]` do contrato já prova a invariante com duas instâncias.

### 2026-09-27 — [finding] Task 33 — materialização real: notícia depois do fechamento do último dia derrubava o `BuildDataset` — Claude (Opus 5.5)
**O que houve:** a primeira `materialize` real rodou 914 s (quase todos no FinBERT sobre as notícias) e caiu com `ValueError: No trading session after 2025-12-31 within the materialized window`. O `ScoreAndAggregateSentiment` montava o calendário só na janela dos candles. Um artigo publicado depois do fechamento no último dia resolve para a sessão seguinte, que não estava no calendário. O dado sintético do e2e não tinha esse caso, porque todos os artigos saem antes do fechamento.
**Correção:** o calendário ganha folga de 14 dias no fim, e os artigos cujo dia de pregão cai depois da janela saem, porque não têm linha no grid. Dentro da janela o comportamento não muda. Há teste de regressão com o caso real (artigo às 20:00 UTC do último dia, `close_hour` 16:00). É um bug da Stage 3.2, corrigido aqui porque bloqueia a execução real da 5.5.

### 2026-09-27 — [finding] Task 33 — `materialize` não é re-executável sobre um bronze existente — Claude (Opus 5.5)
**O que houve:** a segunda tentativa encontrou o bronze deixado pela primeira e caiu em 14 s com `DuplicateKeyError: Duplicate logical PK collision in (bronze, candle) … path=data/cohorts/aapl/bronze/candle/asset=AAPL/year=2010/candle.parquet`. A ingestão grava por acréscimo e recusa chave repetida.
**Disposição:** a recusa é o comportamento certo, porque não sobrescreve nada em silêncio, e o erro nomeia o arquivo. Antes de repetir a `materialize`, o runbook manda apagar as camadas derivadas (`bronze/` e `processed/dataset_tft/`), preservando `raw/` e `processed/fundamentals/`, que são entrada. Aqui foi apagado só o `bronze/` produzido pela tentativa que falhou.

### 2026-09-27 — Checkpoint C (bloco 24–31) — rodada 2 (reverificação das correções) — Claude (Opus 5.5)
Revisor de contexto zerado sobre `a62209b` e `74e0cc4`, que confirmou 17 dos 20 itens. Os pontos restantes foram corrigidos (`task-31-fix2`):
- **F4 tinha regressão:** `ensure_ascii=True` escapa caractere fora do BMP como par substituto (`😀`), que o `tomllib` recusa. Um cohort com emoji no nome deixaria de congelar.
  - **Correção:** `_basic_string` escapa só aspas, barra, controles e DEL, e o resto vai cru em UTF-8.
  - **Teste:** ida e volta com DEL, controle e U+1F600.
- **F5 incompleto:** exceções fora da tupla (`KeyError`, `AssertionError`) saíam com 1, que é o `EXIT_MISMATCH`.
  - **Correção:** um `except Exception` final imprime o traceback e sai com 2.
  - **Teste:** um `KeyError` sai com 2.
- **Teste vácuo:** o teste da fábrica do probe tinha cwd igual a `repo_root`.
  - **Correção:** o teste agora roda com cwd em `sub/` e espera `sub/config/…`.
- **Duas alegações de cobertura acima não se sustentavam:**
  - O e2e com `calib_size ≠ val_size` **não** detecta a troca, porque a contagem de linhas depende só de `n_folds`, `test_size` e horizontes. A guarda da troca é o teste unitário `test_every_unit_command_carries_the_spec_geometry_and_grid`; a mudança no e2e só faz o caminho real correr com valores distintos.
  - A limpeza do temporário do `freeze` não era exercitada. Agora é: `test_freeze_removes_its_temporary_file_when_the_replace_fails`.
- **Log por unidade (G7):** passou a ter teste (`test_each_unit_logs_its_start_and_outcome`).
  - Na suíte inteira o teste falhou uma vez: algum teste anterior reconfigura o logging e desliga os loggers já criados. O teste agora religa o logger do módulo.
  - Conferido no container: no processo do CLI o logger segue ligado depois do import, do `wire_dependencies` e de o MLflow criar o banco SQLite (`after mlflow sqlite init disabled: False`). O rastro por unidade existe na corrida real.

Resíduos declarados:
- O ledger grava as contagens devolvidas pelo use case, e não as relidas do silver. A divergência entre as duas é pega pelo `verify` e pelo I6 na retomada, então não há buraco de completude.
- No G5, o `cli.py` importa o composition root e as exceções base de `shared`, além de `Settings`. A justificativa do "aceito" vale mesmo assim: o `cli.py` não instancia nenhum concreto.

### 2026-09-27 — [decision:E] Task 33 — R9: o gate de qualidade recusou o começo da série real; dataset começa em 2010-04-20 — Claude (Opus 5.5)
**Contexto:** a `materialize` real (depois do achado do sentimento) caiu no check (d) do `DatasetQualityGate`, após 871 s: `Effective warmup exceeds declared warmup_count … revenue: first finite at row 72 > warmup_count 0; … revenue_yoy_growth: first finite at row 324 > warmup_count 252; net_income_yoy_growth: first finite at row 324 > warmup_count 252`. É o risco R9 do concept ("decisão com a medição antes de seguir").

**Medição** (skill `data-shape-evidence`, consulta `scratchpad/t33/measure_start.py` sobre o bronze real):
- O bronze tem 81 fundamentos, 17 `reported_date` NaT e 1 linha sem valores. É a mesma contagem medida em 2026-09-26, sobre o raw reusado.
- Primeiro relatório: trimestral, `fiscal_date_end` 2010-03-31, `reported_date` **2010-04-20**.
- Candles vão de 2010-01-04 a 2025-12-31 (4024). A linha 0 do dataset é 2010-01-05, porque o alvo precisa de t−1.
- A linha 72 do dataset é 2010-04-20, o que bate com a linha que o gate acusa. A linha 324 é 2011-04-18.

**Opções simuladas sobre as linhas reais:**
- **(A) Dataset a partir de 2010-04-20** (o primeiro fundamento efetivo):
  - os fundamentos ficam finitos desde a linha 0, e o YoY na linha 252 (= warmup declarado), então o check (d) passa;
  - o grid útil começa na mesma sessão que começaria sem o corte (2011-04-18), porque o YoY é quem limita;
  - diferença residual: indicadores de memória exponencial (EMA, Wilder) partem de um histórico 72 sessões mais curto.
- **(B) Dataset a partir do primeiro YoY finito:** os indicadores reaqueceriam a partir dali, e o grid útil perderia cerca de 200 sessões.
- **(C) Afrouxar o gate ou mudar o `warmup_count` declarado:** muda o `feature_set_hash` e desarma a guarda do #83. Descartada.

**Decisão:** (A), pela nova opção `materialize --start AAAA-MM-DD`. Ela corta só o `BuildDatasetRequest`; bronze e sentimento veem os brutos inteiros. O valor 2010-04-20 é um fato do dado (o `reported_date` do primeiro relatório), não uma escolha por desempenho, e fica ancorado pela impressão digital do dataset no cohort e registrado no runbook.

**Verificação:** `materialize --data-root data/cohorts/aapl --cohort config/cohorts/aapl_confirmatory.toml --start 2010-04-20` →
- `materialized AAPL: 4024 candles, 6921 news, 81 fundamentals` / `dataset rows 3950 (2010-04-21..2025-12-31), feature_set_hash 7df0e1b4…09e0`;
- exit 0 em 755 s.

### 2026-09-27 — [measurement] Task 33 — dado real materializado (A5/D6) — Claude (Opus 5.5)
Consulta: `scratchpad/t33/measure.py`, rodada no container com DuckDB sobre o Parquet e pelos use cases. Saída integral em `scratchpad/t33/measure.out`.
- **Dataset:** 3950 linhas, 2010-04-21 → 2025-12-31, 3950 timestamps distintos, 58 colunas de modelagem.
- **Linhas reais:**
  - começo (2010-04-21…27): `rsi_14` nulo, `revenue` = 13.499e9;
  - corte (2011-04-14…20): todas as colunas finitas desde 2011-04-18; a `revenue` troca de 26.741e9 para 24.667e9 em 2011-04-20, com o relatório de 2011-04-20;
  - fim (2025-12-24…31): nada nulo.
- **Prefixo cortado:** 251 linhas, com 29 colunas com NaN nele. As piores: `revenue_yoy_growth` 251, `net_income_yoy_growth` 251, `ema_200` 198, `trend_regime` 111, `ema_100` 98.
- **NaN interior:** 0 colunas.
- **Grid útil:** 3699 sessões, 2011-04-18 → 2025-12-31.
- **Limiar D6:**
  - treino do fold 0 = 1641 sessões → τ·n = 0,02 × 1641 = **32,8 ≥ 30** (0,1 × 1641 = 164,1). A geometria não precisa ser revista;
  - OOS por horizonte: 1511 (h=1) e 1505 (h=7) ≥ 30/0,02 = 1500.
- **Reconciliação do alvo:** `target_return == log(close_t/close_{t−1})` em 3949/3949 linhas (tolerância 1e−9). É o retorno para trás, como documentado. O deslocamento para `t+h` é do modelo (ADR 4.3.0001). Para `log(close_{t+1}/close_t)`: 0/3949.
- **Impressão digital do grid:** `00e4406dcd96658d557f7d4d86face9874fac42385e3cb182d54c5d2286695bd`.

### 2026-09-27 — Checkpoint C (bloco 24–31) — rodada 3 (última) — Claude (Opus 5.5)
Revisor de contexto zerado sobre `9b6386f` e `fa5adc8`: 5 dos 6 itens foram confirmados.
- **F4:** a ida e volta pelo `tomllib` foi testada em todos os 1.112.064 pontos de código escalares. Surrogate isolado não vem de arquivo lido, porque a leitura é UTF-8 estrita; se entrasse, a gravação ergueria `UnicodeEncodeError`, sairia com exit 2 e deixaria o original intacto.
- **F5:** `SystemExit` do argparse e `KeyboardInterrupt` continuam passando.
- **Fábrica do probe e temporário do `freeze`:** as mutações são mortas pelos testes.
- **Logger:** nada em `src/` desliga loggers.

Item aberto e **corrigido** (`task-33`, teste): o teste de `--start` trocava o `_materialize` inteiro e passaria mesmo com o valor indo para a ingestão. Agora roda o `_materialize` real com use cases falsos e confere os três pedidos (candles e news na janela ampla, fundamentos sem janela, dataset com o `--start`), mais a liberação do lock. O código já estava certo. Esta foi a última rodada: nenhum achado material ficou aberto.

### 2026-09-27 — [measurement] Task 33 — custo no CPU (insumo das decisões [P]) — Claude (Opus 5.5)
Container com 12 threads, CPU, torch 2.13.0+cpu.
- **`sweep --n-trials 1`** (comando do plano, dado real, geometria exploratória): 115 s no total, exit 0.
  - O trial do TFT sorteou `hidden_size` 21, batch 81, lr 9,0e−3 e dropout 0,43, e levou cerca de 75 s: do `Seed set to 0` às 23:59:39 até a abertura do banco do MLflow às 00:00:54.
  - O trial do GBM levou ≤ 20 s (`num_leaves` 12, lr 0,078, `min_data_in_leaf` 93).
  - Resultados gravados sob o scope `aapl_confirmatory-r0-sweep-f1d501d62829`, com `n_trials = 1`. Esse scope é separado do sweep real.
- **Cantos do espaço D9 do TFT** (`scratchpad/t33/cost_corner.py`, `RunTftSweep` real, sem persistência):
  - canto barato (hidden 10, batch 255, lr 1e−2): **140 s**;
  - canto caro (hidden 319, batch 64, lr 1e−4): **806 s**.
- **Custo estimado da corrida:**
  - o treino cresce de 1641 (fold 0) a 2901 sessões (fold 5), então os 6 folds somam cerca de 8,3 vezes o custo de um ajuste no fold 0;
  - por seed do TFT, o custo fica entre ~10 min (params como o trial de 75 s) e ~1,9 h (canto caro);
  - GBM (6 ajustes) e baselines somam minutos.
- **Conclusão:** o custo cabe em CPU mesmo no pior caso (10 seeds no canto caro ≈ 19 h de corrida). ROCm **não** é necessário (D8).

### 2026-09-27 — [P] Task 33 — decisões do humano no congelamento — Claude (Opus 5.5)
Perguntas feitas com o custo medido acima (entrada anterior); respostas do humano:
- **`n_trials = 60`**, o mesmo para o sweep do TFT e o do GBM (D13). Iguala o orçamento de 60 iterações do paper do TFT (Lim et al. 2021, §6.2). O sweep estimado leva de ~1,6 h a ~14 h.
- **Seeds do TFT = 1..10** (10 seeds), distintas da seed 0 do sweep. Custo estimado da corrida: de ~1,7 h a ~19 h, conforme os HPs congelados.
- **Device: CPU.** ROCm não foi necessário: o custo coube.

<!-- END: post-execution -->
