---
title: Technical — Stage 8.1 — Corrida confirmatória ponta a ponta (cohort persistido → gold → scorecard pela r3)
description: Plano de execução da Stage 8.1 em 17 Tasks inside-out (1 Task = 1 commit) — VO SilverContentHash, tipos declarados no leitor do silver, hash do silver dentro do RefreshGold, resolver da revisão julgada extraído, registros .judged.toml, port JudgedGenerationStore satisfeito pelo ParquetGoldStore, ports de ambiente e lock, use case RunConfirmatoryEvaluation, wiring, subcomando evaluate e gate de custo — e a Etapa R, que roda a corrida real sobre o cohort aapl_confirmatory r0 julgada pela r3, sela a geração e faz a atestação
when-use: Consultar durante a Fase 4 (execução) da Stage 8.1; cada Task tem arquivos (lista fechada), testes a escrever primeiro, critério de aceite do concept que cobre e verificação; a Etapa R traz o runbook da corrida real (intenção commitada, backup, evaluate, selo, tag, comentário, .judged.toml)
keywords: [technical, plano de execução, confirmatory-run, evaluation, refresh-gold, scorecard, silver-content-hash, judged-generation, attempt-log, run-record, attestation, evaluate, cost-gate, blinding, r3]
status: draft
created_at: 2026-10-22
updated_at: 2026-10-22
stage_id: 8.1-confirmatory-run
stage_title: Corrida confirmatória ponta a ponta
step_id: 8
step_title: Reprodução, equivalência e relatório
depends_on: [6.5-preregistration-and-scorecard, 6.6-scorecard-profiles, 7.1-inference-engine, 7.2-conformal-cqr, 7.3-explainability]
concept_ref: ./concept.md
issue_id: 211
branch: feat/211-8-1-confirmatory-run
tasks_count: 17
---

# Technical — Stage 8.1 — Corrida confirmatória ponta a ponta

