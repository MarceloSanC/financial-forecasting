---
title: Concept — Stage 8.2 — Reprodução da corrida confirmatória e equivalência interna com a evidência anterior
description: (i) reprodução bit a bit da geração julgada da 8.1 no commit dela (060537fc), a partir do backup de entrada restaurado num data_root descartável, com RefreshGold e BuildConfirmatoryScorecard direto e comparação por classe contra a cópia julgada; (ii) auditoria interna de equivalência com a evidência anterior congelada por hash, na interseção comum, com tolerância numérica no alvo e no código de métrica e tolerância de sentido nos números do modelo, por um andaime fora do src/ e um teste opt-in fora do CI
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; antes de rodar a reprodução ou ler qualquer valor da evidência anterior; ao consumir a cópia julgada na 8.3; ao questionar por que a reprodução roda em 060537fc e não no HEAD, por que não passa pelo RunConfirmatoryEvaluation, ou por que o teste de equivalência pula no CI
keywords: [concept, reproduction, equivalence, evaluation, judged-generation, bit-identical, r-bit, r-bit-commit, eq-hash, eq-inter, eq-must, eq-desc, eq-expl, eq-andaime, prior-evidence, oracle, scaffold, result-layer]
status: draft
created_at: 2026-10-23
updated_at: 2026-10-23
stage_id: 8.2-equivalence-audit
stage_title: Reprodução da corrida confirmatória e equivalência interna
step_id: 8
step_title: Reprodução, equivalência e relatório
depends_on: [8.1-confirmatory-run]
---

# Concept — Stage 8.2 — Reprodução da corrida confirmatória e equivalência interna

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.
>
> **A teoria não é reaberta aqui.** As regras de reprodução (R-BIT,
> R-BIT-COMMIT, R-ENV, R-PRESERVA) e de equivalência (EQ-HASH, EQ-INTER,
> EQ-MUST, EQ-DESC, EQ-EXPL, EQ-ANDAIME) são as do
> [doc de domínio](../../domain/evaluation/reproduction-equivalence-and-reporting.md)
> §4–§5 e §9, fixadas antes de a 8.1 rodar. Este concept só preenche a
> mecânica; mudar uma regra agora seria escolher a análise pelo resultado
> (doc §5.2) e passaria a ser decisão P do humano, registrada como desvio.

## 1. Escopo

### Dentro do escopo
- **(i) Reprodução da própria corrida** (claim citável no TCC, doc §4.7 (a)):
  re-executar silver → gold → scorecard da geração julgada
  `aapl_confirmatory-r3-00fd83d9cd39` no commit da corrida (`060537fc`), no
  mesmo ambiente (imagem `sha256:b69a7620…`, `--cpus 6 --memory 8g`), a
  partir do backup de entrada `data/backups/aapl-pre-8.1-20261023-084758`
  restaurado num `data_root` **descartável**, e comparar com a cópia julgada,
  por classe (R1/R2/R3), com max |Δ| reportado também quando passa. O cálculo
  inteiro — refresh **e** scorecard — roda no código de `060537fc`, por um
  **driver** versionado no HEAD fora de `src/` (`scripts/reproduce_judged_generation.py`),
  montado à parte no container; o HEAD só compara, nunca recalcula.
- **Leitor da cópia julgada** como `GoldGeneration` (método novo do port
  `JudgedGenerationStore`), com a mesma verificação de integridade do `find`
  — consumido pela comparação e, depois, pela 8.3.
- **Comparador puro** `compare_reproduction` (application do evaluation) e o
  DTO `ReproductionComparison`, com ponto de entrada só-leitura no CLI
  (`audit-reproduction`).
- **Registro R-BIT-COMMIT** do diff `060537fc..64b8a17d` em `src/` (`64b8a17d` =
  merge-base com `origin/develop` no início da Stage, base fixa): arquivos
  tocados e igualdade de AST **sem docstrings** por arquivo; os acréscimos da
  própria 8.2 (`64b8a17d..HEAD`) vão numa lista separada, cada arquivo
  justificado como fora do caminho de refresh/scorecard (confirmação de que o
  código da base tem o mesmo caminho de cálculo; não substitui a reprodução em
  `060537fc`).
- **(ii) Equivalência interna** com a evidência anterior (só no repositório;
  o TCC não a menciona — P-EDIT):
  - registro de hashes de conteúdo + tipos físicos das colunas (EQ-HASH),
    commitado **antes** de qualquer leitura de valor;
  - andaime de leitura da evidência anterior em `tests/equivalence/` (nunca em
    `src/` — doc §5.1 item 3);
  - interseção por `target_timestamp` e horizonte (EQ-INTER), A1 e A2
    (EQ-MUST), tabela de sentido por horizonte (EQ-DESC), classificação de
    cada divergência pelo catálogo fechado (EQ-EXPL);
  - teste opt-in `tests/equivalence/test_official_vs_prior_evidence.py`
    (EQ-ANDAIME): pula sem o oráculo, falha com hash divergente, nunca
    regenera.
- Relatórios `docs/reports/reproduction_audit.md` e
  `docs/reports/equivalence_audit.md`.

