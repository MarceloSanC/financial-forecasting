---
title: Technical — Stage 8.2 — Reprodução da corrida confirmatória e equivalência interna
description: Plano de execução da Stage 8.2 em 10 Tasks inside-out (1 Task = 1 commit) — DTO e mapa de classes da reprodução, comparador puro, leitor da cópia julgada no port, use case de auditoria, subcomando audit-reproduction, driver da reprodução com smoke test, prova de independência de processo, e o andaime da equivalência em tests/equivalence/ — e as Etapas reais E1–E5 na ordem do D10 (registro de hashes, pré-voo em 060537fc, reprodução real, leitura de valores do anterior, teste opt-in e relatórios)
when-use: Consultar durante a Fase 4 (execução) da Stage 8.2; cada Task tem arquivos (lista fechada), testes a escrever primeiro, critério de aceite do concept que cobre e verificação; as Etapas E1–E5 trazem o runbook da parte real, com a ordem fixa do D10 e a tabela "Se falhar"
keywords: [technical, plano de execução, equivalence-audit, reproduction, evaluation, judged-generation, bit-identical, audit-reproduction, driver, prior-evidence, hash-registry, scaffold, opt-in-test, r-bit-commit]
status: draft
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
tasks_count: 10
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
> 6. Depois da Task 10, da auditoria de testes e do 1º `make check`: **Etapas
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
3. **Andaime da equivalência (Tasks 08–10).** Checagem de hash (unit sempre
   ativo) e isolamento (`import-linter` + teste de arquitetura) → regras puras
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
    `main(argv=None) -> int`, que monta `deps = wire_dependencies(Settings(data_root=...))`,
    `source = TomlPreregistrationSource(root=Path("config/preregistration"))` e
    `snapshot = deps.run_confirmatory_evaluation_for(cohort, "cpu")._environment.snapshot`
    (acesso privado declarado — ADR 8.2.0001 item 7);
  - ordem: resolver a revisão → foto (`snapshot()`) → `--check`: imprime a foto
    como `document_bytes` no stdout e sai 0, **nada gravado**; senão cria
    `reproduction/`, grava `environment.json` = `document_bytes(foto)` **antes**
    do refresh → `refresh_gold(refresh_command_from(plan, ref))` → status ≠
    `COMPLETED` → stderr + exit 1, sem scorecard → `build_confirmatory_scorecard(
    BuildConfirmatoryScorecardCommand(name, revision, ref))` → grava
    `scorecard.json` = `document_bytes(scorecard.as_mapping())`;
  - stdout: `reproduction <ref>: refresh <STATUS> tables <n>` e
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
  `HorizonReports`, `CalibrationTable`), conferidas na Task 09 e gravadas como
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
| 1 | 10 (depois da auditoria de testes com mutação real e do Checkpoint C final) | Pré-corrida: muda port consumido pelo composition root e pela 8.3 (`read_judged_generation`), o composition root e o `cli.py` (Task 05), o `.importlinter` e um teste de arquitetura (Task 08) — o T1 não roda `tests/architecture/` nem os scripts de gate. O driver que a E3 executa e o `audit-reproduction` que a julga têm de estar verdes como no CI **antes** da E2: uma correção do driver depois da E3 obriga a re-reproduzir (~15 min de refresh e a evidência refeita). Um ponto antes (depois da 05) não se paga: as Tasks 06–10 não constroem sobre um contrato que o gate pudesse invalidar além do que o T1 delas já exercita. |
| 2 | saída (depois da E5) | Gate de saída (Passo 10): a E1/E5 acrescentam `tests/equivalence/comparison_set.py` e a tabela declarada do teste opt-in (lint, mypy fora de escopo, coleta e skip no CI), o registro e os relatórios. |

Nas demais Tasks o gate é o T1 da Task. Vermelho no ponto 1 → `fix(<escopo>): …
[8.2/task-NN-fix]` e novo `make check` (3º ponto, justificado: só o commit verde
pode ser o do driver da E3).

### Estrutura de pastas afetada

