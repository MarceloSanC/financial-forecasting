---
title: Technical — Stage 6.4 — Gold builders modulares e quality gates (montagem das séries, DuckDB, MCS em produção)
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), TDD inside-out no BC evaluation — validadores públicos da 6.2, regra única de identificador em shared, VOs de entrada, SeriesAssembly, registry de quality checks, HorizonReports e gold_build_order, DTOs e ports GoldStore/GoldBuilder/SilverTableReader, ParquetGoldStore e cinco builders, use case RefreshGold, wiring, e2e e roadmap
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, gold-builders-and-quality-gates, evaluation, gold, refresh-gold, series-assembly, quality-checks, registry, horizon-reports, graphlib, gold-store, gold-builder, silver-table-reader, parquet, duckdb, manifest, mcs, port-coverage, importlinter]
status: done
created_at: 2026-09-29
updated_at: 2026-09-29
stage_id: 6.4-gold-builders-and-quality-gates
stage_title: Gold builders modulares e quality gates
step_id: 6
step_title: Núcleo estatístico confirmatório
depends_on: [6.2-paired-inference-dm-mcs-holm, 6.3-calibration-risk-backtests]
concept_ref: ./concept.md
issue_id: 117
branch: feat/117-6-4-gold-builders-and-quality-gates
tasks_count: 13
---

# Technical — Stage 6.4 — Gold builders modulares e quality gates