### Fora do escopo (explicitamente)
- **Reprodução entre ambientes (R-ENV / claim (c)):** o projeto tem um único
  ambiente (Windows/Docker CPU; a máquina Linux saiu). Não é executada e o
  claim (c) da §4.7 **não** é afirmado ("só é afirmado se tiver sido de fato
  executado"). O comparador reporta por classe, mas não implementa a
  tolerância R2 com u_q (sem consumidor em `src/`; a tolerância R2 de A2 é do
  andaime — D12).
- **Re-treino, re-inferência e re-julgamento:** nada de `infer`,
  `RunConfirmatoryEvaluation`, `judged/` novo, `ATTEMPTS.jsonl`, tag ou
  comentário. A reprodução das predições a partir dos checkpoints é da 7.1
  (claim (b)) e não é repetida.
- Bit a bit contra a evidência anterior (non-goal do roadmap); qualquer teste
  de hipótese novo (o DM do anterior **não** é recomputado — EQ-INTER);
  cruzar decisões de Holm entre as pipelines.
- Ajustar a pipeline oficial para "bater" com o anterior (doc §5.1 item 1).
- Plots, dossiê e texto do TCC → 8.3 (§14).
- Mudar regra do doc de domínio (fixada antes da 8.1).

### Vínculo com o roadmap
Step 8 — Reprodução, equivalência e relatório; bloco
[`roadmap.md`](../../roadmap.md) §Stage 8.2 (emendado por B1/B2, ADRs
0.0.0061 e 0.0.0062). Atende o critério "Reprodutibilidade" do
[`overview.md`](../../overview.md) §4 (reconstrução sem re-treino) e a
ASSUM-4 / R-REPRO-1 (equivalência com tolerância declarada, oráculo nunca
autoridade — overview §2). Este concept corrige `contratos_consumidos` do
bloco, que citava `RunConfirmatoryEvaluation` (D2), e completa arquivos e
contratos introduzidos.

## 2. Objetivo da Stage

Ao fechar, o repositório contém a evidência de que a geração julgada da 8.1
é reconstruída **bit a bit** a partir dos dados persistidos, no commit e no
ambiente registrados, e um registro auditável — com hashes fixados antes da
leitura — de onde a pipeline oficial coincide, por construção, com o
confirmatório anterior (alvo e código de métrica) e de onde e por que os
números do modelo mudam de sentido.

## 3. Contexto e premissas

### Contexto
A 8.1 (#211, PR #231) julgou o cohort `aapl_confirmatory-r0-665f45d9169a`
pela r3: status `JUDGED`, `generation_digest`
`96c0541301885ed1c6688a517176f63a54e872a3e18ee82fbb5c23121747e539`, tag
`confirmatory-run/aapl_confirmatory-r3-00fd83d9cd39` → `060537fc`, registro
[`aapl_confirmatory-r3.judged.toml`](../../../config/preregistration/aapl_confirmatory-r3.judged.toml).
A cópia julgada (`judged/<ref>/generation/` + scorecard + `run_record.json`
+ `CONTENTS.sha256`) e o `ATTEMPTS.jsonl` estão na partição viva do checkout
principal; o backup da entrada (311 arquivos, listagem `e4c77457…`) e o da
cópia (23 arquivos, listagem `ebaadfc4…`) estão em `data/backups/`. A linha
`input_read` do `ATTEMPTS.jsonl` registra `silver_content.digest`
`7ac4c759c966b8e1914cd33492a8a598a3b57bcb63eff1e80e9ede1bd02a74e2`,
`dataset_fingerprint`
`00e4406dcd96658d557f7d4d86face9874fac42385e3cb182d54c5d2286695bd` e
`result_digest`
`7c7940d4f77ff772212d5ddc392ee46e5f46cebe06506c17a20885b7f0e31b7e`
(sha256 da camada de resultado — ADR 8.1.0004 item 1). O concept 8.1 §14
deixa para cá: usar `silver_content` como pré-condição de identidade,
`run_record.json` para "mesmo ambiente", o diff de commit para R-BIT-COMMIT
e "como montar o `RefreshGold`/scorecard sobre outra raiz de gold".

Nota herdada (technical 8.1 §7 e issue #232): entre `060537fc` e o HEAD,
`src/` mudou em 15 arquivos (21+/48−), só por formatação (junções de linha do
ruff, f-strings adjacentes unidas) e por um trecho de docstring de módulo em
`refresh_gold.py`; o `code.src` difere. Fora de `src/`, `Dockerfile` (uv
pinado) e `pyproject.toml` (alvo do mypy) mudaram — ambiente/tooling, não
caminho de cálculo; a imagem da corrida segue presente localmente.

### Premissas
- A imagem `sha256:b69a7620e7bd8449369bde2f46e903c5f46c25e9efb3597f452af3272e0a8f45`
  continua disponível (conferido em 2026-10-23 por `docker image inspect`); se
  sumir, a reprodução no mesmo ambiente fica impossível e cai na tabela de
  erros (§6).
- O backup de entrada é íntegro (`sha256sum -c` contra a listagem cujo sha256
  está no `.judged.toml`) — conferido na Fase 4 antes de restaurar.
- A evidência anterior em `data/analytics/` do checkout principal é a mesma
  medida na §7 (sha256 de D-M1) até o commit do registro.
- **Backup ≠ partição viva byte a byte só em `inference/<cohort>/manifest.json`**
  (o `infer` da 8.1 o regravou depois do backup; Checkpoint A, DT-10). O
  `RefreshGold` não o lê: seus colaboradores no composition root são o
  repositório silver, o `ReadTrainingGrid`, o clock, o MCS, o gold store, os
  builders, o `CalibrateConformal` e o hasher (`composition_root.py`,
  montagem do `RefreshGold`) — sem `JsonInferenceManifest`. O technical
  reconfere em `060537fc`.

### Dependências
- `8.1-confirmatory-run` (`done`): geração julgada preservada, `silver_content`
  no manifesto, `run_record.json`, `ATTEMPTS.jsonl` (`result_digest`),
  `.judged.toml` com os backups; port `JudgedGenerationStore`;
  `result_layer_digest`; `resolve_judged_revision`; `refresh_command_from`.

## 4. Contratos

### Introduzidos
- **`JudgedGenerationStore.read_judged_generation`** (`port-out`, método novo):
  ```python
  def read_judged_generation(
      self, *, partition: GoldPartition, preregistration_ref: str
  ) -> GoldGeneration: ...
  ```
  Lê `judged/<ref>/generation/` (tabelas + `MANIFEST.json`) depois de
  verificar `CONTENTS.sha256` como o `find` (arquivo faltando, a mais ou com
  hash diferente → `JudgedGenerationTamperedError`; sem cópia → erro de
  cópia ausente, nome fixado no technical). Real: `ParquetGoldStore`; fake em
  memória; suíte de contrato estendida.
- **`ReproductionComparison`** (`dto`, `application/dtos/`): identidade
  (`preregistration_ref`, partição, `silver_content.digest`,
  `dataset_fingerprint` — cada um com os dois lados e `equal`);
  `result_digest` dos dois lados; por tabela: linhas de cada lado, chaves
  iguais, e por classe R1/R2/R3 o número de valores comparados, de diferentes
  e o max |Δ| absoluto; scorecard: igualdade da serialização sem as chaves de
  proveniência e max |Δ| nas folhas numéricas; `bit_identical: bool`
  (identidade igual **e** zero diferença em toda classe e no scorecard).
- **`compare_reproduction`** (função pura, `application/use_cases/`):
  ```python
  def compare_reproduction(
      *, judged: GoldGeneration, judged_scorecard: Mapping[str, object],
      reproduced: GoldGeneration, reproduced_scorecard: Mapping[str, object],
      expected_result_digest: str,
  ) -> ReproductionComparison: ...
  ```
  Classe por coluna por um mapa declarado (`REPRODUCTION_CLASSES`), **completo**:
  toda coluna de todo `GoldTableSchema` tem classe declarada (teste de
  completude; sem fallback por tipo). Não-float (contagens, decisões,
  rótulos, timestamps) → R1; float que depende de número aleatório (p-valores
  do MCS e da sensibilidade de bloco, p-valores de Monte Carlo do
  Christoffersen, limites bootstrap de H3) → R3; demais floats → R2.
  Igualdade de float é **por bits** (distingue `-0.0` de `0.0` e padrões de
  NaN). max |Δ| só para numéricos; para R1 não numérico, a contagem de
  diferentes. `bit_identical` exige também `result_layer_digest` dos dois
  lados = `expected_result_digest` (o `result_digest` da linha `input_read`
  do `ATTEMPTS.jsonl`). Proveniência excluída: `started_at`/`finished_at` do
  manifesto (`RESULT_EXCLUDED_KEYS`) e as mesmas chaves dentro de
  `manifest_read` do scorecard.
- **Driver da reprodução** (contrato operacional, fora de `src/`):
  `scripts/reproduce_judged_generation.py`, versionado no HEAD, executado no
  container da imagem da corrida com a árvore de `060537fc` montada como
  `/app` e o driver montado à parte (`/driver/`, fora dos caminhos do probe —
  a árvore segue limpa). Só faz wiring pelo `ApplicationDependencies` de
  `060537fc` (`wire_dependencies(Settings(data_root=<descartável>))` →
  `resolve_judged_revision` → `refresh_gold(refresh_command_from(plan, ref))`
  → `build_confirmatory_scorecard`) e grava, num diretório fixo fora de
  `gold/` (`<descartável>/reproduction/`), `scorecard.json` =
  `document_bytes(scorecard.as_mapping())` (o serializador da cópia julgada,
  presente em `060537fc`) e `environment.json` = a foto do
  `EvaluationEnvironment` montada em `060537fc`. Recusa `data_root` sob
  `data/cohorts/` ou com `gold/`/`reproduction/` pré-existente. Usa só APIs
  idênticas em `060537fc` e no HEAD (o diff de `src/` é só formatação), o que
  permite um **smoke test** barato no HEAD com dependências falsas — prova só
  a lógica do driver (ordem refresh → scorecard, bytes gravados, recusas), não
  o wiring de `060537fc`; por isso o driver tem o modo `--check`, executado
  **em `060537fc`** como pré-voo da reprodução: monta o wiring e tira a foto
  do ambiente, sem refresh.
  **Foto do ambiente — mesmo produtor da linha `started` (Checkpoint A r2, N1).**
  Em `060537fc` o `GitEvaluationEnvironment` só é montado dentro da closure
  `run_confirmatory_evaluation_for` do composition root (com
  `_torch_cpu_capability` privada e `CODE_KEYS`/`DIRTY_KEY` do modeling). O
  driver usa exatamente esse produtor:
  `deps.run_confirmatory_evaluation_for(cohort, device)._environment.snapshot()`
  — acesso a atributo privado **declarado e justificado**: é o único caminho
  que dá, sem código novo em `060537fc`, a mesma foto que a 8.1 gravou; o
  use case montado não é chamado. Parâmetros fixos: `cohort` =
  `config/cohorts/aapl_confirmatory.toml`, `device` = `cpu`, `IMAGE_ID` = id
  da imagem por variável de ambiente (sem ele, `MissingImageIdError`), cwd =
  `/app` (o `repo_root` tem de ser o `git rev-parse --show-toplevel`), e
  `GIT_DIR`/`GIT_WORK_TREE` explícitos (o `.git` de uma worktree aponta para
  caminho do host). A foto é tirada **antes** do refresh, como na 8.1.
- **Subcomando `audit-reproduction`** (`adapters/in/cli`): `--judged-data-root`,
  `--reproduced-data-root`, `--preregistration`, `--revision`,
  `--preregistration-ref`; sem lock, só leitura nas duas raízes; recusa as duas
  raízes iguais; confere o `generation_digest` da cópia contra o `.judged.toml`
  commitado; lê a geração reproduzida e `<reproduzida>/reproduction/scorecard.json`
  (**nunca recalcula** o scorecard) e o `result_digest` do `ATTEMPTS.jsonl` da
  raiz julgada; imprime a comparação por classe e sai `0` só com
  `bit_identical`.
- **Registro de hashes da evidência anterior** (formato persistido):
  `docs/reports/prior_evidence_registry.toml` — por arquivo: caminho relativo a
  `data/analytics/`, sha256 do conteúdo, número de linhas e tipo físico de cada
  coluna (lidos do footer Parquet, sem valores).

### Consumidos
- **Geração julgada preservada** (`judged/<ref>/`), `silver_content` do
  manifesto, `run_record.json`, `ATTEMPTS.jsonl` e `.judged.toml` — Stage 8.1
  (ADRs 8.1.0002–8.1.0004).
- **`RefreshGold`** (6.4) e **`BuildConfirmatoryScorecard`** +
  `refresh_command_from` + `resolve_judged_revision` (6.5/8.1) — **na árvore
  de `060537fc`**, montados pelo `wire_dependencies` daquele commit com
  `Settings(data_root=<descartável>)`.
- **`result_layer_digest`** e `RESULT_EXCLUDED_KEYS` (8.1,
  `application/dtos/judged_generation.py`).
- **`GoldGenerationReader`** / `ParquetGoldStore.read_generation` (6.5) — para
  ler a geração reproduzida.
- Serviços de domínio de pinball, PICP/MPIW e Wilson (Step 6) — aplicados pelo
  andaime às predições anteriores (A2).

## 5. Invariantes e regras

- **I1 — Partição viva intocada.** Nenhuma escrita sob `data/cohorts/aapl/`:
  `current/MANIFEST.json` (sha256 `56d3ee1c…`), `judged/ATTEMPTS.jsonl`
  (`320def2b…`) e `CONTENTS.sha256` da cópia (digest `96c05413…`) iguais antes
  e depois da Stage.
- **I2 — Destino separado.** A reprodução escreve só no `data_root`
  descartável, fora de `data/cohorts/` e de qualquer `judged/`.
- **I3 — Identidade antes de resultado.** A reprodução só conta se
  `silver_content.digest`, `dataset_fingerprint`, `preregistration_ref` e
  partição forem iguais aos da geração julgada; senão "é outra corrida"
  (doc §2.2) e nada é comparado como resultado.
- **I4 — Mesmo caminho de cálculo e ambiente.** A foto do
  `EvaluationEnvironment` montada em `060537fc` (`environment.json` do driver)
  é igual, chave a chave, às chaves `code.*` e `env.*` da linha `started` do
  `ATTEMPTS.jsonl` (`code.src` `4d2b2540…`, `code.uv_lock` `0f36050a…`,
  `env.lib.*`, `env.probe.*` inclusive `torch_threads`, `env.image_id`), com
  a árvore limpa, o container criado pelo id da imagem e o mesmo `--cpus`
  (evidência: `cat /sys/fs/cgroup/cpu.max` e sha256 de `uv pip freeze` do
  `.venv` usado, colados no technical §7).
- **I5 — Falha no mesmo ambiente é parada.** Qualquer diferença com I3–I4
  satisfeitas → `[finding]` e diagnóstico; nenhuma tolerância "salva" a falha
  (R-BIT); a geração julgada nunca é trocada pela reproduzida (doc §4.6).
  Lista de diagnóstico pré-declarada inclui o processo novo (a 8.1 rodou o
  refresh depois do `infer` no mesmo processo; aqui é outro processo, com
  outro `PYTHONHASHSEED`) — o technical pré-checa um refresh sintético em dois
  processos com `PYTHONHASHSEED` diferentes.
- **I6 — Hash antes de valor (recorte de D11).** Nenhum valor de métrica,
  perda, p-valor, sinal, veredito ou realizado (`y_true`) da evidência anterior
  é lido antes do commit do registro; metadados de forma (schema, contagens,
  datas, ids, rótulos de definição) são permitidos e os de D9 já foram lidos;
  o andaime lê só arquivo cujo sha256 bate com o registro e recusa o resto
  (EQ-HASH).
- **I7 — A evidência anterior nunca é entrada oficial.** Leitores dela só em
  `tests/equivalence/`; nada em `src/` a importa ou lê (doc §5.1 item 3).
- **I8 — Regras do doc de domínio fixas.** Interseção, tolerâncias, catálogo
  de explicação e aplicabilidade por comparação são os da §5.3–§5.6; o
  technical não os amplia.
- **I9 — Por horizonte.** Toda comparação é por horizonte, nunca agregada.

## 6. Casos de erro e exceções

| Situação | Comportamento |
|---|---|
| `sha256sum -c` do backup de entrada falha | não restaurar; `[finding]`, parar (o backup é a entrada congelada — ADR 8.1.0003 item 6b) |
| Imagem `b69a7620…` ausente, ou probe com `non-code diff` ≠ `[]` / `code.src` ≠ `4d2b2540…` | não rodar como R-BIT; `[finding]`; parada para decisão (sem segundo ambiente, só diagnóstico) |
| Identidade da geração reproduzida ≠ julgada (I3) | `ReproductionComparison` com identidade desigual, `bit_identical = false`; `[finding]` "outra entrada" e diagnóstico |
| Resultado difere com identidade e ambiente iguais | `audit-reproduction` sai ≠ 0 com a tabela por classe; `[finding]` R-BIT, diagnóstico antes de qualquer uso; correção de código que mude número confirmatório = desvio (doc §4.6) |
| Cópia julgada adulterada | `JudgedGenerationTamperedError`; restaurar do backup da cópia com `sha256sum -c` e `[deviation]` (ADR 8.1.0004 item 2c); nunca re-julgar |
| `--judged-data-root` = `--reproduced-data-root` | recusa antes de ler (I2) |
| Arquivo da evidência anterior com sha256 ≠ registro | o andaime recusa; o teste **falha** (nunca pula nem regenera) |
| Oráculo ausente (variável de ambiente não definida ou caminho inexistente) | o teste **pula** com o motivo e o caminho do registro |
| Interseção de um horizonte vazia | registrado; sem comparação numérica naquele horizonte (EQ-INTER item 4) |
| Amostra do anterior não reconstruível para uma grandeza | A2 "não realizável", registrado (doc §5.4) |
| A1 ou A2 fora da tolerância com indício de defeito na pipeline nova | `[finding]` investigado antes de fechar; defeito confirmado → correção pelo processo normal, reportada como desvio (doc §5.6) |

## 7. Decisões técnicas relevantes

Todas fecham por documento (doc de domínio, ADRs, código) ou por medição
desta sessão; triagem `evidence-resolution`: nenhuma de classe P. A pesquisa
da issue #232 (§Referências) é usada, não repetida.

### D1 — Reproduzir no commit da geração julgada
```
[decision:E] D1 — commit da reprodução
Escolha: a reprodução roda na árvore de 060537fc (o commit do run_record.json e da tag), com o probe confirmando code.src 4d2b2540…; o HEAD entra só como confirmação: registro do diff 060537fc..HEAD em src/ com igualdade de AST sem docstrings por arquivo · Alternativas: reproduzir no HEAD e argumentar R-BIT-COMMIT pelo diff textual; comparar a AST do HEAD com docstrings
Base: doc §4.2 R-BIT-COMMIT ("o claim do TCC só vale para a reprodução feita com o caminho de cálculo da geração julgada (o que pode exigir re-executar no commit dela)"); doc §4.7 (a); Python 3.12 Glossary "docstring" ("recognized by the compiler and put into the __doc__ attribute") — o docstring é um Expr(Constant) no corpo e entra em ast.dump (medido: ast.dump(ast.parse('"""doc"""\nx = 1')) contém Expr(value=Constant(value='doc'))); f-strings adjacentes unidas dão a mesma AST (medido: ast.dump de f"{a}: " f"{b}" igual ao de f"{a}: {b}")
Verificado: medição local (stdlib, Python 3.13 do host); a confirmação definitiva roda no container 3.12 na Fase 4 (A7)
Sensibilidade pré-registrada: nenhuma · Reversível: sim
```
Por quê: em `060537fc` o `code.src` é literalmente o da tentativa — o claim
fica limpo sem depender de um argumento sobre o diff. ADR
[8.2.0001](../../adr/8_2_0001-reproduction-at-judged-commit-in-disposable-data-root.md).

### D2 — Destino separado sem a orquestração da 8.1
```
[decision:E] D2 — como re-executar em destino separado
Escolha: copiar o backup de entrada para um data_root descartável (fora de data/cohorts/), conferir com sha256sum -c a listagem cujo sha256 está no .judged.toml, e rodar o driver scripts/reproduce_judged_generation.py (versionado no HEAD, montado em /driver/) contra a árvore de 060537fc montada como /app: wire_dependencies(Settings(data_root=<descartável>)) → resolve_judged_revision → refresh_gold(refresh_command_from(plan, ref)) → build_confirmatory_scorecard, gravando document_bytes(scorecard.as_mapping()) e a foto do EvaluationEnvironment em <descartável>/reproduction/; o audit-reproduction do HEAD só lê esses arquivos e a geração (nunca recalcula); sem RunConfirmatoryEvaluation, sem infer, sem judged/, sem ATTEMPTS.jsonl, sem tag nem comentário; o roadmap passa a consumir RefreshGold + BuildConfirmatoryScorecard em vez de RunConfirmatoryEvaluation · Alternativas: RunConfirmatoryEvaluation sobre o descartável; reproduzir na partição viva; restaurar o backup sobre data/cohorts/aapl; recalcular o scorecard no HEAD a partir da geração reproduzida (contradiz D1); subcomando novo do CLI (não existe em 060537fc); driver dentro de src/ (sujaria o probe) ou copiado para a árvore montada (mistura o driver ao código julgado)
Base: CLI de 060537fc sem subcomando de refresh nem de scorecard e scorecard só em memória fora do RunConfirmatoryEvaluation (Checkpoint A, CA-1); ApplicationDependencies expõe refresh_gold e build_confirmatory_scorecard; montar o driver em /driver/ é escolha de isolamento (a árvore de 060537fc fica intocada), não necessidade — o probe só marca dirty por git status em src/, uv.lock e o arquivo do cohort (git_runtime_environment_probe.py); ADR 6.5.0003 item 4 (o primeiro refresh confirmatório é, por definição, o da 8.1); ADR 8.1.0004 (um julgamento por partição; o .judged.toml commitado é verdade cruzada — no HEAD o G4 recusa um data_root sem a cópia; em 060537fc, sem o registro, selaria um segundo judged/); ADR 6.4.0005 itens 4–5 (o refresh troca current/); doc §4.1, §4.6, R-PRESERVA; ADR 8.1.0003 item 6b (o backup é a entrada congelada da 8.2); concept 8.1 §14 ("os dois já recebem o store por injeção"); composition_root.py (ParquetGoldStore(cfg.data_root), RefreshGold e confirmatory_wiring sobre o mesmo data_root)
Verificado: leitura do código e dos ADRs nesta sessão
Sensibilidade pré-registrada: nenhuma · Reversível: sim
```
Por quê: o `RefreshGold` e o scorecard são exatamente o caminho de cálculo; o
orquestrador da 8.1 só acrescenta guardas e efeitos de julgamento que aqui
seriam ou recusa ou um segundo selo. ADR 8.2.0001.

### D3 — O que se compara e com que leitor
```
[decision:C] D3 — comparação da reprodução
Escolha: camada de resultado por valor — result_layer_digest dos dois lados (e contra o result_digest 7c7940d4… do ATTEMPTS) mais comparação tabela a tabela, coluna a coluna, com classe R1/R2/R3 por mapa declarado, igualdade de float por bits e max |Δ| por classe reportado mesmo quando zero; scorecard pela serialização sem started_at/finished_at; leitor da cópia julgada como método do JudgedGenerationStore (reusado pela 8.3); comparador puro no application do evaluation com subcomando só-leitura · Alternativas: comparar bytes dos Parquet ou o generation_digest (o MANIFEST.json tem instantes — proveniência); só o digest (não mostra onde nem quanto); snippet de runbook sem teste; comparador em scripts/ ou em tests/
Degrau: 1 (doc §2.2 R-CAMADAS: resultado comparado, proveniência excluída; §4.6 "classe por classe, com max |Δ| também quando passa — como o ADR 7.1.0003 item 5"; ADR 8.1.0004 item 1: camada de resultado sem started_at/finished_at) e 4 (código testado é a forma mais conservadora para um claim citável)
Base: doc §2.2, §4.2–§4.3, §4.6; ADR 8.1.0004 item 1; ADR 8.1.0003 itens 2–5b; concept 8.1 §14 (a 8.3 lê de judged/<ref>/, nunca de current/)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim
```
Por quê: o digest prova a igualdade; a tabela por classe é o que o claim cita
e o que diagnostica uma falha. O leitor da cópia é necessidade compartilhada
8.2/8.3 — fica no port, não num atalho local. ADR
[8.2.0002](../../adr/8_2_0002-reproduction-comparison-by-result-layer-and-judged-copy-reader.md).

### D4 — R-ENV não executada
```
[decision:C] D4 — reprodução entre ambientes
Escolha: não executar; declarar no relatório que só o claim (a) — e o (b) da 7.1 — é afirmado; o comparador classifica R1/R2/R3 mas não implementa a tolerância R2 com u_q (sem consumidor em src/; o A2 da equivalência usa a fórmula R2 no andaime, com u_q fixado em D12) · Alternativas: simular um segundo ambiente com outra imagem (não é ambiente registrado do estudo e não sustenta (c))
Degrau: 1 (doc §4.7: "O item (c) só é afirmado se tiver sido de fato executado; o TCC não promete reprodução que não foi feita")
Base: doc §4.3, §4.7; fato do projeto: um único ambiente (Windows/Docker CPU)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim (com um segundo ambiente, a tolerância entra numa issue própria)
```

### D5 — Registro de hashes da evidência anterior
```
[decision:C] D5 — EQ-HASH
Escolha: docs/reports/prior_evidence_registry.toml com sha256 de conteúdo, linhas e tipo físico de cada coluna (footer Parquet) de cada arquivo que a auditoria lê, commitado em commit próprio antes de qualquer leitura de valor; o conjunto lido é o do registro e nenhum outro; fora de tests/ para sobreviver à aposentadoria do andaime · Alternativas: versionar os próprios arquivos (contraria o "nunca entrada" e o caráter git-ignorado); registro dentro de tests/equivalence/; listagem sha256sum sem tipos
Degrau: 1 (doc §5.2: hash por arquivo + lista, versionado, precisão do schema "registrada junto"; §5.7: "o registro durável da auditoria é o relatório com os hashes")
Base: doc §5.2, §5.7; Sandve et al. 2013 Rules 1 e 4 (via doc)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: não depois de lidos os valores
```

### D6 — Andaime e teste de equivalência
```
[decision:C] D6 — EQ-ANDAIME
Escolha: leitores, alinhamento, A1/A2 e tabela de sentido da evidência anterior vivem em tests/equivalence/ (andaime); o teste é opt-in por variáveis de ambiente que apontam a raiz do oráculo e a do dado oficial: ausentes → pytest.skip com o motivo e o caminho do registro (pula em make check e no CI; o comando documentado usa -rs para mostrar o motivo); presentes → confere todo sha256 contra o registro (diferente → falha) e afirma que a classificação recomputada de cada comparação (dentro da tolerância / explicada com a categoria / não explicada) é a declarada no próprio teste **e** que essa tabela declarada é igual à tabela parseada de docs/reports/equivalence_audit.md (editar uma sem a outra falha, e o diff fica visível) — oráculo de regressão; a função de checagem de hash tem teste unitário sempre ativo (tmp_path, roda no CI); nunca escreve registro nem relatório · Alternativas: script fora da suíte (contraria o arquivo do roadmap); teste sempre ativo (quebra o CI sem o oráculo); teste que só afirma A1/A2 (falharia numa divergência legitimamente explicada, p. ex. fator 2 de escala)
Degrau: 1 (doc §5.7; §5.1 "oráculo de equivalência/regressão"; roadmap 8.2 arquivos_a_criar) e 5
Base: doc §5.1, §5.7; pytest "How to use skip and xfail" (skip com motivo — referência da issue #232)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim
```
ADR [8.2.0003](../../adr/8_2_0003-prior-evidence-scaffold-in-tests-with-hash-registry-and-opt-in-test.md).

### D7 — Um ponto por `target_timestamp` no lado anterior (mecânica de EQ-INTER)
```
[decision:C] D7 — ponto do anterior com janelas sobrepostas
Escolha: medido que o anterior tem três janelas de teste sobrepostas (um target_timestamp aparece em até duas) e declara dedup_rule = operationally_latest_fold; o ponto do anterior num target_timestamp é o que a sua própria regra seleciona; o lado novo tem folds de teste disjuntos (medido) e um ponto por timestamp; nas grandezas A2 gravadas por run (PICP/MPIW e pinball por run do anterior), a amostra é a do run, como o anterior gravou · Alternativas: média das duas predições sobrepostas (previsão que nenhuma pipeline emitiu); manter os dois pontos (dois pesos para um timestamp)
Degrau: 1 (doc §5.4 A2 "na mesma amostra que o anterior usou" e linha "amostra (pontos, dedup, exclusões)"; §5.3 item 3 — não se pontua previsão que nenhum lado emitiu; evaluation §6.7 conv. 17 — um ponto alinhado por timestamp)
Base: medição D-M3; doc §5.3–§5.4
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim
```

### D8 — "Rejeição" no sentido do DM
```
[decision:E] D8 — o que é a rejeição comparada no DM
Escolha: o par comparado por (horizonte, baseline comum) é (sinal de d̄, p do teste primário de cada lado ≤ α daquele lado), sem ajuste de Holm em nenhum dos lados; o sinal é normalizado para d̄ = perda(candidato) − perda(baseline) nos dois lados, com a convenção de cada lado lida do nome da coluna e do código (mean_loss_diff_tft_minus_baseline do anterior; candidate/comparator do gold novo), nunca dos valores; do lado novo, gold_dm_results com o estimador retangular, também onde H1 reprova; do lado anterior, phase_b_dm_family_6 (analysis_role primary_family_6); estimador, HLN, lateralidade, loss e família de cada lado entram como contexto declarado · Alternativas: comparar significant_adj_0_05 × rejected (decisões de Holm)
Base: doc §5.3 ("o sinal de d̄ e a rejeição ao α de cada lado"; "Não se cruzam decisões de Holm entre as pipelines: as famílias, o candidato e o gate H1 diferem"); ADR 6.5.0006 (estimador primário)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim
```

### D9 — Medição de forma (data-shape-evidence; sem valor de métrica)

Leituras de schema e de colunas-chave (modelo, split, fold, seed, horizonte,
timestamps, contagens e rótulos de definição) em 2026-10-23, no container da
imagem `b69a7620…`, montagens só-leitura; nenhuma coluna de métrica, perda,
p-valor, sinal, veredito ou realizado foi lida. Ressalva de registro: ao
listar os valores distintos das colunas de rótulo dos reports de DM, a
coluna `direction` (rótulo categórico do sentido) também foi impressa como
**conjunto** {`baseline_better_or_equal`, `tft_better`}, sem associação a
horizonte ou baseline; ela não entra em nenhuma decisão deste concept. Isto
é fato declarado sob D11.

- **D-M1 — Arquivos candidatos ao registro e sha256 na medição**
  (`data/analytics/`, git-ignorado; `reports/phase_b/` com mtime 2026-06-29;
  o registro da Fase 4 reconfere):

  | arquivo (sob `data/analytics/`) | linhas | sha256 |
  |---|---|---|
  | `reports/phase_b/cohort=phase_b_confirmatorio_20260524/phase_b_delta_pinball.parquet` | 6 | `d801eff08fa094bfdcd95048252c07edbbaeba2c8019a9c1c15d795ec2947b9b` |
  | `reports/phase_b/cohort=phase_b_confirmatorio_20260524/phase_b_dm_family_6.parquet` | 6 | `f91148b1b849f0de5a17efdc22b8ea068257450b5227615ba6e5d415f20cae6c` |
  | `reports/phase_b/cohort=phase_b_confirmatorio_20260524/phase_b_dm_family_18_sensitivity.parquet` | 18 | `4c9debe465e72de453af1ebbad7b44b07df57e5f89057da36a909bc18ffb3bc0` |
  | `reports/phase_b/cohort=phase_b_confirmatorio_20260524/phase_b_marginal_coverage.parquet` | 60 | `664c41b4b01e9155a35282664107c5ed64773c26c47a6af95542717b04a033c8` |
  | `reports/phase_b/cohort=phase_b_confirmatorio_20260524/phase_b_tier_verdict.parquet` | 6 | `5c381b31dc81b304b34578000ffff33a6fc949ca18241493c349bfa3146eca08` |
  | `gold/gold_oos_consolidated.parquet` | 410208 | `b53bc84f293010d8a2b21d98f42e27161dfb0da0e5e888d69f7976d775d89e29` |
  | `gold/gold_prediction_calibration.parquet` | 452 | `d64779b0f310148b5c6fa8a95e7a49d533c9ca020b5e9b0300a04ca93cffab42` |
  | `gold/gold_prediction_metrics_by_run_split_horizon.parquet` | 452 | `6c8ca7607b7cfd75306c645158832f31dade670d42e7cb663e2c81729f170026` |
  | `gold/gold_dm_pairwise_results.parquet` | 84 | `33970e46af00a12f06092f806464a4af1bdf5e9508895642bc35694feaac62e6` |
  | `gold/gold_mcs_results.parquet` | 54 | `cff92a14363812ee455326b03de1b29df77f66e291bd277d12313b9064a81fe0` |

- **D-M2 — Lado anterior, `gold_oos_consolidated`** (mistura
  `phase_a_smoke…`, `trial_*` e o confirmatório; filtra-se
  `parent_sweep_id = phase_b_confirmatorio_20260524`, `split = test`):
  52 280 linhas; candidato `BTSF` com 15 `model_version` = 3 janelas × 5 seeds
  (20260517–20260521); baselines `baseline_zero_return_v1`,
  `baseline_historical_mean_rolling_v1`,
  `baseline_historical_quantiles_rolling_v1`, cada um com 3
  `config_signature` (uma por janela) repetidos por seed; `fold = 'none'`;
  horizontes {1, 7}; só p10/p50/p90, em duas variantes (`quantile_*` bruto e
  `quantile_*_post_guardrail`; `quantile_guardrail_applied` ∈ {0, 1});
  `y_true` `double`; timestamps texto `YYYY-MM-DDT00:00:00+00:00`; nenhuma
  chave duplicada (config, seed, h, target_timestamp).
- **D-M3 — Janelas e definições do anterior (teste)**: três janelas
  sobrepostas de 435–436 pontos por horizonte — h=1 [2022-03-30, 2023-12-20],
  [2023-03-30, 2024-12-20], [2024-03-28, 2025-12-22] (h=7 deslocado, até
  2025-12-31); 937 `target_timestamp` distintos por horizonte. Reports
  `phase_b_dm_*`: `dedup_rule = operationally_latest_fold`, `seed_aggregation
  = mean_loss_diff_by_timestamp`, `loss_function =
  pinball_loss_post_guardrail`, `hln_applied = True`, `hac_lag_used` ∈ {1, 6},
  `n_obs_effective` 937 (família 6) e 435/436 (sensibilidade por janela
  `wf_1..wf_3`); `phase_b_marginal_coverage` por `run_id` (15 runs ×
  {test, val} × h, `n_obs` 435–439); `phase_b_tier_verdict` com hipóteses
  H1, H2a, H2b por horizonte.
- **D-M4 — Lado novo** (backup de entrada, `fact_oos_predictions`,
  `split = test`): 6 folds de teste **disjuntos** (h=1 de 2019-12-27 a
  2025-12-31; 252 timestamps por fold, 251 no fold 5; h=7 245 no fold 5);
  grade de 7 níveis {0,02; 0,1; 0,25; 0,5; 0,75; 0,9; 0,98} com `value_raw`
  e `value_guardrail`; `tft_quantile` com 10 seeds, `gbm_quantile` e os
  baselines `baseline_zero_return`, `baseline_historical_mean`,
  `baseline_historical_quantiles`, `baseline_ar1`, `baseline_ewma_vol` (sem
  seed); o silver de entrada também tem o cohort de ablação (5 configurações
  × 60 runs), fora da comparação; mesmo formato de timestamp do anterior.
  Gold julgado: 19 tabelas + `MANIFEST.json`; `gold_dm_results` com 24
  linhas.
- **D-M6 — Tipo físico do realizado do lado novo (Checkpoint A, CA-4; só
  schema):** o realizado do `RefreshGold` vem do `ReadTrainingGrid` sobre
  `processed/dataset_tft/AAPL/dataset_tft_AAPL.parquet`, coluna
  `target_return: double` (também `log_return_1d/5d/21d: double`,
  `timestamp: timestamp[ns, tz=UTC]`); nenhuma tabela do gold julgado guarda
  o realizado por ponto. Os dois lados gravam `double` — o caminho float32
  não se aplica ao alvo; o risco remanescente é de **definição** (como o
  realizado de h=7 é formado a partir da série diária) — §10 e D13. O
  andaime obtém y_novo pelo `ReadTrainingGrid` do código novo sobre o
  backup restaurado (o gold não guarda o realizado por ponto).
  **Emenda pós-execução (B3, ADR [8.2.0004](../../adr/8_2_0004-a1-tolerance-by-effective-float32-storage-precision.md)):** o tipo físico `double` do
  `y_true` anterior **não** é a sua precisão efetiva — na E4 real, o
  diagnóstico de D13 mostrou y_ant = float32(y_novo) em 937/937 pontos nos
  dois horizontes (|Δ| relativo máx 0,978·2⁻²⁴). A suposição "os dois lados
  `double` ⇒ o caminho float32 não se aplica" desta medição estava errada para
  o lado anterior.
- **D-M5 — Interseção (só datas, amostra de 2023):** h=1, 249 das 250 datas
  do anterior presentes no novo; h=7, 243 de 250. A interseção exata (T∩ por
  horizonte) e o motivo do h=7 menor são da Fase 4.
- **Consequências para a mecânica (sem valor):** níveis comuns = {0,1; 0,5;
  0,9}, sem reinterpolar; par 80 % = (0,1; 0,9) dos dois lados; o candidato
  anterior agrega seeds pela média das perdas, como o novo (B-SEEDS) — a
  categoria "agregação de seeds" da §5.6 não tem efeito previsto, salvo prova
  em contrário; o anterior pontua a variante `post_guardrail` — candidata à
  categoria "bruto × rearranjado" se o lado novo pontuar outra variante (a
  conferir no código, não nos números); baseline comum só por **definição**
  declarada dos dois lados (EQ-INTER item 1); `y_true` `double` ⇒ tolerância
  A1 = meio ulp de float64 na magnitude (2⁻⁵³·|y|) — **emendado por B3**
  (D13): `float32(y_novo) == y_ant`, com a pré-condição, por horizonte, de
  representabilidade exata em float32 e valores finitos.

### D11 — Recorte do "antes de qualquer valor" (decisão da mestra no Checkpoint A, CA-2)
```
[decision:C] D11 — o que o EQ-HASH proíbe ler antes do registro
Escolha: antes do commit do registro, nenhum valor de métrica, perda, p-valor, sinal, veredito ou realizado (y_true) da evidência anterior é lido; metadados de forma (schema, contagens, datas, ids, rótulos de definição) são permitidos; as leituras de D9 são declaradas como fato; os sha256 de D-M1 ficaram fixados no commit ba289aa3, antes de qualquer valor, e o registro formal os reproduz e confere (arquivo com sha256 diferente de D-M1 → parar e [finding]) · Alternativas: proibir também metadados de forma (inviabiliza fixar a interseção antes dos números, que o próprio doc pede); tratar ba289aa3 como violação e refazer (nenhum valor protegido foi lido)
Degrau: 1 (doc §5.2: "o congelamento protege a escolha do conjunto de comparação contra os números novos, não contra os antigos"; os agregados do anterior já são conhecidos — overview §2; o registro serve à integridade do oráculo)
Base: doc §5.2, §9 conv. 8; decisão da mestra no Checkpoint A, rodada 1
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: não
```

### D12 — O que A2 e A11 comparam, fixado antes dos valores (Checkpoint A, DT-2/DT-3/DT-4/CA-3/CA-5)
```
[decision:C] D12 — conjunto de comparação da equivalência
Escolha: (a) baseline comum: só se a definição dos dois lados (estimador, janela, parâmetros e — para baselines quantílicos como o zero_return — a regra que gera a dispersão dos quantis) vier de fonte versionada ou registrada no registro de hashes (código/docs do anterior, payload de configuração); a lista de comuns, sua fonte e as colunas lidas fecham no technical e entram no commit do registro, antes do passo 3 do D10; zero comuns → tabela de baseline vazia registrada, não contornada; (b) comparações candidato × candidato independem de baseline e sempre existem: por h, deltas com sinal m_novo − m_A em T∩ na pinball de cada nível comum, no PICP e no MPIW do par 80 %, e o lado do nominal do PICP 80 % do candidato (banda de Wilson 95 % do lado novo) para m_novo e para m_A — o lado anterior entra por m_A (código novo em T∩), nunca por m_ant; (c) variante: cada m_ant usa a variante que o seu rótulo/schema declara (colunas *_raw × *_post_guardrail; loss_function); sem rótulo, a variante declarada pelo anterior para a loss (post_guardrail) — o A2 roda m_A só com essa variante; o lado novo pontua a variante que o seu código declara; (d) agregação de seeds do candidato, nos dois lados: pinball pela média das perdas ponto a ponto e PICP/MPIW pela média das coberturas/larguras por seed (B-SEEDS, evaluation §6.9); (e) u_q de A2 (doc §4.3): pinball por nível = média de |termo| (os termos são ≥ 0, logo a própria pinball); MPIW = média de |largura|; PICP = 1; precisão de armazenamento de m_ant = meio ulp do tipo físico do registro na magnitude de m_ant; tolerância A2 = max(1e-9·max(|m_A|, |m_ant|, u_q), precisão de armazenamento) · Alternativas: fixar baselines e variantes depois de ver os valores (forking paths, doc §5.2); amarrar o sentido só a baseline comum (perde o pareamento por papel do doc §5.3 item 1)
Degrau: 1 (doc §5.2–§5.5, §4.3; evaluation §6.9; ADR 0.0.0062)
Base: doc §5.3 item 1 ("O candidato é pareado por papel"), §5.4 tabela de definições, §5.5, §4.3 (u_q por grandeza)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: não depois do passo 3 do D10
```

### D13 — Critério ponto a ponto de A1 e diagnóstico pré-declarado (Checkpoint A, DT-5/CA-4)
```
[decision:C] D13 — A1 por ponto
Escolha: todo ponto de T∩ (por horizonte) é conferido: |y_novo − y_ant| ≤ 2⁻⁵³·|y_ant| (meio ulp do double gravado pelo anterior, na magnitude do valor anterior; y_ant = 0 ⇒ igualdade exata); reporta-se a contagem fora e o max |Δ|; um ponto fora basta para A1 falhar naquele horizonte, e a única categoria que explica é "alvo"; diagnóstico pré-declarado, nesta ordem: (1) definição do realizado multi-passo (retorno de h=7 composto × soma de log × retorno diário em t+h), (2) ajuste de preço (splits/dividendos — ADR 3.5.0001), (3) mapeamento de target_timestamp por calendário de pregão × dias corridos (a interseção h=7 menor de D-M5 é o indício), (4) caminho float32 (descartado para o alvo por D-M6, mantido na lista) · Alternativas: tolerância relativa à maior magnitude dos dois lados; amostrar pontos
Degrau: 1 (doc §5.4 A1 "meio ulp do tipo gravado na magnitude do valor"; sem ampliar a regra)
Base: doc §5.4, §5.6 (categoria "alvo"); medições D-M5, D-M6
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: não depois do passo 3 do D10
```

**Emenda pós-execução de D13 (desvio declarado):**
```
[decision:P] B3 — tolerância de A1 pela precisão de armazenamento efetiva
Escolha: opção 2 — tolerância de A1 = meio ulp de float32 no ponto (a precisão efetiva do anterior), com a PRÉ-CONDIÇÃO verificada, por horizonte, de que todo y_ant DO HORIZONTE é finito e exatamente representável em float32 e todo y_novo é finito (senão vale, para aquele horizonte, a regra de double acima, sem mudança); o resultado sob a regra original de double também é reportado; as linhas A10/A11 dos horizontes julgados pela regra float32 levam o rótulo de desvio pós-A1; emenda commitada antes de qualquer número de modelo do anterior; E4/E5 refeitas sob ela; a comparação de modelo (A10/A11) que A1 libera é rotulada no relatório interno como desvio pós-hoc · Alternativas: 1 — manter A1 pela regra de double (A1 falha por artefato de armazenamento; A10/A11 ficam not_compared:A1); 3 — manter A1 reprovado e adiar a emenda para outra issue · Decisor: humano (issue #232, comentário de 2026-10-23)
Base: doc §5.4 ("dentro da precisão de armazenamento do anterior"; meio ulp do tipo gravado); diagnóstico pré-declarado de D13 item 4 na E4 real: y_ant = float32(y_novo) em 937/937 pontos nos dois horizontes, |Δ| relativo máx 0,978·2⁻²⁴; com a regra de double, 934/937 fora, explicados como "alvo"; nenhum número de modelo do anterior calculado
Sensibilidade pré-registrada: nenhuma · Reversível: sim (ADR 8.2.0004)

[decision:C] B3-EXATO — critério float32 exato (refinamento dentro da B3)
Escolha: sob a pré-condição, A1 passa num ponto exatamente quando float32(y_novo) == y_ant (y_ant é o arredondamento ao float32 mais próximo de y_novo); max |Δ| e max |Δ|/|y| reportados só como informação · Alternativas: |Δ| ≤ np.spacing(float32(y))/2 (meio ulp "acima" — errado em potências de 2, onde o ulp abaixo é metade do acima)
Degrau: 1 (equivale ao meio ulp de float32 com a direção certa e ties-to-even — IEEE 754 round-to-nearest-even; ADR 8.2.0004 item 2b)
Base: ADR 8.2.0004; doc §5.4
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim
```

### D10 — Ordem das leituras
```
[decision:C] D10 — sequência obrigatória da Fase 4
Escolha: (1) commit do registro de hashes (D5), junto com o que D12 delega ao technical (lista de baselines comuns e fonte, colunas lidas); (2) reprodução e audit-reproduction (independem do anterior); (3) só então leitura de valor do anterior pelo andaime; (4) relatórios; a (ii) nunca altera a (i) nem a cópia julgada
Degrau: 1 (doc §5.2, ordem; §4.6; I1)
Base: doc §5.2, §4.6
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: não (é o objetivo)
```

## 8. Integrações

### Internas (com outras Stages/módulos)
- `evaluation` (application): comparador e DTO novos; o port
  `JudgedGenerationStore` ganha o leitor; `result_layer_digest` reusado.
- `evaluation` (adapters/out): `ParquetGoldStore` implementa o leitor (mesmo
  dono do layout `judged/`).
- `cli` + `composition_root`: subcomando `audit-reproduction` monta dois
  `ParquetGoldStore` (raiz julgada e descartável) e o `TomlPreregistrationSource`.
- Árvore de `060537fc` (git worktree destacado, só leitura de código): o
  `wire_dependencies` daquele commit roda a reprodução.
- 8.3: consome `read_judged_generation` e os dois relatórios.

### Externas
- Docker: imagem `sha256:b69a7620…`, `--cpus 6 --memory 8g --memory-swap 8g`.
- Nenhum serviço de rede; nenhuma tag nem comentário de issue.

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| A reprodução não sai bit a bit (estado não capturado pelas chaves) | B | A | parada e `[finding]` (I5); a tabela por classe localiza; nunca tolerância sem diagnóstico |
| Imagem `b69a7620…` removida antes da Fase 4 | B | A | conferir no início; não fazer `docker image prune`; sem ela, só diagnóstico e decisão humana |
| Reprodução escreve na partição viva por erro de caminho | B | A | I1–I2; `audit-reproduction` recusa raízes iguais; sha256 de `current/MANIFEST.json`, `ATTEMPTS.jsonl` e `CONTENTS.sha256` conferidos antes e depois |
| Valor do anterior lido antes do registro (forking paths) | B | A | D10; I6; o andaime só lê arquivo do registro |
| Definição dos baselines anteriores não recuperável | M | M | ficam fora do "modelo comum" e entram só em A2 (EQ-INTER item 1); registrado |
| Interseção h=7 menor que h=1 por definição diferente de `target_timestamp` | M | M | diagnosticar pelo calendário na Fase 4; se for definição do alvo, A1 o mostra |
| A1 falhar por armazenamento: o anterior gravou o alvo arredondado para float32 dentro de coluna `double` (**materializado** na E4: 937/937 pontos) | A | M | emenda B3 / ADR 8.2.0004: tolerância pela precisão efetiva com pré-condição verificada; resultado da regra original também reportado; comparação de modelo rotulada desvio pós-hoc |
| A1 falhar por definição do realizado de h=7 | M | M | critério e diagnóstico pré-declarados em D13; a comparação de modelo daquele horizonte para e a divergência é registrada com a categoria "alvo"; a regra não é afrouxada (seria desvio) |
| `env.platform` inclui o kernel do WSL (`6.18.54.1-microsoft-standard-WSL2`); uma atualização do WSL quebra a igualdade da foto | M | M | diagnóstico de **ambiente**, não de código: `[finding]`, sem rodar como R-BIT; registrar a versão do kernel antes da Fase 4 e não atualizar o WSL até a reprodução |
| Driver da reprodução divergir do código de `060537fc` | B | A | só wiring, por APIs idênticas nos dois commits; smoke test no HEAD; roda com a árvore de `060537fc` em `/app` |
| Tempo (~14 min de refresh; `h3` 625 s) e memória da reprodução | M | B | mesmos limites da 8.1; nada concorrente no Docker durante a corrida |
| O CI passar a buscar o oráculo | B | B | skip por variável de ambiente ausente; o teste nunca procura caminho padrão |

## 11. Critérios de aceitação

- [ ] **A1 — Registro antes da leitura (recorte D11).** `docs/reports/prior_evidence_registry.toml`
  (sha256, linhas, tipos físicos; os sha256 iguais aos de D-M1) commitado em
  commit próprio, junto com o que D12 delega ao technical; nenhum commit
  anterior a ele na branch contém valor de métrica, perda, p-valor, sinal,
  veredito ou realizado do anterior (metadados de forma permitidos); o
  `git log` mostra o registro antes de qualquer número do anterior nos
  relatórios.
- [ ] **A2 — Entrada e ambiente da reprodução.** Backup de entrada conferido
  (`sha256sum -c` + sha256 da listagem = `input_backup_sha256`);
  `environment.json` do driver igual, chave a chave, às chaves `code.*`/`env.*`
  da linha `started` do `ATTEMPTS.jsonl`, árvore de `060537fc` limpa,
  container pelo id da imagem, `cpu.max` e sha256 do `uv pip freeze` colados
  no technical §7 (I4).
- [ ] **A3 — Reprodução real bit a bit.** O driver roda em `060537fc` e grava
  `reproduction/scorecard.json` e `reproduction/environment.json`; o
  `audit-reproduction` do HEAD, lendo esses arquivos sem recalcular nada, sai
  `0` com `bit_identical = true`: identidade igual (`silver_content.digest`
  `7ac4c759…`, `dataset_fingerprint` `00e4406d…`, ref, partição),
  `result_layer_digest` dos dois lados = `7c7940d4…`, por classe R1/R2/R3 o
  número de valores comparados, zero diferentes e max |Δ| = 0 (contagem de
  diferentes para R1 não numérico) **reportados** em
  `docs/reports/reproduction_audit.md`; scorecard igual sem proveniência.
- [ ] **A3b — Driver testado.** `--check` do driver executado em `060537fc`
  (wiring + foto do ambiente, sem refresh) verde antes da reprodução; smoke
  test do driver no HEAD com dependências falsas (prova a lógica do driver,
  não o wiring de `060537fc`): chama refresh e depois scorecard, grava os bytes de
  `document_bytes(...)` no caminho fixo, recusa `data_root` sob
  `data/cohorts/` ou com `gold/`/`reproduction/` pré-existente; pré-checagem
  de refresh sintético em dois processos com `PYTHONHASHSEED` diferentes
  dando o mesmo `result_layer_digest` (I5).
- [ ] **A4 — Partição viva intocada.** sha256 de `current/MANIFEST.json`,
  `judged/ATTEMPTS.jsonl` e `CONTENTS.sha256` da cópia iguais antes e depois
  (I1); nenhum `judged/` nem `ATTEMPTS.jsonl` no `data_root` descartável.
- [ ] **A5 — Leitor da cópia julgada.** `read_judged_generation` com fake,
  real e suíte de contrato: devolve a geração íntegra; recusa arquivo
  faltando, a mais ou adulterado; sem cópia → erro; `check_port_coverage` e
  `check_fake_parity` verdes.
- [ ] **A6 — Comparador testado.** Unitários de `compare_reproduction`:
  gerações idênticas → `bit_identical`; mudança de 1 ulp num float R2, num R3
  e de 1 num inteiro R1 → diferença na classe certa com o max |Δ| certo;
  `-0.0` × `0.0` distintos; `started_at`/`finished_at` diferentes não contam;
  identidade diferente ou `result_layer_digest` ≠ `expected_result_digest` →
  `bit_identical = false`; teste de completude: toda coluna de todo
  `GoldTableSchema` tem classe em `REPRODUCTION_CLASSES`.
- [ ] **A7 — R-BIT-COMMIT registrado.** Lista dos arquivos de `src/` do diff
  `060537fc..64b8a17d` (base fixa) e, por arquivo, igualdade de `ast.dump` com
  docstrings removidos (Python 3.12 do container); lista separada dos
  arquivos de `src/` tocados pela própria 8.2 (`64b8a17d..HEAD`), cada um
  justificado como fora do caminho de refresh/scorecard; tudo no relatório
  de reprodução, com a declaração de que o claim é o da execução em
  `060537fc`.
- [ ] **A8 — Claim declarado.** O relatório de reprodução afirma (a), cita (b)
  da 7.1 e declara que (c) não foi executada (D4).
- [ ] **A9 — EQ-MUST A1 (D13, emendado por B3).** Por horizonte, T∩
  reportado; a pré-condição (todo y_ant do horizonte finito e exatamente
  representável em float32; todo y_novo finito) conferida e reportada; todo
  ponto de T∩ conferido com `float32(y_novo) == y_ant` (pré-condição
  verdadeira — B3-EXATO) ou |y_novo − y_ant| ≤ 2⁻⁵³·|y_ant| (pré-condição
  falsa), com a contagem fora, max |Δ| e max |Δ|/|y| reportados, e o
  resultado sob a regra original de double também reportado — ou a
  divergência é registrada com a categoria "alvo", o diagnóstico
  pré-declarado percorrido, e a comparação de modelo daquele horizonte para;
  as linhas A10/A11 dos horizontes julgados pela regra float32 levam o
  rótulo de desvio pós-A1 (ADR 8.2.0004).
- [ ] **A10 — EQ-MUST A2 (D12 c, e).** Para pinball por nível comum, PICP e
  MPIW do par 80 %: m_A (código novo sobre as predições anteriores, na
  variante e na amostra que o anterior usou — D7, D12) contra m_ant dentro de
  max(R2 com o u_q de D12, precisão de armazenamento), ou explicada por uma
  linha da tabela de definições da §5.4 com a previsão verificada, ou "não
  realizável", ou `[finding]`.
- [ ] **A11 — Tabela de sentido por horizonte (D12 a, b, d).** Para h ∈ {1, 7}:
  (1) candidato × candidato, sempre — deltas com sinal m_novo − m_A em T∩ na
  pinball de cada nível comum, no PICP e no MPIW do par 80 %, e o lado do
  nominal do PICP 80 % (banda de Wilson 95 % do lado novo) de m_novo e de
  m_A; (2) por baseline comum (tabela vazia registrada se não houver) — sinal
  de (candidato − baseline) na pinball de cada nível comum, dentro de cada
  lado, o lado anterior por m_A em T∩ (doc §5.5), e DM — só o reportado
  por cada lado, sem m_A — (sinal de d̄ normalizado e rejeição — D8); igual/divergente por
  célula; toda divergência de sentido com a categoria aplicável pela tabela
  da §5.6 e (a)(b)(c) verificados, ou `[finding]` não explicado.
- [ ] **A12 — Relatório de equivalência.** `docs/reports/equivalence_audit.md`
  com os hashes dos dois lados (registro + `generation_digest`), as
  diferenças declaradas entre as pipelines como contexto, A9–A11, a lista de
  `[finding]` não explicados, o inventário de andaime e a aposentadoria
  (doc §5.7: comparações registradas, nada oficial depende dele, motivo).
- [ ] **A13 — Teste fora do CI.** `tests/equivalence/test_official_vs_prior_evidence.py`:
  sem as variáveis de ambiente → `skipped` com o motivo e o caminho do
  registro (visto com `-rs`); com o oráculo → passa, inclusive a igualdade
  entre a tabela declarada no teste e a parseada do `equivalence_audit.md`;
  a função de checagem de hash tem teste unitário sempre ativo (`tmp_path`,
  roda no CI): arquivo adulterado ou faltando → falha; nunca escreve registro
  nem relatório.
- [ ] **A14 — Isolamento do anterior.** Nenhum módulo de `src/` lê
  `data/analytics/` nem importa `tests/equivalence/` (grep + import-linter).
- [ ] **A15 — Roadmap e gates.** Bloco da 8.2 corrigido (contratos, arquivos,
  camada) e linha no Histórico; `make check` verde; cobertura ≥ 90 % por
  arquivo de `src/` tocado.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? — §4: método do
  port, função pura, DTO, subcomando e formato do registro.
- [x] Toda decisão em §7 tem fonte rastreável? — D1–D13 com âncora no doc de
  domínio, ADRs, código ou medição D-M1–D-M6.
- [x] Toda integração externa tem contrato definido (interface, formato, auth)?
  — só Docker, com a imagem e os limites da 8.1; nenhuma rede.
- [x] Decisões com alternativa real descartada têm ADR escrito? — 8.2.0001
  (D1, D2, driver), 8.2.0002 (D3), 8.2.0003 (D5, D6), 8.2.0004 (emenda B3
  de D13); D4, D7, D8, D10–D13 aplicam o doc de domínio sem alternativa real
  fora dele.
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? — 8.1 `done`
  (PR #231 mergeado).
- [x] Stage cabe em ~3–12 Tasks (ver [`CONVENTIONS.md`](../../CONVENTIONS.md) §6)?
  — estimativa 9–10: registro; port + fake + contrato + real; DTO +
  comparador; CLI + wiring; corrida da reprodução + relatório; leitores do
  andaime + interseção + A1; A2; sentido; teste + relatório de equivalência.
- [x] Riscos críticos têm mitigação plausível? — §10 (reprodução não bit a
  bit, imagem, escrita na partição viva, ordem de leitura).
- [x] Cada mecanismo novo passou pelo **teste da solução mais direta**: não é caso especial/tipo/métrica novo remendando, local, um sintoma que recorre em outros consumidores e teria tratamento mais simples/geral em outra camada (concern compartilhado). Captura assim → piso declarado + issue, não solução local. — (i) a reprodução não ganha orquestrador: reusa `RefreshGold` + scorecard pelo composition root do próprio commit (o caminho mais direto); (ii) identidade/fingerprint: reusa `silver_content`, `dataset_fingerprint` e `result_layer_digest` da 8.1 — nenhum hash novo; (iii) o leitor da cópia julgada fica no port (concern compartilhado com a 8.3), não num atalho de leitura de diretório na 8.2; (iv) o comparador é a única peça nova de cálculo em `src/` e é genérico sobre `GoldGeneration` (serve a uma futura R-ENV sem mudar de forma); (v) os leitores da evidência anterior não entram em `src/` (doc §5.1 item 3); (vi) nenhuma métrica nova: A2 aplica os serviços de domínio existentes.
- [x] A Stage reabre alguma regra do doc de domínio? — não: D7 e D8 são
  leituras do texto da §5.3–§5.4 aplicadas à forma medida (I8).
- [x] Algum valor da evidência anterior foi lido neste concept? — nenhum
  valor protegido pelo recorte de D11: só schema, contagens, chaves, datas e
  rótulos de definição (D9, com a ressalva declarada do conjunto de
  `direction`).

## 13. Questões em aberto

- [ ] Quais arquivos de D-M1 entram no registro (todo arquivo que o andaime
  lê) e quais colunas de cada um — technical (Fase 3B); entra no commit do
  registro (D10, passo 1).
- [ ] Fonte da definição dos baselines anteriores e lista de comuns (D12 a) —
  technical; entra no commit do registro, antes do passo 3 do D10. Sem
  definição recuperável, a tabela por baseline fica vazia (registrada); a
  parte candidato × candidato do A11 e o A2 seguem de pé.

### Checkpoint A, rodada 1 — disposição

| achado | disposição |
|---|---|
| CA-1 / DT-1 | corrigido — driver `scripts/reproduce_judged_generation.py` como contrato (§4), D2, A3, A3b, ADR 8.2.0001 |
| CA-2 | corrigido — D11 (decisão da mestra), I6, A1, ressalva em D9 |
| CA-3 | corrigido — D12 (b), A11 (1), §13 |
| CA-4 | corrigido — medição D-M6 (`target_return: double`), D13, risco em §10 |
| CA-5 / DT-3 | corrigido — D4 "sem consumidor em `src/`"; u_q e precisão de m_ant em D12 (e) |
| CA-6 | corrigido — roadmap (DoD sem "entre ambientes" incondicional; `evaluation_commands.py`; driver) |
| DT-2 | corrigido — D12 (a), D10 passo 1, §13 |
| DT-4 | corrigido — D12 (c, d); sinal normalizado em D8 |
| DT-5 | corrigido — D13, A9 |
| DT-6 | corrigido — I4, A2 (`environment.json` chave a chave, `cpu.max`, `uv pip freeze`) |
| DT-7 | corrigido — D6, A13, ADR 8.2.0003 itens 5–6 |
| DT-8 | corrigido — §4 (`REPRODUCTION_CLASSES` completo, max \|Δ\| só numérico, `expected_result_digest`), A6, ADR 8.2.0002 |
| DT-9 | corrigido — I5, A3b |
| N1 (r2) | corrigido — foto pelo mesmo produtor da `started` (closure `run_confirmatory_evaluation_for`, acesso privado justificado), parâmetros fixos, risco do kernel WSL em §10 |
| N2 (r2) | corrigido — R-BIT-COMMIT até a base fixa + lista dos acréscimos da 8.2; `--check` em `060537fc`; escopo do smoke test declarado |
| N3 (r2) | corrigido — justificativa do `/driver` em D2 |
| N4 (r2) | corrigido — y_novo pelo `ReadTrainingGrid` (D-M6) |
| DT-10 | corrigido — premissa em §3 (o `RefreshGold` não recebe `JsonInferenceManifest`); reconferência no technical |

## 14. O que fica para a 8.3

- Plots e dossiê a partir de `judged/<ref>/` pelo `read_judged_generation`
  (nunca de `current/` nem da geração reproduzida); o dossiê cita o
  `reproduction_audit.md` como prova do claim (a), com o `generation_digest`
  e o `result_digest`.
- Nenhum gráfico compara com o anterior (P-EDIT); o `equivalence_audit.md`
  fica só no repositório.

## 15. Referências

- [`../../overview.md`](../../overview.md) — §2 (oráculo, nunca autoridade), §3, §4 (Reprodutibilidade), ASSUM-4, R-REPRO-1
- [`../../roadmap.md`](../../roadmap.md) — Stage `8.2-equivalence-audit`, 8.1, 8.3
- Doc de domínio [`reproduction-equivalence-and-reporting`](../../domain/evaluation/reproduction-equivalence-and-reporting.md) §2.1–§2.2, §4, §5, §9
- Concept 8.1 §14 e technical 8.1 §7 (Etapa R; erratas O1/O2)
- ADRs desta Stage: prefixo `8_2_` em [`../../adr/`](../../adr/)
- ADRs consumidos: 0.0.0060–0.0.0062, 6.4.0005, 6.5.0003, 6.5.0006, 7.1.0003, 8.1.0002–8.1.0004
- Issue #232 §Referências (Python 3.12 Glossary "docstring" e `ast`; pytest "How to use skip and xfail"; DVC; NumPy `assert_allclose`; pytest-regressions)