```
scripts/reproduce_judged_generation.py                                 # novo (T06)
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
├── unit/tooling/test_reproduce_judged_generation.py                   # T06
├── contract/features/evaluation/test_judged_generation_store_contract.py   # T03
├── integration/features/evaluation/{test_audit_reproduction_cli.py,
│                                    test_reproduction_process_independence.py}   # T05, T07
├── architecture/test_prior_evidence_isolation.py                      # T08
└── equivalence/                                                       # andaime (T08–T10, E1, E5)
    ├── __init__.py, prior_evidence.py, comparison_set.py, alignment.py,
    ├── comparisons.py, readers.py, audit_table.py
    └── test_prior_evidence_registry_check.py, test_scaffold_comparisons.py,
        test_audit_table_render.py, test_official_vs_prior_evidence.py
.importlinter                                                          # contrato src ↛ tests (T08)
docs/LAYOUT.md                                                         # tests/equivalence/ no §2 (T08)
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
  `test_tampered_judged_copy_exit_2`; `test_judged_toml_with_other_digest_exit_2`;
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

### Task 06 — Driver da reprodução e smoke test

- **Arquivos a criar:**
  - `scripts/reproduce_judged_generation.py`
  - `tests/unit/tooling/test_reproduce_judged_generation.py`
- **Testes primeiro** (deps falsas: objeto com `hasher`, `refresh_gold`,
  `build_confirmatory_scorecard`, `run_confirmatory_evaluation_for` devolvendo um
  objeto com `_environment.snapshot`; `source` = `InMemoryPreregistrationSource`;
  registro de chamadas em ordem): `test_calls_snapshot_then_refresh_then_scorecard`;
  `test_writes_environment_before_refresh_and_document_bytes_of_scorecard`
  (bytes = `document_bytes(...)` nos caminhos fixos);
  `test_check_mode_prints_snapshot_and_writes_nothing_nor_refreshes`;
  `test_refuses_data_root_under_data_cohorts` (também via `..` e link relativo
  resolvido); `test_refuses_existing_gold_or_reproduction[gold|reproduction]`
  (nos dois modos, antes do wiring); `test_refresh_not_completed_exits_1_without_scorecard`;
  `test_snapshot_error_propagates_before_any_write` (ex.: `MissingImageIdError`);
  `test_main_wires_snapshot_from_run_confirmatory_evaluation_for_cpu` (com `wire`
  injetado: `run_confirmatory_evaluation_for(cohort, "cpu")`).
- **O que fazer:** como no §1 (argumentos, recusas, ordem, saídas). Docstring do
  módulo: o contrato operacional do concept §4 e o porquê do acesso privado.
- **Critério de aceite:** A3b (smoke test).
- **Verificação (T1):** `pytest tests/unit/tooling/test_reproduce_judged_generation.py -q --no-cov` (+ ruff do script)
- **Commit:** `feat(tooling): driver da reprodução da geração julgada [8.2/task-06]`

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

### Task 08 — Andaime: checagem de hash do registro e isolamento da evidência anterior

- **Arquivos a criar:**
  - `tests/equivalence/__init__.py` *(pacote)*
  - `tests/equivalence/prior_evidence.py`
  - `tests/equivalence/test_prior_evidence_registry_check.py`
  - `tests/architecture/test_prior_evidence_isolation.py`
- **Arquivos a modificar:**
  - `.importlinter` (contrato `forbidden` `src-no-tests`: `financial_forecasting` ↛ `tests`)
  - `docs/LAYOUT.md` (§2: `tests/equivalence/` — andaime interino da 8.2, fora do
    `src/`, ADR 8.2.0003)
- **Testes primeiro** (sempre ativos, `tmp_path` com Parquet sintético):
  `test_registered_files_matching_pass_and_return_paths`;
  `test_altered_byte_fails`; `test_missing_registered_file_fails`;
  `test_row_count_or_column_type_other_than_registry_fails` (footer);
  `test_unregistered_file_in_root_is_never_read` (o leitor recusa caminho fora do
  registro); `test_malformed_registry_fails` (sha não hex, `rows` não inteiro,
  `path` absoluto ou com `..`); arquitetura:
  `test_no_src_module_reads_prior_evidence_or_imports_the_scaffold` (AST de
  `src/`: nenhum import de `tests`, nenhum literal com `data/analytics` ou
  `phase_b`), `test_isolation_detector_flags_violations` (o detector não é vácuo).
- **O que fazer:** `load_registry(path) -> PriorEvidenceRegistry`;
  `verify_registered_files(*, oracle_root, registry) -> Mapping[str, Path]`
  (sha256 por streaming, linhas e tipos pelo footer — `pyarrow.parquet.read_schema`
  / `read_metadata`, sem ler valor); `PriorEvidenceHashError(AssertionError)` com a
  lista de divergências; `REGISTRY_PATH` = `docs/reports/prior_evidence_registry.toml`.
- **Critério de aceite:** A13 (função de checagem com unit sempre ativo), A14,
  base do A1.
- **Verificação (T1):** `pytest tests/equivalence/test_prior_evidence_registry_check.py tests/architecture/test_prior_evidence_isolation.py -q --no-cov` e `uv run --no-sync lint-imports`
- **Commit:** `test(evaluation): checagem de hash e isolamento da evidência anterior [8.2/task-08]`

---

### Task 09 — Andaime: conjunto de comparação, interseção, A1, A2 e sentido (regras puras)

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
  regra D7, `COMMON_BASELINES: tuple[...] = ()` — preenchido só na E1 — e as
  constantes do lado novo lidas do código, com o caminho na docstring);
  `alignment.py` (seleção D7, T∩ por horizonte, agregação de seeds);
  `comparisons.py` (A1, A2 com tolerância, células de sentido, `RawStatus` =
  `within_tolerance | out_of_tolerance | not_realizable | empty_intersection |
  same_sense | divergent_sense`). As métricas do lado novo e de m_A usam os
  serviços de domínio existentes (`pinball_score`, `coverage_series`,
  `wilson_band`); nenhuma métrica nova (concept §12 item vi).
- **Critério de aceite:** A9, A10, A11 (regras), D7, D8, D12, D13.
- **Verificação (T1):** `pytest tests/equivalence/test_scaffold_comparisons.py -q --no-cov`
- **Commit:** `test(evaluation): regras do andaime da equivalência sobre dado sintético [8.2/task-09]`

---

### Task 10 — Andaime: leitores, tabela renderizada e teste opt-in

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
  bloco 08–10 por subagente e a **auditoria de testes** (PROMPT-stage §AUDITORIA
  DE TESTES; subagente que não escreveu os testes) com **mutação real** —
  igualdade por bits no `compare_reproduction` (trocar por `==` de float),
  conjunção do `bit_identical` (tirar o `expected_result_digest`), conferência do
  `CONTENTS.sha256` no `read_judged_generation` (pular o `find`), recusa
  `data/cohorts` e ordem foto → refresh no driver, limiar de A1 (2⁻⁵² no lugar de
  2⁻⁵³) —, editando, rodando o T1 dos arquivos afetados e revertendo, saída
  colada em §7. Achado → `test(<escopo>): cobrir <X> [8.2/task-NN-extra]` **antes**
  do ponto 1 (o driver da E3 é o do commit verde).
- **Gate T3 — ponto 1 do plano:** `make check` (comando literal do §1).
- **Commit:** `test(evaluation): teste opt-in da equivalência e tabela do relatório [8.2/task-10]`

---

### Etapas reais E1–E5 — ordem fixa do D10

Não são Tasks numeradas: produzem commits de runbook (registro, §7, relatórios,
tabela declarada). Rodam **depois** do ponto 1 verde, com a árvore limpa, **na
ordem E1 → E2 → E3 → E4 → E5**; nenhuma Etapa começa sem o commit da anterior
(quando ela tem commit). Toda medição vai para §7 (`[measurement]`;
`[finding]` quando a tabela "Se falhar" manda parar).

**Sessão que executa** (modelo da Etapa R da 8.1). Cada chamada de shell é um
processo novo (variáveis não persistem) e tem teto de 10 min: (i) todo valor
calculado vai para `$SCRATCH/etapa-82.env`, e **todo** bloco começa com
`set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1`;
(ii) a reprodução (E3) roda num container **destacado** `ff82-repro`, esperado por
`docker wait` em segundo plano (`run_in_background`, notificação ao sair), com
`docker ps` e `docker logs --tail`; (iii) o container roda pelo **id** da imagem,
nunca pela tag `:dev`; (iv) prefixar todo `docker run` com `MSYS_NO_PATHCONV=1`;
(v) scripts Python de runbook são gravados com a ferramenta Write no
`$SCRATCH` (não heredoc: o Bash colapsa `\`) e montados `:ro`.

**E0 — Variáveis (host, Git Bash; uma vez).**
```bash
set -eu
SCRATCH=<scratchpad da sessão, caminho absoluto literal, fora do repo>
STAMP=$(date -u +%Y%m%d-%H%M%S)
cat > "$SCRATCH/etapa-82.env" <<EOF
SCRATCH=$SCRATCH
STAMP=$STAMP
WT=feat-232-8-2-equivalence-audit
WTH=/c/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/feat-232-8-2-equivalence-audit
WTD=C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/feat-232-8-2-equivalence-audit
MAINH=/c/Users/Marcelo/Documents/Code/financial-forecasting
MAIND=C:/Users/Marcelo/Documents/Code/financial-forecasting
SCRATCHD=<o mesmo scratchpad em forma C:/...>
REPRO=repro-060537fc
REPROH=/c/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/repro-060537fc
REPROD=C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/repro-060537fc
DISPH=/c/Users/Marcelo/Documents/Code/financial-forecasting/data/reproductions/aapl-r3-$STAMP
DISPD=C:/Users/Marcelo/Documents/Code/financial-forecasting/data/reproductions/aapl-r3-$STAMP
JUDGED_COMMIT=060537fc7069b38a318bb5cf839d84b7767b1b4f
BASE=64b8a17dfcec6694b03d14b2ea2b39da9e624291
IMAGE_ID=sha256:b69a7620e7bd8449369bde2f46e903c5f46c25e9efb3597f452af3272e0a8f45
REF=aapl_confirmatory-r3-00fd83d9cd39
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