> **Como usar (para code assistant):** ler §1, executar Tasks em ordem (§2),
> 1 Task = 1 commit, não avançar sem verificação verde; ao fim validar §3 e
> registrar §7. Commits seguem [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
> `<type>(<escopo>): <descrição> [6.4/task-NN]`, `Refs #117`, subject
> ≤ 100 caracteres (hook `commit-msg`). Escopo `evaluation`, salvo a Task 02
> (`shared`) e a Task 13 (`roadmap`).
>
> Ao encontrar algo não previsto em §1–§6 ou no `concept.md`: **pausar**,
> resolver pelo §2 de [`PROMPT-step-single-session.md`](../../PROMPT-step-single-session.md)
> (docs → ADR; E/C → `evidence-resolution` + ADR 6.4.0009+; P → sobe à sessão
> mestra) e registrar em §7. Gap que muda contrato, fronteira ou critério do
> concept não é resolvido aqui: sobe. Nunca propagar silenciosamente.

## 1. Contexto e estratégia de execução

### Resumo

Terceira fatia do BC `evaluation` e primeira com leitura, orquestração e
escrita: os ajustes públicos mínimos em quatro arquivos da 6.2
(`MIN_MODELS` no VO e importado pela fábrica, `validate_bootstrap_parameters`,
`validate_mcs_reps`), a regra de identificador de caminho com dono único em
`shared/domain`, os VOs de entrada (`ForecastRecord`, `CohortRun`,
`RealizedReturns`) e da montagem (`AssembledCohort`, `HorizonSamples`,
`AlignmentReport`), o serviço `SeriesAssembly` (dono único de I3–I10, com a
aresta de dados declarada para `QuantileForecast`), o `QualityCheckRegistry`
com quatro checks e o passo de pré-condições no domínio, o `HorizonReports` e
o `gold_build_order`, os DTOs do refresh, os ports-out `GoldStore`,
`GoldBuilder` e `SilverTableReader` com fakes e suítes de contrato, o
`ParquetGoldStore` e os cinco builders em `adapters/out/duckdb/`, o use case
`RefreshGold`, o wiring no `composition_root` com e2e sobre silver sintético e
a redação do roadmap §6.4.

Todas as decisões vêm do concept **por referência** — nenhuma é re-derivada:
D1 (montagem num serviço único, achados em vez de exceção), D2 (dedup não
reaplicado —
[ADR 6.4.0003](../../adr/6_4_0003-single-observation-verified-not-rededuplicated.md)),
D3 (insumos —
[ADR 6.4.0004](../../adr/6_4_0004-evaluation-inputs-silver-reader-port-and-medallion-dataset.md)),
D4 (registry e severidade —
[ADR 6.4.0002](../../adr/6_4_0002-quality-checks-severity-and-persisted-results.md)),
D5 (relatórios, duas amostras —
[ADR 6.4.0007](../../adr/6_4_0007-gold-persists-both-samples-identified.md)),
D6 (MCS com parâmetros explícitos —
[ADR 6.4.0006](../../adr/6_4_0006-refresh-parameters-explicit-no-domain-defaults.md)),
D7 (DAG por `graphlib` —
[ADR 6.4.0001](../../adr/6_4_0001-gold-builder-dag-graphlib-declared-dependencies.md)),
D8 (geração inteira, manifesto por último —
[ADR 6.4.0005](../../adr/6_4_0005-gold-full-refresh-per-cohort-partition.md)),
D9 (roadmap). Sem check "domínio × biblioteca" em runtime
([ADR 6.4.0008](../../adr/6_4_0008-no-runtime-library-cross-check-in-gold.md)).

### Estratégia

**TDD inside-out** (skill `task-ordering-hex`): primeiro os validadores
públicos que o DTO e o passo de pré-condições consomem (6.2, Task 01) e a regra
de identificador (shared, Task 02) → VOs folha (Task 03) → `SeriesAssembly`
(Task 04) → checks (Task 05) → `HorizonReports` + `gold_build_order` (Task 06)
→ DTOs + port `GoldStore` (Task 07) → `ParquetGoldStore` (Task 08) → port
`GoldBuilder` (Task 09) → builders (Task 10) → port `SilverTableReader` + use
case `RefreshGold` (Task 11) → wiring + e2e (Task 12) → roadmap (Task 13).
Cada commit deixa o build verde.

**Exceções de ordem/contagem declaradas (PIPELINE §4.3; skill `task-ordering-hex`):**

- **13 Tasks** — acima da estimativa do concept (12) e dentro do teto do
  ROADMAP-1 (15; precedente: 6.2 com 13). Motivos: (a) as mudanças em
  arquivos da 6.2 ficam numa Task própria, com os testes existentes intactos
  (pedido da sessão mestra); (b) a regra de identificador do C3 ganha dono
  único em `shared` numa Task de escopo `shared` (decisão de detalhe abaixo)
  — um commit = um escopo; (c) a janela de baseline do `port-coverage` é de
  **exatamente um commit** (ADR 6.1.0005), o que força port → adapter
  adjacentes para `GoldStore` (07 → 08) e `GoldBuilder` (09 → 10). Em troca,
  a montagem é uma Task só (o concept estimava duas) e o `SilverTableReader`
  entra junto do seu primeiro consumidor (Task 11), sem baseline, porque o
  real (`ParquetAnalyticsRepository`) já existe.
- **Tasks com mais de 5 arquivos** (PIPELINE §4.3 "tipicamente"): 01 (quatro
  arquivos da 6.2 + os quatro testes que só ganham casos), 04 (serviço +
  teste + conftest + `.importlinter` + caso de violação + LAYOUT — a aresta
  nova precisa nascer no mesmo commit do import), 05 (registry e quatro
  checks num subpacote — os checks só existem juntos no registry), 07 e 09
  (port + fake + suíte + as duas pontas do baseline; na 07 os DTOs entram
  junto porque `GoldPartition`/`GoldTable`/`GoldManifest` **são** a assinatura
  do port `GoldStore` — separá-los numa Task anterior levaria a 14 Tasks sem
  ganho de isolamento: nada consome os DTOs antes do port), 10 (cinco builders
  de mapeamento puro + `__init__` + suíte + as duas pontas do baseline), 03
  (quatro VOs folha + `__init__` do subpacote de teste + o teste + o gate de
  pureza, que precisa varrer `gold/` no mesmo commit em que o subpacote nasce)
  e 11 (port + fake + contrato do `SilverTableReader`, que já tem real, junto
  do seu único consumidor — use case + teste unitário — e a docstring do
  repositório que o `check_port_coverage` lê; separar deixaria um port sem
  consumidor por um commit).
- **Gates de arquitetura tocados:** Task 03 (`test_unit_evaluation_purity.py`
  passa a varrer subpacotes), Task 04 (`.importlinter` +
  `test_import_contracts.py`), Tasks 07–10 (`scripts/arch_baseline.toml` +
  `test_port_coverage_gate.py`, janela de um commit cada). Essas Tasks rodam
  T3 (`make check`).

**Decisões de detalhe planejadas (abaixo do limiar de concept — não mudam
contrato, fronteira nem critério; viram `[decision]` em §7 ao executar):**

- **Testes unitários da 6.4 em `tests/unit/features/evaluation/gold/`**
  (caminho do roadmap e do A1 para `test_builder_explicit_deps.py`). O gate
  AST `tests/architecture/test_unit_evaluation_purity.py` hoje só varre
  `*.py` do nível de cima (`glob`); a Task 03 troca por `rglob` e acrescenta
  um caso que prova a cobertura do subpacote. A fábrica de cohort sintético
  vive em `gold/conftest.py` (local do subpacote, stdlib + domínio).
- **Regra de identificador de caminho com dono único** (Task 02; C3, ADR
  6.4.0005 item 1 "the identifier rule of the MedallionStore read-only
  pair"): o padrão `^[A-Za-z0-9._-]+$` hoje está **duas** vezes (privado no
  `ParquetMedallionStore` e no `FakeMedallionStore`) e o `GoldPartition`
  seria a terceira. Sobe para `shared/domain/services/path_identifier.py`
  (`PATH_IDENTIFIER_PATTERN`, `validate_path_identifier(value, *, field) ->
  None`, com `fullmatch` — concept §4 "Shared"); adapter e fake passam a
  consumi-lo com o mesmo texto de mensagem
  (o campo carrega o prefixo `read-only pair (…) asset filter`), e o DTO da
  6.4 também. Sem mudança de comportamento no `MedallionStore`.
- **`ForecastRecord.model` = `fact_oos_predictions.model_version`** e
  `seed`/`fold` vêm do `dim_run` do mesmo `run_id` (junção no use case): é o
  que permite ao `SeriesAssembly` comparar o `model_version` do fato com o do
  `CohortRun` (I3). Linha de fato com `run_id` fora do cohort é descartada na
  leitura (ADR 6.4.0004 item 2), não é achado.
- **Mais de um `feature_set_name` no cohort:** o use case lê a partição de
  cada nome (ordenados) e entrega tudo ao `SeriesAssembly`, que registra o
  achado `multiple_feature_sets` — a leitura não decide.
- **Resumo do `target_return` como propriedade do `RealizedReturns`**
  (`n_sessions`, `returns_fsum` por `math.fsum`, `first_timestamp`,
  `last_timestamp`): uma computação, consumida pelo `realized_provenance` e
  pelo manifesto. As somas de `close`/`volume` do fingerprint ficam na função
  de leitura do use case (entradas do `DatasetFingerprint.compute`; o hash é
  do VO de `shared`, LAYOUT §7).
- **I10 consulta os donos:** `check_points(T, h)` (6.2, público) é chamado e o
  `ValueError` vira achado `common_sample_too_short`; o mínimo do b̂_sb é
  `T < MIN_BLOCK_LENGTH_OBS` contra a constante pública do dono.
- **`window_deficits`** validados no `SeriesAssembly` (int não-`bool` ≥ 0 por
  modelo; modelo ausente ⇒ 0): não há validador público "int ≥ 0" (a
  unificação é da #118, e o ADR 6.4.0006 veda nova escrita no DTO); o ponto
  de chamada novo vira `[finding]` para a #118 em §7.
- **Passo de pré-condições** (ADR 6.4.0002 item 4) em
  `domain/services/quality_checks/statistical_preconditions_check.py`:
  `models_suffice(models) -> bool` (k ≥ `MIN_MODELS`) e
  `block_request_defect(differential) -> UndefinedReason | None`
  (`is_constant` → `CONSTANT_DIFFERENTIAL`; `validate_block_length_request`
  erguendo → `INVALID_SERIES`); o VO `BlockEstimate` (par, valor ou motivo
  `UndefinedReason` + `detail`) e o enum `UndefinedReason` moram em
  `domain/value_objects/block_estimate.py` (o `QualityCheckContext` do
  `registry.py` e o check os importam sem ciclo registry ↔ check). O use case chama o
  backend só para os pares sem defeito e converte **só** `ArithmeticError` em
  `BlockEstimate` indefinido (`BACKEND_ARITHMETIC`).
- **`HorizonReports` recebe a `PairedLossSeries`** montada uma vez pelo use
  case depois do passo de pré-condições (a mesma que foi ao backend) — sem
  segunda chamada da fábrica. O MCS (bloco → índices → `evaluate`) é
  orquestrado no use case, porque atravessa o port `McsBackend`; os
  relatórios de 6.1/6.2/6.3 ficam no domínio.
- **`GoldTable(name, key, rows)`**: `key` é a tupla das colunas do grão; o
  `__post_init__` exige mesmas colunas em toda linha, `key ⊆ colunas`, linhas
  **estritamente** ordenadas pela chave (`None` antes de qualquer valor) —
  o "rows are sorted by the table's key" do ADR 6.4.0005 item 5 com dono
  único no DTO, que os builders satisfazem e o store preserva. Tabela
  `gold_<builder.name>` (builder `quality_checks` → `gold_quality_checks`).
- **`GoldManifest.as_mapping()`** é a única serialização (JSON-safe; o store
  grava com `json.dumps(sort_keys=True)`); fake e real guardam/escrevem o
  mesmo mapeamento.
- **`gold_metrics_by_run` em formato longo** (concept §13, questão aberta):
  uma linha por (modelo, seed, horizonte, amostra, métrica, nível baixo,
  nível alto) — colunas em §1 "Tabelas gold".
- **Testes de mapeamento dos builders no módulo de contrato**
  (`test_gold_builder_contract.py`): adapter não pode entrar em
  `tests/unit/features/evaluation/**` (gate AST); os testes específicos de
  cada builder ficam fora da parametrização, no mesmo arquivo (precedente: o
  teste só-do-fake da 6.2 Task 11). Os `GoldInputs` de teste vêm de
  `tests/contract/features/evaluation/_gold_inputs.py` (módulo privado, sem
  `test_`, importado absolutamente; montado só com domínio + `FakeMcsBackend`).
- **Hasher nos testes unitários do use case:** o gate AST proíbe importar
  `CanonicalJsonHasher` (adapter) e o `Hasher` não tem fake por desenho
  (#70); o teste declara um dublê local mínimo (`_StubHasher`, devolve o
  `repr` ordenado do payload) só para o `DatasetFingerprint.compute`. O e2e
  usa o `CanonicalJsonHasher` real.
- **`_LazyArchMcs` no `composition_root`** (precedente statsforecast/torch):
  `import arch` medido nesta Fase 3B em **8,15 s** a frio no container
  (`python -X importtime`); o proxy adia o import até a primeira chamada.
- **`validate_mcs_reps` com mensagem que satisfaz os dois testes existentes**
  (`"reps must be >= 1000"` do `McsReport` e `"reps >= 1000"` do
  `ModelConfidenceSet.evaluate`): `f"reps must be >= {MIN_MCS_REPS} (the MCS
  needs reps >= {MIN_MCS_REPS}), got {reps!r}"`. Nenhuma expectativa de
  teste da 6.2 muda.
- **Ordem dos builders validada no `RefreshGold.__init__`** (C1, I15, ADR
  6.4.0001 item 4): `gold_build_order` roda no construtor e a ordem fica
  guardada — grafo inválido falha no wiring, antes de qualquer `__call__` e,
  portanto, antes de qualquer leitura; I15 ("ordem validada → …") segue
  valendo porque a validação precede tudo o que o use case faz.
- **Log por etapa** via `logging.getLogger(__name__)` do use case, uma linha
  `INFO` por etapa com `step=<nome> duration_s=<perf_counter> in=<n>
  out=<n>` e uma linha final `status=<COMPLETED|BLOCKED>`; timestamps do
  manifesto só do `Clock` (I16).

**Custo do MCS — medido nesta Fase 3B, não presumido (concept §3, §10, A12):**
script fora do repo no container de dev (`python 3.12.13`, volume
`ff-step62-venv`, 12 CPUs), `ArchMcs` real + `ModelConfidenceSet` do domínio,
perdas AR(1) positivas sintéticas (`random.Random(20260929)`),
`reps = MIN_MCS_REPS = 1000`, α = 0,10, bloco da regra (l = 3):

| T | k (pares) | b̂_sb (todos os pares) | índices estacionário | `evaluate` estacionário | índices moving-block | `evaluate` moving-block |
|---|---|---|---|---|---|---|
| 1000 | 4 (6) | 0,011 s | 0,289 s | 0,243 s | 0,312 s | 0,211 s |
| 1000 | 6 (15) | 0,025 s | 0,335 s | 0,505 s | 0,389 s | 0,351 s |
| 500 | 4 (6) | 0,007 s | 0,166 s | 0,135 s | 0,182 s | 0,110 s |

Pior caso medido ≈ 0,9 s por (horizonte, esquema): 2 horizontes × 2 esquemas
com k = 6 e T = 10³ ≈ 3,6 s — stdlib + `arch` bastam, sem paralelismo nem
cache. `import arch` a frio: 8,15 s (motiva o proxy lazy). A Task 12 re-mede
dentro do `RefreshGold` real (duração da etapa `mcs` no log do e2e e um
`timeit` com T = 1000) e registra **uma** entrada `[decision] Task 12 — custo
do MCS` em §7 (A12).

**Gate por Task (RUNBOOK §Gates em camadas, ADR 0.0.0055):** T1 =
`make check-task SLICE=evaluation` nas Tasks 01, 05, 06; `SLICE="evaluation
analytics_store"` na 11 (docstring do repositório); `make check-block` nas
Tasks 02 (`shared`) e 12 (`composition_root`); T3 = `make check` nas Tasks
03, 04, 07, 08, 09, 10 (gates de arquitetura/baseline). Task 13 (docs):
`make docs-check`. Checkpoint C (T2, `make check-block`) após as Tasks 03,
06, 09 e 12; T3 no gate de saída (§3).

**Onde rodar — convenção dos blocos de verificação (vale para §2 e §3; regra
do Step):**

- Cada verificação vem rotulada **Container** ou **Host**. O host não tem o
  toolchain (`uv`/`make` só no container).
- **Container:** o bloco inteiro roda num **único** `bash -euo pipefail -c`,
  dentro de **um** `docker run`, com o venv da 6.4 (volume `ff-step62-venv`,
  que tem `arch`/`statsmodels` do lock atual do `develop`; se o lock mudar,
  `uv sync --inexact --extra dev` uma vez):
  ```bash
  WT=feat-117-6-4-gold-builders-and-quality-gates
  MSYS_NO_PATHCONV=1 docker run --rm \
    -v "<raiz-das-worktrees>/$WT:/app" \
    -v "<raiz-do-repo>/.git:/main.git" \
    -v ff-step62-venv:/app/.venv \
    -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app \
    -w /app financial_forecasting-app:dev bash -euo pipefail -c "$(cat <<'EOF'
  git config --global --add safe.directory '*'
  # <linhas do bloco Container da Task>
  EOF
  )"
  ```
  (script por `-c`, não por stdin: um comando que lesse stdin consumiria o
  resto do script.)
- **Host:** Git Bash na raiz da worktree, o bloco como um só script
  `bash -euo pipefail` (scripts stdlib `python scripts/check_*.py`, greps de
  docs, `git`).
- **Negação:** `set -e` ignora o status de `! cmd`; toda asserção negativa é
  `if <cmd>; then echo "FAIL: <motivo>"; exit 1; fi`. Pipeline dentro de
  `if` nunca termina em `grep -q` (com `pipefail`, o SIGPIPE do produtor
  vira falso negativo): a saída vai para arquivo e o `grep` lê o arquivo.
  Arquivo produzido e lido no mesmo bloco; toda leitura começa por
  `test -s "$f"` (o `/tmp` não sobrevive entre `docker run --rm`; `grep`
  sobre arquivo ausente devolve 2).
- **Tokens de nome de teste:** cada Task lista, por arquivo, os tokens que os
  nomes dos seus testes **devem** conter. O §3 prova por coleta que cada
  token casa ≥ 1 teste do arquivo — casado contra o nome da função após o
  `::`, **sem** o id `[...]` de parametrização, substring sem distinção de
  caixa — e **recusa a lista** se um token repetir ou estiver contido em
  outro do mesmo arquivo (prova vácua). Os tokens são novos: nenhum casa um
  teste que já existe no `develop` (a Task 01 acrescenta a arquivos da 6.2).

### Pré-condições

- Stages `6.1`, `6.2` e `6.3` em `done` e mergeadas em `develop` (PRs #112,
  #116, #115): `CoverageSeries`, relatórios da 6.1, `paired_pinball_losses`,
  `PairedLossSeries`, `HolmCorrection`, `ModelConfidenceSet`,
  `BootstrapIndices`, `McsBackend` + `ArchMcs` + `FakeMcsBackend`,
  `HitSequences`, `ChristoffersenTest`, `WilsonBand`, `var_tail_for`.
- Concept desta Stage em `done` (commit `765fd2f`, re-aprovado após o
  Checkpoint A rodada 3 e o Checkpoint B rodada 1 — `path_identifier` em
  `shared` ratificado no §4/D9/C3); ADRs 6.4.0001–0008 em `accepted`.
- Working tree na branch `feat/117-6-4-gold-builders-and-quality-gates`;
  volume `ff-step62-venv` presente.
- Nenhuma dependência nova (`pyproject.toml`/`uv.lock` intocados):
  `pyarrow`, `pandas` e `duckdb` já são dependências do projeto (4.2, 3.5).

### Premissas técnicas

- Python 3.12; `uv`; `make check` = ruff + mypy strict + check_layout +
  lint-imports + fake-parity + port-coverage + docs-check + pytest com
  cobertura ≥ 90 %.
- Domínio só stdlib (`graphlib`, `math`, `dataclasses`, `enum.StrEnum`) +
  domínio + o VO `QuantileForecast` (aresta declarada) + os VOs de
  `shared/domain`. `pyarrow`/`duckdb`/`pandas` **só** em
  `evaluation/adapters/out/duckdb/` (A11).
- Silver sintético nos testes: sem dado materializado no checkout (concept §3
  "derivado de schema/código"). As strings de timestamp são
  `datetime.isoformat()` de datas tz-aware UTC (ex.
  `"2024-01-02T00:00:00+00:00"`), a convenção do 4.3.
- Tolerâncias numéricas declaradas no módulo de teste (ADR 0.0.0021);
  igualdade de VO (`==`) quando o teste compara com a chamada direta ao
  serviço (A5).

### Estrutura de pastas afetada

```
src/financial_forecasting/
├── composition_root.py                                   # MODIFICADO (12): RefreshGold + _LazyArchMcs
├── shared/
│   ├── domain/services/path_identifier.py                # NOVO (02)
│   └── adapters/out/parquet/parquet_medallion_store.py   # MODIFICADO (02)
└── features/
    ├── analytics_store/adapters/out/parquet/
    │   └── parquet_analytics_repository.py               # MODIFICADO (11): docstring cita SilverTableReader
    └── evaluation/
        ├── domain/
        │   ├── value_objects/
        │   │   ├── paired_loss_series.py                 # MODIFICADO (01): MIN_MODELS público
        │   │   ├── bootstrap_indices.py                  # MODIFICADO (01): validate_bootstrap_parameters
        │   │   ├── forecast_record.py                    # NOVO (03)
        │   │   ├── cohort_run.py                         # NOVO (03)
        │   │   ├── realized_returns.py                   # NOVO (03)
        │   │   ├── assembled_cohort.py                   # NOVO (03)
        │   │   ├── quality_check_result.py               # NOVO (05)
        │   │   └── block_estimate.py                     # NOVO (05)
        │   └── services/
        │       ├── paired_pinball_losses.py              # MODIFICADO (01): importa MIN_MODELS
        │       ├── model_confidence_set.py               # MODIFICADO (01): validate_mcs_reps
        │       ├── series_assembly.py                    # NOVO (04)
        │       ├── horizon_reports.py                    # NOVO (06)
        │       ├── gold_build_order.py                   # NOVO (06)
        │       └── quality_checks/                       # NOVO (05)
        │           ├── __init__.py
        │           ├── registry.py
        │           ├── alignment_check.py
        │           ├── statistical_preconditions_check.py
        │           ├── degeneracy_check.py
        │           └── realized_provenance_check.py
        ├── application/
        │   ├── dtos/__init__.py                          # NOVO (07)
        │   ├── dtos/refresh_gold.py                      # NOVO (07)
        │   ├── ports/out/gold_store.py                   # NOVO (07)
        │   ├── ports/out/gold_builder.py                 # NOVO (09)
        │   ├── ports/out/silver_table_reader.py          # NOVO (11)
        │   └── use_cases/{__init__.py, refresh_gold.py}  # NOVO (11)
        └── adapters/out/duckdb/
            ├── __init__.py                               # NOVO (08)
            ├── parquet_gold_store.py                     # NOVO (08)
            └── gold_builders/                            # NOVO (10)
                ├── __init__.py
                ├── quality_checks.py
                ├── metrics_by_run.py
                ├── calibration_table.py
                ├── dm_results.py
                └── mcs_results.py
tests/
├── architecture/test_unit_evaluation_purity.py           # MODIFICADO (03): rglob
├── architecture/test_import_contracts.py                 # MODIFICADO (04): caso da aresta nova
├── architecture/test_port_coverage_gate.py               # MODIFICADO (07, 08, 09, 10)
├── unit/shared/domain/test_path_identifier.py            # NOVO (02)
├── unit/shared/test_composition_root.py                  # MODIFICADO (12)
├── unit/features/evaluation/
│   ├── test_paired_loss_series.py                        # MODIFICADO (01): só acréscimos
│   ├── test_paired_pinball_losses.py                     # MODIFICADO (01): só acréscimos
│   ├── test_bootstrap_indices.py                         # MODIFICADO (01): só acréscimos
│   ├── test_mcs_vs_arch.py                               # MODIFICADO (01): só acréscimos
│   └── gold/
│       ├── __init__.py                                   # NOVO (03)
│       ├── conftest.py                                   # NOVO (04): fábrica de cohort sintético
│       ├── test_gold_value_objects.py                    # NOVO (03)
│       ├── test_series_assembly.py                       # NOVO (04)
│       ├── test_quality_checks.py                        # NOVO (05)
│       ├── test_horizon_reports.py                       # NOVO (06)
│       ├── test_builder_explicit_deps.py                 # NOVO (06)
│       ├── test_refresh_gold_dtos.py                     # NOVO (07)
│       └── test_refresh_gold_use_case.py                 # NOVO (11)
├── fakes/shared/in_memory_medallion_store.py             # MODIFICADO (02)
├── fakes/features/evaluation/
│   ├── in_memory_gold_store.py                           # NOVO (07)
│   ├── fake_gold_builder.py                              # NOVO (09)
│   └── fake_silver_table_reader.py                       # NOVO (11)
├── contract/features/evaluation/
│   ├── test_gold_store_contract.py                       # NOVO (07), MODIFICADO (08)
│   ├── _gold_inputs.py                                   # NOVO (09)
│   ├── test_gold_builder_contract.py                     # NOVO (09), MODIFICADO (10)
│   └── test_silver_table_reader_contract.py              # NOVO (11)
└── integration/features/evaluation/test_refresh_gold.py  # NOVO (12)
.importlinter                                             # MODIFICADO (04)
scripts/arch_baseline.toml                                # MODIFICADO (07, 08, 09, 10)
docs/LAYOUT.md                                            # MODIFICADO (04): §7, 22 arestas
docs/roadmap.md                                           # MODIFICADO (13)
```

Intocados por decisão: `pyproject.toml`, `uv.lock`, `concept.md`, ADRs
6.4.0001–0008, `src/**/modeling/**`, `src/**/feature_engineering/**`,
`src/**/market_data/**`, os schemas do `analytics_store`.

### Tabelas gold (colunas exatas — concept §9, ADR 6.4.0005/0007)

Toda linha carrega `asset` e `parent_sweep_id`; as quatro confirmatórias
carregam `preregistration_ref`. Tipos: `str`, `int`, `float`, `bool` ou
`None` (nunca NaN). `key` = grão (ordem das linhas).

| Tabela | `key` | Demais colunas |
|---|---|---|
| `gold_quality_checks` | `check, kind, horizon, model, seed` | `asset, parent_sweep_id, severity, outcome, occurrences, value, detail` |
| `gold_metrics_by_run` | `model, seed, horizon, sample, metric, level_low, level_high` | `asset, parent_sweep_id, preregistration_ref, value, label, n_points, first_target_timestamp, last_target_timestamp, degeneracy_tolerance` — `metric ∈ {pinball_grid_mean, pinball, crps_q, interval_score, interval_width, coverage_rate, picp, mpiw, degeneracy_rate, guardrail_applied_rate, coverage_n_evaluated}`; `label` = `CRPS_Q_LABEL`/`MPIW_LABEL` onde o relatório tem rótulo |
| `gold_calibration_table` | `model, seed, horizon, sample, kind, level_low, level_high, includes_degenerate, dgt_offset, dgt_step, band_level` | `asset, parent_sweep_id, preregistration_ref, n_points, first_target_timestamp, last_target_timestamp, violation_rate, tolerance, degeneracy_rate, min_violations, n_observed, n_violations, n00, n01, n10, n11, kupiec_pof, kupiec_pof_p_value, lr_uc, p_uc, lr_ind, p_ind, lr_cc, p_cc, independence_status, independence_descriptive, wilson_applicable, wilson_estimate, wilson_lower, wilson_upper, wilson_contains_nominal, serial_dependence_warning, var_level, var_label` |
| `gold_dm_results` | `horizon, variance_estimator, candidate, comparator` | `asset, parent_sweep_id, preregistration_ref, n_points, common_first_target_timestamp, common_last_target_timestamp, mean_differential, long_run_variance, statistic, degrees_of_freedom, p_value, horizon_used, fallback_applied, adjusted_p_value, rejected, alpha` |
| `gold_mcs_results` | `horizon, scheme, model` | `asset, parent_sweep_id, preregistration_ref, elimination_rank, step_p_value, mcs_p_value, included, alpha, statistic, reps, seed, block_size, generator, n_points, max_block_estimate, block_estimates` (`block_estimates` = `"a|b=<valor>;…"` na ordem de `model_pairs()`) |

### Rastreabilidade — concept §11 (critérios A*) → Tasks

Notação dos checks: `arquivo::token` — ver "Tokens de nome de teste" acima;
`U` = `tests/unit/features/evaluation/gold/`, `K` =
`tests/contract/features/evaluation/`, `I` =
`tests/integration/features/evaluation/`.

| # | Critério de aceitação (concept §11) | Tasks | Check objetivo |
|---|---|---|---|
| A1 | `gold_build_order`: mesma ordem para qualquer registro; `ValueError` em duplicata, ciclo, dependência desconhecida, auto-dependência; `RefreshGold` com grafo inválido não chama leitura | 06, 11 | `U/test_builder_explicit_deps.py::order_invariant`, `::duplicate_name`, `::cycle_raises`, `::unknown_dependency`, `::self_dependency`; `U/test_refresh_gold_use_case.py::graph_checked_before_read` |
| A2 | `SeriesAssembly`: um achado por violação de I3–I10 (um teste por regra) e prefixo dentro do déficit aceito com T e primeiro/último corretos | 04 | tokens de I3–I10 em `U/test_series_assembly.py` (matriz I*) + `::prefix_within_deficit`, `::common_intersection` |
| A3 | Sem achado, séries reproduzem ponto a ponto `value_guardrail`/`value_raw`/`guardrail_applied` e o `target_return` | 04, 11 | `U/test_series_assembly.py::reproduces_persisted_values`, `::realized_joined`; `U/test_refresh_gold_use_case.py::guardrail_int_to_bool` |
| A4 | Registry: ordem; `alignment_check` FAIL agregado / PASS por horizonte; `statistical_preconditions` FAIL (k < 2, diferencial constante, série inválida, b̂_sb indefinido) e SKIPPED; `degeneracy_check` REPORTED (1.0 no baseline pontual) e SKIPPED; `realized_provenance` REPORTED; fábrica e backend nunca recebem entrada inválida | 05, 11 | `U/test_quality_checks.py` (tokens da Task 05); `U/test_refresh_gold_use_case.py::factory_never_short`, `::backend_never_invalid` |
| A5 | `HorizonReports` = chamadas diretas (igualdade de VO), duas amostras, com/sem lacunas, uma banda por nível, um DM por estimador, DGT só em h > 1 | 06 | `U/test_horizon_reports.py` (tokens da Task 06) |
| A6 | `RefreshGold` com fakes: ordem antes da leitura; identificador inválido antes de caminho; MCS com bloco da regra e `reps`/`seed`/esquemas; `ArithmeticError` → FAIL (outra exceção propaga); bloqueado publica só `runs_when_blocked` + manifesto `BLOCKED` e devolve `FailedCheck`s; exceção antes do `publish` não chama o store; log por etapa | 11 | `U/test_refresh_gold_use_case.py` (tokens da Task 11) |
| A7 | `RefreshParameters` sem default; inválidos erguem na construção pela mensagem do dono (`validate_mcs_reps`, `validate_bootstrap_parameters`…); 6.2 com as mesmas mensagens; `MIN_MODELS` do VO único; `preregistration_ref` no manifesto e nas linhas confirmatórias | 01, 07, 10, 11 | Task 01: pytest dos arquivos da 6.2 + diff só de acréscimos + greps; `U/test_refresh_gold_dtos.py::parameters_no_default`, `::parameters_owner_messages`; `K/test_gold_builder_contract.py::confirmatory_rows_carry_prereg`; `U/test_refresh_gold_use_case.py::manifest_carries_parameters` |
| A8 | `SilverTableReader`, `GoldBuilder`, `GoldStore` com fake e contrato `[fake, real]` (superconjunto nas duas pernas; cinco builders; `ParquetGoldStore`); `check_port_coverage` sem entrada nova no baseline | 07–11 | bloco Container do §3 (três suítes, zero `SKIPPED`, ids de cada perna) + Host (baseline sem `GoldStore`/`GoldBuilder`/`SilverTableReader`) |
| A9 | `ParquetGoldStore`: falha antes da troca preserva `current/`; sobras removidas; manifesto por último; falha ao apagar `.previous/` → aviso e sucesso | 08 | `K/test_gold_store_contract.py::real_failure_keeps_current`, `::real_leftovers_removed`, `::real_manifest_written_last`, `::real_previous_delete_warns` |
| A10 | E2E no mesmo `data_root`, pelo `RefreshGold` de `wire_dependencies`: COMPLETED com cinco tabelas por DuckDB; rerun sem apagar → linhas idênticas (NaN = NaN) e manifesto igual salvo timestamps; lacuna interior → BLOCKED substitui; outro `parent_sweep_id` intocado | 12 | `I/test_refresh_gold.py` (tokens da Task 12), zero `SKIPPED` |
| A11 | `lint-imports` verde com uma aresta nova; nada de `modeling`/`feature_engineering`/application do `analytics_store` em `evaluation`; `duckdb`/`pyarrow`/`pandas` só em `adapters/out/duckdb/` | 04 (aresta + caso), todas (T1) | `uv run lint-imports` + `tests/architecture/test_import_contracts.py -k evaluation-new-module-imports-quantile-forecast` + greps Host do §3 |
| A12 | Custo do MCS medido (T ≈ 10³, `MIN_MCS_REPS`) e registrado em `[decision]` | §1 (medido), 12 (re-medido) | tabela do §1 + Host do §3: exatamente uma entrada `[decision] Task 12 — custo do MCS` em §7 |
| A13 | Roadmap §Stage 6.4 conforme D9 (sem "disposições") | 13 | greps por seção da Task 13 (falham no `develop` de hoje) |
| A14 | `make check` verde | todas; §3 | bloco Container do §3 (inclui cobertura por arquivo) |

### Rastreabilidade — invariantes (I*) e casos de erro (C*) → Tasks

| # | Regra (concept §5/§6) | Tasks | Check objetivo |
|---|---|---|---|
| I1 | Por horizonte; horizontes do comando | 04, 06, 11 | `U/test_series_assembly.py::horizons_from_command`; `U/test_horizon_reports.py::horizon_mismatch_raises`; `U/test_refresh_gold_use_case.py::mcs_reps_seed_schemes` |
| I2 | Um dono por regra; `alignment_check` só traduz | 04, 05 | `U/test_quality_checks.py::alignment_translates_report`; `U/test_series_assembly.py::all_findings_reported` |
| I3 | Split `test`; `model` = `model_version`; um `feature_set_name`; uma `config_signature` por modelo; run órfão; `model_version` divergente | 04 | `U/test_series_assembly.py::split_non_test_ignored`, `::feature_sets_multiple`, `::config_signatures_multiple`, `::orphan_run`, `::model_version_mismatch` |
| I4 | Uma observação por ponto (duplicata = achado) | 04 | `U/test_series_assembly.py::duplicate_point` |
| I5 | `decision_idx` e rótulo de horizonte no índice do `RealizedReturns` | 04 | `U/test_series_assembly.py::decision_index_mismatch`, `::horizon_label_mismatch` |
| I6 | Grade completa e igual; `guardrail_applied` igual nos níveis; `QuantileForecast` com valores persistidos | 04, 11 | `U/test_series_assembly.py::grid_incomplete`, `::grid_divergent`, `::guardrail_flag_mismatch`, `::reproduces_persisted_values`, `::quantile_forecast_not_from_raw`; `U/test_refresh_gold_use_case.py::guardrail_int_to_bool` |
| I7 | Realizado lido, presente em todo `target` | 04, 11 | `U/test_series_assembly.py::realized_missing`, `::realized_joined`; `U/test_refresh_gold_use_case.py::realized_read_once` |
| I8 | Contiguidade; sufixo comum; prefixo ≤ déficit; interseção | 04 | `U/test_series_assembly.py::interior_gap`, `::truncated_suffix`, `::prefix_over_deficit`, `::prefix_within_deficit`, `::common_intersection` |
| I9 | Cobertura de fold, seed × horizonte, horizonte pedido, candidato | 04 | `U/test_series_assembly.py::fold_coverage`, `::seed_horizon_coverage`, `::horizon_missing`, `::required_model_missing` |
| I10 | T mínimo pelos donos | 04 | `U/test_series_assembly.py::common_too_short` |
| I11 | Pré-condições no domínio antes da fábrica/backend; só `ArithmeticError` vira indefinido | 05, 11 | `U/test_quality_checks.py::preconditions_k_below_min` (FAIL `insufficient_models`), `::preconditions_constant_differential` (FAIL `constant_differential`), `::preconditions_invalid_series`, `::preconditions_undefined_estimate`, `::step_delegates_to_owners`; `U/test_refresh_gold_use_case.py::arithmetic_error_fails_precondition`, `::other_backend_error_propagates`, `::factory_never_short`, `::backend_never_invalid` |
| I12 | S seeds pela fábrica da 6.2 (média de L_t) | 06, 11 | `U/test_horizon_reports.py::seed_mean_by_factory` (o relatório usa a série da fábrica); `U/test_refresh_gold_use_case.py::seeds_averaged_by_factory` (espião: a fábrica recebe as S séries `common` por modelo) |
| I13 | Degeneração por (modelo, seed, h) na `model_full`; SKIPPED se a montagem falhou | 05 | `U/test_quality_checks.py::degeneracy_reported`, `::degeneracy_uses_model_full`, `::degeneracy_point_baseline`, `::degeneracy_skipped` |
| I14 | Ordem por `gold_build_order`; builders sem estado compartilhado; `BLOCKED` → só `runs_when_blocked` | 06, 09, 11 | `U/test_builder_explicit_deps.py::dependencies_first`; `K/test_gold_builder_contract.py::builder_pure_mapping`; `U/test_refresh_gold_use_case.py::blocked_publishes_checks_only` |
| I15 | Efeitos colaterais depois dos guardas; nada gravado antes do `publish` | 11 | `U/test_refresh_gold_use_case.py::effects_order`, `::exception_before_publish` |
| I16 | Reconstrução: mesmas entradas → mesmas linhas; só timestamps do manifesto mudam | 11, 12 | `U/test_refresh_gold_use_case.py::rerun_identical`; `I/test_refresh_gold.py::e2e_rerun_identical`, `::e2e_manifest_same_but_timestamps` |
| I17 | Autodescrição (`asset`, `parent_sweep_id`, amostra, T/n, parâmetros; `preregistration_ref` só nas confirmatórias) | 07, 10, 11 | `U/test_refresh_gold_dtos.py::manifest_mapping`; `K/test_gold_builder_contract.py::rows_carry_partition`, `::confirmatory_rows_carry_prereg`, `::quality_rows_no_prereg`; `U/test_refresh_gold_use_case.py::manifest_carries_parameters` |
| C1 | Grafo inválido → `ValueError` antes de qualquer leitura | 06, 11 | `U/test_builder_explicit_deps.py::duplicate_name`, `::cycle_raises`, `::unknown_dependency`, `::self_dependency`; `U/test_refresh_gold_use_case.py::graph_checked_before_read` |
| C2 | Parâmetro inválido → `ValueError` na construção pelo validador dono | 01, 07 | `U/test_refresh_gold_dtos.py::parameters_owner_messages`, `::parameters_no_default`, `::tuple_empty_or_repeated`, `::preregistration_ref_required`; Task 01 (tokens `mcs_reps_validator`, `bootstrap_parameters_invalid`) |
| C3 | Identificador inválido antes de caminho | 02, 07, 11 | `tests/unit/shared/domain/test_path_identifier.py::identifier_rejects`; `U/test_refresh_gold_dtos.py::identifier_rule`; `U/test_refresh_gold_use_case.py::identifier_before_path`; `K/test_gold_store_contract.py::real_rejects_bad_identifier` |
| C4 | Cohort vazio ou dataset vazio → `ValueError`, nada publicado | 11 | `U/test_refresh_gold_use_case.py::cohort_empty_raises`, `::dataset_empty_raises` |
| C5 | Alinhamento violado → BLOCKED, só `gold_quality_checks` | 11, 12 | `U/test_refresh_gold_use_case.py::blocked_publishes_checks_only`, `::blocked_result_failed_checks`; `I/test_refresh_gold.py::e2e_blocked_replaces` |
| C6 | Pré-condição estatística → BLOCKED com causa | 05, 11 | `U/test_quality_checks.py::preconditions_k_below_min`, `::preconditions_constant_differential`, `::preconditions_invalid_series`, `::preconditions_undefined_estimate`; `U/test_refresh_gold_use_case.py::arithmetic_error_fails_precondition`, `::backend_never_invalid` |
| C7 | Erro de programação propaga; nada publicado | 11 | `U/test_refresh_gold_use_case.py::other_backend_error_propagates`, `::exception_before_publish` |
| C8 | Série 100 % degenerada → "não aplicável" + 1.0 | 05, 06 | `U/test_quality_checks.py::degeneracy_point_baseline`; `U/test_horizon_reports.py::degenerate_not_applicable` |
| C9 | Falha de publicação → propaga; `current/` intacto; próximo refresh limpa | 08 | `K/test_gold_store_contract.py::real_failure_keeps_current`, `::real_leftovers_removed`, `::real_previous_delete_warns` |

## 2. Tasks

> Faixa desta Stage: **13 Tasks** (estimativa do concept: 12 — exceções
> declaradas no §1). Blocos de verificação conforme a convenção
> **Container/Host** do §1.

### Task 01 — Validadores públicos da 6.2: `MIN_MODELS` no VO, `validate_bootstrap_parameters`, `validate_mcs_reps`

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/paired_loss_series.py`
  - `src/financial_forecasting/features/evaluation/domain/services/paired_pinball_losses.py`
  - `src/financial_forecasting/features/evaluation/domain/value_objects/bootstrap_indices.py`
  - `src/financial_forecasting/features/evaluation/domain/services/model_confidence_set.py`
  - `tests/unit/features/evaluation/{test_paired_loss_series.py, test_paired_pinball_losses.py, test_bootstrap_indices.py, test_mcs_vs_arch.py}` — **só acréscimos**
- **Arquivos a criar:** nenhum.
- **O que fazer (concept D9, I11, C2, A7; ADR 6.4.0002 item 4, ADR 6.4.0006 item 2):**
  - `paired_loss_series.py`: `_MIN_MODELS` → `MIN_MODELS: Final = 2` público
    (o VO é o primeiro dono); a mensagem do `__post_init__` não muda.
  - `paired_pinball_losses.py`: apaga a cópia `_MIN_MODELS` e importa
    `MIN_MODELS` do VO (direção serviço → VO); a mensagem `"k >= 2 models"`
    não muda.
  - `bootstrap_indices.py`: `validate_bootstrap_parameters(*, reps: int,
    seed: int) -> None` público = as duas linhas `_check_int("reps", reps, 1)`
    e `_check_int("seed", seed, 0)`; `validate_bootstrap_request` passa a
    chamá-lo no mesmo ponto da sequência (depois de `n_obs`/`block_size`) —
    mesmas mensagens, mesma ordem.
  - `model_confidence_set.py`: `validate_mcs_reps(reps: int) -> None`
    público (`reps < MIN_MCS_REPS` → `ValueError` com a mensagem do §1); o
    `McsReport.__post_init__` e o `ModelConfidenceSet.evaluate` consomem-no
    no lugar das duas comparações inline.
- **Critério de aceite (A7, C2):** todos os testes existentes dos quatro
  arquivos e de `tests/contract/features/evaluation/test_mcs_backend_contract.py`
  verdes **sem alteração** (o diff dos quatro arquivos de teste só tem linhas
  `+`); novos testes: `MIN_MODELS == 2` e é o mesmo objeto no VO e na fábrica
  (`paired_pinball_losses_module.MIN_MODELS is paired_loss_series_module.MIN_MODELS`,
  e `not hasattr(paired_pinball_losses_module, "_MIN_MODELS")`);
  `validate_bootstrap_parameters` ergue em `reps` 0/`True`/`1.5`, `seed`
  −1/`True`, e aceita `reps=1, seed=0`; `validate_bootstrap_request` delega
  (monkeypatch de `bootstrap_indices_module.validate_bootstrap_parameters`
  por um sentinela que ergue → o pedido ergue o sentinela);
  `validate_mcs_reps(999)` ergue com as duas substrings antigas e `1000`
  passa; o `McsReport(...)` e o `evaluate` erguem o sentinela quando
  `model_confidence_set_module.validate_mcs_reps` é trocado (dono único).
- **Tokens:** `test_paired_loss_series.py`: `min_models_public`;
  `test_paired_pinball_losses.py`: `factory_imports_min_models`;
  `test_bootstrap_indices.py`: `bootstrap_parameters_invalid`,
  `bootstrap_parameters_accepts`, `bootstrap_request_delegates`;
  `test_mcs_vs_arch.py`: `mcs_reps_validator`, `mcs_reps_single_owner`.
- **Verificação (T1) — Container:**
  ```bash
  U=tests/unit/features/evaluation
  D=src/financial_forecasting/features/evaluation/domain
  uv run pytest $U/test_paired_loss_series.py $U/test_paired_pinball_losses.py $U/test_bootstrap_indices.py $U/test_mcs_vs_arch.py tests/contract/features/evaluation/test_mcs_backend_contract.py -v
  test -s $D/services/paired_pinball_losses.py
  test -s $D/value_objects/paired_loss_series.py
  if grep -n "_MIN_MODELS" $D/services/paired_pinball_losses.py $D/value_objects/paired_loss_series.py; then echo "FAIL: cópia privada de MIN_MODELS"; exit 1; fi
  test -s $D/services/model_confidence_set.py
  test "$(grep -c "< MIN_MCS_REPS" $D/services/model_confidence_set.py)" -eq 1
  d=$(mktemp)
  base=$(git merge-base origin/develop HEAD)
  git diff "$base" -- $U/test_paired_loss_series.py $U/test_paired_pinball_losses.py $U/test_bootstrap_indices.py $U/test_mcs_vs_arch.py > "$d"
  test -s "$d"
  if grep -nE '^-([^-]|$)' "$d"; then echo "FAIL: teste existente da 6.2 alterado"; exit 1; fi
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `refactor(evaluation): MIN_MODELS no VO e validadores de reps/seed públicos da 6.2 [6.4/task-01]`

---

### Task 02 — Regra de identificador de caminho com dono único em `shared/domain`

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/domain/services/path_identifier.py`
  - `tests/unit/shared/domain/test_path_identifier.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/shared/adapters/out/parquet/parquet_medallion_store.py`
  - `tests/fakes/shared/in_memory_medallion_store.py`
- **O que fazer (concept C3; ADR 6.4.0005 item 1; decisão de detalhe do §1):**
  `PATH_IDENTIFIER_PATTERN: Final = re.compile(r"^[A-Za-z0-9._-]+$")` e
  `validate_path_identifier(value: object, *, field: str) -> None` (não-`str`
  ou `not PATH_IDENTIFIER_PATTERN.fullmatch(value)` — `fullmatch`, nunca
  `match`/`search`, porque `$` casa antes de um `\n` final — →
  `ValueError(f"{field} must match {PATH_IDENTIFIER_PATTERN.pattern!r}; got {value!r}")`). O `_validate_read_only_filters` do adapter
  e o `_read_read_only` do fake apagam os seus `_READ_ONLY_ASSET_PATTERN` e
  chamam `validate_path_identifier(str(asset_val), field=f"read-only pair
  ({layer!r}, {table!r}) asset filter")` — mensagem byte-idêntica à de hoje.
  Docstring cita os consumidores (store, fake, `GoldPartition` da 6.4).
- **Critério de aceite (C3):** aceita `AAPL` e `sweep-01.a_b`; rejeita `""`,
  `a/b`, `a\b`, `a b`, `"AAPL\n"` e `"a\n"` (newline final), `ç`, `None` e
  `3`, com a mensagem nomeando o campo;
  `tests/contract/shared/test_medallion_store_contract.py` verde sem
  alteração; o padrão é compilado uma única vez em `src/` e `tests/fakes/`.
- **Tokens:** `test_path_identifier.py`: `identifier_accepts`,
  `identifier_rejects`, `identifier_message_names_field`.
- **Verificação (T1 = `check-block`, toca `shared`) — Container:**
  ```bash
  uv run pytest tests/unit/shared/domain/test_path_identifier.py tests/contract/shared/test_medallion_store_contract.py -v
  f=$(mktemp)
  grep -rn 'A-Za-z0-9._-' src/ tests/fakes/ > "$f"
  test -s "$f"
  test "$(grep -c 're.compile' "$f")" -eq 1
  grep -q "shared/domain/services/path_identifier.py" "$f"
  make check-block
  ```
- **Commit sugerido:** `refactor(shared): identificador de caminho com regra única em shared/domain [6.4/task-02]`

---

### Task 03 — VOs de entrada e da montagem; gate de pureza cobre subpacotes

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/forecast_record.py`
  - `src/financial_forecasting/features/evaluation/domain/value_objects/cohort_run.py`
  - `src/financial_forecasting/features/evaluation/domain/value_objects/realized_returns.py`
  - `src/financial_forecasting/features/evaluation/domain/value_objects/assembled_cohort.py`
  - `tests/unit/features/evaluation/gold/__init__.py`
  - `tests/unit/features/evaluation/gold/test_gold_value_objects.py`
- **Arquivos a modificar:**
  - `tests/architecture/test_unit_evaluation_purity.py` — `_UNIT_DIR.rglob("*.py")`
    e um caso que grava um arquivo impuro num subdiretório de `tmp_path` e
    prova que a varredura recursiva o acusa.
- **O que fazer (concept §4 "Domínio", D1; ADR 6.4.0003, 6.4.0004):** VOs
  frozen, stdlib-only, validação no `__post_init__` com mensagens que nomeiam
  o campo, reusando os helpers do slice (`validate_horizon`,
  `check_strictly_increasing`, `is_finite_number` — todos de
  `value_objects/`):
  - `ForecastRecord` — campos do concept §4; `run_id`/`model`/`split`/
    timestamps `str` não-vazias; `seed` `int` não-`bool` ou `None`; `fold`
    `str` ou `None`; `horizon` por `validate_horizon`; `decision_idx` `int`
    ≥ 0; `quantile_level` só `float` finito não-`bool` (`is_finite_number`,
    helper de `value_objects/`; a validade da grade é da `CoverageSeries`/
    `QuantileForecast` — o VO não importa `validate_rate` de `services/`,
    direção VO → serviço que o slice não tem); `guardrail_applied` `bool`
    (`type(v) is bool`); `value_raw`/`value_guardrail` `float` (a finitude é
    da `CoverageSeries`).
  - `CohortRun` — `run_id`, `model`, `feature_set_name`, `config_signature`
    `str` não-vazias; `seed`/`fold` como acima.
  - `RealizedReturns` — `timestamps` estritamente crescentes (≥ 1),
    `returns` finitos, mesmo tamanho; `index_of(ts) -> int | None`
    (dicionário construído uma vez), `realized_at(ts) -> float` (ausente →
    `ValueError`); resumo: `n_sessions`, `returns_fsum` (`math.fsum`),
    `first_timestamp`, `last_timestamp`.
  - `assembled_cohort.py`: `AlignmentKind(StrEnum)` com os 19 valores
    `multiple_feature_sets`, `multiple_config_signatures`, `orphan_run`,
    `model_version_mismatch`, `duplicate_point`, `decision_index_mismatch`,
    `horizon_label_mismatch`, `grid_incomplete`, `grid_divergent`,
    `guardrail_flag_mismatch`, `realized_missing`, `interior_gap`,
    `truncated_suffix`, `prefix_over_deficit`, `fold_coverage`,
    `seed_horizon_coverage`, `horizon_missing`, `required_model_missing`,
    `common_sample_too_short`; `AlignmentFinding(kind, horizon, model, seed,
    detail)`; `AlignmentReport(findings, common_points)` (`common_points`
    com horizontes estritamente crescentes, T ≥ 1); `HorizonSamples`
    (campos do concept §4 + `levels`): `models` ordenados e únicos, chaves de
    `seeds`/`full`/`common` = `models`, S séries por modelo alinhadas às
    seeds, toda série com `horizon` do objeto e `levels` iguais, toda série
    `common` com `n_points == n_common` e primeiro/último timestamp iguais aos
    declarados; `AssembledCohort(alignment, horizons)`: `horizons` vazio ⇔
    `alignment.findings` não-vazio, horizontes estritamente crescentes.
- **Critério de aceite:** um caso parametrizado por ramo de validação de cada
  VO; `index_of`/`realized_at` (presente, ausente); resumo com
  `math.fsum` exato de `[0.1]*10` (igual a `1.0`, onde `sum` não é);
  `AssembledCohort` com achado **e** horizontes ergue, sem achado e sem
  horizontes ergue; o gate de pureza verde e recursivo.
- **Tokens:** `gold/test_gold_value_objects.py`: `record_invalid`,
  `cohort_run_invalid`, `realized_invalid`, `realized_lookup`,
  `realized_summary`, `findings_xor_horizons`, `samples_incoherent`,
  `alignment_report_invalid`, `finding_invalid`;
  `tests/architecture/test_unit_evaluation_purity.py`:
  `purity_scans_subpackages`.
- **Verificação (T3 — toca `tests/architecture/`) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/gold/test_gold_value_objects.py tests/architecture/test_unit_evaluation_purity.py -v
  test -s tests/architecture/test_unit_evaluation_purity.py
  grep -q 'rglob("\*.py")' tests/architecture/test_unit_evaluation_purity.py
  make check
  ```
- **Commit sugerido:** `feat(evaluation): VOs de entrada e da montagem do gold com gate de pureza recursivo [6.4/task-03]`

> **Checkpoint C (T2) após esta Task:** `make check-block` (Container).

---

### Task 04 — `SeriesAssembly`: regras I3–I10, duas amostras e a aresta declarada

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/series_assembly.py`
  - `tests/unit/features/evaluation/gold/conftest.py`
  - `tests/unit/features/evaluation/gold/test_series_assembly.py`
- **Arquivos a modificar:**
  - `.importlinter` — no `bc-independence`, a exceção nomeada
    `financial_forecasting.features.evaluation.domain.services.series_assembly -> financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast`
    com comentário (aresta de DADOS, ADR 6.4.0003 item 3 / 6.4.0004 item 5,
    ADR 0.0.0053 item 3); o cabeçalho do contrato passa de "(21 hoje)" para
    "(22 hoje)" e cita as **duas** arestas de `evaluation`.
  - `tests/architecture/test_import_contracts.py` — caso real
    `bc-independence:evaluation-new-module-imports-quantile-forecast`: um
    módulo novo `features/evaluation/domain/services/_arch_audit_taint_qf.py`
    importando `QuantileForecast` deixa o contrato `broken` (prova que a
    exceção nova é do módulo, não do slice).
  - `docs/LAYOUT.md` §7 "Perímetro do gate hoje": 21 → **22** arestas; a
    frase da aresta de `evaluation` passa a nomear as duas
    (`coverage_series` e `series_assembly`, Stage 6.4 / ADR 6.4.0004).
- **O que fazer (concept §4 `SeriesAssembly`, I1–I10, D1, D2; ADR 6.4.0003):**
  `SeriesAssembly.assemble(records, runs, realized, *, horizons,
  window_deficits, required_models) -> AssembledCohort` (assinatura literal
  do concept). Sequência (cada violação vira `AlignmentFinding`, nunca
  exceção; todos os achados são coletados antes de devolver):
  1. valida as entradas estruturais (`horizons` não-vazio, estritamente
     crescente, `validate_horizon`; `window_deficits` int não-`bool` ≥ 0 —
     `ValueError`, é erro de chamada, não de dado);
  2. descarta `split != "test"` (sem achado);
  3. identidade (I3): `feature_set_name` distintos nos `runs` > 1;
     `config_signature` distintas por modelo > 1; run sem registro `test`
     (órfão); `record.model` ≠ `runs[run_id].model`;
  4. só os horizontes pedidos; agrupa por (modelo, seed, h,
     `target_timestamp`) → nível → registro; nível repetido = duplicata (I4,
     nenhuma escolha — D2);
  5. por ponto (I5, I7): `realized.index_of(decision_timestamp) !=
     decision_idx` → `decision_index_mismatch`; `target` fora do índice →
     `realized_missing`; senão `index(target) − index(decision) != h` →
     `horizon_label_mismatch`;
  6. grade (I6): grade do modelo no horizonte = união dos níveis vistos;
     ponto sem algum nível → `grid_incomplete`; grades de modelos diferentes
     no mesmo horizonte → `grid_divergent`; `guardrail_applied` diferente
     entre níveis do ponto → `guardrail_flag_mismatch`;
  7. cobertura (I9): folds de cada (modelo, seed) ≠ folds do cohort →
     `fold_coverage`; (modelo, seed) sem ponto num horizonte pedido →
     `seed_horizon_coverage`; horizonte pedido sem ponto nenhum →
     `horizon_missing`; `required_models − modelos do cohort` →
     `required_model_missing`;
  8. contiguidade (I8), nos índices de sessão do `target`: buraco interno →
     `interior_gap`; último índice ≠ o maior último do horizonte →
     `truncated_suffix`; primeiro índice − menor primeiro do horizonte >
     `window_deficits.get(model, 0)` → `prefix_over_deficit`;
  9. amostra comum = interseção dos intervalos; T mínimo (I10) pelos donos:
     `check_points(T, h)` erguendo ou `T < MIN_BLOCK_LENGTH_OBS` →
     `common_sample_too_short`; `common_points` registra (h, T);
  10. sem achado: por (modelo, seed) (modelos e seeds ordenados; `None`
      antes de int) uma `CoverageSeries` `full` (todos os pontos da série) e
      uma `common` (fatia da interseção), com `QuantileForecast(levels=grade,
      raw_values=…, guardrail_values=…, guardrail_applied=…)` construído
      **direto** dos valores persistidos (nunca `from_raw`) e `realized` =
      `realized_at(target)`.
  Achados em ordem determinística (ordem do enum, depois horizonte, modelo,
  seed). O `gold/conftest.py` traz a fábrica pura `make_cohort(...)` (modelos,
  seeds, folds, horizontes, grade, sessões, prefixos) que devolve `records`,
  `runs` e `realized` coerentes, e mutadores nomeados por regra (remover
  ponto, duplicar nível, trocar `decision_idx`…) usados também pelas Tasks
  05, 06 e 11.
- **Critério de aceite (A2, A3):** **um teste por regra** (19 tipos + split
  ignorado), cada um partindo de um cohort válido e aplicando uma violação só,
  com asserção do `kind` e do escopo (horizonte/modelo/seed); prefixo do
  candidato 2 sessões atrás com déficit 3 → sem achado, `n_common`,
  `common_first/last_target_timestamp` e T de `common_points` corretos, e as
  séries `full` do candidato mais curtas que as do GBM; sem achado, cada
  ponto de cada série reproduz `value_raw`/`value_guardrail`/
  `guardrail_applied` e o `target_return` da fixture (A3) — a fixture tem um
  ponto com `value_guardrail ≠ sorted(value_raw)` e `guardrail_applied`
  gravado diferente do que `from_raw` produziria, e a série guarda os
  persistidos; além disso um espião em `QuantileForecast.from_raw`
  (monkeypatch que ergue) prova que ele nunca é chamado; horizonte no
  silver e fora do comando é ignorado; com achado, `horizons == ()`; duas
  violações de tipos diferentes geram os dois achados; mesma entrada em ordem
  embaralhada → `AssembledCohort` igual; entrada estrutural inválida ergue;
  `lint-imports` verde com a aresta e o caso real `broken`.
- **Tokens:** `gold/test_series_assembly.py`: `split_non_test_ignored`,
  `feature_sets_multiple`, `config_signatures_multiple`, `orphan_run`,
  `model_version_mismatch`, `duplicate_point`, `decision_index_mismatch`,
  `horizon_label_mismatch`, `grid_incomplete`, `grid_divergent`,
  `guardrail_flag_mismatch`, `realized_missing`, `interior_gap`,
  `truncated_suffix`, `prefix_over_deficit`, `fold_coverage`,
  `seed_horizon_coverage`, `horizon_missing`, `required_model_missing`,
  `common_too_short`, `prefix_within_deficit`, `reproduces_persisted_values`,
  `quantile_forecast_not_from_raw`,
  `realized_joined`, `common_intersection`, `horizons_from_command`,
  `all_findings_reported`, `shuffled_input_same_result`,
  `invalid_call_raises`; `tests/architecture/test_import_contracts.py`: o id
  `evaluation-new-module-imports-quantile-forecast` (conferido por `-k` no
  bloco).
- **Verificação (T3 — `.importlinter` e `tests/architecture/`) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/gold/test_series_assembly.py -v
  f=$(mktemp)
  uv run pytest tests/architecture/test_import_contracts.py -v -k "evaluation-new-module-imports-quantile-forecast" | tee "$f"
  test -s "$f"
  grep -q "PASSED" "$f"
  uv run lint-imports
  test -s .importlinter
  grep -q "evaluation.domain.services.series_assembly -> financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast" .importlinter
  grep -q "(22 hoje)" .importlinter
  if grep -q "(21 hoje)" .importlinter; then echo "FAIL: contagem antiga no .importlinter"; exit 1; fi
  L=$(awk '/^## 7\./,/^## 8\./' docs/LAYOUT.md); test -n "$L"
  grep -q "22 arestas" <<<"$L"
  grep -q "series_assembly" <<<"$L"
  make check
  ```
- **Commit sugerido:** `feat(evaluation): SeriesAssembly dono das regras de alinhamento e das duas amostras [6.4/task-04]`

---

### Task 05 — `QualityCheckResult`, `QualityCheckRegistry` e os quatro checks (com o passo de pré-condições)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/quality_check_result.py`
  - `src/financial_forecasting/features/evaluation/domain/value_objects/block_estimate.py`
  - `src/financial_forecasting/features/evaluation/domain/services/quality_checks/{__init__.py, registry.py, alignment_check.py, statistical_preconditions_check.py, degeneracy_check.py, realized_provenance_check.py}`
  - `tests/unit/features/evaluation/gold/test_quality_checks.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4, D4, D6, I2, I11, I13, C6, C8; ADR 6.4.0002):**
  - `quality_check_result.py`: `CheckSeverity {ERROR, WARN}`, `CheckOutcome
    {PASS, FAIL, REPORTED, SKIPPED}` (`StrEnum`) e `QualityCheckResult`
    frozen com os campos do ADR item 2; coerência: `occurrences` int ≥ 1;
    `value` finito ou `None`; `ERROR` só com `PASS`/`FAIL`/`SKIPPED`,
    `WARN` só com `REPORTED`/`SKIPPED`; `check`/`kind`/`detail` `str`
    não-vazias.
  - `registry.py`: `QualityCheck` (Protocol: `name`, `severity`,
    `run(context) -> tuple[QualityCheckResult, ...]`),
    `QualityCheckContext` (VO: `assembled`, `paired: Mapping[int,
    PairedLossSeries]`, `block_estimates: Mapping[int, tuple[BlockEstimate,
    ...]]`, `tolerance`, `dataset_fingerprint: DatasetFingerprint`,
    `realized: RealizedReturns`), `QualityCheckRegistry(checks)` (nomes
    únicos; `run` na ordem registrada, concatenando; `is_blocking(results)`
    ⇔ algum ERROR/FAIL).
  - `alignment_check.py` (`alignment_check`, ERROR): traduz o
    `AlignmentReport` — um FAIL por (kind, horizonte, modelo, seed) com
    `occurrences` e o `detail` do primeiro achado; sem achado, um PASS por
    horizonte com T em `value` (de `common_points`). Não re-deriva nada.
  - `statistical_preconditions_check.py` (`statistical_preconditions`,
    ERROR): o passo de domínio (`models_suffice`, `block_request_defect`) e o
    check; `block_estimate.py` traz `UndefinedReason(StrEnum)
    {CONSTANT_DIFFERENTIAL = "constant_differential", INVALID_SERIES =
    "invalid_series", BACKEND_ARITHMETIC = "backend_arithmetic"}` e o VO
    `BlockEstimate(pair, value, reason, detail)` — exatamente um de `value`
    (finito ≥ 0) ou `reason`. O check: montagem
    falha → um SKIPPED; por horizonte, k < `MIN_MODELS` → FAIL
    `insufficient_models`; cada `BlockEstimate` indefinido → FAIL com `kind`
    = o valor do `UndefinedReason` (agregado por (kind, horizonte), detalhe
    nomeando o primeiro par e o motivo); senão PASS por horizonte.
  - `degeneracy_check.py` (`degeneracy_check`, WARN): montagem falha → um
    SKIPPED com o motivo; senão `DegeneracyGate.evaluate(series.full[i],
    tolerance)` por (modelo, seed, horizonte) → REPORTED com `rate`.
  - `realized_provenance_check.py` (`realized_provenance`, WARN): um
    REPORTED com `value = realized.returns_fsum` e `detail` com o
    `dataset_fingerprint.value`, `n_sessions`, primeira e última sessão.
- **Critério de aceite (A4):** registry roda na ordem registrada (checks de
  teste que anotam a chamada) e nome duplicado ergue; `is_blocking` só com
  ERROR+FAIL (WARN nunca bloqueia); um caso por ramo do
  `QualityCheckResult`/`BlockEstimate`; `alignment_check` sobre um
  `AlignmentReport` montado à mão com 3 achados do mesmo (kind, escopo) → 1
  linha com `occurrences == 3` e o primeiro `detail`, e PASS por horizonte com
  T; pré-condições: k = 1 → FAIL `insufficient_models`; diferencial
  constante → `block_request_defect` devolve `CONSTANT_DIFFERENTIAL` **e** o
  check, com o `BlockEstimate` correspondente no contexto, emite FAIL de
  `kind == "constant_differential"` agregado por horizonte (dois pares
  constantes no mesmo h → uma linha, `occurrences == 2`); série de diferencial
  com 10 pontos → `INVALID_SERIES` **e** FAIL `kind == "invalid_series"`;
  `BlockEstimate` `BACKEND_ARITHMETIC` → FAIL `kind == "backend_arithmetic"`;
  montagem falha → SKIPPED; o passo chama os
  donos (monkeypatch de `is_constant`/`validate_block_length_request` no
  módulo do check muda o resultado); degeneração REPORTED para toda (modelo,
  seed, h) com a taxa do `DegeneracyGate` na `full` — provado com uma série
  do GBM cuja `full` é mais longa que a `common` e tem um ponto degenerado
  **fora** da interseção: o `value` reportado é a taxa da `full` e difere da
  taxa da `common`; **1.0** no baseline
  pontual (grade toda igual) e SKIPPED com motivo; proveniência REPORTED com
  o fingerprint e o resumo.
- **Tokens:** `gold/test_quality_checks.py`: `registry_runs_in_order`,
  `registry_duplicate_name`, `is_blocking_rule`, `result_invalid`,
  `block_estimate_invalid`, `alignment_translates_report`,
  `alignment_pass_per_horizon`, `preconditions_k_below_min`,
  `preconditions_constant_differential`, `preconditions_invalid_series`,
  `preconditions_undefined_estimate`, `preconditions_skipped`,
  `preconditions_pass`, `step_delegates_to_owners`, `degeneracy_reported`,
  `degeneracy_point_baseline`, `degeneracy_skipped`,
  `degeneracy_uses_model_full`, `provenance_reported`.
- **Verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/gold/test_quality_checks.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): registry de quality checks com severidade e passo de pré-condições [6.4/task-05]`

---

### Task 06 — `HorizonReports` e `gold_build_order`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/horizon_reports.py`
  - `src/financial_forecasting/features/evaluation/domain/services/gold_build_order.py`
  - `tests/unit/features/evaluation/gold/test_horizon_reports.py`
  - `tests/unit/features/evaluation/gold/test_builder_explicit_deps.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4, D5, D7, I1, I12, I14, C1, C8; ADRs 6.4.0001, 6.4.0007):**
  - `horizon_reports.py`: `SampleKind {MODEL_FULL = "model_full", COMMON =
    "common"}`; `CalibrationRow` (a `ChristoffersenReport`, as
    `WilsonBandReport`s — uma por `band_level`, com `count = n_violations`,
    `n = n_observed`, `nominal = violation_rate` — e `var_level: float |
    None`); `SeriesReports` (modelo, seed, amostra, `n_points`, primeiro/
    último `target_timestamp`, `PinballReport`, `CrpsReport`,
    `IntervalScoreReport`, `CoverageReport`, `guardrail_applied_rate`,
    `calibration: tuple[CalibrationRow, ...]`); `HorizonReport` (horizonte,
    `n_common`, primeiro/último comum, `series`, `paired`, `dm_families`);
    `HorizonReports.evaluate(samples, *, paired, tolerance, band_levels,
    min_violations, candidate, dm_alpha, dm_variance_estimators) ->
    HorizonReport` — só chama os serviços existentes: por (modelo, seed,
    amostra) `PinballScore.score`, `CrpsScore.score`, `IntervalScore.score`,
    `CoverageMetrics.evaluate(tolerance)`; para cada par simétrico
    (`HitSequences.interval`) e cada τ ≠ 0,5 (`lower_tail`/`upper_tail` por
    `var_tail_for`, que dá também o `var_level`), com
    `include_degenerate ∈ {False, True}`, a sequência e — se `h > 1` — cada
    sub-série de `dgt_partition()`, cada uma com
    `ChristoffersenTest.evaluate(min_violations)` e as bandas; na amostra
    comum, um `HolmCorrection.family(paired, candidate, alpha,
    variance_estimator)` por estimador. `paired.horizon != samples.horizon`
    ou `paired.models != samples.models` → `ValueError`.
  - `gold_build_order.py`: `gold_build_order(builders: Sequence[tuple[str,
    frozenset[str]]]) -> tuple[str, ...]` — duplicata, auto-dependência,
    dependência não registrada (mensagem com os dois nomes) → `ValueError`;
    insere no `graphlib.TopologicalSorter` em ordem de nome; `CycleError` →
    `ValueError` com `args[1]` na mensagem.
- **Critério de aceite (A1, A5):** relatórios **iguais** (`==`) aos das
  chamadas diretas sobre as mesmas séries, nas duas amostras; as linhas de
  calibração existem com e sem lacunas; `len(wilson) == len(band_levels)` com
  cada nível; um `DmHolmFamilyReport` por estimador, na ordem dos
  parâmetros; h = 1 → nenhuma linha com `dgt_step`; h = 2 → sub-séries com
  `dgt_step == 2`; `var_level` só nas caudas (0,98 para τ = 0,02 e 0,98);
  série 100 % degenerada → relatórios "não aplicável" dos serviços (C8); o
  `paired` com 2 seeds é o da fábrica (média de L_t — I12, comparado com
  `paired_pinball_losses` direto); `guardrail_applied_rate` copiado da
  série; horizonte ou modelos do `paired` divergentes erguem. Ordem igual
  para 20 permutações do registro dos cinco builders do concept; as quatro
  dependências de `quality_checks` vêm depois dele; cada caso de C1 ergue.
- **Tokens:** `gold/test_horizon_reports.py`: `reports_equal_direct_calls`,
  `both_samples`, `with_and_without_gaps`, `band_per_level`,
  `dm_per_estimator`, `dgt_only_multistep`, `var_level_tails`,
  `degenerate_not_applicable`, `seed_mean_by_factory`,
  `guardrail_rate_copied`, `horizon_mismatch_raises`;
  `gold/test_builder_explicit_deps.py`: `order_invariant`,
  `dependencies_first`, `duplicate_name`, `cycle_raises`,
  `unknown_dependency`, `self_dependency`.
- **Verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/gold/test_horizon_reports.py tests/unit/features/evaluation/gold/test_builder_explicit_deps.py -v
  test -s src/financial_forecasting/features/evaluation/domain/services/gold_build_order.py
  grep -q "graphlib" src/financial_forecasting/features/evaluation/domain/services/gold_build_order.py
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): HorizonReports dos serviços 6.1-6.3 e ordem de builders por graphlib [6.4/task-06]`

> **Checkpoint C (T2) após esta Task:** `make check-block` (Container).

---

### Task 07 — DTOs do refresh + port `GoldStore` + `InMemoryGoldStore` + contrato (perna `fake`)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/__init__.py`
  - `src/financial_forecasting/features/evaluation/application/dtos/refresh_gold.py`
  - `src/financial_forecasting/features/evaluation/application/ports/out/gold_store.py`
  - `tests/fakes/features/evaluation/in_memory_gold_store.py`
  - `tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py`
  - `tests/contract/features/evaluation/test_gold_store_contract.py`
- **Arquivos a modificar (ADR 6.1.0005, janela de um commit):**
  - `scripts/arch_baseline.toml` — entrada transitória `GoldStore`
    (`motivo` citando ADR 6.1.0005, "removida na 6.4 Task 08", `issue = 117`);
  - `tests/architecture/test_port_coverage_gate.py` —
    `["GoldStore", "Hasher"]`, comentário citando o ADR e a Task 08.
- **O que fazer (concept §4 Application, C2, C3, I17; ADRs 6.4.0005, 6.4.0006):**
  - `refresh_gold.py` (DTOs frozen):
    - `RefreshParameters` — os campos do ADR 6.4.0006 item 1, todos keyword,
      **sem default**; `__post_init__`: `preregistration_ref`/`candidate`
      `str` não-vazias; tuplas não-vazias e sem repetição (`band_levels`,
      `dm_variance_estimators`, `mcs_schemes`); `validate_tolerance(…,
      field="degeneracy_tolerance")`; `validate_rate` por nível de banda;
      `validate_min_violations`; `validate_alpha` para `dm_alpha` e
      `mcs_alpha`; `validate_bootstrap_parameters(reps=mcs_reps,
      seed=mcs_seed)` e `validate_mcs_reps(mcs_reps)`; estimadores/esquemas
      instâncias dos enums; `as_mapping()`.
    - `GoldPartition(asset, parent_sweep_id)` — `validate_path_identifier`
      nos dois (C3); `RefreshGoldCommand(asset, parent_sweep_id, horizons,
      window_deficits, parameters)` — constrói `partition` no
      `__post_init__` (C3 antes de qualquer leitura), `horizons` não-vazio e
      sem repetição.
    - `GoldTable(name, key, rows)` (regras do §1); `GoldManifest` (status,
      `rows_by_table`, parâmetros, horizontes, déficits, fingerprint, resumo
      do `target_return`, `n_runs`, `build_order`, `started_at`,
      `finished_at`) com `as_mapping()`; `RefreshStatus {COMPLETED,
      BLOCKED}`; `GoldInputs` (partição, `preregistration_ref`, parâmetros,
      status, resultados dos checks, `HorizonReport`s, `McsReport`s,
      `BlockEstimate`s por horizonte); `FailedCheck` e
      `failed_checks_of(results)` (ERROR+FAIL → DTO); `RefreshGoldResult`.
  - `gold_store.py`: `GoldStore(Protocol)` com `publish(*, partition,
    tables, manifest) -> None` (assinatura literal do concept); docstring com
    a pré-condição de escritor único e o layout do ADR 6.4.0005.
  - `InMemoryGoldStore`: `publish` substitui por inteiro a geração da
    partição (`{(asset, parent_sweep_id): (manifest.as_mapping(), {nome:
    linhas})}`); `current(partition)` para a suíte.
  - Suíte parametrizada por um *harness* por perna (`publish` + leitura da
    geração corrente), ids `["fake"]` nesta Task (a Task 08 acrescenta
    `"parquet"` sem `skipif`).
- **Critério de aceite (A7, A8, C2, C3):** `RefreshParameters` sem qualquer
  campo → `TypeError`; cada campo inválido ergue com a mensagem do dono
  (casada por substring, um caso parametrizado por campo); tupla vazia/
  repetida ergue; `preregistration_ref` `""` ergue; identificador com `/`
  ou espaço ergue no `RefreshGoldCommand`; `GoldTable` fora de ordem,
  chave repetida ou colunas diferentes erguem; `as_mapping()` do manifesto é
  serializável por `json.dumps` e carrega `preregistration_ref`;
  `failed_checks_of` só leva ERROR+FAIL. Contrato (perna `fake`): depois do
  `publish`, a geração corrente é exatamente as tabelas e o manifesto
  publicados; um segundo `publish` com menos tabelas substitui (a tabela que
  saiu não aparece); outra partição intocada; ordem das linhas preservada.
- **Tokens:** `gold/test_refresh_gold_dtos.py`: `parameters_no_default`,
  `parameters_owner_messages`, `tuple_empty_or_repeated`,
  `preregistration_ref_required`, `identifier_rule`, `command_horizons`,
  `table_key_order`, `table_columns_uniform`, `manifest_mapping`,
  `failed_checks_of_results`; `test_gold_store_contract.py`:
  `publish_then_current`, `publish_replaces_generation`,
  `other_partition_untouched`, `rows_order_preserved`.
- **Verificação (T3) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py tests/contract/features/evaluation/test_gold_store_contract.py -v
  uv run pytest tests/architecture/test_port_coverage_gate.py -v
  uv run python scripts/check_port_coverage.py --list
  uv run python scripts/check_fake_parity.py
  test -s scripts/arch_baseline.toml
  grep -q 'key = "GoldStore"' scripts/arch_baseline.toml
  make check
  ```
- **Commit sugerido:** `feat(evaluation): DTOs do refresh e port GoldStore com fake e suíte de contrato [6.4/task-07]`

---

### Task 08 — `ParquetGoldStore` + perna `parquet` (reverte o baseline)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/__init__.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/parquet_gold_store.py`
- **Arquivos a modificar:**
  - `tests/contract/features/evaluation/test_gold_store_contract.py` (perna `"parquet"` + testes só-do-real)
  - `scripts/arch_baseline.toml` — remove `GoldStore`;
  - `tests/architecture/test_port_coverage_gate.py` — volta a `["Hasher"]`.
- **O que fazer (concept D8, C9; ADR 6.4.0005 itens 2, 5, 6):** classe
  pública `ParquetGoldStore(data_root)` (docstring: satisfaz o port
  `GoldStore`). `publish`: raiz da partição
  `<data_root>/gold/asset=<a>/parent_sweep_id=<p>/`; remove `.staging/` e
  `.previous/` sobrantes; grava cada tabela em `.staging/<name>.parquet`
  (`pyarrow.Table.from_pylist(rows)` → `pyarrow.parquet.write_table`, por uma
  função privada `_write_table`); grava `MANIFEST.json`
  (`json.dumps(manifest.as_mapping(), sort_keys=True, indent=2)`, por
  `_write_manifest`) **por último**; `os.replace(current, .previous)` se
  `current/` existe; `os.replace(.staging, current)`; `shutil.rmtree(.previous)`
  — `OSError` aí vira `logger.warning` e o `publish` retorna normalmente.
  Antes de montar o caminho, o adapter chama `validate_path_identifier`
  (dono único, Task 02; concept C3 "de novo no `ParquetGoldStore`") em
  `asset` e `parent_sweep_id` — defesa na fronteira de I/O sem reescrever a
  regra.
- **Critério de aceite (A8, A9, C9):** suíte verde em `fake` e `parquet`,
  zero `SKIPPED`; só-do-real: com uma geração viva, `_write_table`
  monkeypatchado para erguer `OSError` na 2ª tabela → `publish` propaga,
  `current/` e o seu `MANIFEST.json` byte-iguais aos de antes; `.staging/` e
  `.previous/` plantados à mão → removidos no `publish` seguinte; espião nas
  duas funções de escrita → o manifesto é a última escrita; `shutil.rmtree`
  do módulo trocado para erguer em `.previous` → `caplog` com o aviso, o
  `publish` retorna e `current/` é a geração nova, e o `publish` seguinte
  remove o resto; `duckdb.read_parquet` lê cada tabela publicada com as
  mesmas linhas; um `GoldPartition` adulterado (`object.__setattr__(partition,
  "asset", "../x")`) faz o `publish` erguer `ValueError` sem criar nada em
  `<data_root>/gold/`. `check_port_coverage.py` verde **sem** `GoldStore` no
  baseline; `test_port_coverage_gate.py` com `["Hasher"]`.
- **Tokens:** `test_gold_store_contract.py` (acréscimos):
  `real_failure_keeps_current`, `real_leftovers_removed`,
  `real_manifest_written_last`, `real_previous_delete_warns`,
  `real_duckdb_readable`, `real_rejects_bad_identifier`.
- **Verificação (T3) — Container:**
  ```bash
  f=$(mktemp)
  uv run pytest tests/contract/features/evaluation/test_gold_store_contract.py -v -rs | tee "$f"
  test -s "$f"
  if grep -q "SKIPPED" "$f"; then echo "FAIL: SKIPPED"; exit 1; fi
  grep -q "\[fake" "$f"
  grep -q "\[parquet" "$f"
  uv run pytest tests/architecture/test_port_coverage_gate.py -v
  uv run python scripts/check_port_coverage.py --list
  test -s scripts/arch_baseline.toml
  test -s tests/architecture/test_port_coverage_gate.py
  if grep -n "GoldStore" scripts/arch_baseline.toml tests/architecture/test_port_coverage_gate.py; then echo "FAIL: baseline residual"; exit 1; fi
  make check
  ```
- **Commit sugerido:** `feat(evaluation): ParquetGoldStore com staging, manifesto por último e troca de pasta [6.4/task-08]`

---

### Task 09 — Port `GoldBuilder` + `FakeGoldBuilder` + contrato (perna `fake`)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/ports/out/gold_builder.py`
  - `tests/fakes/features/evaluation/fake_gold_builder.py`
  - `tests/contract/features/evaluation/_gold_inputs.py`
  - `tests/contract/features/evaluation/test_gold_builder_contract.py`
- **Arquivos a modificar (ADR 6.1.0005, janela de um commit):**
  - `scripts/arch_baseline.toml` — entrada transitória `GoldBuilder`
    ("removida na 6.4 Task 10", `issue = 117`);
  - `tests/architecture/test_port_coverage_gate.py` — `["GoldBuilder", "Hasher"]`.
- **O que fazer (concept §4, D7, I14, I17; ADR 6.4.0001):**
  - Port `GoldBuilder(Protocol)` com a assinatura literal do concept
    (`name`, `depends_on`, `runs_when_blocked` como propriedades; `build(inputs:
    GoldInputs) -> GoldTable`); docstring: mapeamento puro, sem estado
    compartilhado, tabela `gold_<name>`, confirmatórias com
    `preregistration_ref`.
  - `FakeGoldBuilder(name, depends_on=frozenset(), runs_when_blocked=False)`:
    tabela mínima e **diferente** da do `QualityChecksGoldBuilder` (evita
    duplicação no `check_fake_parity`): uma linha por nome de check distinto,
    `key = ("check",)`, colunas `check`, `n_results`, `asset`,
    `parent_sweep_id` (e `preregistration_ref` quando não
    `runs_when_blocked`) — sem fórmula; registra as chamadas.
  - `_gold_inputs.py`: `completed_inputs()` e `blocked_inputs()` montados só
    com domínio (`SeriesAssembly`, checks, `HorizonReports`,
    `ModelConfidenceSet` sobre `FakeMcsBackend`) a partir de um cohort
    sintético pequeno (2 horizontes, candidato com 2 seeds, GBM e baseline
    pontual).
  - Suíte parametrizada por fábrica, ids `["fake"]` nesta Task (a Task 10
    acrescenta um id por builder real, sem `skipif`).
- **Critério de aceite (A8, I14, I17):** `build` duas vezes com os mesmos
  `GoldInputs` → tabelas iguais e os inputs intactos (frozen); `table.name ==
  "gold_" + builder.name`; toda linha com `asset`/`parent_sweep_id` da
  partição; `preregistration_ref` em toda linha das confirmatórias; builder
  `runs_when_blocked` constrói sobre `blocked_inputs()`; `depends_on` não
  contém o próprio nome. `check_port_coverage.py`, `check_fake_parity.py`,
  `test_port_coverage_gate.py` e `lint-imports` verdes.
- **Tokens:** `test_gold_builder_contract.py`: `builder_pure_mapping`,
  `table_named_after_builder`, `rows_carry_partition`,
  `confirmatory_rows_carry_prereg`, `blocked_inputs_tolerated`,
  `no_self_dependency`.
- **Verificação (T3) — Container:**
  ```bash
  uv run pytest tests/contract/features/evaluation/test_gold_builder_contract.py -v
  uv run pytest tests/architecture/test_port_coverage_gate.py -v
  uv run python scripts/check_port_coverage.py --list
  uv run python scripts/check_fake_parity.py
  test -s scripts/arch_baseline.toml
  grep -q 'key = "GoldBuilder"' scripts/arch_baseline.toml
  make check
  ```
- **Commit sugerido:** `feat(evaluation): port GoldBuilder com fake e suíte de contrato [6.4/task-09]`

> **Checkpoint C (T2) após esta Task:** `make check-block` (Container).

---

### Task 10 — Cinco builders em `adapters/out/duckdb/gold_builders/` + pernas reais (reverte o baseline)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/{__init__.py, quality_checks.py, metrics_by_run.py, calibration_table.py, dm_results.py, mcs_results.py}`
- **Arquivos a modificar:**
  - `tests/contract/features/evaluation/test_gold_builder_contract.py` (ids reais + testes de mapeamento)
  - `scripts/arch_baseline.toml` — remove `GoldBuilder`;
  - `tests/architecture/test_port_coverage_gate.py` — volta a `["Hasher"]`.
- **O que fazer (concept §9, D5, D7, I14, I17; ADRs 6.4.0001, 6.4.0007):**
  classes públicas `QualityChecksGoldBuilder` (`name = "quality_checks"`,
  `depends_on = frozenset()`, `runs_when_blocked = True`),
  `MetricsByRunGoldBuilder`, `CalibrationTableGoldBuilder`,
  `DmResultsGoldBuilder`, `McsResultsGoldBuilder` (`depends_on =
  frozenset({"quality_checks"})`, `runs_when_blocked = False`), docstring
  "satisfaz o port `GoldBuilder`". Cada `build` só mapeia os VOs dos
  `GoldInputs` nas colunas da tabela do §1 (formato longo no
  `metrics_by_run`), com `float`/`int`/`bool`/`str`/`None` nativos, e
  devolve `GoldTable(name, key, rows)` ordenada pela chave. **Nenhuma
  fórmula**: todo número sai de um campo/propriedade de relatório (inclusive
  a média do IS pelo `PairIntervalScore.mean_score`). Os módulos não importam
  `pyarrow`/`duckdb`/`pandas` (mapeamento em Python puro).
- **Critério de aceite (A7, A8, I17):** suíte verde nos seis ids (`fake` + os
  cinco), zero `SKIPPED`; mapeamento: `gold_quality_checks` tem uma linha por
  `QualityCheckResult` e **sem** `preregistration_ref`;
  `gold_metrics_by_run` reproduz cada campo dos relatórios de uma série
  escolhida (pinball por τ, `grid_mean`, `crps_q` + rótulo, IS e largura por
  par, ĉ(τ), PICP/MPIW + `MPIW_LABEL`, degeneração, `guardrail_applied_rate`)
  e a contagem de linhas bate com a fórmula declarada no teste;
  `gold_calibration_table` reproduz o `ChristoffersenReport`/`WilsonBandReport`
  de uma linha escolhida (com e sem lacunas, DGT em h = 2, `var_level`);
  `gold_dm_results` = (k − 1) × estimadores × horizontes linhas com os campos
  do `HolmComparison`; `gold_mcs_results` = k × esquemas × horizontes com a
  ordem de eliminação, p's, `included`, parâmetros e `max_block_estimate`;
  chaves únicas em todas. `check_port_coverage.py` verde **sem**
  `GoldBuilder` no baseline.
- **Tokens:** `test_gold_builder_contract.py` (acréscimos):
  `quality_checks_rows`, `quality_rows_no_prereg`, `metrics_rows_match_reports`,
  `calibration_rows_match_reports`, `dm_rows_match_families`,
  `mcs_rows_match_reports`, `row_keys_unique`.
- **Verificação (T3) — Container:**
  ```bash
  f=$(mktemp)
  uv run pytest tests/contract/features/evaluation/test_gold_builder_contract.py -v -rs | tee "$f"
  test -s "$f"
  if grep -q "SKIPPED" "$f"; then echo "FAIL: SKIPPED"; exit 1; fi
  for id in fake quality_checks metrics_by_run calibration_table dm_results mcs_results; do grep -q "\[$id\]" "$f" || { echo "FAIL: perna $id ausente"; exit 1; }; done
  B=src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders
  test -d "$B"
  if grep -rnE "^\s*(import|from)\s+(pyarrow|duckdb|pandas)\b" "$B"; then echo "FAIL: builder importa engine"; exit 1; fi
  uv run pytest tests/architecture/test_port_coverage_gate.py -v
  test -s scripts/arch_baseline.toml
  test -s tests/architecture/test_port_coverage_gate.py
  if grep -n "GoldBuilder" scripts/arch_baseline.toml tests/architecture/test_port_coverage_gate.py; then echo "FAIL: baseline residual"; exit 1; fi
  make check
  ```
- **Commit sugerido:** `feat(evaluation): cinco gold builders de mapeamento puro com pernas reais do contrato [6.4/task-10]`

---

### Task 11 — Port `SilverTableReader` (contrato `[fake, real]`) + use case `RefreshGold`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/ports/out/silver_table_reader.py`
  - `src/financial_forecasting/features/evaluation/application/use_cases/{__init__.py, refresh_gold.py}`
  - `tests/fakes/features/evaluation/fake_silver_table_reader.py`
  - `tests/contract/features/evaluation/test_silver_table_reader_contract.py`
  - `tests/unit/features/evaluation/gold/test_refresh_gold_use_case.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/analytics_store/adapters/out/parquet/parquet_analytics_repository.py`
    — **só docstring**: "satisfaz também, por duck typing, o port
    `SilverTableReader` do `evaluation` (ADR 0.0.0053, ADR 6.4.0004)" (é o
    que o `check_port_coverage` lê como citação do port).
- **O que fazer (concept §4, D3, D6, D8, I1–I17, C1–C7; ADRs 6.4.0002–0006):**
  - Port `SilverTableReader(Protocol)` com a assinatura literal do concept;
    docstring: filtros só de partição, superconjunto, o consumidor pós-filtra.
  - `FakeSilverTableReader(rows_by_table, partition_keys)`: aplica só as
    chaves de partição declaradas; ignora as demais (como o real).
  - Suíte `[fake, real]` (`ParquetAnalyticsRepository` sobre `tmp_path` com
    `FakeClock`), linhas válidas de `dim_run` e `fact_oos_predictions`
    gravadas nas duas pernas; na perna real, `dim_run` com **um `write` por
    run** (lote misto `seed` None/int falha no schema — #119).
  - `RefreshGold(silver_reader, store, hasher, clock, mcs_backend,
    gold_store, builders)` — o construtor roda `gold_build_order` e guarda a
    ordem (C1, decisão de detalhe do §1); `__call__(command) ->
    RefreshGoldResult`, na ordem de I15: (1) usa a ordem validada; (2)
    `started_at =
    clock.now()`; (3) `dim_run` por `{asset, parent_sweep_id}` → pós-filtro
    exato → `CohortRun`s (vazio → `ValueError` nomeando a partição, C4);
    (4) `fact_oos_predictions` por `{asset, feature_set_name}` para cada
    nome do cohort → pós-filtro `asset`/`run_id` do cohort → `ForecastRecord`
    (`guardrail_applied` int 0/1 → `bool`; outro valor → `ValueError`);
    (5) realizado **uma vez** via `store.read(layer="processed",
    table="dataset_tft", filters={"asset": asset})` → `RealizedReturns`
    (vazio → `ValueError`, C4) + `DatasetFingerprint.compute(hasher, asset,
    timestamp_min/max, row_count, close_sum/volume_sum por math.fsum,
    parquet_file_hash="not-exposed-by-medallion-store")`; (6)
    `SeriesAssembly.assemble(…, required_models=frozenset({candidate}))`;
    (7) se montou: por horizonte, `models_suffice` → `paired_pinball_losses`
    sobre a amostra comum → por par `block_request_defect` → backend só nos
    pares sem defeito, `ArithmeticError` → `BlockEstimate` indefinido
    (qualquer outra exceção propaga, C7); (8) `QualityCheckRegistry` com os
    quatro checks na ordem do ADR 6.4.0002 → `is_blocking`; (9) se não
    bloqueado: `HorizonReports.evaluate` por horizonte e, por horizonte e
    esquema, `ModelConfidenceSet.block_length` → `bootstrap_indices(n_obs=T,
    block_size, reps, seed, scheme)` → `ModelConfidenceSet.evaluate(alpha)`;
    (10) builders na ordem (se `BLOCKED`, só os `runs_when_blocked`);
    (11) `GoldManifest` com `finished_at = clock.now()`; (12)
    `gold_store.publish`; log por etapa (§1); devolve o resultado com
    `failed_checks_of`.
- **Critério de aceite (A1, A3, A4, A6, A7, I15, I16, C1–C7):** com fakes
  (`FakeSilverTableReader`, `FakeMedallionStore.seed_read_only`, `FakeClock`,
  `FakeMcsBackend`, `InMemoryGoldStore`, `FakeGoldBuilder`s que imitam o grafo
  do concept, `_StubHasher`): grafo inválido ergue já no construtor do
  `RefreshGold`, sem nenhuma chamada de leitura (espiões); `RefreshGoldCommand` com `asset="a/b"` ergue antes do
  use case; cohort/dataset vazios erguem sem `publish`; linhas de fato de
  outro cohort descartadas; `guardrail_applied` 0/1 vira `bool` e 2 ergue; o
  realizado é lido uma vez; o bloco passado ao backend é
  `ModelConfidenceSet.block_length` das estimativas, e `reps`/`seed`/esquemas
  são os dos parâmetros para todo horizonte e esquema; backend que ergue
  `ArithmeticError` num par → FAIL `backend_arithmetic` e `BLOCKED`; que ergue
  `RuntimeError` → propaga e o store não é chamado; fábrica monkeypatchada
  que ergue se k < 2 e backend que ergue se receber série constante/curta
  nunca disparam (cohort com 1 modelo; par com diferencial constante), e o
  resultado é `BLOCKED` com o `FailedCheck(check="statistical_preconditions",
  kind="insufficient_models" | "constant_differential")` correspondente;
  espião na fábrica `paired_pinball_losses` (monkeypatch no módulo do use
  case, delegando à real) confirma que ela recebe, por modelo, as S séries
  `common` (candidato com 2 seeds → 2 séries) — a média entre seeds é da
  fábrica (I12);
  bloqueado → `publish` com só `gold_quality_checks`, manifesto `BLOCKED`,
  resultado `BLOCKED` com os `FailedCheck`s; exceção no builder → store não
  chamado; ordem dos efeitos (leituras → backend → builders → publish) por um
  registro comum aos espiões; `caplog` com uma linha por etapa (nome,
  `duration_s`, `in`, `out`) e a final com o status; o manifesto tem
  `parameters.preregistration_ref`, horizontes, déficits, fingerprint e
  resumo; duas execuções idênticas → tabelas iguais e manifestos iguais salvo
  `started_at`/`finished_at`. Contrato do reader: filtro de partição
  aplicado; filtro fora da partição devolve superconjunto nas duas pernas;
  partição ausente → vazio; tabela desconhecida ergue; tipos preservados
  (`guardrail_applied` int, `seed` `None`/int). `check_port_coverage` verde
  **sem** entrada nova.
- **Tokens:** `gold/test_refresh_gold_use_case.py`:
  `graph_checked_before_read`, `identifier_before_path`,
  `cohort_empty_raises`, `dataset_empty_raises`, `foreign_run_rows_dropped`,
  `guardrail_int_to_bool`, `realized_read_once`, `mcs_block_from_rule`,
  `mcs_reps_seed_schemes`, `arithmetic_error_fails_precondition`,
  `other_backend_error_propagates`, `factory_never_short`,
  `backend_never_invalid`, `blocked_publishes_checks_only`,
  `blocked_result_failed_checks`, `exception_before_publish`,
  `effects_order`, `step_logs`, `manifest_carries_parameters`,
  `rerun_identical`, `completed_publishes_all_tables`,
  `seeds_averaged_by_factory`; `test_silver_table_reader_contract.py`: `partition_filter_applied`,
  `non_partition_superset`, `absent_partition_empty`,
  `unknown_table_raises`, `values_round_trip`.
- **Verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/gold/test_refresh_gold_use_case.py -v
  f=$(mktemp)
  uv run pytest tests/contract/features/evaluation/test_silver_table_reader_contract.py -v -rs | tee "$f"
  test -s "$f"
  if grep -q "SKIPPED" "$f"; then echo "FAIL: SKIPPED"; exit 1; fi
  grep -q "\[fake" "$f"
  grep -q "\[real" "$f"
  g=$(mktemp)
  uv run python scripts/check_port_coverage.py --list > "$g"
  test -s "$g"
  h=$(mktemp)
  grep -A3 "SilverTableReader" "$g" > "$h"
  test -s "$h"
  grep -q "ParquetAnalyticsRepository" "$h"
  test -s scripts/arch_baseline.toml
  if grep -n "SilverTableReader" scripts/arch_baseline.toml; then echo "FAIL: baseline"; exit 1; fi
  make check-task SLICE="evaluation analytics_store"
  ```
- **Commit sugerido:** `feat(evaluation): use case RefreshGold e port SilverTableReader com contrato [6.4/task-11]`

---

### Task 12 — Wiring no `composition_root` + e2e sobre silver sintético + re-medição do MCS

- **Arquivos a criar:**
  - `tests/integration/features/evaluation/test_refresh_gold.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/composition_root.py`
  - `tests/unit/shared/test_composition_root.py`
- **O que fazer (concept §8 Internas, §11 E2E, A10, A12; ADR 6.4.0005):**
  - `composition_root`: `_LazyArchMcs` (proxy dos dois métodos do
    `McsBackend`, importa `ArchMcs` na primeira chamada); `refresh_gold:
    RefreshGold` em `ApplicationDependencies`, montado com o
    `ParquetAnalyticsRepository` já wirado (como `SilverTableReader`), o
    `ParquetMedallionStore`, o `CanonicalJsonHasher`, o `SystemClock`, o
    `_LazyArchMcs`, `ParquetGoldStore(settings.data_root)` e os cinco
    builders.
  - `test_refresh_gold.py` (`pytestmark = pytest.mark.integration`), um
    fixture de módulo que roda o cenário inteiro num **único** `data_root` e
    guarda instantâneos (padrão do `test_run_baselines.py`): silver sintético
    (horizontes 1 e 2; `tft_quantile` candidato com seeds 0 e 1 e prefixo 2
    sessões atrás com déficit 3; `gbm_quantile`; `baseline_naive` pontual,
    grade toda igual; 2 folds; grade `(0.05, 0.25, 0.5, 0.75, 0.95)`; ~60
    sessões de teste) gravado pelo `ParquetAnalyticsRepository` real
    (`dim_run` um run por chamada — #119) e o dataset
    `processed/dataset_tft/<asset>/dataset_tft_<asset>.parquet` com
    `timestamp`, `target_return`, `close`, `volume`; `RefreshGold` real
    (`ArchMcs` real, `reps = 1000`, esquemas estacionário e moving-block, dois
    estimadores DM, bandas 0,95 e 0,975, `preregistration_ref` literal
    declarado). Sequência: (0) refresh COMPLETED de um cohort **B**
    (`parent_sweep_id` diferente, mesmo `asset`) e cópia dos bytes do seu
    `current/`; (1) refresh do cohort **A** → `COMPLETED`; (2) rerun **sem
    apagar**; (3) reescreve o arquivo da partição de fatos removendo as
    linhas de um `target_timestamp` interior de um run do GBM (lacuna
    interior) e refresca → `BLOCKED`.
  - O cenário roda o `RefreshGold` **wirado**: `deps =
    wire_dependencies(settings=Settings(data_root=<tmp>))` e
    `deps.refresh_gold(command)` (caminho de produção, não montagem à mão no
    teste); depois do passo (1),
    `deps.refresh_gold._mcs_backend._delegate is not None` (o proxy lazy
    carregou o `ArchMcs`).
  - Re-medição (A12): a duração da etapa `mcs` do log no passo (1) e um
    `timeit` de `ModelConfidenceSet.evaluate` sobre índices do `ArchMcs` com T
    = 1000, k = 6, `reps = 1000` — registrados em §7 como **uma** entrada
    com o título literal `### <AAAA-MM-DD> — [decision] Task 12 — custo do
    MCS — <autor>` (o §3 casa `Task 12 — custo do MCS` ou `Task 12: custo do
    MCS`).
- **Critério de aceite (A10, A11, A12):** (1) cinco tabelas lidas por
  `duckdb.read_parquet` depois de ler `current/MANIFEST.json` (status
  `COMPLETED`), com `COUNT(*)` = `rows_by_table` do manifesto = resultado, e
  `gold_dm_results`/`gold_mcs_results` iguais às fórmulas fechadas
  ((k − 1)·2·2 e k·2·2); (2) todas as linhas das cinco tabelas idênticas às
  do passo (1) (comparação célula a célula que trata NaN = NaN) e manifesto
  igual salvo `started_at`/`finished_at`; (3) `current/` só com
  `gold_quality_checks.parquet` e `MANIFEST.json`, status `BLOCKED`,
  `alignment_check` FAIL `interior_gap`; (todos) os bytes do `current/` do
  cohort B iguais aos do passo (0); `test_composition_root.py`:
  `refresh_gold` wirado com os adapters reais e o proxy sem `arch` carregado
  (`_delegate is None`); no e2e, depois do passo (1), `_delegate is not
  None`.
- **Tokens:** `tests/integration/features/evaluation/test_refresh_gold.py`:
  `e2e_wired_lazy_backend_loaded`, `e2e_completed_five_tables`, `e2e_duckdb_counts`, `e2e_rerun_identical`,
  `e2e_manifest_same_but_timestamps`, `e2e_blocked_replaces`,
  `e2e_other_cohort_untouched`; `tests/unit/shared/test_composition_root.py`:
  `wires_refresh_gold`, `arch_mcs_proxy_lazy`.
- **Verificação (T1 = `check-block`, toca o composition root) — Container:**
  ```bash
  f=$(mktemp)
  uv run pytest tests/integration/features/evaluation/test_refresh_gold.py tests/unit/shared/test_composition_root.py -v -rs --durations=5 | tee "$f"
  test -s "$f"
  if grep -q "SKIPPED" "$f"; then echo "FAIL: SKIPPED"; exit 1; fi
  make check-block
  ```
- **Commit sugerido:** `feat(evaluation): RefreshGold no composition root e e2e sobre silver sintético [6.4/task-12]`

> **Checkpoint C (T2) após esta Task:** coberto pelo `make check-block` da
> própria Task.

---

### Task 13 — Roadmap §Stage 6.4 (D9)

- **Arquivos a modificar:**
  - `docs/roadmap.md`
- **Arquivos a criar:** nenhum.
- **Antes de começar (Host):** `git fetch origin && git rebase origin/develop`
  (GIT-WORKFLOW Etapa 4); conflito resolvido mantendo as duas edições, com
  `[deviation]` em §7 se algo mudar de lugar; rodar de novo o T1 da Task 12
  depois do rebase se algo além de docs entrou.
- **O que fazer (concept D9; autoridade em D9):** na seção `#### Stage 6.4`:
  descrição humana e DoD sem "aplicando as disposições"/"disposições
  aplicadas" (DoD reescrito com o §11 do concept em uma frase);
  `arquivos_a_criar` = a lista real desta Stage (§1 Estrutura), inclusive
  `series_assembly.py`, `horizon_reports.py`, `gold_build_order.py`,
  `silver_table_reader.py`, `gold_store.py`, `dtos/refresh_gold.py`,
  `parquet_gold_store.py`, `gold_builders/quality_checks.py`,
  `quality_checks/statistical_preconditions_check.py`,
  `quality_checks/realized_provenance_check.py`,
  `value_objects/block_estimate.py`,
  `shared/domain/services/path_identifier.py` e os fakes/contratos; `arquivos_a_modificar` com os quatro arquivos da 6.2
  (`paired_loss_series.py`, `paired_pinball_losses.py`,
  `bootstrap_indices.py`, `model_confidence_set.py`), o
  `parquet_medallion_store.py` e o seu fake `in_memory_medallion_store.py`,
  o `composition_root.py` e o `.importlinter`;
  `contratos_introduzidos` + `SeriesAssembly`, `HorizonReports`,
  `gold_build_order`, `ForecastRecord`, `CohortRun`, `RealizedReturns`,
  `AssembledCohort`, `QualityCheckResult`, `SilverTableReader`, `GoldStore`;
  `contratos_consumidos`: `AnalyticsRepository (4.2)` →
  "`ParquetAnalyticsRepository` como real do `SilverTableReader` (ADR
  0.0.0053)"; entram `MedallionStore` (par read-only `dataset_tft`),
  `DatasetFingerprint`/`Hasher`, `Clock`, `validate_mcs_reps`,
  `validate_bootstrap_parameters`, `MIN_MODELS`; em `contratos_introduzidos`
  também `validate_path_identifier` (shared).
- **Critério de aceite (A13):** os greps abaixo reprovam no `develop` de hoje
  (a seção tem "disposições", consome `AnalyticsRepository (4.2)` e não tem
  os nomes novos — `refresh_gold.py` sozinho já casaria o use case do
  roadmap atual, por isso o grep usa `dtos/refresh_gold.py`) e passam
  depois; `make docs-check` verde.
- **Verificação (docs) — Host:**
  ```bash
  S64=$(awk '/^#### Stage 6.4/,/^#### Stage 6.5/' docs/roadmap.md); test -n "$S64"
  if grep -n "disposi" <<<"$S64"; then echo "FAIL: roadmap 6.4 ainda cita disposições"; exit 1; fi
  if grep -n "AnalyticsRepository (4.2)" <<<"$S64"; then echo "FAIL: roadmap 6.4 ainda consome AnalyticsRepository (4.2)"; exit 1; fi
  for t in series_assembly.py horizon_reports.py gold_build_order.py silver_table_reader.py gold_store.py dtos/refresh_gold.py parquet_gold_store.py statistical_preconditions_check.py realized_provenance_check.py block_estimate.py shared/domain/services/path_identifier.py paired_loss_series.py paired_pinball_losses.py bootstrap_indices.py model_confidence_set.py .importlinter parquet_medallion_store.py in_memory_medallion_store.py composition_root.py SilverTableReader GoldStore SeriesAssembly HorizonReports ForecastRecord CohortRun RealizedReturns AssembledCohort QualityCheckResult ParquetAnalyticsRepository MedallionStore DatasetFingerprint Hasher Clock MIN_MODELS validate_mcs_reps validate_bootstrap_parameters validate_path_identifier; do grep -qwF -- "$t" <<<"$S64" || { echo "FAIL: roadmap 6.4 sem $t"; exit 1; }; done
  python scripts/check_docs_pointers.py
  ```
  **Container:**
  ```bash
  make docs-check
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `docs(roadmap): Stage 6.4 com arquivos, contratos e DoD reais do gold [6.4/task-13]`

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 6.4: complete` e ser mergeada em `develop`. Antes: `git fetch` +
> `git rebase origin/develop` (§5) e o push só depois do T3 verde.

### Verificações automatizadas

**Container** (um único `bash -euo pipefail -c` no wrapper do §1):
```bash
make check                 # ruff + mypy strict + check_layout + lint-imports + fake-parity + port-coverage + docs-check + testes (cov >= 90%)

# A14 — cobertura por arquivo do slice e do novo de shared (JSON gerado e lido no mesmo shell):
# falha se arquivo < 90% ou arquivo novo ausente
cov=$(mktemp --suffix=.json)
uv run pytest --cov=financial_forecasting --cov-report=json:"$cov" -q
test -s "$cov"
uv run python - "$cov" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))["files"]
norm = {f.replace(chr(92), "/"): v["summary"]["percent_covered"] for f, v in d.items()}
scope = {f: p for f, p in norm.items() if "features/evaluation/" in f or f.endswith("shared/domain/services/path_identifier.py")}
need = ["forecast_record.py", "cohort_run.py", "realized_returns.py", "assembled_cohort.py",
        "quality_check_result.py", "block_estimate.py", "series_assembly.py", "horizon_reports.py", "gold_build_order.py",
        "quality_checks/registry.py", "quality_checks/alignment_check.py",
        "quality_checks/statistical_preconditions_check.py", "quality_checks/degeneracy_check.py",
        "quality_checks/realized_provenance_check.py", "dtos/refresh_gold.py",
        "ports/out/gold_store.py", "ports/out/gold_builder.py", "ports/out/silver_table_reader.py",
        "use_cases/refresh_gold.py", "duckdb/parquet_gold_store.py",
        "gold_builders/quality_checks.py", "gold_builders/metrics_by_run.py",
        "gold_builders/calibration_table.py", "gold_builders/dm_results.py",
        "gold_builders/mcs_results.py", "shared/domain/services/path_identifier.py"]
miss = [n for n in need if not any(f.endswith("/" + n) for f in scope)]
bad = {f: p for f, p in scope.items() if p < 90}
print(len(scope), "arquivos no escopo; abaixo de 90%:", bad, "; ausentes:", miss)
sys.exit(1 if bad or miss else 0)
PY

# A8 — três suítes de contrato, todas as pernas, zero skips
f=$(mktemp)
uv run pytest tests/contract/features/evaluation/test_gold_store_contract.py tests/contract/features/evaluation/test_gold_builder_contract.py tests/contract/features/evaluation/test_silver_table_reader_contract.py -v -rs | tee "$f"
test -s "$f"
if grep -q "SKIPPED" "$f"; then echo "FAIL: SKIPPED no contrato"; exit 1; fi
for id in fake parquet real quality_checks metrics_by_run calibration_table dm_results mcs_results; do grep -q "\[$id" "$f" || { echo "FAIL: perna $id ausente"; exit 1; }; done

# A10 — e2e, zero skips
g=$(mktemp)
uv run pytest tests/integration/features/evaluation/test_refresh_gold.py -v -rs | tee "$g"
test -s "$g"
if grep -q "SKIPPED" "$g"; then echo "FAIL: SKIPPED no e2e"; exit 1; fi

# A11 — uma aresta nova, caso real de violação; gates de arquitetura tocados
uv run lint-imports
uv run pytest tests/architecture/test_import_contracts.py tests/architecture/test_unit_evaluation_purity.py tests/architecture/test_port_coverage_gate.py -v

# Matriz — cada token casa >= 1 teste do arquivo (coleta uma vez por arquivo; token casado contra o
# nome da função após o '::' SEM o id '[...]', substring sem distinção de caixa, como o -k).
# A lista é recusada se um token repetir ou estiver contido em outro do mesmo arquivo (prova vácua).
U=tests/unit/features/evaluation; G=$U/gold; K=tests/contract/features/evaluation; I=tests/integration/features/evaluation
while read -r file toks; do
  test -s "$file"
  for a in $toks; do for b in $toks; do
    [ "$a" = "$b" ] || [[ "$b" != *"$a"* ]] || { echo "FAIL: token '$a' contido em '$b' ($file)"; exit 1; }
  done; done
  test "$(tr ' ' '\n' <<<"$toks" | sort | uniq -d | wc -l)" -eq 0
  ids=$(uv run pytest --co -q "$file" </dev/null | grep '::' | sed 's/^[^:]*:://; s/\[.*//' | sort -u)
  test -n "$ids"
  for t in $toks; do grep -qi -- "$t" <<<"$ids" || { echo "FAIL: sem teste '$t' em $file"; exit 1; }; done
done <<LIST
$U/test_paired_loss_series.py min_models_public
$U/test_paired_pinball_losses.py factory_imports_min_models
$U/test_bootstrap_indices.py bootstrap_parameters_invalid bootstrap_parameters_accepts bootstrap_request_delegates
$U/test_mcs_vs_arch.py mcs_reps_validator mcs_reps_single_owner
tests/unit/shared/domain/test_path_identifier.py identifier_accepts identifier_rejects identifier_message_names_field
tests/architecture/test_unit_evaluation_purity.py purity_scans_subpackages
$G/test_gold_value_objects.py record_invalid cohort_run_invalid realized_invalid realized_lookup realized_summary findings_xor_horizons samples_incoherent alignment_report_invalid finding_invalid
$G/test_series_assembly.py split_non_test_ignored feature_sets_multiple config_signatures_multiple orphan_run model_version_mismatch duplicate_point decision_index_mismatch horizon_label_mismatch grid_incomplete grid_divergent guardrail_flag_mismatch realized_missing interior_gap truncated_suffix prefix_over_deficit fold_coverage seed_horizon_coverage horizon_missing required_model_missing common_too_short prefix_within_deficit reproduces_persisted_values quantile_forecast_not_from_raw realized_joined common_intersection horizons_from_command all_findings_reported shuffled_input_same_result invalid_call_raises
$G/test_quality_checks.py registry_runs_in_order registry_duplicate_name is_blocking_rule result_invalid block_estimate_invalid alignment_translates_report alignment_pass_per_horizon preconditions_k_below_min preconditions_constant_differential preconditions_invalid_series preconditions_undefined_estimate preconditions_skipped preconditions_pass step_delegates_to_owners degeneracy_reported degeneracy_point_baseline degeneracy_skipped degeneracy_uses_model_full provenance_reported
$G/test_horizon_reports.py reports_equal_direct_calls both_samples with_and_without_gaps band_per_level dm_per_estimator dgt_only_multistep var_level_tails degenerate_not_applicable seed_mean_by_factory guardrail_rate_copied horizon_mismatch_raises
$G/test_builder_explicit_deps.py order_invariant dependencies_first duplicate_name cycle_raises unknown_dependency self_dependency
$G/test_refresh_gold_dtos.py parameters_no_default parameters_owner_messages tuple_empty_or_repeated preregistration_ref_required identifier_rule command_horizons table_key_order table_columns_uniform manifest_mapping failed_checks_of_results
$G/test_refresh_gold_use_case.py graph_checked_before_read identifier_before_path cohort_empty_raises dataset_empty_raises foreign_run_rows_dropped guardrail_int_to_bool realized_read_once mcs_block_from_rule mcs_reps_seed_schemes arithmetic_error_fails_precondition other_backend_error_propagates factory_never_short backend_never_invalid blocked_publishes_checks_only blocked_result_failed_checks exception_before_publish effects_order step_logs manifest_carries_parameters rerun_identical completed_publishes_all_tables seeds_averaged_by_factory
$K/test_gold_store_contract.py publish_then_current publish_replaces_generation other_partition_untouched rows_order_preserved real_failure_keeps_current real_leftovers_removed real_manifest_written_last real_previous_delete_warns real_duckdb_readable real_rejects_bad_identifier
$K/test_gold_builder_contract.py builder_pure_mapping table_named_after_builder rows_carry_partition confirmatory_rows_carry_prereg blocked_inputs_tolerated no_self_dependency quality_checks_rows quality_rows_no_prereg metrics_rows_match_reports calibration_rows_match_reports dm_rows_match_families mcs_rows_match_reports row_keys_unique
$K/test_silver_table_reader_contract.py partition_filter_applied non_partition_superset absent_partition_empty unknown_table_raises values_round_trip
$I/test_refresh_gold.py e2e_wired_lazy_backend_loaded e2e_completed_five_tables e2e_duckdb_counts e2e_rerun_identical e2e_manifest_same_but_timestamps e2e_blocked_replaces e2e_other_cohort_untouched
tests/unit/shared/test_composition_root.py wires_refresh_gold arch_mcs_proxy_lazy
LIST
```

**Host** (Git Bash, raiz da worktree, um script `bash -euo pipefail`):
```bash
T=docs/stages/6.4-gold-builders-and-quality-gates/technical.md
EV=src/financial_forecasting/features/evaluation
# A8 — baseline sem resíduo
test -s scripts/arch_baseline.toml
test -s tests/architecture/test_port_coverage_gate.py
if grep -nE "GoldStore|GoldBuilder|SilverTableReader" scripts/arch_baseline.toml tests/architecture/test_port_coverage_gate.py; then echo "FAIL: baseline residual"; exit 1; fi
# A11 — engines só no adapter duckdb; nenhum import de modeling/feature_engineering/application do analytics_store
test -d "$EV"
e=$(mktemp)
grep -rnE "^\s*(import|from)\s+(duckdb|pyarrow|pandas)\b" "$EV" > "$e" || true
test -s "$e"   # o adapter duckdb importa pyarrow/duckdb: arquivo vazio = grep quebrado
if grep -v "/adapters/out/duckdb/" "$e"; then echo "FAIL: engine fora de adapters/out/duckdb"; exit 1; fi
if grep -rnE "features\.(modeling|feature_engineering)|features\.analytics_store\.application" "$EV"; then echo "FAIL: import proibido em evaluation"; exit 1; fi
# só dois módulos de evaluation importam de analytics_store: coverage_series (6.1) e series_assembly (6.4)
q=$(mktemp)
grep -rlE "^\s*(from|import)\s+financial_forecasting\.features\.analytics_store" "$EV" > "$q"
test -s "$q"
test "$(wc -l < "$q")" -eq 2
grep -q "series_assembly.py" "$q"
grep -q "coverage_series.py" "$q"
# A12 — exatamente uma entrada de medição do MCS em §7
test -s "$T"
test "$(grep -cE "^### [0-9-]+ — \[decision\] Task 12(:| —) custo do MCS" "$T")" -eq 1
# A14 — ADRs; §7; issue; nada de caminho do host versionado
test -z "$(grep -L '^status: accepted' docs/adr/6_4_000*.md)"
HP="C:""/Users"   # montado em partes: o literal não aparece neste arquivo
if git grep -n "$HP" -- docs/ tests/ src/; then echo "FAIL: caminho do host versionado"; exit 1; fi
# o gate não é vácuo: um arquivo de rascunho com caminho de host é pego pelo mesmo padrão
s=$(mktemp); printf '%s\n' "x ${HP}/alguem/y" > "$s"; test -s "$s"; grep -q "$HP" "$s"; rm -f "$s"
python scripts/check_technical_postexec.py "$T"
python scripts/check_stage_issue.py
```

(A saída dos blocos A14, A8, A10, A11 e do laço de tokens é colada no PR.)

### Verificações funcionais

- [ ] **Artefato novo consumível por fora (RUNBOOK Passo 10, último
      quilômetro):** no e2e (A10),
      `<data_root>/gold/asset=<a>/parent_sweep_id=<p>/current/MANIFEST.json`
      existe com `status = COMPLETED`, lista as cinco tabelas e o
      `preregistration_ref`; `read_parquet` do DuckDB sobre
      `current/gold_dm_results.parquet` devolve (k − 1)·2·2 linhas com
      `p_value`, `adjusted_p_value` e `rejected` preenchidos, e
      `current/gold_mcs_results.parquet` k·2·2 linhas com `mcs_p_value`,
      `included`, `reps = 1000` e a seed declarada.
- [ ] Rerun sem apagar dá as mesmas linhas; silver com lacuna interior dá uma
      geração `BLOCKED` só com `gold_quality_checks` cuja linha
      `alignment_check`/`interior_gap` diz por quê; o outro cohort segue
      byte-igual.
- [ ] Sem cohort real: a execução sobre o silver AAPL é da 8.1 (concept §1).

### Checklist de fechamento da Stage

- [ ] Todas as Tasks commitadas, cada uma com o seu gate (T1/T2/T3) verde;
      Checkpoints C após 03, 06, 09 e 12.
- [ ] `make check` verde no branch (após rebase em `origin/develop`);
      cobertura por arquivo (A14) colada.
- [ ] Laço de tokens da matriz verde, saída colada.
- [ ] `scripts/arch_baseline.toml` e `test_port_coverage_gate.py` sem
      `GoldStore`/`GoldBuilder`/`SilverTableReader` (ADR 6.1.0005).
- [ ] §7 com as decisões de detalhe do §1 efetivamente aplicadas, a entrada
      única do custo do MCS (Task 12), o `[finding]` do ponto de chamada novo
      para a #118 (`window_deficits`) e os `[finding]`s dos encaminhamentos
      do concept §7 (perfis de §Fora do escopo para a 6.5/8.3; redação da
      linha 6.5 do roadmap).
- [ ] Commit final `stage 6.4: complete` aplicado (pós-auditoria).
- [ ] `roadmap.md`: Stage 6.4 marcada `done`, `updated_at` e
      `last_reviewed_at` no fechamento.
- [ ] ADRs 6.4.0001–0008 em `accepted`.
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo.

## 4. Ordem de dependência entre Tasks

```
Task 01 (validadores 6.2) ──────────────────────────────────────────┐
Task 02 (identificador shared) ────────────────────────────────────┐│
Task 03 (VOs) ─► Task 04 (SeriesAssembly) ─► Task 05 (checks) ─► Task 06 (HorizonReports + ordem)
Tasks 01, 02, 05, 06 ─► Task 07 (DTOs + port GoldStore; baseline +) ─► Task 08 (ParquetGoldStore; baseline −)
Task 07 ─► Task 09 (port GoldBuilder; baseline +) ─► Task 10 (cinco builders; baseline −)
Tasks 04–10 ─► Task 11 (SilverTableReader + RefreshGold) ─► Task 12 (wiring + e2e)
Tasks 01–12 ─► (rebase em origin/develop) ─► Task 13 (roadmap)
```

- A Task 01 vem primeiro porque o `RefreshParameters` (07) e o passo de
  pré-condições (05) consomem `validate_bootstrap_parameters`,
  `validate_mcs_reps` e `MIN_MODELS`; a 02 antes da 07 porque o
  `GoldPartition` consome `validate_path_identifier`.
- A 05 depende da 04 (o `AssembledCohort` montado alimenta os checks e os
  testes); a 06 depende da 04 (amostras); a 07 da 05/06 (`GoldInputs` carrega
  `QualityCheckResult`, `BlockEstimate` e `HorizonReport`).
- 07 → 08 e 09 → 10 são adjacentes: janela de baseline de exatamente um
  commit (ADR 6.1.0005).
- A 11 junta o port `SilverTableReader` ao seu primeiro consumidor: o real já
  existe, então não há baseline nem adapter novo.
- A 13 fecha: o roadmap descreve arquivos e contratos que já existem.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Valor não-finito no silver (`value_guardrail` NaN) faz a `CoverageSeries` erguer dentro do `SeriesAssembly` | Propaga como C7 (nada publicado, geração anterior viva) — não é regra de I3–I10; se aparecer no cohort real (8.1), `[finding]` para a 6.5/8.1 decidir se vira achado; não inventar tratamento aqui |
| `pyarrow` inferir tipos diferentes entre reruns (coluna toda `None` → `null`) e a comparação do e2e falhar | Comparação célula a célula por DuckDB (`SELECT *` ordenado pela chave), NaN = NaN; os builders emitem sempre as mesmas colunas (`GoldTable` valida); se o tipo da coluna importar, schema explícito por tabela no adapter com `[decision]` |
| `os.replace` de diretório no bind mount `9p` falhar com `errno 39` quando o destino existe | O algoritmo nunca renomeia sobre destino existente (`current → .previous` primeiro, `.previous` sobrante removido antes); a sonda do ADR 6.4.0005 confirmou; se falhar no container, HALT à sessão mestra (muda o mecanismo do ADR) |
| `ArchMcs.optimal_block_length` erguer outra exceção além de `ArithmeticError` numa série que passa o validador | Propaga (C7, concept I11 iii) — é o contrato; registrar o caso em §7 e subir à sessão mestra se ocorrer no e2e |
| `check_port_coverage` não reconhecer o `ParquetAnalyticsRepository` como real do `SilverTableReader` | A docstring cita o port (heurística documentada no script); conferir com `--list` na Task 11 antes do commit; nunca abrir entrada no baseline |
| `check_fake_parity` acusar bloco idêntico fake × adapter (store/builders) | O `InMemoryGoldStore` guarda dicionários, o real escreve arquivos; o `FakeGoldBuilder` não reusa mapeamento dos builders reais; regra compartilhada sobe para o domínio/DTO |
| Cobertura < 90 % nos ramos dos `__post_init__` e nos 19 achados | Um teste por ramo e por regra (tokens); `# pragma: no cover` só comentado e em ramo comprovadamente inalcançável |
| e2e lento (`ArchMcs` real, 2 horizontes × 2 esquemas × `reps = 1000`, `import arch` 8 s a frio) | Medido no §1 (< 1 s por par horizonte/esquema com T = 10³); T ≈ 60 no e2e; `--durations=5` no bloco da Task 12; `slow` só se passar de minutos, com `[decision]` |
| Rebase conflitar em `docs/roadmap.md` (Stages vizinhas em voo) ou em `.importlinter`/`LAYOUT.md` | `git fetch && git rebase origin/develop` antes da Task 13 e de novo no PR; manter as duas edições; rerodar os greps da Task 13 e da Task 04 depois de cada rebase |
| Verde falso por shell (`!` sob `set -e`, `grep -q` num pipe com `pipefail`, arquivo lido em outro `docker run`) | Convenção do §1: um `bash -euo pipefail -c` por bloco, negação por `if …; then exit 1; fi`, saída em arquivo antes do `grep`, `test -s` antes de ler |

## 6. Referências

- [`./concept.md`](./concept.md) — escopo, contratos (§4), invariantes (§5),
  erros (§6), decisões D1–D9 (§7), integrações (§8), modelo de dados (§9),
  critérios (§11).
- ADRs desta Stage:
  [`6.4.0001`](../../adr/6_4_0001-gold-builder-dag-graphlib-declared-dependencies.md),
  [`6.4.0002`](../../adr/6_4_0002-quality-checks-severity-and-persisted-results.md),
  [`6.4.0003`](../../adr/6_4_0003-single-observation-verified-not-rededuplicated.md),
  [`6.4.0004`](../../adr/6_4_0004-evaluation-inputs-silver-reader-port-and-medallion-dataset.md),
  [`6.4.0005`](../../adr/6_4_0005-gold-full-refresh-per-cohort-partition.md),
  [`6.4.0006`](../../adr/6_4_0006-refresh-parameters-explicit-no-domain-defaults.md),
  [`6.4.0007`](../../adr/6_4_0007-gold-persists-both-samples-identified.md),
  [`6.4.0008`](../../adr/6_4_0008-no-runtime-library-cross-check-in-gold.md);
  relacionados: [`6.1.0002`](../../adr/6_1_0002-coverage-series-aligned-input-vo.md),
  [`6.1.0005`](../../adr/6_1_0005-transient-port-coverage-baseline-between-port-and-first-adapter.md),
  [`6.2.0004`](../../adr/6_2_0004-mcs-procedure-in-domain-over-backend-bootstrap-indices.md),
  [`6.2.0005`](../../adr/6_2_0005-mcs-block-length-ceiling-integer.md),
  [`0.0.0053`](../../adr/0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md),
  [`0.0.0055`](../../adr/0_0_0055-tiered-quality-gates.md).
- Doc de domínio: [`probabilistic-forecast-evaluation.md`](../../domain/evaluation/probabilistic-forecast-evaluation.md)
  §2.1, §2.7, §5.3, §6.5, §6.7–§6.9, §8.2.
- [`../../LAYOUT.md`](../../LAYOUT.md) §2, §3, §7; [`../../PIPELINE.md`](../../PIPELINE.md) §4.3;
  [`../../RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) §Gates em camadas;
  [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §2, §6.
- Skills: `task-ordering-hex`, `hex-arch-python`, `repository-pattern`,
  `composition-root`, `orchestrator-design`, `pytest-with-fakes`,
  `import-linter-rules`.
- Stages de referência: [`../6.2-paired-inference-dm-mcs-holm/technical.md`](../6.2-paired-inference-dm-mcs-holm/technical.md),
  [`../6.3-calibration-risk-backtests/technical.md`](../6.3-calibration-risk-backtests/technical.md) (+ §7).
- Issues: [#117](https://github.com/MarceloSanC/financial-forecasting/issues/117),
  [#118](https://github.com/MarceloSanC/financial-forecasting/issues/118),
  [#119](https://github.com/MarceloSanC/financial-forecasting/issues/119),
  [#120](https://github.com/MarceloSanC/financial-forecasting/issues/120).
- Python `graphlib`, `os.replace`, `math.fsum`; pyarrow `Table.from_pylist`,
  `parquet.write_table`; DuckDB `read_parquet`.

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a Fase 4. Apenas esta seção é editável após
> `status: done`. Cada entrada carrega data + autor.

### 2026-09-29 — [decision] Task 01: validadores públicos da 6.2 sem mudança de mensagem — Claude (Opus 5.5)
**Contexto:** decisões de detalhe planejadas no §1 (`MIN_MODELS` no VO,
`validate_bootstrap_parameters`, `validate_mcs_reps` com a mensagem dupla).
**Razão:** executadas como planejado. `MIN_MODELS: Final = 2` mora em
`paired_loss_series.py` e a fábrica o importa (mesmo objeto, sem `_MIN_MODELS`);
`validate_bootstrap_parameters(*, reps, seed)` é chamado por
`validate_bootstrap_request` depois de `n_obs`/`block_size` (mesma ordem e
mensagens); `validate_mcs_reps` ergue `"reps must be >= 1000 (the MCS needs reps >=
1000), got 999"` e substitui as duas comparações inline (`McsReport.__post_init__`
e `ModelConfidenceSet.evaluate`), no mesmo ponto da sequência de cada uma. Os
quatro arquivos de teste da 6.2 só ganharam linhas (`+`): as expectativas
existentes (`"reps must be >= 1000"`, `"reps >= 1000"`, `"k >= 2"`) passam sem
edição. Provado por `test_mcs_vs_arch.py::mcs_reps_validator`,
`::mcs_reps_single_owner` (monkeypatch nas duas pontas),
`test_bootstrap_indices.py::bootstrap_request_delegates` e
`test_paired_pinball_losses.py::factory_imports_min_models`.

### 2026-09-29 — [decision] Task 02: regra de identificador de caminho em `shared/domain` — Claude (Opus 5.5)
**Contexto:** decisão de detalhe planejada no §1 (C3; ADR 6.4.0005 item 1): o padrão
`^[A-Za-z0-9._-]+$` estava compilado no `ParquetMedallionStore` e no
`FakeMedallionStore`.
**Razão:** executada como planejado. `PATH_IDENTIFIER_PATTERN` e
`validate_path_identifier(value, *, field)` (com `fullmatch`; não-`str` erguem) moram em
`shared/domain/services/path_identifier.py`; adapter e fake apagaram os seus
`_READ_ONLY_ASSET_PATTERN` (e o `import re`) e chamam o validador com
`field=f"read-only pair ({layer!r}, {table!r}) asset filter"` — mensagem
byte-idêntica à anterior; `test_medallion_store_contract.py` verde sem alteração. O
grep do bloco acha um único `re.compile` do padrão em `src/` + `tests/fakes/`. Os casos
rejeitados incluem `"AAPL\n"`, `"\nAAPL"`, `a*b` e `bytes` além da lista do critério.

### 2026-09-29 — [deviation] Task 03: `sum([0.1]*10)` dá 1.0 no Python 3.12 — Claude (Opus 5.5)
**Contexto:** o critério de aceite da Task 03 diz "resumo com `math.fsum` exato de
`[0.1]*10` (igual a `1.0`, onde `sum` não é)". Na execução (Python 3.12.13 do container)
`sum((0.1,)*10) == 1.0`: desde o 3.12 o `sum` builtin de floats usa soma compensada
(Neumaier — "What's New In Python 3.12", `sum()`), então a premissa "onde `sum` não é"
é falsa nesta versão.
**Razão:** o que o critério quer provar (o resumo usa soma exata) continua de pé com
duas referências em `test_gold_value_objects.py::realized_summary`: (a) `[0.1]*10`
contra a dobra ingênua `functools.reduce(operator.add, …)` (0.9999999999999999), com
`returns_fsum == 1.0`; (b) — acrescentada após o Checkpoint C bloco 1 (achado M1: (a)
não mata o mutante "`math.fsum` → `sum` builtin") — `xs = (1e16, 1e-16, -2.0, 1.0, 3.0,
2.0**53)`, medida no container (Python 3.12.13): `math.fsum(xs) = 1.9007199254740996e+16`
e `sum(xs) = 1.900719925474099e+16`; o teste exige `returns_fsum == math.fsum(xs)` e
`!= sum(xs)`. O VO continua com `math.fsum` como o §1 manda. Sem mudança de contrato.

### 2026-09-29 — [decision] Task 03: helpers de forma nos VOs de entrada e coerência extra do `AssembledCohort` — Claude (Opus 5.5)
**Contexto:** `ForecastRecord`, `CohortRun` e `AlignmentFinding`/`HorizonSamples`
repetem "str não-vazia", "seed int não-`bool` ou `None`" e "fold str ou `None`".
**Razão:** uma escrita só, em `forecast_record.py` (o primeiro VO de entrada):
`check_non_empty_str`, `check_optional_seed`, `check_optional_fold`, importados por
`cohort_run.py` e `assembled_cohort.py` (direção VO → VO, sem arquivo novo fora da
lista da Task). `quantile_level` exige `float` (não `int`) finito;
`value_raw`/`value_guardrail` só o tipo `float`. `RealizedReturns` guarda o índice
por timestamp num campo `init=False, compare=False` (construído uma vez; igualdade e
`replace` intactos). Além do que o §2 lista, o `AssembledCohort` sem achado exige
`(horizon, n_common)` de cada `HorizonSamples` = `alignment.common_points` — a mesma T
nos dois lugares, sem segunda fonte. O gate de pureza passou a
`_UNIT_DIR.rglob("*.py")` (via `_scan(root)`) e as violações citam o caminho, não só
o nome (dois arquivos homônimos em subpacotes diferentes seriam indistinguíveis);
`purity_scans_subpackages` grava `gold/deeper/test_impure.py` num `tmp_path` e prova
que a varredura o acusa. Após o Checkpoint C bloco 1 (achados M2/L3): `seeds`/`full`/
`common` do `HorizonSamples` precisam ser `Mapping` (senão `ValueError` nomeando o
campo) e o VO guarda `MappingProxyType(dict(v))` — mutar o dict de origem depois da
construção não altera o VO validado (`samples_mappings_frozen_copy`).

### 2026-09-29 — [finding] Checkpoint C bloco 1 (I3) → Task 07: tipo de `reps` antes do piso do MCS — Claude (Opus 5.5)
**Contexto:** `validate_mcs_reps` (Task 01) só compara `reps < MIN_MCS_REPS`; não
checa tipo (`True`, `1000.5`, `"x"` passam ou erguem `TypeError`). No `McsReport` e no
`evaluate` o tipo já foi validado antes (`validate_bootstrap_request` / `BootstrapIndices`).
**Encaminhamento:** na Task 07, o `RefreshParameters.__post_init__` chama
`validate_bootstrap_parameters(reps=…, seed=…)` **antes** de `validate_mcs_reps(reps)`,
e o teste `parameters_owner_messages` cobre `reps=True`/`1000.0` com a mensagem do
dono do tipo.

### 2026-09-29 — [decision] Task 04: valor não-finito em `value_guardrail` ergue (não é achado) — Claude (Opus 5.5)
**Contexto:** fork levantado no Checkpoint C bloco 1 (B6): um ponto alinhado em I3–I10
mas com `value_guardrail` não-finito — achado de alinhamento ou exceção?
**Razão (docs primeiro):** o D1 ("achados em vez de exceção") cobre as regras de
alinhamento I3–I10, que têm dono no `SeriesAssembly` e um tipo no `AlignmentKind`
(19 valores, contrato do concept §4 — criar um 20º mudaria o contrato). Finitude não é
regra de alinhamento: o dono é a `CoverageSeries`, e o ADR 6.1.0002 decide o caso —
item 5 "Non-finite ⇒ raise, never drop" e o contexto "the modeling adapters already
raise on non-finite emission (5.2/5.3 C5), so a non-finite value reaching evaluation
is an upstream invariant violation, not a data condition". Logo o `ValueError` da
`CoverageSeries` propaga pelo `assemble` (C7 do concept: erro fora de C2–C6 propaga,
nada é publicado). Sem ADR novo: a decisão já tem dono (ADR 6.1.0002). Provado por
`test_series_assembly.py::test_non_finite_guardrail_raises_not_finding`.

### 2026-09-29 — [decision] Task 04: detalhes do `SeriesAssembly` — Claude (Opus 5.5)
**Contexto:** escolhas abaixo do limiar do concept, feitas ao implementar a sequência
do §2 Task 04.
**Razão:**
- **Erro de chamada (`ValueError`), não achado:** `run_id` repetido nos `runs` (PK do
  `dim_run`) e registro cujo `run_id` não está nos `runs` (a leitura descarta os fatos
  fora do cohort — ADR 6.4.0004 item 2; e `seed`/`fold` do registro vêm da junção com o
  `dim_run`, então o registro sem run não existe numa chamada correta).
- **Escopo dos achados:** `multiple_feature_sets` e `required_model_missing`/
  `fold_coverage` sem horizonte; `grid_divergent` um por horizonte (`model=None`,
  detalhe com a grade de cada modelo); `model_version_mismatch` por (horizonte, run);
  `duplicate_point`, `decision_index_mismatch`, `horizon_label_mismatch`,
  `grid_incomplete`, `guardrail_flag_mismatch` por ponto; `common_sample_too_short` por
  horizonte. Achados idênticos (mesmo tipo, escopo e detalhe — ex. um por nível do
  mesmo ponto) são deduplicados; o `alignment_check` (Task 05) agrega as ocorrências
  por (tipo, escopo).
- **Série (modelo, seed)** = união dos runs (folds) do par; o universo de pares vem
  dos `runs`. Folds do par vêm dos `runs` (o run sem predição é `orphan_run`, não
  `fold_coverage`).
- **`common_points`** registra (h, T) só com T ≥ 1 (interseção vazia fica só no
  achado — pedido do Checkpoint C bloco 1, B6); o T mínimo consulta
  `check_points(T, h)` e `MIN_BLOCK_LENGTH_OBS` (donos 6.2) e a mensagem do dono vai no
  `detail`.
- **Fixture:** `gold/conftest.py::make_cohort` guarda o ponto especial em
  `Cohort.special` (valores persistidos fora do `from_raw`), e os mutadores são
  funções puras sobre o `Cohort` imutável.

### 2026-09-29 — [decision] Task 05: forma dos resultados e coerência do registry — Claude (Opus 5.5)
**Contexto:** detalhes abaixo do limiar do concept ao implementar o ADR 6.4.0002.
**Razão:**
- **`kind` das linhas que não são achado:** `alignment_check` PASS → `common_sample_size`
  (`value` = T); `statistical_preconditions` PASS → `preconditions_met`, FAIL de k →
  `insufficient_models` (`value` = k), SKIPPED → `assembly_failed`;
  `degeneracy_check` → `degeneracy_rate` / `assembly_failed`; `realized_provenance` →
  `target_return_fsum`.
- **Uma escrita do resultado:** `registry.result_of(check, outcome, kind, …)` preenche
  `check`/`severity` a partir do próprio check; o `QualityCheckRegistry.run` ergue
  `ValueError` se um check devolver resultado com outro nome ou severidade (erro de
  programação), e `QualityCheckResult.is_blocking` é a regra única ERROR + FAIL que o
  `is_blocking(results)` consulta.
- **`QualityCheckContext`** guarda `paired`/`block_estimates` como
  `MappingProxyType` (mesma disciplina do `HorizonSamples`, Checkpoint C bloco 1) e
  exige que as estimativas de um horizonte cubram, em ordem, os `model_pairs()` da
  série pareada desse horizonte — um horizonte sem estimativa para algum par daria
  PASS falso.
- **`BlockEstimate.detail`** é obrigatório (não-vazio) só com `reason`; com `value`
  pode ser vazio. O FAIL agrega por (motivo, horizonte) na ordem do `UndefinedReason`,
  com o primeiro par e o seu detalhe.

### 2026-09-29 — [decision] Task 06: ordem das linhas do `HorizonReports` e validação do `gold_build_order` — Claude (Opus 5.5)
**Contexto:** detalhes abaixo do limiar do concept (D5, D7).
**Razão:**
- **Ordem determinística:** `series` por modelo (ordenado) → seed (`None` antes de
  int) → amostra (`model_full`, `common`); `calibration` por `include_degenerate`
  (`False`, `True`) → intervalos (ordem de `symmetric_pairs`) → caudas (ordem de
  `levels`, sem 0,5), cada sequência seguida das suas sub-séries DGT quando
  `is_multi_step(h)` (a regra única do slice).
- **Coerência do `paired`:** além de horizonte e modelos (critério do §2), o
  `HorizonReports` exige que os `target_timestamps` do `paired` sejam os da amostra
  comum — a série que foi ao backend é a da interseção (ADR 6.4.0007). `band_levels` e
  `dm_variance_estimators` vazios erguem (o DTO da Task 07 também os valida).
- **`gold_build_order`:** valida forma (nome `str` não-vazio, dependências
  `frozenset`), duplicata, auto-dependência e dependência não registrada antes de
  montar o grafo; insere no `TopologicalSorter` em ordem de nome com dependências
  ordenadas (ordem idêntica em 20 permutações do registro dos cinco builders).

<!-- END: post-execution -->
