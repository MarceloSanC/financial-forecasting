---
title: Technical — Stage 7.1 — Motor de inferência (grade a partir do checkpoint, partição calib, reprodução bit a bit)
description: Plano de execução da Stage 7.1 em 12 Tasks inside-out (1 Task = 1 commit) — índice do cohort só de teste, helpers do treinador extraídos, ports e adapter de checkpoint no modeling, predição a partir do checkpoint pela mesma receita, use cases fornecedores, slice inference sob os gates, ports do consumidor, RunInference, manifesto JSON, wiring e CLI infer com ponta a ponta — e a etapa final de execução real sobre o cohort aapl_confirmatory r0, sem métrica
when-use: Consultar durante a Fase 4 (execução) da Stage 7.1; cada Task tem arquivos (lista fechada), testes a escrever primeiro, critério de aceite do concept que cobre e verificação; a Etapa E traz o comando da execução real
keywords: [technical, plano de execução, inference-engine, inference, checkpoint, checkpoint-locator, tft-checkpoint-predictor, calib, reproduction, strict, tolerance, manifest, write-ahead, cohort-run-index, port-coverage, import-linter, cli, blinding]
status: done
created_at: 2026-10-06
updated_at: 2026-10-06
stage_id: 7.1-inference-engine
stage_title: Motor de inferência
step_id: 7
step_title: Inferência, conformal, explicabilidade e API
depends_on: [5.4-tft-trainer, 4.3-prediction-persister]
concept_ref: ./concept.md
issue_id: 153
branch: feat/153-7-1-inference-engine
tasks_count: 12
---

# Technical — Stage 7.1 — Motor de inferência