**E1 — Registro de hashes da evidência anterior (A1; D5, D10 passo 1, D11, D12 a).**
Antes de qualquer valor. Só footer, contagens e rótulos de definição.

1. *Rótulo de modelo do `gold_oos_consolidated`* (metadado): listar, com o
   container da imagem e `data/analytics` `:ro`, os valores **distintos** de
   `model_version_x` e `model_version_y` nas linhas `parent_sweep_id =
   phase_b_confirmatorio_20260524`, `split = test` (só rótulos; nenhuma coluna de
   valor); fixar em `comparison_set.MODEL_LABEL_COLUMN` a coluna que traz o
   candidato `BTSF` e os três baselines de D-M2.
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
3. *Registro.* Script Write-gravado `$SCRATCH/registry.py` (stdlib + `pyarrow`;
   para cada arquivo do conjunto lido do §1 e de 2(b): sha256 por streaming,
   `read_metadata().num_rows`, `read_schema()` → nome/tipo; imprime o TOML do §1) e:
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   MSYS_NO_PATHCONV=1 docker run --rm $RES -v $MAIND/data/analytics:/oracle:ro -v $SCRATCHD:/scratch:ro -v financial-forecasting_app-venv:/app/.venv -w /app "$IMAGE_ID" /app/.venv/bin/python -I /scratch/registry.py /oracle > "$WTH/docs/reports/prior_evidence_registry.toml"
   grep -c '^\[\[file\]\]' "$WTH/docs/reports/prior_evidence_registry.toml"
   ```
   Conferir cada `sha256` do registro contra a tabela D-M1 do concept (comando
   `grep` por sha, um por arquivo) → `REGISTRY_EQUALS_DM1`; e a checagem do
   andaime sobre o oráculo real:
   ```bash
   MSYS_NO_PATHCONV=1 docker run --rm $RES $HMOUNTS -v $MAIND/data/analytics:/oracle:ro $HENVS "$IMAGE_ID" sh -c "$PRE; uv run --no-sync python -c \"from pathlib import Path; from tests.equivalence.prior_evidence import REGISTRY_PATH, load_registry, verify_registered_files as v; print('REGISTRY_OK', len(v(oracle_root=Path('/oracle'), registry=load_registry(REGISTRY_PATH))))\""
   ```
4. *Commit próprio* (registro + `comparison_set.py` + §7):
   `docs(evaluation): registro de hashes da evidência anterior antes da leitura [8.2/--]`.
   Anotar `REGISTRY_COMMIT` no `etapa-82.env`. Nenhum commit anterior da branch
   contém valor do anterior (conferido no A1 por `git log -p origin/develop..$REGISTRY_COMMIT`
   sem os sha/valores de D-M1 além de schema e contagens).

**E2 — Pré-voo da reprodução (A2, A3b, A4, A7; sem refresh).**

1. *Árvore de `060537fc`* — **worktree destacada** em diretório temporário, sem
   branch nova:
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   test ! -e "$REPROH"
   git -C "$WTH" worktree add --detach "$REPROH" "$JUDGED_COMMIT"
   test "$(git -C "$REPROH" rev-parse HEAD)" = "$JUDGED_COMMIT" && echo TREE_AT_JUDGED
   cp "$MAINH/.env" "$REPROH/.env"; git -C "$REPROH" check-ignore -q .env && echo ENV_IGNORED
   sha256sum "$REPROH/.env" | cut -d' ' -f1 > "$SCRATCH/dotenv.sha"; test -z "$(git -C "$REPROH" status --porcelain)" && echo TREE_CLEAN
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
2. *Imagem e Docker:* `docker image inspect --format '{{.Id}}' "$IMAGE_ID"` =
   `$IMAGE_ID` (`SAME_IMAGE`); `docker ps --filter name=ff82 -q` vazio; `uname -r`
   do container = `6.18.54.1-microsoft-standard-WSL2` (o `env.platform` da `started`).
3. *Backup de entrada e restauração no descartável:*
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   test "$(sha256sum "$BK.sha256sum" | cut -d' ' -f1)" = "$(grep '^input_backup_sha256' "$WTH/config/preregistration/aapl_confirmatory-r3.judged.toml" | cut -d'"' -f2)" && echo LISTING_IS_REGISTERED
   (cd "$BK" && sha256sum -c --quiet "$BK.sha256sum") && echo BACKUP_OK
   test ! -e "$DISPH"; mkdir -p "$DISPH" && cp -a "$BK/." "$DISPH/"
   (cd "$DISPH" && sha256sum -c --quiet "$BK.sha256sum") && echo RESTORE_OK
   ls -a "$DISPH"      # bronze inference processed raw silver — sem gold/, judged/, reproduction/
   ```
