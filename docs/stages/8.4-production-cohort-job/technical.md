---
title: Technical — Stage 8.4 — Job de cohort de produção
description: Plano de execução da Stage 8.4 em 8 Tasks inside-out (1 Task = 1 commit) — CohortSpec.production_round, parâmetro inherited_hyperparameters no runner do cohort, modelo de produção versionado, fábrica production_cohort_for, comandos de produção (spec da rodada e ponteiro atômico), subcomando production-round, e2e com a API servindo a rodada e o runbook — e a Etapa real R (duas rodadas reais sobre os brutos do AAPL e a troca do cohort servido)
when-use: Consultar durante a Fase 4 (execução) da Stage 8.4; cada Task tem arquivos (lista fechada), testes a escrever primeiro, critérios do concept que cobre e verificação; a Etapa R traz o roteiro da execução real
keywords: [technical, plano de execução, production-cohort-job, production-round, serving-pointer, cohort-spec, inherited-hyperparameters, idempotency, e2e, runbook]
status: done
created_at: 2026-10-25
updated_at: 2026-10-25
stage_id: 8.4-production-cohort-job
stage_title: Job de cohort de produção
step_id: 8
step_title: Reprodução, equivalência e relatório
depends_on: [7.4-inference-api, 8.1-confirmatory-run, 8.3-plots-and-final-report]
concept_ref: ./concept.md
issue_id: 202
branch: feat/202-8-4-production-cohort-job
tasks_count: 8
---

# Technical — Stage 8.4 — Job de cohort de produção

