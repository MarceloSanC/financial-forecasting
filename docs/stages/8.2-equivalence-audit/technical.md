---
title: Technical — Stage 8.2 — Reprodução da corrida confirmatória e equivalência interna
description: Plano de execução da Stage 8.2 em 11 Tasks inside-out (1 Task = 1 commit) — DTO e mapa de classes da reprodução, comparador puro, leitor da cópia julgada no port, use case de auditoria, subcomando audit-reproduction, driver da reprodução com smoke test, prova de independência de processo, e o andaime da equivalência em tests/equivalence/ — e as Etapas reais E1–E5 na ordem do D10 (registro de hashes, pré-voo em 060537fc, reprodução real, leitura de valores do anterior, teste opt-in e relatórios)
when-use: Consultar durante a Fase 4 (execução) da Stage 8.2; cada Task tem arquivos (lista fechada), testes a escrever primeiro, critério de aceite do concept que cobre e verificação; as Etapas E1–E5 trazem o runbook da parte real, com a ordem fixa do D10 e a tabela "Se falhar"
keywords: [technical, plano de execução, equivalence-audit, reproduction, evaluation, judged-generation, bit-identical, audit-reproduction, driver, prior-evidence, hash-registry, scaffold, opt-in-test, r-bit-commit]
status: done
created_at: 2026-10-23
updated_at: 2026-10-23
stage_id: 8.2-equivalence-audit
stage_title: Reprodução da corrida confirmatória e equivalência interna
step_id: 8
step_title: Reprodução, equivalência e relatório
depends_on: [8.1-confirmatory-run]
concept_ref: ./concept.md
issue_id: 232
branch: feat/232-8-2-equivalence-audit
tasks_count: 11
---

# Technical — Stage 8.2 — Reprodução da corrida confirmatória e equivalência interna