4. *Partição viva antes (I1):*
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   sha256sum "$P/current/MANIFEST.json" "$P/judged/ATTEMPTS.jsonl" "$P/judged/$REF/CONTENTS.sha256" | tee "$SCRATCH/live-before.sha"
   ```
   Esperado `56d3ee1c…`, `320def2b…`, `96c05413…` (I1).
5. *Ambiente no container da reprodução:*
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   MSYS_NO_PATHCONV=1 docker run --rm $RES $RMOUNTS $RENVS "$IMAGE_ID" sh -c "$PRE; git rev-parse HEAD; git status --porcelain; cat /sys/fs/cgroup/cpu.max; uname -r; uv pip freeze --python /app/.venv/bin/python | sha256sum" | tee "$SCRATCH/env-preflight.txt"
   ```
   Esperado: `060537fc…`, status vazio, `600000 100000` (6 CPUs), o kernel do item 2,
   e o sha256 do freeze (registrado; a 8.1 não registrou o seu — vale como foto,
   não como comparação).
6. *Driver `--check` em `060537fc`* (wiring + foto, sem refresh; prova também que o
   driver só usa nomes que existem em `060537fc`):
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   MSYS_NO_PATHCONV=1 docker run --rm $RES $RMOUNTS $RENVS "$IMAGE_ID" sh -c "$PRE; $DRIVER --check" > "$SCRATCH/check.json"
   ls -a "$DISPH"      # continua sem gold/ e sem reproduction/
   ```
   Comparação chave a chave com a linha `started` (script Write-gravado
   `$SCRATCH/env_equal.py`, stdlib: lê a linha `phase = started` do
   `ATTEMPTS.jsonl` vivo e a foto; exige `commit` igual, `code_dirty` e
   `preregistration_dirty` = `"false"`, o conjunto de chaves `code.*` igual ao de
   `code` e o de `env.*` igual ao de `environment`, e cada valor igual; imprime
   `ENV_EQUAL` ou a lista de chaves divergentes):
   ```bash
   python "$SCRATCH/env_equal.py" "$P/judged/ATTEMPTS.jsonl" "$SCRATCH/check.json"   # ENV_EQUAL
   ```
7. *R-BIT-COMMIT (A7, D1)* — no container 3.12 do HEAD, script Write-gravado
   `$SCRATCH/ast_equal.py`: auto-teste (docstrings diferentes ⇒ igual; `x = 1` ×
   `x = 2` ⇒ diferente; f-strings adjacentes unidas ⇒ igual), depois, para cada
   arquivo de `git diff --name-only --diff-filter=M $JUDGED_COMMIT $BASE -- src/`,
   `ast.dump` das duas versões (`git show <rev>:<arquivo>`) com o docstring removido
   do corpo de todo `Module`/`ClassDef`/`FunctionDef`/`AsyncFunctionDef`
   (substituído por `pass` se o corpo esvaziar); arquivos A/D/R do diff listados à
   parte (esperado: nenhum):
   ```bash
   MSYS_NO_PATHCONV=1 docker run --rm $HMOUNTS -v $SCRATCHD:/scratch:ro $HENVS "$IMAGE_ID" sh -c "$PRE; python3 --version; /app/.venv/bin/python -I /scratch/ast_equal.py $JUDGED_COMMIT $BASE" | tee "$SCRATCH/ast-equal.txt"
   git -C "$WTH" diff --name-only "$BASE"..HEAD -- src/ | tee "$SCRATCH/src-8.2.txt"
   ```
   Esperado: 15 arquivos `AST_EQUAL`, `ast_diff 0`. A lista `src-8.2.txt` é a dos
   acréscimos da 8.2 (Tasks 01–05), cada um justificado no relatório como fora do
   caminho refresh/scorecard (o `ParquetGoldStore` ganha leitura e um helper
   extraído da `read_generation`, sem mudar a escrita; o composition root e o
   `cli.py` ganham só o wiring do subcomando).
8. *Pré-checagem de processo (A3b):* citar o T1 verde da Task 07 e o ponto 1
   (`test_reproduction_process_independence.py`).
9. **Commit** da evidência do pré-voo em §7 (`[measurement] E2`, saídas literais
   dos itens 1–8): `docs(evaluation): pré-voo da reprodução em 060537fc [8.2/--]`.

**E3 — Reprodução real e auditoria (A3, A4, A7, A8).**

1. *Corrida destacada* (~15 min: o refresh da 8.1 levou 13,9 min):
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   test -z "$(docker ps -a --filter name=ff82-repro -q)"
   MSYS_NO_PATHCONV=1 docker run -d --name ff82-repro $RES $RMOUNTS $RENVS "$IMAGE_ID" sh -c "$PRE; $DRIVER"
   ```
   Em segundo plano (`run_in_background`): `docker wait ff82-repro > "$SCRATCH/repro.exit"`.
   Enquanto roda: `docker ps --filter name=ff82`, `docker logs --tail 5 ff82-repro`.
   Ao sair:
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   docker logs ff82-repro > "$SCRATCH/repro.out" 2> "$SCRATCH/repro.err"; cat "$SCRATCH/repro.exit"   # 0
   docker rm ff82-repro
   grep "^reproduction " "$SCRATCH/repro.out"   # refresh COMPLETED tables 19; scorecard sha256 <hex>
   ls "$DISPH/reproduction"                      # environment.json scorecard.json
   python "$SCRATCH/env_equal.py" "$P/judged/ATTEMPTS.jsonl" "$DISPH/reproduction/environment.json"   # ENV_EQUAL
   cmp "$SCRATCH/check.json" "$DISPH/reproduction/environment.json" && echo SNAPSHOT_SAME_AS_CHECK
   test -z "$(find "$DISPH" -name judged -o -name ATTEMPTS.jsonl)" && echo NO_JUDGMENT_IN_DISPOSABLE
   ```
   Tempos por etapa: linhas `_timed` do `repro.err`.
2. *Auditoria pelo HEAD* (só leitura nas duas raízes):
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   MSYS_NO_PATHCONV=1 docker run --rm $RES $HMOUNTS -v $MAIND/data/cohorts/aapl:/judged:ro -v $DISPD:/reproduced:ro $HENVS "$IMAGE_ID" sh -c "$PRE; uv run --no-sync python -m financial_forecasting.cli audit-reproduction --judged-data-root /judged --reproduced-data-root /reproduced --preregistration aapl_confirmatory --revision 3 --preregistration-ref $REF" > "$SCRATCH/audit.out"; echo "exit $?"
   head -2 "$SCRATCH/audit.out"   # bit_identical true; os três result_digest = 7c7940d4…
   ```