> **Como usar este documento (para code assistant):**
> 1. Ler §1 inteiro antes da Task 01 (decisões de forma fixadas aqui).
> 2. Executar as Tasks na ordem de §2. **1 Task = 1 commit.** A lista de
>    arquivos de cada Task é **fechada**: tocar arquivo fora dela = parar e
>    perguntar (RUNBOOK Passo 8, "Escopo estrito"). Arquivos `__init__.py`
>    marcados *(pacote)* são marcadores vazios ou de uma linha de docstring;
>    **pacotes não contam** na contagem de arquivos da Task (PIPELINE §4.3
>    item 2), mas estão na lista fechada.
> 3. Escrever primeiro os testes listados em "Testes primeiro" (vermelho),
>    depois o código (verde). **T1 verde antes de todo commit**; as camadas
>    (T1/T2/T3) estão em [RUNBOOK §Gates em camadas](../../RUNBOOK-STAGE-LIFECYCLE.md#gates-em-camadas)
>    e cada Task diz qual camada é o seu gate de commit.
> 4. Commit: `<type>(<escopo>): <descrição> [7.1/task-NN]`, body em bullets,
>    `Refs #153`, subject ≤ 100 caracteres, mensagem UTF-8 sem BOM por
>    `git commit -F` ([`CONVENTIONS.md`](../../CONVENTIONS.md) §4).
> 5. Algo não previsto em §1–§6, no concept ou nos ADRs → pausar, perguntar com
>    opções, registrar em §7. Nunca propagar em silêncio.
> 6. Depois da Task 12: §3 (gate de saída), incluindo a **Etapa E** (execução
>    real) e o commit `stage 7.1: complete`.
>
> **Stage = 1 branch:** `feat/153-7-1-inference-engine`, worktree própria.
>
> **Cegamento (I13, inegociável).** Nenhuma Task, teste ou etapa desta Stage
> calcula escore, cobertura, largura ou qualquer função de predição × realizado
> sobre o cohort `aapl_confirmatory-r0-665f45d9169a`. Testes usam dado
> sintético. A Etapa E só grava predições de `calib` e o manifesto; a
> reprodução compara predição com predição. Nada de `evaluation` é chamado.

## 1. Contexto e estratégia de execução

### Resumo

O concept aprovado ([`concept.md`](./concept.md), ADRs
[7.1.0001](../../adr/7_1_0001-checkpoint-prediction-supplied-by-modeling-through-consumer-port.md)–[7.1.0004](../../adr/7_1_0004-checkpoint-resolution-before-load-and-write-ahead-inference-manifest.md))
pede três coisas: **(A)** no `modeling`, resolver o checkpoint de cada run sem
carregá-lo e predizer a partir dele pela **mesma** receita de dataset e pelo
**mesmo** `_emit` do treinador; **(B)** um slice `inference` novo cujo use case
`RunInference` confere ambiente, `dim_run` e manifesto **antes** de qualquer
unpickle, prova que o teste re-predito reproduz o `value_raw` do silver
(`strict` = igualdade exata; `tolerance` = regra do `assert_close` no espaço
normalizado) e grava a partição `calib` em `fact_oos_predictions` por
complementação idempotente com manifesto write-ahead; **(C)** a correção do
índice do cohort (só linhas de teste) antes da primeira linha de calib existir.
A execução real sobre o r0 fecha a Stage (Etapa E, §2).

### Estratégia (ordem e porquê)

TDD inside-out (skill `task-ordering-hex`), com as exceções declaradas:

1. **Correção do índice primeiro (Task 01).** I10 tem de valer antes de qualquer
   código capaz de gravar `calib`; é também a única mudança em código já
   usado pelo `verify` da 5.5.
2. **Extrações antes do código novo (Task 02).** Identidade do run, diretório do
   artefato, leitura do painel, guarda de emissão, conferência de declarações e
   construção `CohortSpec → TrainTftCommand` passam a ser funções públicas,
   **sem mudar valor persistido algum** (goldens da 5.4 verdes sem atualização).
   O código novo das Tasks 04–05 só chama essas funções — nunca as recopia.
3. **Fornecedor antes do consumidor.** Ports-out e adapters do `modeling`
   (Tasks 03–04), depois os use cases fornecedores (Task 05). Só então o slice
   `inference` nasce (Task 06), já sob os contratos do import-linter, e recebe
   os ports do consumidor (Tasks 07–08) — todos com real já existente, logo sem
   entrada de baseline do `port-coverage`.
4. **Use case com fakes (Task 09), adapter real (Task 10), wiring (Task 11),
   CLI + ponta a ponta (Task 12).**
5. **Exceções declaradas à regra 4 do PIPELINE §4.3 (port × adapter):**
   - Task 03: `CheckpointLocator` (1 método) e `FilesystemCheckpointLocator`
     (wrapper stdlib de listagem + hash) no mesmo commit — ambos triviais.
   - `TftCheckpointPredictor` (Task 03) e `InferenceManifest` (Task 09) nascem
     **sem** adapter real, pelo padrão ratificado do
     [ADR 6.1.0005](../../adr/6_1_0005-transient-port-coverage-baseline-between-port-and-first-adapter.md):
     a Task do port acrescenta a entrada temporária em
     `scripts/arch_baseline.toml` (`issue = 153` e `motivo` citando o ADR 6.1.0005 — campo obrigatório no `arch_baseline_lib.py`) **e**, no mesmo commit, troca
     a lista literal de `test_real_repo_violations_are_exactly_the_declared_baseline`
     em `tests/architecture/test_port_coverage_gate.py` (hoje `["Hasher"]`) para
     `["Hasher", "<Port>"]`, com comentário citando o ADR 6.1.0005; a Task do
     adapter (04 e 10) reverte as duas edições. As quatro Tasks são T3. O gate
     de saída exige `scripts/arch_baseline.toml` sem diferença contra o
     `develop` e a lista literal de volta a `["Hasher"]`.
   - **Teste `check_port_coverage` vácuo para homônimos.** O gate é cego a
     slice: indexa fakes por nome de classe e escolhe **um** contrato por port
     ordenando por caminho. Para os três ports espelho do `inference`
     (`RuntimeEnvironmentProbe`, `PredictionPersister`, `SilverTableReader`) ele
     fica verde só porque os homônimos do `modeling`/`evaluation` já estão
     cobertos — a prova real de que o port do inference é satisfeito é a fixture
     do contrato tipada pelo Protocol **do inference** + mypy. A Task 08 ajusta
     `test_port_coverage_gate.py` para indexar por `(slice, nome)` e conferir
     cada contrato pelo predicado do próprio gate (ver lá).
6. **Tasks acima de 5 arquivos** (pacotes não contam; justificadas na própria
   Task): 03 (dois ports de um método acoplados pela função de hash, mais o par
   baseline/teste do gate do ADR 6.1.0005), 04 (reversão do par do ADR
   6.1.0005 e helper do checkpoint de teste), 06 (contratos de import + ADR),
   08 (quatro declarações de Protocol, três com assinatura copiada do
   fornecedor, e o teste do gate que passa a distinguir homônimos), 09 (o use
   case cria as arestas de dados que `.importlinter` e LAYOUT declaram no mesmo
   commit — a lista `ignore_imports` reprova exceção que não casa — e o par do
   ADR 6.1.0005) e 12 (CLI + ponta a ponta: o comando é fino e só o fluxo
   inteiro o testa).
7. **Execução real = Etapa E, não Task** (concept §12): não produz código; a
   evidência vai para §7 num commit `docs(inference): … [7.1/--]`.

### Decisões de forma fixadas aqui (o concept §13 deixou para a Fase 3B)

- **Nomes e casas das exceções** (todas `ApplicationError`, salvo `ValueError`
  de validação de comando e o `ModelTrainingError` existente):
  - `modeling/application/ports/out/checkpoint_locator.py`:
    `CheckpointNotFoundError`, `AmbiguousCheckpointError` (erguidas pelo
    adapter; precedente: `CohortRunLockedError` no módulo do port).
  - `modeling/application/ports/out/tft_checkpoint_predictor.py`:
    `CheckpointMismatchError` (C4), `ArtifactChangedError` (C10, lado modeling).
  - `modeling/application/use_cases/resolve_tft_checkpoints.py`:
    `IncompleteCohortError` (C14).
  - `modeling/application/use_cases/predict_tft_from_checkpoints.py`:
    `UnknownRunError` (C6, lado modeling).
  - `inference/application/use_cases/run_inference.py` (precedente 5.5:
    exceções no módulo do use case): `CohortNotFrozenError` (C1, local do
    inference — homônima da do modeling, **sem** aresta nova),
    `ReproductionError`, `UnknownRunError`, `ArtifactChangedError`,
    `IncompleteCalibError`, `InferenceEnvironmentError`,
    `CalibProvenanceMissingError`. O `inference` **não** importa as homônimas do
    modeling: elas propagam como `ApplicationError` (concept §4).
- **Função de hash por streaming** (ADR 7.1.0001 item 3): no módulo do port
  `checkpoint_locator.py`, `sha256_of_stream(stream: IO[bytes], *, chunk_size:
  int = 1 << 20) -> str` — stdlib (`hashlib`), **não abre arquivo** (a
  application fica sem I/O): o locator passa o arquivo aberto, o trainer passa
  `io.BytesIO(data)`.
- **Fakes homônimos reaproveitados** (concept §13): os ports do `inference`
  com o mesmo nome e a mesma forma de um port já existente
  (`RuntimeEnvironmentProbe`, `PredictionPersister`, `SilverTableReader`) usam
  o fake existente (`InMemoryRuntimeEnvironmentProbe`,
  `InMemoryPredictionPersister`, `FakeSilverTableReader`) — duplicar a classe
  seria uma segunda definição do mesmo dublê, e o `check_port_coverage.py`
  indexa fakes por nome de classe (a cópia sombrearia a outra em silêncio). As
  suítes `[fake, real]` desses três ficam em `tests/contract/features/inference/`
  tipando a fixture pelo Protocol **do inference** (o mypy prova a conformidade
  estrutural). Fakes novos em `tests/fakes/features/inference/`:
  `InMemoryCheckpointResolver`, `InMemoryCheckpointGridPredictor`,
  `InMemoryInferenceManifest` e `InMemoryCohortLedger` — este último é
  subclasse fina do `InMemoryCohortProgressLedger` existente (sem corpo além
  da docstring; o nome existe para o gate e para tipar pelo port do
  inference).
- **`CohortLedger` reconhecido pelo gate:** o `check_port_coverage.py` acha o
  real por citação do nome do port; a docstring do `JsonCohortProgressLedger`
  passa a citar que ele também satisfaz o port `CohortLedger` do `inference`
  (Task 08). Nenhum import muda.
- **Leitura do painel extraída** (refinamento de I1, sem mudar contrato): o
  corpo de `TrainTft._load_dataset` vira `load_tft_panel(*, store, asset_id) ->
  TftPanel` em `train_tft.py` (timestamps ISO, `target_return`, sessões, matriz,
  `feature_names`, `known_feature_names`) — os dois use cases fornecedores
  montam o painel exatamente como o treino montou.
- **Formato do manifesto** (`<data_root>/inference/<cohort_id>/manifest.json`,
  JSON UTF-8, `indent=2`, `sort_keys=True`, escrita por temporário +
  `os.replace`):

  ```json
  {
    "cohort_id": "<cohort_id>",
    "cohort_environment": {"<chave>": "<valor>"},
    "runs": {
      "<run_id>": {
        "checkpoint_sha256": "...",            "first_write_environment": {...},
        "first_write_settings": {...},         "first_written_at": "<ISO>",
        "status": "started | completed",       "fold_index": 0, "seed": 1,
        "checkpoint_path": "...",              "environment": {...},
        "settings": {...},                     "normalizer_center": 0.0,
        "normalizer_scale": 0.0,               "reproduction_mode": "strict | tolerance",
        "mode_reason": "...",                  "forced": false,
        "justification": null,                 "test_values_compared": 0,
        "max_abs_diff": 0.0,                   "max_normalized_diff": 0.0,
        "calib_rows_written": 0,               "calib_rows_verified": 0,
        "verified_at": "<ISO do Clock>"
      }
    }
  }
  ```

  Regra de mescla (dona única: função pura `merge_run_entry(previous, entry)`
  e a constante `FIRST_WRITE_FIELDS` no módulo do port `inference_manifest.py`,
  usadas pelo adapter **e** pelo fake — fake-parity seguro): os quatro campos
  de primeira escrita (`checkpoint_sha256`, `first_write_environment`,
  `first_write_settings`, `first_written_at`) nunca são sobrescritos; os demais
  são substituídos. `cohort_environment` vem na `entry` e é cabeçalho de
  primeira escrita do arquivo (gravado no primeiro `record_run`, nunca
  sobrescrito). `recorded(cohort_id)` devolve o documento inteiro ou `None`.
- **Conferência de linha de calib já presente** (I8/C8): `value_raw` e
  `value_guardrail` pelo modo; `guardrail_applied` por igualdade só em
  `strict`; `model_version`, `asset`, `feature_set_name`, `schema_version` por
  igualdade com a linha do run em `dim_run`; `timestamp_utc` e
  `target_timestamp_utc` por igualdade com `dataset_timestamps[decision_idx]`
  e `dataset_timestamps[decision_idx + horizon]` da grade devolvida pelo
  fornecedor. É **conferência**, não produção: toda escrita continua pelo
  `PersistPredictions`, que resolve os timestamps por
  `MultiHorizonPredictionPersister.build` (dono único da convenção do
  `target_timestamp`, ADR 4.3.0001); se a convenção do 4.3 mudasse, a
  conferência falharia fechada (nunca grava). Uma
  decisão com conjunto de chaves `(horizonte, nível)` diferente do esperado
  (gravação parcial) também é C8.
- **Fluxo do `RunInference`, ordem exata** (concept §5, I4, ADR 7.1.0004 item 2):
  C1 (`is_frozen`) e C13 (justificativa) → `cohort_id` por `CohortHash` →
  `acquire_writer` → `try`: probe (`code_dirty` → C11) → `ledger.environment`
  (ausente → C11) → `manifest.recorded` → por seed em `spec.seeds`: resolver →
  por resolução: `dim_run` (C6: linha com `run_id` igual, `fold ==
  str(resolution.fold_index)` — o `fold` de `dim_run` é texto —, `seed` igual
  e `model_version == resolution.model_version`) e sha256 × manifesto (C10) →
  predictor com
  `allowed` e `partitions=("test", "calib")`, `num_threads =
  int(cohort_env[THREADS_KEY])` → por run, em ordem de fold: reprodução do
  teste (C7) → C15 → write-ahead / retomada (C11) → calib por decisão (C8) →
  releitura (C9) → `completed`. `finally`: `release_writer`. O silver é lido
  uma vez por seed (`dim_run` do cohort; `fact_oos_predictions` do ativo e do
  feature set) e relido por run para a contagem.
- **Modo** (I6, ADR 7.1.0003 item 3): chaves não-código = união das chaves dos
  dois ambientes menos `CODE_KEYS` e `DIRTY_KEY` (importados do port do
  modeling, nunca redeclarados). Iguais e sem justificativa → `strict`
  (`mode_reason = "non-code keys equal"`); iguais com justificativa válida →
  `tolerance`, `forced = true` (`mode_reason = "forced: cross-environment"`);
  diferentes → `tolerance`, `forced = false` (`mode_reason = "non-code keys
  differ: [<chaves>]"`). Justificativa válida = não vazia e contém `[finding]`.
- **Saída do `infer`** (stdout; contrato da Etapa E):
  `run <run_id> fold <f> seed <s>: <modo> compared <n> max|d| <x:.3e> max|d|/s <y:.3e> calib written <w> verified <v>`
  por run, e no fim
  `inference <cohort_id>: <N> runs (<k> strict, <t> tolerance); calib rows written <W>, verified <V>`.
- **Comandos no container.** Fluxo Docker-only; as worktrees rodam por
  `docker run` avulso (o container de dev monta só o checkout principal). Para
  checks de Task, `$RUN` abaixo (Git Bash); dentro, `uv run --no-sync`:

  ```bash
  WT=feat-153-7-1-inference-engine
  RUN="docker run --rm -v C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/$WT:/app \
    -v C:/Users/Marcelo/Documents/Code/financial-forecasting/.git:/main.git \
    -v financial-forecasting_app-venv:/app/.venv \
    -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app -w /app financial_forecasting-app:dev"
  # uso: MSYS_NO_PATHCONV=1 $RUN sh -c "git config --global --add safe.directory '*'; make check-task SLICE=modeling"
  ```

  Caminhos com barra normal (com `\` o bind mount sai vazio sem erro). Nos
  blocos de verificação abaixo, cada linha roda dentro de `$RUN sh -c "…"`.

### Pré-condições

- Concept `done` (`dabcbe8`) e ADRs 7.1.0001–0004 `accepted`; 5.4, 4.3, 5.5 e
  5.1 em `develop`; gate de domínio #150 mergeado (PR #152).
- Imagem `financial_forecasting-app:dev` e volume `financial-forecasting_app-venv`
  (conferido em 2026-10-06: torch 2.13.0+cpu, lightning 2.6.5,
  pytorch-forecasting 1.8.0, numpy 2.5.0, pandas 2.3.3, pyarrow 24.0.0,
  scikit-learn 1.9.0, `x86_64/12`, 6 threads — as versões gravadas pelo cohort).
- Etapa E: `data/cohorts/aapl/` e `artifacts/` no checkout principal (fora do
  git; 13 MB e 1,6 GB).

### Premissas técnicas

- Python 3.12, mypy strict, `from __future__ import annotations`; imports
  cross-slice de tipo só sob `TYPE_CHECKING` (invisíveis ao import-linter,
  `exclude_type_checking_imports = True`).
- `scripts/check_layout.py`: regra 3b (adapter não importa adapter de outro
  slot), regra 5 (todo slice tem `domain/`, `application/`, `adapters/`),
  regra 6 (hash de identidade só por VO de `shared/`; `hashlib` sobre bytes de
  arquivo não é chamada do port `Hasher`).
- `scripts/check_port_coverage.py`: fake `Fake<X>`/`InMemory<X>`; real = adapter
  que cita o port, ou use case de outro slice com as **mesmas anotações** e
  importado por um contrato `[fake, real]` (#93).
- `make check-task SLICE=…` aceita `analytics_store`, `evaluation`,
  `feature_engineering`, `inference`, `market_data`, `modeling`, `shared`,
  `tooling`; reprova slice sem nenhum diretório de teste.

### Estrutura de pastas afetada

```
.importlinter                                                        (mod, Tasks 06, 09)
docs/LAYOUT.md                                                       (mod, Tasks 06, 09)
docs/adr/7_1_0001-…md (item 4: domain-purity na lista de contratos) (mod, Task 06)
scripts/arch_baseline.toml                                           (mod temporário, Tasks 03/04, 09/10)
tests/architecture/test_port_coverage_gate.py                        (mod, Tasks 03/04, 08, 09/10)
src/financial_forecasting/
├── cli.py                                                           (mod, Task 12)
├── composition_root.py                                              (mod, Task 11)
└── features/
    ├── analytics_store/adapters/out/parquet/parquet_cohort_run_index.py      (mod, 01)
    ├── modeling/
    │   ├── application/ports/out/{checkpoint_locator.py, tft_checkpoint_predictor.py}   (novos, 03)
    │   ├── application/ports/out/{cohort_run_index.py (01), runtime_environment_probe.py (02)}
    │   ├── application/use_cases/{train_tft.py, run_confirmatory_cohort.py}            (mod, 02)
    │   ├── application/use_cases/{resolve_tft_checkpoints.py, predict_tft_from_checkpoints.py} (novos, 05)
    │   ├── adapters/out/filesystem/checkpoint_locator.py                               (novo, 03)
    │   ├── adapters/out/filesystem/json_cohort_progress_ledger.py                      (docstring, 08)
    │   ├── adapters/out/runtime/git_runtime_environment_probe.py                       (mod, 02)
    │   └── adapters/out/pytorch_forecasting/pf_tft_trainer.py                          (mod, 04)
    └── inference/                                                    (novo)
        ├── domain/  application/  adapters/                          (06)
        ├── application/ports/out/{checkpoint_resolver, checkpoint_grid_predictor}.py   (07)
        ├── application/ports/out/{runtime_environment_probe, prediction_persister,
        │                          silver_table_reader, cohort_ledger}.py               (08)
        ├── application/ports/out/inference_manifest.py                                 (09)
        ├── application/use_cases/run_inference.py                                      (09)
        ├── adapters/out/filesystem/json_inference_manifest.py                          (10)
        └── adapters/in/cli/inference_commands.py                                       (12)
tests/
├── fakes/features/modeling/{in_memory_cohort_run_index.py (01), in_memory_checkpoint_locator.py,
│                           in_memory_tft_checkpoint_predictor.py (03)}
├── fakes/features/inference/{in_memory_checkpoint_resolver, in_memory_checkpoint_grid_predictor (07),
│                            in_memory_cohort_ledger (08), in_memory_inference_manifest (09)}.py
├── contract/features/modeling/{test_cohort_run_index_contract (01), test_checkpoint_locator_contract,
│                              test_tft_checkpoint_predictor_contract (03/04), _tft_checkpoint_fixture (04)}.py
├── contract/features/inference/{test_checkpoint_ports_contract (07), test_consumer_mirror_ports_contract (08),
│                               test_inference_manifest_contract (10)}.py
├── unit/features/modeling/application/{test_cohort_tft_helpers (02), _frozen_tft_cohort,
│                                       test_resolve_tft_checkpoints, test_predict_tft_from_checkpoints (05)}.py
├── unit/features/inference/application/test_run_inference.py                    (09)
├── unit/shared/test_composition_root.py (11)    unit/test_cli.py (12)
├── integration/features/evaluation/test_refresh_gold.py                         (mod, 01)
├── integration/features/modeling/test_pf_tft_checkpoint_prediction.py           (04)
├── integration/features/inference/test_run_inference.py                         (12)
└── architecture/{test_import_contracts.py (06), test_port_coverage_gate.py (03/04, 08, 09/10)} (mod)
```

## 2. Tasks

> Faixa saudável: 3–12 Tasks (CONVENTIONS §6). **Esta Stage tem 12**, mais a
> Etapa E (execução real, sem código). A estimativa do concept §12 (11 Tasks)
> ganhou uma Task porque o slice `inference` nasce sob os gates antes dos seus
> ports (Task 06) e os ports do consumidor ficaram em dois commits (07, 08).

### Task 01 — Índice do cohort conta só linhas de teste; avaliação intocada pelo calib (I10)

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/analytics_store/adapters/out/parquet/parquet_cohort_run_index.py`
  - `src/financial_forecasting/features/modeling/application/ports/out/cohort_run_index.py` (só docstring)
  - `tests/fakes/features/modeling/in_memory_cohort_run_index.py`
  - `tests/contract/features/modeling/test_cohort_run_index_contract.py` (só acréscimos)
  - `tests/integration/features/evaluation/test_refresh_gold.py` (só acréscimos)
- **Arquivos a criar:** nenhum.
- **Testes primeiro:**
  - contrato `[fake, real]`: `test_calib_rows_do_not_change_counts_or_targets`
    — o mesmo cohort com e sem linhas `split = "calib"` (real: gravadas pelo
    `PersistPredictions` sobre o silver em `tmp_path`; fake:
    `record(..., split="calib")`) devolve contagens e conjuntos de
    `target_timestamp` idênticos; `test_calib_only_run_counts_as_orphan` — run
    com só linhas de calib aparece com 0 linhas.
  - integração: `test_refresh_gold_identical_with_and_without_calib_rows` — dois
    `data_root` sintéticos iguais exceto por linhas de calib de um run TFT;
    `RefreshGold` (que monta pela `SeriesAssembly`) produz gold idêntico
    (mesmas tabelas, mesmas linhas, mesma ordem).
- **O que fazer (ADR 7.1.0002 item 4):** `ParquetCohortRunIndex` descarta fatos
  com `split != "test"` antes de contar linhas e coletar alvos (constante
  `_TEST_SPLIT = "test"`). Docstring do port: "linhas **de teste** de
  `fact_oos_predictions`". O fake ganha `split: str = "test"` em `record` e
  ignora o registro quando `split != "test"` (os chamadores existentes não
  mudam).
- **Critério de aceite (concept §11 "Índice do cohort (I10)" e "Avaliação
  intocada"):** os dois testes novos verdes nas duas pernas; testes existentes
  do índice, do `RunConfirmatoryCohort` e do `verify` inalterados e verdes.
- **Verificação (T1):**
  ```bash
  uv run pytest tests/contract/features/modeling/test_cohort_run_index_contract.py tests/integration/features/evaluation/test_refresh_gold.py -v
  make check-task SLICE="analytics_store modeling evaluation"
  ```
- **Commit:** `fix(analytics-store): índice do cohort conta só linhas de teste [7.1/task-01]`
  (body: I10; avaliação provada intocada; ADR 7.1.0002 item 4).

---

### Task 02 — Helpers do treinador e do cohort extraídos, sem mudar valor persistido

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/modeling/application/use_cases/train_tft.py`
  - `src/financial_forecasting/features/modeling/application/use_cases/run_confirmatory_cohort.py`
  - `src/financial_forecasting/features/modeling/application/ports/out/runtime_environment_probe.py`
  - `src/financial_forecasting/features/modeling/adapters/out/runtime/git_runtime_environment_probe.py`
- **Arquivos a criar:**
  - `tests/unit/features/modeling/application/test_cohort_tft_helpers.py`
- **Testes primeiro** (`test_cohort_tft_helpers.py`):
  `test_run_id_from_shared_identity_matches_train_tft` (o `run_id` de cada fold
  pela função pública = o que `TrainTft` grava com o fake do trainer);
  `test_artifact_dir_rule_matches_train_tft`;
  `test_tft_command_builder_matches_confirmatory_cohort_units` (o
  `TrainTftCommand` que o `RunConfirmatoryCohort` passa ao `train_tft` — capturado
  por um callable espião — é igual ao da função pública);
  `test_declarations_check_raises_the_cohort_errors` (`DatasetMismatchError`,
  `CohortDeclarationMismatchError` para fingerprint, `feature_set_hash`,
  `pipeline_version` e device);
  `test_emission_guard_names_the_partition` (mensagem `"outside the requested
  calib range"` com `partition="calib"`);
  `test_load_tft_panel_matches_train_tft_dataset`;
  `test_threads_key_is_the_probe_key` (`THREADS_KEY == "torch_threads"` e está
  em `REQUIRED_KEYS`).
- **O que fazer (concept §1 "extração de helpers", ADR 7.1.0001 item 2):**
  - `train_tft.py`: `TftPanel` (frozen) + `load_tft_panel(*, store, asset_id)`
    (corpo de `_load_dataset`, que passa a delegar);
    `tft_run_identity(*, command, feature_names, known_names, fold, hasher) ->
    tuple[str, str]` (corpo de `_identity`, que delega);
    `tft_artifact_dir(artifacts_root: Path, run_id: str) -> Path`;
    `assert_emission_within_request(*, grids, requested_decision_indices,
    horizons, partition: str)` (generaliza `_assert_emission_within_request`;
    `TrainTft` passa `partition="test"` — a mensagem existente `"outside the
    requested test range"` não muda).
  - `run_confirmatory_cohort.py`: `check_cohort_declarations(spec, *, store,
    hasher, modeling_columns, observed_feature_set_hash, pipeline_version,
    supported_device) -> TrainingGrid` (corpo de `_check_declarations`, que
    delega; mesmas exceções e mensagens) e `tft_train_command(spec, *, scope,
    seed, schema_version) -> TrainTftCommand` (o `tft(seed)` de `_units`).
  - Port `runtime_environment_probe.py`: `THREADS_KEY = "torch_threads"`, usado
    em `REQUIRED_KEYS`; o adapter git usa a constante no lugar do literal.
- **Critério de aceite (concept §11 "Sem duplicação", parte):**
  `test_tft_trainer_golden.py`, `test_identity_golden.py`,
  `test_train_tft*.py` e `test_run_confirmatory_cohort.py` verdes **sem
  nenhuma alteração** (`git diff` vazio nesses arquivos); testes novos verdes.
- **Verificação (T1):**
  ```bash
  uv run pytest tests/unit/features/modeling/application/test_cohort_tft_helpers.py -v
  uv run pytest tests/contract/features/modeling/test_tft_trainer_golden.py tests/unit/features/modeling/application/test_identity_golden.py tests/unit/features/modeling/application/test_run_confirmatory_cohort.py -q
  git diff --exit-code HEAD -- tests/contract/features/modeling/test_tft_trainer_golden.py tests/unit/features/modeling/application/test_identity_golden.py 'tests/unit/features/modeling/application/test_train_tft*.py' tests/unit/features/modeling/application/test_run_confirmatory_cohort.py
  make check-task SLICE=modeling
  ```
- **Commit:** `refactor(modeling): extrai identidade, painel e conferências do cohort [7.1/task-02]`

---

### Task 03 — Ports de checkpoint no modeling, fakes e `FilesystemCheckpointLocator`

> **> 5 arquivos, justificado:** dois ports de um método cada, acoplados pela
> função de hash que mora no módulo do locator e que o predictor usa; o adapter
> do locator é wrapper stdlib (exceção declarada à regra 4); o predictor nasce
> sem adapter (baseline temporário).

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/application/ports/out/checkpoint_locator.py`
  - `src/financial_forecasting/features/modeling/application/ports/out/tft_checkpoint_predictor.py`
  - `src/financial_forecasting/features/modeling/adapters/out/filesystem/checkpoint_locator.py`
  - `tests/fakes/features/modeling/in_memory_checkpoint_locator.py`
  - `tests/fakes/features/modeling/in_memory_tft_checkpoint_predictor.py`
  - `tests/contract/features/modeling/test_checkpoint_locator_contract.py`
  - `tests/contract/features/modeling/test_tft_checkpoint_predictor_contract.py` (perna `fake`)
- **Arquivos a modificar:**
  - `scripts/arch_baseline.toml` — entrada temporária `key = "TftCheckpointPredictor"`, `issue = 153`, `motivo` citando o ADR 6.1.0005.
  - `tests/architecture/test_port_coverage_gate.py` — lista literal de
    `test_real_repo_violations_are_exactly_the_declared_baseline` para
    `["Hasher", "TftCheckpointPredictor"]`, comentário citando o ADR 6.1.0005.
- **Testes primeiro:**
  - locator `[fake, real]`: `test_locate_returns_the_single_ckpt_and_its_sha256`,
    `test_locate_without_ckpt_raises_not_found` (mensagem nomeia o diretório),
    `test_locate_with_two_ckpts_raises_ambiguous`; só real:
    `test_locator_module_does_not_import_the_dl_stack` (subprocesso: importa o
    módulo, chama `locate`, imprime `sorted({"torch", "lightning",
    "pytorch_forecasting"} & set(sys.modules))` → `[]`);
    `test_sha256_of_stream_equals_hashlib_of_whole_bytes` (chunk menor que o
    arquivo).
  - predictor `[fake]`: `test_wrong_expected_sha256_raises_artifact_changed`,
    `test_emits_one_entry_per_requested_decision_and_horizon`,
    `test_non_contiguous_decisions_raise_value_error`,
    `test_declared_inputs_mismatch_raises_checkpoint_mismatch`.
- **O que fazer (concept §4 "Ports-out do modeling", C3/C4/C10; ADR 7.1.0001
  item 3, 7.1.0004 item 1):** DTOs `CheckpointLocation(path, sha256)` e
  `TftCheckpointPrediction(grids, normalizer_center, normalizer_scale,
  settings)` (`grids: Mapping[int, GridByHorizon]`); Protocols
  `CheckpointLocator.locate(*, artifact_dir) -> CheckpointLocation` e
  `TftCheckpointPredictor.predict_from_checkpoint(...)` com a assinatura do
  concept §4; exceções e `sha256_of_stream` conforme §1. Adapter
  `FilesystemCheckpointLocator` (stdlib: `pathlib`, `hashlib` via
  `sha256_of_stream`), docstring "satisfaz o port `CheckpointLocator`",
  devolve caminho absoluto. Fakes: locator sobre um `dict` diretório → lista de
  `(nome, bytes)`; predictor com grades configuradas por decisão, sha256
  esperado por caminho e entradas declaradas, registrando as chamadas.
- **Critério de aceite (concept §11 "Adapter", parte: C3 e o subprocesso sem
  pilha de DL):** suítes verdes; `check_port_coverage.py` verde com a entrada
  temporária (e só ela); `test_port_coverage_gate.py` verde com a lista
  ampliada.
- **Verificação (T3 — toca `scripts/arch_baseline.toml` e o teste do gate):**
  ```bash
  uv run pytest tests/contract/features/modeling/test_checkpoint_locator_contract.py tests/contract/features/modeling/test_tft_checkpoint_predictor_contract.py tests/architecture/test_port_coverage_gate.py -v
  uv run python scripts/check_port_coverage.py
  make check
  ```
- **Commit:** `feat(modeling): ports de localização e predição a partir do checkpoint [7.1/task-03]`

---

### Task 04 — `PfTftTrainer.predict_from_checkpoint` pela mesma receita e o mesmo `_emit`

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/modeling/adapters/out/pytorch_forecasting/pf_tft_trainer.py`
  - `tests/contract/features/modeling/test_tft_checkpoint_predictor_contract.py` (perna `real`, marcada `@pytest.mark.slow`)
  - `scripts/arch_baseline.toml` (remove a entrada da Task 03)
  - `tests/architecture/test_port_coverage_gate.py` (lista literal de volta a `["Hasher"]`, comentário da Task 03 removido)
- **Arquivos a criar:**
  - `tests/contract/features/modeling/_tft_checkpoint_fixture.py` — helper
    que treina, uma vez por módulo (`tmp_path_factory`), o TFT minúsculo da
    geometria do contract test do trainer e devolve o caminho do checkpoint, o
    sha256, as entradas do treino e a grade de teste do `train_and_predict`;
    usado pela perna real do contrato e pelo teste de integração abaixo
  - `tests/integration/features/modeling/test_pf_tft_checkpoint_prediction.py`
- **Testes primeiro** (`test_pf_tft_checkpoint_prediction.py`, `integration` +
  `slow`, um treino real minúsculo em fixture de módulo, geometria do contract
  test do trainer):
  `test_checkpoint_prediction_equals_train_and_predict_test_grid` (`==`
  exato, mesmas chaves); `test_prediction_independent_of_global_rng`
  (`torch.manual_seed(1)` × `(2)` antes de cada chamada → grades idênticas);
  `test_prediction_in_subprocess_is_identical` (subprocesso com
  `sys.executable`, grades serializadas por `float.hex`);
  `test_calib_decisions_emit_one_entry_per_decision_and_horizon`;
  `test_wrong_sha_never_calls_the_loader` (spy em
  `TemporalFusionTransformer.load_from_checkpoint` no namespace do módulo);
  `test_loader_receives_the_hashed_bytes_as_file_object` (spy: argumento é
  objeto de arquivo, não `str`/`Path`, e `.getvalue()` = bytes do disco);
  `test_mismatched_levels_or_reals_raise_checkpoint_mismatch`;
  `test_threads_and_deterministic_flag_restored` (antes: threads = N, flag =
  `True`; durante: `num_threads` pedido e flag `False`, lidos por spy em
  `_emit`; depois: N e `True`);
  `test_train_and_checkpoint_paths_share_dataset_helper_and_emit` (spies no
  helper de dataset e em `_emit` contam uma chamada de cada caminho, com o
  mesmo objeto de função); `test_settings_record_the_inference_parameters`
  (`settings` traz `batch_size`, `num_workers="0"`, `accelerator="cpu"`,
  `num_threads`, `deterministic_algorithms="false"`, `cpu_capability`,
  `platform`, `scikit-learn`, com os valores pedidos/lidos). A perna `real` do
  contrato usa o checkpoint de `_tft_checkpoint_fixture.py`.
- **O que fazer (concept §4 contrato do predictor, I1, I3, I7, D2; ADR 7.1.0001
  item 3, 7.1.0003 itens 2 e 7):**
  - Helper de módulo `_prediction_dataset(parameters, frame, *,
    decision_indices, max_horizon)` =
    `TimeSeriesDataSet.from_parameters(parameters,
    frame.iloc[: max(decisões) + max_horizon + 1],
    min_prediction_idx=min(decisões) + 1, min_prediction_length=1,
    stop_randomization=True)`. `build_datasets` passa a montar o dataset de
    predição por ele com `training.get_parameters()` (golden intocado).
  - `predict_from_checkpoint`: lê os bytes **uma vez**; `sha256_of_stream(io.BytesIO(data))`
    ≠ esperado → `ArtifactChangedError` antes de qualquer carga; carga por
    `TemporalFusionTransformer.load_from_checkpoint(io.BytesIO(data))` dentro de
    `_translating_backend_errors` (C5); confere reais conhecidas/desconhecidas,
    `max_prediction_length == max_horizon` e `loss.quantiles ==
    quantile_levels` contra o `dataset_parameters` do checkpoint (C4 →
    `CheckpointMismatchError`, fora da seção traduzida); faixa de decisões
    contígua e crescente (`ValueError`); quadro por `_panel_frame`; dataset pelo
    helper com `model.dataset_parameters` (nada é ajustado — I3); `try/finally`
    com `torch.set_num_threads(num_threads)` e
    `torch.use_deterministic_algorithms(False)`, restaurando os dois; emissão
    por `_emit` com `requested_decisions` = as pedidas; centro/escala lidos do
    normalizador do dataset reconstruído (nunca recalculados); `settings` =
    `batch_size`, `num_workers="0"`, `accelerator="cpu"`, `num_threads`,
    `deterministic_algorithms="false"`, `cpu_capability`
    (`torch.backends.cpu.get_cpu_capability()`), `platform`
    (`platform.platform()`), `scikit-learn` (`importlib.metadata`).
  - Docstring do módulo: satisfaz também o port `TftCheckpointPredictor`.
- **Mutação obrigatória (registrar em §7):** forçar o dropout ativo na predição
  (hook temporário que chama `.train()` nos submódulos `Dropout` depois que o
  loop de predição chama `eval()`), rodar
  `test_prediction_independent_of_global_rng` → tem de falhar; reverter; colar
  a saída em §7.
- **Critério de aceite (concept §11 "Adapter" e "Sem duplicação", parte):**
  todos os testes acima verdes; golden do trainer verde sem atualização;
  baseline e teste do gate de volta ao estado do `develop`; mutação registrada.
- **Verificação (T3 — toca `scripts/arch_baseline.toml` e o teste do gate):**
  ```bash
  uv run pytest tests/integration/features/modeling/test_pf_tft_checkpoint_prediction.py tests/contract/features/modeling/test_tft_checkpoint_predictor_contract.py tests/contract/features/modeling/test_tft_trainer_golden.py tests/architecture/test_port_coverage_gate.py -v
  git diff --exit-code "$(git merge-base origin/develop HEAD)" -- scripts/arch_baseline.toml tests/architecture/test_port_coverage_gate.py
  make check
  ```
- **Commit:** `feat(modeling): predição a partir do checkpoint pela receita do treino [7.1/task-04]`

---

### Task 05 — Use cases `ResolveTftCheckpoints` e `PredictTftFromCheckpoints`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/application/use_cases/resolve_tft_checkpoints.py`
  - `src/financial_forecasting/features/modeling/application/use_cases/predict_tft_from_checkpoints.py`
  - `tests/unit/features/modeling/application/_frozen_tft_cohort.py` (construtor de cohort congelado + painel no `FakeMedallionStore` + runs no `InMemoryCohortRunIndex`; reusado pela Task 07)
  - `tests/unit/features/modeling/application/test_resolve_tft_checkpoints.py`
  - `tests/unit/features/modeling/application/test_predict_tft_from_checkpoints.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro:**
  - resolve: `test_run_ids_equal_what_train_tft_records`,
    `test_artifact_dir_follows_the_train_tft_rule`,
    `test_model_version_is_in_each_resolution`,
    `test_guards_raise_before_locate` (parametrizado: C1 não congelado, C2
    fingerprint / `feature_set_hash` / `pipeline_version` / device, C13 seed ∉
    `spec.seeds`, C14 cohort incompleto — o fake do locator registra zero
    chamadas), `test_locator_errors_propagate` (C3).
  - predict: `test_calib_decisions_are_the_fold_calib_sessions`,
    `test_test_decisions_are_the_fold_test_sessions`,
    `test_run_outside_allowlist_raises_without_predicting` (C6),
    `test_emission_outside_request_raises` (I12, decisão e horizonte),
    `test_guards_raise_before_predicting` (C1, C2, C13 seed, partição fora de
    `{test, calib}`, partições vazias), `test_settings_normalizer_and_sha_are_forwarded`,
    `test_batch_size_and_threads_reach_the_port`.
- **O que fazer (concept §4 "Use cases do modeling", I12, C1/C2/C6/C13/C14):**
  DTOs exatamente como no concept §4. `ResolveTftCheckpoints(*, store, hasher,
  splitter, run_index, locator, artifacts_root, modeling_columns,
  observed_feature_set_hash, pipeline_version, supported_device)`: valida C13
  e C1 antes de I/O → `check_cohort_declarations` (C2) → completude
  (`recorded_run_problems` sobre as chaves `(tft_quantile, s)` de **todas** as
  seeds do spec, lidas do `run_index`; problema → `IncompleteCohortError`,
  C14) → `load_tft_panel` → folds pelo `splitter` → por fold
  `tft_train_command` + `tft_run_identity` + `tft_artifact_dir` →
  `locator.locate`. `PredictTftFromCheckpoints(*, store, hasher, splitter,
  predictor, artifacts_root, modeling_columns, observed_feature_set_hash,
  pipeline_version, supported_device)`: valida comando (C13) e C1 → C2 →
  painel → folds → por fold: `run_id` derivado ∉ `allowed` → `UnknownRunError`
  sem chamar o port; uma chamada ao port por partição pedida (decisões =
  índices das sessões de `fold.test`/`fold.calib`), `batch_size =
  spec.tft_params.batch_size`, `num_threads = command.num_threads`,
  `expected_sha256 = allowed[run_id]`; `assert_emission_within_request(…,
  partition=<p>)`; `dataset_timestamps` do painel; `settings` da primeira
  chamada.
- **Critério de aceite (concept §11 "Use cases do modeling"):** todos os testes
  verdes com fakes; nenhum import de torch/lightning/pytorch_forecasting nos
  dois módulos (`modeling-no-torch-leak` verde).
- **Verificação (T1):**
  ```bash
  uv run pytest tests/unit/features/modeling/application/test_resolve_tft_checkpoints.py tests/unit/features/modeling/application/test_predict_tft_from_checkpoints.py -v
  make check-task SLICE=modeling
  ```
- **Commit:** `feat(modeling): resolução e predição da grade do cohort a partir do checkpoint [7.1/task-05]`

---

### Task 06 — Slice `inference` nasce sob os contratos de import

- **Arquivos a criar** *(pacote)*:
  - `src/financial_forecasting/features/inference/__init__.py`
  - `src/financial_forecasting/features/inference/domain/__init__.py`
  - `src/financial_forecasting/features/inference/application/__init__.py`
  - `src/financial_forecasting/features/inference/adapters/__init__.py`
- **Arquivos a modificar:**
  - `.importlinter` — `inference` como container de `hexagonal-layers`;
    `inference.domain` em `domain-purity` (com comentário no padrão dos
    outros slices); `inference.application` e `inference.domain` em
    `inward-only` e `store-no-storage-leak`; contrato novo `inference-no-torch-leak`
    (`forbidden`; fontes `inference.application`, `inference.domain`; proibidos
    `torch`, `lightning`, `pytorch_forecasting`; comentário com o perímetro do
    ADR 7.1.0001 item 4); `inference` em `bc-independence` (`modules` e `name`),
    sem aresta nova (os ports só terão imports de tipo).
  - `tests/architecture/test_import_contracts.py` — `"inference-no-torch-leak"`
    em `_EXPECTED_CONTRACTS`; casos de quebra intencional.
  - `docs/LAYOUT.md` §7 — perímetro do `bc-independence` com **seis** slices;
    `inference` sem pilha de DL no core.
  - `docs/adr/7_1_0001-checkpoint-prediction-supplied-by-modeling-through-consumer-port.md`
    — edição mínima no item 4: a lista de contratos que o slice integra ganha
    `domain-purity` (hoje lista `hexagonal-layers`, `inward-only`,
    `store-no-storage-leak` e `bc-independence`); nada mais muda no ADR.
- **Testes primeiro** (casos novos em `test_import_contracts.py`):
  `inference-no-torch-leak:inference-application-imports-torch`,
  `inference-no-torch-leak:inference-domain-imports-lightning`,
  `inference-no-torch-leak:inference-application-imports-pytorch-forecasting`,
  `domain-purity:inference-domain-imports-pandas`,
  `hexagonal-layers:inference-domain-imports-application`,
  `inward-only:inference-application-imports-infrastructure` (import de
  `financial_forecasting.shared.infrastructure.config.settings.Settings`),
  `store-no-storage-leak:inference-application-imports-pandas`,
  `bc-independence:inference-imports-new-evaluation-edge`.
- **O que fazer (concept §1 "Gates", I2, I13; ADR 7.1.0001 item 4):** como
  acima. Prova manual exigida pelo concept §11 "Gates": criar
  `inference/application/_taint.py` com `import torch`, rodar `lint-imports` →
  `inference-no-torch-leak` **BROKEN**; apagar → verde; colar as duas saídas
  em §7.
- **Critério de aceite (concept §11 "Gates", parte):** `lint-imports` verde
  com o contrato novo; casos de arquitetura verdes; `check_layout.py` verde
  (regra 5: os três diretórios existem); LAYOUT §7 lista seis slices.
- **Verificação (T3 — toca `.importlinter`):**
  ```bash
  make docs-check
  uv run lint-imports
  uv run python scripts/check_layout.py
  uv run pytest tests/architecture/test_import_contracts.py -v
  make check
  ```
- **Commit:** `feat(inference): slice inference sob os contratos de import [7.1/task-06]`

---

### Task 07 — Ports `CheckpointResolver` e `CheckpointGridPredictor` do inference

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/application/ports/__init__.py` *(pacote)*
  - `src/financial_forecasting/features/inference/application/ports/out/__init__.py` *(pacote)*
  - `src/financial_forecasting/features/inference/application/ports/out/checkpoint_resolver.py`
  - `src/financial_forecasting/features/inference/application/ports/out/checkpoint_grid_predictor.py`
  - `tests/fakes/features/inference/__init__.py` *(pacote)*
  - `tests/fakes/features/inference/in_memory_checkpoint_resolver.py`
  - `tests/fakes/features/inference/in_memory_checkpoint_grid_predictor.py`
  - `tests/contract/features/inference/__init__.py` *(pacote)*
  - `tests/contract/features/inference/test_checkpoint_ports_contract.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro** (`[fake, real]`, real = os use cases da Task 05 com os
  fakes do modeling, montados por `_frozen_tft_cohort.py`; o módulo **importa
  `ResolveTftCheckpoints` e `PredictTftFromCheckpoints` pelo nome**, em
  `from … import …` — é o que a regra #93 do `check_port_coverage.py` lê para
  reconhecer o use case de outro slice como real):
  `test_resolver_returns_one_resolution_per_fold_in_order`,
  `test_resolver_incomplete_cohort_raises_application_error`,
  `test_grid_predictor_rejects_run_outside_allowlist`,
  `test_grid_predictor_returns_only_the_requested_partitions`,
  `test_grid_predictor_grid_aligned_to_quantile_levels`.
- **O que fazer (concept §4 "Ports do inference"; ADR 7.1.0001 item 1):**
  `CheckpointResolver.__call__(self, command: ResolveTftCheckpointsCommand) ->
  ResolveTftCheckpointsResult` e `CheckpointGridPredictor.__call__(self,
  command: PredictTftFromCheckpointsCommand) -> PredictTftFromCheckpointsResult`
  — anotações **textualmente iguais** às dos use cases (o
  `check_port_coverage.py` compara o texto, #93); DTOs importados do modeling
  só sob `TYPE_CHECKING`. Docstring do resolver: "não carrega nenhum
  checkpoint". Fakes: resolver com resoluções configuradas por seed (ou
  exceção configurada) e contagem de chamadas; predictor com grades
  configuradas por `run_id`/partição, erguendo `ApplicationError` para `run_id`
  fora de `allowed`, e registro das chamadas (para "sem chamar o predictor").
- **Critério de aceite (concept §11 "Ports do inference", parte):** suíte verde
  nas duas pernas; `check_port_coverage.py --list` mostra os dois ports com
  fake, real (`ResolveTftCheckpoints`/`PredictTftFromCheckpoints`) e contrato,
  sem baseline.
- **Verificação (T1):**
  ```bash
  uv run pytest tests/contract/features/inference/test_checkpoint_ports_contract.py -v
  uv run python scripts/check_port_coverage.py --list
  make check-task SLICE="inference modeling"
  ```
- **Commit:** `feat(inference): ports do consumidor para resolver e predizer pelo checkpoint [7.1/task-07]`

---

### Task 08 — Ports espelho do inference (probe, persister, leitor do silver, ledger)

> **> 5 arquivos, justificado:** quatro declarações de Protocol (três com a
> assinatura copiada do port homônimo), um fake (subclasse fina) e uma suíte;
> a docstring do ledger não toca código; o teste do gate muda porque os
> homônimos entram no inventário do `check_port_coverage.py`.

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/application/ports/out/runtime_environment_probe.py`
  - `src/financial_forecasting/features/inference/application/ports/out/prediction_persister.py`
  - `src/financial_forecasting/features/inference/application/ports/out/silver_table_reader.py`
  - `src/financial_forecasting/features/inference/application/ports/out/cohort_ledger.py`
  - `tests/fakes/features/inference/in_memory_cohort_ledger.py`
  - `tests/contract/features/inference/test_consumer_mirror_ports_contract.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/modeling/adapters/out/filesystem/json_cohort_progress_ledger.py` (só docstring: satisfaz também o port `CohortLedger` do `inference`)
  - `tests/architecture/test_port_coverage_gate.py` — os testes de inventário
    real passam a indexar por `(slice, nome)` (`gate.slice_of(port.module)`),
    não só por nome. Motivo: `inventory()` ordena por caminho e
    `features/inference` vem antes de `features/modeling`; a escolha do
    contrato também é cega a slice. Com o espelho `PredictionPersister`, o
    contrato atribuído ao port do modeling pode virar
    `test_consumer_mirror_ports_contract.py` e quebrar a igualdade literal
    `contract.name == "test_persistence_ports_contract.py"`.
    - `test_real_repo_consumer_ports_resolve_to_the_supplier_use_cases`
      conserva `adapters == ("PersistPredictions",)` e `("PersistRunRecord",)`
      para `("modeling", …)`. A igualdade do nome do contrato vira `contract is
      not None` mais a conferência, pelo predicado do próprio gate
      (`gate.imports_class`, `gate.mentions_class`, `gate._PARAMETRIZATION`),
      de que `test_persistence_ports_contract.py` importa o fake, cita o real e
      parametriza.
    - Asserção nova
      `test_real_repo_inference_mirror_ports_have_their_own_contract`: para
      `("inference", "RuntimeEnvironmentProbe" | "PredictionPersister" |
      "SilverTableReader")`, `violation is None` e
      `test_consumer_mirror_ports_contract.py` satisfaz o predicado com o fake
      e o real de cada um.
    - Docstring do teste registra que o gate é **vácuo para homônimos** (§1).
- **Testes primeiro** (uma fixture `[fake, real]` por port, tipada pelo
  Protocol do inference): probe (`InMemoryRuntimeEnvironmentProbe` /
  `GitRuntimeEnvironmentProbe` sobre repositório git descartável):
  `test_probe_snapshot_has_code_dirty_and_threads_keys`; persister
  (`InMemoryPredictionPersister` / `PersistPredictions` sobre silver em
  `tmp_path`): `test_persister_writes_a_calib_decision_atomically`,
  `test_persister_collision_propagates`; leitor (`FakeSilverTableReader` /
  `ParquetAnalyticsRepository`): `test_reader_returns_dim_run_and_calib_facts_of_the_partition`;
  ledger (`InMemoryCohortLedger` / `JsonCohortProgressLedger`):
  `test_ledger_second_writer_is_refused`, `test_ledger_break_stale_releases`,
  `test_ledger_environment_none_then_recorded`.
- **O que fazer (concept §4 "Ports do inference"):** `RuntimeEnvironmentProbe`
  (`snapshot() -> Mapping[str, str]`), `PredictionPersister` (`__call__(self,
  command: PersistPredictionsCommand) -> PersistPredictionsResult`, tipos do
  analytics_store sob `TYPE_CHECKING`), `SilverTableReader` (`read(*, layer,
  table, filters=None)`), `CohortLedger` (`acquire_writer(*, break_stale: bool
  = False) -> None`, `release_writer() -> None`, `environment(cohort_id: str)
  -> Mapping[str, str] | None`) — assinaturas textualmente iguais às dos
  fornecedores. `InMemoryCohortLedger(InMemoryCohortProgressLedger)`:
  subclasse fina, sem corpo além da docstring. O lock, o `break_stale` e o
  ambiente vêm do fake existente; a perna fake grava o ambiente por
  `record_environment` herdado.
- **Critério de aceite (concept §11 "Ports do inference", parte):** suíte verde
  nas duas pernas dos quatro; `check_port_coverage.py` verde sem entrada nova.
  **Registro:** para os três homônimos o `check_port_coverage.py` é vácuo
  (cego a slice, §1). A prova de que o port **do inference** é satisfeito é a
  fixture tipada pelo Protocol do inference mais o mypy, e a asserção nova do
  teste do gate amarra a suíte do inference a cada um deles.
- **Verificação (T3 — toca o teste do gate):**
  ```bash
  uv run pytest tests/contract/features/inference/test_consumer_mirror_ports_contract.py tests/architecture/test_port_coverage_gate.py -v
  uv run python scripts/check_port_coverage.py --list
  make check
  ```
- **Commit:** `feat(inference): ports do consumidor para ambiente, silver e lock [7.1/task-08]`

---

### Task 09 — `RunInference` com fakes, port `InferenceManifest` e arestas de dados declaradas

> **> 5 arquivos, justificado:** o use case cria as cinco arestas de dados de
> runtime que `.importlinter` (`ignore_imports` com
> `unmatched_ignore_imports_alerting = error`) e LAYOUT §7 (contagem de
> arestas) precisam declarar **no mesmo commit**; o port do manifesto nasce sem
> real (par baseline + teste do gate, ADR 6.1.0005).

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/application/ports/out/inference_manifest.py`
  - `src/financial_forecasting/features/inference/application/use_cases/__init__.py` *(pacote)*
  - `src/financial_forecasting/features/inference/application/use_cases/run_inference.py`
  - `tests/fakes/features/inference/in_memory_inference_manifest.py`
  - `tests/unit/features/inference/__init__.py`, `tests/unit/features/inference/application/__init__.py` *(pacote)*
  - `tests/unit/features/inference/application/test_run_inference.py`
- **Arquivos a modificar:**
  - `scripts/arch_baseline.toml` — entrada temporária `key = "InferenceManifest"`, `issue = 153`, `motivo` citando o ADR 6.1.0005.
  - `tests/architecture/test_port_coverage_gate.py` — lista literal para
    `["Hasher", "InferenceManifest"]`, comentário citando o ADR 6.1.0005.
  - `.importlinter` — `bc-independence.ignore_imports`, uma a uma e comentadas
    (ADR 0.0.0053 item 3, dados): `run_inference →
    modeling.application.use_cases.resolve_tft_checkpoints`, `→
    modeling.application.use_cases.predict_tft_from_checkpoints` (DTOs de
    comando), `→ modeling.application.ports.out.runtime_environment_probe`
    (`CODE_KEYS`/`DIRTY_KEY`/`THREADS_KEY`, importados, nunca redeclarados), `→
    analytics_store.application.use_cases.persist_predictions`
    (`PersistPredictionsCommand`), `→
    analytics_store.domain.value_objects.quantile_forecast` (guardrail).
  - `docs/LAYOUT.md` §7 — contagem de arestas declaradas e as do `inference`.
- **Testes primeiro** (`test_run_inference.py`; dublês que fecham o ciclo
  escrita → releitura: **persister = `PersistPredictions(repository=repo)`**
  e **leitor do silver = o mesmo `repo`**, com `repo =
  FakeAnalyticsRepository(clock=FakeClock(...))`
  (`tests/fakes/features/analytics_store/in_memory_analytics_repository.py`,
  `read(*, layer, table, filters)`). O `dim_run` e as linhas de teste de
  referência são semeados por `repo.write`. Os testes de C8 (campo divergente,
  decisão parcial, `guardrail_applied` cruzado) gravam a linha divergente
  **direto** no `repo`. Completam os dublês os fakes das Tasks 07–09,
  `InMemoryRuntimeEnvironmentProbe`, `InMemoryCohortLedger`, `FakeClock` e o
  hasher real):
  - modo: `test_strict_when_non_code_keys_equal`,
    `test_tolerance_when_a_library_key_differs`,
    `test_cross_environment_with_equal_keys_forces_tolerance_and_records_forced`,
    `test_code_key_difference_does_not_change_the_mode`,
    `test_invalid_justification_raises_before_lock_and_probe` (vazia; sem
    `[finding]`), `test_unfrozen_spec_raises_before_lock_and_probe` (o
    `CohortNotFrozenError` **local** do inference);
  - retomada: `test_started_entry_resumed_in_other_environment_raises_without_writing`,
    `test_started_entry_resumed_in_same_environment_completes`;
  - conferência do calib: `test_tolerance_accepts_flipped_guardrail_applied_within_tolerance`,
    `test_strict_rejects_flipped_guardrail_applied`,
    `test_present_row_with_divergent_non_value_field_raises` (cada um de
    `model_version`, `asset`, `feature_set_name`, `schema_version`,
    `timestamp_utc`, `target_timestamp_utc`),
    `test_partially_present_decision_raises`,
    `test_present_calib_verified_under_first_write_environment_mode` (teste
    em `strict` contra o ambiente do cohort, mas o `first_write_environment`
    do manifesto difere numa chave de biblioteca: as linhas presentes são
    conferidas em `tolerance`; e o inverso);
  - critério: `test_one_float32_ulp_fails_strict_and_passes_tolerance`,
    `test_normalized_diff_above_tolerance_fails`,
    `test_test_key_set_mismatch_fails`, `test_reproduction_failure_writes_no_calib`;
  - guardas: `test_guards_in_order_never_call_the_predictor` (parametrizado na
    ordem `code_dirty`, ambiente do cohort ausente, cohort incompleto, run fora
    do `dim_run` — fold/seed/`model_version` divergentes —, sha256 ≠ manifesto);
  - write-ahead: `test_started_entry_written_before_first_calib_write`,
    `test_crash_between_decisions_rerun_completes_only_missing_and_keeps_first_write`,
    `test_calib_without_manifest_entry_raises_provenance_missing`;
  - guardrail: `test_crossed_raw_grid_written_raw_with_monotone_guardrail`;
  - fecho: `test_reread_count_completes_the_run`,
    `test_incomplete_reread_raises_and_keeps_started`,
    `test_second_run_writes_zero_and_verifies_all`,
    `test_lock_released_on_error`, `test_manifest_entry_has_all_fields`,
    `test_calib_rows_inherit_the_training_run_identity`.
- **O que fazer (concept §4 "Use case do inference", §5 I4–I13, §6 C1/C6–C15;
  ADRs 7.1.0002–0004):** port `InferenceManifest` (`recorded(cohort_id) ->
  Mapping[str, object] | None`; `record_run(cohort_id, run_id, entry:
  Mapping[str, object]) -> None`) com `FIRST_WRITE_FIELDS` e `merge_run_entry`
  (§1); fake sobre `dict` usando `merge_run_entry`. `run_inference.py`: DTOs do
  concept §4 (`RunInferenceCommand`, `InferenceRunOutcome`,
  `RunInferenceResult`), exceções de §1, `RunInference(*, resolver, predictor,
  probe, persister, silver, ledger, manifest, hasher, clock)` com o fluxo, o
  modo e a conferência de §1. Reprodução: chaves `(decision_idx, horizon,
  quantile_level)` do teste do run no silver × re-preditas, em `float`
  (float64); `strict` = `==`; `tolerance` = `abs(new - ref) / s <= 1e-5 +
  1.3e-6 * abs((ref - c) / s)`; `max_abs_diff` e `max_normalized_diff`
  registrados também quando passa. Calib: `QuantileForecast.from_raw` por
  decisão × horizonte, `PersistPredictionsCommand(split="calib", …)` com
  `run_id`, `model_version`, `asset`, `feature_set_name`, `schema_version` da
  linha do run em `dim_run`; contagem esperada = `spec.geometry.calib_size ×
  |spec.horizons| × |spec.quantile_levels|`. Nenhum import de `evaluation`.
- **Critério de aceite (concept §11 "`RunInference` com fakes", todos os
  subitens):** todos os testes verdes; `lint-imports` verde com as cinco
  arestas (e só elas).
- **Verificação (T3 — toca `.importlinter`, baseline e teste do gate):**
  ```bash
  uv run pytest tests/unit/features/inference/application/test_run_inference.py tests/architecture/test_port_coverage_gate.py -v
  uv run lint-imports
  uv run python scripts/check_port_coverage.py
  make check
  ```
- **Commit:** `feat(inference): RunInference reproduz o teste e completa o calib [7.1/task-09]`

---

### Task 10 — `JsonInferenceManifest` (escrita atômica, mescla de primeira escrita)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/adapters/out/__init__.py`, `…/adapters/out/filesystem/__init__.py` *(pacote)*
  - `src/financial_forecasting/features/inference/adapters/out/filesystem/json_inference_manifest.py`
  - `tests/contract/features/inference/test_inference_manifest_contract.py`
- **Arquivos a modificar:**
  - `scripts/arch_baseline.toml` (remove a entrada da Task 09)
  - `tests/architecture/test_port_coverage_gate.py` (lista literal de volta a `["Hasher"]`, comentário da Task 09 removido)
- **Testes primeiro** (`[fake, real]`):
  `test_recorded_is_none_without_a_manifest`,
  `test_first_write_fields_are_never_overwritten`,
  `test_last_verification_fields_are_replaced`,
  `test_cohort_environment_header_written_once`; só real (o fake não tem
  estado fora da instância): `test_persists_across_instances`,
  `test_failed_replace_keeps_the_previous_file` (falha injetada em
  `os.replace`), `test_file_lives_under_data_root_inference_cohort`.
- **O que fazer (ADR 7.1.0004 item 4):** `JsonInferenceManifest(*, data_root:
  Path)`, arquivo `<data_root>/inference/<cohort_id>/manifest.json`, leitura e
  escrita UTF-8, temporário `manifest.json.tmp-<pid>` + `os.replace`, mescla por
  `merge_run_entry` do port; docstring "satisfaz o port `InferenceManifest`".
- **Critério de aceite (concept §11 "Ports do inference": suíte `[fake, real]`
  dos sete; `check_port_coverage.py` sem entrada nova no baseline):** suíte
  verde; `scripts/arch_baseline.toml` sem diferença contra o `develop`; lista
  literal do teste do gate de volta a `["Hasher"]`.
- **Verificação (T3 — toca baseline e teste do gate):**
  ```bash
  uv run pytest tests/contract/features/inference/ tests/architecture/test_port_coverage_gate.py -v
  uv run python scripts/check_port_coverage.py
  git diff --exit-code "$(git merge-base origin/develop HEAD)" -- scripts/arch_baseline.toml
  make check
  ```
- **Commit:** `feat(inference): manifesto JSON da inferência com primeira escrita imutável [7.1/task-10]`

---

### Task 11 — Wiring da inferência no composition root

- **Arquivos a modificar:**
  - `src/financial_forecasting/composition_root.py`
  - `tests/unit/shared/test_composition_root.py` (só acréscimos)
- **Arquivos a criar:** nenhum.
- **Testes primeiro:** `test_wires_run_inference_for_with_the_real_collaborators`
  (resolver = `ResolveTftCheckpoints`, predictor =
  `PredictTftFromCheckpoints`, persister = `PersistPredictions`, leitor = o
  `analytics_repository`, ledger = o `cohort_ledger`, manifesto =
  `JsonInferenceManifest` sob `data_root`);
  `test_checkpoint_locator_is_wired_outside_the_lazy_proxy` (subprocesso:
  `wire_dependencies` + `run_inference_for` sem `torch` em `sys.modules`);
  `test_lazy_tft_proxy_exposes_predict_from_checkpoint_without_building`;
  `test_injected_probe_factory_reaches_run_inference`;
  `test_run_inference_for_wires_no_evaluation_use_case` (nenhum colaborador
  do `RunInference` montado pela fábrica — inclusive os internos dos use
  cases fornecedores — é instância de classe de
  `financial_forecasting.features.evaluation`; evidência do CA-10).
- **O que fazer (skill `composition-root`; concept §8):** `_LazyPfTftTrainer`
  ganha `predict_from_checkpoint` (delegação, mesmo padrão de
  `train_and_predict`); `FilesystemCheckpointLocator()` direto, fora do proxy;
  `ResolveTftCheckpoints` e `PredictTftFromCheckpoints` com o **mesmo**
  splitter, store, hasher, `artifacts_root`, `columns`,
  `observed_feature_set_hash`, `PIPELINE_VERSION` e `_TRAINERS_DEVICE` do
  cohort; fábrica `run_inference_for(cohort_path: Path, device: str) ->
  RunInference` (probe por `runtime_probe_for`, como `confirmatory_cohort_for`);
  campo novo em `ApplicationDependencies`.
- **Critério de aceite:** testes verdes; `lint-imports` e `check_layout.py`
  verdes (só o composition root instancia concretos).
- **Verificação (T2 — composition root: raio maior que um slice):**
  ```bash
  uv run pytest tests/unit/shared/test_composition_root.py -v
  make check-block
  ```
- **Commit:** `feat(inference): wiring do RunInference no composition root [7.1/task-11]`

---

### Task 12 — Subcomando `infer` e ponta a ponta sintético

> **> 5 arquivos, justificado:** o adapter de CLI é fino (traduz argumentos em
> comando e imprime o resultado); o teste que dá sentido a ele é o ponta a
> ponta pelo `main` (skill `task-ordering-hex` passo 4).
>
> **Casa do ponta a ponta (registrada):** fica em
> `tests/integration/features/inference/test_run_inference.py`, o caminho que
> o concept §11 ("Integração ponta a ponta") e o roadmap 7.1
> (`arquivos_a_criar`) nomeiam; mover para `tests/e2e/` (precedente
> `tests/e2e/test_cohort_cli.py`) contradiria os dois. O teste é marcado
> `integration` + `slow`, então fica fora do T1 e roda em T2/T3/CI.

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/adapters/in/__init__.py`, `…/adapters/in/cli/__init__.py` *(pacote)*
  - `src/financial_forecasting/features/inference/adapters/in/cli/inference_commands.py`
  - `tests/integration/features/inference/__init__.py` *(pacote)*
  - `tests/integration/features/inference/test_run_inference.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/cli.py`
  - `tests/unit/test_cli.py` (só acréscimos)
- **Testes primeiro:**
  - `test_cli.py`: `test_infer_requires_data_root_and_cohort`,
    `test_infer_dispatches_break_stale_lock_and_cross_environment`,
    `test_infer_application_error_exits_2`.
  - `test_run_inference.py` (`integration` + `slow`; dado bruto da fixture
    `tests/e2e/fixtures/cohort/raw_cohort_fixture.py`, sentimento fake, cohort
    congelado montado no teste com uma seed e geometria mínima, TFT real com
    poucas épocas, `CliWiring(runtime_probe_factory=…)` com probe fake de
    snapshot fixo e `code_dirty = "false"`): `materialize` → `run` (5.5) →
    `infer`, e
    `test_infer_reproduces_every_run_strict_with_zero_diff`,
    `test_calib_rows_expected_per_run_with_training_identity` (`split =
    "calib"`; `run_id`, `model_version`, `asset`, `feature_set_name`,
    `schema_version` iguais aos do teste do mesmo run; `value_guardrail`
    monótono), `test_verify_is_green_after_infer`,
    `test_second_infer_writes_zero_rows`, `test_manifest_is_complete`.
- **O que fazer (concept §4 "CLI", D8; ADR 7.1.0001 item 5, LAYOUT §8):**
  `cli.py`: subcomando `infer` (`--data-root`, `--cohort`,
  `--break-stale-lock`, `--cross-environment "<justificativa>"`), carregando
  `financial_forecasting.features.inference.adapters.in.cli.inference_commands`
  por `importlib`; o TOML lido pelo `cohort_file.load` da 5.5; docstring do
  módulo lista o subcomando. `inference_commands.infer(run_inference_for,
  spec, cohort_path, *, out, break_stale_lock, cross_environment) -> int`:
  monta `RunInferenceCommand`, chama, imprime as linhas de §1 e devolve 0;
  `ApplicationError`/`ValueError` sobem para o `main` (exit 2).
- **Critério de aceite (concept §11 "Integração ponta a ponta"):** testes
  verdes; tempo do ponta a ponta medido e colado em §7.
- **Verificação (T2 — `cli.py` da raiz):**
  ```bash
  uv run pytest tests/unit/test_cli.py tests/integration/features/inference/test_run_inference.py -v
  make check-block
  ```
- **Commit:** `feat(inference): subcomando infer da CLI com ponta a ponta [7.1/task-12]`

---

### Etapa E — Execução real sobre o cohort `aapl_confirmatory` r0 (sem métrica)

Não é Task numerada (concept §12): não produz código. Roda **depois** da Task 12,
com a árvore limpa e `make check` verde no HEAD. Evidência literal em §7
(`[measurement]`), num commit
`docs(inference): evidência da execução real da inferência [7.1/--]`.

**E0 — Pré-condições (host, Git Bash).**
```bash
WT=feat-153-7-1-inference-engine
WTH=/c/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/$WT
MAINH=/c/Users/Marcelo/Documents/Code/financial-forecasting
SCRATCH=<diretório de scratchpad da sessão, caminho absoluto, fora do repo>
git -C "$WTH" status --short                    # vazio (code_dirty = false)
docker ps --format '{{.Names}} {{.Mounts}}'     # nenhum container usando data/cohorts/aapl
ls -a "$MAINH/data/cohorts/aapl"                # bronze processed raw silver; sem .writer.lock, sem gold/ nem inference/
```

**E1 — Backup do `data_root` (obrigatório antes da primeira escrita).**
```bash
STAMP=$(date +%Y%m%d-%H%M%S)
BK="$MAINH/data/backups/aapl-pre-7.1-$STAMP"
mkdir -p "$BK" && cp -a "$MAINH/data/cohorts/aapl/." "$BK/"
(cd "$MAINH/data/cohorts/aapl" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$BK.src.sha"
(cd "$BK" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$BK.bak.sha"
diff "$BK.src.sha" "$BK.bak.sha" && echo BACKUP_OK
```
Os checkpoints não precisam de cópia: `artifacts/` é montado **somente
leitura** abaixo (nada desta Stage escreve lá).

**E2 — Container (mounts certos).** A worktree em `/app`; o `.git` principal
somente leitura com `GIT_DIR` da worktree (o probe precisa do git); o
`data_root` real do checkout principal em `/app/data/cohorts/aapl` (leitura e
escrita); `artifacts/` em `/app/artifacts` **somente leitura** (checkpoints e
`progress.json`; o `artifacts_root` default é `artifacts` relativo a `/app`); o
venv de dev `financial-forecasting_app-venv` — **não** o `ff55-venv-sentiment`
da 5.5, que não tem `scoringrules`/`arch` (o composition root os importa) —,
conferido em 2026-10-06 com as mesmas versões gravadas pelo cohort; MLflow
apontado para `/tmp` (nada escrito na worktree).
```bash
WTD=C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/$WT
MAIND=C:/Users/Marcelo/Documents/Code/financial-forecasting
RUN="docker run --rm -v $WTD:/app -v $MAIND/.git:/main.git:ro \
  -v $MAIND/data/cohorts/aapl:/app/data/cohorts/aapl \
  -v $MAIND/artifacts:/app/artifacts:ro \
  -v financial-forecasting_app-venv:/app/.venv \
  -w /app -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app -e GIT_OPTIONAL_LOCKS=0 \
  -e MLFLOW_TRACKING_URI=sqlite:////tmp/mlruns.db financial_forecasting-app:dev"
CLI="uv run --no-sync python -m financial_forecasting.cli"
COHORT="--data-root data/cohorts/aapl --cohort config/cohorts/aapl_confirmatory.toml"
PRE="git config --global --add safe.directory '*'"
```
(Git Bash: prefixar cada `$RUN` com `MSYS_NO_PATHCONV=1`.)

**E3 — Pré-voo: ambiente atual × gravado (nenhuma escrita).**
```bash
MSYS_NO_PATHCONV=1 $RUN sh -c "$PRE; git status --short; uv run --no-sync python -c \"import json, pathlib; from financial_forecasting.features.modeling.adapters.out.runtime.git_runtime_environment_probe import GitRuntimeEnvironmentProbe as P; from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import CODE_KEYS, DIRTY_KEY; cur = dict(P(repo_root=pathlib.Path('/app'), cohort_file=pathlib.Path('config/cohorts/aapl_confirmatory.toml').resolve(), device='cpu').snapshot()); ref = json.load(open('artifacts/cohorts/aapl_confirmatory-r0-665f45d9169a/progress.json'))['environment']; skip = set(CODE_KEYS) | {DIRTY_KEY}; print('dirty', cur[DIRTY_KEY]); print('non-code diff', sorted(k for k in set(cur) | set(ref) if k not in skip and cur.get(k) != ref.get(k)))\""
```
Esperado: `git status` vazio, `dirty false`, `non-code diff []`. Qualquer
outra saída → **não rodar** o `infer` (ver "Se falhar").

**E4 — Inferência.**
```bash
MSYS_NO_PATHCONV=1 $RUN sh -c "$PRE; $CLI infer $COHORT" 2>&1 | tee "$SCRATCH/infer-1.log"; echo "EXIT=${PIPESTATUS[0]}"
```
Esperado: `EXIT=0`; 60 linhas `run …: strict compared <n> max|d| 0.000e+00
max|d|/s 0.000e+00 calib written 3528 verified 0` (soma de `compared` =
211.120, 10 seeds × 21.112 linhas de teste); última linha
`inference aapl_confirmatory-r0-665f45d9169a: 60 runs (60 strict, 0 tolerance); calib rows written 211680, verified 0`.

**E5 — Conferências depois da escrita.**
```bash
MSYS_NO_PATHCONV=1 $RUN sh -c "$PRE; $CLI verify $COHORT"; echo "VERIFY_EXIT=$?"
MSYS_NO_PATHCONV=1 $RUN sh -c "$PRE; $CLI infer $COHORT" 2>&1 | tee "$SCRATCH/infer-2.log"; echo "EXIT=${PIPESTATUS[0]}"
ls -a "$MAINH/data/cohorts/aapl"; ls "$MAINH/data/cohorts/aapl/inference/aapl_confirmatory-r0-665f45d9169a"
```
Esperado: `VERIFY_EXIT=0` com `rows expected 337792, observed 337792` / `OK`
(o índice conta só teste); segunda inferência
`… calib rows written 0, verified 211680`, 60 runs `strict`; `manifest.json`
presente com 60 entradas `completed`; **sem** `gold/` no `data_root`.

Evidência de "sem `evaluation`" (CA-10), em três partes. O processo da CLI
carrega módulos de `evaluation` ao importar o composition root, então "nenhum
módulo importado" não é verificável no processo; o que se prova é:
1. o slice `inference` não importa `evaluation` (`bc-independence` sem aresta
   para ele; `lint-imports` verde);
2. nenhum use case de `evaluation` é wireado em `run_inference_for`
   (`test_run_inference_for_wires_no_evaluation_use_case`, Task 11);
3. nenhum executou: não há `gold/` no `data_root` depois de E4/E5.

Colar em §7: E3, as duas últimas linhas e uma linha de run de cada log
(`$SCRATCH/infer-*.log`, fora do repo), o `verify`, a contagem de entradas
`completed` do manifesto e o `ls`.

**Se falhar** (nunca editar o silver à mão; nunca usar `--cross-environment`
sem diagnóstico):

| Sintoma | Ação |
|---|---|
| E3 com `non-code diff` não vazio ou `dirty true` | não rodar; `dirty` → commitar; chave diferente → corrigir o ambiente (venv, imagem, CPUs do Docker Desktop). Se não for corrigível: `[finding]` + pergunta ao humano (o critério exige `strict`) |
| `ReproductionError` em `strict` com chaves iguais | **parar**; `[finding]` em §7 com run, nº de valores e max \|Δ\|; diagnosticar (capacidade de CPU, kernel, caminho de código) antes de qualquer outra corrida. Os runs anteriores gravaram calib já provada; o run que falhou não gravou nada. `--cross-environment` só depois do diagnóstico, citando o `[finding]` — e aí o critério "60 strict" não fecha: pergunta ao humano |
| `CohortRunLockedError` | conferir que nenhum processo usa o `data_root` (`docker ps`); só então `--break-stale-lock` |
| `DatasetMismatchError` / `CohortDeclarationMismatchError` / `IncompleteCohortError` / `ArtifactChangedError` | parar: dado, identidade do código ou artefato mudou; `[finding]`; nada foi carregado nem escrito |
| `IncompleteCalibError` / queda no meio | investigar a causa; rodar de novo (retoma pelo manifesto, completa só o que falta, no mesmo ambiente) |
| `InferenceEnvironmentError` na retomada | retomar no ambiente da primeira escrita (mesma imagem e venv) |
| Silver suspeito por qualquer motivo | restaurar o backup inteiro, com caminhos absolutos: `rm -rf "$MAINH/data/cohorts/aapl" && cp -a "$BK" "$MAINH/data/cohorts/aapl"` (o manifesto viaja junto); conferir com o `$BK.bak.sha`; registrar em §7 |

## 3. Gate de saída da Stage

### Verificações automatizadas
```bash
make check                                                     # T3, idêntico ao CI
uv run pytest tests/ --cov=src/financial_forecasting --cov-report=term-missing   # cada arquivo de src/ tocado >= 90%
uv run python scripts/check_port_coverage.py
git diff --exit-code origin/develop...HEAD -- scripts/arch_baseline.toml
grep -n 'violating == \["Hasher"\]' tests/architecture/test_port_coverage_gate.py
python scripts/check_technical_postexec.py docs/stages/7.1-inference-engine/technical.md
grep -n "Errata (2026-10-06)" docs/adr/5_4_0006-explicit-train-fitted-target-normalizer.md
```

### Verificações funcionais
- [ ] Etapa E concluída: 60 runs `strict` com max |Δ| = 0; 211.680 linhas de
      calib; `verify` da 5.5 verde; segunda execução escreve 0; manifesto com
      60 entradas `completed`; saídas literais em §7.
- [ ] Mutação "dropout ativo na predição" (Task 04) e quebra intencional do
      `inference-no-torch-leak` (Task 06) registradas em §7.

### Checklist de fechamento
- [ ] 12 Tasks commitadas, cada uma com o seu gate verde; Checkpoints C nas
      fronteiras de §4 com disposições registradas
- [ ] Auditoria de testes (subagente) com todos os itens "sim"
- [ ] `docs/roadmap.md`: 7.1 `done`, `updated_at` e `last_reviewed_at` de hoje
      (commit `docs(roadmap): … [7.1/--]`); commit `stage 7.1: complete`
- [ ] ADRs 7.1.0001–0004 `accepted`; errata do 5.4.0006 presente
- [ ] PR contra `develop` com `Closes #153`
- [ ] `concept.md` sem retoque retrospectivo pendente

## 4. Ordem de dependência entre Tasks

```
01 ─► 02 ─► 03 ─► 04 ─► 05 ─► 06 ─► 07 ─► 08 ─► 09 ─► 10 ─► 11 ─► 12 ─► [Etapa E]
```

- 01 antes de tudo (I10 antes de qualquer gravador de calib); 02 antes de 04/05
  (as funções extraídas são chamadas lá); 03 antes de 04 (port antes do
  adapter); 05 antes de 07 (os reais dos ports do consumidor); 06 antes de 07
  (o slice nasce sob os gates); 07–08 antes de 09; 09 antes de 10 (port antes
  do adapter); 10 antes de 11; 11 antes de 12.
- **Checkpoint C** (T2 `make check-block` + revisão do diff) depois de 02, 05,
  08, 10 e 12.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Extrair o helper de dataset muda o golden do trainer | parar; o helper tem de ser literalmente `from_parameters(get_parameters())`; diferença = bug da extração, nunca golden atualizado |
| `load_from_checkpoint(io.BytesIO)` não reconstrói como o caminho de arquivo | parar e perguntar; não voltar a carregar por caminho (abre a janela entre hash e unpickle, ADR 7.1.0004 item 3) |
| Reprodução em subprocesso difere do processo pai | `[finding]`; diagnosticar threads/flag antes de seguir (é o teste que fecha a lacuna "entre processos" antes da Etapa E) |
| Mutação de dropout não derruba o teste de RNG | o teste não prova A2: reforçar (mais decisões, outro estado de RNG) até a mutação derrubar |
| `check_port_coverage.py` não reconhece um real (anotação divergente) | alinhar o texto da anotação do port ao do fornecedor; nunca entrada nova no baseline |
| Fakes homônimos reaproveitados divergem do Protocol do inference | o mypy acusa na fixture tipada; ajustar o port do inference (espelho), não o fake |
| Leitura do `fact_oos_predictions` inteiro por run fica lenta no cohort real | aceitável (minutos); medir na Etapa E e registrar; otimizar só com `[decision]` |
| Ponta a ponta (Task 12) lento demais | geometria e épocas mínimas, uma seed; marcado `slow` (fora do T1) |
| Etapa E fora de `strict` | tabela "Se falhar" da Etapa E; `--cross-environment` só com diagnóstico citado |
| Mount de `data/cohorts/aapl` cria diretórios vazios na worktree | `data/` é ignorado pelo git; `code_dirty` não muda (não rastreado) |

## 6. Referências

- [`./concept.md`](./concept.md); ADRs [7.1.0001](../../adr/7_1_0001-checkpoint-prediction-supplied-by-modeling-through-consumer-port.md),
  [7.1.0002](../../adr/7_1_0002-calib-predictions-in-fact-oos-predictions-idempotent-completion.md),
  [7.1.0003](../../adr/7_1_0003-reproduction-contract-strict-same-environment-tolerance-across.md),
  [7.1.0004](../../adr/7_1_0004-checkpoint-resolution-before-load-and-write-ahead-inference-manifest.md);
  consumidos: 0.0.0053, 4.3.0001, 4.3.0002, 5.4.0001, 5.4.0006, 5.5.0001, 5.5.0003
- [`../../LAYOUT.md`](../../LAYOUT.md) §3, §7, §8; [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §2, §3.4, §4, §6;
  [`../../PIPELINE.md`](../../PIPELINE.md) §4.3; [`../../RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) Passos 6–10 e §Gates em camadas
- Technical [5.5](../5.5-confirmatory-retrain/technical.md) (Task 35, corrida real) e
  runbook [`confirmatory-cohort-aapl.md`](../../runbooks/confirmatory-cohort-aapl.md) (mounts do container)
- Skills: `task-ordering-hex`, `hex-arch-python`, `pytest-with-fakes`,
  `composition-root`, `import-linter-rules`, `dmls-ch06-deployment-and-inference-decisions`
- Issue [#153](https://github.com/MarceloSanC/financial-forecasting/issues/153)

### Matriz de rastreabilidade (concept §11 → Task → teste)

| # | Critério de aceite (concept §11) | Task(s) | Teste / evidência |
|---|---|---|---|
| CA-01 | Adapter: `predict_from_checkpoint` = `train_and_predict` (`==`); RNG; subprocesso; calib uma entrada por decisão × horizonte | 04 | `test_pf_tft_checkpoint_prediction.py::{test_checkpoint_prediction_equals_train_and_predict_test_grid, test_prediction_independent_of_global_rng, test_prediction_in_subprocess_is_identical, test_calib_decisions_emit_one_entry_per_decision_and_horizon}` |
| CA-01 | Adapter: locator com 0/2 `.ckpt` ergue C3; módulo do locator sem pilha de DL (subprocesso) | 03 | `test_checkpoint_locator_contract.py::{test_locate_without_ckpt_raises_not_found, test_locate_with_two_ckpts_raises_ambiguous, test_locator_module_does_not_import_the_dl_stack}` |
| CA-01 | Adapter: sha256 errado ergue C10 sem carga; carga recebe os bytes hasheados; C4; threads/flag restaurados; mutação de modo treino | 03, 04 | `test_tft_checkpoint_predictor_contract.py::{test_wrong_expected_sha256_raises_artifact_changed, test_declared_inputs_mismatch_raises_checkpoint_mismatch}` `[fake, real]`; `test_pf_tft_checkpoint_prediction.py::{test_wrong_sha_never_calls_the_loader, test_loader_receives_the_hashed_bytes_as_file_object, test_mismatched_levels_or_reals_raise_checkpoint_mismatch, test_threads_and_deterministic_flag_restored, test_settings_record_the_inference_parameters}`; mutação em §7 |
| CA-02 | Sem duplicação: mesmo helper de dataset e mesmo `_emit`; goldens verdes sem atualização; `run_id` e `TrainTftCommand` das funções compartilhadas | 02, 04 | `test_pf_tft_checkpoint_prediction.py::test_train_and_checkpoint_paths_share_dataset_helper_and_emit`; `test_cohort_tft_helpers.py::{test_run_id_from_shared_identity_matches_train_tft, test_tft_command_builder_matches_confirmatory_cohort_units}`; `git diff --exit-code` dos goldens (Task 02) |
| CA-03 | Use cases do modeling: `run_id` = `TrainTft`; calib = `FoldSplit.calib`; C1/C2/C13/C14 antes de `locate`; fora da lista permitida; I12; `model_version` | 05 | `test_resolve_tft_checkpoints.py::{test_run_ids_equal_what_train_tft_records, test_guards_raise_before_locate, test_model_version_is_in_each_resolution}`; `test_predict_tft_from_checkpoints.py::{test_calib_decisions_are_the_fold_calib_sessions, test_run_outside_allowlist_raises_without_predicting, test_emission_outside_request_raises}` |
| CA-04a | `RunInference`: modos, `--cross-environment`, chave de código, C13 e C1 antes de lock/probe | 09 | `test_run_inference.py::{test_strict_when_non_code_keys_equal, test_tolerance_when_a_library_key_differs, test_cross_environment_with_equal_keys_forces_tolerance_and_records_forced, test_code_key_difference_does_not_change_the_mode, test_invalid_justification_raises_before_lock_and_probe, test_unfrozen_spec_raises_before_lock_and_probe}` |
| CA-04b | Retomada `started` em outro ambiente ergue C11 sem escrever; no mesmo completa | 09 | `test_run_inference.py::{test_started_entry_resumed_in_other_environment_raises_without_writing, test_started_entry_resumed_in_same_environment_completes}` |
| CA-04c | `guardrail_applied` cruzado: passa em tolerance, C8 em strict; modo do calib presente pelo ambiente da 1ª escrita | 09 | `test_run_inference.py::{test_tolerance_accepts_flipped_guardrail_applied_within_tolerance, test_strict_rejects_flipped_guardrail_applied, test_present_calib_verified_under_first_write_environment_mode}` |
| CA-04d | 1 ulp float32: reprova strict, passa tolerance; \|Δ\|/s acima reprova; reprovação não escreve | 09 | `test_run_inference.py::{test_one_float32_ulp_fails_strict_and_passes_tolerance, test_normalized_diff_above_tolerance_fails, test_reproduction_failure_writes_no_calib}` |
| CA-04e | Guardas na ordem, sem chamar o predictor | 09 | `test_run_inference.py::test_guards_in_order_never_call_the_predictor` |
| CA-04f | Write-ahead; queda e rerun; calib sem entrada → C15; campo não-valor divergente → C8 | 09 | `test_run_inference.py::{test_started_entry_written_before_first_calib_write, test_crash_between_decisions_rerun_completes_only_missing_and_keeps_first_write, test_calib_without_manifest_entry_raises_provenance_missing, test_present_row_with_divergent_non_value_field_raises}` |
| CA-04g | Grade crua cruzada gravada crua, guardrail monótono, `guardrail_applied = 1` | 09 | `test_run_inference.py::test_crossed_raw_grid_written_raw_with_monotone_guardrail` |
| CA-04h | Contagem relida; segunda execução escreve 0; lock liberado em erro; manifesto completo | 09, 10 | `test_run_inference.py::{test_reread_count_completes_the_run, test_second_run_writes_zero_and_verifies_all, test_lock_released_on_error, test_manifest_entry_has_all_fields}`; `test_inference_manifest_contract.py::test_first_write_fields_are_never_overwritten` |
| CA-05 | Índice do cohort (I10) `[fake, real]` | 01 | `test_cohort_run_index_contract.py::test_calib_rows_do_not_change_counts_or_targets` |
| CA-06 | Avaliação intocada com e sem calib | 01 | `test_refresh_gold.py::test_refresh_gold_identical_with_and_without_calib_rows` |
| CA-07 | Ports do inference: fake + suíte `[fake, real]` para os sete; `port-coverage` sem entrada nova | 07, 08, 10 | `test_checkpoint_ports_contract.py`, `test_consumer_mirror_ports_contract.py`, `test_inference_manifest_contract.py`; `test_port_coverage_gate.py::test_real_repo_inference_mirror_ports_have_their_own_contract` (homônimos: o gate é vácuo, a prova é fixture tipada + mypy); baseline sem diferença e lista `["Hasher"]` (Task 10 e §3) |
| CA-08 | Integração ponta a ponta pela CLI (strict, \|Δ\| = 0, calib com identidade do treino, guardrail monótono, `verify` verde, segunda execução 0, manifesto) | 12 | `tests/integration/features/inference/test_run_inference.py::{test_infer_reproduces_every_run_strict_with_zero_diff, test_calib_rows_expected_per_run_with_training_identity, test_verify_is_green_after_infer, test_second_infer_writes_zero_rows, test_manifest_is_complete}` |
| CA-09 | Gates: `inference-no-torch-leak` provado por quebra revertida; `bc-independence` com arestas comentadas; `check_layout`; LAYOUT §7 com seis slices | 06, 09 | `test_import_contracts.py::{inference-no-torch-leak:*, domain-purity:inference-domain-imports-pandas, hexagonal-layers:inference-domain-imports-application, inward-only:inference-application-imports-infrastructure, store-no-storage-leak:inference-application-imports-pandas, bc-independence:inference-imports-new-evaluation-edge}`; saída da quebra em §7; `lint-imports` (Task 09) |
| CA-10 | Execução real: 60 strict com max \|Δ\| = 0; 211.680 linhas; `verify` verde; segunda execução 0; sem `evaluation` | Etapa E, 11 | saídas literais de E3–E5 em §7; "sem `evaluation`" = `bc-independence` sem aresta `inference → evaluation` + `test_composition_root.py::test_run_inference_for_wires_no_evaluation_use_case` + ausência de `gold/` |
| CA-11 | Roadmap emendado (concept) e 7.1 `done`; errata do 5.4.0006 presente | §3 | commit de roadmap `[7.1/--]`; `grep` da errata |
| CA-12 | `make check` verde | §3 | saída do `make check` no relatório |

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas no Passo 10 do
> [`RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.
> Seção pode estar vazia se a execução não produziu notas relevantes.
>
> **Regra de pergunta antes da nota.** Ao encontrar durante a Fase 4
> algo não previsto no Concept ou neste Technical, **pause** e
> levante a pergunta para o humano com 2–4 opções e uma marcada como
> **recomendada** + razão (via `AskUserQuestion` ou equivalente).
> Apenas após a decisão, registre a entrada abaixo. Na dúvida sobre
> se algo é "pequeno o suficiente para decidir sozinho", **pergunte**.

**Formato de cada entrada** (ADR-like, ordem cronológica):

```markdown
### YYYY-MM-DD — [tag] escopo — Autor
**Contexto:** <o que foi encontrado durante a execução>
**Pergunta:** <o que precisava ser decidido>            <!-- só [decision] -->
**Opções:**                                              <!-- só [decision] -->
- A — <descrição>
- B — <descrição> ✅ recomendada
**Decisão:** B                                           <!-- só [decision] -->
**Razão:** <por que>
```

- `[decision]` — algo não previsto foi decidido durante a execução.
  Inclui pergunta, opções, decisão, razão.
- `[finding]` — gap/observação a tratar em **próxima Stage**; corpo
  inclui "direção sugerida" e Stage candidata.
- `[deviation]` — ajuste pequeno aplicado vs. o plano original; corpo
  diz o que mudou e por que ficou abaixo do threshold de perguntar.

### 2026-10-06 — [deviation] task-04 — mutação obrigatória: dropout ativo na predição a partir do checkpoint — Claude (Opus 5.5)
**Contexto:** a Task 04 exige registrar aqui a mutação "forçar o dropout ativo na predição". Não houve desvio de código. O registro só guarda a evidência que o plano pede, já que nenhuma das três tags descreve esse caso.
**Mutação:** depois de `parameters = dict(model.dataset_parameters)` em `PfTftTrainer.predict_from_checkpoint`, entrou um hook temporário `model.register_forward_pre_hook(...)`. Ele chama `.train()` em todo `torch.nn.Dropout` antes de cada forward, ou seja, depois que o loop de predição já chamou `eval()`. Em seguida rodou `uv run --no-sync pytest tests/integration/features/modeling/test_pf_tft_checkpoint_prediction.py -k test_prediction_independent_of_global_rng`. A primeira versão do hook devolvia uma lista, que o torch tomou como novos argumentos do forward (`TypeError`). Esse erro não serve de evidência, e o hook foi refeito para devolver `None`.
**Saída com a mutação (falha esperada):**
```
E       AssertionError: assert {40: {1: (0.0...026276)}, ...} == {40: {1: (0.0...358078)}, ...}
E         Differing items:
E         {40: {1: (0.01977621018886566, 0.01697353646159172, 0.020038358867168427), 2: (0.01784750446677208, 0.013174274936318398, 0.021491434425115585)}} != {40: {1: (0.020934753119945526, 0.016908634454011917, 0.020815810188651085), 2: (0.018182741478085518, 0.013605349697172642, 0.022123156115412712)}}
1 failed, 11 deselected in 17.86s
```
**Revertido:** o arquivo foi restaurado da cópia anterior à mutação (`grep -c MUTATION` → 0) e o mesmo teste voltou a passar: `1 passed, 11 deselected in 18.26s`.
**Razão:** sem o modo eval, a predição dependeria do RNG global. A mutação prova que `test_prediction_independent_of_global_rng` pega essa dependência (A2).

### 2026-10-06 — [deviation] task-05 — `PredictTftFromCheckpoints` recebe o `CheckpointLocator` — Claude (Opus 5.5)
**Contexto:** a §2 Task 05 lista o construtor como `PredictTftFromCheckpoints(*, store, hasher, splitter, predictor, artifacts_root, …)`, sem locator. Mas o port `TftCheckpointPredictor` recebe `checkpoint_path`, um ARQUIVO, e o nome do checkpoint gravado pelo treino (`epoch=N-step=M.ckpt`) não pode ser derivado do `run_id`. Restavam três caminhos: a application listar o diretório, o que é I/O proibido (LAYOUT §3); mudar o port para receber o diretório, o que é contrato do concept §4; ou usar o mesmo `CheckpointLocator` da resolução.
**O que mudou:** o use case recebe `locator: CheckpointLocator` e obtém o caminho por `locator.locate(artifact_dir=tft_artifact_dir(artifacts_root, run_id)).path`, com a mesma regra de "exatamente um `*.ckpt`" (C3) da `ResolveTftCheckpoints`. O sha256 que o locator devolve não é usado. A conferência C10 continua no adapter, sobre os bytes efetivamente carregados, com `expected_sha256 = allowed[run_id]`. A guarda C6 (`UnknownRunError`) roda antes do primeiro `locate`. Ao contrário do "por fold" do texto, ela confere todos os folds antes de predizer qualquer um: nada é carregado se algum run estiver fora da lista. A Task 11 (wiring) passa o `FilesystemCheckpointLocator` também a este use case.
**Razão:** é reversível e ancorado no ADR 7.1.0004 item 1 (resolução pelo locator stdlib, sem carga) e no LAYOUT §3. O port do concept fica como está, e a lista do construtor é detalhe de wiring dentro do mesmo slice. Ficou abaixo do limiar de pergunta.

### 2026-10-06 — [deviation] task-06 — prova manual do `inference-no-torch-leak` (concept §11 "Gates") — Claude (Opus 5.5)
**Contexto:** a Task 06 exige colar aqui as duas saídas da prova manual. Não houve desvio de código. O registro só guarda a evidência que o plano pede, já que nenhuma das três tags descreve esse caso.
**Com a violação:** criado `src/financial_forecasting/features/inference/application/_taint.py` contendo `import torch`, e rodado `uv run --no-sync lint-imports` (saída filtrada):
```
Application/domain de inference não importam torch/lightning/pytorch_forecastingBROKEN
Contracts: 15 kept, 1 broken.
-   financial_forecasting.features.inference.application._taint -> torch (l.1)
exit=1
```
**Sem a violação:** com o arquivo apagado, o mesmo comando deu:
```
Contracts: 16 kept, 0 broken.
exit=0
```
**Razão:** o slice nasce vazio, e `lint-imports` verde sobre pacotes vazios não prova nada. Esta prova manual, junto com os oito casos novos de `_REAL_VIOLATION_CASES`, um por contrato e por módulo proibido, mostra que o contrato reage.

### 2026-10-06 — [deviation] task-01-fix — o fake do `CohortRunIndex` descarta `split != "test"` por inteiro (Checkpoint C, C1-1) — Claude (Opus 5.5)
**Contexto:** na Task 01, o `record(..., split="calib")` do `InMemoryCohortRunIndex` criava um órfão quando o run ainda não existia. O ADR 7.1.0002 item 4 não prevê isso (diz "discards non-test entries"), e nenhum contrato exercitava o caso.
**O que mudou:** agora o registro de calib é descartado sem efeito algum. Num run só com calib, o órfão vem do `record(..., rows=0)` de teste, como a perna fake do contrato já fazia. Os dois testes de calib continuam verdes nas duas pernas.

### 2026-10-06 — [deviation] task-03-fix — chaves de `settings` fixadas no port `TftCheckpointPredictor` (Checkpoint C, C1-4) — Claude (Opus 5.5)
**Contexto:** o contrato do predictor não fixava as chaves de `settings`, e o fake devolvia só cinco das oito que o adapter real produz.
**O que mudou:** o port ganhou `SETTINGS_KEYS` (`batch_size`, `num_workers`, `accelerator`, `num_threads`, `deterministic_algorithms`, `cpu_capability`, `platform`, `scikit-learn`), documentados conforme o concept §4 e o ADR 7.1.0004 item 4. O fake passou a devolver as oito, e o contrato confere, nas duas pernas, o conjunto exato e os valores fixos.

### 2026-10-06 — [deviation] task-03-fix — fake do `CheckpointLocator` normaliza o diretório para absoluto (Checkpoint C, C1-5) — Claude (Opus 5.5)
**Contexto:** o contrato do locator não conferia que o caminho devolvido é absoluto. O adapter real o torna absoluto por `resolve()`, mas o fake devolvia o diretório como recebido.
**O que mudou:** o fake normaliza os diretórios (`os.path.abspath`) no registro e na consulta, de modo que um diretório relativo e o seu absoluto são o mesmo. O contrato agora assere `Path(location.path).is_absolute()` e ganhou o caso `test_relative_directory_resolves_to_an_absolute_path` nas duas pernas.

### 2026-10-06 — [deviation] task-08 — colisão de PK do persister só na perna real — Claude (Opus 5.5)
**Contexto:** a Task 08 lista `test_persister_collision_propagates` entre os testes `[fake, real]` do `PredictionPersister` do `inference`. Só que o fake reaproveitado, `InMemoryPredictionPersister`, não guarda linhas: ele conta as resolvíveis e por isso não tem como colidir. Alterar esse fake está fora da lista fechada da Task.
**O que mudou:** o teste de colisão roda só sobre o `PersistPredictions` real, com o silver Parquet em `tmp_path`, e a docstring da suíte declara isso. O caso compartilhado pelas duas pernas é `test_persister_writes_a_calib_decision_atomically` (contagens). Na perna real, um caso extra confere `split = "calib"` e o guardrail das linhas gravadas.
**Razão:** o caminho de produção (o `PersistPredictions`) fica provado. Fazer o fake guardar linhas só para colidir seria uma segunda implementação do repositório; o `FakeAnalyticsRepository` já cumpre esse papel nos testes do `RunInference`.

### 2026-10-06 — [deviation] task-04-fix — faixa de decisões conferida antes de ler o checkpoint; `warn_only` restaurado (Checkpoint C, C2-9) — Claude (Opus 5.5)
**Contexto:** no `predict_from_checkpoint`, a faixa contígua era conferida depois da carga, e o `finally` restaurava a flag de algoritmos determinísticos sem o `warn_only`.
**O que mudou:** `_require_contiguous` passou a rodar antes da leitura dos bytes. Uma faixa inválida é erro do pedido e ergue `ValueError` sem tocar o arquivo; a ordem sha256 → carga → C4 entre as demais conferências fica igual. O `finally` agora restaura a flag junto com o `warn_only` anterior. No mesmo commit, sem mudança de comportamento: a docstring cita `assert_emission_within_request` (C2-1); o C4 ganhou casos que mudam só as reais desconhecidas (C2-3); o teste de subprocesso também roda sobre o bloco de teste e compara com a grade gravada pelo treino (C2-4).

### 2026-10-06 — [deviation] task-03-fix — o fake do predictor recusa faixa de decisões vazia (Checkpoint C, C2-2) — Claude (Opus 5.5)
**Contexto:** o `InMemoryTftCheckpointPredictor` aceitava `decision_indices=()` e devolvia uma grade vazia, enquanto o adapter real ergue `ValueError`. A divergência não aparecia em nenhum contrato.
**O que mudou:** o fake confere a faixa (não vazia, contígua e crescente) antes de qualquer outra conferência, na mesma ordem que o real usa desde a task-04-fix. O contrato ganhou `test_empty_decisions_raise_value_error` nas duas pernas.

<!-- END: post-execution -->