> **Como usar este documento (para code assistant):**
> 1. Ler §1 inteiro antes da Task 01 (decisões de forma fixadas aqui, a ordem
>    do D10 e o cegamento da evidência anterior).
> 2. Executar as Tasks na ordem de §2. **1 Task = 1 commit.** A lista de
>    arquivos de cada Task é **fechada**: tocar arquivo fora dela = parar e
>    perguntar (RUNBOOK Passo 8, "Escopo estrito"). Arquivos `__init__.py`
>    marcados *(pacote)* não contam na contagem de arquivos (PIPELINE §4.3 item 2).
> 3. Escrever primeiro os testes listados em "Testes primeiro" (vermelho),
>    depois o código (verde). **T1 verde antes de todo commit**; `make check`
>    só nos pontos do [plano de gates](#plano-de-gates)
>    ([RUNBOOK §Gates em camadas](../../RUNBOOK-STAGE-LIFECYCLE.md#gates-em-camadas)).
> 4. Commit: `<type>(<escopo>): <descrição> [8.2/task-NN]` (Etapas: `[8.2/--]`),
>    body em bullets, `Refs #232`, subject ≤ 100 caracteres, mensagem UTF-8
>    sem BOM por `git -C <worktree> commit -F <arquivo>`
>    ([`CONVENTIONS.md`](../../CONVENTIONS.md) §4).
> 5. Algo não previsto em §1–§6, no concept ou nos ADRs 8.2.0001–0003 → pausar,
>    triar (skill `evidence-resolution`: E/C decide e registra, ADR `8_2_0004+`
>    se tiver alternativa real; só P sobe ao humano) e registrar em §7.
> 6. Depois da Task 11, da auditoria de testes e do 1º `make check`: **Etapas
>    E1 → E5** na ordem fixa (runbook com commits próprios), §3 e `stage 8.2: complete`.
>
> **Stage = 1 branch:** `feat/232-8-2-equivalence-audit`, worktree própria.
>
> **Cegamento da evidência anterior (I6/D11, inegociável).** Nenhuma Task lê
> valor de métrica, perda, p-valor, sinal, veredito ou realizado de
> `data/analytics/`. Todo teste das Tasks usa dado **sintético** (`tmp_path`).
> A primeira leitura de valor é a da Etapa **E4**, depois do commit do registro
> (E1) e da reprodução (E3). Metadados de forma (schema pelo footer, contagens,
> rótulos de definição) são permitidos e só na E1.
>
> **Partição viva intocada (I1/I2).** Nenhuma Task nem Etapa escreve sob
> `data/cohorts/aapl/`. O container da reprodução **não monta** a partição viva;
> os que a leem montam `:ro`.

## 1. Contexto e estratégia de execução

### Resumo

A Stage tem duas partes independentes. **(i) Reprodução:** um driver fora de
`src/` (`scripts/reproduce_judged_generation.py`) roda, na árvore de `060537fc`
e na imagem `b69a7620…`, `RefreshGold` + `BuildConfirmatoryScorecard` sobre o
backup de entrada restaurado num `data_root` descartável e grava
`reproduction/{scorecard,environment}.json`; o HEAD compara, só lendo, a geração
reproduzida com a cópia julgada pelo subcomando `audit-reproduction` (leitor
`read_judged_generation` novo no port `JudgedGenerationStore`, use case
`AuditReproduction`, comparador puro `compare_reproduction` com o mapa de classes
`REPRODUCTION_CLASSES`). **(ii) Equivalência:** registro de hashes da evidência
anterior commitado antes de qualquer leitura de valor, andaime em
`tests/equivalence/` (checagem de hash, interseção, A1, A2, tabela de sentido,
tabela renderizada) e teste opt-in que afirma a tabela declarada = a tabela do
`equivalence_audit.md`.

### Estratégia (ordem e porquê)

TDD inside-out (skill `task-ordering-hex`), em três blocos de código e um
bloco real:

1. **Comparação (Tasks 01–02).** DTO + mapa de classes com teste de completude →
   comparador puro. Base de tudo o que a (i) afirma; puro, sem I/O.
2. **Leitura e entrada (Tasks 03–07).** Leitor da cópia julgada no port (port,
   fake, real e contrato juntos: **estende** um port existente com um método —
   a mesma exceção declarada da 8.1 Tasks 02/07; nenhum port novo) → use case de
   auditoria com fakes → subcomando + composition root + e2e sintético → driver +
   smoke test → independência de processo (driver em subprocesso com
   `PYTHONHASHSEED` diferentes + `audit-reproduction` real).
3. **Andaime da equivalência (Tasks 08–11).** Checagem de hash e gerador do
   registro (unit sempre ativo) + teste de isolamento → contrato `src-no-tests`
   no `import-linter` (Task própria, escopo `architecture`) → regras puras
   (interseção, A1, A2, sentido) → leitores + tabela + teste opt-in.
4. **Auditoria de testes com mutação real, Checkpoint C final e 1º `make check`**
   → **Etapas E1–E5** (ordem do D10) → **2º `make check`** (saída).

Por que todo o código antes de qualquer Etapa: o driver que a E3 roda é o
arquivo do HEAD; uma correção dele depois da E3 obrigaria a re-reproduzir. E o
andaime fica pronto (e verde no CI) antes do registro, de modo que a E4 só
executa código já revisado — nenhuma linha do andaime é escrita depois de ver
um valor do anterior (forking paths, doc §5.2).

### Decisões de forma fixadas aqui (o concept §4/§13 e os ADRs deixaram para a Fase 3B)

Todas `[decision:C]` de forma, dentro do que os ADRs 8.2.0001–0003 já decidem;
nenhuma pede ADR novo.

- **Arquivos.** `compare_reproduction` em
  `application/use_cases/reproduction_comparison.py` (nome do roadmap);
  `ReproductionComparison`, `ReproductionClass` e `REPRODUCTION_CLASSES` em
  `application/dtos/reproduction_comparison.py`.
- **`REPRODUCTION_CLASSES` cobre as colunas gravadas, não só as do schema.** O
  `GoldTableSchema` declara `key` + `read_columns`, mas os builders gravam mais
  colunas (ex.: `gold_dm_results` grava `p_value`, `long_run_variance`,
  `degrees_of_freedom`, `horizon_used`, `common_*_target_timestamp`, e toda linha
  leva `asset`, `parent_sweep_id`, `preregistration_ref` de `partition_columns`).
  O mapa é `tabela → coluna → classe` sobre **toda coluna gravada**; o comparador
  ergue `ValueError` para coluna sem classe (sem fallback por tipo — concept §4);
  o teste de completude unitário cobre `key` + `read_columns` + colunas de
  partição de todo `GOLD_SCHEMAS`, e o de integração (Task 07) cobre toda coluna
  de toda tabela não vazia de uma geração `COMPLETED` sintética com as 19
  tabelas. Refinamento do concept §4 ("toda coluna de todo `GoldTableSchema`"),
  sem mudar contrato.
- **Igualdade de valor.** `float` × `float` por bits (`struct.pack(">d", x)`);
  `int`/`bool`/`str`/`None` por `==` **e** mesmo tipo (`1` × `1.0` e `True` × `1`
  são diferentes). Linhas casadas pela `key` do `GOLD_SCHEMAS`; chave só de um
  lado → `keys_equal = false` e contada como diferença R1 da tabela. max |Δ| só
  quando os dois valores são numéricos não-`bool`; NaN ou ±inf num lado e bits
  diferentes → max |Δ| = `inf`. Classe R1 não numérica reporta só a contagem.
- **Scorecard.** Comparação recursiva das folhas dos dois `Mapping` JSON
  (judged: `documents[SCORECARD_DOCUMENT]` da cópia; reproduzido:
  `reproduction/scorecard.json`), sem `manifest_read.started_at` /
  `manifest_read.finished_at` (as chaves de `RESULT_EXCLUDED_KEYS`); folhas
  numéricas por bits, max |Δ| sobre elas, caminho JSON das diferentes (até 20 no
  DTO).
- **`expected_result_digest`** = `result_digest` da **última** linha `input_read`
  com `preregistration_ref` = a ref no `ATTEMPTS.jsonl` da raiz julgada (a 8.1
  tem uma tentativa; re-execuções sem `--deviation` têm de reproduzir o mesmo
  digest — I13 da 8.1). Nenhuma linha `input_read` da ref →
  `ReproductionAuditError`.
- **Use case `AuditReproduction`** (`application/use_cases/audit_reproduction.py`)
  faz as leituras do subcomando com ports (`PreregistrationSource`, `Hasher`,
  `JudgedGenerationStore` da raiz julgada, `GoldGenerationReader` da raiz
  reproduzida): resolve a revisão (`resolve_judged_revision`) e a partição
  (`refresh_command_from(plan, ref).partition`); exige o registro `.judged.toml`
  da ref com `generation_digest` igual ao da cópia (`find`), senão
  `JudgedGenerationTamperedError` (ausente → `ReproductionAuditError`); lê a cópia
  por `read_judged_generation`, o scorecard da cópia (ausente →
  `ReproductionAuditError`), o `expected_result_digest`, a geração reproduzida por
  `read_generation`; chama `compare_reproduction`. O adapter de CLI fica fino
  (lê o `scorecard.json`, imprime, devolve o exit) — concept §4 "subcomando", ADR
  8.2.0002 item 4; não muda contrato.
- **Erro de cópia ausente:** `JudgedGenerationNotFoundError(ApplicationError)`,
  no módulo do port (precedente `JudgedGenerationTamperedError`).
- **`audit-reproduction` — saída (stdout; contrato da E3), exit 0 só com
  `bit_identical`, 1 com diferença (precedente `EXIT_MISMATCH` do `verify`), 2 em
  erro:**
  ```
  reproduction <ref>: bit_identical <true|false> partition <asset>/<parent_sweep_id>
  result_digest judged <64 hex> reproduced <64 hex> expected <64 hex>
  identity <campo> judged <v> reproduced <v> equal <true|false>          # 4 linhas
  class <R1|R2|R3> compared <n> different <n> max_abs_diff <repr>         # totais
  table <nome> rows <n>/<n> keys_equal <bool> R1 <c>/<d>/<m> R2 <c>/<d>/<m> R3 <c>/<d>/<m>
  scorecard equal <bool> leaves <n> different <n> max_abs_diff <repr>
  ```
  O subcomando não usa o helper `add()` do `cli.py` (não tem `--data-root`,
  `--cohort` nem lock); é despachado antes do `wire_dependencies` (não monta o
  grafo inteiro) por `composition_root.wire_reproduction_audit(settings, *,
  judged_data_root, reproduced_data_root) -> AuditReproduction` (dois
  `ParquetGoldStore`, `TomlPreregistrationSource(<repo_root>/config/preregistration)`,
  `CanonicalJsonHasher`). Raízes iguais (após `resolve()`) → recusa antes de
  montar qualquer adapter (exit 2).
- **Driver** (`scripts/reproduce_judged_generation.py`; ADR 8.2.0001 itens 3 e 7):
  - argumentos: `--data-root`, `--cohort`, `--preregistration`, `--revision`,
    `--preregistration-ref`, `--check`;
  - recusas, nos dois modos, antes de montar o wiring: caminho resolvido com
    as partes consecutivas `data`/`cohorts`; `gold/` ou `reproduction/` já
    existente no `data_root`;
  - `reproduce(*, deps, source, data_root, cohort, name, revision,
    preregistration_ref, snapshot, check, out) -> int` (testável com fakes) e
    `main(argv=None, *, wire=wire_dependencies) -> int` (`wire_dependencies`
    existe em `060537fc`; o smoke test injeta `wire`), que monta `deps = wire_dependencies(Settings(data_root=...))`,
    `source = TomlPreregistrationSource(root=Path("config/preregistration"))` e
    `snapshot = deps.run_confirmatory_evaluation_for(cohort, "cpu")._environment.snapshot`
    (acesso privado declarado — ADR 8.2.0001 item 7);
  - ordem: resolver a revisão → foto (`snapshot()`) → `--check`: escreve no stdout
    exatamente os bytes `document_bytes(foto)` (os mesmos do `environment.json`;
    nenhuma outra linha no stdout) e sai 0, **nada gravado**; senão cria
    `reproduction/`, grava `environment.json` = `document_bytes(foto)` **antes**
    do refresh → `refresh_gold(refresh_command_from(plan, ref))` → status ≠
    `COMPLETED` → stderr + exit 1, sem scorecard → `build_confirmatory_scorecard(
    BuildConfirmatoryScorecardCommand(name, revision, ref))` → grava
    `scorecard.json` = `document_bytes(scorecard.as_mapping())`;
  - stdout do modo normal: `reproduction <ref>: refresh <STATUS> tables <n>` e
    `reproduction <ref>: scorecard sha256 <64 hex>`; exceções sobem (exit ≠ 0,
    traceback): o driver não traduz erro;
  - só importa nomes presentes em `060537fc` (o `--check` em `060537fc` é a prova:
    `ImportError` ali = parada).
- **Andaime (`tests/equivalence/`).** Variáveis do teste opt-in:
  `EQUIVALENCE_ORACLE_ROOT` (raiz `data/analytics/` do anterior) e
  `EQUIVALENCE_OFFICIAL_ROOT` (a partição viva `data/cohorts/aapl`, montada
  `:ro` — o silver, o dataset e a cópia julgada; nada é escrito). O andaime monta
  só os adaptadores de leitura de que precisa (sem `wire_dependencies`: nada de
  ledger, MLflow ou lock). Registro: `docs/reports/prior_evidence_registry.toml`,
  forma:
  ```toml
  registry_version = 1
  root = "data/analytics"
  [[file]]
  path = "gold/gold_oos_consolidated.parquet"
  sha256 = "<64 hex>"
  rows = 410208
  columns = [{ name = "schema_version", type = "int64" }, ...]   # ordem do footer
  ```
  (mais `[[definition_source]]` se a E1 achar fonte de definição de baseline —
  ver E1).
- **Conjunto lido da evidência anterior (concept §13, D12 c; fixado aqui, antes
  de qualquer valor).** O registro contém **só** os arquivos que o andaime lê
  (D5: "o conjunto lido é o do registro e nenhum outro"), com sha256 iguais aos
  de D-M1:

  | arquivo (`data/analytics/`) | serve a | colunas de filtro/forma | colunas de valor |
  |---|---|---|---|
  | `gold/gold_oos_consolidated.parquet` | A9 (y_ant), A10 (predições → m_A), A11 (m_A) | `run_id`, `parent_sweep_id`, `split`, `config_signature`, `seed`, `fold`, `horizon`, `target_timestamp_utc`, rótulo de modelo (`model_version_x` ou `model_version_y` — o que D-M2 usou; fixado na E1 pela lista de rótulos distintos, sem valor) | `y_true`, `quantile_p{10,50,90}`, `quantile_p{10,50,90}_post_guardrail`, `quantile_guardrail_applied` |
  | `gold/gold_prediction_metrics_by_run_split_horizon.parquet` | A10 (m_ant por run) | `run_id`, `parent_sweep_id`, `config_signature`, `split`, `fold`, `seed`, `horizon`, `n_samples` | `pinball_q{10,50,90}_{raw,post_guardrail}`, `picp_{raw,post_guardrail}`, `mpiw_{raw,post_guardrail}` |
  | `gold/gold_prediction_calibration.parquet` | A10 (m_ant por run) | `run_id`, `parent_sweep_id`, `config_signature`, `split`, `horizon`, `n_samples` | as mesmas de valor da linha acima |
  | `reports/phase_b/cohort=phase_b_confirmatorio_20260524/phase_b_marginal_coverage.parquet` | A10 (m_ant por run, sem rótulo de variante → `post_guardrail`, D12 c) | `run_id`, `split`, `horizon`, `n_obs` | `picp_q10_q90`, `mpiw` |
  | `reports/phase_b/cohort=phase_b_confirmatorio_20260524/phase_b_dm_family_6.parquet` | A11 (DM do anterior, D8) | `horizon`, `baseline_model_version`, `split`, `analysis_role`, `loss_function`, `dedup_rule`, `seed_aggregation`, `hln_applied`, `hac_lag_used`, `n_obs_effective` | `mean_loss_diff_tft_minus_baseline`, `pvalue_one_sided_less` |

  Fora do registro (de D-M1, não lidos), com o motivo: `phase_b_delta_pinball`
  (média da grade P̄_G, não pinball por nível — fora da interseção, doc §5.3, e
  as predições por ponto existem); `phase_b_dm_family_18_sensitivity` (não é a
  família primária, D8); `phase_b_tier_verdict` (decisões de família/gate: não
  se cruzam, doc §5.3); `gold_dm_pairwise_results` e `gold_mcs_results` (DM/MCS
  entre configurações com Holm/MCS do anterior: fora da interseção, doc §5.3).
  Filtros fixos: `parent_sweep_id = phase_b_confirmatorio_20260524`,
  `split = test`, `horizon ∈ {1, 7}`; A10 cobre **toda** linha desses filtros
  (candidato e baselines — "as predições do candidato anterior entram como as de
  qualquer modelo", doc §5.3 item 1).
- **D8 fechado na coluna (antes dos valores).** O p "do teste primário" do
  anterior é `pvalue_one_sided_less`: o nome declara a alternativa
  unilateral `mean_loss_diff_tft_minus_baseline < 0` (candidato melhor), a mesma
  do lado novo (`p_value = P(t_{T-1} ≤ S)`, `diebold_mariano.py`); α do anterior =
  0,05 (declarado no nome `significant_adj_0_05`); `pvalue_two_sided` e
  `pvalue_one_sided` entram como contexto declarado. Lado novo:
  `gold_dm_results` da **cópia julgada** (`read_judged_generation`), estimador
  primário retangular (ADR 6.5.0006), `p_value` (não o `adjusted_p_value`) ≤
  `alpha` da linha, sinal de `mean_differential` (candidato − comparador, do
  código), também onde H1 reprova.
- **D7 na mecânica.** Ponto do anterior num `target_timestamp` com duas janelas
  = o da janela de teste **mais recente** (início de teste maior do
  `config_signature`), regra declarada `operationally_latest_fold`; o lado novo
  tem um ponto por timestamp (folds disjuntos).
- **Realizado do lado novo (D-M6, A9).** y_novo(h, t) = `RealizedReturns(...)
  .realized_at(t)` sobre a grade do `ReadTrainingGrid` real da partição viva
  (`timestamps_iso()` + coluna `target_return`), a mesma montagem do
  `RefreshGold._read_realized`; o `dataset_fingerprint` lido tem de ser o da cópia
  julgada (`00e4406d…`), senão parar.
- **Variante e níveis do lado novo.** A variante pontuada pelo lado novo e a regra
  da banda de Wilson do "lado do nominal" saem do **código** (`series_assembly`,
  `HorizonReports`, `CalibrationTable`), conferidas na Task 10 e gravadas como
  constantes em `tests/equivalence/comparison_set.py` com o caminho de código na
  docstring — nunca de um número.
- **Diagnóstico pré-declarado** (antes de qualquer resultado; percorrido na
  ordem, cada passo registrado em §7):
  - *Reprodução não bit a bit com I3–I4 satisfeitas (I5):* (1) processo novo /
    `PYTHONHASHSEED` (pré-checado na Task 07: se ela passou, só um caminho não
    exercitado pelo mundo sintético); (2) ordem de leitura de arquivos no bind
    mount (listagem de diretório do backup restaurado × da partição viva); (3)
    threads (`env.probe.torch_threads`, `cpu.max`) e BLAS; (4) `.env`/`Settings`
    da árvore (`.env` copiado, sha256 registrado); (5) entrada (identidade — I3
    já separa); (6) estado aleatório (colunas R3: `reps`, `seed` do MCS e do H3);
    (7) caminho dependente de relógio fora de `started_at`/`finished_at`. Nenhuma
    tolerância salva a falha; nada substitui a geração julgada (doc §4.6).
  - *A1 fora (D13):* (1) definição do realizado multi-passo; (2) ajuste de preço
    (ADR 3.5.0001); (3) mapeamento de `target_timestamp` (pregão × dias corridos;
    a interseção h=7 menor de D-M5 é o indício); (4) caminho float32 (descartado
    por D-M6, mantido).
  - *A2 fora:* as linhas da tabela da §5.4 aplicáveis à grandeza (§5.6,
    aplicabilidade), na ordem: escala (fator 2) → bruto × rearranjado → convenção
    de empate → amostra (pontos, dedup, exclusões; `n_samples`/`n_obs` contra os
    pontos lidos) → pesos na grade → defeito referenciado; sem linha que preveja
    o efeito → `[finding]`.
  - *Sentido divergente:* só as categorias da tabela de aplicabilidade da §5.6;
    "features/dados/hiperparâmetros" é contexto, nunca explicação.

### Comandos no container

Fluxo Docker-only (as worktrees rodam por `docker run` avulso). Git Bash;
caminhos com barra normal (com `\` o bind mount sai vazio sem erro):

```bash
WT=feat-232-8-2-equivalence-audit
RUN="docker run --rm --cpus 6 --memory 8g --memory-swap 8g \
  -v C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/$WT:/app \
  -v C:/Users/Marcelo/Documents/Code/financial-forecasting/.git:/main.git \
  -v financial-forecasting_app-venv:/app/.venv \
  -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app -w /app financial_forecasting-app:dev"
PRE="git config --global --add safe.directory '*'"
# T1 de uma Task (testes + ruff/mypy dos arquivos, RUNBOOK "T1 sem o hook"):
MSYS_NO_PATHCONV=1 $RUN sh -c "$PRE; uv run --no-sync pytest <arquivos> -q --no-cov && uv run --no-sync ruff format --check <arquivos> && uv run --no-sync ruff check <arquivos> && uv run --no-sync mypy"
```

T3 (`make check`) — comando literal; **`PYTEST_PAR` como argumento do make**
(atribuição do Makefile vence a variável de ambiente — finding da 8.1, ponto 1):

```bash
MSYS_NO_PATHCONV=1 docker run --rm --cpus 6 --memory 8g --memory-swap 8g -v "C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/feat-232-8-2-equivalence-audit:/app" -v "C:/Users/Marcelo/Documents/Code/financial-forecasting/.git:/main.git" -v financial-forecasting_app-venv:/app/.venv -e GIT_DIR=/main.git/worktrees/feat-232-8-2-equivalence-audit -e GIT_WORK_TREE=/app -w /app financial_forecasting-app:dev sh -c "git config --global --add safe.directory '*'; make check PYTEST_PAR='-n 4 --dist loadgroup'"
```

Conferir no log que só sobem `gw0..gw3`. Worker do xdist caído ("node down",
CPU ~0 % perto do fim) invalida o resultado: parar e rodar de novo.

### Pré-condições

- Concept `done` (`2b1f1bfe`) e ADRs 8.2.0001–0003; 8.1 mergeada (PR #231).
- Imagem `sha256:b69a7620e7bd8449369bde2f46e903c5f46c25e9efb3597f452af3272e0a8f45`
  presente (conferida na Fase 3B: é a tag `:dev` atual); **nenhum `docker image
  prune`** até a E3 fechar; não atualizar o WSL até a E3 (kernel em
  `env.platform`).
- Etapas: partição viva `data/cohorts/aapl/` com a cópia julgada e o
  `ATTEMPTS.jsonl`; backups `data/backups/aapl-pre-8.1-20261023-084758` (+
  `.sha256sum`) e `judged-…-20261023-084758` (+ `.sha256sum`); `data/analytics/`
  do anterior; ~1 GB livre em `C:` (o disco tem ~40 GB).

### Premissas técnicas

- Python 3.12, mypy strict (`src`, `tests/contract`, `tests/fakes`),
  `from __future__ import annotations`.
- `scripts/check_port_coverage.py`: o método novo do port precisa de fake e
  contrato `[fake, real]`; `scripts/check_fake_parity.py`: a leitura da geração
  tem dono único — o fake devolve a `GoldGeneration` guardada no `preserve`, o
  real relê os arquivos; nenhum bloco ≥ 15 linhas duplicado.
- `scripts/check_use_case_deps.py`: o `__init__` do `AuditReproduction` anota só
  ports.
- `tests/architecture/test_unit_evaluation_purity.py`: os unit de
  `tests/unit/features/evaluation/` não importam `*.adapters.*` nem abrem
  arquivo — os testes que precisam de Parquet real ficam em `contract/`,
  `integration/` ou `tests/equivalence/`.
- `scripts/` fica fora da cobertura (`omit`); o smoke test do driver mora em
  `tests/unit/tooling/` (precedente `test_check_technical_postexec.py`, import por
  `importlib.util.spec_from_file_location`).
- O driver roda com `/app` = árvore de `060537fc`: o editable install do volume
  `financial-forecasting_app-venv` aponta para `/app/src`, então o
  `financial_forecasting` importado é o de `060537fc`.

### Plano de gates

| # | Depois da Task | Por quê |
|---|---|---|
| 1 | 11 (depois da auditoria de testes com mutação real e do Checkpoint C final) | Pré-corrida: muda port consumido pelo composition root e pela 8.3 (`read_judged_generation`), o composition root e o `cli.py` (Task 05), o `.importlinter` e o `test_import_contracts.py` (Task 09) e um teste de arquitetura (Task 08) — o T1 não roda `tests/architecture/` nem os scripts de gate. O driver que a E3 executa e o `audit-reproduction` que a julga têm de estar verdes como no CI **antes** da E2: uma correção do driver depois da E3 obriga a re-reproduzir (~15 min de refresh e a evidência refeita). Um ponto antes (depois da 05) não se paga: as Tasks 06–11 não constroem sobre um contrato que o gate pudesse invalidar além do que o T1 delas já exercita. |
| 2 | saída (depois da E5) | Gate de saída (Passo 10): a E1/E5 acrescentam `tests/equivalence/comparison_set.py` e a tabela declarada do teste opt-in (lint, mypy fora de escopo, coleta e skip no CI), o registro e os relatórios. |

Nas demais Tasks o gate é o T1 da Task. Vermelho no ponto 1 → `fix(<escopo>): …
[8.2/task-NN-fix]` e novo `make check` (3º ponto, justificado: só o commit verde
pode ser o do driver da E3).

### Estrutura de pastas afetada

```
scripts/{reproduce_judged_generation.py, reproduction_evidence.py}     # novos (T06)
src/financial_forecasting/
├── cli.py                                                             # audit-reproduction (T05)
├── composition_root.py                                                # wire_reproduction_audit (T05)
└── features/evaluation/
    ├── application/
    │   ├── dtos/reproduction_comparison.py                            # novo (T01)
    │   ├── ports/out/judged_generation_store.py                       # read_judged_generation (T03)
    │   └── use_cases/{reproduction_comparison.py, audit_reproduction.py}   # novos (T02, T04)
    └── adapters/
        ├── in/cli/evaluation_commands.py                              # audit_reproduction (T05)
        └── out/duckdb/parquet_gold_store.py                           # read_judged_generation (T03)
tests/
├── fakes/features/evaluation/in_memory_judged_generation_store.py     # T03
├── unit/features/evaluation/{test_reproduction_comparison_dtos.py,
│                             test_compare_reproduction.py, test_audit_reproduction.py}   # T01, T02, T04
├── unit/test_cli.py                                                   # T05
├── unit/tooling/{test_reproduce_judged_generation.py, test_reproduction_evidence.py}   # T06
├── contract/features/evaluation/test_judged_generation_store_contract.py   # T03
├── integration/features/evaluation/{test_audit_reproduction_cli.py,
│                                    test_reproduction_process_independence.py}   # T05, T07
├── architecture/test_prior_evidence_isolation.py                      # T08
├── architecture/test_import_contracts.py                              # T09
└── equivalence/                                                       # andaime (T08, T10–T11, E1, E5)
    ├── __init__.py, prior_evidence.py, comparison_set.py, alignment.py,
    ├── comparisons.py, readers.py, audit_table.py
    └── test_prior_evidence_registry_check.py, test_scaffold_comparisons.py,
        test_audit_table_render.py, test_official_vs_prior_evidence.py
.importlinter                                                          # contrato src-no-tests (T09)
docs/LAYOUT.md                                                         # §2 tests/equivalence/, §3 src ↛ tests (T09)
docs/reports/{prior_evidence_registry.toml, reproduction_audit.md, equivalence_audit.md}   # E1, E3, E4/E5
```

## 2. Tasks

### Task 01 — DTO `ReproductionComparison` e mapa `REPRODUCTION_CLASSES`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/reproduction_comparison.py`
  - `tests/unit/features/evaluation/test_reproduction_comparison_dtos.py`
- **Testes primeiro:** `test_every_schema_column_has_a_declared_class` (toda
  coluna de `key` + `read_columns` de todo `GOLD_SCHEMAS`, mais `asset`,
  `parent_sweep_id`, `preregistration_ref`, tem classe; nenhuma tabela do mapa
  fora de `GOLD_SCHEMAS`); `test_random_dependent_floats_are_r3` (p-valores do
  MCS e da sensibilidade de bloco, p-valores de Monte Carlo do Christoffersen,
  limites bootstrap de H3 — lista explícita por tabela/coluna); 
  `test_non_float_columns_are_r1` (contagens, decisões, rótulos, timestamps das
  chaves); `test_identity_field_equal_is_derived_from_sides`;
  `test_bit_identical_requires_identity_digests_tables_and_scorecard` (cada um dos
  quatro falso isoladamente → `False`); `test_class_comparison_rejects_negative_counts_and_max_for_non_numeric`.
- **O que fazer:** `ReproductionClass(StrEnum)` R1/R2/R3;
  `REPRODUCTION_CLASSES: Mapping[str, Mapping[str, ReproductionClass]]`
  (`MappingProxyType`, tabela → coluna gravada → classe; colunas gravadas
  conferidas nos builders de `adapters/out/duckdb/gold_builders/`); DTOs frozen
  `IdentityComparison` (campo, judged, reproduced, `equal`), `ClassComparison`
  (classe, `compared`, `different`, `max_abs_diff: float | None` — `None` para R1
  não numérica), `TableComparison` (nome, linhas de cada lado, `keys_equal`,
  classes), `ScorecardComparison` (`equal`, `leaves`, `different`,
  `max_abs_diff`, `paths` ≤ 20), `ReproductionComparison` (`preregistration_ref`,
  `partition`, identidade × 4, `result_digest` judged/reproduced/expected, tabelas,
  totais por classe, scorecard, propriedade `bit_identical`). Validação na
  construção (`ValueError`).
- **Critério de aceite:** A6 (completude; `bit_identical` composto).
- **Verificação (T1):** `pytest tests/unit/features/evaluation/test_reproduction_comparison_dtos.py -q --no-cov`
- **Commit:** `feat(evaluation): DTO da comparação da reprodução e mapa de classes [8.2/task-01]`

---

### Task 02 — Comparador puro `compare_reproduction`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/reproduction_comparison.py`
  - `tests/unit/features/evaluation/test_compare_reproduction.py`
- **Testes primeiro** (gerações sintéticas montadas por `GoldGeneration.from_stored`
  com `InMemoryGoldStore`/helpers de `tests/unit/features/evaluation/`):
  `test_identical_generations_are_bit_identical_with_zero_max_per_class` (contagens
  `compared` > 0 em R1, R2 e R3; `different` 0; max |Δ| 0.0);
  `test_one_ulp_in_r2_float_is_reported_in_r2_with_its_delta`
  (`math.nextafter`; max |Δ| = o ulp exato); `test_one_ulp_in_r3_float_is_reported_in_r3`;
  `test_integer_off_by_one_is_r1_with_max_1`; `test_label_change_is_r1_count_without_max`;
  `test_negative_zero_differs_from_zero`; `test_nan_payloads_compared_by_bits`;
  `test_int_and_float_of_same_value_differ`; `test_missing_or_extra_key_row_sets_keys_equal_false`;
  `test_started_and_finished_at_differences_do_not_count` (manifesto e
  `manifest_read` do scorecard); `test_other_scorecard_leaf_differs_with_path`;
  `test_scorecard_key_only_on_one_side_differs` (chave a mais ou a menos num lado,
  fora das excluídas → `equal = false`, caminho listado);
  `test_identity_mismatch_is_not_bit_identical` (cada campo: `silver_content.digest`,
  `dataset_fingerprint`, ref, partição); `test_result_digest_other_than_expected_is_not_bit_identical`
  (os dois lados iguais entre si, ≠ esperado); `test_undeclared_column_raises`.
- **O que fazer:** `compare_reproduction(*, judged, judged_scorecard, reproduced,
  reproduced_scorecard, expected_result_digest) -> ReproductionComparison` com a
  assinatura do concept §4 e as regras de igualdade do §1; `result_layer_digest`
  dos dois lados (reuso, `dtos/judged_generation.py`); identidade lida dos
  manifestos. Função pura, sem I/O.
- **Critério de aceite:** A6.
- **Verificação (T1):** `pytest tests/unit/features/evaluation/test_compare_reproduction.py -q --no-cov`
- **Commit:** `feat(evaluation): comparação da reprodução por classe com igualdade por bits [8.2/task-02]`

---

### Task 03 — `read_judged_generation` no `JudgedGenerationStore` (port, fake, real e contrato)

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/ports/out/judged_generation_store.py`
  - `tests/fakes/features/evaluation/in_memory_judged_generation_store.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/parquet_gold_store.py`
  - `tests/contract/features/evaluation/test_judged_generation_store_contract.py`
- **Testes primeiro** (`[fake, real]`, na suíte existente):
  `test_read_judged_generation_equals_the_generation_preserved` (tabelas, linhas e
  manifesto iguais aos da geração viva no momento do `preserve`;
  `result_layer_digest` igual); `test_read_judged_generation_after_new_publish_returns_the_judged_one`;
  `test_read_judged_generation_without_copy_raises_not_found`;
  `test_read_judged_generation_refuses_tampered_copy[altered|missing|extra|empty_generation]`
  (`JudgedGenerationTamperedError`, mesmo parametrize do `find`);
  `test_read_judged_generation_refuses_copy_moved_to_another_reference`; perna real:
  `test_real_reads_generation_dir_even_without_current` (apaga `current/` depois do
  selo).
- **O que fazer:** método do concept §4 no Protocol (docstring: verifica
  `CONTENTS.sha256` como o `find`; sem cópia → `JudgedGenerationNotFoundError`, erro
  novo no módulo do port); real no `ParquetGoldStore`: `find` (integridade) e
  depois a leitura de `judged/<ref>/generation/` pela **mesma** função privada da
  `read_generation` (extrair `_read_generation_dir(directory, partition)`; sem
  duplicar a montagem); manifesto/tabela ilegível na cópia →
  `JudgedGenerationTamperedError`. Fake: guarda a `GoldGeneration` copiada no
  `preserve` e a devolve depois do `find`.
- **Critério de aceite:** A5.
- **Verificação (T1):** `pytest tests/contract/features/evaluation/test_judged_generation_store_contract.py tests/contract/features/evaluation/test_gold_generation_reader_contract.py -q --no-cov`
- **Commit:** `feat(evaluation): leitura da cópia julgada como GoldGeneration [8.2/task-03]`

---

### Task 04 — Use case `AuditReproduction` com fakes

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/audit_reproduction.py`
  - `tests/unit/features/evaluation/test_audit_reproduction.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/reproduction_comparison.py`
    (`AuditReproductionCommand`: `name`, `revision`, `preregistration_ref`,
    `reproduced_scorecard: Mapping[str, object]`)
- **Testes primeiro** (fakes `InMemoryPreregistrationSource` com `add_judged`,
  `InMemoryJudgedGenerationStore`, `InMemoryGoldGenerationReader`):
  `test_reproduced_equal_to_judged_is_bit_identical`;
  `test_expected_digest_is_last_input_read_of_the_ref`;
  `test_without_input_read_raises_audit_error`;
  `test_without_committed_record_raises_audit_error`;
  `test_record_digest_other_than_copy_raises_tampered`;
  `test_copy_without_scorecard_raises_audit_error`;
  `test_partition_comes_from_the_resolved_plan`;
  `test_reproduced_other_partition_or_missing_generation_propagates`
  (`GoldManifestNotFoundError`); `test_reads_never_write` (contadores de
  `preserve`/`record_attempt` do fake em zero).
- **O que fazer:** `AuditReproduction(source, hasher, judged_store,
  reproduced_reader).__call__(command) -> ReproductionComparison` pela ordem do §1;
  `ReproductionAuditError(ApplicationError)` no módulo.
- **Critério de aceite:** A3 (parte de software), base do A5/A6 em uso.
- **Verificação (T1):** `pytest tests/unit/features/evaluation/test_audit_reproduction.py tests/unit/features/evaluation/test_reproduction_comparison_dtos.py -q --no-cov`
- **Commit:** `feat(evaluation): auditoria da reprodução contra a cópia julgada [8.2/task-04]`

---

### Task 05 — Subcomando `audit-reproduction`, wiring e ponta a ponta sintético

- **Arquivos a modificar:**
  - `src/financial_forecasting/composition_root.py` (`wire_reproduction_audit`)
  - `src/financial_forecasting/features/evaluation/adapters/in/cli/evaluation_commands.py`
    (`audit_reproduction(...)`)
  - `src/financial_forecasting/cli.py` (subparser sem `add()`, despacho antes do
    `wire_dependencies`, docstring do módulo)
  - `tests/unit/test_cli.py`
- **Arquivos a criar:**
  - `tests/integration/features/evaluation/test_audit_reproduction_cli.py` (`integration`, `slow`)
- **Testes primeiro:** unit — `test_audit_reproduction_requires_both_roots_and_revision`;
  `test_audit_reproduction_refuses_equal_roots_before_wiring_exit_2`;
  `test_audit_reproduction_exit_0_only_when_bit_identical` (comando com use case
  fake: `bit_identical` → 0, senão 1); `test_audit_reproduction_prints_contract_lines`.
  E2E (mundo julgado sintético da 8.1 — `_judged_world` de
  `tests/integration/features/evaluation/test_run_confirmatory_evaluation.py` — e o
  `.judged.toml` gravado como no fixture `judged_toml`; raiz reproduzida = cópia do
  `data/` do mundo com o `gold/` vivo + `reproduction/scorecard.json` =
  `document_bytes` do scorecard da cópia): `test_copy_of_judged_is_bit_identical_exit_0`;
  `test_one_float_changed_in_reproduced_table_exit_1_with_r2_line`;
  `test_altered_leaf_in_reproduced_scorecard_json_exit_1_with_scorecard_line`
  (uma folha numérica do `reproduction/scorecard.json` alterada, geração intacta →
  exit 1 e linha `scorecard equal false`: prova que o subcomando lê o arquivo e
  não recalcula); `test_tampered_judged_copy_exit_2`;
  `test_judged_toml_with_other_digest_exit_2`;
  `test_missing_reproduced_scorecard_exit_2`; `test_nothing_written_in_either_root`
  (sha256 de todo arquivo das duas raízes antes e depois).
- **O que fazer:** como no §1 (saída, exits, recusa, `settings_overrides` do
  `CliWiring` alimentando o `Settings(**overrides)` do subcomando, para o
  `repo_root` do e2e).
- **Critério de aceite:** A3 (o `audit-reproduction` lê sem recalcular, só
  leitura, exit 0 só com `bit_identical`), §6 do concept (raízes iguais, cópia
  adulterada).
- **Verificação (T1):** `pytest tests/unit/test_cli.py tests/integration/features/evaluation/test_audit_reproduction_cli.py -q --no-cov`
- **Commit:** `feat(evaluation): subcomando audit-reproduction só leitura [8.2/task-05]`

---

### Task 06 — Driver da reprodução, scripts de evidência e smoke tests

- **Arquivos a criar:**
  - `scripts/reproduce_judged_generation.py`
  - `scripts/reproduction_evidence.py`
  - `tests/unit/tooling/test_reproduce_judged_generation.py`
  - `tests/unit/tooling/test_reproduction_evidence.py`
- **Testes primeiro** — driver (deps falsas: objeto com `hasher`, `refresh_gold`,
  `build_confirmatory_scorecard`, `run_confirmatory_evaluation_for` devolvendo um
  objeto com `_environment.snapshot`; `source` = `InMemoryPreregistrationSource`;
  registro de chamadas em ordem): `test_calls_snapshot_then_refresh_then_scorecard`;
  `test_writes_environment_before_refresh_and_document_bytes_of_scorecard`
  (bytes = `document_bytes(...)` nos caminhos fixos);
  `test_check_mode_prints_snapshot_and_writes_nothing_nor_refreshes`;
  `test_check_stdout_equals_environment_json_bytes` (mesma foto: stdout do
  `--check` == bytes do `environment.json` do modo normal — base do
  `SNAPSHOT_SAME_AS_CHECK` da E3);
  `test_refuses_data_root_under_data_cohorts` (também via `..` e link relativo
  resolvido); `test_refuses_existing_gold_or_reproduction[gold|reproduction]`
  (nos dois modos, antes do wiring); `test_refresh_not_completed_exits_1_without_scorecard`;
  `test_snapshot_error_propagates_before_any_write` (ex.: `MissingImageIdError`);
  `test_main_wires_snapshot_from_run_confirmatory_evaluation_for_cpu`
  (`main(argv, wire=<fake>)`: `run_confirmatory_evaluation_for(cohort, "cpu")`).
  Scripts de evidência (stdlib, sem importar `financial_forecasting`):
  `test_env_equal_passes_on_identical_keys_and_values`;
  `test_env_equal_fails_listing_missing_extra_and_different_keys` (inclusive
  `commit` e `code_dirty`/`preregistration_dirty` ≠ `"false"`);
  `test_env_equal_reads_the_started_line_only`;
  `test_ast_equal_ignores_docstrings_and_joined_fstrings`;
  `test_ast_equal_flags_code_change`; `test_ast_equal_lists_added_or_deleted_files_apart`
  (repositório git temporário em `tmp_path` com dois commits).
- **O que fazer:** driver como no §1 (argumentos, recusas, ordem, saídas;
  docstring com o contrato do concept §4 e o porquê do acesso privado).
  `reproduction_evidence.py` (CB-7 do Checkpoint B: as evidências de A2/A7 saem
  de código versionado e testado, não de script de sessão), subcomandos:
  `env-equal <ATTEMPTS.jsonl> <foto.json>` — compara a linha `phase = started`
  com a foto (`commit`; `code_dirty` e `preregistration_dirty` = `"false"`;
  conjunto e valores de `code.*` = `code` e de `env.*` = `environment`); imprime
  `ENV_EQUAL` e sai 0, ou as chaves divergentes e sai 1. `ast-equal <rev_a>
  <rev_b> [--paths src/]` — auto-teste embutido (docstrings diferentes ⇒ igual;
  `x = 1` × `x = 2` ⇒ diferente; f-strings adjacentes unidas ⇒ igual), depois,
  para cada arquivo `M` de `git diff --name-only <a> <b> -- src/`, `ast.dump` das
  duas versões (`git show`) com o docstring removido do corpo de todo
  `Module`/`ClassDef`/`FunctionDef`/`AsyncFunctionDef` (`pass` se o corpo
  esvaziar); `AST_EQUAL`/`AST_DIFF` por arquivo, arquivos `A`/`D`/`R` à parte,
  `files <n> ast_diff <n>`, exit 1 se `ast_diff > 0` ou se houver A/D/R.
- **Critério de aceite:** A3b (smoke test), base do A2 e do A7.
- **Verificação (T1):** `pytest tests/unit/tooling/test_reproduce_judged_generation.py tests/unit/tooling/test_reproduction_evidence.py -q --no-cov` (+ ruff dos dois scripts)
- **Commit:** `feat(tooling): driver da reprodução e scripts de evidência [8.2/task-06]`

---

### Task 07 — Independência de processo e completude sobre colunas gravadas

- **Arquivos a criar:**
  - `tests/integration/features/evaluation/test_reproduction_process_independence.py`
    (`integration`, `slow`)
- **Testes primeiro:** mundo julgado sintético (como a Task 05) com o
  `.judged.toml`; duas cópias do `data/` do mundo **sem** `gold/`; em cada uma, um
  subprocesso (`sys.executable`, `cwd` = raiz do mundo, `env` com
  `PYTHONHASHSEED=0` numa e `PYTHONHASHSEED=4242` noutra) importa o driver pelo
  caminho e chama `reproduce(...)` com `deps = wire_dependencies(Settings(data_root=<cópia>,
  repo_root=<mundo>))` e `snapshot` constante:
  `test_reproduced_result_digest_is_independent_of_hash_seed` (os dois
  `result_layer_digest` iguais entre si e ao `result_digest` da `input_read` do
  mundo julgado); `test_audit_reproduction_is_bit_identical_for_both_copies`
  (`cli.main([... "audit-reproduction" ...])` → 0 nas duas);
  `test_every_stored_column_has_a_declared_class` (toda coluna de toda tabela não
  vazia da geração reproduzida em `REPRODUCTION_CLASSES[tabela]`; tabelas vazias
  listadas na mensagem); `test_reproduced_root_has_no_judged_dir_nor_attempts`.
- **O que fazer:** só o teste (o driver e o subcomando já existem). Se o mundo
  sintético não for `COMPLETED` com as 19 tabelas, parar (`[deviation]` com o
  ajuste da geração das grades).
- **Critério de aceite:** A3b (pré-checagem de `PYTHONHASHSEED`, I5), A6
  (completude sobre colunas gravadas), A4 (forma: nada de `judged/` no descartável).
- **Verificação (T1):** `pytest tests/integration/features/evaluation/test_reproduction_process_independence.py -q --no-cov`
- **Commit:** `test(evaluation): reprodução independente do hash seed do processo [8.2/task-07]`

---

### Task 08 — Andaime: checagem e gerador do registro, isolamento da evidência anterior

- **Arquivos a criar:**
  - `tests/equivalence/__init__.py` *(pacote)*
  - `tests/equivalence/prior_evidence.py`
  - `tests/equivalence/test_prior_evidence_registry_check.py`
  - `tests/architecture/test_prior_evidence_isolation.py`
- **Testes primeiro** (sempre ativos, `tmp_path` com Parquet sintético):
  `test_registered_files_matching_pass_and_return_paths`;
  `test_altered_byte_fails`; `test_missing_registered_file_fails`;
  `test_row_count_or_column_type_other_than_registry_fails` (footer);
  `test_unregistered_file_in_root_is_never_read` (o leitor recusa caminho fora do
  registro); `test_malformed_registry_fails` (sha não hex, `rows` não inteiro,
  `path` absoluto ou com `..`); `test_built_registry_round_trips_and_verifies`
  (o TOML do gerador relido por `load_registry` e conferido por
  `verify_registered_files`; colunas na ordem do footer);
  `test_builder_reads_footer_only` (o gerador não chama leitura de valores —
  `read_table`/`to_pylist` instrumentados); arquitetura:
  `test_no_src_module_reads_prior_evidence_or_imports_the_scaffold` (AST de
  `src/`: nenhum import de `tests`, nenhum literal com `data/analytics` ou
  `phase_b`), `test_isolation_detector_flags_violations` (o detector não é vácuo).
- **O que fazer:** `load_registry(path) -> PriorEvidenceRegistry`;
  `verify_registered_files(*, oracle_root, registry) -> Mapping[str, Path]`
  (sha256 por streaming, linhas e tipos pelo footer — `pyarrow.parquet.read_schema`
  / `read_metadata`, sem ler valor); `PriorEvidenceHashError(AssertionError)` com a
  lista de divergências; `REGISTRY_PATH` = `docs/reports/prior_evidence_registry.toml`;
  `build_registry(*, oracle_root, paths, definition_sources=()) -> str` (o TOML do
  §1, só footer + sha256) com `__main__`: `python -m tests.equivalence.prior_evidence
  build <oracle_root> <path>...` **imprime** o TOML (o redirecionamento para o
  arquivo é do runbook da E1; CB-7).
- **Critério de aceite:** A13 (função de checagem com unit sempre ativo), A14
  (parte AST), base do A1.
- **Verificação (T1):** `pytest tests/equivalence/test_prior_evidence_registry_check.py tests/architecture/test_prior_evidence_isolation.py -q --no-cov`
- **Commit:** `test(evaluation): checagem e gerador do registro da evidência anterior [8.2/task-08]`

---

### Task 09 — Contrato `src-no-tests` no `import-linter` (CB-1 do Checkpoint B)

- **Arquivos a modificar:**
  - `.importlinter` (contrato `forbidden` `src-no-tests`: `source_modules =
    financial_forecasting`, `forbidden_modules = tests`; comentário com LAYOUT §3
    e ADR 8.2.0003 item 2)
  - `tests/architecture/test_import_contracts.py` (`src-no-tests` em
    `_EXPECTED_CONTRACTS`; caso em `_REAL_VIOLATION_CASES` com módulo-sonda sob
    `src/` que importa `tests.equivalence` — cobre
    `test_every_expected_contract_has_a_real_violation_case` e
    `test_every_forbidden_module_has_a_real_violation_case`)
  - `docs/LAYOUT.md` (§2: `tests/equivalence/` — andaime interino da 8.2, ADR
    8.2.0003; §3: regra "nenhum módulo de `src/` importa `tests/`", espelhada no
    `.importlinter`)
- **Testes primeiro:** a entrada `src-no-tests` em `_EXPECTED_CONTRACTS` — o
  vermelho real é o `test_importlinter_declares_expected_contracts` até o contrato
  existir no `.importlinter` (o caso novo de `_REAL_VIOLATION_CASES` não dá um
  vermelho informativo antes: `limit_to_contracts` com nome inexistente já sai com
  erro); com o contrato, o caso real prova que a sonda que importa
  `tests.equivalence` reprova o `lint-imports` (verde do teste = contrato não vácuo).
- **O que fazer:** Task própria porque muda configuração de gate (RUNBOOK §Gates em
  camadas) e um escopo que não é o do `evaluation`; 3 arquivos.
- **Critério de aceite:** A14 (parte `import-linter`).
- **Verificação (T1):** `pytest tests/architecture/test_import_contracts.py -q --no-cov` e `uv run --no-sync lint-imports`
- **Se o `import-linter` recusar o pacote externo `tests` como `forbidden_modules`:**
  ficar com o teste AST da Task 08, `[deviation]` com a mensagem literal do
  `lint-imports`, Task sem o contrato (LAYOUT §3 continua com a regra, citando o
  teste AST como fitness function).
- **Commit:** `test(architecture): contrato src-no-tests no import-linter e no LAYOUT [8.2/task-09]`

---

### Task 10 — Andaime: conjunto de comparação, interseção, A1, A2 e sentido (regras puras)

- **Arquivos a criar:**
  - `tests/equivalence/comparison_set.py`
  - `tests/equivalence/alignment.py`
  - `tests/equivalence/comparisons.py`
  - `tests/equivalence/test_scaffold_comparisons.py`
- **Testes primeiro** (sempre ativos, linhas sintéticas em memória):
  `test_prior_point_is_the_latest_test_window` (D7); `test_intersection_by_horizon_and_timestamp_ignores_fold`;
  `test_empty_intersection_is_recorded_not_compared`;
  `test_a1_passes_at_half_ulp_and_fails_one_ulp_beyond` (2⁻⁵³·|y_ant|; `y_ant = 0` ⇒
  igualdade exata); `test_a1_reports_count_out_and_max`;
  `test_a2_tolerance_is_max_of_r2_and_storage_precision` (u_q por grandeza do D12 e:
  pinball = a própria pinball, MPIW = média de |largura|, PICP = 1; 2⁻⁵³·|m_ant|
  para `double`); `test_a2_not_realizable_when_sample_size_cannot_be_rebuilt`
  (`n_samples`/`n_obs` ≠ pontos lidos);
  `test_seed_aggregation_mean_of_losses_and_mean_of_coverages` (D12 d);
  `test_dm_sign_normalized_to_candidate_minus_baseline` (as duas convenções do D8);
  `test_dm_rejection_uses_unadjusted_p_and_side_alpha`;
  `test_side_of_nominal_below_inside_above_wilson_band`;
  `test_sense_cell_equal_or_divergent` (sinal ± e zero exato tratado como sinal
  próprio).
- **O que fazer:** `comparison_set.py` com as constantes do §1 (arquivos, colunas,
  filtros, níveis {0,1; 0,5; 0,9}, par 80 %, variantes por coluna, p e α do D8,
  regra D7, `MODEL_LABEL_COLUMN` e `COMMON_BASELINES: tuple[...] = ()` —
  preenchidos só na E1 — e as constantes do lado novo lidas do código, com o
  caminho na docstring); `alignment.py` (seleção D7, T∩ por horizonte, agregação
  de seeds); `comparisons.py` (A1, A2 com tolerância, células de sentido,
  `RawStatus` = `within_tolerance | out_of_tolerance | not_realizable |
  empty_intersection | same_sense | divergent_sense`). As métricas do lado novo e
  de m_A usam os serviços de domínio existentes (`pinball_score`,
  `coverage_series`, `wilson_band`); nenhuma métrica nova (concept §12 item vi).
- **Critério de aceite:** A9, A10, A11 (regras), D7, D8, D12, D13.
- **Verificação (T1):** `pytest tests/equivalence/test_scaffold_comparisons.py -q --no-cov`
- **Commit:** `test(evaluation): regras do andaime da equivalência sobre dado sintético [8.2/task-10]`

---

### Task 11 — Andaime: leitores, tabela renderizada e teste opt-in

- **Arquivos a criar:**
  - `tests/equivalence/readers.py`
  - `tests/equivalence/audit_table.py`
  - `tests/equivalence/test_audit_table_render.py`
  - `tests/equivalence/test_official_vs_prior_evidence.py`
- **Testes primeiro:** sempre ativos — `test_render_then_parse_round_trip`;
  `test_parse_refuses_missing_markers_or_malformed_row`;
  `test_declared_vs_parsed_mismatch_shows_the_diff`;
  `test_prior_reader_reads_only_registered_columns_and_filters` (Parquet sintético
  em `tmp_path` com registro sintético); opt-in (sem as variáveis):
  `test_official_vs_prior_evidence` → **skipped** com o motivo citando
  `docs/reports/prior_evidence_registry.toml` (visto com `-rs`).
- **O que fazer:** `readers.py` — anterior: só depois do
  `verify_registered_files`, só as colunas do `comparison_set`; oficial: cópia
  julgada por `ParquetGoldStore(<official>).read_judged_generation`, predições pelo
  leitor silver real do `RefreshGold` (`ParquetAnalyticsRepository`), realizado
  pelo `ReadTrainingGrid` real (§1), conferindo o `dataset_fingerprint` contra o
  manifesto da cópia. `audit_table.py` — `compute(oracle_root, official_root) ->
  tuple[Row, ...]` (cada comparação: id, horizonte, grandeza, valores, tolerância,
  `RawStatus`), `render(rows) -> str` (tabelas markdown de A9, A10, A11 entre
  marcadores `<!-- BEGIN: declared-classification -->` / `<!-- END: … -->`),
  `parse(markdown) -> tuple[Declared, ...]`, e `__main__` que **imprime** no
  stdout (nunca grava arquivo). `test_official_vs_prior_evidence.py` — sem
  `EQUIVALENCE_ORACLE_ROOT`/`EQUIVALENCE_OFFICIAL_ROOT` (ou caminho inexistente)
  → `pytest.skip(<motivo + caminho do registro>)`; com eles →
  `verify_registered_files` (falha, nunca pula), `compute`, afirma
  `RawStatus` recomputado = `DECLARED` (constante do módulo, **vazia** até a E5:
  com o oráculo e `DECLARED` vazio o teste falha) e `DECLARED` =
  `parse(docs/reports/equivalence_audit.md)`; nunca escreve registro nem
  relatório.
- **Critério de aceite:** A13 (skip, falha por hash, igualdade das tabelas),
  A12 (forma da tabela).
- **Verificação (T1):** `pytest tests/equivalence/ -rs -q --no-cov` (os unit
  passam; o opt-in aparece `SKIPPED` com o motivo)
- **Antes do ponto 1 — Checkpoint C final e auditoria de testes.** Revisão do
  bloco 08–11 por subagente e a **auditoria de testes** (PROMPT-stage §AUDITORIA
  DE TESTES; subagente que não escreveu os testes) com **mutação real** —
  igualdade por bits no `compare_reproduction` (trocar por `==` de float),
  conjunção do `bit_identical` (tirar o `expected_result_digest`), conferência do
  `CONTENTS.sha256` no `read_judged_generation` (pular o `find`), o
  `audit-reproduction` ignorando o `scorecard.json` (passar o scorecard da cópia
  nos dois lados — CB-3), recusa `data/cohorts` e ordem foto → refresh no driver,
  `env-equal` ignorando chave a mais, limiar de A1 (2⁻⁵² no lugar de 2⁻⁵³) —,
  editando, rodando o T1 dos arquivos afetados e revertendo, saída colada em §7.
  Achado → `test(<escopo>): cobrir <X> [8.2/task-NN-extra]` **antes** do ponto 1
  (o driver da E3 é o do commit verde).
- **Gate T3 — ponto 1 do plano:** `make check` (comando literal do §1). Anotar o
  sha do commit verde como `GATE1` (entra no `etapa-82.env` da E0).
- **Commit:** `test(evaluation): teste opt-in da equivalência e tabela do relatório [8.2/task-11]`

---

### Etapas reais E1–E5 — ordem fixa do D10

Não são Tasks numeradas: produzem commits de runbook (registro, §7, relatórios,
tabela declarada). Rodam **depois** do ponto 1 verde, com a árvore limpa, **na
ordem E1 → E2 → E3 → E4 → E5**; nenhuma Etapa começa sem o commit da anterior
(quando ela tem commit). Toda medição vai para §7 (`[measurement]`;
`[finding]` quando a tabela "Se falhar" manda parar).

**Sessão que executa** (modelo da Etapa R da 8.1). Cada chamada de shell é um
processo novo (variáveis não persistem) e tem teto de 10 min:

- (i) todo valor calculado vai para `$SCRATCH/etapa-82.env`, e **todo** bloco
  começa com `set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1`;
- (ii) **toda asserção que manda parar** tem a forma
  `test … || { echo FAIL_<NOME>; exit 1; }; echo <NOME>` (com `set -e`, uma falha à
  esquerda de `&&` **não** aborta o bloco — GB-1); todo comando cujo exit é
  evidência usa `cmd > out && rc=0 || rc=$?; echo "exit $rc"` (com `set -e`,
  `echo "exit $?"` depois de um comando que falhou nunca roda — GB-6) e a
  conferência do `rc` é a linha seguinte;
- (iii) a reprodução (E3) roda num container **destacado** `ff82-repro`, esperado
  por `docker wait` em segundo plano (`run_in_background`, notificação ao sair),
  com `docker ps` e `docker logs --tail`; o estado (`ExitCode`, `OOMKilled`) é
  gravado **antes** do `docker rm` (GB-2);
- (iv) o container roda pelo **id** da imagem, nunca pela tag `:dev`; prefixar todo
  `docker run` com `MSYS_NO_PATHCONV=1`;
- (v) as evidências saem de código versionado e testado
  (`scripts/reproduction_evidence.py`, `tests/equivalence/prior_evidence.py`, Tasks
  06 e 08 — CB-7), executado a partir da worktree limpa no commit registrado;
- (vi) **venv congelado (GB-3):** o volume `financial-forecasting_app-venv` é
  compartilhado por todas as worktrees (há outra em voo). Da E2 ao fim da E3,
  **proibido** em qualquer worktree: `uv sync`, `make setup`, `make install`,
  `make check`, `make test` (e todo alvo do Makefile que chama `uv run` puro —
  `Makefile` l.146–221 —, que sincroniza o volume), qualquer `uv run` **sem**
  `--no-sync`, rebuild de imagem ou `docker compose up`; todo comando das Etapas
  usa `uv run --no-sync`. A sessão declara essa lista ao coordenador antes da E2,
  e o sha256 do `uv pip freeze` da E2 é exigido igual depois da E3.

**E0 — Variáveis (host, Git Bash; uma vez, depois do ponto 1).**
```bash
set -eu
SCRATCH=<scratchpad da sessão, caminho absoluto literal, fora do repo>
STAMP=$(date -u +%Y%m%d-%H%M%S)
cat > "$SCRATCH/etapa-82.env" <<EOF
SCRATCH=$SCRATCH
STAMP=$STAMP
GATE1=<sha do commit verde do ponto 1>
WT=feat-232-8-2-equivalence-audit
WTH=/c/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/feat-232-8-2-equivalence-audit
WTD=C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/feat-232-8-2-equivalence-audit
MAINH=/c/Users/Marcelo/Documents/Code/financial-forecasting
MAIND=C:/Users/Marcelo/Documents/Code/financial-forecasting
REPRO=repro-060537fc
REPROH=/c/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/repro-060537fc
REPROD=C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/repro-060537fc
DISPH=/c/Users/Marcelo/Documents/Code/financial-forecasting/data/reproductions/aapl-r3-$STAMP
DISPD=C:/Users/Marcelo/Documents/Code/financial-forecasting/data/reproductions/aapl-r3-$STAMP
JUDGED_COMMIT=060537fc7069b38a318bb5cf839d84b7767b1b4f
BASE=64b8a17dfcec6694b03d14b2ea2b39da9e624291
IMAGE_ID=sha256:b69a7620e7bd8449369bde2f46e903c5f46c25e9efb3597f452af3272e0a8f45
REF=aapl_confirmatory-r3-00fd83d9cd39
LIVE=/c/Users/Marcelo/Documents/Code/financial-forecasting/data/cohorts/aapl
P=/c/Users/Marcelo/Documents/Code/financial-forecasting/data/cohorts/aapl/gold/asset=AAPL/parent_sweep_id=aapl_confirmatory-r0-665f45d9169a
BK=/c/Users/Marcelo/Documents/Code/financial-forecasting/data/backups/aapl-pre-8.1-20261023-084758
EOF
cat >> "$SCRATCH/etapa-82.env" <<'EOF'
RES="--cpus 6 --memory 8g --memory-swap 8g"
PRE="git config --global --add safe.directory '*'"
RMOUNTS="-v $REPROD:/app -v $MAIND/.git:/main.git:ro -v $MAIND/artifacts:/app/artifacts:ro -v financial-forecasting_app-venv:/app/.venv -v $DISPD:/repro -v $WTD/scripts/reproduce_judged_generation.py:/driver/reproduce_judged_generation.py:ro"
RENVS="-w /app -e GIT_DIR=/main.git/worktrees/$REPRO -e GIT_WORK_TREE=/app -e GIT_OPTIONAL_LOCKS=0 -e IMAGE_ID=$IMAGE_ID -e MLFLOW_TRACKING_URI=sqlite:////tmp/mlruns.db"
DRIVER="uv run --no-sync python /driver/reproduce_judged_generation.py --data-root /repro --cohort config/cohorts/aapl_confirmatory.toml --preregistration aapl_confirmatory --revision 3 --preregistration-ref $REF"
HMOUNTS="-v $WTD:/app -v $MAIND/.git:/main.git:ro -v financial-forecasting_app-venv:/app/.venv"
HENVS="-w /app -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app -e GIT_OPTIONAL_LOCKS=0"
EOF
```
`RMOUNTS`/`RENVS` repetem os da Etapa R da 8.1 (`.git` e `artifacts/` só leitura,
`MLFLOW_TRACKING_URI`, `GIT_OPTIONAL_LOCKS`, `IMAGE_ID`), trocando a partição viva
pelo descartável (`/repro`) e acrescentando o driver em `/driver/` (fora dos
caminhos do probe). A partição viva **não** é montada no container da reprodução.

**Bloco "HEAD íntegro" (GB-4)** — roda no início da E1, da E2 e da E3 (o driver e
os scripts montados são a cópia de trabalho; ela tem de ser o blob commitado e
o mesmo do `GATE1`):
```bash
set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
test -z "$(git -C "$WTH" status --porcelain)" || { echo FAIL_WT_DIRTY; exit 1; }; echo WT_CLEAN
for f in scripts/reproduce_judged_generation.py scripts/reproduction_evidence.py tests/equivalence/prior_evidence.py; do
  test "$(git -C "$WTH" rev-parse "HEAD:$f")" = "$(git -C "$WTH" rev-parse "$GATE1:$f")" || { echo "FAIL_CHANGED_SINCE_GATE1 $f"; exit 1; }
  test "$(git -C "$WTH" hash-object "$f")" = "$(git -C "$WTH" rev-parse "HEAD:$f")" || { echo "FAIL_WORKING_COPY $f"; exit 1; }
  echo "BLOB $f $(git -C "$WTH" rev-parse "HEAD:$f")"
done
```
As linhas `BLOB` vão para o §7 e para o relatório de reprodução.

**E1 — Registro de hashes da evidência anterior (A1; D5, D10 passo 1, D11, D12 a).**
Antes de qualquer valor. Só footer, contagens e rótulos de definição.

1. *Rótulo de modelo do `gold_oos_consolidated`* (metadado): listar, com o
   container da imagem e `data/analytics` `:ro`, os valores **distintos** de
   `model_version_x` e `model_version_y` nas linhas `parent_sweep_id =
   phase_b_confirmatorio_20260524`, `split = test` (só essas duas colunas e as de
   filtro; nenhuma coluna de valor); fixar em `comparison_set.MODEL_LABEL_COLUMN`
   a coluna que traz o candidato `BTSF` e os três baselines de D-M2.
2. *Baselines comuns (D12 a).* Lado novo: definição dos `baseline_zero_return`,
   `baseline_historical_mean` e `baseline_historical_quantiles` no código do HEAD
   (`features/modeling/…`, arquivo e linhas citados). Lado anterior, fontes
   aceitas, nesta ordem: (a) código do anterior no commit que o `dim_run` do
   cohort registra (`git_commit`, `pipeline_version` — rótulos; `git cat-file -e
   <commit>` nos repositórios locais em `C:/Users/Marcelo/Documents/Code/*`); se
   achado, a definição (estimador, janela, parâmetros, regra de dispersão dos
   quantis) é lida desse código e registrada em `[[definition_source]]`
   (`repo`, `commit`, `path`, `blob`); (b) payload de definição em arquivo de
   `data/analytics/` (ex.: colunas `*_json` de `silver/dim_run` ou
   `silver/fact_config` das linhas dos baselines, se existirem) — o arquivo entra
   no registro com as colunas lidas; (c) nenhuma → **zero comuns**. Nome igual
   não basta; `config_signature` (hash) não é definição. Comum = as quatro partes
   da definição declaradas equivalentes nos dois lados. Resultado em
   `comparison_set.COMMON_BASELINES` (pares `prior_label`/`new_label` + fonte) e
   numa entrada `[decision:C] E1 — baselines comuns` em §7 (com as fontes
   olhadas e o que cada uma deu).
3. *Registro* — pelo gerador versionado (Task 08):
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   MSYS_NO_PATHCONV=1 docker run --rm $RES $HMOUNTS -v $MAIND/data/analytics:/oracle:ro $HENVS "$IMAGE_ID" sh -c "$PRE; uv run --no-sync python -m tests.equivalence.prior_evidence build /oracle <os 5 caminhos do §1> <os de 2(b), se houver>" > "$SCRATCH/registry.toml" && rc=0 || rc=$?
   echo "exit $rc"; test "$rc" = 0 || { echo FAIL_REGISTRY_BUILD; exit 1; }
   cp "$SCRATCH/registry.toml" "$WTH/docs/reports/prior_evidence_registry.toml"
   for sha in <os 5 sha256 de D-M1 dos arquivos do §1>; do grep -q "\"$sha\"" "$SCRATCH/registry.toml" || { echo "FAIL_NOT_DM1 $sha"; exit 1; }; done; echo REGISTRY_EQUALS_DM1
   MSYS_NO_PATHCONV=1 docker run --rm $RES $HMOUNTS -v $MAIND/data/analytics:/oracle:ro $HENVS "$IMAGE_ID" sh -c "$PRE; uv run --no-sync python -c \"from pathlib import Path; from tests.equivalence.prior_evidence import REGISTRY_PATH, load_registry, verify_registered_files as v; print('REGISTRY_OK', len(v(oracle_root=Path('/oracle'), registry=load_registry(REGISTRY_PATH))))\"" && rc=0 || rc=$?
   echo "exit $rc"; test "$rc" = 0 || { echo FAIL_REGISTRY_CHECK; exit 1; }
   ```
4. *T1 antes do commit (GB-8)* — a E1 muda código que a E4 executa
   (`comparison_set.py`): `pytest tests/equivalence/ -rs -q --no-cov`, `ruff
   format --check`/`ruff check` de `tests/equivalence/comparison_set.py` e `mypy`
   (comando T1 do §1); verde antes do commit. Sem `make check` novo (o ponto 2
   cobre).
5. *Commit próprio* (registro + `comparison_set.py` + §7):
   `docs(evaluation): registro de hashes da evidência anterior antes da leitura [8.2/--]`.
   Anotar `REGISTRY_COMMIT` no `etapa-82.env`. O `git log -p origin/develop..$REGISTRY_COMMIT`
   não traz valor do anterior (só schema, contagens, rótulos e os sha de D-M1).

**E2 — Pré-voo da reprodução (A2, A3b, A4, A7; sem refresh).** Começa pelo bloco
"HEAD íntegro" e pela declaração do venv congelado (vi).

1. *Árvore de `060537fc`* — **worktree destacada** em diretório temporário, sem
   branch nova:
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   test ! -e "$REPROH" || { echo FAIL_REPRO_EXISTS; exit 1; }
   git -C "$WTH" worktree add --detach "$REPROH" "$JUDGED_COMMIT"
   test "$(git -C "$REPROH" rev-parse HEAD)" = "$JUDGED_COMMIT" || { echo FAIL_TREE_NOT_JUDGED; exit 1; }; echo TREE_AT_JUDGED
   cp "$MAINH/.env" "$REPROH/.env"
   git -C "$REPROH" check-ignore -q .env || { echo FAIL_ENV_NOT_IGNORED; exit 1; }; echo ENV_IGNORED
   printf 'DOTENV_SHA=%s\n' "$(sha256sum "$REPROH/.env" | cut -d' ' -f1)" >> "$SCRATCH/etapa-82.env"
   test -z "$(git -C "$REPROH" status --porcelain)" || { echo FAIL_TREE_DIRTY; exit 1; }; echo TREE_CLEAN
   ```
   **Por que worktree e não `git archive`:** o probe exige um repositório git —
   `git rev-parse HEAD:src` (`code.src`), `git status --porcelain` (sujeira) e
   `rev-parse --show-toplevel` = `repo_root` (`/app`, com `GIT_DIR`/`GIT_WORK_TREE`
   explícitos, porque o `.git` de uma worktree aponta para caminho do host); a
   árvore de um `git archive` não tem `.git` e a foto falharia (`RuntimeError`),
   tornando I4 impossível. É também como a 8.1 rodou (worktree com o `.git` do
   checkout principal em `/main.git`). O `.env` é copiado porque a worktree da 8.1
   o tinha (`worktree-new.py` copia o `.env`); nenhuma chave dele entra no cálculo
   (`DATA_ROOT` é sobrescrito pelo `Settings(data_root=...)` explícito), e o sha256
   fica no relatório.
2. *Imagem, Docker e lock:*
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   test "$(docker image inspect --format '{{.Id}}' "$IMAGE_ID")" = "$IMAGE_ID" || { echo FAIL_IMAGE; exit 1; }; echo SAME_IMAGE
   test -z "$(docker ps --filter name=ff82 -q)" || { echo FAIL_CONTAINER_ALIVE; exit 1; }; echo NO_FF82
   printf 'UV_LOCK_SAME_AS_HEAD=%s\n' "$(git -C "$WTH" diff --quiet "$JUDGED_COMMIT" HEAD -- uv.lock && echo yes || echo no)" >> "$SCRATCH/etapa-82.env"
   ```
   `UV_LOCK_SAME_AS_HEAD` é registro (GB-3): `no` não para nada sozinho (o
   `code.uv_lock` comparado é o de `060537fc`), mas diz se uma sincronização do
   volume pelo HEAD mudaria libs.
3. *Backup de entrada e restauração no descartável:*
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   test "$(sha256sum "$BK.sha256sum" | cut -d' ' -f1)" = "$(grep '^input_backup_sha256' "$WTH/config/preregistration/aapl_confirmatory-r3.judged.toml" | cut -d'"' -f2)" || { echo FAIL_LISTING_NOT_REGISTERED; exit 1; }; echo LISTING_IS_REGISTERED
   (cd "$BK" && sha256sum -c --quiet "$BK.sha256sum") || { echo FAIL_BACKUP; exit 1; }; echo BACKUP_OK
   test ! -e "$DISPH" || { echo FAIL_DISPOSABLE_EXISTS; exit 1; }
   mkdir -p "$DISPH"; cp -a "$BK/." "$DISPH/"
   (cd "$DISPH" && sha256sum -c --quiet "$BK.sha256sum") || { echo FAIL_RESTORE; exit 1; }; echo RESTORE_OK
   test -z "$(ls -A "$DISPH" | grep -vxE 'bronze|inference|processed|raw|silver')" || { echo FAIL_DISPOSABLE_LAYOUT; exit 1; }; echo DISPOSABLE_INPUT_ONLY
   ```
4. *Partição viva antes (I1; GB-5 — a partição inteira, não só três arquivos):*
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   (cd "$P/judged/$REF" && sha256sum -c --quiet CONTENTS.sha256) || { echo FAIL_JUDGED_COPY; exit 1; }; echo JUDGED_COPY_OK
   test "$(sha256sum "$P/judged/$REF/CONTENTS.sha256" | cut -d' ' -f1)" = 96c0541301885ed1c6688a517176f63a54e872a3e18ee82fbb5c23121747e539 || { echo FAIL_DIGEST; exit 1; }; echo DIGEST_OK
   (cd "$LIVE" && find . -type f -printf '%P\0' | LC_ALL=C sort -z | xargs -0 sha256sum) > "$SCRATCH/live-before.sha256sum"
   wc -l < "$SCRATCH/live-before.sha256sum"
   grep -E ' gold/.*/(current/MANIFEST.json|judged/ATTEMPTS.jsonl)$' "$SCRATCH/live-before.sha256sum"   # 56d3ee1c…, 320def2b…
   ```
5. *Ambiente no container da reprodução:*
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   MSYS_NO_PATHCONV=1 docker run --rm $RES $RMOUNTS $RENVS "$IMAGE_ID" sh -c "$PRE; git rev-parse HEAD; git status --porcelain | wc -l; cat /sys/fs/cgroup/cpu.max; uname -r" > "$SCRATCH/env-preflight.txt" && rc=0 || rc=$?
   echo "exit $rc"; test "$rc" = 0 || { echo FAIL_ENV_PROBE; exit 1; }; cat "$SCRATCH/env-preflight.txt"
   test "$(wc -l < "$SCRATCH/env-preflight.txt")" = 4 || { echo FAIL_PREFLIGHT_SHAPE; exit 1; }
   test "$(sed -n 1p "$SCRATCH/env-preflight.txt")" = "$JUDGED_COMMIT" || { echo FAIL_CONTAINER_HEAD; exit 1; }; echo CONTAINER_AT_JUDGED
   test "$(sed -n 2p "$SCRATCH/env-preflight.txt" | tr -d " ")" = 0 || { echo FAIL_CONTAINER_DIRTY; exit 1; }; echo CONTAINER_TREE_CLEAN
   test "$(sed -n 3p "$SCRATCH/env-preflight.txt")" = "600000 100000" || { echo FAIL_CPU_MAX; exit 1; }; echo CPU_MAX_6
   test "$(sed -n 4p "$SCRATCH/env-preflight.txt")" = 6.18.54.1-microsoft-standard-WSL2 || { echo FAIL_KERNEL; exit 1; }; echo SAME_KERNEL
   MSYS_NO_PATHCONV=1 docker run --rm $RES $RMOUNTS $RENVS "$IMAGE_ID" sh -c "uv pip freeze --python /app/.venv/bin/python" > "$SCRATCH/freeze-e2.txt" && rc=0 || rc=$?
   echo "exit $rc"; test "$rc" = 0 || { echo FAIL_FREEZE; exit 1; }
   printf 'FREEZE_E2=%s\n' "$(sha256sum "$SCRATCH/freeze-e2.txt" | cut -d' ' -f1)" >> "$SCRATCH/etapa-82.env"
   ```
   (Quatro linhas fixas: HEAD do container, número de linhas do `git status
   --porcelain`, `cpu.max`, kernel.)
   O sha256 do freeze é a foto do venv; a 8.1 não registrou o seu, então ele não
   compara com a 8.1 — compara E2 × E3 (`FREEZE_SAME`).
6. *Driver `--check` em `060537fc`* (wiring + foto, sem refresh; prova também que o
   driver só usa nomes que existem em `060537fc`):
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   MSYS_NO_PATHCONV=1 docker run --rm $RES $RMOUNTS $RENVS "$IMAGE_ID" sh -c "$PRE; $DRIVER --check" > "$SCRATCH/check.json" 2> "$SCRATCH/check.err" && rc=0 || rc=$?
   echo "exit $rc"; test "$rc" = 0 || { echo FAIL_CHECK; tail -20 "$SCRATCH/check.err"; exit 1; }
   test ! -e "$DISPH/gold" && test ! -e "$DISPH/reproduction" || { echo FAIL_CHECK_WROTE; exit 1; }; echo CHECK_WROTE_NOTHING
   python "$WTH/scripts/reproduction_evidence.py" env-equal "$P/judged/ATTEMPTS.jsonl" "$SCRATCH/check.json" && rc=0 || rc=$?
   echo "exit $rc"; test "$rc" = 0 || { echo FAIL_ENV_EQUAL; exit 1; }   # a linha anterior imprimiu ENV_EQUAL
   ```
7. *R-BIT-COMMIT (A7, D1)* — no container 3.12, pelo script versionado:
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   MSYS_NO_PATHCONV=1 docker run --rm $HMOUNTS $HENVS "$IMAGE_ID" sh -c "$PRE; /app/.venv/bin/python --version; /app/.venv/bin/python scripts/reproduction_evidence.py ast-equal $JUDGED_COMMIT $BASE" > "$SCRATCH/ast-equal.txt" && rc=0 || rc=$?
   echo "exit $rc"; cat "$SCRATCH/ast-equal.txt"
   git -C "$WTH" diff --name-status "$BASE"..HEAD -- src/ | tee "$SCRATCH/src-8.2.txt"
   ```
   Esperado: `Python 3.12.13`, 15 arquivos `AST_EQUAL`, `files 15 ast_diff 0`,
   exit 0 (`AST_DIFF` → linha do "Se falhar", não parada da reprodução). A lista
   `src-8.2.txt` é a dos acréscimos da 8.2 (Tasks 01–05), cada um justificado no
   relatório (CB-2): `reproduction_comparison.py` (dto e use case),
   `audit_reproduction.py`, `judged_generation_store.py`, `evaluation_commands.py`,
   `cli.py` e `composition_root.py` — **fora** do caminho refresh/scorecard (só
   comparação, leitura da cópia e wiring do subcomando; o `wire_dependencies`
   não muda); `parquet_gold_store.py` — **no caminho de leitura do scorecard**
   (`BuildConfirmatoryScorecard(reader=gold_store)`): a Task 03 extrai
   `_read_generation_dir` da `read_generation` sem mudar comportamento, provado pela
   suíte de contrato do `GoldGenerationReader` (verde no ponto 1) e, de qualquer
   modo, fora do claim, que é o da execução em `060537fc`. A redação do A7 do
   concept ("cada um justificado como fora do caminho de refresh/scorecard") não
   cabe para esse arquivo: registrar `[deviation]` de redação em §7 na E2, com
   esta justificativa.
8. *Pré-checagem de processo (A3b):* citar o T1 verde da Task 07 e o ponto 1
   (`test_reproduction_process_independence.py`).
9. **Commit** da evidência do pré-voo em §7 (`[measurement] E2`, saídas literais
   dos itens 1–8, linhas `BLOB`, `DOTENV_SHA`, `FREEZE_E2`, `UV_LOCK_SAME_AS_HEAD`, e
   o `[deviation]` de redação do A7): `docs(evaluation): pré-voo da reprodução em 060537fc [8.2/--]`.

**E3 — Reprodução real e auditoria (A3, A4, A7, A8).** Começa pelo bloco "HEAD
íntegro"; o venv segue congelado (vi).

1. *Corrida destacada* (~15 min: o refresh da 8.1 levou 13,9 min):
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   test -z "$(docker ps -a --filter name=ff82-repro -q)" || { echo FAIL_CONTAINER_EXISTS; exit 1; }
   test ! -e "$DISPH/gold" && test ! -e "$DISPH/reproduction" || { echo FAIL_DISPOSABLE_USED; exit 1; }
   MSYS_NO_PATHCONV=1 docker run -d --name ff82-repro $RES $RMOUNTS $RENVS "$IMAGE_ID" sh -c "$PRE; $DRIVER"
   ```
   Em segundo plano (`run_in_background`): `docker wait ff82-repro > "$SCRATCH/repro.exit"`.
   Enquanto roda: `docker ps --filter name=ff82`, `docker logs --tail 5 ff82-repro`.
   Ao sair:
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   docker inspect --format '{{.State.ExitCode}} {{.State.OOMKilled}}' ff82-repro > "$SCRATCH/repro.state"
   docker logs ff82-repro > "$SCRATCH/repro.out" 2> "$SCRATCH/repro.err"
   cat "$SCRATCH/repro.exit" "$SCRATCH/repro.state"
   test "$(cat "$SCRATCH/repro.state")" = "0 false" || { echo FAIL_REPRO_EXIT; tail -30 "$SCRATCH/repro.err"; exit 1; }
   docker rm ff82-repro
   grep "^reproduction " "$SCRATCH/repro.out"   # refresh COMPLETED tables 19; scorecard sha256 <hex>
   grep -q "^reproduction $REF: refresh COMPLETED tables 19$" "$SCRATCH/repro.out" || { echo FAIL_REFRESH_STATUS; exit 1; }; echo REFRESH_COMPLETED
   test -f "$DISPH/reproduction/environment.json" && test -f "$DISPH/reproduction/scorecard.json" || { echo FAIL_REPRO_FILES; exit 1; }; echo REPRO_FILES
   python "$WTH/scripts/reproduction_evidence.py" env-equal "$P/judged/ATTEMPTS.jsonl" "$DISPH/reproduction/environment.json" || { echo FAIL_ENV_EQUAL_RUN; exit 1; }
   cmp -s "$SCRATCH/check.json" "$DISPH/reproduction/environment.json" || { echo FAIL_SNAPSHOT_CHANGED; exit 1; }; echo SNAPSHOT_SAME_AS_CHECK
   test -z "$(find "$DISPH" \( -name judged -o -name ATTEMPTS.jsonl \) -print)" || { echo FAIL_JUDGMENT_IN_DISPOSABLE; exit 1; }; echo NO_JUDGMENT_IN_DISPOSABLE
   ```
   Tempos por etapa: linhas `_timed` do `repro.err`.
2. *Venv igual ao da E2 (GB-3):*
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   MSYS_NO_PATHCONV=1 docker run --rm $RES $RMOUNTS $RENVS "$IMAGE_ID" sh -c "uv pip freeze --python /app/.venv/bin/python" > "$SCRATCH/freeze-e3.txt" && rc=0 || rc=$?
   echo "exit $rc"; test "$rc" = 0 || { echo FAIL_FREEZE; exit 1; }
   test "$(sha256sum "$SCRATCH/freeze-e3.txt" | cut -d' ' -f1)" = "$FREEZE_E2" || { echo FAIL_FREEZE_CHANGED; exit 1; }; echo FREEZE_SAME
   ```
3. *Auditoria pelo HEAD* (só leitura nas duas raízes):
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   MSYS_NO_PATHCONV=1 docker run --rm $RES $HMOUNTS -v $MAIND/data/cohorts/aapl:/judged:ro -v $DISPD:/reproduced:ro $HENVS "$IMAGE_ID" sh -c "$PRE; uv run --no-sync python -m financial_forecasting.cli audit-reproduction --judged-data-root /judged --reproduced-data-root /reproduced --preregistration aapl_confirmatory --revision 3 --preregistration-ref $REF" > "$SCRATCH/audit.out" 2> "$SCRATCH/audit.err" && rc=0 || rc=$?
   echo "exit $rc"; head -2 "$SCRATCH/audit.out"
   test "$rc" = 0 || { echo FAIL_NOT_BIT_IDENTICAL; exit 1; }; echo BIT_IDENTICAL
   ```
   Esperado: `bit_identical true`; os três `result_digest` = `7c7940d4…`.
4. *Partição viva depois (I1, A4):*
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   (cd "$LIVE" && sha256sum -c --quiet "$SCRATCH/live-before.sha256sum") || { echo FAIL_LIVE_CHANGED; exit 1; }
   test "$(cd "$LIVE" && find . -type f | wc -l)" = "$(wc -l < "$SCRATCH/live-before.sha256sum")" || { echo FAIL_LIVE_NEW_FILE; exit 1; }; echo LIVE_INTACT
   ```
5. *Relatório* `docs/reports/reproduction_audit.md`: o claim — (a) afirmado
   (reprodução bit a bit no commit e no ambiente registrados, a partir dos dados
   persistidos, sem re-treino), (b) citado da 7.1 (predições a partir dos
   checkpoints), (c) **não executado** (um único ambiente, D4) —; identidade
   (`silver_content.digest`, `dataset_fingerprint`, ref, partição); os três
   `result_digest`; a tabela por classe e por tabela do `audit.out` (contagens,
   diferentes, max |Δ| também quando zero); o scorecard sem proveniência; o
   ambiente (imagem, `cpu.max`, kernel, `FREEZE_E2` = E3, `DOTENV_SHA`, `ENV_EQUAL`
   chave a chave); os blobs do driver e dos scripts de evidência (linhas `BLOB`);
   o R-BIT-COMMIT (lista `060537fc..64b8a17d` com `AST_EQUAL` e a lista
   `64b8a17d..HEAD` justificada como na E2 item 7) com a declaração de que o claim
   é o da execução em `060537fc`; a partição viva antes/depois; os comandos.
   Entrada `[measurement] E3` em §7. Commit
   `docs(evaluation): relatório da reprodução bit a bit da geração julgada [8.2/--]`.
6. *Limpeza da árvore temporária:* `git -C "$WTH" worktree remove "$REPROH"` (com
   arquivos ignorados — `.env`, `artifacts/`, `__pycache__` —: `rm -rf "$REPROH"` e
   `git -C "$WTH" worktree prune`); o `data_root` descartável fica em
   `data/reproductions/` (git-ignorado) até o merge, como evidência. Fim do venv
   congelado (avisar o coordenador).

**E4 — Leitura de valores da evidência anterior e comparações (A9–A11; D10 passo 3).**

Só depois do commit do E3 (`git log` mostra registro → pré-voo → relatório de
reprodução).

1. *Tabela recomputada:*
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   test -z "$(git -C "$WTH" status --porcelain)" || { echo FAIL_WT_DIRTY; exit 1; }
   git -C "$WTH" diff --quiet "$GATE1" HEAD -- tests/equivalence ':!tests/equivalence/comparison_set.py' || { echo FAIL_SCAFFOLD_CHANGED; exit 1; }; echo SCAFFOLD_AS_GATE1
   REG_SHA=$(sha256sum "$WTH/docs/reports/prior_evidence_registry.toml" | cut -d' ' -f1)
   MSYS_NO_PATHCONV=1 docker run --rm $RES $HMOUNTS -v $MAIND/data/analytics:/oracle:ro -v $MAIND/data/cohorts/aapl:/official:ro $HENVS -e EQUIVALENCE_ORACLE_ROOT=/oracle -e EQUIVALENCE_OFFICIAL_ROOT=/official "$IMAGE_ID" sh -c "$PRE; uv run --no-sync python -m tests.equivalence.audit_table" > "$SCRATCH/equivalence.md" 2> "$SCRATCH/equivalence.err" && rc=0 || rc=$?
   echo "exit $rc"; test "$rc" = 0 || { echo FAIL_AUDIT_TABLE; tail -30 "$SCRATCH/equivalence.err"; exit 1; }
   (cd "$LIVE" && sha256sum -c --quiet "$SCRATCH/live-before.sha256sum") || { echo FAIL_LIVE_CHANGED; exit 1; }; echo LIVE_INTACT
   test -z "$(git -C "$WTH" status --porcelain)" || { echo FAIL_SCAFFOLD_WROTE; exit 1; }
   test "$(sha256sum "$WTH/docs/reports/prior_evidence_registry.toml" | cut -d' ' -f1)" = "$REG_SHA" || { echo FAIL_REGISTRY_TOUCHED; exit 1; }; echo SCAFFOLD_WROTE_NOTHING
   ```
2. *Por horizonte:* T∩ (h=1, h=7) e o motivo do h=7 menor (calendário, D-M5);
   A1 (contagem fora, max |Δ|) — fora em algum horizonte → diagnóstico D13 na
   ordem, categoria "alvo", a comparação de modelo daquele horizonte **para**
   (as linhas A10/A11 daquele horizonte ficam `not_compared: A1`).
3. *A2 e sentido:* cada linha `out_of_tolerance`/`divergent_sense` percorre o
   diagnóstico pré-declarado do §1 e recebe `explained:<categoria>` (com (a), (b),
   (c) da §5.6 verificados — as previsões por conta, como o fator 2 ou a amostra
   reconstruída, recalculadas pelo andaime) ou `not_explained` → `[finding]` no
   relatório. A1/A2 fora **com indício de defeito na pipeline nova** →
   `[finding]` investigado antes de fechar (doc §5.6, exceção); correção = desvio
   (§4.6), nunca ajuste para "bater".
4. *Relatório* `docs/reports/equivalence_audit.md`: hashes dos dois lados (registro
   + `generation_digest` `96c05413…` e `result_digest` `7c7940d4…`); diferenças
   declaradas entre as pipelines como contexto; A9, A10, A11 (a tabela do
   `equivalence.md` entre os marcadores, com a classificação final); `[finding]`
   não explicados; inventário do andaime (arquivos de `tests/equivalence/`) e a
   aposentadoria (doc §5.7: comparações registradas, nada oficial depende dele,
   motivo). Entrada `[measurement] E4` em §7 com o comando, o exit e
   `SCAFFOLD_WROTE_NOTHING`.

**E5 — Teste opt-in e commits dos relatórios (A12, A13).**

1. Copiar para `DECLARED` do `test_official_vs_prior_evidence.py` a classificação
   do relatório (mesmas linhas); T1 da Task 11 (`pytest tests/equivalence/ -rs`,
   ruff, mypy) → o opt-in `SKIPPED` com o motivo.
2. Commits: `docs(evaluation): relatório da equivalência com a evidência anterior [8.2/--]`
   (relatório + §7) e `test(evaluation): tabela declarada da equivalência [8.2/--]`
   (o teste).
3. Com o oráculo, sobre a árvore commitada (CB-6):
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   test -z "$(git -C "$WTH" status --porcelain)" || { echo FAIL_WT_DIRTY; exit 1; }
   BEFORE=$(sha256sum "$WTH/docs/reports/prior_evidence_registry.toml" "$WTH/docs/reports/equivalence_audit.md")
   MSYS_NO_PATHCONV=1 docker run --rm $RES $HMOUNTS -v $MAIND/data/analytics:/oracle:ro -v $MAIND/data/cohorts/aapl:/official:ro $HENVS -e EQUIVALENCE_ORACLE_ROOT=/oracle -e EQUIVALENCE_OFFICIAL_ROOT=/official "$IMAGE_ID" sh -c "$PRE; uv run --no-sync pytest tests/equivalence/test_official_vs_prior_evidence.py -rs -q --no-cov -p no:cacheprovider" > "$SCRATCH/optin.out" && rc=0 || rc=$?
   echo "exit $rc"; tail -3 "$SCRATCH/optin.out"; test "$rc" = 0 || { echo FAIL_OPTIN; exit 1; }   # 1 passed
   test -z "$(git -C "$WTH" status --porcelain)" || { echo FAIL_TEST_WROTE; exit 1; }
   test "$(sha256sum "$WTH/docs/reports/prior_evidence_registry.toml" "$WTH/docs/reports/equivalence_audit.md")" = "$BEFORE" || { echo FAIL_TEST_TOUCHED_FILES; exit 1; }; echo TEST_NEVER_WRITES
   ```
   Prova negativa (não vácua: sem a checagem de árvore limpa do bloco acima —
   a edição à mão suja a árvore de propósito):
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   T=tests/equivalence/test_official_vs_prior_evidence.py
   # antes: alterar à mão a classificação de UMA linha de DECLARED em $WTH/$T (não commitar)
   test -n "$(git -C "$WTH" status --porcelain -- "$T")" || { echo FAIL_NO_EDIT; exit 1; }
   MSYS_NO_PATHCONV=1 docker run --rm $RES $HMOUNTS -v $MAIND/data/analytics:/oracle:ro -v $MAIND/data/cohorts/aapl:/official:ro $HENVS -e EQUIVALENCE_ORACLE_ROOT=/oracle -e EQUIVALENCE_OFFICIAL_ROOT=/official "$IMAGE_ID" sh -c "$PRE; uv run --no-sync pytest $T -rs -q --no-cov -p no:cacheprovider" > "$SCRATCH/optin-neg.out" && rc=0 || rc=$?
   echo "exit $rc"; test "$rc" != 0 || { echo FAIL_NEGATIVE_PASSED; exit 1; }
   grep -qE 'DECLARED|declared|!=|mismatch' "$SCRATCH/optin-neg.out" || { echo FAIL_NO_DIFF_SHOWN; exit 1; }
   grep -nE 'DECLARED|declared|!=|mismatch' "$SCRATCH/optin-neg.out" | head -20
   git -C "$WTH" checkout -- "$T"
   test -z "$(git -C "$WTH" status --porcelain)" || { echo FAIL_WT_DIRTY_AFTER; exit 1; }; echo NEGATIVE_PROOF_OK
   ```
   (o `grep` tem de mostrar a linha alterada no diff da asserção; o padrão exato
   segue a mensagem do `test_declared_vs_parsed_mismatch_shows_the_diff`.)
   Saídas em §7 (`[measurement] E5`), commit `docs(evaluation): evidência do teste
   opt-in da equivalência [8.2/--]`. Depois, o **ponto 2** do plano (`make check`),
   o roadmap e `stage 8.2: complete`.

**Se falhar** (nunca editar silver, gold, cópia julgada ou `ATTEMPTS.jsonl` à mão;
nunca montar a partição viva com escrita; nunca re-julgar):

| Sintoma | Ação |
|---|---|
| Bloco "HEAD íntegro": `FAIL_WT_DIRTY`, `FAIL_CHANGED_SINCE_GATE1`, `FAIL_WORKING_COPY` | parar; commitar ou descartar o que sujou a árvore; se um script de evidência ou o driver mudou desde o `GATE1`, ele precisa de novo `make check` (`[deviation]` justificado) e `GATE1` atualizado antes de seguir |
| E1: `FAIL_NOT_DM1` (sha256 ≠ D-M1) | `[finding]` e **parar** (o oráculo mudou desde a medição; nada é lido) |
| E1: fonte de definição de baseline ausente | zero comuns, tabela por baseline vazia registrada (D12 a); o resto segue |
| E1: T1 vermelho no `comparison_set.py` | corrigir só a forma (nunca por valor: nenhum foi lido); repetir o T1 |
| E2: `git worktree add` recusado (hook ou caminho existente) | conferir `git worktree list`; caminho existente de sessão anterior → `git worktree prune` e outro `REPRO`; recusa do hook → registrar e repetir pelo checkout principal (`git -C "$MAINH" worktree add --detach …`, sem branch) |
| E2: `FAIL_LISTING_NOT_REGISTERED`, `FAIL_BACKUP`, `FAIL_RESTORE`, `FAIL_DISPOSABLE_LAYOUT` | não seguir; `[finding]` e **parar** (entrada congelada — ADR 8.1.0003 item 6b); o descartável é apagado só depois do registro |
| E2: `FAIL_JUDGED_COPY`/`FAIL_DIGEST` | cópia julgada adulterada: restaurar do backup `judged-…` com `sha256sum -c` e `[deviation]` (ADR 8.1.0004 item 2c); nunca re-julgar |
| E2: `FAIL_IMAGE`, `FAIL_TREE_DIRTY`, `FAIL_ENV_EQUAL` (chave divergente), `FAIL_CPU_MAX`, `FAIL_KERNEL` | não rodar como R-BIT; `[finding]` (diagnóstico de ambiente, não de código); parada para decisão (concept §6) |
| E2: `FAIL_CHECK` com `ImportError`/`AttributeError` | o driver usa nome ausente em `060537fc`: `fix` do driver no HEAD (`[deviation]`), `make check` extra justificado, `GATE1` novo, repetir E2 |
| E2: `AST_DIFF` num arquivo (exit 1 do `ast-equal`) | `[finding]` no relatório (a reprodução em `060537fc` continua sendo o claim; o diff só deixa de confirmar a base); seguir |
| E3: `FAIL_REPRO_EXIT` com `OOMKilled true` / exit 137 | repetir com mais `--memory` (memória não é chave do I4) num **novo** descartável (E2 itens 3–6), `[deviation]` |
| E3: `FAIL_REPRO_EXIT` sem OOM, `FAIL_REFRESH_STATUS`, `FAIL_REPRO_FILES` | logs (`repro.err`); `[finding]`; nada é apagado; diagnóstico antes de repetir (repetição = novo descartável, E2 itens 3–6) |
| E3: `FAIL_ENV_EQUAL_RUN`, `FAIL_SNAPSHOT_CHANGED` (GB-7) | o ambiente mudou entre o `--check` e a corrida (ou o driver não grava a mesma foto): `[finding]` de ambiente, a reprodução não conta como R-BIT; parada para decisão |
| E3: `FAIL_JUDGMENT_IN_DISPOSABLE` | `[finding]` e **parar**: o driver fez efeito de julgamento (contradiz D2); nada é usado |
| E3: `FAIL_FREEZE_CHANGED` (GB-3) | o venv mudou durante as Etapas: `[finding]`, a reprodução não conta; descobrir quem sincronizou, refazer E2 e E3 com o venv congelado |
| E3: identidade desigual (I3) | `bit_identical = false`, "outra entrada"; `[finding]` e diagnóstico (§1); nada comparado como resultado |
| E3: `FAIL_NOT_BIT_IDENTICAL` (exit 1) com I3–I4 satisfeitas | `[finding]` R-BIT, **parada**; diagnóstico pré-declarado do §1 na ordem, cada passo em §7; nenhuma tolerância; a geração julgada não é trocada (doc §4.6) |
| E3: exit 2 do `audit-reproduction` | ler o `audit.err` (`JudgedGenerationTamperedError` → restauração do backup da cópia e `[deviation]`; outro erro → `[finding]`) |
| E3/E4/E5: `FAIL_LIVE_CHANGED`/`FAIL_LIVE_NEW_FILE` | `[finding]` e **parar**: algo escreveu na partição viva; restaurar dos backups conferidos e `[deviation]` |
| E4: `FAIL_AUDIT_TABLE` com `PriorEvidenceHashError` | o oráculo mudou depois do registro: `[finding]`, **parar** (nunca regenerar o registro) |
| E4: `dataset_fingerprint` do `ReadTrainingGrid` ≠ `00e4406d…` | `[finding]` e parar (a partição viva não é a entrada julgada) |
| E4: `FAIL_SCAFFOLD_CHANGED` | o andaime mudou depois do `GATE1` (fora do `comparison_set.py` da E1): parar; a mudança precisa de T1, revisão e `make check` extra justificado (`[deviation]`), `GATE1` novo, antes de qualquer leitura |
| E4/E5: `FAIL_SCAFFOLD_WROTE`, `FAIL_REGISTRY_TOUCHED`, `FAIL_TEST_WROTE`, `FAIL_TEST_TOUCHED_FILES` | o andaime escreveu: `[finding]`, `git -C "$WTH" checkout -- <arquivo>`, corrigir o andaime (`fix`, T1) e repetir |
| E4: A1 fora | D13 (diagnóstico na ordem), categoria "alvo", comparação de modelo daquele horizonte para; regra não afrouxada |
| E5: `FAIL_OPTIN` com o oráculo | corrigir a cópia de `DECLARED` (nunca o cálculo para caber); se o recomputado mudou entre E4 e E5, `[finding]` |

## 3. Gate de saída da Stage

### Verificações automatizadas

Tudo no container (nada de suíte no host; ADR 0.0.0059):
```bash
make check PYTEST_PAR='-n 4 --dist loadgroup'   # ponto 2 do plano (comando literal do §1); cobertura por
                                                 # arquivo lida da tabela term-missing desta MESMA saída
                                                 # (cada arquivo de src/ tocado >= 90 %)
MSYS_NO_PATHCONV=1 $RUN sh -c "$PRE; uv run --no-sync pytest tests/equivalence/test_official_vs_prior_evidence.py -rs -q --no-cov"   # 1 skipped, motivo com o registro
git diff --exit-code origin/develop...HEAD -- scripts/arch_baseline.toml        # nenhuma entrada nova de baseline
python scripts/check_technical_postexec.py docs/stages/8.2-equivalence-audit/technical.md
```

### Verificações funcionais
- [ ] E1: registro commitado antes de qualquer número do anterior (`git log`).
- [ ] E2: `TREE_AT_JUDGED`, `TREE_CLEAN`, `SAME_IMAGE`, `BACKUP_OK`, `RESTORE_OK`,
      `ENV_EQUAL`, `cpu.max`, freeze, `ast_diff 0`, saídas literais em §7.
- [ ] E3: driver exit 0, `audit-reproduction` exit 0 com `bit_identical true`,
      `LIVE_INTACT`, `NO_JUDGMENT_IN_DISPOSABLE`, `reproduction_audit.md` commitado.
- [ ] E4/E5: `equivalence_audit.md` commitado; opt-in `1 passed` com o oráculo e
      `1 skipped` sem ele.

### Checklist de fechamento
- [ ] 11 Tasks commitadas, cada uma com o seu T1 verde; Checkpoints C nas
      fronteiras do §4 com disposições registradas
- [ ] Auditoria de testes com mutação real **antes do ponto 1**, todos os itens
      "sim", saídas em §7
- [ ] Dois `make check` do plano verdes (três se o ponto 1 precisou de `fix`),
      saídas coladas no relatório
- [ ] `docs/roadmap.md`: bloco da 8.2 com a lista fechada de arquivos (inclusive
      `audit_reproduction.py` e o andaime) e linha no Histórico (A15); 8.2 `done`,
      `updated_at` e `last_reviewed_at` de hoje; commit `stage 8.2: complete`
- [ ] ADRs 8.2.0001–0003 `accepted`
- [ ] PR contra `develop` com `Closes #232`
- [ ] `concept.md` sem retoque retrospectivo pendente

## 4. Ordem de dependência entre Tasks

```
01 ─► 02 ─► 04 ─► 05 ─► 06 ─► 07 ─► 08 ─► 09 ─► 10 ─► 11 ─[make check 1]─► E1 ─► E2 ─► E3 ─► E4 ─► E5 ─[make check 2]
      03 ──┘
```

- 01 antes de 02 (DTO e mapa); 02 e 03 antes de 04 (comparador e leitor); 04
  antes de 05; 05 antes de 07 (o teste chama o subcomando); 06 antes de 07 (o
  teste chama o driver); 08 antes de 09 (a sonda do contrato importa
  `tests.equivalence`) e de 10–11 (registro e checagem); 10 antes de 11; 11 antes
  da E1 (o `comparison_set.py` existe para receber os comuns); E1 → E5 na ordem do
  D10.
- **Checkpoint C** (revisão do bloco por subagente, sem gate de suíte) depois de
  03, 05, 07 e 11; a **auditoria de testes** com mutação real fecha antes do
  ponto 1 (Task 11), nunca depois da E3.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| O `import-linter` não aceita `financial_forecasting` como fonte de um contrato `forbidden` contra o pacote externo `tests` | Task 09: ficar só com o teste de arquitetura da Task 08 (AST + literais) e `[deviation]` com a mensagem do `lint-imports`; A14 por grep + teste |
| Um builder grava coluna não prevista no mapa | o comparador ergue na Task 07 (sintético) ou na E3 (real): acrescentar a classe no mapa com a regra do concept §4 (`[deviation]`); nunca fallback por tipo |
| Mundo sintético da Task 07 sem alguma das 19 tabelas não vazia | a completude cobre as não vazias e a unit cobre o schema; registrar as vazias na mensagem |
| `ReadTrainingGrid`/leitor silver exigem escrita (lock, cache) sobre a montagem `:ro` | montar o adaptador com o parâmetro que desliga a escrita, ou ler os mesmos Parquet pelo `ParquetMedallionStore` de leitura; `[deviation]` |
| Bind mount de arquivo único (`/driver/…`) não aparece no Docker Desktop | montar `$WTD/scripts:/driver:ro` (o diretório; fora dos caminhos do probe do mesmo jeito), `[deviation]` |
| Volume `financial-forecasting_app-venv` (compartilhado por todas as worktrees) re-sincronizado depois da 8.1 ou durante as Etapas | `ENV_EQUAL` falha nas chaves `env.lib.*`/`env.probe.*`, ou `FREEZE_SAME` falha entre E2 e E3: diagnóstico de ambiente, parada (concept §6); proibição declarada de `uv sync`/`make setup` em qualquer worktree da E2 ao fim da E3; nunca `uv sync` para "consertar" sem decisão |
| Tempo da E3 acima de 3× o esperado sem progresso | `docker stats ff82-repro`, registrar; não matar sem `[finding]` |
| `git worktree remove` recusa por arquivos não rastreados | `rm -rf` da árvore temporária e `git worktree prune` (nenhum dado do repo nela) |

## 6. Referências

- [`./concept.md`](./concept.md); ADRs
  [8.2.0001](../../adr/8_2_0001-reproduction-at-judged-commit-in-disposable-data-root.md),
  [8.2.0002](../../adr/8_2_0002-reproduction-comparison-by-result-layer-and-judged-copy-reader.md),
  [8.2.0003](../../adr/8_2_0003-prior-evidence-scaffold-in-tests-with-hash-registry-and-opt-in-test.md);
  consumidos: 0.0.0059–0.0.0062, 3.5.0001, 6.4.0005, 6.5.0006, 7.1.0003,
  8.1.0002–8.1.0004
- Doc de domínio [`reproduction-equivalence-and-reporting`](../../domain/evaluation/reproduction-equivalence-and-reporting.md) §2.2, §4.2–§4.7, §5.1–§5.7, §8.2
- Technical [8.1](../8.1-confirmatory-run/technical.md) §1 (comandos, chaves do
  ambiente, layout de `judged/`), Etapa R (modelo do runbook) e §7 (evidência da
  corrida, finding do `PYTEST_PAR`, erratas O1/O2)
- [`../../LAYOUT.md`](../../LAYOUT.md) §2, §3, §8; [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §2, §3.4, §4, §6;
  [`../../PIPELINE.md`](../../PIPELINE.md) §4.3; [`../../RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) Passos 6–10 e §Gates em camadas
- Skills: `task-ordering-hex`, `hex-arch-python`, `pytest-with-fakes`,
  `orchestrator-design`, `data-shape-evidence`, `composition-root`,
  `architecture-fitness`
- Issue [#232](https://github.com/MarceloSanC/financial-forecasting/issues/232)

### Matriz de rastreabilidade (concept §11 → Task → teste/evidência)

| # | Critério de aceite | Task(s)/Etapa | Teste / evidência |
|---|---|---|---|
| A1 | Registro antes da leitura | 08, E1 | `test_prior_evidence_registry_check.py` (inclusive `test_built_registry_round_trips_and_verifies`); `REGISTRY_EQUALS_DM1`, `REGISTRY_OK`; commit do registro antes do E4 no `git log` |
| A2 | Entrada e ambiente da reprodução | 06, E2, E3 | `test_reproduction_evidence.py::test_env_equal_*`; `LISTING_IS_REGISTERED`, `BACKUP_OK`, `RESTORE_OK`, `TREE_CLEAN`, `SAME_IMAGE`, `ENV_EQUAL`, `CPU_MAX_6`, `FREEZE_E2` e `FREEZE_SAME` em §7 |
| A3 | Reprodução real bit a bit | 01, 02, 04, 05, E3 | `test_compare_reproduction.py`; `test_audit_reproduction.py`; `test_audit_reproduction_cli.py` (inclusive `test_altered_leaf_in_reproduced_scorecard_json_exit_1_with_scorecard_line`); `audit.out` (`BIT_IDENTICAL`, `7c7940d4…` × 3) e `reproduction_audit.md` |
| A3b | Driver testado | 06, 07, E2 | `test_reproduce_judged_generation.py` (lista da Task 06); `test_reproduction_process_independence.py::test_reproduced_result_digest_is_independent_of_hash_seed`; `--check` em `060537fc` (`check.json`, `ENV_EQUAL`, `CHECK_WROTE_NOTHING`) |
| A4 | Partição viva intocada | 05, 07, E2, E3 | `test_nothing_written_in_either_root`; `test_reproduced_root_has_no_judged_dir_nor_attempts`; `live-before.sha256sum` (partição inteira) + `LIVE_INTACT`; `NO_JUDGMENT_IN_DISPOSABLE` |
| A5 | Leitor da cópia julgada | 03 | `test_judged_generation_store_contract.py` (lista da Task 03); `check_port_coverage`/`check_fake_parity` no ponto 1 |
| A6 | Comparador testado | 01, 02, 07 | `test_reproduction_comparison_dtos.py::test_every_schema_column_has_a_declared_class`; `test_compare_reproduction.py` (lista da Task 02); `test_every_stored_column_has_a_declared_class` |
| A7 | R-BIT-COMMIT registrado | 06, E2, E3 | `test_reproduction_evidence.py::test_ast_equal_*`; `ast-equal.txt` (15 `AST_EQUAL`, auto-teste), `src-8.2.txt` justificada no `reproduction_audit.md` (com o `[deviation]` de redação para o `parquet_gold_store.py`) |
| A8 | Claim declarado | E3 | seção de claim do `reproduction_audit.md` ((a) afirmado, (b) citado, (c) não executado) |
| A9 | EQ-MUST A1 | 10, E4 | `test_scaffold_comparisons.py::test_a1_*`; tabela A9 do `equivalence_audit.md` (T∩, fora, max \|Δ\| por h) |
| A10 | EQ-MUST A2 | 10, 11, E4 | `test_a2_tolerance_is_max_of_r2_and_storage_precision`, `test_a2_not_realizable_*`; tabela A10 com a classificação |
| A11 | Tabela de sentido por horizonte | 10, 11, E4 | `test_dm_sign_*`, `test_dm_rejection_*`, `test_side_of_nominal_*`, `test_sense_cell_*`; tabela A11 (candidato × candidato sempre; por baseline comum ou vazia registrada) |
| A12 | Relatório de equivalência | 11, E4, E5 | `test_audit_table_render.py`; `equivalence_audit.md` com hashes, contexto, A9–A11, findings, inventário e aposentadoria |
| A13 | Teste fora do CI | 08, 11, E4, E5 | `test_prior_evidence_registry_check.py` (sempre ativo); opt-in `SKIPPED` com `-rs` (T1 da 11 e §3), `1 passed` com o oráculo e `TEST_NEVER_WRITES`/`SCAFFOLD_WROTE_NOTHING` (E4, E5) |
| A14 | Isolamento do anterior | 08, 09 | `test_prior_evidence_isolation.py`; contrato `src-no-tests` no `lint-imports` e caso real em `test_import_contracts.py` (ponto 1) |
| A15 | Roadmap e gates | 11, saída | pontos 1 e 2 do plano (saídas coladas, cobertura por arquivo); roadmap no fechamento |

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
> **Regra de pergunta antes da nota.** Algo não previsto no Concept ou neste
> Technical → triagem `evidence-resolution` (E/C decide e registra; só P sobe ao
> humano), depois a entrada abaixo.

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
`decision:C`), `finding`, `deviation`, `measurement`. Outra tag no cabeçalho de
entrada é recusada por `scripts/check_technical_postexec.py`.

### 2026-10-23 — [decision:C] Task 01, forma do `ClassComparison`/`ReproductionComparison` — Claude (executor)
**Contexto:** o §1 pede `max_abs_diff = None` para R1 não numérica e validação na
construção, mas uma classe de uma tabela mistura colunas numéricas (inteiros) e
rótulos; sem saber quantos pares numéricos houve, o DTO não distingue "None
legítimo" de "max esquecido".
**Pergunta:** como o DTO valida o max |Δ| sem conhecer as colunas?
**Opções:**
- A — só checar `max_abs_diff >= 0` quando presente.
- B — campo `numeric` (pares com os dois lados numéricos não-`bool`): `max_abs_diff`
  é `None` sse `numeric = 0`, e `0.0` quando `different = 0`. ✅ recomendada
**Decisão:** B. Também derivados (não campos): `IdentityComparison.equal`,
`ScorecardComparison.equal` (`different = 0`), `ReproductionComparison.totals` (soma
das tabelas; max dos max) e `bit_identical`; `TableComparison` recusa
`keys_equal = false` sem diferença R1 (a linha de chave só de um lado conta 1 em R1).
Colunas float da chave (`level_low`, `lower_level`, `band_level`…) ficam R2 e
`block_estimates` (texto) R1, pela regra de tipo do concept §4.
**Razão:** reversível barato, sem âncora explícita no §1: impede DTO incoerente
(contagem e max que se contradizem) sem mudar o contrato do concept §4.

### 2026-10-23 — [deviation] Task 02, regra "número não-`bool`" com dono único — Claude (executor)
**Contexto:** o ripple da Task 05 rodou `tests/architecture/` e
`test_evaluation_validation_single_owner.py::test_number_rule_has_a_single_owner`
reprovou: o `_is_numeric` do `compare_reproduction` reescrevia
`isinstance(x, int | float) and not isinstance(x, bool)`, regra cujo dono único é
`domain/value_objects/_finite_number.py` (issue #167). O T1 da Task 02 não roda
`tests/architecture/`.
**Razão:** correção local, sem mudar comportamento: o comparador passa a usar
`is_real_number` do dono (`fix(evaluation): … [8.2/task-02-fix]`).

### 2026-10-23 — [decision:C] Task 11, status dos deltas de modelo na tabela — Claude (executor)
**Contexto:** o A11 (1) pede os deltas m_novo − m_A por nível, PICP e MPIW "documentados
com sinal, sem limiar" (EQ-DESC, doc §5.5); nenhum dos seis `RawStatus` da Task 10 é a
classificação de um delta sem limiar.
**Pergunta:** que status a linha de delta leva na tabela declarada?
**Opções:**
- A — `within_tolerance` (falso: não há tolerância).
- B — status `reported` (status `None` no código), só para os deltas; o lado do nominal,
  os sinais por baseline e o DM seguem `same_sense`/`divergent_sense`. ✅ recomendada
**Decisão:** B.
**Razão:** reversível barato; mantém o vocabulário do §2 para tudo o que é classificado e
não inventa tolerância onde o doc diz que não há (EQ-DESC).

### 2026-10-23 — [deviation] Task 11, `PRIOR_CANDIDATE_LABELS` no `comparison_set.py` — Claude (executor)
**Contexto:** o A11 precisa identificar o candidato anterior (`BTSF`, D-M2) na
`MODEL_LABEL_COLUMN`; o §1 fixa só a coluna na E1. A constante nova
`PRIOR_CANDIDATE_LABELS: tuple[str, ...] = ()` entrou no `comparison_set.py` (arquivo da
Task 10, fora da lista da Task 11), ao lado da `MODEL_LABEL_COLUMN`, para a E1 fixar os
dois pela mesma lista de rótulos distintos (metadado, sem valor) no mesmo commit do
registro. Sem ela vazia, o `compute` recusa (`run the E1`).
**Razão:** o arquivo já é o que a E1 edita (runbook E1 passo 1); outra casa espalharia o
que a E1 fixa. Também entrou no `test_audit_table_render.py` um teste do `compute_rows`
sobre dois lados sintéticos (o cálculo da E4 só rodaria no opt-in) e o teste AST da porta
única de leitura (CC3-3 do Checkpoint C bloco 3).

### 2026-10-23 — [deviation] `env-equal` com `--preregistration-ref` obrigatória (emenda do runbook E2/E3) — Claude (executor)
**Contexto:** Checkpoint C bloco 3, CC3-1: o `env-equal` passou a filtrar a linha `started`
pela referência (CC2-2, `bd4b54ff`), mas o §2 Task 06 (linha "`env-equal <ATTEMPTS.jsonl>
<foto.json>`") e as chamadas do runbook na E2 passo do `--check` (`env-equal
"$P/judged/ATTEMPTS.jsonl" "$SCRATCH/check.json"`) e na E3 (`env-equal
"$P/judged/ATTEMPTS.jsonl" "$DISPH/reproduction/environment.json"`) não a passam. A opção
virou **obrigatória** no script (`[8.2/task-06-extra]`): sem ela o argparse sai com erro de
uso — a chamada antiga falha alto, nunca compara a `started` de outra referência.
**Razão / emenda:** §1–§6 não são editáveis com `status: done` (CONVENTIONS §3.4;
`check_technical_postexec.py`), então a emenda vale por esta entrada: nas duas chamadas do
runbook (E2 e E3), acrescentar `--preregistration-ref "$REF"` ao fim do comando
`env-equal`; o §2 Task 06 lê-se `env-equal <ATTEMPTS.jsonl> <foto.json>
--preregistration-ref <ref>`.

### 2026-10-23 — [deviation] Checkpoint C final (bloco 4), CC4-1..CC4-8 no andaime — Claude (executor)
**Contexto:** o Checkpoint C final achou o andaime da Task 11 sem a classificação final na
tabela declarada (CC4-1) e o `compute_rows` quase sem teste — cinco mutações sobreviviam
(CC4-2) —, além de CC4-3..CC4-8. Correções em `[8.2/task-10-fix]` (CC4-5) e
`[8.2/task-11-fix]` (o resto):
- **CC4-1:** `APPLICABILITY_TEXT` transcreve LITERALMENTE a tabela "Aplicabilidade por
  comparação" do doc de domínio §5.6 (um teste confere linha a linha contra o doc);
  `APPLICABILITY` dá, por tipo de comparação, os tokens de categoria aceitos (`alvo`,
  `escala`, `bruto_rearranjado`, `amostra`, `pesos_grade`, `defeito_referenciado`,
  `convencao_empate`, `agregacao_seeds`). A tabela ganha as colunas `tipo` e
  `classificação`: `within_tolerance`/`same_sense` (passou), `explained:<token>` ou
  `not_explained` (não passou), `not_compared:<motivo>` (`A1`, `empty_intersection`,
  `sample`, `dm_rows`), `reported` (delta). O `parse` recusa classificação que não cabe no
  status ou categoria fora da aplicabilidade do tipo. **Reconciliação com o runbook:** o
  `not_compared: A1` do E4 passo 2 escreve-se `not_compared:A1` (sem espaço); o
  `explained:<categoria>` do E4 passo 3 usa os tokens acima. Seguindo o mesmo passo 2, as
  linhas **A10** de um horizonte com A1 fora também viram `not_compared:A1`. O teste opt-in
  afirma ids, tipos e status recomputados = `DECLARED`, e `DECLARED` = a tabela parseada (a
  classificação é declarada na E5).
- **E4 passo 1:** o runbook chama `python -m tests.equivalence.audit_table` sem argumentos;
  o `main` passou a ler `EQUIVALENCE_ORACLE_ROOT`/`EQUIVALENCE_OFFICIAL_ROOT` quando não há
  argumento (antes, exit 2).
- **CC4-3** seed que não cobre T∩ → `ValueError` nomeando as seeds (sem descarte);
  **CC4-4** D7 e T∩ só pelas funções de `alignment.py`; **CC4-5** meio ulp pelo tipo
  registrado (`half_ulp_of`); **CC4-6** as unidades `dim_run|<sweep>` e
  `fact_oos_predictions|…` do silver vivo, hasheadas pelo `SilverContentAccumulator` com o
  pós-filtro do `RefreshGold`, têm de ser as do `silver_content` da cópia julgada;
  **CC4-7** guarda da E1 no início do `compute` (coluna e rótulos do candidato; `source` de
  baseline comum no registro); **CC4-8** predição nova repetida → `ValueError`.
**Mutações M1–M5 (CC4-2), cada uma aplicada, `pytest tests/equivalence/test_audit_table_render.py`
e revertida:**
```
M1 D7 janela mais antiga: 2 failed, 18 passed, 1 warning in 7.62s
M2 agregação só a primeira seed: 2 failed, 18 passed, 1 warning in 7.67s
M3 lado do nominal novo fixo inside: 1 failed, 19 passed, 1 warning in 7.60s
M4 a1_ok ignorado: 1 failed, 19 passed, 1 warning in 7.69s
M5 variante raw no candidato anterior: 1 failed, 19 passed, 1 warning in 7.60s
```
**Razão:** correções in-scope do andaime, sem mudar concept nem ADR; o runbook (§1–§6
congelados) fica reconciliado por esta entrada.

### 2026-10-23 — [deviation] re-auditoria de testes (rodada b): l3, m, n e registro da tabela vazia — Claude (executor)
**Contexto:** a re-auditoria independente em `0d9ede0f` viu sobreviverem l3 (linha nova na
tabela da §5.6 do doc passava), m (`_model_predictions` sem a conferência do silver) e n
(T∩ vazio num horizonte sem a sua linha). Correções em `[8.2/task-11-fix]`:
- o teste da aplicabilidade extrai a tabela inteira do doc e afirma igualdade de CONJUNTO
  com `APPLICABILITY_TEXT` nos dois sentidos;
- `_model_predictions` exercitado com silver sintético (leitor de duck typing) e
  `silver_content` julgado divergente numa unidade `fact_oos_predictions|…`;
- `compute_rows` com h=7 sem predição nova: A9 e `A11/h7/stopped` = `empty_intersection`
  (motivo `empty_intersection`). Para isso, o "A1 fora" que para A10/A11 passou a ser só
  `out_of_tolerance` (T∩ vazio não é A1 fora; o A10 do horizonte segue calculado);
- `recomputed_matches` confere também o motivo de `not_compared:<motivo>`;
- com `COMMON_BASELINES` vazio, a linha `A11/baselines/none` (`not_compared:no_common_baseline`)
  registra a tabela de baselines vazia (A11, D12 a).
**Mutações (aplicadas, `pytest tests/equivalence/test_audit_table_render.py`, revertidas):**
```
l3 linha nova na tabela da §5.6 do doc: 1 failed, 23 passed, 1 warning in 7.58s
m sem conferência do silver oficial: 1 failed, 23 passed, 1 warning in 7.60s
n T∩ vazio sem a sua linha: 1 failed, 23 passed, 1 warning in 7.75s
```
**Razão:** cobertura in-scope do andaime antes do ponto 1 do plano de gates.

### 2026-10-23 — [decision:C] semântica do T∩ vazio no andaime (escopo de A1, A10 e A11) — Claude (executor)
**Contexto:** a rodada b mudou o que para A10/A11 num horizonte (`6cfbcf91`): antes, um T∩
vazio caía no mesmo caminho do "A1 fora".
**Decisão e escopo:**
- **T∩ vazio = A1 não verificável, não "A1 fora".** O concept §6 ("Interseção de um
  horizonte vazia | registrado; sem comparação numérica naquele horizonte (EQ-INTER item
  4)") e o doc de domínio §5.3 item 4 ("Se a interseção de um horizonte for vazia, aquele
  horizonte não tem comparação numérica — registrado, não contornado") pedem o registro, não
  a categoria "alvo": A9 do horizonte = `empty_intersection`.
- **A11 para** naquele horizonte com `A11/h<h>/stopped` = `empty_intersection`
  (`not_compared:empty_intersection`): a comparação de modelo (m_novo × m_A) vive em T∩.
- **A10 continua:** o A2 do doc §5.4 é "código novo aplicado às predições anteriores, na
  mesma amostra que o anterior usou" contra o número anterior gravado — a amostra é a do run
  anterior, com o y do próprio anterior; não depende de T∩ nem do realizado novo.
- **A1 `out_of_tolerance`** (D13 intacto): a comparação de modelo daquele horizonte para e
  as linhas A10/A11 do horizonte viram `not_compared:A1` (runbook E4 passo 2).
**Razão:** reversível barato; ancorado no concept §6 e no doc §5.3 item 4 / §5.4.

### 2026-10-23 — [measurement] E0/E1 — HEAD íntegro e rótulo de modelo — Claude (executor das Etapas)
**Contexto:** E0 com `STAMP=20261023-190339`, `GATE1=0d422aab2e2f4dc8136220378a896038d8b96bb2`
(`make check` 1 verde: 8965 passed, coverage 99 %). Bloco "HEAD íntegro" no início da E1:
```
WT_CLEAN
BLOB scripts/reproduce_judged_generation.py 855aaa02744f30d13dcae74beea1274bb95b7aff
BLOB scripts/reproduction_evidence.py 960598f5229765f68b2102c3622d35aaa4e166d2
BLOB tests/equivalence/prior_evidence.py f04e2f2a8699d05512725c563cad93d267148a76
```
E1 passo 1 (container `b69a7620…`, `data/analytics` `:ro`; lidas só `parent_sweep_id`, `split`,
`model_version_x`, `model_version_y`): 52 280 linhas `phase_b_confirmatorio_20260524`/`test`;
as duas colunas têm os mesmos 18 rótulos distintos (15 `20260524_*_BTSF` +
`baseline_zero_return_v1`, `baseline_historical_mean_rolling_v1`,
`baseline_historical_quantiles_rolling_v1`), sem nulo, e `rows_x_ne_y 0` (iguais linha a
linha). `MODEL_LABEL_COLUMN = "model_version_x"`; `PRIOR_CANDIDATE_LABELS` = os 15 `*_BTSF`.
E1 passo 3:
```
exit 0
REGISTRY_EQUALS_DM1
REGISTRY_OK 5
exit 0
```
(`docs/reports/` não existia: o primeiro `cp` falhou e o bloco foi repetido inteiro depois do
`mkdir -p`.) Os 5 sha256 do registro = D-M1; linhas 410208, 452, 452, 60, 6.

### 2026-10-23 — [decision:C] E1 — baselines comuns — Claude (executor das Etapas)
**Contexto:** D12 a: comum só com as quatro partes da definição (estimador, janela,
parâmetros, regra de dispersão dos quantis) declaradas equivalentes nos dois lados, por fonte
versionada ou registrada; nome igual não basta.
**Fontes olhadas (só rótulos/definição, nenhum valor):**
- lado novo (HEAD): `features/modeling/domain/services/baseline_emission.py` l.140–146 e
  184–193 e `quantile_grid_emission.py` (`degenerate_grid` l.38, `sample_quantiles_type7`
  l.83); `config/cohorts/aapl_confirmatory.toml` l.93–107. `zero_return` = grade degenerada em
  0; `historical_mean` = média do train expansivo, grade degenerada; `historical_quantiles` =
  quantil tipo 7 (Hyndman & Fan) da janela rolante W = 252.
- (a) código do anterior: o `silver/dim_run` do sweep
  (`3b02f2a7169bbcdd295d52813e7542ff0ced8d81104ea93d1e631d8b0686eb10`) registra
  `git_commit = 2dc191160d6afb5529740730a517c9acd2089f65` só nas 15 linhas do candidato
  (as 45 dos baselines têm `git_commit` nulo; `pipeline_version = 0.1`); `git cat-file -e`
  falhou em todos os repositórios git de `C:/Users/Marcelo/Documents/Code/*`
  (financial-forecasting, learning, restaurant-hub, tcc-sentiment-analysis,
  whaka-dev-project-tamplate) → sem código.
- (b) payload: `silver/fact_config` do sweep
  (`8622c34338abb0ef263177b92308b4403b834641a4dd66db238dd224d1f1ea45`), linhas dos baselines:
  `training_config_json` = `{"baseline": "zero_return", "window": null}` (modo `point`),
  `{"baseline": "historical_mean_rolling", "window": 30}` (`point`),
  `{"baseline": "historical_quantiles_rolling", "window": 252}` (`quantile`);
  `dataset_parameters_json` e `search_space_json` vazios. Declara família e janela, não o
  estimador de quantil nem a regra de dispersão.
**Pergunta:** algum par é comum?
**Opções:**
- A — `historical_quantiles` comum por família + W = 252 iguais.
- B — zero comuns: `zero_return` sem regra de dispersão declarada no anterior;
  `historical_mean` com janela diferente (rolante 30 × train expansivo); `historical_quantiles`
  sem estimador de quantil declarado no anterior (tipo 7 não verificável). ✅ recomendada
**Decisão:** B. `COMMON_BASELINES = ()`; o A11 registra a linha
`A11/baselines/none` (`not_compared:no_common_baseline`). Como nenhuma fonte deu definição
completa, nenhum `[[definition_source]]` entra no registro e os dois arquivos do silver ficam
fora dele (o andaime não os lê; os sha256 acima registram o que foi olhado).
**Razão:** D12 a exige as quatro partes; A seria "nome (e janela) igual basta", que o technical
recusa explicitamente.

### 2026-10-23 — [deviation] E1 passo 4 — T1 vermelho por testes presos ao estado pré-E1 — Claude (executor das Etapas)
**Contexto:** com o `comparison_set.py` preenchido, o T1 da E1 deu `3 failed, 65 passed,
1 skipped`: `test_prior_reader_reads_only_registered_columns_and_filters` (o Parquet sintético
não tinha a coluna de rótulo que o leitor passa a ler), `test_compute_rows_requires_the_e1`
(partia do módulo sem monkeypatch) e `test_comparison_set_is_fixed_before_values`
(`assert cs.MODEL_LABEL_COLUMN is None`). Defeito de forma dos testes, não do cálculo.
**Razão / correção:** linha "E1: T1 vermelho" do "Se falhar" (corrigir só a forma; nenhum valor
lido). Commit `543e602a` (`test(evaluation): … [8.2/--]`): o oráculo sintético e a asserção
usam `readers.prior_columns`; a guarda da E1 parte do estado pré-E1 por monkeypatch; o teste do
conjunto aceita `None` ou uma das duas colunas. Verde com o `comparison_set.py` do GATE1 e com o
da E1 (`68 passed, 1 skipped` nos dois). Como o andaime mudou fora do `comparison_set.py`, a
guarda `SCAFFOLD_AS_GATE1` da E4 reprovaria: pela linha `FAIL_SCAFFOLD_CHANGED` do "Se
falhar", `make check` extra (antes da E2, fora do venv congelado) sobre o commit do registro,
que passa a ser o `GATE1`.

### 2026-10-23 — [measurement] E1 — `make check` extra e `GATE1` novo — Claude (executor das Etapas)
**Contexto:** antes do `make check` extra, a revisão do `543e602a` achou o esperado do
`test_prior_reader_reads_only_registered_columns_and_filters` tautológico (`prior_columns` dos
dois lados). Commit `096a2e9b` (`test(evaluation): … [8.2/--]`, só
`tests/equivalence/test_audit_table_render.py`): esperado literal `FILTER_COLUMNS` +
`VALUE_COLUMNS`, mais o rótulo só no `gold_oos` e só depois da E1, parametrizado `before_e1`
/`after_e1` por monkeypatch; mutação (`prior_columns` sem o rótulo) reprova o `after_e1`.
Forma do teste, nenhum valor lido.
`make check` extra (container `ff82-check`, imagem `:dev`, `UV_NO_SYNC`, antes da E2 e fora do
venv congelado) sobre `096a2e9b`: início 2026-10-23T19:14:15Z, fim 19:54:45Z, exit 0,
`8966 passed, 30 skipped`, coverage 98,68 %. Nada commitado entre o `096a2e9b` e o fim.
**Razão:** linha `FAIL_SCAFFOLD_CHANGED` do "Se falhar": `GATE1 := 096a2e9be7452fd3989abf9896300d6fc99dda0e`
(substitui o `0d422aab…` da E0 no `etapa-82.env`). Esta entrada só toca o `technical.md`; os
blobs do bloco "HEAD íntegro" seguem os do `GATE1`.

### 2026-10-23 — [measurement] E2 — pré-voo da reprodução em `060537fc` — Claude (executor das Etapas)
**Contexto:** venv congelado declarado (vi) antes do item 1. Bloco "HEAD íntegro" (HEAD
`cedd4511`, `GATE1` `096a2e9b`):
```
WT_CLEAN
BLOB scripts/reproduce_judged_generation.py 855aaa02744f30d13dcae74beea1274bb95b7aff
BLOB scripts/reproduction_evidence.py 960598f5229765f68b2102c3622d35aaa4e166d2
BLOB tests/equivalence/prior_evidence.py f04e2f2a8699d05512725c563cad93d267148a76
```
Item 1 (worktree destacada `repro-060537fc`): `TREE_AT_JUDGED`, `ENV_IGNORED`, `TREE_CLEAN`;
`DOTENV_SHA=408e44ff45f7883e2540d2e38650dea3f61d8e36a9a96bb51c6bce9f28bfd69b`.
Item 2: `SAME_IMAGE`, `NO_FF82`, `UV_LOCK_SAME_AS_HEAD=yes`.
Item 3: `LISTING_IS_REGISTERED`, `BACKUP_OK`, `RESTORE_OK`, `DISPOSABLE_INPUT_ONLY`
(descartável `data/reproductions/aapl-r3-20261023-190339`: `bronze inference processed raw silver`).
Item 4: `JUDGED_COPY_OK`, `DIGEST_OK`; `live-before.sha256sum` com 355 arquivos;
`current/MANIFEST.json` `56d3ee1c…` e `judged/ATTEMPTS.jsonl` `320def2b…`. O `grep` de
exibição do runbook (`' gold/…'`) não casa no Git Bash: o `sha256sum` do host grava o marcador
binário (`<hex> *gold/…`); as duas linhas foram exibidas com `grep -E 'MANIFEST|ATTEMPTS'`. Só
exibição — o `sha256sum -c` da E3/E4 lê esse formato.
Item 5:
```
exit 0
060537fc7069b38a318bb5cf839d84b7767b1b4f
0
600000 100000
6.18.54.1-microsoft-standard-WSL2
CONTAINER_AT_JUDGED / CONTAINER_TREE_CLEAN / CPU_MAX_6 / SAME_KERNEL
exit 0   (freeze: 172 linhas)
FREEZE_E2=0c95c798bd37701400d62f8b2f17e4504277fc71b91d64566b34091eb328035f
```
Item 6 (`--check`; `env-equal … --preregistration-ref "$REF"`, emenda do §7): `exit 0`,
`CHECK_WROTE_NOTHING`, `ENV_EQUAL`, `exit 0`. Foto: `commit 060537fc…`, `code.src 4d2b2540…`,
`code.uv_lock 0f36050a…`, `code.cohort_file 6d7c8b82…`, `code_dirty false`,
`preregistration_dirty false`, `env.image_id b69a7620…`, `env.probe.python 3.12.13`,
`env.probe.torch 2.13.0+cpu`, `env.probe.torch_threads 6`, `env.cpu_count 12`.
Item 7 (R-BIT-COMMIT): `exit 0`, `Python 3.12.13`, 15 `AST_EQUAL`, `files 15 ast_diff 0`.
`64b8a17d..HEAD -- src/` (acréscimos da 8.2): `M cli.py`, `M composition_root.py`,
`M evaluation_commands.py`, `M parquet_gold_store.py`, `A dtos/reproduction_comparison.py`,
`M ports/out/judged_generation_store.py`, `A use_cases/audit_reproduction.py`,
`A use_cases/reproduction_comparison.py` — fora do caminho refresh/scorecard, salvo o
`parquet_gold_store.py` (ver o `[deviation]` abaixo).
Item 8 (A3b): T1 verde da Task 07 e o ponto 1 (`test_reproduction_process_independence.py`
no `make check` do `GATE1`, `8966 passed`).

### 2026-10-23 — [deviation] E2 item 7 — redação do A7 para o `parquet_gold_store.py` — Claude (executor das Etapas)
**Contexto:** o A7 do concept pede cada acréscimo de `src/` desde `64b8a17d` "justificado como
fora do caminho de refresh/scorecard"; o `parquet_gold_store.py` está no caminho de leitura do
scorecard (`BuildConfirmatoryScorecard(reader=gold_store)`).
**Razão:** a Task 03 só extrai `_read_generation_dir` da `read_generation`, sem mudar
comportamento (suíte de contrato do `GoldGenerationReader` verde no ponto 1); e o claim é o da
execução em `060537fc`, onde o arquivo não tem a mudança. A justificativa do A7 para esse arquivo
lê-se "no caminho de leitura, sem mudança de comportamento, fora do claim".

### 2026-10-23 — [measurement] E3 — reprodução real e auditoria — Claude (executor das Etapas)
**Contexto:** bloco "HEAD íntegro" (HEAD `c2fa50bb`): `WT_CLEAN` e as mesmas três linhas `BLOB`
da E2. Corrida destacada `ff82-repro` (imagem pelo id), 20:08:36Z → 20:22:49Z (14,2 min):
```
repro.exit 0 / repro.state "0 false"
reproduction aapl_confirmatory-r3-00fd83d9cd39: refresh COMPLETED tables 19
reproduction aapl_confirmatory-r3-00fd83d9cd39: scorecard sha256 25b3e0a6e279c96aee1c825cdf1891a863c252064f4cc17ca0f14683a96d3ebf
REFRESH_COMPLETED / REPRO_FILES / ENV_EQUAL / SNAPSHOT_SAME_AS_CHECK / NO_JUDGMENT_IN_DISPOSABLE
```
(o `repro.err` saiu vazio: sem linhas `_timed`; o tempo é o do `docker inspect`.)
Item 2: `exit 0`, `FREEZE_SAME` (`0c95c798…` = `FREEZE_E2`). Item 3 (`audit-reproduction`):
`exit 0`, `bit_identical true`, os três `result_digest` = `7c7940d4…`, identidade igual nos 4
campos; `R1 882727/0/0.0`, `R2 288671/0/0.0`, `R3 1856/0/0.0`; 19 tabelas com `keys_equal true`;
`scorecard equal true leaves 66117 different 0`. `BIT_IDENTICAL`. Item 4: `LIVE_INTACT`.
Item 5: `docs/reports/reproduction_audit.md` (claim (a) afirmado, (b) citado da 7.1, (c) não
executado; tabelas por classe e por tabela).
Item 6: `git worktree remove` da `repro-060537fc` (exit 0; sem prune). Fim do venv congelado.

### 2026-10-23 — [finding] E4 passo 1 — `FAIL_AUDIT_TABLE` por `OfficialSilverMismatchError` do andaime — Claude (executor das Etapas)
**Contexto:** `SCAFFOLD_AS_GATE1` ok; o `python -m tests.equivalence.audit_table` saiu `exit 1`
com `OfficialSilverMismatchError: official silver differs from the judged copy's silver_content
in ['fact_oos_predictions|00d427b0…|2023', …]` (dentro do `read_official`, antes de qualquer
leitura da evidência anterior chegar ao cálculo — nenhuma linha da tabela foi gerada; nenhum
valor do anterior foi visto). Depois: `LIVE_INTACT`, árvore limpa.
**Diagnóstico (só hashes e chaves de unidade, nenhum valor):**
- o silver vivo é byte a byte o do backup de entrada da 8.1 (257 arquivos `silver/`, `diff` das
  listagens sha256 vazio), e esse backup reproduziu o `silver_content.digest` `7ac4c759…` na E3
  — o dado está certo;
- sonda descartável no scratchpad (`diag_units.py`, chama `read_official` com o
  `check_silver_units` substituído por um espião; fora do repo): `dim_run|<cohort>` igual;
  unidades `fact_oos_predictions|…` lidas 252 × julgadas 852; **0 com digest diferente, 0 só no
  lido, 600 só no julgado** — as 600 são dos 300 runs da ablação (o `silver_content` julgado tem
  `dim_run|aapl_ablation-r0-8a2d1de2dd8c` e as unidades `test` por ano desses runs, que o
  `RefreshGold._read_ablation…` consome).
**Causa:** defeito do andaime (`tests/equivalence/readers.py`, `check_silver_units.ours`): o
esperado toma **toda** unidade `fact_oos_predictions|` do `silver_content`, inclusive as da
ablação, mas o `_model_predictions` só lê os runs do `dim_run` do cohort. A mutação "m" da
rodada b usou um silver sintético sem ablação e não exercitou o caso.
**Estado e parada:** linha "E4/E5: andaime" do "Se falhar" não cobre exatamente este sintoma (o
andaime não escreveu; recusou); pela regra de parada dura da sessão, nada foi consertado. A
correção (restringir o esperado às unidades dos runs do cohort, ou exigir as da ablação como
"não lidas", com teste sintético que inclua unidades de ablação) precisa de `fix` no andaime,
T1, revisão e `make check` extra (`[deviation]`) e `GATE1` novo antes de repetir a E4 desde o
passo 1 (linha `FAIL_SCAFFOLD_CHANGED`). E2/E3 seguem válidas (não dependem do andaime).

### 2026-10-23 — [deviation] E4 — `check_silver_units` só com as unidades do cohort — Claude (executor das Etapas)
**Contexto:** o `[finding]` acima. Autorizado pela coordenadora (`[decision:C]`, caminho do "Se
falhar" do andaime; nenhum valor lido). Correção `0e59b9f9` (`[8.2/task-11-fix]`):
- `check_silver_units(read, consumed, partition, run_ids)`: o esperado (lado julgado) leva só
  `dim_run|<cohort>` e as unidades `fact_oos_predictions|<run_id>|<ano>` dos `run_ids` do cohort
  (os mesmos que o `_model_predictions` lê); o lado lido entra inteiro (ler unidade da ablação
  conta como "a mais"). Nunca as da ablação no esperado.
- testes: o unitário do `check_silver_units` ganha unidades de ablação no julgado (passa) e a
  leitura de uma unidade de ablação (falha); o do `_model_predictions` passa com
  `dim_run|ablation-01` e unidades `fact_oos_predictions` de ablação no julgado e ergue
  `OfficialSilverMismatchError` com a unidade do cohort adulterada.
**Mutações (aplicadas, `pytest tests/equivalence/test_audit_table_render.py`, revertidas):**
```
m  conferência desligada no _model_predictions: 1 failed, 24 passed, 1 warning in 7.65s
m2 esperado incluindo a ablação (cohort_only=False): 2 failed, 23 passed, 1 warning in 7.58s
corrigido: 25 passed, 1 warning in 0.51s
```
**T1:** `ruff format --check`/`ruff check` dos dois arquivos e `mypy` verdes (551 arquivos);
`pytest tests/equivalence tests/architecture -n 4 --dist loadgroup`: `448 passed, 1 skipped`
(o opt-in, com o motivo). Uma primeira rodada com `-n 4` **sem** `--dist loadgroup` deu 25
falhas só em `tests/architecture` (fixtures que injetam arquivo em `src/` se atropelando entre
workers; árvore limpa depois) — forma do comando, não do código; o `make check` usa
`loadgroup`. Pendente: revisão independente, `make check` extra e `GATE1` novo antes da E4.

### 2026-10-23 — [measurement] E4 — fix revisado, `make check` extra e `GATE1` novo — Claude (executor das Etapas)
**Contexto:** revisão independente do fix `0e59b9f9`: aprovado (um achado médio de cobertura de
teste, tratado depois da E5 só com testes). `make check` extra sobre `bec99bdf` (coordenadora):
`EXIT=0`, `8966 passed, 30 skipped`, coverage 98,68 %.
**Razão:** linha `FAIL_SCAFFOLD_CHANGED`: `GATE1 := bec99bdf60a075e78b181791b357dfe6cd8735b3`
no `etapa-82.env`. Esta entrada só toca o `technical.md`; a E4 recomeça do passo 1.

### 2026-10-23 — [measurement] E4 — tabela de equivalência e diagnóstico D13 do A1 — Claude (executor das Etapas)
**Contexto:** passo 1 (HEAD `09b9906b`, `GATE1` `bec99bdf`):
```
SCAFFOLD_AS_GATE1
exit 0          (python -m tests.equivalence.audit_table; 2483 linhas)
LIVE_INTACT
SCAFFOLD_WROTE_NOTHING
```
Passo 2: T∩ = 937 em h=1 (2022-03-30 → 2025-12-22) e em h=7 (2022-04-07 → 2025-12-31); o h=7
**não** ficou menor (os 937 timestamps do anterior caem em sessões do lado novo). A1 fora nos dois
horizontes: `out=934`, `max_abs_diff=3.67589654548528e-09` (tolerância meio ulp de `double`
= 1,11e-16·|y_ant|). Pela regra, A10 (1 230 linhas por horizonte) e A11 (`A11/h1/stopped`,
`A11/h7/stopped`) ficam `not_compared:A1`; `A11/baselines/none` = `not_compared:no_common_baseline`.
Diagnóstico D13 na ordem (sonda `diag_a1.py` no scratchpad, fora do repo, raízes `:ro`):
```
prior y_true type double
h=1: |Δ| max 3.676e-09, mediana 1.389e-10; rel max 5.829e-08 (0.978·2^-24), mediana 2.021e-08
     y_ant == float32(y_novo): 937/937; float32(y_ant) == float32(y_novo): 937/937
     y_ant float32-exato: 937/937; y_novo float32-exato: 3/937; sinal igual 937/937; corr 1.0
     |log1p(y_ant) − y_novo| max 9.30e-03
h=7: idem (rel max 0.978·2^-24; 937/937 nas três igualdades)
```
(1) definição multi-passo, (2) ajuste de preço e (3) mapeamento de timestamp descartados
(iguais em float32 ponto a ponto); (4) caminho float32 confirmado: o anterior gravou o realizado
arredondado para float32 num `double`. Passo 3: A9/h1 e A9/h7 → `explained:alvo` ((a) diferença
concreta: alvo anterior em precisão float32; (b) |Δ| ≤ 2⁻²⁴·|y|, observado 0,978·2⁻²⁴, sem viés;
(c) localizado no A1); nenhuma linha `out_of_tolerance`/`divergent_sense` além delas (as demais
não foram comparadas). Sem indício de defeito na pipeline nova (é o lado mais preciso).
**[finding]:** a premissa de D-M6 ("os dois lados gravam `double` — o caminho float32 não se
aplica ao alvo") não vale para os valores: o tipo físico é `double`, mas a precisão efetiva do
alvo anterior é float32; com o critério D13 não afrouxado, a comparação de modelo (A10/A11) não
roda nesta auditoria. Não bloqueia a 8.2 nem o veredito da 8.1 (doc §5.6). Passo 4:
`docs/reports/equivalence_audit.md`.

### 2026-10-23 — [measurement] E5 — teste opt-in da equivalência — Claude (executor das Etapas)
**Contexto:** passo 1: `DECLARED` = as 2 465 linhas da tabela do relatório (gerado da tabela por
script do scratchpad; A9/h1 e A9/h7 `explained:alvo`, o resto `not_compared:<motivo>`). T1 da
Task 11: `ruff format --check`/`ruff check` e `mypy` verdes; `pytest tests/equivalence/ -rs`:
`69 passed, 1 skipped` — `SKIPPED [1] … opt-in: set EQUIVALENCE_ORACLE_ROOT and
EQUIVALENCE_OFFICIAL_ROOT to existing directories; the prior evidence is checked against
docs/reports/prior_evidence_registry.toml`. Commits `1a9eeb87` (relatório + §7) e `d37fb097`
(teste). Passo 3, com o oráculo, árvore commitada:
```
exit 0
1 passed, 1 warning in 22.87s
TEST_NEVER_WRITES
LIVE_INTACT
```
Prova negativa (linha 48 do `DECLARED`, A9/h1 `explained:alvo` → `not_explained`, não
commitada):
```
exit 1
E       AssertionError: --- declared
E         -A9/h1/realized a1_realized out_of_tolerance not_explained
E         +A9/h1/realized a1_realized out_of_tolerance explained:alvo
1 failed, 1 warning in 30.31s
NEGATIVE_PROOF_OK
```
(o `recomputed_matches` passou — a classificação de uma falha é humana —; a igualdade
`DECLARED` = tabela parseada reprovou com o diff visível.)

### 2026-10-23 — [deviation] pós-E5 — testes da barreira `dim_run|<cohort>` (achado médio da revisão) — Claude (executor das Etapas)
**Contexto:** a revisão independente do `0e59b9f9` notou que, com o esperado restrito aos
`run_ids`, a igualdade de `dim_run|<cohort>` virou a única barreira contra "um run some do
silver vivo e as suas unidades somem do esperado junto", e a mutação `if (False and key ==
dim_run)` em `readers.py` l.284 sobrevivia. Só testes (`[8.2/task-11-extra]`); `readers.py` não
muda, então o código executado na E4 é o do `GATE1`.
- `test_check_silver_units_compares_dim_run_and_fact_units`: caso `dim_run|sweep-01` com outro
  digest no laço `changed`;
- `test_official_predictions_are_checked_against_the_judged_silver`: silver sintético sem o run
  `r2` no `dim_run` → `OfficialSilverMismatchError` com `match="dim_run"`.
**Mutação (aplicada, `pytest tests/equivalence/test_audit_table_render.py`, revertida):**
```
m3 if (False and key == dim_run): 2 failed, 23 passed, 1 warning in 7.71s
corrigido: 25 passed, 1 warning in 0.59s
```
`ruff format --check`/`ruff check` e `mypy` verdes; `pytest tests/equivalence/ -rs`: `69 passed,
1 skipped`.

### 2026-10-23 — [deviation] B3 — emenda do A1: meio ulp de float32 com pré-condição (ADR 8.2.0004) — Claude (executor das Etapas)
**Contexto:** decisão humana B3 = opção 2 (registrada na #232; ADR 8.2.0004 e emenda do concept
escritos em paralelo por outra sessão): com o alvo anterior em precisão float32 (`[finding]` da
E4), o A1 passa a usar a precisão efetiva do anterior — **só** quando ela é verificável no dado.
Correção no andaime (`[8.2/task-10-fix]`), antes de qualquer número de modelo:
- `comparisons.py`: `float32_exact(y)` (`float(np.float32(y)) == y`), `a1_float32_tolerance(y_ant)`
  = `float(np.spacing(np.float32(|y_ant|))) / 2`, `A1Rule`/`a1_rule(prior_values)` (pré-condição:
  há y_ant e **todo** y_ant do horizonte é float32-exato) e `a1_check(..., rule=)`: com a
  pré-condição, |Δ| ≤ meio ulp de float32 no ponto; sem ela, a regra de `double` do D13, intacta;
- `comparison_set.py`: `A1_FLOAT32_DEVIATION = "desvio B3 (ADR 8.2.0004): A1 por meio ulp de
  float32"` — rótulo de desvio pós-A1, declarado antes de calcular números de modelo;
- `audit_table.a9_rows`: a pré-condição sobre todos os y_ant do horizonte (não só T∩); a linha A9
  registra `float32_exact=<n>/<total> rule=<float32|double>` e, na tolerância, `meio ulp float32 no
  ponto (<rótulo>)` ou a de `double`.
**Testes e mutações** (aplicadas, `pytest tests/equivalence/`, revertidas):
```
corrigido: 70 passed, 1 skipped
mA float32 sem pré-condição (if rule is not None): 1 failed, 69 passed, 1 skipped
mB tolerância de 1 ulp (sem / 2): 1 failed, 69 passed, 1 skipped
mC pré-condição sempre verdadeira (float32 = n_prior > 0): 3 failed, 67 passed, 1 skipped
```
Pré-condição verdadeira: |Δ| = meio ulp de float32 em 1.0 passa e 1 ulp falha; pré-condição falsa
(`[1.0, 0.1]`) cai na regra de `double`. Os dois testes de render que fixavam o texto da linha A9
passam a trazer `float32_exact=0/4 rule=double` (o sintético não é float32-exato).
**T1:** `ruff format --check`/`ruff check` dos 5 arquivos e `mypy` verdes; `pytest tests/equivalence
tests/architecture -n 4 --dist loadgroup`: `449 passed, 1 skipped`. Pendente: revisão
independente, `make check` extra e `GATE1` novo; depois a E4 desde o passo 1 e a E5 (o `DECLARED`
é regenerado do novo relatório).
Complemento (`[8.2/task-10-extra]`, só testes): `a9_rows` sintético com T∩ float32-exato e um
y_ant fora de T∩ = 0.1 → `rule=double`, `float32_exact=4/5`; mutação mD (pré-condição só sobre
T∩): `2 failed, 69 passed, 1 skipped`; corrigido `71 passed, 1 skipped`.

### 2026-10-23 — [deviation] B3 refinada — critério float32 exato, fail-closed e rótulo propagado — Claude (executor das Etapas)
**Contexto:** a revisão independente de `fb9e29d2` não aprovou: (1) `np.spacing(np.float32(|y|))/2`
é o meio ulp ACIMA; com |y_ant| potência de 2 o ulp para baixo é metade (y_ant = 1.0, y_novo =
1 − 2⁻²⁴ passava); (2) NaN/inf sem tratamento explícito; (4) o rótulo pós-A1 só na linha A9 e sem
o resultado da regra original. Decisão da coordenadora (`[decision:C]`, refinamento dentro da B3,
ADR 8.2.0004). Correção (`[8.2/task-10-fix]`, só andaime):
- critério float32 **exato**: `a1_float32_match(y_novo, y_ant)` = `float(np.float32(y_novo)) ==
  y_ant` (y_ant é o arredondamento ao float32 mais próximo de y_novo: meio ulp com a direção
  certa e empate para o par); `a1_float32_tolerance` removida;
- fail-closed: `float32_exact` exige `math.isfinite(y)`; `a1_float32_match` exige os dois
  finitos; na regra de `double`, NaN/inf já reprovam (`<=` falso);
- `A1Result` ganha `n_out_double` e `max_rel_diff` (informação: o A1 sob a regra original do D13
  e max |Δ|/|y_ant|), impressos na linha A9 (`out_double=… max_rel=…`); tolerância da A9
  `float32(y_novo) == y_ant (<rótulo>)`;
- `a1_rules(prior)` (dono único da regra por horizonte) e `label_post_a1`: toda linha A10/A11 de
  um horizonte sob a regra float32 leva `[desvio B3 (ADR 8.2.0004): …]` na tolerância.
**Testes e mutações** (aplicadas, `pytest tests/equivalence/`, revertidas):
```
corrigido: 74 passed, 1 skipped
mE critério com tolerância acima (spacing/2): 1 failed, 73 passed, 1 skipped
mF isfinite removido da pré-condição: 1 failed, 73 passed, 1 skipped
mF2 isfinite removido do critério: 1 failed, 73 passed, 1 skipped (depois do caso inf/inf)
mG rótulo não propagado: 1 failed, 73 passed, 1 skipped
```
Casos: 1 + 2⁻²⁴ → 1.0 passa (empate ao par); 1 − 2⁻²⁴ reprova (fronteira); 1 − 2⁻²⁵ passa;
1 + 2⁻²³ + 2⁻²⁴ contra 1 + 2⁻²³ reprova (empate ao par); NaN, ±inf fora da pré-condição e do
critério; `compute_rows` sintético rotula as linhas de modelo de h=1 sob float32 e nenhuma sob
`double`. **T1:** ruff e mypy verdes; `pytest tests/equivalence tests/architecture -n 4 --dist
loadgroup`: `453 passed, 1 skipped` (antes do caso inf/inf, que só acrescenta uma asserção;
`tests/equivalence` depois dele: `74 passed, 1 skipped`).
**Texto a reconciliar (fora deste executor):** o ADR 8.2.0004 (Decision 2) e a emenda do D13 no
concept dizem "todo y_ant de T∩"; o implementado é "todo y_ant **do horizonte**" e o critério
exato acima — avisado à coordenadora para o autor dos docs.
Re-verificação: na regra de `double`, `a1_within` aceitava y_ant = inf (`inf <= 2⁻⁵³·inf`);
agora exige os dois finitos (fail-closed). Testes com y_ant = ±inf/NaN na regra de `double`;
mutação mH (guarda removida): `1 failed, 73 passed, 1 skipped`; T1 `tests/equivalence
tests/architecture --dist loadgroup`: `453 passed, 1 skipped`; ruff e mypy verdes.

<!-- END: post-execution -->