3. *Partição viva depois (I1, A4):*
   `sha256sum -c "$SCRATCH/live-before.sha"` → `LIVE_INTACT` (os três `OK`).
4. *Relatório* `docs/reports/reproduction_audit.md`: o claim — (a) afirmado
   (reprodução bit a bit no commit e no ambiente registrados, a partir dos dados
   persistidos, sem re-treino), (b) citado da 7.1 (predições a partir dos
   checkpoints), (c) **não executado** (um único ambiente, D4) —; identidade
   (`silver_content.digest`, `dataset_fingerprint`, ref, partição); os três
   `result_digest`; a tabela por classe e por tabela do `audit.out` (contagens,
   diferentes, max |Δ| também quando zero); o scorecard sem proveniência; o
   ambiente (imagem, `cpu.max`, kernel, sha256 do freeze e do `.env`, `ENV_EQUAL`
   chave a chave); o R-BIT-COMMIT (lista `060537fc..64b8a17d` com `AST_EQUAL` e a
   lista `64b8a17d..HEAD` justificada) com a declaração de que o claim é o da
   execução em `060537fc`; a partição viva antes/depois; os comandos. Entrada
   `[measurement] E3` em §7. Commit
   `docs(evaluation): relatório da reprodução bit a bit da geração julgada [8.2/--]`.