> **Como usar este documento (para code assistant):**
> 1. Ler §1 inteiro antes da Task 01.
> 2. Executar as Tasks na ordem de §2. **1 Task = 1 commit.** A lista de arquivos
>    de cada Task é **fechada**: tocar arquivo fora dela = parar e triar.
> 3. Escrever primeiro os testes (vermelho), depois o código (verde). Por Task roda
>    só o pytest dos testes dela; `make check` só nos pontos do
>    [plano de gates](#plano-de-gates).
> 4. Mensagem de commit: `<type>(<scope>): <description> [8.4/task-NN]`, body em
>    bullets, `Refs #202` (CONVENTIONS §4).
> 5. O que não estiver previsto aqui ou no concept vai para §7.

## 1. Contexto e estratégia de execução

### Resumo

Um subcomando `production-round` no `cli.py` encadeia, para uma rodada datada e
sob o lock da raiz de produção: cópia dos brutos para `<production-root>/rounds/<round>/`, `materialize` (marca
`.materialized`), derivação do spec congelado da rodada a partir de
`config/cohorts/aapl_production.toml` (`CohortSpec.production_round`), corrida
pelo `RunConfirmatoryCohort` da fábrica `production_cohort_for`
(`inherited_hyperparameters=True`), `verify` e a troca atômica e monotônica de
`<production-root>/serving.env`. A API não muda: o e2e sobe `create_app` com os
valores do ponteiro.

### Estratégia

Inside-out (skill `task-ordering-hex`): o método do DTO e o parâmetro do runner
primeiro (application, testes com fakes), depois o arquivo versionado, a
composition root, os comandos do adapter `in/cli`, o subcomando do processo e
o e2e. O runbook fecha a parte de código. A Etapa R roda com a árvore limpa
depois do gate.

### Pré-condições

- 7.4, 8.1 e 8.3 `done` e mergeadas em `develop`; o bloco da 8.4 no roadmap
  (PR #239) mergeado.
- Imagem `financial_forecasting-app:dev` e volume `financial-forecasting_app-venv`.
- Para a Etapa R: um venv com o extra `sentiment` (FinBERT), copiado do volume
  de dev e sincronizado pelo `uv.lock` da branch (runbook do cohort, Step 2).

### Premissas técnicas

- Comandos no container (memórias do projeto): `docker run` avulso da imagem de
  dev com a worktree em `/app`, o `.git` principal `:ro` em `/main.git`,
  `GIT_DIR=/main.git/worktrees/feat-202-8-4-production-cohort-job`,
  `GIT_WORK_TREE=/app`, `GIT_OPTIONAL_LOCKS=0`, `--cpus 6 --memory 8g
  --memory-swap 8g` e `make check PYTEST_PAR='-n 4 --dist loadgroup'`.
- `T1` de cada Task: `uv run --no-sync pytest <arquivos> -q --no-cov`.

### Plano de gates

| # | Depois da Task | Por quê |
|---|---|---|
| 1 | Task 08 (saída do código) | gate de saída do código; a Etapa R exige a árvore limpa e o código final, e o `make check` cobre os contratos de arquitetura (`lint-imports`, `arch-ast`, `port-coverage`) que os testes por Task não rodam |

A Etapa R e o commit `stage 8.4: complete` só mudam docs (§7 do technical,
roadmap). O `docs-check` roda de novo antes do commit final.

### Estrutura de pastas afetada

```
config/cohorts/
└── aapl_production.toml                                  # novo
src/financial_forecasting/
├── cli.py                                                # + production-round
├── composition_root.py                                   # + production_cohort_for
└── features/modeling/
    ├── application/dtos/cohort_spec.py                   # + production_round
    ├── application/use_cases/cohort_unit_runner.py       # + inherited_hyperparameters
    ├── application/use_cases/run_confirmatory_cohort.py  # + inherited_hyperparameters
    └── adapters/in/cli/production_commands.py            # novo
tests/
├── unit/features/modeling/application/test_cohort_spec_production_round.py
├── unit/features/modeling/application/test_inherited_hyperparameters.py
├── unit/features/modeling/adapters/in_/test_production_commands.py
├── unit/test_cli_production_round.py
├── unit/test_composition_root_production.py
├── integration/features/modeling/test_production_cohort_config.py
└── e2e/test_production_round_cli.py
docs/runbooks/production-cohort-job.md                    # novo
```

## 2. Tasks

### Task 01 — `CohortSpec.production_round`

- **Arquivos a criar:**
  - `tests/unit/features/modeling/application/test_cohort_spec_production_round.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/modeling/application/dtos/cohort_spec.py`
- **O que fazer:** método `production_round(self, dataset_fingerprint: str) ->
  CohortSpec` que devolve `replace(self, dataset_fingerprint=...)`. Recusa com
  `ValueError` se `self.dataset_fingerprint` já existe, se falta qualquer campo
  de congelamento (`tft_params`, `gbm_params`, `provenance`, `seeds` vazio,
  `sweep.n_trials`) ou se a impressão digital não é um sha256 hex
  (`validate_sha256_hex`, LAYOUT §7). O resultado tem `is_frozen()` verdadeiro.
- **Testes primeiro:** modelo completo → spec congelado com a impressão digital
  e todos os outros campos iguais; `cohort_id` muda com a impressão digital;
  cada campo faltante → `ValueError` nomeando o campo; modelo já com impressão
  digital → `ValueError`; impressão digital malformada → `ValueError`.
- **Critério de aceite:** CA5 (parte do `production_round`).
- **Verificação:** `uv run --no-sync pytest tests/unit/features/modeling/application/test_cohort_spec_production_round.py -q --no-cov`
- **Commit:** `feat(modeling): spec congelado da rodada de produção a partir do modelo [8.4/task-01]`

---

### Task 02 — Parâmetro `inherited_hyperparameters` no runner

- **Arquivos a criar:**
  - `tests/unit/features/modeling/application/test_inherited_hyperparameters.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/modeling/application/use_cases/cohort_unit_runner.py`
  - `src/financial_forecasting/features/modeling/application/use_cases/run_confirmatory_cohort.py`
- **O que fazer:** `check_cohort_declarations(..., inherited_hyperparameters:
  bool = False)`: com `True`, pula só a igualdade
  `provenance.dataset_fingerprint == spec.dataset_fingerprint` (a ausência de
  `provenance` continua erro). `RunConfirmatoryCohort.__init__(...,
  inherited_hyperparameters: bool = False)` repassa ao `_check_declarations`.
  Docstrings citam o ADR 8.4.0001 item 6.
- **Testes primeiro** (fakes do `test_run_confirmatory_cohort.py`/`_frozen_tft_cohort.py`):
  default → sweeps de outro dado recusados (`CohortDeclarationMismatchError`);
  `True` → a corrida roda as unidades; com `True`, impressão digital observada
  ≠ declarada → `DatasetMismatchError`, `feature_set_hash` diferente, device e
  `pipeline_version` → `CohortDeclarationMismatchError`; `provenance` ausente
  com `True` → recusa.
- **Critério de aceite:** CA5 (garantias do runner), I5.
- **Verificação:** `uv run --no-sync pytest tests/unit/features/modeling/application/test_inherited_hyperparameters.py tests/unit/features/modeling/application/test_run_confirmatory_cohort.py tests/unit/features/modeling/application/test_cohort_unit_runner.py -q --no-cov`
- **Commit:** `feat(modeling): runner aceita hiperparâmetros herdados quando declarado [8.4/task-02]`

---

### Task 03 — Modelo de produção versionado

- **Arquivos a criar:**
  - `config/cohorts/aapl_production.toml`
  - `tests/integration/features/modeling/test_production_cohort_config.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** o arquivo é o `aapl_confirmatory.toml` com `name =
  "aapl_production"`, `geometry.n_folds = 1`, as seeds do D7, `dataset_start =
  2010-04-20` e sem `dataset_fingerprint` no topo (a `[provenance]` fica, com a
  impressão digital dos sweeps do r0). Gerado por `cohort_file.dump` para ficar
  no formato canônico.
- **Testes primeiro:** carregar os dois arquivos pelo `cohort_file.load`; o de
  produção não está congelado; `replace` do confirmatório com os campos
  declarados (nome, `n_folds`, seeds, `dataset_start`, `dataset_fingerprint =
  None`) é igual ao de produção; `production_round(<hex>)` do de produção está
  congelado; o `run` confirmatório (use case com fakes) recusa o modelo com
  `CohortNotFrozenError`.
- **Critério de aceite:** CA5 (modelo igual ao r0 fora dos campos declarados;
  `run` recusa).
- **Verificação:** `uv run --no-sync pytest tests/integration/features/modeling/test_production_cohort_config.py -q --no-cov`
- **Commit:** `feat(modeling): modelo do cohort de produção herdado do confirmatório r0 [8.4/task-03]`

---

### Task 04 — Fábricas `production_cohort_for` e `writer_lock_for` na composition root

- **Arquivos a criar:**
  - `tests/unit/test_composition_root_production.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/composition_root.py`
- **O que fazer:** campos `production_cohort_for: Callable[[Path, str],
  RunConfirmatoryCohort]` e `writer_lock_for: Callable[[Path],
  CohortProgressLedger]` em `ApplicationDependencies`. A primeira monta o mesmo
  runner do `confirmatory_cohort_for` com `inherited_hyperparameters=True` e o
  probe `runtime_probe_for(template_path, device)`; a segunda devolve um
  `JsonCohortProgressLedger(artifacts_root=<raiz>/artifacts, data_root=<raiz>)`
  usado só pelo lock (`<raiz>/.writer.lock`). Docstring do módulo ganha o
  parágrafo da Stage 8.4.
- **Testes primeiro:** `wire_dependencies` em `tmp_path` com probe injetado: o
  runner de `confirmatory_cohort_for` sai com a herança desligada e o de
  `production_cohort_for` com ela ligada; o probe da fábrica de produção recebe
  o caminho do modelo; `writer_lock_for(raiz)` trava `<raiz>/.writer.lock` e
  uma segunda aquisição é recusada.
- **Critério de aceite:** CA5 (só a fábrica de produção passa `True`), I5.
- **Verificação:** `uv run --no-sync pytest tests/unit/test_composition_root_production.py tests/unit/test_cli.py -q --no-cov`
- **Commit:** `feat(composition): fábricas do runner e do lock da rodada de produção [8.4/task-04]`

---

### Task 05 — Comandos de produção: spec da rodada e ponteiro atômico

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/adapters/in/cli/production_commands.py`
  - `tests/unit/features/modeling/adapters/in_/test_production_commands.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  - `ProductionRoundError(ApplicationError)`.
  - `prepare_round_spec(deps, template_path, round_spec_path, *, out) -> CohortSpec`:
    carrega o modelo, lê o grid (`load_training_grid`) e a impressão digital
    (`grid_fingerprint`), deriva `production_round`, confere a geometria
    (`fits`), faz a ida e volta `parse(dump(spec)) == spec` e grava por
    escrita atômica; arquivo existente igual → mantém; diferente →
    `ProductionRoundError`, arquivo intacto. Recebe `ProductionCommandDeps`
    (dataclass próprio: `store`, `hasher`, `modeling_columns`, `load_spec`,
    `parse_spec`, `dump_spec`, montado pelo `cli.py`): o `CohortCommandDeps` vive
    num módulo irmão sob `adapters/in/` e não é importável (LAYOUT §8).
  - `parse_round_name(text) -> tuple[date, int]`: aceita só `AAAA-MM-DD` e
    `AAAA-MM-DD.N` (N ≥ 1, sem zero à esquerda); o resto → `ValueError`.
  - `publish_serving_pointer(production_root, round_name, round_root,
    round_spec_path, *, out) -> bool`: lê o ponteiro atual (se houver) e só
    publica se não há ponteiro, se ele já aponta para esta rodada ou se esta
    rodada ordena depois da apontada (`parse_round_name` do diretório
    apontado); senão escreve `not published: …` e devolve `False`. Publicar =
    `tempfile.mkstemp(dir=production_root)` com `DATA_ROOT=<abs>` e
    `SERVING_COHORT_FILE=<abs>` e `os.replace`; temporário removido em
    `finally`.
  - O módulo não importa `features.evaluation` (I8).
- **Testes primeiro:** derivação grava spec congelado com a impressão digital do
  grid fake; repetida → mesmo arquivo; arquivo adulterado →
  `ProductionRoundError` e bytes iguais; modelo congelado → `ValueError`;
  nomes de rodada válidos e inválidos (`..`, `.`, `2026-13-01`, `x`,
  `2026-10-25.0`, `2026-10-25.01`); ponteiro com exatamente duas linhas
  absolutas; rodada mais antiga → `False` e ponteiro intacto; mesma rodada →
  regrava igual; mais nova → troca; falha simulada no `os.replace`
  (monkeypatch) → ponteiro anterior byte a byte igual e sem temporário; AST:
  nenhum import de `features.evaluation`.
- **Critério de aceite:** CA3 (spec adulterado, rodada antiga), CA4 (ponteiro),
  CA7 (nomes), CA8 (AST), I3, I4, I8, I9.
- **Verificação:** `uv run --no-sync pytest tests/unit/features/modeling/adapters/in_/test_production_commands.py -q --no-cov`
- **Commit:** `feat(modeling): comandos da rodada de produção (spec e ponteiro) [8.4/task-05]`

---

### Task 06 — Subcomando `production-round`

- **Arquivos a criar:**
  - `tests/unit/test_cli_production_round.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/cli.py`
- **O que fazer:** subparser próprio (fora do helper `add()`): `--production-root`,
  `--round`, `--raw-root`, `--cohort`, `--break-stale-lock`. Despacho antes do
  `wire_dependencies` geral, como o `audit-reproduction`:
  1. Validações sem escrita: `parse_round_name(round)`; raiz de produção igual,
     dentro ou contendo `<repo_root>/data/cohorts` (`resolve()` + `casefold`) →
     `ProductionRoundError`; os três brutos em `--raw-root`
     (`ProductionRoundError` nomeando o ausente).
  2. `Settings(**overrides, data_root=<rodada>, artifacts_root=<rodada>/artifacts,
     mlflow_tracking_uri=sqlite:///<rodada>/mlruns.db)` (os três sobrepõem os
     overrides) e `wire_dependencies`; `deps.writer_lock_for(production_root)
     .acquire_writer(break_stale=...)`, liberado em `finally`.
  3. Sem `.materialized`: apaga `raw/`, `processed/` e `bronze/` da rodada,
     copia os brutos (`shutil.copy2`), `_materialize(...)` com o
     `dataset_start` do modelo e o `break_stale` do argumento, grava a marca.
     Com a marca: se algum bruto do `--raw-root` difere da cópia
     (`filecmp.cmp(shallow=False)`), uma linha `warning: …` e segue.
  4. `production_commands.prepare_round_spec`.
  5. `deps.production_cohort_for(cohort, device)` com o spec da rodada; linhas
     por unidade como o `run`.
  6. `cohort_commands.verify` sobre o spec da rodada; ≠ 0 → devolve o código
     sem publicar.
  7. `production_commands.publish_serving_pointer`; última linha
     `published <cohort_id> → <serving.env>` ou `not published: …`.
  Docstring do módulo ganha a Stage 8.4.
- **Testes primeiro** (deps e comandos fake por monkeypatch, como o
  `tests/unit/test_cli.py`): ordem das etapas; `Settings` com os três campos da
  rodada mesmo com overrides; `--round` inválido, bruto ausente e raiz dentro
  de `data/cohorts` (também com outra caixa e contendo-a) → exit 2 sem criar a
  raiz de produção; lock da raiz ocupado → exit 2 sem apagar nada da rodada; com
  a marca, não copia nem materializa, e avisa se o bruto difere; sem a marca e
  com bronze velho, apaga e refaz; `verify` com 1 → exit 1 e ponteiro intocado;
  lock liberado em erro.
- **Critério de aceite:** CA3 (materialização refeita/pulada), CA4 (verify
  divergente), CA7, I1, I2, I6, I7, I9.
- **Verificação:** `uv run --no-sync pytest tests/unit/test_cli_production_round.py tests/unit/test_cli.py -q --no-cov`
- **Commit:** `feat(cli): subcomando production-round da rodada de produção [8.4/task-06]`

---

### Task 07 — Ponta a ponta: rodadas pelo CLI e a API servindo

- **Arquivos a criar:**
  - `tests/e2e/test_production_round_cli.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** repositório git descartável (padrão do `test_cohort_cli.py`)
  com um modelo de produção sintético versionado (parâmetros mínimos, `seeds`
  duas, `n_folds = 1`) e um `data/cohorts/conf/` sintético com arquivos cujo
  hash é tirado antes e depois. `CliWiring` só com o sentimento fake e
  `repo_root` (sem override de `data_root`, `artifacts_root` nem
  `mlflow_tracking_uri`); diretório de trabalho em `tmp_path`
  (`monkeypatch.chdir`). Brutos sintéticos por `write_raw` em duas raízes: a
  curta e a longa (mais sessões). Roda:
  - rodada `2026-01-01` (brutos curtos) → exit 0, `verify` OK, ponteiro nela,
    `artifacts/` e `mlruns.db` dentro da rodada;
  - `create_app(Settings(_env_file=None, **valores do serving.env, repo_root=…))`
    + `TestClient`: data do teste de A → 200 com as duas seeds, o `cohort_id`
    de A e os blocos `unavailable` "gold não publicado"; data posterior → 404;
  - repetir A → exit 0, unidades `skipped_completed`, ponteiro igual;
  - rodada `2026-01-08` (brutos longos) → ponteiro em B; hash dos arquivos de A
    igual antes e depois de B; nova app: a data que dava 404 em A → 200;
  - repetir A depois de B → exit 0, `not published`, ponteiro em B;
  - arquivo rastreado de `src/` sujo → rodada nova sai com 2 e
    `EnvironmentMismatchError` (I5 pelo probe real sobre o modelo versionado);
  - `cohort.toml` de B adulterado → exit 2, arquivo intacto; hash de
    `data/cohorts/conf/` igual no fim; nada novo no repositório fora da raiz de
    produção (lista de arquivos antes e depois).
- **Critério de aceite:** CA1, CA2, CA3, I1, I2, I5, I9.
- **Verificação:** `uv run --no-sync pytest tests/e2e/test_production_round_cli.py -q --no-cov`
- **Commit:** `test(cli): ponta a ponta das rodadas de produção servidas pela API [8.4/task-07]`

---

### Task 08 — Runbook do job de produção

- **Arquivos a criar:**
  - `docs/runbooks/production-cohort-job.md`
- **Arquivos a modificar:** nenhum
- **O que fazer:** runbook (EN, formato dos runbooks do projeto): pré-requisitos
  (volume de venv com `sentiment`, cache do HF, checkout limpo, mesmo caminho
  de container no job e na API), o `docker run` exato de uma rodada, retomada e
  rodada nova (`.N`), lock órfão, a recriação da API (`docker rm -f` + `docker
  run -d --env-file …`), agendamento (script com a linha de cron e a tarefa do
  Agendador de Tarefas), rollback (ponteiro de volta à mão), limpeza de rodadas
  antigas, os limites D9/D10 com as issues #241 e #242 e a tabela de
  troubleshooting.
- **Critério de aceite:** CA8.
- **Verificação:** `python scripts/check_docs_pointers.py`
- **Commit:** `docs(runbooks): runbook do job de cohort de produção [8.4/task-08]`

**Gate 1 (`make check`) depois desta Task.**

---

### Etapa R — Execução real (sem commit de código)

Roteiro, com a árvore limpa no HEAD da Task 08 (ou do fix do gate):

- **R0 — venv e brutos.** Volume `ff84-venv-sentiment` copiado do volume de
  dev + `uv sync --locked --extra dev --extra sentiment`. Brutos lidos (cópia)
  de `<checkout principal>/data/cohorts/aapl/{raw,processed/fundamentals}`
  para duas raízes no scratchpad: `raw-cut` (candles e notícias até
  2025-06-30; fundamentos com `reported_date` ≤ 2025-06-30) e `raw-full`
  (cópia integral). `sha256sum` de todos os arquivos de
  `data/cohorts/aapl` antes.
- **R1 — rodada `2025-06-30`** com `--raw-root raw-cut`, raiz de produção
  `data/production/aapl` da worktree, pelo `docker run` do runbook; do checkout
  principal só o `.git` é montado (`:ro` em `/main.git`, exigido pelo probe),
  nunca o `data/`; tempo medido; data do fim do treino lida do `dim_run`.
- **R2 — API na rodada 1** pelo comando de recriação do runbook, pedido de uma
  decisão de setembro de 2025 → 404; tempo de subida.
- **R3 — rodada `2025-12-31`** com `raw-full`, montada como R1; tempo medido;
  data do fim do treino lida do `dim_run`; recriação da API com o ponteiro novo;
  o mesmo pedido → 200 com as seeds de produção e o `cohort_id` da rodada 2;
  tempo da recriação.
- **R4 — isolamento**: `sha256sum` de `data/cohorts/aapl` depois, igual ao de
  antes.
- Tudo colado em §7 como `[measurement]`, mais a aceitação escrita do risco do
  reinício (CA6).

| Se falhar | Fazer |
|---|---|
| `MissingSentimentExtraError` | venv errado: refazer R0 |
| `EnvironmentMismatchError: uncommitted` | árvore suja: `git status`, commitar ou limpar |
| `DatasetQualityError` na rodada cortada | conferir o corte dos fundamentos e o `dataset_start`; registrar `[deviation]` |
| `GeometryDoesNotFitError` | grid curto demais para a geometria: impossível com ~3.700 sessões; investigar o corte |
| rodada interrompida | rodar de novo com o mesmo `--round` (retoma) |

## 3. Gate de saída da Stage

### Verificações automatizadas

```bash
make check PYTEST_PAR='-n 4 --dist loadgroup'
python scripts/check_technical_postexec.py docs/stages/8.4-production-cohort-job/technical.md
git diff --stat origin/develop -- src/financial_forecasting/features/inference src/financial_forecasting/shared/infrastructure/http   # vazio (CA2)
git log -L ':serve_inference_for:src/financial_forecasting/composition_root.py' origin/develop..HEAD                                # vazio (CA2)
git log -L ':register_http_routes:src/financial_forecasting/composition_root.py' origin/develop..HEAD                               # vazio (CA2)
grep -rnE "^\s+inherited_hyperparameters=True," src/                                                                               # só production_cohort_for (CA5)
grep -L "^status: accepted" docs/adr/8_4_000*.md                                                                                   # vazio (CA8)
```

### Verificações funcionais

- [ ] Etapa R com as duas rodadas, a API servindo cada uma e o `data/cohorts/aapl` intacto (CA6).

### Checklist de fechamento da Stage

- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Commit final `stage 8.4: complete` aplicado
- [ ] `roadmap.md` atualizado: Stage `done`, Step 8 `done`, `updated_at` e `last_reviewed_at`
- [ ] ADRs 8.4.0001 e 8.4.0002 em `status: accepted`
- [ ] Runbook `production-cohort-job.md` criado
- [ ] `concept.md` sem retoque retrospectivo pendente

## 4. Ordem de dependência entre Tasks

```
Task 01 ─► Task 03 ─┐
Task 02 ─► Task 04 ─┼─► Task 05 ─► Task 06 ─► Task 07 ─► Task 08 ─► gate ─► Etapa R
                    ┘
```

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| e2e lento com duas rodadas reais de treino | parâmetros mínimos do TFT (1 época, encoder 10) como no `test_cohort_cli.py`; marca `e2e` |
| `create_app` no e2e carregar a pilha de deep learning | não é o caso: a composition root usa proxies lazy (provado na 7.4); se mudar, `[finding]` |
| Etapa R longa demais | rodar em background com `docker run -d` e acompanhar pelo log; a rodada retoma |
| Corte dos brutos quebrar o gate de qualidade | `[deviation]` com o corte ajustado |

## 6. Referências

- [`./concept.md`](./concept.md)
- [`../../roadmap.md`](../../roadmap.md) — Stage 8.4
- [`../../runbooks/confirmatory-cohort-aapl.md`](../../runbooks/confirmatory-cohort-aapl.md)
- ADRs: 8.4.0001, 8.4.0002, 5.5.0001, 5.5.0003, 6.4.0005, 7.4.0001
- Skills: `orchestrator-design`, `composition-root`, `hex-arch-python`, `task-ordering-hex`, `pytest-with-fakes`

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

### 2026-10-25 — [measurement] Concept D2, custo do retreino num fold — Claude (executor)
**Contexto:** o D2 manda medir o custo do retreino antes de decidir entre retreinar e
predizer com os checkpoints congelados, e o D7 escolhe as seeds com esse número.
**Medição:** script avulso no scratchpad (`probe_cost.py`) chamando `deps.train_tft` com
`tft_train_command` sobre o `aapl_confirmatory.toml` com `geometry.n_folds = 1`, seed 1,
sobre uma CÓPIA do `processed/dataset_tft` do confirmatório num `data_root` descartável
(nenhuma métrica calculada, nada gravado no `data_root` confirmatório). Container
`financial_forecasting-app:dev`, `--cpus 6 --memory 8g`, com outro gate (`ff-gate-233`)
rodando ao mesmo tempo:
```
ELAPSED_S 1641.9 runs [('aa6486a46a33e3f29d1b06de2b99cd7ae032613286c38432f5d30b29948e57aa', 3472)]
```
3472 linhas = 7 níveis × (251 decisões em h+1 + 245 em h+7).
**Razão:** ~27 min por seed num fold contra 1,5–2,9 h por seed nos 6 folds da 5.5; com
três seeds, a rodada fica em ~1 h 45 min (FinBERT ~15 min). Sustenta D2 e D7.

### 2026-10-25 — [deviation] Checkpoint C uma vez, depois das oito Tasks — Claude (executor)
**Contexto:** o PROMPT da sessão única pede o Checkpoint C a cada 2–3 Tasks.
**Razão:** as oito Tasks foram implementadas e testadas antes do primeiro bloco ser
revisado (a sessão adiantou o código enquanto esperava a CI do PR #239). O Checkpoint C
rodou uma vez sobre o diff inteiro `8573e368..HEAD`, com a mesma lente; os achados viraram
os commits `-fix` (abaixo). Nenhum achado dependia da ordem dos blocos.

### 2026-10-25 — [measurement] Checkpoint C, achados e disposição — Claude (executor)
**Contexto:** revisor de contexto zerado sobre `8573e368..HEAD` (skills hex-arch-python,
composition-root, orchestrator-design, pytest-with-fakes).
**Medição:** 1 major e 3 minor.
1. major — `mkstemp` cria o temporário com 0600, e o `os.replace` publica o `serving.env` e
   o `cohort.toml` com esse modo: o `docker --env-file` no host Linux e o `USER app` da
   imagem de runtime não os leriam. **Corrigido** em `8865d28b` (chmod 0644 antes da troca,
   teste do modo em POSIX).
2. minor — `production_cohort_for` repetia os 14 argumentos do `confirmatory_cohort_for`.
   **Corrigido** em `480ea62e` (construtor `cohort_runner` único).
3. minor — o leiaute dos três brutos (`_RAW_INPUTS` do `cli.py`) repete o nome de arquivo
   dos fetchers Parquet. **Refutado** com artefato: o e2e
   `tests/e2e/test_production_round_cli.py` grava os brutos pelo `write_raw` (o leiaute que
   os fetchers leem), passa-os pelo `_raw_inputs`/cópia e materializa com os fetchers reais;
   uma divergência quebra o e2e (`materialize` não acha o arquivo). A duplicação de
   `prepare_round_spec` com o `freeze` (grid → impressão digital → `fits` → ida e volta) é
   a mesma leitura pelas MESMAS funções (`load_training_grid`, `grid_fingerprint`), não uma
   segunda fórmula.
4. minor — o `infer` da 7.1 chama `check_cohort_declarations` com o padrão `False` e recusaria
   uma rodada; um gold de produção futuro precisaria disso. **Escalado** como `[finding]`
   (abaixo) e issue #253.

### 2026-10-25 — [finding] Gold de produção exigiria a herança no `infer` — Claude (executor)
**Contexto:** achado 4 do Checkpoint C. O spec da rodada herda a proveniência dos sweeps do
r0; `resolve_tft_checkpoints`, `predict_tft_from_checkpoints` e
`predict_tft_attribution_from_checkpoints` chamam `check_cohort_declarations` sem
`inherited_hyperparameters`, então o `infer` sobre uma rodada sai com
`CohortDeclarationMismatchError`. A API não é afetada (o `serve_inference_for` não confere
declarações).
**Direção sugerida:** se o dono reverter o D3 e quiser o conformal em produção, passar a
herança ao `infer` pela mesma restrição de fábrica.
**Stage candidata:** issue #253 (gold de conformal no cohort de produção), ligada à #202.

### 2026-10-25 — [measurement] Auditoria de testes (subagente independente) — Claude (executor)
**Contexto:** gate "Auditoria de Testes" do PROMPT da sessão única, com mutação real nas três
funções mais críticas (`publish_serving_pointer`, `_refuse_cohort_overlap`, o ramo
`inherited_hyperparameters` de `check_cohort_declarations`), worktree montada `:ro` e
copiada para `/tmp/m`, `PYTHONPATH=/tmp/m/src:/tmp/m` (import conferido em
`/tmp/m/src/financial_forecasting/__init__.py`).
**Medição (rodada 1):** caminho feliz coberto em CA1–CA5, CA7, CA8; ramo da herança 8/8
mutantes mortos; sobreviventes reais: P5 (sufixo comparado como texto), P6 (só a data),
P10 (caminho relativo), P14 (ponteiro sem `DATA_ROOT`), O6 (caixa do repositório), O7
(irmão de `data/cohorts`), O9 (`..` no caminho), M1 (marca antes de materializar), M2/M5
(`--break-stale-lock` não repassado), M3 (`raw/` não refeito); e casos do §6 sem teste pelo
CLI (verify divergente com ponteiro anterior, falha do ponteiro, modelo congelado, ida e
volta do spec). Os testes que faltavam entraram em `8865d28b` e `8cfda3b3`; o modelo passou a
ser validado antes de escrever (`require_production_model`).
**Medição (rodada 2, mesmo script `mut.sh`):**
```
IMPORT FROM /tmp/m/src/financial_forecasting/__init__.py
BASELINE: 118 passed, 6 warnings in 3.53s
[P3] SOBREVIVENTE :: 32 passed
[P4] SOBREVIVENTE :: 32 passed
[P12] MUTATION NOT APPLIED
[I8] MUTATION NOT APPLIED
```
Todos os outros mutantes morreram. P3 e P4 são equivalentes (`parse_round_name` é injetivo:
a guarda `current != round_name` e o `>=` não mudam o resultado). P12 e I8 não se aplicam ao
código novo (a escrita ganhou o `chmod`; a fábrica passou a delegar a `cohort_runner`); os
equivalentes atuais são mortos por `test_failed_replace_keeps_the_previous_pointer_and_no_temporary`
e `test_only_the_production_factory_inherits_hyperparameters`.
**Razão:** os seis itens do questionário ficam "sim".

### 2026-10-25 — [deviation] Conferência do CA5 no gate depois do `cohort_runner` — Claude (executor)
**Contexto:** o §3 confere "só `production_cohort_for` passa `True`" com
`grep -rnE "^\s+inherited_hyperparameters=True," src/`. Depois de `480ea62e` a fábrica de
produção passa `inherited_hyperparameters=True` como argumento de `cohort_runner(...)`, numa
linha sem a vírgula final.
**Razão:** a conferência mecânica do CA5 passa a ser o teste
`tests/unit/test_composition_root_production.py` (flag `False` no confirmatório e `True` na
produção) mais `grep -rn "inherited_hyperparameters=True" src/ --include=*.py`, cujas
ocorrências são só a fábrica de produção e docstrings.

### 2026-10-25 — [measurement] Gate 1, `make check` na saída do código — Claude (executor)
**Contexto:** o plano de gates (§1) tem um único `make check`, depois da Task 08 e dos
`-fix`, sobre o HEAD `8cfda3b3` rebaseado em `4c4e631b`.
**Medição:** `docker run --name ff-gate-202 --cpus 6 --memory 8g` com a worktree em `/app`,
`make check PYTEST_PAR='-n 4 --dist loadgroup'` (21:06–22:12 UTC):
```
uv run lint-imports … Contracts: 19 kept, 0 broken.
[fake_parity] PASSOU — nenhuma violação nova.
[port_coverage] PASSOU — nenhuma violação nova (1 no baseline).
src/financial_forecasting/cli.py                                         266      3    99%
src/financial_forecasting/composition_root.py                            366      7    98%
src/financial_forecasting/features/modeling/adapters/in/cli/production_commands.py   81  0  100%
src/financial_forecasting/features/modeling/application/dtos/cohort_spec.py         127  0  100%
src/financial_forecasting/features/modeling/application/use_cases/cohort_unit_runner.py   133  0  100%
src/financial_forecasting/features/modeling/application/use_cases/run_confirmatory_cohort.py   91  1  99%
TOTAL                                                                  21180    308    99%
Required test coverage of 90.0% reached. Total coverage: 98.55%
========= 9396 passed, 38 skipped, 892 warnings in 3813.15s (1:03:33) ==========
MAKE_EXIT=0
```
**Razão:** gate de saída verde; cada arquivo tocado ≥ 98 %.

### 2026-10-25 — [measurement] Etapa R0–R2, rodada real 2025-06-30 e a API servindo-a — Claude (executor)
**Contexto:** CA6. Brutos lidos (cópia) de `<checkout principal>/data/cohorts/aapl`; a raiz
`raw-cut` corta candles em `timestamp < 2025-07-01`, notícias em `published_at` e
fundamentos em `reported_date` (3896 candles, 3584 notícias, 61 fundamentos); `raw-full` é a
cópia integral (4024, 6921, 81; sha256 `e102c738…`, `918cde47…`, `babfffbf…`). `sha256sum`
dos 355 arquivos de `data/cohorts/aapl` gravado antes. Venv `ff84-venv-sentiment` (cópia
do venv de dev + `uv sync --locked --extra dev --extra sentiment`, transformers 4.57.6,
torch 2.13.0+cpu). Rodada pelo `docker run` do runbook com `--cpus 6 --memory 8g`, a worktree
limpa em `/app`, só o `.git` principal `:ro` em `/main.git` e os brutos `:ro` em `/raw`; o
`data/` do checkout principal não é montado.
**Medição (R1):** `production-round --production-root data/production/aapl --round 2025-06-30
--raw-root /raw/raw-cut --cohort config/cohorts/aapl_production.toml`, 22:13:55 → 23:31:35 UTC
(77 min 40 s):
```
materialized AAPL: 3896 candles, 3584 news, 61 fundamentals
dataset rows 3822 (2010-04-21..2025-06-30), feature_set_hash 7df0e1b4…09e0
round spec written: /app/data/production/aapl/rounds/2025-06-30/cohort.toml (dataset fe7f5185f308)
unit baselines: ran (5 runs, 17360 rows written, 208.3s)
unit gbm: ran (1 runs, 3472 rows written, 52.3s)
unit tft:seed=1: ran (1 runs, 3472 rows written, 1391.8s)
unit tft:seed=2: ran (1 runs, 3472 rows written, 1159.6s)
unit tft:seed=3: ran (1 runs, 3472 rows written, 1368.3s)
cohort aapl_production-r0-df7d1ccd49bf: 9 models x 1 folds; rows expected 31248, observed 31248
OK
published aapl_production-r0-df7d1ccd49bf → /app/data/production/aapl/serving.env
EXIT=0
```
Teste servido (TFT, h+1): 251 decisões, 2024-06-27..2025-06-27. Fim do treino (grid da
rodada, `test_start − 547`): 2022-04-22.
**Medição (R2):** API pelo comando de recriação do runbook (`docker rm -f` + `docker run -d
--env-file data/production/aapl/serving.env … uvicorn`), `--cpus 2 --memory 2g`:
```
2025-09-15 HTTP 404 0.514289s  {"detail": "não há dados para o pedido solicitado: decisão 2025-09-15 sem linha de teste para (seed 1, h+1), (seed 2, h+1), (seed 3, h+1)", "type": "not_found"}
2025-06-27 HTTP 200 0.584167s  cohort_id aapl_production-r0-df7d1ccd49bf, target 2025-06-30, seeds [1, 2, 3], conformal unavailable "gold não publicado para o cohort aapl_production-r0-df7d1ccd49bf", explainability unavailable
recreate_ms=22566
```
**Razão:** a rodada sai servível pela API sem mudança de código (CA1, CA2 do concept; critérios
1 e 3 da #202), e a API recriada leva ~23 s para voltar a responder.


### 2026-10-26 — [measurement] Etapa R3–R4, rodada real 2025-12-31, troca do cohort servido e isolamento — Claude (executor)
**Contexto:** CA6, segunda metade. A rodada roda depois do merge de `origin/develop`
(`339ecef7`) e dos `-fix` da auditoria, com a mesma montagem da R1: só o `.git` principal
`:ro`, brutos `raw-full` `:ro` e o `data/` do checkout principal sem montar.
**Medição (R3, rodada):** `production-round … --round 2025-12-31 --raw-root /raw/raw-full`,
00:31:58 → 01:51:14 UTC (79 min 16 s):
```
materialized AAPL: 4024 candles, 6921 news, 81 fundamentals
dataset rows 3950 (2010-04-21..2025-12-31), feature_set_hash 7df0e1b4…09e0
round spec written: /app/data/production/aapl/rounds/2025-12-31/cohort.toml (dataset 00e4406dcd96)
unit baselines: ran (5 runs, 17360 rows written, 147.0s)
unit gbm: ran (1 runs, 3472 rows written, 38.6s)
unit tft:seed=1: ran (1 runs, 3472 rows written, 1316.1s)
unit tft:seed=2: ran (1 runs, 3472 rows written, 1509.3s)
unit tft:seed=3: ran (1 runs, 3472 rows written, 1073.9s)
cohort aapl_production-r0-ad1bd972fad7: 9 models x 1 folds; rows expected 31248, observed 31248
OK
published aapl_production-r0-ad1bd972fad7 → /app/data/production/aapl/serving.env
EXIT=0
```
O dado da rodada é o do confirmatório (impressão digital `00e4406d…`, o mesmo fim em
2025-12-31): ela simula a chegada de dado novo em relação à rodada 1, como o CA6 declara.
Teste servido (TFT, h+1): 251 decisões, 2024-12-30..2025-12-30. Fim do treino (`test_start −
547`): 2022-10-25. O `serving.env` passou a `DATA_ROOT=/app/data/production/aapl/rounds/2025-12-31`.
**Medição (R3, troca da API):** recriação pelo comando do runbook com o ponteiro novo:
```
recreate_ms=19103
2025-09-15 HTTP 200 0.704211s  cohort_id aapl_production-r0-ad1bd972fad7, target 2025-09-16, seeds [1, 2, 3], conformal unavailable "gold não publicado para o cohort aapl_production-r0-ad1bd972fad7", explainability unavailable
2025-12-30 HTTP 200 0.551813s
```
A mesma decisão de 2025-09-15 que respondia 404 com a API na rodada 1 (R2) responde 200 na
rodada 2, sem mudança de código.
**Medição (R4, isolamento):** `sha256sum` dos arquivos de
`<checkout principal>/data/cohorts/aapl` antes de R0 e depois de R3, `diff` dos dois:
```
IDENTICAL 355 files
```
**Razão:** fecha o CA6 e os três critérios da #202 com execução real: rodada servível sem
tocar o `data_root` confirmatório, janela tratada pela raiz imutável e o risco da recriação
medido (19–23 s) e aceito (entrada abaixo), API servindo o cohort novo sem mudança de código.

### 2026-10-26 — [deviation] Etapa R, fim do treino derivado da geometria — Claude (executor)
**Contexto:** a Etapa R (R1, R3) mandava ler a data do fim do treino "do `dim_run`".
**Razão:** o `dim_run` não guarda janela de treino (colunas: `run_id`, `asset`,
`parent_sweep_id`, `feature_set_name`, `config_signature`, `split_fingerprint`, `fold`,
`seed`, `model_version`, `schema_version`, `created_at_utc`). A data sai do grid materializado
da rodada pela mesma geometria do splitter: última sessão de treino = `test_start − 547`
(gaps de 14 + early stopping 252 + calibração 252), conferida contra a primeira decisão de
teste gravada no silver.

### 2026-10-26 — [measurement] Cópia de artefatos do MLflow fora da raiz da rodada — Claude (executor)
**Contexto:** achado F3 da auditoria da Stage; o concept I1 declara que a cópia de artefato do
MLflow vai para `./mlruns/` do diretório de trabalho.
**Medição:** `du -sh mlruns` na worktree: `103M` depois da rodada 2025-06-30 e `185M` depois
da rodada 2025-12-31, ou seja, ~80–100 MB por rodada (checkpoints das três seeds do TFT). O
probe de custo não conta: rodou com a worktree montada `:ro`.
**Razão:** o runbook passa a mandar limpar o `./mlruns/` junto com as rodadas antigas
(`c34e0fb2`).

### 2026-10-26 — [decision] Aceitação do risco da recriação da API (CA6) — Claude (executor)
**Contexto:** o CA6 pede o risco do intervalo de recriação aceito por escrito no §7; o ADR
8.4.0002 item 3 já o declara.
**Pergunta:** o intervalo em que a API não responde durante a troca de cohort é aceitável no v0?
**Opções:**
- A — dois processos atrás de um proxy (troca sem intervalo)
- B — recriar o container no horário agendado e aceitar o intervalo ✅ recomendada
**Decisão:** B.
**Razão:** medido em 22,6 s (R2) e 19,1 s (R3), uma vez por semana, num projeto com um
operador e sem meta de disponibilidade; o caminho A exige infraestrutura nova para um ganho
que ninguém pediu. Fica a ratificar pelo dono junto com o D4.

<!-- END: post-execution -->