> **Como usar este documento (para code assistant):**
> 1. Ler §1 inteiro antes da Task 01 (decisões de forma fixadas aqui e a
>    pendência G1).
> 2. Executar as Tasks na ordem de §2. **1 Task = 1 commit.** A lista de
>    arquivos de cada Task é **fechada**: tocar arquivo fora dela = parar e
>    perguntar (RUNBOOK Passo 8, "Escopo estrito"). Arquivos `__init__.py`
>    marcados *(pacote)* são marcadores vazios ou de uma linha de docstring e
>    **não contam** na contagem de arquivos da Task (PIPELINE §4.3 item 2).
> 3. Escrever primeiro os testes listados em "Testes primeiro" (vermelho),
>    depois o código (verde). **T1 verde antes de todo commit**; `make check`
>    só nos pontos do [plano de gates](#plano-de-gates)
>    ([RUNBOOK §Gates em camadas](../../RUNBOOK-STAGE-LIFECYCLE.md#gates-em-camadas)).
> 4. Commit: `<type>(<escopo>): <descrição> [8.1/task-NN]`, body em bullets,
>    `Refs #211`, subject ≤ 100 caracteres, mensagem UTF-8 sem BOM por
>    `git commit -F` ([`CONVENTIONS.md`](../../CONVENTIONS.md) §4).
> 5. Algo não previsto em §1–§6, no concept ou nos ADRs 8.1.0001–0004 → pausar,
>    triar (skill `evidence-resolution`: E/C decide e registra; só P sobe ao
>    humano) e registrar em §7. Nunca propagar em silêncio.
> 6. Depois da Task 17 e do 2º `make check`: **Etapa R** (corrida real,
>    runbook com commits próprios), §3 (gate de saída) e `stage 8.1: complete`.
>
> **Stage = 1 branch:** `feat/211-8-1-confirmatory-run`, worktree própria.
>
> **Cegamento (I12, inegociável).** Nenhuma Task nem teste roda
> `RefreshGold`, `BuildConfirmatoryScorecard` ou qualquer função de predição ×
> realizado sobre o cohort `aapl_confirmatory-r0-665f45d9169a`. Testes,
> integração, e2e e o gate de custo (Task 17) usam silver **sintético**. Só a
> Etapa R toca o cohort real, e só depois do G1 (r3 ancorada) — o primeiro
> refresh confirmatório é o da Etapa R (ADR 6.5.0003 item 4).

## 1. Contexto e estratégia de execução

### Resumo

A Stage liga peças que já existem — `infer` (7.1), `RefreshGold` (6.4–7.3) e
`BuildConfirmatoryScorecard` (6.5) — num use case de orquestração
`RunConfirmatoryEvaluation` com guardas antes de efeitos (G1 resolução da r3 →
G2 árvore limpa → G3 lock → G4 julgamento e tentativas anteriores), registro
write-ahead da tentativa, E1 refresh → E2 scorecard → E3 preservação da geração
julgada numa cópia selada (`judged/<ref>/` com `CONTENTS.sha256` por último).
Acrescenta a identidade de conteúdo do silver lido (`SilverContentHash`,
calculado dentro do `RefreshGold`, gravado em `GoldManifest.silver_content`), o
registro de execução (`run_record.json`) e o subcomando `evaluate`, que roda o
`infer` e, só se ele terminar sem erro, o use case. Fecha com a corrida real
sobre o cohort AAPL julgada pela r3 e a atestação por tag, comentário na #211 e
`config/preregistration/aapl_confirmatory-r3.judged.toml`.

### Estratégia (ordem e porquê)

TDD inside-out (skill `task-ordering-hex`), em seis blocos; cada bloco deixa o
build verde e o seguinte se apoia nele:

1. **Identidade do silver (Tasks 01–05).** VO em `shared/` (domínio puro) →
   tipos declarados no port do leitor (port + fake + real, contrato) →
   acumulador de unidades na aplicação → integração no `RefreshGold` e campo
   obrigatório do manifesto (com o ripple mecânico dos manifestos de teste) →
   integração com o `ParquetAnalyticsRepository` real (A2). Vem primeiro porque
   muda um DTO consumido pelo 6.5, pelo 7.4 (`ReadServingGold`) e por todos os
   fixtures de gold — quebra cedo, uma vez.
2. **Resolver e registros commitados (Tasks 06–07).** Refator sem mudança de
   comportamento (A3) e método novo do `PreregistrationSource`.
3. **Geração julgada (Tasks 08–09).** Port + DTOs + fake; depois o
   `ParquetGoldStore` satisfaz o port, com a suíte `[fake, real]` (A6).
4. **Ambiente e lock (Tasks 10–11).** Ports do consumidor + fakes; depois o
   real de ambiente (git em diretório temporário no contrato) e o ledger da 5.5
   como real do lock, por duck typing. **1º `make check`** depois da Task 11.
5. **Use case e entrada (Tasks 12–16).** DTOs e corpo de atestação → use case
   com fakes (A4, A5, A6b, A7) → wiring + integração com stores reais (A9) →
   `infer_with_summary` → `evaluate` + e2e (A10).
6. **Gate de custo (Task 17)** → **2º `make check`** → **Etapa R** (A12–A16) →
   **3º `make check`** (saída).

A ordem respeita PIPELINE §4.3 item 4: nenhum port nasce no mesmo commit do seu
adapter (08→09, 10→11). As Tasks 02 e 07 **estendem** ports existentes com um
método: port, fake, real e contrato vão juntos porque o contrato `[fake, real]`
é o que prova que o fake espelha o real (exceção declarada; nenhum port novo).

### Pendência G1 — não-finito nas tabelas de atribuição (gap no concept, escalado)

O concept fixa que o `SilverContentHash` recusa NaN/±inf com `ValueError`
(A1; ADR 8.1.0002 item 1) e que o hash é calculado **dentro** do `RefreshGold`
sobre as linhas consumidas (D4). A Stage 7.3 fixou (I16, C8-2) que uma linha
inválida de `fact_permuted_predictions`/`fact_vsn_weights` **nunca aborta** o
refresh — vira `undefined` com o motivo —, e os testes
`test_refresh_gold_use_case.py::test_bad_attribution_row_is_undefined_never_aborts[vsn-weight-inf]`
e `[permuted-inf]` provam isso com `math.inf`. Com as duas regras, essas linhas
passam a abortar o refresh no hash, contra o A2(d) ("testes da 6.4–7.3
verdes"). A disposição muda critério de aceite (A1 ou A2(d)) e foi **escalada à
sessão mestra** antes do Checkpoint B; o concept não foi editado aqui.

- **Opção recomendada (a):** o `SilverContentHash` codifica não-finitos como
  fichas próprias (`float:inf`, `float:-inf`, `float:nan`) em coluna float — a
  identidade continua distinguindo a entrada consumida, e o refresh mantém o
  `undefined` da 7.3; `None` em coluna não-nula segue `ValueError`. Muda o
  texto do A1 e do ADR 8.1.0002 item 1.
- Opção (b): manter a recusa e emendar o I16 da 7.3 (linha não-finita de
  atribuição passa a abortar) — muda A2(d) e um invariante herdado.

As Tasks 01 e 04 abaixo estão escritas para a opção (a) e marcam com **[G1]**
as linhas que mudam se a decisão for (b). Nenhuma Task começa antes da
disposição registrada (concept re-aprovado ou `[decision]` da sessão mestra).

### Decisões de forma fixadas aqui (o concept §13 e os ADRs deixaram para a Fase 3B)

Todas `[decision:C]` de forma, dentro do que os ADRs 8.1.0001–0004 já decidem;
nenhuma pede ADR novo.

- **Unidades do hash (ADR 8.1.0002 item 3).** Chave de unidade = partes
  unidas por `|`: `dim_run|<parent_sweep_id>`,
  `<tabela de fato>|<run_id>|<year>` (com `year` da linha) e
  `realized|<asset>`. Os digests por unidade ficam **no manifesto**
  (`silver_content.units`), ao lado de `tables` (tabela → digest combinado das
  suas unidades; o realizado entra como a tabela `realized`) e de `digest`
  (combinado de **todas** as unidades). Um dono só do layout da geração (o
  manifesto); o tamanho estimado (≈ 4 mil unidades) cabe no JSON.
- **Forma do VO.** `SilverContentHash.of_unit(*, hasher, table, columns, rows)`
  recebe os tipos declarados (`Mapping[str, tuple[str, bool]]`) com as linhas
  (concept §4 "recebido junto com as linhas"). A lista de colunas de
  proveniência de escrita é constante do próprio VO
  (`WRITE_PROVENANCE_COLUMNS = frozenset({"created_at_utc"})`, a única coluna de
  proveniência nos quatro schemas lidos — conferido em
  `analytics_store/adapters/out/parquet/schemas/`); ela é removida **antes** da
  checagem de coluna declarada. Cada linha canonizada vira um JSON canônico
  (`sort_keys`, separadores fixos, floats pela codificação exata compartilhada
  com o `PreregistrationHash`); a unidade hasheia `{"table": t, "rows": [<json
  das linhas, ordenados>]}` pelo `Hasher` — o multiconjunto não depende da ordem
  de leitura.
- **Codificação exata de float compartilhada.** `_encode_floats` sai do
  `PreregistrationHash` para `shared/domain/services/exact_float.py` (ADR
  8.1.0002 item 1: "shared, not copied"); o golden do `PreregistrationHash` não
  muda.
- **`RefreshGold` ganha o colaborador `hasher: Hasher`** (o VO precisa dele) e um
  acumulador por chamada (`SilverContentAccumulator`); cada unidade é hasheada
  na leitura que a consome e descartada (memória limitada a uma leitura); a
  mesma unidade em duas leituras é erro de programação (`ValueError`).
- **Protocols locais do use case.** `GoldRefresh.__call__(command:
  RefreshGoldCommand) -> RefreshGoldResult` e `ScorecardBuilder.__call__(command:
  BuildConfirmatoryScorecardCommand) -> ScorecardResult`, declarados no módulo do
  use case (fora de `ports/out/`: são o mesmo slice; `RefreshGold` e
  `BuildConfirmatoryScorecard` os satisfazem por duck typing).
- **`clock: Clock` no `__init__` do use case** (ADR 8.1.0004 item 1:
  `started_at` "from the Clock"), além dos colaboradores do concept §4.
- **`JudgedGeneration` carrega também `manifest` e `documents`** (o JSON do
  scorecard e do `run_record` lidos da cópia): o corpo de atestação do
  `ALREADY_JUDGED` é reconstruído da cópia selada (ADR 8.1.0003 item 7), e o do
  `JUDGED` sai do `JudgedGeneration` que o `preserve` devolve — a mesma função
  sobre a mesma entrada dá o mesmo texto (A5, A15).
- **Tentativas (ADR 8.1.0004 item 1).** `JudgedAttempt` com `phase`
  (`started` | `input_read`) e `attempt_id` (= `started_at` ISO da linha
  `started`); a linha `input_read` (com `silver_content` e
  `dataset_fingerprint` do manifesto novo) é gravada logo depois do E1 e
  **antes** das conferências pós-E1, para a entrada ficar registrada mesmo
  quando a conferência recusa.
- **Chaves do `EvaluationEnvironment` (ADR 8.1.0003 item 6).** Nomes do próprio
  `evaluation`: `commit`, `code_dirty`, `preregistration_dirty`, `code.src`,
  `code.uv_lock`, `code.cohort_file` e o prefixo `env.` para tudo o que o R-BIT
  chama de ambiente — `env.image_id`, `env.platform`, `env.cpu_count`,
  `env.cpu_capability`, `env.lib.<dist>` e as demais chaves do probe da 5.5 como
  `env.probe.<chave>`. Código = chaves `code.*`; ambiente = chaves `env.*`
  (comparação do I13 por prefixo). O real recebe do composition root o mapa
  chave-do-probe → chave-do-evaluation e a chave de sujeira do probe; não
  importa `modeling`.
- **Bibliotecas do caminho do gold** (D6, lista fechada): `arch`, `statsmodels`,
  `scipy`, `scikit-learn`, `scoringrules`, `duckdb`, `mapie` (as que o probe não
  tem; `numpy`, `pandas`, `pyarrow`, `torch` já estão nele).
- **Capacidade de CPU** = `torch.backends.cpu.get_cpu_capability()` (a grandeza
  do manifesto de inferência, ADR 7.1.0003 item 2), lida por uma função lazy do
  composition root injetada no real — o `evaluation` não importa `torch`.
- **Id da imagem**: `Settings.image_id` (env `IMAGE_ID`), passado pelo runbook
  com `docker image inspect --format '{{.Id}}'`; ausente ou vazio →
  `MissingImageIdError` no `snapshot()`.
- **`preregistration_dirty`** = `git status --porcelain --untracked-files=all --
  config/preregistration` não vazio (arquivo não rastreado também conta: um
  `.judged.toml` não commitado seria lido pelo G4).
- **Geração viva corrompida no G4(d)**: `GoldGenerationCorruptError` propaga
  (zero efeito; diagnóstico humano). `GoldManifestNotFoundError` = sem geração
  viva.
- **Layout de `judged/`**: staging em `judged/.staging/` (removido no início do
  `preserve`), cópia em `judged/<ref>/generation/`, documentos
  `gold_model_comparison_confirmatory_scorecard.json` e `run_record.json`
  (`json.dumps(..., sort_keys=True, indent=2) + "\n"`), `CONTENTS.sha256` por
  último, `judged/ATTEMPTS.jsonl` (uma linha JSON por entrada, reescrito por
  temporário + `os.replace`). `judged_refs` lista os diretórios de `judged/` sem
  prefixo `.`.
- **Saída do `evaluate`** (stdout; contrato da Etapa R): as linhas do `infer`
  (inalteradas), depois
  `evaluation <preregistration_ref>: <STATUS> generation_digest <64 hex> partition <asset>/<parent_sweep_id>`,
  uma linha `--- attestation ---` e o corpo de atestação até o fim.

### Comandos no container

Fluxo Docker-only (as worktrees rodam por `docker run` avulso). Git Bash;
caminhos com barra normal (com `\` o bind mount sai vazio sem erro):

```bash
WT=feat-211-8-1-confirmatory-run
RUN="docker run --rm --cpus 6 --memory 8g --memory-swap 8g \
  -v C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/$WT:/app \
  -v C:/Users/Marcelo/Documents/Code/financial-forecasting/.git:/main.git \
  -v financial-forecasting_app-venv:/app/.venv \
  -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app -w /app financial_forecasting-app:dev"
PRE="git config --global --add safe.directory '*'"
# T1 de uma Task:
MSYS_NO_PATHCONV=1 $RUN sh -c "$PRE; uv run --no-sync pytest <arquivos> -q --no-cov"
```

T3 (`make check`) — comando literal, sem `$RUN` (o `PYTEST_PAR` tem espaços):

```bash
MSYS_NO_PATHCONV=1 docker run --rm --cpus 6 --memory 8g --memory-swap 8g -v "C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/feat-211-8-1-confirmatory-run:/app" -v "C:/Users/Marcelo/Documents/Code/financial-forecasting/.git:/main.git" -v financial-forecasting_app-venv:/app/.venv -e GIT_DIR=/main.git/worktrees/feat-211-8-1-confirmatory-run -e GIT_WORK_TREE=/app -e PYTEST_PAR="-n 4 --dist loadgroup" -w /app financial_forecasting-app:dev sh -c "git config --global --add safe.directory '*'; make check"
```

Worker do xdist caído ("node down", CPU ~0 % perto do fim) invalida o
resultado: parar e rodar de novo.

### Pré-condições

- Concept `done` (`e4dde3bb`) e ADRs 8.1.0001–0004 `accepted`; 6.5, 6.6, 7.1,
  7.2, 7.3 e 7.4 em `develop`; gate de domínio do Step 8 (#208) mergeado.
- **Pendência G1 disposta** (acima).
- Imagem `financial_forecasting-app:dev` e volume `financial-forecasting_app-venv`.
- Etapa R: `data/cohorts/aapl/` e `artifacts/` no checkout principal, fora do
  git; 60 checkpoints do confirmatório em `artifacts/tft` (concept §3); sem
  `gold/` no `data_root`.

### Premissas técnicas

- Python 3.12, mypy strict, `from __future__ import annotations`; imports de
  tipo entre slices só sob `TYPE_CHECKING`.
- `scripts/check_layout.py` regra 6: `hasher.hash_mapping`/`hash_text` só em
  `shared/domain/value_objects/`; `hashlib` sobre bytes de arquivo (sha256 da
  cópia julgada) não é chamada do port `Hasher` (precedente ADR 7.1.0004).
- `scripts/check_port_coverage.py`: port em `application/ports/out/` exige fake
  `InMemory<X>`/`Fake<X>` e contrato `[fake, real]`; o real cita o port no
  módulo (o `JsonCohortProgressLedger` passa a citar `EvaluationWriterLock` no
  docstring, como já cita o `CohortLedger` do `inference`).
- `scripts/check_use_case_deps.py`: o `__init__` do use case anota só ports e
  Protocols; `RefreshGold`/`BuildConfirmatoryScorecard` são do mesmo slice e
  entram pelos Protocols locais.
- `scripts/check_fake_parity.py`: o formato do `CONTENTS.sha256` tem dono único
  em `application/dtos/judged_generation.py` (fake e real chamam as mesmas
  funções; nenhum bloco ≥ 15 linhas duplicado).
- `.importlinter` `bc-independence`: nenhuma aresta nova `evaluation →
  inference` nem `evaluation → modeling` (A11). O encadeamento `infer` →
  use case fica no `cli.py` (raiz do pacote).

### Plano de gates

| # | Depois da Task | Por quê |
|---|---|---|
| 1 | 11 | Fecha o grupo que muda contrato consumido fora do use case: VO novo em `shared/` (regra 6 do `check_layout`, LAYOUT §7), campo obrigatório do `GoldManifest` lido pelo `inference` (7.4), método novo no port do leitor com real no `analytics_store`, três ports novos (port-coverage, fake-parity) e docstring do ledger do `modeling`. O T1 não roda `tests/architecture/` nem os scripts de gate; as Tasks 12–16 constroem o use case sobre esses contratos, e um port-coverage ou import-linter vermelho descoberto só no ponto 2 obrigaria retrabalho em cinco Tasks. |
| 2 | 17 | Pré-corrida: o commit que roda o julgamento confirmatório tem de estar verde como o CI (A11 antes do A12). As Tasks 14–16 mudam composition root, `Settings` e `cli.py`; uma correção de código **depois** do selo seria desvio do plano (doc de domínio §4.6), não um `fix`. |
| 3 | saída (depois da Etapa R) | Gate de saída (Passo 10): a Etapa R commita `config/preregistration/aapl_confirmatory-r3.judged.toml` (lido pelo `TomlPreregistrationSource` e por testes de arquitetura que leem `config/preregistration/`) e o §7. |

Nas demais Tasks o gate de commit é o T1 da Task. `make check-task` só com
motivo concreto (conta no orçamento se for `check-block`).

### Estrutura de pastas afetada

```
src/financial_forecasting/
├── cli.py                                                   # subcomando evaluate (T16)
├── composition_root.py                                      # hasher no RefreshGold (T04); fábrica run_confirmatory_evaluation_for (T14)
├── shared/
│   ├── domain/services/exact_float.py                       # T01 (novo)
│   ├── domain/value_objects/{silver_content_hash.py, preregistration_hash.py}   # T01
│   └── infrastructure/config/settings.py                    # image_id (T14)
└── features/
    ├── analytics_store/adapters/out/parquet/parquet_analytics_repository.py     # columns (T02)
    ├── modeling/adapters/out/filesystem/json_cohort_progress_ledger.py          # docstring (T11)
    ├── inference/adapters/in/cli/inference_commands.py                          # infer_with_summary (T15)
    └── evaluation/
        ├── application/
        │   ├── dtos/{silver_content.py, judged_generation.py, confirmatory_run.py}   # novos (T03, T08, T12)
        │   ├── dtos/refresh_gold.py                                              # T04
        │   ├── ports/out/{judged_generation_store.py, evaluation_environment.py, evaluation_writer_lock.py}  # novos (T08, T10)
        │   ├── ports/out/{silver_table_reader.py, preregistration_source.py}      # T02, T07
        │   └── use_cases/{silver_content_accumulator.py, judged_revision.py,
        │                  confirmatory_attestation.py, run_confirmatory_evaluation.py}  # novos (T03, T06, T12, T13)
        │   └── use_cases/{refresh_gold.py, build_confirmatory_scorecard.py}       # T04, T06
        └── adapters/
            ├── in/cli/evaluation_commands.py                                      # novo (T16) + pacotes in/, in/cli/
            ├── out/duckdb/parquet_gold_store.py                                   # T09
            ├── out/runtime/git_evaluation_environment.py                          # novo (T11) + pacote
            └── out/toml/toml_preregistration_source.py                            # T07
tests/
├── fakes/features/evaluation/{in_memory_judged_generation_store.py, in_memory_evaluation_environment.py,
│                              in_memory_evaluation_writer_lock.py, fake_confirmatory_steps.py}  # novos
├── unit/shared/domain/value_objects/test_silver_content_hash.py
├── unit/features/evaluation/{gold/test_silver_content_accumulator.py, test_judged_revision.py,
│                             test_judged_generation_dtos.py, test_confirmatory_run_dtos.py,
│                             test_confirmatory_attestation.py, test_run_confirmatory_evaluation.py}
├── contract/features/evaluation/{test_judged_generation_store_contract.py,
│                                 test_evaluation_environment_contract.py, test_evaluation_writer_lock_contract.py}
└── integration/features/evaluation/{test_silver_content_refresh.py, test_run_confirmatory_evaluation.py,
                                     test_evaluate_cli.py, test_silver_hash_cost_measurement.py}
```

## 2. Tasks

### Task 01 — Codificação exata de float compartilhada e VO `SilverContentHash`

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/domain/services/exact_float.py`
  - `src/financial_forecasting/shared/domain/value_objects/silver_content_hash.py`
  - `tests/unit/shared/domain/value_objects/test_silver_content_hash.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/shared/domain/value_objects/preregistration_hash.py`
  - `docs/LAYOUT.md` (§7, lista de VOs de identidade: `SilverContentHash`, ADR 8.1.0002)
- **Testes primeiro** (`test_silver_content_hash.py`, contra o
  `CanonicalJsonHasher` real, como `test_preregistration_hash.py`):
  `test_golden_value_for_small_payload` (valor fixo colado no teste);
  `test_invariant_to_row_order`; `test_invariant_to_column_order`;
  `test_neighbour_float32_values_hash_differently` (dois float32 vizinhos com
  |x| < 1e-4, montados por `struct`); `test_int_column_accepts_integral_float`
  (`3` e `3.0` → mesmo hash); `test_int_column_rejects_fractional_float`
  (`3.5` → `ValueError`); `test_none_in_non_nullable_column_raises`;
  `test_none_in_nullable_column_accepted`; `test_undeclared_column_raises`;
  `test_missing_declared_column_raises`; `test_str_preserved` (`"1"` ≠ `1`);
  `test_created_at_utc_does_not_change_hash`;
  `test_non_finite_floats_encoded_as_distinct_tokens` **[G1]** (`inf`, `-inf`,
  `nan` dão hashes distintos entre si e de qualquer finito; sob a opção (b):
  `test_nan_and_inf_raise`); `test_numpy_scalars_normalized` (`numpy.int64`,
  `numpy.float64` iguais a `int`/`float`); `test_combine_depends_on_keys_and_digests`;
  `test_raw_constructor_validates_sha256_hex`.
- **O que fazer:** mover `_encode_floats`/`_encode_mapping` para
  `exact_float.py` como `encode_exact_float(value: float) -> str` e
  `encode_floats(value: object) -> object` (mesma regra, mesma mensagem; o
  `PreregistrationHash` passa a importá-las — seus testes passam sem mudança).
  Criar o VO com `value: str` (validado por `validate_sha256_hex`),
  `of_unit(*, hasher, table, columns, rows)`, `combine(*, hasher, digests)` e as
  constantes `KIND_INT/FLOAT/STR/BOOL`, `WRITE_PROVENANCE_COLUMNS`. Canonização
  pelo tipo declarado (§1 "Forma do VO"): int → `int(v)` se integral
  (`numbers.Integral` sem `bool`, ou float integral), float → `float(v)` com a
  codificação exata (**[G1]** não-finito → ficha), str → `str` exigido, bool →
  `bool` exigido, `None` só em coluna nula. Stdlib só (`json`, `numbers`).
- **Critério de aceite:** A1 inteiro; `test_preregistration_hash.py` verde sem
  edição; LAYOUT §7 cita o VO.
- **Verificação (T1):**
  ```bash
  MSYS_NO_PATHCONV=1 $RUN sh -c "$PRE; uv run --no-sync pytest tests/unit/shared/domain/value_objects/test_silver_content_hash.py tests/unit/shared/domain/value_objects/test_preregistration_hash.py -q --no-cov; uv run --no-sync python scripts/check_layout.py"
  ```
- **Commit:** `feat(shared): VO SilverContentHash com floats exatos e tipos declarados [8.1/task-01]`

---

### Task 02 — Tipos declarados no `SilverTableReader` (`columns`)

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/ports/out/silver_table_reader.py`
  - `tests/fakes/features/evaluation/fake_silver_table_reader.py`
  - `src/financial_forecasting/features/analytics_store/adapters/out/parquet/parquet_analytics_repository.py`
  - `tests/contract/features/evaluation/test_silver_table_reader_contract.py`
- **Testes primeiro** (contrato `[fake, real]`):
  `test_columns_declares_every_schema_column_with_kind_and_nullability` (as
  quatro tabelas do refresh; `seed` → `("int", True)`, `year` → `("int",
  False)`, `quantile_level` → `("float", False)`, `parent_sweep_id` → `("str",
  True)`, `created_at_utc` presente); `test_fake_columns_equal_real_columns`
  (as quatro tabelas, igualdade exata — é o que prova o espelho);
  `test_columns_of_unknown_table_raises_application_error`.
- **O que fazer:** método `columns(*, layer: str, table: str) -> Mapping[str,
  tuple[str, bool]]` no Protocol (só tipos embutidos; doc do contrato). Real:
  deriva de `SilverTable.schema.columns` (dtype `int64`/`Int64` → `"int"`,
  `float64` → `"float"`, `str` → `"str"`, `bool` → `"bool"`; dtype fora disso →
  `ValueError` nomeando tabela e coluna; nulabilidade do `Column.nullable`).
  Fake: `SILVER_COLUMNS` literal ao lado de `SILVER_PARTITIONS`. Método novo em
  port existente: port + fake + real + contrato no mesmo commit (exceção do §1).
- **Critério de aceite:** base do A2 e do R12 (tipo declarado com dono único);
  contrato verde nas duas pernas.
- **Verificação (T1):** `pytest tests/contract/features/evaluation/test_silver_table_reader_contract.py -q --no-cov`
- **Commit:** `feat(evaluation): tipos declarados das colunas no leitor do silver [8.1/task-02]`

---

### Task 03 — `SilverContent` e acumulador de unidades

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/silver_content.py`
  - `src/financial_forecasting/features/evaluation/application/use_cases/silver_content_accumulator.py`
  - `tests/unit/features/evaluation/gold/test_silver_content_accumulator.py`
- **Testes primeiro:** `test_year_taken_from_row_one_pass_equals_per_year_passes`;
  `test_same_unit_in_two_reads_raises`; `test_tables_and_units_keys_format`
  (`dim_run|<p>`, `fact_oos_predictions|<run>|<year>`, `realized|<asset>`);
  `test_changing_one_row_changes_only_its_unit_its_table_and_total`;
  `test_realized_unit_uses_declared_str_and_float_kinds`;
  `test_silver_content_round_trip_and_rejects_bad_hex_or_missing_key`;
  `test_row_without_run_id_or_int_year_raises`.
- **O que fazer:** DTO `SilverContent(digest, tables, units)` (frozen;
  `as_mapping()`/`from_mapping()` com chaves exatas e hex validado;
  `unit_key(*parts)`, `REALIZED_TABLE = "realized"`). Acumulador
  `SilverContentAccumulator(*, hasher)` com `add_dim_run(*, columns,
  parent_sweep_id, rows)`, `add_facts(*, table, columns, rows)` (agrupa por
  `(run_id, year)` da linha), `add_realized(*, asset, realized: RealizedReturns)`
  (colunas `timestamp` `("str", False)` e `target_return` `("float", False)`) e
  `result() -> SilverContent` (`combine` por tabela e no total). Hasheia cada
  unidade na chamada que a recebe; nada de I/O.
- **Critério de aceite:** A2 (lógica de unidades e de quem muda o quê, com
  fake), I6.
- **Verificação (T1):** `pytest tests/unit/features/evaluation/gold/test_silver_content_accumulator.py -q --no-cov`
- **Commit:** `feat(evaluation): acumulador do hash de conteúdo do silver por unidade [8.1/task-03]`

---

### Task 04 — `RefreshGold` grava `silver_content`; manifesto devolvido no resultado

- **Arquivos a modificar (lógica):**
  - `src/financial_forecasting/features/evaluation/application/use_cases/refresh_gold.py`
  - `src/financial_forecasting/features/evaluation/application/dtos/refresh_gold.py`
  - `src/financial_forecasting/composition_root.py` (`RefreshGold(..., hasher=hasher)`)
  - `tests/unit/features/evaluation/gold/test_refresh_gold_use_case.py`
  - `tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py`
- **Arquivos do ripple mecânico** (campo obrigatório `silver_content` e
  colaborador `hasher` / `columns` nos leitores de teste — uma linha ou um
  helper por arquivo, sem mudança de asserção):
  - `tests/unit/features/evaluation/_silver_content.py` *(novo: `SAMPLE_SILVER_CONTENT`)*
  - `tests/unit/features/evaluation/_scorecard_factory.py`
  - `tests/unit/features/evaluation/_serving_gold_rows.py`
  - `tests/contract/features/evaluation/test_gold_store_contract.py`
  - `tests/contract/features/evaluation/test_gold_generation_reader_contract.py`
  - `tests/contract/features/inference/test_serving_gold_reader_contract.py`
  - `tests/integration/features/evaluation/test_conformal_refresh_end_to_end.py`
  - `tests/integration/features/evaluation/test_h3_refresh_memory.py` (`_GeneratingReader.columns`)

  Acima de 5 arquivos por ser ripple de campo obrigatório (PIPELINE §4.3 item
  2): o commit não compila sem eles e a lógica está nos três primeiros.
- **Testes primeiro** (fakes): `test_manifest_carries_silver_content`;
  `test_result_manifest_equals_published_manifest`;
  `test_blocked_hashes_exactly_dim_run_facts_and_realized` (A7);
  `test_completed_with_h3_hashes_the_five_tables`;
  `test_rows_discarded_by_post_filters_do_not_change_digest` (outro
  `parent_sweep_id`, `calib` da ablação, run de fold/seed inutilizável);
  `test_gold_tables_identical_with_and_without_hashing` (mesmas `GoldTable`s
  com o hash de unidade trocado por constante — "nenhum número muda");
  `test_bad_attribution_row_is_undefined_never_aborts` **inalterado** **[G1]**
  (sob a opção (b): os casos `vsn-weight-inf` e `permuted-inf` passam a esperar
  `ValueError`). Em `test_refresh_gold_dtos.py`:
  `test_manifest_round_trip_with_silver_content`;
  `test_manifest_without_silver_content_is_unreadable` (`from_mapping` →
  `ValueError`, precedente `test_manifest_before_this_stage_is_unreadable`).
- **O que fazer:** `GoldManifest.silver_content: SilverContent` obrigatório no
  construtor, em `as_mapping()` (chave `silver_content`) e em `from_mapping()`;
  `RefreshGoldResult.manifest: GoldManifest`. No `RefreshGold`: colaborador
  `hasher`; por chamada, um `SilverContentAccumulator`; tipos via
  `self._silver_reader.columns(...)` (uma vez por tabela por chamada); unidades
  alimentadas **depois** de cada pós-filtro — `_read_dim_run` (cohort e
  ablação), `_read_records` (linhas mantidas, os dois splits),
  `_read_realized`, `_attribution_reductions` (permutadas e VSN do run com fold
  e seed utilizáveis), `_ablation_reductions` (linhas `test` mantidas por ano) —
  e `silver_content=acc.result()` no `_manifest`. Nenhuma tabela gold muda.
- **Critério de aceite:** A2(a)(b)(c) com fakes, A2(d), A7 (parte do
  manifesto), D4, I6, I7, I10; testes da 6.4–7.3 verdes (salvo **[G1]** (b)).
- **Verificação (T1):**
  ```bash
  MSYS_NO_PATHCONV=1 $RUN sh -c "$PRE; uv run --no-sync pytest tests/unit/features/evaluation tests/contract/features/evaluation tests/contract/features/inference/test_serving_gold_reader_contract.py tests/unit/features/inference tests/integration/features/evaluation/test_conformal_refresh_end_to_end.py tests/integration/features/evaluation/test_h3_refresh_end_to_end.py tests/integration/features/evaluation/test_build_confirmatory_scorecard.py tests/integration/features/evaluation/test_profiles_end_to_end.py tests/integration/features/evaluation/test_refresh_gold.py -q --no-cov"
  ```
  (`test_h3_refresh_memory.py` é `slow`: entra no ponto 1 do plano.)
- **Commit:** `feat(evaluation): RefreshGold grava o hash de conteúdo do silver no manifesto [8.1/task-04]`

---

### Task 05 — Integração do hash do silver com o leitor real (A2)

- **Arquivos a criar:**
  - `tests/integration/features/evaluation/test_silver_content_refresh.py`
- **O que fazer / testes:** mundo sintético do `_world`/`_r3` de
  `test_h3_refresh_end_to_end.py` (composition root real,
  `ParquetAnalyticsRepository` real, plano com `[conformal]` e `[h3]`):
  `test_two_runs_same_digest`; `test_same_silver_split_in_two_files_same_digest`
  (a mesma partição regravada em duas metades com `pyarrow.parquet.write_table`
  no mesmo diretório); `test_one_consumed_row_changed_changes_its_unit_table_and_total`
  parametrizado por origem — `dim_run` do cohort, `dim_run` da ablação,
  `fact_oos_predictions` `test` e `calib` do cohort, `fact_oos_predictions`
  `test` da ablação, `fact_permuted_predictions`, `fact_vsn_weights`, realizado
  (via grade do mundo) — conferindo que nenhuma outra unidade muda;
  `test_read_and_discarded_rows_do_not_change_digest` parametrizado — outro
  `parent_sweep_id` na mesma partição, linha `calib` da ablação, ano da ablação
  fora dos `years`, permutada/VSN de run não candidato, run com fold ou seed
  inutilizável; `test_dim_run_seed_null_and_not_null_hash` (baseline sem seed e
  TFT com seed, ambos aceitos e distintos).
- **Critério de aceite:** A2 com o leitor real (R12).
- **Verificação (T1):** `pytest tests/integration/features/evaluation/test_silver_content_refresh.py -q --no-cov`
- **Commit:** `test(evaluation): hash do silver sobre o leitor real do analytics store [8.1/task-05]`

---

### Task 06 — `resolve_judged_revision` extraído do scorecard

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/judged_revision.py`
  - `tests/unit/features/evaluation/test_judged_revision.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/build_confirmatory_scorecard.py`
- **Testes primeiro:** `test_returns_every_record_plan_and_the_chain`;
  `test_broken_chain_raises_chain_error`; `test_hash_mismatch_raises`;
  `test_unanchored_revision_raises`; `test_anchor_of_another_reference_raises`;
  `test_errors_in_the_same_order_as_the_scorecard` (cadeia quebrada **e** hash
  divergente → erro de cadeia).
- **O que fazer:** `JudgedRevision` (frozen: `records`, `plans`, `chain`,
  `anchor`; propriedades `plan` e `reference`) e `resolve_judged_revision(*,
  source, hasher, name, revision, preregistration_ref) -> JudgedRevision` com o
  código dos passos 1–3 do `BuildConfirmatoryScorecard` movido sem mudança. O
  scorecard passa a chamá-la; `_readiness` recebe `revision.plans`.
- **Critério de aceite:** A3 — `git diff --exit-code origin/develop -- tests/unit/features/evaluation/test_build_confirmatory_scorecard_use_case.py tests/integration/features/evaluation/test_build_confirmatory_scorecard.py` vazio e os dois verdes.
- **Verificação (T1):** `pytest tests/unit/features/evaluation/test_judged_revision.py tests/unit/features/evaluation/test_build_confirmatory_scorecard_use_case.py tests/integration/features/evaluation/test_build_confirmatory_scorecard.py -q --no-cov`
- **Commit:** `refactor(evaluation): resolução da revisão julgada com dono único [8.1/task-06]`

---

### Task 07 — Registros `.judged.toml` no `PreregistrationSource`

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/ports/out/preregistration_source.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/toml/toml_preregistration_source.py`
  - `tests/fakes/features/evaluation/in_memory_preregistration_source.py`
  - `tests/contract/features/evaluation/test_preregistration_source_contract.py`
- **Testes primeiro** (contrato): `test_judged_records_empty_without_files`;
  `test_judged_record_round_trip` (todos os campos do concept §4);
  `test_judged_records_sorted_by_revision`; perna real:
  `test_judged_file_with_extra_or_missing_key_raises`,
  `test_judged_tag_must_be_confirmatory_run_of_its_reference`,
  `test_commented_at_must_be_offset_datetime`.
- **O que fazer:** `JudgedRecord` (frozen; `revision`, `preregistration_ref`,
  `generation_digest` (hex), `refresh_status`, `commit` (40 hex), `tag` (=
  `confirmatory-run/<ref>`), `comment_url`, `commented_at` (com fuso),
  `input_backup`, `input_backup_sha256`, `judged_backup`,
  `judged_backup_sha256`), `JUDGED_TAG_PREFIX = "confirmatory-run/"` e
  `judged_records(*, name) -> tuple[JudgedRecord, ...]` no Protocol. Real: glob
  `<name>-r*.judged.toml`, revisão do nome do arquivo, chaves exatas (como o
  `.anchor.toml`). Fake: `add_judged(name, record)`. Método novo em port
  existente (exceção do §1).
- **Critério de aceite:** base do G4(a) (A4, A16); D12.
- **Verificação (T1):** `pytest tests/contract/features/evaluation/test_preregistration_source_contract.py -q --no-cov`
- **Commit:** `feat(evaluation): leitura dos registros de atestação commitados [8.1/task-07]`

---

### Task 08 — Port `JudgedGenerationStore`, DTOs da geração julgada e fake

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/ports/out/judged_generation_store.py`
  - `src/financial_forecasting/features/evaluation/application/dtos/judged_generation.py`
  - `tests/fakes/features/evaluation/in_memory_judged_generation_store.py`
  - `tests/unit/features/evaluation/test_judged_generation_dtos.py`
- **Testes primeiro:** `test_contents_listing_format_is_sha256sum` (`<hex>  <path>\n`,
  ordenado pelos bytes do caminho, POSIX, UTF-8, LF);
  `test_parse_listing_rejects_crlf_bad_hex_duplicate_or_unsorted`;
  `test_listing_round_trip`; `test_attempt_round_trip_started_and_input_read`;
  `test_attempt_phase_fields_validated` (`input_read` sem `silver_content` →
  `ValueError`; `started` sem `code`/`environment` → `ValueError`);
  `test_judged_generation_requires_non_empty_files_and_hex_digest`.
- **O que fazer:** Protocol com `find`, `preserve` (assinaturas do concept §4),
  `judged_refs(*, partition) -> tuple[str, ...]`, `record_attempt(*, partition,
  attempt: JudgedAttempt) -> None`, `attempts(*, partition) ->
  tuple[JudgedAttempt, ...]`; erros `JudgedGenerationTamperedError`,
  `JudgedGenerationMismatchError`, `JudgedGenerationExistsError`
  (`ApplicationError`, no módulo do port, precedente
  `PreregistrationNotFoundError`). DTOs: `JudgedGeneration`
  (`preregistration_ref`, `partition`, `generation_digest`, `refresh_status`,
  `files`, `manifest`, `documents`), `AttemptPhase`, `JudgedAttempt`
  (`as_mapping`/`from_mapping`), nomes `GENERATION_DIR`, `CONTENTS_NAME`,
  `SCORECARD_DOCUMENT`, `RUN_RECORD_DOCUMENT`, `ATTEMPTS_NAME`,
  `contents_listing(files) -> bytes` e `parse_contents_listing(data) -> dict`.
  Fake `InMemoryJudgedGenerationStore(store: InMemoryGoldStore)`: copia a
  geração viva do `InMemoryGoldStore` com bytes determinísticos por "arquivo",
  calcula sha256 e o digest pela mesma listagem, contadores `preserves` e
  `recorded`, e ganchos de adulteração para o contrato.
- **Critério de aceite:** base do A6 (o contrato vem na Task 09).
- **Verificação (T1):** `pytest tests/unit/features/evaluation/test_judged_generation_dtos.py -q --no-cov`
- **Commit:** `feat(evaluation): port da geração julgada e registro de tentativas [8.1/task-08]`

---

### Task 09 — `ParquetGoldStore` satisfaz o `JudgedGenerationStore`

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/parquet_gold_store.py`
- **Arquivos a criar:**
  - `tests/contract/features/evaluation/test_judged_generation_store_contract.py`
  - (se o adapter passar de ~400 linhas) `src/financial_forecasting/features/evaluation/adapters/out/duckdb/judged_generation_files.py`
    — funções privadas de cópia, sha256 por streaming e JSONL, importadas só pelo `ParquetGoldStore`
- **Testes primeiro** (`[fake, real]`): `test_preserve_copies_current_and_seals_last`
  (conjunto de arquivos de `generation/` = o de `current/`, não vazio; bytes
  iguais na perna real); `test_generation_digest_is_sha256_of_contents_file`;
  `test_find_returns_none_without_copy`; `test_find_round_trip_with_manifest_and_documents`;
  `test_find_refuses_altered_byte` / `_missing_file` / `_extra_file` /
  `_empty_generation_dir` (`JudgedGenerationTamperedError`);
  `test_find_with_coherently_rewritten_contents_returns_new_digest`;
  `test_preserve_with_other_manifest_raises_mismatch_and_seals_nothing`;
  `test_preserve_over_sealed_raises_exists_and_touches_nothing`;
  `test_preserve_removes_staging_leftover`;
  `test_record_attempt_appends_and_attempts_reads_in_order`;
  `test_judged_refs_lists_sealed_refs_only` (ignora `.staging`, `ATTEMPTS.jsonl`);
  perna real: `test_sha256sum_check_passes_on_sealed_copy` (`sha256sum -c` em
  subprocesso), `test_preregistration_ref_validated_as_path_identifier`.
- **O que fazer:** os cinco métodos no `ParquetGoldStore` (dono único do layout;
  docstring cita o port), pelo protocolo do ADR 8.1.0003 itens 3–5b e o layout
  do §1; sha256 por streaming (`hashlib`, blocos de 1 MiB).
- **Critério de aceite:** A6.
- **Verificação (T1):** `pytest tests/contract/features/evaluation/test_judged_generation_store_contract.py tests/contract/features/evaluation/test_gold_store_contract.py -q --no-cov`
- **Commit:** `feat(evaluation): cópia julgada selada no ParquetGoldStore [8.1/task-09]`

---

### Task 10 — Ports `EvaluationEnvironment` e `EvaluationWriterLock` com fakes

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/ports/out/evaluation_environment.py`
  - `src/financial_forecasting/features/evaluation/application/ports/out/evaluation_writer_lock.py`
  - `tests/fakes/features/evaluation/in_memory_evaluation_environment.py`
  - `tests/fakes/features/evaluation/in_memory_evaluation_writer_lock.py`
- **O que fazer:** `EvaluationEnvironment.snapshot() -> Mapping[str, str]`, as
  constantes de chave do §1 (`COMMIT_KEY`, `CODE_DIRTY_KEY`,
  `PREREGISTRATION_DIRTY_KEY`, `CODE_PREFIX`, `ENV_PREFIX`, `IMAGE_ID_KEY`,
  `PLATFORM_KEY`, `CPU_COUNT_KEY`, `CPU_CAPABILITY_KEY`, `GOLD_LIBRARIES`) e
  `MissingImageIdError`. `EvaluationWriterLock` com `acquire_writer(self, *,
  break_stale: bool = False) -> None` e `release_writer(self) -> None` (as
  anotações do `JsonCohortProgressLedger`). Fakes: ambiente de foto fixa
  (limpo por padrão, sobrescrevível) e lock que registra `acquired`/`released` e
  pode recusar.
- **Critério de aceite:** base do A8 e do D8 (o contrato vem na Task 11).
- **Verificação (T1):** `uv run --no-sync mypy src/financial_forecasting/features/evaluation/application/ports tests/fakes/features/evaluation`
- **Commit:** `feat(evaluation): ports do ambiente de execução e do lock de escritor [8.1/task-10]`

---

### Task 11 — Reais do ambiente e do lock, com contratos

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/runtime/__init__.py` *(pacote)*
  - `src/financial_forecasting/features/evaluation/adapters/out/runtime/git_evaluation_environment.py`
  - `tests/contract/features/evaluation/test_evaluation_environment_contract.py`
  - `tests/contract/features/evaluation/test_evaluation_writer_lock_contract.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/modeling/adapters/out/filesystem/json_cohort_progress_ledger.py` (só docstring: satisfaz também o `EvaluationWriterLock`)
- **Testes primeiro:** ambiente `[fake, real]` (real sobre `git init` em
  `tmp_path` com um commit de `config/preregistration/x.toml`, probe =
  `InMemoryRuntimeEnvironmentProbe` do `modeling`):
  `test_snapshot_has_every_key` (inclusive `env.cpu_capability` e
  `env.image_id`); `test_commit_is_40_hex`;
  `test_dirty_flags_are_true_or_false`; perna real:
  `test_without_image_id_refuses_snapshot`,
  `test_untracked_file_in_preregistration_dir_is_dirty`,
  `test_probe_keys_mapped_without_importing_modeling` (o módulo do real não
  importa `modeling`); `test_modeling_probe_required_keys_unchanged`
  (`REQUIRED_KEYS` igual à tupla literal de hoje). Lock `[fake, real =
  JsonCohortProgressLedger]`: `test_acquire_then_release`;
  `test_second_acquire_raises_application_error`;
  `test_break_stale_takes_an_orphan_lock`.
- **O que fazer:** `GitEvaluationEnvironment(*, repo_root, probe, probe_keys:
  Mapping[str, str], probe_dirty_key, image_id: str | None, cpu_capability:
  Callable[[], str], preregistration_dir: Path)` — `git rev-parse HEAD`,
  `git status --porcelain --untracked-files=all -- <dir>`, `platform.platform()`,
  `os.cpu_count()`, `importlib.metadata.version` das `GOLD_LIBRARIES`, chaves do
  probe pelo mapa (código → `code.*`, demais → `env.probe.<chave>`).
- **Critério de aceite:** A8 (chaves, commit, `code_dirty`, recusa sem imagem,
  probe inalterado; "nenhum import `evaluation → modeling`" fecha no
  import-linter do ponto 1); D6, D8.
- **Verificação (T1):** `pytest tests/contract/features/evaluation/test_evaluation_environment_contract.py tests/contract/features/evaluation/test_evaluation_writer_lock_contract.py -q --no-cov`
- **Gate T3 — ponto 1 do plano:** `make check` (comando literal do §1).
- **Commit:** `feat(evaluation): ambiente de execução por git e lock pelo ledger da 5.5 [8.1/task-11]`

---

### Task 12 — DTOs da corrida e corpo de atestação

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/confirmatory_run.py`
  - `src/financial_forecasting/features/evaluation/application/use_cases/confirmatory_attestation.py`
  - `tests/unit/features/evaluation/test_confirmatory_run_dtos.py`
  - `tests/unit/features/evaluation/test_confirmatory_attestation.py`
- **Testes primeiro:** DTOs — `test_status_values`;
  `test_command_validates_name_revision_ref_and_deviation_type`;
  `test_inference_summary_from_mapping_exact_keys`; atestação —
  `test_body_golden_for_judged` e `test_body_golden_for_blocked` (texto fixo);
  `test_body_labels_h3_descriptive_and_conformal_empirical` ("descritiva",
  "cobertura empírica (não garantida)", tabela e linhas do manifesto);
  `test_body_reads_no_gold_value` (só manifesto, `run_record` e scorecard);
  `test_same_judged_generation_same_body`.
- **O que fazer:** `ConfirmatoryRunStatus` (`JUDGED`, `BLOCKED`,
  `ALREADY_JUDGED`), `InferenceSummary` (`runs`, `strict`, `tolerance`,
  `max_abs_diff`, `calib_rows_written`, `calib_rows_verified`),
  `RunConfirmatoryEvaluationCommand`, `RunConfirmatoryEvaluationResult` (concept
  §4), `DEVIATION_TAG = "[deviation]"` e os erros `DirtyCodeError`,
  `PriorAttemptCodeChangedError`, `PriorAttemptEnvironmentChangedError`,
  `PriorAttemptInputChangedError`, `PriorAttemptDivergenceError`,
  `InvalidDeviationError`. `attestation_body(judged: JudgedGeneration) -> str`:
  referência, `generation_digest`, status selado, commit (do `run_record`), tag
  `confirmatory-run/<ref>`, `started_at`/`finished_at`, prontidão com razões e
  veredito por horizonte (do documento do scorecard), H3 e conformal por nome de
  tabela e contagem (`rows_by_table`); com `BLOCKED`, os checks que falharam no
  lugar do veredito.
- **Critério de aceite:** D3, D7 (forma do corpo), base do A5/A15.
- **Verificação (T1):** `pytest tests/unit/features/evaluation/test_confirmatory_run_dtos.py tests/unit/features/evaluation/test_confirmatory_attestation.py -q --no-cov`
- **Commit:** `feat(evaluation): DTOs da corrida confirmatória e corpo de atestação [8.1/task-12]`

---

### Task 13 — Use case `RunConfirmatoryEvaluation` com fakes

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/run_confirmatory_evaluation.py`
  - `tests/fakes/features/evaluation/fake_confirmatory_steps.py` (`FakeGoldRefresh`, `FakeScorecardBuilder`)
  - `tests/unit/features/evaluation/test_run_confirmatory_evaluation.py`
- **Testes primeiro:**
  - **A4** — `test_guard_refuses_with_zero_effect` parametrizado, cada caso com
    zero `publish`, zero `preserve`, zero `record_attempt` e lock liberado quando
    adquirido: cadeia quebrada; hash divergente; revisão sem âncora; código sujo;
    `config/preregistration/` sujo; `.judged.toml` de outra revisão;
    `.judged.toml` desta revisão sem cópia; `.judged.toml` desta revisão com
    digest diferente; cópia selada de outra revisão; tentativa de outra revisão;
    `current/` com outra `preregistration_ref`; `current/` desta revisão sem
    tentativa; tentativa com outro `code.src` sem `--deviation`; tentativa com
    outro `env.image_id`/`env.platform`/`env.cpu_capability` sem `--deviation`;
    `--deviation` sem `[deviation]`; `find` coerente com digest ≠ o do
    `.judged.toml`. `test_guards_run_in_order` (G1 antes de G2 antes de G3 antes
    de G4). Pós-E1: `test_input_changed_raises_and_seals_nothing`;
    `test_divergent_generation_with_equal_code_env_input_raises_and_seals_nothing`.
  - **A5** — `test_sealed_intact_is_already_judged_without_refresh_or_scorecard`
    (corpo igual ao do `JUDGED`); `test_crash_between_e1_and_e3_leaves_attempt_and_no_seal`;
    `test_rerun_same_code_env_input_completes_with_two_attempts_in_run_record`;
    `test_rerun_with_changed_code_and_valid_deviation_records_it`;
    `test_staging_leftover_removed` (pelo store).
  - **A6b** — `test_scorecard_manifest_read_differs_raises_mismatch_nothing_sealed`.
  - **A7** — `test_blocked_preserves_without_scorecard_and_with_failed_checks`;
    `test_blocked_second_call_is_already_judged`.
  - `test_attempt_recorded_before_refresh` (I13);
    `test_lock_released_on_any_exception_after_g3`;
    `test_judged_returns_scorecard_digest_and_body`.
- **O que fazer:** Protocols locais (§1); `__init__(*, source, hasher,
  refresh_gold, build_scorecard, judged_store, gold_reader, environment,
  writer_lock, clock)`; `__call__`: G1 `resolve_judged_revision` → G2 snapshot
  (`code_dirty`/`preregistration_dirty` = `"false"`, senão `DirtyCodeError`) →
  G3 lock (`try/finally`) → G4 (a)–(e) do ADR 8.1.0004 item 2 (com o formato do
  `--deviation` conferido sempre que vier) → `ALREADY_JUDGED` ou registro
  `started` → E1 `refresh_gold(refresh_command_from(plan, ref))` → registro
  `input_read` → conferências 2b(i)(ii) → E2 só com `COMPLETED` → `run_record`
  (snapshot, `inference_summary`, `deviation`, todas as tentativas da partição,
  resumo do refresh, `failed_checks` quando `BLOCKED`, referência às seeds) →
  E3 `preserve(expected_manifest=result.manifest)` (com scorecard,
  `manifest_read == result.manifest` antes, I8) → resultado com
  `attestation_body(judged)`. Nenhum número calculado (I1).
- **Critério de aceite:** A4, A5, A6b, A7 (fakes), I1–I5, I8, I13, I14, D2, D3,
  D8, D12.
- **Verificação (T1):** `pytest tests/unit/features/evaluation/test_run_confirmatory_evaluation.py -q --no-cov`
- **Commit:** `feat(evaluation): use case da corrida confirmatória com guardas e replay [8.1/task-13]`

---

### Task 14 — Wiring, `Settings.image_id` e integração com stores reais

- **Arquivos a modificar:**
  - `src/financial_forecasting/composition_root.py`
  - `src/financial_forecasting/shared/infrastructure/config/settings.py`
  - `tests/unit/shared/test_composition_root.py`
  - `tests/unit/shared/infrastructure/config/test_settings.py`
- **Arquivos a criar:**
  - `tests/integration/features/evaluation/test_run_confirmatory_evaluation.py`
- **Testes primeiro:** composition root —
  `test_run_confirmatory_evaluation_for_wires_the_same_gold_store_source_and_ledger`;
  `test_cpu_capability_is_lazy` (montar a fábrica não importa `torch`); settings —
  `test_image_id_from_env`. Integração (mundo sintético do
  `test_h3_refresh_end_to_end.py`, `ParquetAnalyticsRepository`,
  `ParquetGoldStore` e `TomlPreregistrationSource` reais, ambiente fake,
  `JsonCohortProgressLedger` real): **A9** —
  `test_judged_copy_equals_scorecard_mapping_and_current_bytes` (JSON do
  scorecard = `ScorecardResult.as_mapping()`; tabelas de `generation/` byte a
  byte as de `current/`; manifesto da cópia com `silver_content`; `started_at`
  ≥ `anchored_at` da revisão de teste; `ATTEMPTS.jsonl` com uma entrada
  `started` e uma `input_read`); **A7** — `test_blocked_world_seals_without_scorecard_then_already_judged`;
  **A5** real — `test_second_call_already_judged_with_same_digest_and_body`.
- **O que fazer:** `run_confirmatory_evaluation_for(cohort_path: Path, device:
  str) -> RunConfirmatoryEvaluation` em `ApplicationDependencies`, montado com o
  **mesmo** `TomlPreregistrationSource`, `hasher`, `refresh_gold`,
  `build_confirmatory_scorecard`, `gold_store` (como `judged_store` e
  `gold_reader`), `cohort_ledger` (lock) e `GitEvaluationEnvironment` sobre
  `runtime_probe_for(cohort_path, device)` com o mapa de chaves do probe
  (`CODE_KEYS`, `DIRTY_KEY` importados do port do `modeling` **aqui**),
  `image_id=cfg.image_id` e `cpu_capability=_torch_cpu_capability` (import lazy).
  `Settings.image_id: str | None = None` (env `IMAGE_ID`).
- **Critério de aceite:** A9, A7 (real), A5 (real), D8.
- **Verificação (T1):** `pytest tests/unit/shared/test_composition_root.py tests/unit/shared/infrastructure/config/test_settings.py tests/integration/features/evaluation/test_run_confirmatory_evaluation.py -q --no-cov`
- **Commit:** `feat(evaluation): wiring da corrida confirmatória no composition root [8.1/task-14]`

---

### Task 15 — `infer_with_summary` ao lado do `infer`

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/inference/adapters/in/cli/inference_commands.py`
  - `tests/unit/test_cli.py`
- **Testes primeiro:** `test_infer_with_summary_prints_the_same_lines_and_returns_the_summary`
  (runs, `strict`, `tolerance`, `max_abs_diff` = máximo dos runs,
  `calib_rows_written`, `calib_rows_verified`).
- **O que fazer:** `infer_with_summary(run_inference_for, spec, cohort_path, *,
  out, break_stale_lock=False, cross_environment=None) -> Mapping[str, object]`
  com o corpo atual do `infer`; `infer` passa a chamá-la e devolve `0`. Os testes
  existentes do `infer` passam sem edição (`git diff` deles vazio).
- **Critério de aceite:** concept §4 (`infer_with_summary`), D1; base do A10.
- **Verificação (T1):** `pytest tests/unit/test_cli.py -q --no-cov`
- **Commit:** `feat(inference): resumo do infer devolvido por função ao lado do comando [8.1/task-15]`

---

### Task 16 — Subcomando `evaluate` e ponta a ponta sintético

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/in/__init__.py` *(pacote)*
  - `src/financial_forecasting/features/evaluation/adapters/in/cli/__init__.py` *(pacote)*
  - `src/financial_forecasting/features/evaluation/adapters/in/cli/evaluation_commands.py`
  - `tests/integration/features/evaluation/test_evaluate_cli.py` (`integration`, `slow`)
- **Arquivos a modificar:**
  - `src/financial_forecasting/cli.py`
  - `tests/unit/test_cli.py`
- **Testes primeiro:** unit — `test_evaluate_requires_preregistration_revision_and_ref`;
  `test_evaluate_dispatch_runs_infer_then_use_case_with_its_summary`;
  `test_evaluate_infer_failure_never_calls_the_use_case_exit_2`;
  `test_evaluate_prints_status_digest_and_attestation`. E2E **A10** (fluxo da
  7.1 — `materialize` → `run` com TFT de uma época, uma seed — com `repo_root`
  temporário inicializado como repositório git com um plano r0 sem
  `[conformal]`/`[h3]` e sua âncora commitados, `IMAGE_ID` em
  `settings_overrides`): `test_missing_checkpoint_exits_2_and_writes_no_gold`
  (um `.ckpt` movido para fora antes do `evaluate`, devolvido depois);
  `test_evaluate_runs_infer_first_and_records_its_summary_in_run_record`;
  `test_evaluate_prints_status_digest_and_body` (status `JUDGED` ou `BLOCKED`
  aceitos: o e2e prova o encadeamento, não o veredito);
  `test_second_evaluate_is_already_judged`.
- **O que fazer:** `evaluation_commands.evaluate(run_confirmatory_evaluation, *,
  name, revision, preregistration_ref, inference_summary, break_stale_lock,
  deviation, out) -> int` (imprime a saída do §1; não importa `inference`).
  `cli.py`: subcomando `evaluate` (`--data-root`, `--cohort`,
  `--preregistration`, `--revision`, `--preregistration-ref`,
  `--break-stale-lock`, `--deviation`); `_dispatch_evaluate`: carrega o spec,
  `infer_with_summary(...)` e, só sem exceção,
  `deps.run_confirmatory_evaluation_for(args.cohort, spec.device)` e
  `evaluate(...)`; docstring do módulo atualizada.
- **Critério de aceite:** A10, D1, D7 (impressão do corpo).
- **Verificação (T1):** `pytest tests/unit/test_cli.py tests/integration/features/evaluation/test_evaluate_cli.py -q --no-cov`
- **Commit:** `feat(evaluation): subcomando evaluate encadeado ao infer [8.1/task-16]`

---

### Task 17 — Gate de custo do hash do silver (A17)

- **Arquivos a criar:**
  - `tests/integration/features/evaluation/test_silver_hash_cost_measurement.py`
    (`integration`, `slow`, `skipif` sem `MEASURE_SILVER_HASH_COST=1`,
    precedente `test_profile_cost_measurement.py`)
- **Arquivos a modificar:**
  - `docs/stages/8.1-confirmatory-run/technical.md` (§7, entrada `[measurement]`)
- **O que fazer:** silver **sintético** gravado em Parquet num `data_root`
  temporário com as contagens do concept §3 (`dim_run` 96 + 300;
  `fact_oos_predictions` 549.472 `fs_all` com 211.680 `calib` e 1.055.600
  `fs_all_ablation`; `fact_permuted_predictions` 8.655.920 em 120 arquivos;
  `fact_vsn_weights` 891.490), grades não degeneradas (o refresh tem de sair
  `COMPLETED` para ler as tabelas de H3), plano com `[conformal]` e `[h3]`;
  `RefreshGold` montado pelo composition root (mesmo caminho do `_world` da 7.3,
  escalado). Duas pernas, cada uma num subprocesso: hash ligado e hash desligado
  (`SilverContentHash.of_unit`/`combine` trocados por constante **só** no
  subprocesso de medição). Mede o tempo por etapa (linhas do `_timed`) e o pico
  (`VmHWM`). Asserções: pico da perna ligada ≤ 6 GiB e (tempo ligado − tempo
  desligado) ≤ 30 min (D11).
- **Se reprovar:** plano B do D11 como `[decision]` em §7 e Task 17b (memória →
  unidade `(tabela, run_id, year, horizon)`; tempo → canonização colunar com
  teste de igualdade de digest contra a versão por linha), medida de novo.
  Reprovar no plano B → `[finding]`, parar e escalar (revisão do concept antes de
  qualquer tentativa real).
- **Critério de aceite:** A17, registrado em §7 antes do A12.
- **Verificação:**
  ```bash
  MSYS_NO_PATHCONV=1 $RUN sh -c "$PRE; MEASURE_SILVER_HASH_COST=1 uv run --no-sync pytest tests/integration/features/evaluation/test_silver_hash_cost_measurement.py -s -q --no-cov"
  ```
  (o `$RUN` já traz `--memory 8g --memory-swap 8g`; saída bruta colada em §7.)
- **Gate T3 — ponto 2 do plano:** `make check` (comando literal do §1), depois do commit.
- **Commit:** `test(evaluation): gate de custo do hash do silver em escala sintética [8.1/task-17]`

---

### Etapa R — Corrida confirmatória real (A12–A16)

Não é Task numerada: não produz código; produz commits de runbook (§7 e o
registro de atestação). Roda **depois** da Task 17 com o ponto 2 do plano
verde, a árvore limpa e o HEAD contendo só commits de docs depois do ponto 2.
Toda tentativa e todo resultado vão para §7 (`[measurement]`; `[finding]` quando
o I5/I13 manda parar).

**R0 — Variáveis (host, Git Bash).**
```bash
WT=feat-211-8-1-confirmatory-run
WTH=/c/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/$WT
MAINH=/c/Users/Marcelo/Documents/Code/financial-forecasting
WTD=C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/$WT
MAIND=C:/Users/Marcelo/Documents/Code/financial-forecasting
SCRATCH=<scratchpad da sessão, caminho absoluto, fora do repo>
REF=aapl_confirmatory-r3-00fd83d9cd39
P="$MAINH/data/cohorts/aapl/gold/asset=AAPL/parent_sweep_id=aapl_confirmatory-r0-665f45d9169a"
IMAGE_ID=$(docker image inspect --format '{{.Id}}' financial_forecasting-app:dev); test -n "$IMAGE_ID"
RUN_REAL="docker run --rm --cpus 6 --memory 8g --memory-swap 8g \
  -v $WTD:/app -v $MAIND/.git:/main.git:ro \
  -v $MAIND/data/cohorts/aapl:/app/data/cohorts/aapl \
  -v $MAIND/artifacts:/app/artifacts:ro \
  -v financial-forecasting_app-venv:/app/.venv \
  -w /app -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app -e GIT_OPTIONAL_LOCKS=0 \
  -e IMAGE_ID=$IMAGE_ID -e MLFLOW_TRACKING_URI=sqlite:////tmp/mlruns.db financial_forecasting-app:dev"
CLI="uv run --no-sync python -m financial_forecasting.cli"
EVAL="$CLI evaluate --data-root data/cohorts/aapl --cohort config/cohorts/aapl_confirmatory.toml --preregistration aapl_confirmatory --revision 3 --preregistration-ref $REF"
PRE="git config --global --add safe.directory '*'"
```
(Mounts da Etapa E da 7.1: `.git` só leitura, `artifacts/` só leitura,
`data_root` real em leitura e escrita. Prefixar cada `$RUN_REAL` com
`MSYS_NO_PATHCONV=1`.)

**R1 — Pré-condições (A12, sem escrita).**
```bash
git -C "$WTH" status --short                                  # vazio
docker ps --format '{{.Names}} {{.Mounts}}'                   # nenhum container no data/cohorts/aapl
ls -a "$MAINH/data/cohorts/aapl"                              # sem gold/ e sem .writer.lock (R9)
grep -c "\[measurement\] task-17" "$WTH/docs/stages/8.1-confirmatory-run/technical.md"   # >= 1, A17 aprovado
MSYS_NO_PATHCONV=1 $RUN_REAL sh -c "$PRE; uv run --no-sync python -c \"import json, pathlib; m = json.load(open('data/cohorts/aapl/inference/aapl_confirmatory-r0-665f45d9169a/manifest.json')); ids = sorted(m['runs']) if isinstance(m['runs'], dict) else sorted(r['run_id'] for r in m['runs']); found = {i: len(list(pathlib.Path('artifacts/tft', i).rglob('*.ckpt'))) for i in ids}; print(len(ids), sum(1 for n in found.values() if n == 1), [i for i, n in found.items() if n != 1])\""
```
Esperado: `60 60 []` (60/60 checkpoints, um `.ckpt` cada). O pré-voo de
ambiente da Etapa E3 da 7.1 (`non-code diff []`, `dirty false`) e a resolução
da r3 sem efeito:
```bash
MSYS_NO_PATHCONV=1 $RUN_REAL sh -c "$PRE; uv run --no-sync python -c \"from pathlib import Path; from financial_forecasting.features.evaluation.adapters.out.toml.toml_preregistration_source import TomlPreregistrationSource as S; from financial_forecasting.features.evaluation.application.use_cases.judged_revision import resolve_judged_revision as r; from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import CanonicalJsonHasher as H; v = r(source=S(root=Path('config/preregistration')), hasher=H(), name='aapl_confirmatory', revision=3, preregistration_ref='$REF'); print(v.reference, v.anchor.anchored_at.isoformat())\""
```
Esperado: `aapl_confirmatory-r3-00fd83d9cd39 2026-10-21T17:41:23+00:00`.
Qualquer divergência → **não** seguir.

**R2 — Backup do `data_root` (D10; entrada congelada da 8.2).**
```bash
STAMP=$(date -u +%Y%m%d-%H%M%S)
BK="$MAINH/data/backups/aapl-pre-8.1-$STAMP"
mkdir -p "$BK" && cp -a "$MAINH/data/cohorts/aapl/." "$BK/"
(cd "$BK" && find . -type f -printf '%P\0' | LC_ALL=C sort -z | xargs -0 sha256sum) > "$BK.sha256sum"
(cd "$MAINH/data/cohorts/aapl" && sha256sum -c --quiet "$BK.sha256sum") && echo BACKUP_OK
INPUT_BACKUP_SHA=$(sha256sum "$BK.sha256sum" | cut -d' ' -f1); echo "$BK $INPUT_BACKUP_SHA"
```

**R3 — Intenção da tentativa commitada (A12, D12; antes de CADA `evaluate`).**
Entrada `### <data> — [measurement] etapa-r — intenção da tentativa <n> da
corrida confirmatória — <autor>` em §7 com: HEAD atual, `code.src` e
`code.uv_lock` (do pré-voo), `IMAGE_ID`, plataforma, capacidade de CPU, hora
UTC, se é 1ª execução, replay (A15) ou pós-registro (A16), e o `--deviation`
(nenhum, salvo decisão registrada). Commit
`docs(evaluation): intenção da tentativa <n> da corrida confirmatória [8.1/--]`
por `git -C "$WTH" commit -F <arquivo UTF-8 sem BOM>`.

**R4 — Corrida (A13).**
```bash
MSYS_NO_PATHCONV=1 $RUN_REAL sh -c "$PRE; $EVAL" > "$SCRATCH/eval-1.out" 2> "$SCRATCH/eval-1.err"; echo "EXIT=$?"
tail -n 2 "$SCRATCH/eval-1.out"; grep -n "^evaluation \|refresh_gold" "$SCRATCH/eval-1.out" "$SCRATCH/eval-1.err"
```
Esperado: `EXIT=0`; 60 linhas de run do `infer` (modo e max |Δ| registrados) e a
linha `inference …: 60 runs (…)`; `evaluation aapl_confirmatory-r3-00fd83d9cd39:
JUDGED|BLOCKED generation_digest <hex> partition AAPL/aapl_confirmatory-r0-665f45d9169a`;
`$P/judged/$REF/` com `CONTENTS.sha256`; `$P/judged/ATTEMPTS.jsonl` com duas
linhas. Conferências (sem ler valor do gold além do que o scorecard já
publicou): manifesto `started_at` > `2026-10-21T17:41:23Z`; `silver_content.tables`
com `dim_run`, `fact_oos_predictions`, `fact_permuted_predictions`,
`fact_vsn_weights` e `realized` (`JUDGED`) ou só `dim_run`,
`fact_oos_predictions` e `realized` (`BLOCKED`); com `JUDGED`, o JSON do
scorecard com `preregistration_ref` = `$REF`, veredito por horizonte,
`academic_decision_ready` e razões; `rows_by_table` de `gold_h3_reading` e das
tabelas conformais > 0. Tempos por etapa: linhas `refresh_gold`/`_timed` do
`.err`.
**`BLOCKED` → seguir R5–R9 (selar, conferir o replay e atestar), registrar `[finding]` e parar
para decisão humana (I5); o DoD de veredito fica não cumprido. Não re-rodar.**

**R5 — Integridade de fora do código (A14).**
```bash
cd "$P/judged/$REF" && sha256sum -c --quiet CONTENTS.sha256 && echo CONTENTS_OK
DIGEST=$(sha256sum CONTENTS.sha256 | cut -d' ' -f1); grep -c "generation_digest $DIGEST" "$SCRATCH/eval-1.out"   # 1
```

**R6 — Replay (A15).** R3 (intenção da tentativa 2, replay) e:
```bash
MAN1=$(sha256sum "$P/current/MANIFEST.json" | cut -d' ' -f1); ATT1=$(wc -l < "$P/judged/ATTEMPTS.jsonl")
MSYS_NO_PATHCONV=1 $RUN_REAL sh -c "$PRE; $EVAL" > "$SCRATCH/eval-2.out" 2> "$SCRATCH/eval-2.err"; echo "EXIT=$?"
grep "^evaluation " "$SCRATCH/eval-2.out"                     # ALREADY_JUDGED, mesmo digest
diff <(sed -n '/^--- attestation ---$/,$p' "$SCRATCH/eval-1.out") <(sed -n '/^--- attestation ---$/,$p' "$SCRATCH/eval-2.out") && echo BODY_SAME
test "$(sha256sum "$P/current/MANIFEST.json" | cut -d' ' -f1)" = "$MAN1" && test "$(wc -l < "$P/judged/ATTEMPTS.jsonl")" = "$ATT1" && echo NO_NEW_EFFECT
```

**R7 — Backup da cópia selada (ADR 8.1.0003 item 6c).**
```bash
JB="$MAINH/data/backups/judged-$REF-$STAMP"
mkdir -p "$JB" && cp -a "$P/judged/$REF/." "$JB/"
(cd "$JB" && find . -type f -printf '%P\0' | LC_ALL=C sort -z | xargs -0 sha256sum) > "$JB.sha256sum"
(cd "$JB" && sha256sum -c --quiet "$JB.sha256sum") && echo JUDGED_BACKUP_OK
JUDGED_BACKUP_SHA=$(sha256sum "$JB.sha256sum" | cut -d' ' -f1)
```

**R8 — Tag e comentário (A16; ADR 8.1.0003 item 7).**
```bash
COMMIT=$(grep -o '"commit": "[0-9a-f]\{40\}"' "$P/judged/$REF/run_record.json" | head -1 | grep -o '[0-9a-f]\{40\}')
TAG="confirmatory-run/$REF"
git -C "$WTH" rev-parse -q --verify "refs/tags/$TAG" && { echo "FAIL: tag já existe"; exit 1; }
git -C "$WTH" push origin feat/211-8-1-confirmatory-run
git -C "$WTH" tag "$TAG" "$COMMIT" && git -C "$WTH" push origin "refs/tags/$TAG"
git -C "$WTH" ls-remote --tags origin "$TAG" | grep -qF "$COMMIT" && echo TAG_OK
gh api --paginate repos/{owner}/{repo}/issues/211/comments --jq '.[] | select(.body | contains("'"$DIGEST"'")) | .html_url'   # vazio (R11 do concept)
sed -n '/^--- attestation ---$/,$p' "$SCRATCH/eval-1.out" | tail -n +2 > "$SCRATCH/attestation.md"; test -s "$SCRATCH/attestation.md"
gh issue comment 211 --body-file "$SCRATCH/attestation.md"
gh api --paginate repos/{owner}/{repo}/issues/211/comments --jq '.[] | select(.body | contains("'"$DIGEST"'")) | "\(.created_at) \(.html_url)"' > "$SCRATCH/comment.txt"
test "$(wc -l < "$SCRATCH/comment.txt")" -eq 1; TS=$(cut -d' ' -f1 "$SCRATCH/comment.txt"); URL=$(cut -d' ' -f2 "$SCRATCH/comment.txt")
[[ "$TS" > "2026-10-21T17:41:23Z" ]] && echo COMMENT_AFTER_ANCHOR
```
(Rede ou permissão falhou → não gravar o `.judged.toml`; repetir o passo.)

**R9 — Registro de atestação (A16; I14).** Gravar
`config/preregistration/aapl_confirmatory-r3.judged.toml` com
`preregistration_ref`, `generation_digest` (`$DIGEST`), `refresh_status`,
`commit` (`$COMMIT`), `tag`, `comment_url` (`$URL`), `commented_at` (`$TS`,
offset date-time TOML), `input_backup` (`$BK`, relativo ao checkout principal),
`input_backup_sha256`, `judged_backup` (`$JB`, relativo),
`judged_backup_sha256`; conferir com o leitor real
(`TomlPreregistrationSource.judged_records`) no container; commit
`chore(evaluation): registro de atestação da corrida confirmatória r3 [8.1/--]`.
Depois, R3 (intenção da tentativa 3, pós-registro) e terceira execução:
```bash
MSYS_NO_PATHCONV=1 $RUN_REAL sh -c "$PRE; $EVAL" > "$SCRATCH/eval-3.out" 2> "$SCRATCH/eval-3.err"; echo "EXIT=$?"
grep "^evaluation " "$SCRATCH/eval-3.out"                     # ALREADY_JUDGED, mesmo digest (G4 leu o registro commitado)
```

**R10 — Evidência em §7.** Uma entrada `[measurement] etapa-r` com: R1 (saídas),
R2 (`$BK`, sha), as últimas linhas de cada `.out`, a linha `evaluation` das três
execuções, tempos por etapa do refresh (do `.err`), `ATTEMPTS.jsonl` inteiro,
R5, R6, R7 e R8 (tag, URL, `created_at`). Com `BLOCKED`: `[finding]` com os
checks que falharam e "parada para decisão humana". Commit
`docs(evaluation): evidência da corrida confirmatória real [8.1/--]`. Depois, o
**ponto 3** do plano (`make check`).

**Se falhar** (nunca editar silver, gold ou `ATTEMPTS.jsonl` à mão; nunca
apagar `gold/`):

| Sintoma | Ação |
|---|---|
| R1 com `non-code diff` ou `dirty true`; checkpoint faltando | não rodar; corrigir ambiente/árvore ou restaurar checkpoints do `data/backups/tft-pre-7.4-20261022-030008/` (R1 do concept); repetir R1 |
| `infer` com erro (`CheckpointNotFoundError`, `ReproductionError`…) | exit 2 antes do use case, nada de gold; tabela "Se falhar" da Etapa E da 7.1 |
| G1–G4 recusam (`Preregistration*Error`, `DirtyCodeError`, `JudgedGeneration*Error`, `PriorAttempt*Error`) | zero efeito; ler a mensagem, `[finding]` se não for erro de operação; nunca `--deviation` sem decisão registrada |
| `CohortRunLockedError` | conferir `docker ps`; só então `--break-stale-lock` |
| Queda ou erro entre E1 e E3 (`MemoryError`, `OSError`…) | a tentativa ficou registrada; diagnosticar; re-rodar **só** com o mesmo código, a mesma imagem e a mesma entrada (I13), com nova intenção commitada (R3); o use case confere a geração nova contra a viva |
| `PriorAttemptInputChangedError` / `PriorAttemptDivergenceError` | **parar**: `[finding]` (R-BIT), diagnóstico humano; nada selado |
| `BLOCKED` | I5: selar, atestar, `[finding]`, parar (R4) |
| Cópia julgada adulterada ou perdida depois do selo | `[deviation]` commitado + restauração do `$JB` conferida por `sha256sum -c` (I14); nunca re-julgar |

## 3. Gate de saída da Stage

### Verificações automatizadas
```bash
make check                                     # ponto 3 do plano (comando literal do §1)
uv run --no-sync pytest tests/ --cov=src/financial_forecasting --cov-report=term-missing   # cada arquivo de src/ tocado >= 90%
uv run --no-sync python scripts/check_port_coverage.py --list | grep -E "JudgedGenerationStore|EvaluationEnvironment|EvaluationWriterLock"
git diff --exit-code origin/develop...HEAD -- scripts/arch_baseline.toml      # nenhuma entrada nova de baseline
python scripts/check_technical_postexec.py docs/stages/8.1-confirmatory-run/technical.md
```

### Verificações funcionais
- [ ] Etapa R concluída: `evaluate` real até o fim (A13), integridade por
      `sha256sum -c` (A14), replay `ALREADY_JUDGED` sem efeito (A15), tag,
      comentário único na #211, `.judged.toml` commitado e terceira execução
      `ALREADY_JUDGED` (A16), com as saídas literais em §7.
- [ ] Gate de custo (A17) registrado em §7 antes da primeira intenção de tentativa.
- [ ] Com `BLOCKED`: `[finding]` e parada para decisão humana registrados (I5).

### Checklist de fechamento
- [ ] 17 Tasks commitadas, cada uma com o seu T1 verde; Checkpoints C nas
      fronteiras do §4 com disposições registradas
- [ ] Auditoria de testes (subagente que não escreveu os testes) com todos os
      itens "sim"; mutação real no use case (ordem das guardas), no acumulador
      (unidade) e no `find` (comparação de digest)
- [ ] Três `make check` do plano verdes, saídas coladas no relatório
- [ ] `docs/roadmap.md`: 8.1 `done`, `updated_at` e `last_reviewed_at` de hoje;
      commit `stage 8.1: complete`
- [ ] ADRs 8.1.0001–0004 `accepted`
- [ ] PR contra `develop` com `Closes #211`; a tag `confirmatory-run/$REF`
      mantém o commit da corrida alcançável depois do rebase do fechamento
- [ ] `concept.md` sem retoque retrospectivo pendente

## 4. Ordem de dependência entre Tasks

```
01 ─► 02 ─► 03 ─► 04 ─► 05
                   │
06 ─► 07 ──────────┤
                   ▼
            08 ─► 09 ─► 10 ─► 11 ─[make check 1]─► 12 ─► 13 ─► 14 ─► 15 ─► 16 ─► 17 ─[make check 2]─► Etapa R ─[make check 3]
```

- 01 antes de 03 (o acumulador usa o VO); 02 antes de 04 (o refresh lê
  `columns`); 03 antes de 04; 04 antes de 05, 09 e 13 (`RefreshGoldResult.manifest`,
  `silver_content`); 06 antes de 13 (G1) e da Etapa R (R1); 07 antes de 13
  (G4(a)); 08 antes de 09 e de 12 (`JudgedGeneration`); 10 antes de 11; 12 antes
  de 13; 13 antes de 14; 15 antes de 16; 16 antes de 17 (a medição usa o wiring
  final); 17 antes da Etapa R (A17 antes do A12).
- **Checkpoint C** (revisão do bloco por subagente, sem gate de suíte) depois
  de 05, 09, 11, 13 e 16.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| G1 sem disposição | nenhuma Task começa; escalado à sessão mestra |
| Ripple da Task 04 maior que a lista (outro fixture monta `GoldManifest`) | parar, `[deviation]` com o arquivo, acrescentar só a linha do campo |
| `check_port_coverage` não reconhece o ledger como real do `EvaluationWriterLock` | alinhar o docstring e as anotações do port às do ledger; nunca entrada no baseline |
| `ParquetGoldStore` passa de ~400 linhas | helpers privados em `judged_generation_files.py` no mesmo diretório (previsto na Task 09) |
| e2e da Task 16 lento (TFT real) | geometria e épocas mínimas da 7.1, uma seed, `slow`; medir e registrar em §7 |
| Plano r0 do e2e não casa com o cohort sintético | montar o plano a partir do spec congelado (id, hash, fingerprint), como `test_profiles_end_to_end._freeze`; `[deviation]` se precisar de helper novo |
| Mundo sintético da Task 17 sai `BLOCKED` (não lê H3) | ajustar a geração das grades até `COMPLETED`; medição com `BLOCKED` não vale como A17 |
| A17 reprova | plano B do D11 (Task 17b); reprova de novo → `[finding]` e revisão do concept antes da Etapa R |
| `infer` da Etapa R fora de `strict` | política da 7.1 (R2 do concept): registrado no `inference_summary`, não bloqueia |
| Rename de diretório no bind mount do Windows falha no `preserve` | `OSError` propaga, nada selado, staging limpo no próximo `preserve`; re-rodar nas condições do I13 |
| Mount de `data/cohorts/aapl` cria diretórios vazios na worktree | `data/` é ignorado pelo git; `code_dirty` não muda |

## 6. Referências

- [`./concept.md`](./concept.md); ADRs
  [8.1.0001](../../adr/8_1_0001-confirmatory-run-orchestration-guards-status-replay.md),
  [8.1.0002](../../adr/8_1_0002-silver-content-hash-exact-rows-consumed-by-refresh.md),
  [8.1.0003](../../adr/8_1_0003-judged-generation-preserved-copy-run-record-attestation.md),
  [8.1.0004](../../adr/8_1_0004-single-judgment-attempt-log-committed-record-deviation.md);
  consumidos: 1.4.0001, 5.5.0001, 5.5.0004, 6.4.0005, 6.5.0001, 6.5.0003,
  6.5.0005, 6.5.0007, 6.6.0002, 7.1.0002–7.1.0004, 7.2.0003, 7.3.0001, 7.3.0005,
  0.0.0053, 0.0.0059, 0.0.0060–0.0.0062
- [`../../LAYOUT.md`](../../LAYOUT.md) §3, §7, §8; [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §2, §3.4, §4, §6;
  [`../../PIPELINE.md`](../../PIPELINE.md) §4.3; [`../../RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) Passos 6–10 e §Gates em camadas
- Technical [6.5](../6.5-preregistration-and-scorecard/technical.md) (âncora por
  tag + comentário + registro), [7.1](../7.1-inference-engine/technical.md)
  (Etapa E, mounts), [7.4](../7.4-inference-api/technical.md) §7 (checkpoints)
- Doc de domínio [`reproduction-equivalence-and-reporting`](../../domain/evaluation/reproduction-equivalence-and-reporting.md) §3, §4.2, §4.5, §4.6
- Skills: `task-ordering-hex`, `hex-arch-python`, `pytest-with-fakes`,
  `orchestrator-design`, `composition-root`, `repository-pattern`,
  `architecture-fitness`
- Issue [#211](https://github.com/MarceloSanC/financial-forecasting/issues/211)

### Matriz de rastreabilidade (concept §11 → Task → teste)

| # | Critério de aceite | Task(s) | Teste / evidência |
|---|---|---|---|
| A1 | `SilverContentHash`: golden, ordem, floats exatos, tipo declarado, proveniência, não-finito **[G1]**, construtor cru | 01 | `test_silver_content_hash.py` (todos os casos da Task 01) |
| A2 | `silver_content` estável, muda só a unidade alterada, não muda com linha descartada, `seed` nulo/não nulo, tabelas gold idênticas, `manifest` = publicado | 02, 03, 04, 05 | `test_silver_table_reader_contract.py::test_fake_columns_equal_real_columns`; `test_silver_content_accumulator.py`; `test_refresh_gold_use_case.py::{test_result_manifest_equals_published_manifest, test_rows_discarded_by_post_filters_do_not_change_digest, test_gold_tables_identical_with_and_without_hashing}`; `test_silver_content_refresh.py` (leitor real) |
| A3 | `resolve_judged_revision` extraído; testes do scorecard sem alteração | 06 | `test_judged_revision.py`; `git diff --exit-code` dos testes do scorecard |
| A4 | Guardas com zero efeito; conferências pós-E1 | 07, 10, 13 | `test_run_confirmatory_evaluation.py::{test_guard_refuses_with_zero_effect[*], test_guards_run_in_order, test_input_changed_raises_and_seals_nothing, test_divergent_generation_with_equal_code_env_input_raises_and_seals_nothing}` |
| A5 | Replay e tentativas | 13, 14 | `test_run_confirmatory_evaluation.py::{test_sealed_intact_is_already_judged_without_refresh_or_scorecard, test_crash_between_e1_and_e3_leaves_attempt_and_no_seal, test_rerun_same_code_env_input_completes_with_two_attempts_in_run_record, test_rerun_with_changed_code_and_valid_deviation_records_it}`; integração `test_second_call_already_judged_with_same_digest_and_body`; contrato `test_preserve_removes_staging_leftover` |
| A6 | `JudgedGenerationStore` `[fake, real]` | 08, 09 | `test_judged_generation_store_contract.py` (lista da Task 09); `test_judged_generation_dtos.py` |
| A6b | `manifest_read` ≠ publicado → mismatch | 13 | `test_run_confirmatory_evaluation.py::test_scorecard_manifest_read_differs_raises_mismatch_nothing_sealed` |
| A7 | Caminho `BLOCKED` | 04, 13, 14 | `test_refresh_gold_use_case.py::test_blocked_hashes_exactly_dim_run_facts_and_realized`; `test_run_confirmatory_evaluation.py::{test_blocked_preserves_without_scorecard_and_with_failed_checks, test_blocked_second_call_is_already_judged}`; integração `test_blocked_world_seals_without_scorecard_then_already_judged` |
| A8 | `EvaluationEnvironment` (contrato), probe inalterado, sem import `evaluation → modeling` | 10, 11 | `test_evaluation_environment_contract.py`; `lint-imports` no ponto 1 |
| A9 | Integração com stores reais | 14 | `test_run_confirmatory_evaluation.py` (integração)`::test_judged_copy_equals_scorecard_mapping_and_current_bytes` |
| A10 | CLI `evaluate` e2e | 15, 16 | `test_cli.py::test_infer_with_summary_*`, `test_evaluate_*`; `test_evaluate_cli.py` |
| A11 | `make check` verde (lint, mypy, layout, import-linter, fake-parity, port-coverage, docs) | 01, 11, 17, Etapa R | pontos 1, 2 e 3 do plano de gates, saídas coladas |
| A17 | Gate de custo | 17 | `test_silver_hash_cost_measurement.py` + `[measurement] task-17` em §7 |
| A12 | Pré-condições e intenção commitada | Etapa R (R1–R3) | saídas de R1/R2 e as entradas de intenção em §7 |
| A13 | `evaluate` real até o fim | Etapa R (R4) | `eval-1.out`/`.err` em §7 |
| A14 | Integridade de fora do código | Etapa R (R5) | `CONTENTS_OK` + digest |
| A15 | Replay real sem efeito | Etapa R (R6) | `BODY_SAME`, `NO_NEW_EFFECT` |
| A16 | Atestação | Etapa R (R7–R9) | `TAG_OK`, `COMMENT_AFTER_ANCHOR`, `.judged.toml` commitado, `JUDGED_BACKUP_OK`, terceira execução `ALREADY_JUDGED` |

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas no Passo 10 do
> [`RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.
>
> **Regra de pergunta antes da nota.** Algo não previsto no Concept ou neste
> Technical → triar pela skill `evidence-resolution` (E/C decide e registra;
> P sobe ao humano com 2–4 opções e uma recomendada) e só então registrar.
>
> **Etapa R:** a intenção de cada tentativa é commitada aqui **antes** do
> `evaluate` correspondente (D12); a evidência, depois.

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

Vocabulário fechado (CONVENTIONS §3.4): `decision` (ou `decision:E` /
`decision:C`), `finding`, `deviation`, `measurement`.

<!-- END: post-execution -->