5. *Limpeza da árvore temporária:* `git -C "$WTH" worktree remove "$REPROH"` (com
   arquivos ignorados — `.env`, `artifacts/`, `__pycache__` —: `rm -rf "$REPROH"` e
   `git -C "$WTH" worktree prune`); o `data_root` descartável fica em
   `data/reproductions/` (git-ignorado) até o merge, como evidência.

**E4 — Leitura de valores da evidência anterior e comparações (A9–A11; D10 passo 3).**

Só depois do commit do E3 (`git log` mostra registro → pré-voo → relatório de
reprodução).

1. *Tabela recomputada:*
   ```bash
   set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-82.env" || exit 1
   MSYS_NO_PATHCONV=1 docker run --rm $RES $HMOUNTS -v $MAIND/data/analytics:/oracle:ro -v $MAIND/data/cohorts/aapl:/official:ro $HENVS -e EQUIVALENCE_ORACLE_ROOT=/oracle -e EQUIVALENCE_OFFICIAL_ROOT=/official "$IMAGE_ID" sh -c "$PRE; uv run --no-sync python -m tests.equivalence.audit_table" > "$SCRATCH/equivalence.md"; echo "exit $?"
   sha256sum -c "$SCRATCH/live-before.sha"   # a leitura não tocou a partição viva
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
   motivo). Entrada `[measurement] E4` em §7 com o comando e o exit.

**E5 — Teste opt-in e commits dos relatórios (A12, A13).**

1. Copiar para `DECLARED` do `test_official_vs_prior_evidence.py` a classificação
   do relatório (mesmas linhas).
2. Com o oráculo (comando do E4 trocando `python -m tests.equivalence.audit_table`
   por `pytest tests/equivalence/test_official_vs_prior_evidence.py -rs -q --no-cov`)
   → `1 passed`; sem as variáveis (T1 normal) → `1 skipped` com o motivo e o
   caminho do registro. Prova negativa: com uma linha de `DECLARED` alterada à mão
   (não commitada) → falha mostrando o diff; revertida.
3. Commits: `docs(evaluation): relatório da equivalência com a evidência anterior [8.2/--]`
   (relatório + §7) e `test(evaluation): tabela declarada da equivalência [8.2/--]`
   (o teste). Depois, o **ponto 2** do plano (`make check`), o roadmap e
   `stage 8.2: complete`.

**Se falhar** (nunca editar silver, gold, cópia julgada ou `ATTEMPTS.jsonl` à mão;
nunca montar a partição viva com escrita; nunca re-julgar):

| Sintoma | Ação |
|---|---|
| E1: sha256 de um arquivo ≠ D-M1 | `[finding]` e **parar** (o oráculo mudou desde a medição; nada é lido) |
| E1: fonte de definição de baseline ausente | zero comuns, tabela por baseline vazia registrada (D12 a); o resto segue |
| E2: `git worktree add` recusado (hook ou caminho existente) | conferir `git worktree list`; caminho existente de sessão anterior → `git worktree prune` e outro `REPRO`; recusa do hook → registrar e repetir pelo checkout principal (`git -C "$MAINH" worktree add --detach …`, sem branch) |
| E2: `BACKUP_OK`/`RESTORE_OK`/`LISTING_IS_REGISTERED` falha | não restaurar; `[finding]` e **parar** (entrada congelada — ADR 8.1.0003 item 6b) |
| E2: imagem ausente, `TREE_CLEAN` falha, `ENV_EQUAL` com chave divergente, kernel ≠ | não rodar como R-BIT; `[finding]` (diagnóstico de ambiente, não de código); parada para decisão (concept §6) |
| E2: `--check` com `ImportError`/`AttributeError` | o driver usa nome ausente em `060537fc`: `fix` do driver no HEAD (`[deviation]`), `make check` extra justificado, repetir E2 |
| E2: `AST_DIFF` num arquivo | `[finding]` no relatório (a reprodução em `060537fc` continua sendo o claim; o diff só deixa de confirmar a base) |
| E3: exit ≠ 0 / `refresh` ≠ `COMPLETED` | logs; `[finding]`; nada é apagado; diagnóstico antes de repetir (repetição = novo `data_root` descartável, mesmo E2) |
| E3: exit 137 / OOM | `docker inspect ff82-repro --format '{{.State.OOMKilled}}'`; repetir com mais `--memory` (memória não é chave do I4), `[deviation]` |
| E3: identidade desigual (I3) | `bit_identical = false`, "outra entrada"; `[finding]` e diagnóstico (§1); nada comparado como resultado |
| E3: `audit-reproduction` exit 1 com I3–I4 satisfeitas | `[finding]` R-BIT, **parada**; diagnóstico pré-declarado do §1 na ordem, cada passo em §7; nenhuma tolerância; a geração julgada não é trocada (doc §4.6) |
| E3: `JudgedGenerationTamperedError` | restaurar a cópia do backup `judged-…` com `sha256sum -c` e `[deviation]` (ADR 8.1.0004 item 2c); nunca re-julgar |
| E3/E4: `LIVE_INTACT` falha | `[finding]` e **parar**: algo escreveu na partição viva; restaurar dos backups conferidos e `[deviation]` |
| E4: `PriorEvidenceHashError` | o oráculo mudou depois do registro: `[finding]`, **parar** (nunca regenerar o registro) |
| E4: `dataset_fingerprint` do `ReadTrainingGrid` ≠ `00e4406d…` | `[finding]` e parar (a partição viva não é a entrada julgada) |
| E4: A1 fora | D13 (diagnóstico na ordem), categoria "alvo", comparação de modelo daquele horizonte para; regra não afrouxada |
| E5: opt-in falha com o oráculo | corrigir a cópia de `DECLARED` (nunca o cálculo para caber); se o recomputado mudou entre E4 e E5, `[finding]` |

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
- [ ] 10 Tasks commitadas, cada uma com o seu T1 verde; Checkpoints C nas
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
01 ─► 02 ─► 04 ─► 05 ─► 06 ─► 07 ─► 08 ─► 09 ─► 10 ─[make check 1]─► E1 ─► E2 ─► E3 ─► E4 ─► E5 ─[make check 2]
      03 ──┘
```

- 01 antes de 02 (DTO e mapa); 02 e 03 antes de 04 (comparador e leitor); 04
  antes de 05; 05 antes de 07 (o teste chama o subcomando); 06 antes de 07 (o
  teste chama o driver); 08 antes de 09–10 (registro e checagem); 09 antes de 10;
  10 antes da E1 (o `comparison_set.py` existe para receber os comuns); E1 → E5 na
  ordem do D10.
- **Checkpoint C** (revisão do bloco por subagente, sem gate de suíte) depois de
  03, 05, 07 e 10; a **auditoria de testes** com mutação real fecha antes do
  ponto 1 (Task 10), nunca depois da E3.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| O `import-linter` não aceita `financial_forecasting` como fonte de um contrato `forbidden` contra o pacote externo `tests` | ficar só com o teste de arquitetura da Task 08 (AST + literais) e `[deviation]` com a mensagem do `lint-imports`; A14 por grep + teste |
| Um builder grava coluna não prevista no mapa | o comparador ergue na Task 07 (sintético) ou na E3 (real): acrescentar a classe no mapa com a regra do concept §4 (`[deviation]`); nunca fallback por tipo |
| Mundo sintético da Task 07 sem alguma das 19 tabelas não vazia | a completude cobre as não vazias e a unit cobre o schema; registrar as vazias na mensagem |
| `ReadTrainingGrid`/leitor silver exigem escrita (lock, cache) sobre a montagem `:ro` | montar o adaptador com o parâmetro que desliga a escrita, ou ler os mesmos Parquet pelo `ParquetMedallionStore` de leitura; `[deviation]` |
| Bind mount de arquivo único (`/driver/…`) não aparece no Docker Desktop | montar `$WTD/scripts:/driver:ro` (o diretório; fora dos caminhos do probe do mesmo jeito), `[deviation]` |
| Volume `financial-forecasting_app-venv` re-sincronizado depois da 8.1 com outra versão de lib | `ENV_EQUAL` falha nas chaves `env.lib.*`/`env.probe.*`: diagnóstico de ambiente, parada (concept §6); nunca `uv sync` para "consertar" sem decisão |
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
| A1 | Registro antes da leitura | 08, E1 | `test_prior_evidence_registry_check.py`; `REGISTRY_EQUALS_DM1`, `REGISTRY_OK`; commit do registro antes do E4 no `git log` |
| A2 | Entrada e ambiente da reprodução | E2 | `LISTING_IS_REGISTERED`, `BACKUP_OK`, `RESTORE_OK`, `TREE_CLEAN`, `SAME_IMAGE`, `ENV_EQUAL`, `cpu.max`, sha256 do freeze em §7 |
| A3 | Reprodução real bit a bit | 01, 02, 04, 05, E3 | `test_compare_reproduction.py`; `test_audit_reproduction.py`; `test_audit_reproduction_cli.py`; `audit.out` (exit 0, `bit_identical true`, `7c7940d4…` × 3) e `reproduction_audit.md` |
| A3b | Driver testado | 06, 07, E2 | `test_reproduce_judged_generation.py` (lista da Task 06); `test_reproduction_process_independence.py::test_reproduced_result_digest_is_independent_of_hash_seed`; `--check` em `060537fc` (`check.json`, `ENV_EQUAL`) |
| A4 | Partição viva intocada | 05, 07, E2, E3 | `test_nothing_written_in_either_root`; `test_reproduced_root_has_no_judged_dir_nor_attempts`; `live-before.sha` + `LIVE_INTACT`; `NO_JUDGMENT_IN_DISPOSABLE` |
| A5 | Leitor da cópia julgada | 03 | `test_judged_generation_store_contract.py` (lista da Task 03); `check_port_coverage`/`check_fake_parity` no ponto 1 |
| A6 | Comparador testado | 01, 02, 07 | `test_reproduction_comparison_dtos.py::test_every_schema_column_has_a_declared_class`; `test_compare_reproduction.py` (lista da Task 02); `test_every_stored_column_has_a_declared_class` |
| A7 | R-BIT-COMMIT registrado | E2, E3 | `ast-equal.txt` (15 `AST_EQUAL`, auto-teste), `src-8.2.txt` justificada no `reproduction_audit.md` |
| A8 | Claim declarado | E3 | seção de claim do `reproduction_audit.md` ((a) afirmado, (b) citado, (c) não executado) |
| A9 | EQ-MUST A1 | 09, E4 | `test_scaffold_comparisons.py::test_a1_*`; tabela A9 do `equivalence_audit.md` (T∩, fora, max \|Δ\| por h) |
| A10 | EQ-MUST A2 | 09, 10, E4 | `test_a2_tolerance_is_max_of_r2_and_storage_precision`, `test_a2_not_realizable_*`; tabela A10 com a classificação |
| A11 | Tabela de sentido por horizonte | 09, 10, E4 | `test_dm_sign_*`, `test_dm_rejection_*`, `test_side_of_nominal_*`, `test_sense_cell_*`; tabela A11 (candidato × candidato sempre; por baseline comum ou vazia registrada) |
| A12 | Relatório de equivalência | 10, E4, E5 | `test_audit_table_render.py`; `equivalence_audit.md` com hashes, contexto, A9–A11, findings, inventário e aposentadoria |
| A13 | Teste fora do CI | 08, 10, E5 | `test_prior_evidence_registry_check.py` (sempre ativo); opt-in `SKIPPED` com `-rs` (T1 da 10 e §3) e `1 passed` com o oráculo (E5) |
| A14 | Isolamento do anterior | 08 | `test_prior_evidence_isolation.py`; contrato `src-no-tests` no `lint-imports` (ponto 1) |
| A15 | Roadmap e gates | 10, saída | pontos 1 e 2 do plano (saídas coladas, cobertura por arquivo); roadmap no fechamento |

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

<!-- END: post-execution -->
