# Conventions

Regras prescritivas. Não são sugestões.

Hierarquia conceitual (Step → Stage → Task) e fluxo de fases vivem em
[`PIPELINE.md`](./PIPELINE.md). Este documento fixa
nomes, frontmatter, status, branches, commits, versionamento e tamanhos.

---

## 0. Mapa de autoridade (fonte única por classe de regra)

Cada classe de regra tem **um doc dono** — a definição completa vive só
nele; os demais docs apenas apontam. Encontrou eco extenso divergente?
O dono vence; corrija o eco.

| Classe de regra | Doc dono (editar LÁ) |
|---|---|
| Nomenclatura, frontmatter, status, formato de branch/commit/título de PR, tamanhos | `CONVENTIONS.md` (este doc) |
| Fluxo git operacional, gates de PR, hotfix/release, comportamento bloqueante | [`GIT-WORKFLOW.md`](./GIT-WORKFLOW.md) |
| Hierarquia Step/Stage/Task, atomicidade, fases e gates conceituais, litmus issue×Stage, exceções | [`PIPELINE.md`](./PIPELINE.md) |
| Checklists operacionais de gate (concept / technical / saída da Stage) | [`RUNBOOK-STAGE-LIFECYCLE.md`](./RUNBOOK-STAGE-LIFECYCLE.md) Passos 5/7/10 |
| Arquitetura e regras de import | [`LAYOUT.md`](./LAYOUT.md) |
| Procedimento de auditoria e falsos verdes | skills `stage-audit` / `issue-audit` |

**Regra do eco:** citar uma regra fora do doc dono é permitido como
**1 frase + ponteiro** (regra acionável no ponto de uso); o texto
normativo completo vive só na casa dona.

---

## 1. Nomenclatura

### Arquivos e pastas

| Item | Padrão | Exemplo |
|---|---|---|
| Pasta de Stage | `N.M-<kebab-slug>` (Step.Stage, sem zero-padding) | `1.1-bootstrap`, `2.3-s3-source`, `15.2-multi-tenant` |
| Concept de Stage | `concept.md` (fixo, dentro da pasta da Stage) | `docs/stages/1.2-domain-model/concept.md` |
| Technical de Stage | `technical.md` (fixo) | `docs/stages/1.2-domain-model/technical.md` |
| ADR de Stage | `N_M_NNNN-<kebab-slug>.md` em `docs/adr/` (`N.M` herda da Stage; `NNNN` 4 dígitos, sequencial **dentro do prefixo `N_M`** — o prefixo no nome do arquivo é o separador, não há subpasta por Stage) | `docs/adr/2_3_0001-stream-vs-batch.md` |
| ADR global | `0_0_NNNN-<kebab-slug>.md` em `docs/adr/` (`N.M` fixo em `0.0`; `NNNN` 4 dígitos, sequencial dentro do prefixo `0_0`) | `docs/adr/0_0_0001-hexagonal-from-day-one.md` |
| Runbook | `<kebab-slug>.md` | `docs/runbooks/local-dev-setup.md` |
| Overview / Roadmap | fixos na raiz de `docs/` | `docs/overview.md`, `docs/roadmap.md` |

### Idioma do código

**Todo código-fonte deve ser escrito em inglês.** Esta regra aplica-se a:

- Nomes de arquivos e pastas de código (`.py`, `.sql`, `.yaml` de configuração interna)
- Classes, funções, métodos, variáveis, parâmetros, constantes
- Campos de DTO, modelos Pydantic, entidades de domínio
- Valores de enum internos (exceto enums que espelham valores de um sistema externo)
- Nomes de tabelas, colunas e índices do banco de dados (nossas tabelas)
- Nomes de módulos e pacotes Python

**Exceção estrita** — valores de string que identificam dados de um sistema
externo replicado (status, tipos, nomes de colunas de schemas espelhados em
queries SQL e mappers) podem preservar o idioma/grafia original da fonte.

Comentários e docstrings permanecem em português (conforme §4 de commits/PR).

### Slugs de Stage

- **Kebab-case, em inglês**, mesmo que o conteúdo seja em português.
- Curto (2–4 palavras). Descreve o **resultado**, não a atividade.
- O **número `N.M`** é prefixo da pasta/branch, **não conta como palavra
  do slug**.
- Bom: `1.1-bootstrap`, `2.3-s3-source-adapter`, `4.1-tenant-context`.
- Ruim: `1.1-fazer-setup`, `2.3-implementar-s3`, `4.1-mexer-no-tenant`.

### Numeração

- **Step:** identificador **numérico**, sequencial, sem zero-padding. Não
  recicla — Step 4 cancelado fica vago, Step 5 continua sendo Step 5.
  **Cresce indefinidamente.** Cada Step tem um **escopo temático claro**
  (ex.: "ingestão medalhão bronze", "feature engineering", "harness
  walk-forward", "serving de previsões quantílicas"; ver
  [`PIPELINE.md`](./PIPELINE.md) §4.1). **Nunca use letra** para um Step —
  não existe "Step F" para feature engineering, é o Step 3. A **única**
  exceção é `X`.
- **`X` — bucket de escopo órfão/futuro.** Trabalho **já definido** como
  Stage futura, mas cujo **Step-lar ainda não foi criado/planejado**, fica
  em stand-by sob `X` (ex.: `X.4-quantile-serving`). É o estado
  **pré-identidade**. **Migração obrigatória:** quando o Step que comporta o
  escopo for planejado, o item migra para lá **com o número desse Step** (se
  o escopo se manteve) — ou se desdobra em mais Stages, podendo virar um Step
  inteiro. Ganhar um número = achou seu Step. `X` é rótulo fixo, nunca
  renumerado (número = identidade, não posição).
- **Ordem de implementação = `depends_on`, não o número.** Como o número é
  identidade e não posição, a sequência cronológica real de implementação é
  dada pelo `depends_on` de cada Stage/issue — não pela ordem dos números.
- **Stage:** `N.M` dentro do Step `N`. Não recicla.
- **Task:** `task-NN` dentro do `technical.md` da Stage, zero-padded
  (`task-01`, `task-02`).
- **ADR de Stage:** nome do arquivo `N_M_NNNN-<slug>.md` em `docs/adr/`;
  `adr_id` no frontmatter `N.M.NNNN`. `N.M` herda da Stage; `NNNN` é
  sequencial **dentro do prefixo `N_M`** (4 dígitos, não recicla) — o
  prefixo no filename é o separador namespace, **não há subpasta por
  Stage**. Cross-ref usa `adr_id` completo (ex.: `2.3.0001`) — sem
  ambiguidade entre Stages.
- **ADR global:** ADRs tomados antes ou fora do escopo de uma Stage
  específica (ex.: decisão fundacional de arquitetura). Vivem na
  mesma pasta `docs/adr/` (Stage e global coexistem; o prefixo
  `N_M` no filename basta para distinguir). Usam `N.M = 0.0` fixo —
  nome do arquivo `0_0_NNNN-<slug>.md`; `adr_id: 0.0.NNNN`. `NNNN`
  sequencial dentro do prefixo `0_0`.

---

## 2. Frontmatter

Todo doc tem frontmatter YAML no topo. Campos comuns + campos por tipo.

### Campos comuns (obrigatórios em todo doc)

```yaml
---
title: string                    # título humano em português
description: string              # 1 frase, o que este doc é
when-use: string                 # quando consultar este doc (para Claude e humanos)
keywords: [list, of, strings]    # termos para busca/grep
status: <enum por tipo de doc — ver §3>      # concept/technical: draft | done | archived
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
---
```

### Campos adicionais por tipo

**`overview.md`:**
```yaml
project_name: string
stakeholders: [list]
```

**`roadmap.md`:**
```yaml
last_reviewed_at: YYYY-MM-DD     # forçado a atualizar ao fechar Stage
```

**`concept.md` e `technical.md` (de Stage):**
```yaml
stage_id: N.M-<slug>             # bate com o nome da pasta
stage_title: string              # título humano da Stage
step_id: N                       # Step que contém esta Stage
step_title: string               # título humano do Step
depends_on: [list of stage_ids]  # vazio se nenhuma
```

**`technical.md` (adicional):**
```yaml
concept_ref: ./concept.md        # caminho relativo
issue_id: integer                # número da issue do GitHub (ex: 42)
branch: feat/<num-issue>-<N-M>-<slug>   # ex: feat/42-2-3-s3-source-adapter
tasks_count: integer             # quantas Tasks tem
```

**ADRs:**
```yaml
adr_id: N.M.NNNN                 # Stage: 2.3.0001 — N.M herda da Stage; Global: 0.0.NNNN
decision: string                 # 1 frase resumindo a decisão
status: proposed | accepted | superseded | deprecated
superseded_by: N.M.NNNN          # ex: 2.3.0002 — apenas se status=superseded
context_stage: N.M-<slug>        # Stage em que a decisão foi tomada (mesmo para ADRs globais)
```

**Runbooks:**
```yaml
runbook_id: kebab-slug
triggers: [list of strings]      # quando rodar este runbook
estimated_duration: string       # ex.: "15min"
```

---

## 3. Status — máquina de estados

### 3.1 `concept.md` e `technical.md` — máquina simplificada (dois estados)

```
draft ◄──────► done ──────► archived
```

- **`draft`**: rascunho, desde a criação. Não pode ser usado como input
  para o gate da fase seguinte enquanto não estiver `done`.
- **`done`**: aceito no gate humano. Pode **regredir para `draft`**
  quando uma fase posterior (tipicamente Fase 3B revisando o concept,
  ou Fase 4 revisando o technical antes do início da execução) revela
  gap material — ver §3.2.
- **`archived`**: foi `done`, mas a Stage foi descartada/recortada e o
  artefato saiu do plano vivo. Mantido por histórico (ver §5).

Por que dois estados: na prática os estados intermediários
(`in_progress`, `review`) não eram usados — o gate humano flipa direto
`draft → done` no commit reservado. Manter máquina enxuta reduz fricção
sem perder rastreabilidade (git log carrega a transição).

### 3.2 Regressão `done → draft`

Permitida (e esperada) quando o trabalho de uma fase posterior revela
gap material em um artefato já `done`. O caso típico é a Fase 3B
revelando lacuna no Concept aprovado.

Procedimento:

1. Reabrir o artefato. Mudar `status` de volta para `draft`. Atualizar
   `updated_at`.
2. Commit reservado de regressão (não segue Conventional Commits no
   título; segue a forma fixa):
   ```
   chore(concept): revert to draft — revision-from-technical: <motivo curto>

   Refs #<num-issue>
   ```
   Variantes: `chore(technical): revert to draft — revision-from-execution: <motivo>`.
3. Aplicar a correção, re-rodar o gate da fase, novo commit reservado
   de aprovação (ex.: `stage N.M: conceptual approved`).

**Invariante de início da Fase 4 (execução):** `concept.status == done`
**e** `technical.status == done` simultaneamente. Se qualquer um regredir
para `draft`, a Fase 4 trava até ambos voltarem a `done` (Passo 8 do
[`RUNBOOK-STAGE-LIFECYCLE.md`](./RUNBOOK-STAGE-LIFECYCLE.md)).

Regressões depois de iniciada a Fase 4 caem em §3.4 (seção pós-execução
do technical) — sem mudar status; usar `[decision]`/`[finding]`/`[deviation]`
ou loop reverso completo.

### 3.3 Outros artefatos — máquina ampliada

Demais artefatos versionados (overview, roadmap) usam o conjunto
ampliado quando faz sentido — em prática:

- **`overview.md`:** `draft → done`. `in_progress`/`review` opcionais.
- **`roadmap.md`:** permanece `in_progress` da Stage `1.1-bootstrap` até
  o projeto encerrar (não há `done` para o roadmap inteiro; o que vai a
  `done` são as Stages dentro dele).
- **ADRs:** máquina própria — `proposed | accepted | superseded | deprecated`.
- **Runbooks, skills:** máquinas próprias documentadas em PIPELINE §13
  (skills) e em seus templates (runbooks).

### 3.4 Seção pós-execução do `technical.md` (§7 do template)

A seção §7 ("Execução — post-hoc") do `technical.md` é **a única parte
editável após `status: done`** — **enquanto a Stage está em execução**,
isto é, **antes de a branch da Stage mergear** em `develop`/`main`. O
objetivo do freeze é impedir que a execução reescreva o plano aprovado
sem rastro; desvios vão para a §7, onde são revisados.

**Depois do merge**, o `technical.md` vira **doc de referência mutável**:
alinhá-lo à realidade (ex.: renomear identificadores que mudaram no
código, padronizar tags) é legítimo e dispensa cerimônia — o plano
original aprovado permanece no git. Regras durante a janela de execução:

- Delimitada por marcadores `<!-- BEGIN: post-execution -->` e
  `<!-- END: post-execution -->`. Qualquer diff fora desses marcadores
  em um `technical.md` com `status: done` **cuja Stage ainda não mergeou**
  é rejeitado pelo script `scripts/check_technical_postexec.py` (rodado
  no pre-commit e no Passo 10 do runbook). A detecção de merge usa
  ancestralidade do commit `stage N.M: technical approved` em relação a
  `develop`/`main`; Stage mergeada → checagem pulada.
- **`updated_at` do frontmatter não muda** com edições nessa seção. O
  metadado por entrada (data + autor no header) é o audit trail.
- **Regra de pergunta antes da nota:** ao encontrar durante a Fase 4
  algo não previsto em outras seções do `technical.md`, no `concept.md`
  ou em ADRs, **pausar a execução**, levantar a pergunta para o humano
  com 2–4 opções e uma marcada como **recomendada** + razão (via
  `AskUserQuestion` ou equivalente), e só então registrar a entrada.
- Entradas seguem três categorias: `[decision]` (decisão tomada durante
  a execução), `[finding]` (gap a tratar em próxima Stage), `[deviation]`
  (ajuste pequeno aplicado em relação ao plano). **Tags sempre em inglês**
  (são identificadores, como código — §1); o corpo da entrada é em PT.
  Formato detalhado no template `stage-technical.md` §7.
- **Durante a execução** (Stage não mergeada), mudar algo em §1–§6 do
  `technical.md` após `done` exige regressão para `draft` (§3.2). Nunca
  editar §1–§6 silenciosamente nessa janela. Pós-merge a restrição não
  se aplica (doc de referência mutável).

### 3.5 Diagrama legado (mantido para overview/roadmap)

```
draft ──────► in_progress ──────► review ──────► done
  │                │                  │             │
  └─► archived ◄───┴──────────────────┴─────────────┘
```

### Exceção — docs estruturais do template

Os documentos estruturais do template — `PIPELINE.md`, `CONVENTIONS.md`,
`LAYOUT.md`, `GIT-WORKFLOW.md`, `RUNBOOK-STAGE-LIFECYCLE.md` (todos em
`docs/`), `README.md` (raiz e boilerplate) e `CLAUDE.md` — são
**exceção** ao frontmatter padrão de §2: **não carregam
`created_at`/`updated_at`/`status`**. Justificativa:

- São contratos do template, não artefatos versionados por Stage.
- Mudam pouco e por motivos amplos (revisão estrutural, refactor de
  pipeline); o histórico fica no git, sem necessidade de máquina de
  estado.
- Frontmatter em docs que mudam pouco tende a ficar stale (`updated_at`
  esquecido); melhor ausente do que mentindo.

A mesma exceção vale para `SKILL.md` (justificada em PIPELINE §13 —
lifecycle expresso por `metadata.status`).

### Mapeamento gate ↔ commit ↔ status

| Gate aprovado | Commit (mensagem reservada) | Status do artefato |
|---|---|---|
| Overview | `docs(overview): approved` | `overview.md → done` |
| Roadmap | `docs(roadmap): approved` | `roadmap.md → in_progress` (vive até o projeto acabar) |
| Concept da Stage (Fase 3A) | `stage N.M: conceptual approved` | `concept.md → done` |
| Concept regredido (3B revelou gap) | `chore(concept): revert to draft — revision-from-technical: <motivo>` | `concept.md → draft` |
| Technical da Stage (Fase 3B) | `stage N.M: technical approved` | `technical.md → done` |
| Technical regredido (4 revelou gap antes da execução) | `chore(technical): revert to draft — revision-from-execution: <motivo>` | `technical.md → draft` |
| Stage completa (Fase 4) | `stage N.M: complete` | Stage N.M no roadmap → `done` |

**Regras:**
- **Pré-requisito de Fase 3A (bloqueante):** a Stage só pode iniciar a
  Fase 3A (criar `concept.md` em qualquer estado, inclusive `draft`)
  **se já existir uma issue correspondente no backlog do GitHub**,
  verificável via `gh issue view <num>`. Sem issue: parar e criar a
  issue antes de qualquer artefato. O `issue_id` registrado no
  frontmatter do `technical.md` é o ponto de verificação programática
  (ver `scripts/check_stage_issue.py` em `make docs-check`).
  Issue-first é princípio bloqueante ([`./GIT-WORKFLOW.md`](./GIT-WORKFLOW.md)
  §Princípios fundamentais #1).
- `concept.md` só pode estar `done` se passou no checklist de validação
  interno (§12 do template).
- `technical.md` pode entrar em `draft` a qualquer momento — não precisa
  esperar `concept.md` estar `done`. **Mas** o gate da Fase 3B
  (`stage N.M: technical approved`) exige `concept.status == done` no
  momento da aprovação.
- Fase 4 só pode iniciar (Passo 8 do runbook) com `concept.status == done`
  **e** `technical.status == done` simultaneamente.
- Stage só pode ser marcada `done` no `roadmap.md` se `concept.md` e
  `technical.md` estão `done` **e** o gate de saída da Stage foi cumprido
  (§3 do `technical.md`).

---

## 4. Branches e commits

### Branches

**Uma Stage = uma issue + um branch.** O branch carrega todos os
commits da Stage, do `conceptual draft` ao `complete`, e abre PR contra
`develop` quando a Stage termina (premissa
[`GIT-WORKFLOW.md`](./GIT-WORKFLOW.md)).
**Não há sub-PRs internos da Stage.**

Formato: `<tipo>/<num-issue>-<N-M>-<slug>` — `N.M` em kebab (Stage 2.3
vira `2-3`). Tipo segue GIT-WORKFLOW (`feat` para Stage nova, `fix`
para correção via Stage, `refactor`, etc.; em geral `feat`).

```
develop
├── feat/42-1-1-bootstrap            # Issue #42, Stage 1.1
├── feat/57-1-2-domain-model         # Issue #57, Stage 1.2
├── feat/89-2-3-s3-source-adapter    # Issue #89, Stage 2.3
└── docs/<change-desc>               # mudanças só de docs, fora de Stage
```

**Revisões pós-Stage** (branches criadas depois que o PR da Stage foi
mergeado) voltam ao formato **genérico** definido em
[`./GIT-WORKFLOW.md`](./GIT-WORKFLOW.md) §Branches —
`<tipo>/<num-issue>-<slug>`, **sem `<N-M>`**. O `<N-M>` identifica a
execução da Stage; depois que ela fechou, o trabalho passa a ser
bug/chore/doc normal, com nova issue própria. Rastreabilidade fica no
`Refs #<num-issue>` do commit, não no nome da branch.

Promoção de `develop` para `main` ocorre na release (ver GIT-WORKFLOW).

### Commits

Há **duas classes** de mensagens de commit:

#### (a) Commits de Task — Conventional Commits + `[N.M/task-NN]` + `Refs #<issue>`

```
<tipo>(<escopo>): <descrição imperativa em português> [N.M/task-NN]

- <bullet 1: o que mudou e por quê — 1 frase>
- <bullet 2: outro aspecto da mesma mudança lógica>
- <bullet 3+: opcional, conforme a complexidade da Task>

Refs #<num-issue>
```

Tipos: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`,
`style`, `build`, `ci` (lista espelhada em `ALLOWED_TYPES` de
`scripts/check_commit_msg.py` — o hook é o gate; mudou lá, atualizar aqui).

**Escopo mínimo (regra de ouro):** o `<escopo>` é o **menor recorte
que ainda faz sentido sozinho** — feature/módulo/bounded context da
mudança, **NÃO** o nome da Stage. Quanto mais estreito, melhor.
**Escopo em ASCII/kebab** (mesmo critério de slug de branch: ver §1)
para não exigir acentos no terminal; descrição é livre em PT-BR
acentuado:

- ✅ `feat(ingestion): adicionar S3 source adapter` — escopo é o BC
  `ingestion`, descrição em PT.
- ✅ `fix(payment.retry): limitar backoff exponencial em 30s` —
  escopo pode ser sub-módulo (`payment.retry`) quando isso desambigua.
- ❌ `feat(stage-2.3): adicionar S3 source adapter` — Stage não é escopo.
- ❌ `chore(repo): um monte de fixes` — escopo amplo demais; quebrar
  em vários commits com escopos mínimos diferentes.

Se a mudança realmente toca vários escopos independentes (cross-cut),
quebre em **vários commits** — um por escopo. "Sou preguiçoso, deixa
tudo num commit só" é red flag.

**Body em bullet points, sempre (≥ 1 bullet).** O body explica **o
quê** e **por quê** em itens de 1 frase. Listas longas (>8 bullets)
sinalizam Task grande demais; agrupar ou quebrar. Permitido omitir
body **apenas** em commits triviais e auto-explicativos (rename
puro, ajuste de typo) — e mesmo assim com `Refs` no rodapé.

Subject e body em **português** (ver [`./GIT-WORKFLOW.md`](./GIT-WORKFLOW.md)
§Princípios fundamentais #3); escopo permanece em ASCII/kebab;
`Refs #<num-issue>` no rodapé.

Exemplos (rodapé `Refs #89` em todos):

```
feat(ingestion): adicionar S3 source adapter [2.3/task-01]

- Implementar IngestionSource port adapter usando aioboto3
- Streamar objetos multipart em chunks de 8MB para limitar RSS
- Mapear erros do client S3 para IngestionError preservando causa

Refs #89
```

```
test(ingestion): cobrir happy path do adapter S3 [2.3/task-02]

- Fake do aiobotocore client devolvendo objeto de 3 partes
- Assertar que chunks chegam ordenados e concatenação bate com input
- Cobrir mapeamento credenciais ausentes → IngestionError

Refs #89
```

```
docs(roadmap): marcar stage 2.3 como done [2.3/--]

- Mudar status da stage 2.3-s3-source-adapter para done
- Atualizar last_reviewed_at no frontmatter do roadmap

Refs #89
```

**Um commit por Task.** Se uma Task precisou de mais de um commit, ela
estava grande demais — fica como lição para a próxima.

##### Tag `[N.M/--]` — commit no branch da Stage que não pertence a uma Task

`[N.M/--]` (dois hífens) é o **placeholder de off-task**: marca commits
feitos no branch da Stage que **não fazem parte** de uma das Tasks
numeradas em `technical.md` §2. Usar quando:

- **Atualização de roadmap/overview** ao fechar a Stage:
  `docs(roadmap): marcar stage 2.3 como done [2.3/--]`
- **Hotfix dentro do branch da Stage** para destravar `make check`/CI
  antes da próxima Task (ex.: arquivo do template fora do escopo da
  Stage que quebrou após upgrade de dep):
  `fix(tooling): restaurar make check no scaffold limpo [1.1/--]`
- **Reordenação puramente mecânica** que não cabe em Task (ex.:
  renomear arquivo já incluído numa Task anterior):
  `chore(repo): renomear helpers/io.py para helpers/files.py [2.1/--]`

Regras do `[N.M/--]`:

1. **Tipo, escopo e `Refs #<issue>` continuam obrigatórios** — só a
   posição da Task vira `--`. Não é "vale-tudo".
2. **Justificativa no body, sempre.** Diga **por que** isto não foi uma
   Task formal (urgência, escopo cruzado, descoberta pós-`approved`).
   Um `[N.M/--]` sem justificativa é red flag — provavelmente devia
   ter sido uma Task ou uma regressão do `technical.md` (§3.2).
3. **Não substitui regressão.** Se o gap exige reescrita do
   `concept.md`/`technical.md` §1–§6, usar `chore(concept|technical):
   revert to draft — ...` (§3.2), **não** um `[N.M/--]`.
4. **Não é commit reservado de gate.** Para os gates fixos use as
   mensagens reservadas de §4(b) (`stage N.M: ... approved`, etc.).
5. **Frequência saudável: 0–2 por Stage.** Três ou mais é sinal de
   Stage mal recortada — escopo escapou do `technical.md`.

##### Tag de issue avulsa — `[#<num>/task-NN]` e `[#<num>/--]`

Commits de **issue avulsa** (sem Stage; fluxo operacional em
[`PROMPT-issue-single-session.md`](./PROMPT-issue-single-session.md)) usam a
mesma mecânica de tag, trocando `N.M` pelo número da issue prefixado com `#`:

- Sub-task da issue: `<tipo>(<escopo>): <descrição> [#68/task-01]`
- Off-task no branch da issue: `[#68/--]` — mesmas regras do `[N.M/--]`
  (tipo/escopo/`Refs` obrigatórios + justificativa no body)
- Sufixo `-extra` para sub-task de teste nascida da auditoria de testes
  (vale nas duas formas): `test(<escopo>): cobrir <X> [#68/task-03-extra]`
  ou `[N.M/task-NN-extra]`

A tag de issue avulsa e o sufixo `-extra` viajam na **descrição livre** do
subject (UTF-8), então o hook `commit-msg` não os rejeita; a conformidade com
o formato é garantida no code review.

#### (b) Commits reservados de gate — texto fixo, não seguem Conventional Commits

Marcam aprovação de fase no branch. No branch de uma Stage, carregam
`Refs #<num-issue>` no rodapé:

```
stage N.M: conceptual draft

Refs #<num-issue>
```

Variantes (mesma estrutura):
- `stage N.M: conceptual approved`
- `stage N.M: technical draft`
- `stage N.M: technical approved`
- `stage N.M: complete`

Variantes **de regressão** (status `done → draft` em concept ou technical;
ver §3.2). Não seguem Conventional Commits no título; texto fixo:

- `chore(concept): revert to draft — revision-from-technical: <motivo curto>`
- `chore(technical): revert to draft — revision-from-execution: <motivo curto>`

Carregam `Refs #<num-issue>` no rodapé. Após reaplicar a correção,
seguir o gate normal da fase (`stage N.M: conceptual approved` ou
`stage N.M: technical approved`).

Para overview/roadmap (PRs fora do fluxo de Stage; podem não ter issue
associada — nesse caso, dispensam `Refs #`):

```
docs(overview): approved
docs(roadmap): approved
```

Mensagens reservadas são as únicas que **não** precisam de referência
`[N.M/task-NN]` no título. Qualquer outra mudança no branch da Stage é
commit de Task (classe a).

**Exceção — bootstrap:** durante o procedimento de inicialização de
projeto (`RUNBOOK-INIT-PROJECT.md`) ou adoção em legado
(`RUNBOOK-ADOPT-EXISTING.md`), as mensagens reservadas de overview/roadmap
carregam um sufixo de contexto identificando qual projeto/modo gerou o
commit:

```
docs(overview): approved [projects/<projeto-slug>]
docs(roadmap):  approved [projects/<projeto-slug>]
docs(overview): approved [projects/<projeto-slug>] (adoption)
docs(roadmap):  approved [projects/<projeto-slug>] (adoption)
```

Sufixos só aparecem em commits de bootstrap (cwd no template, antes do
projeto destino estar inicializado). No projeto destino as mensagens
reservadas voltam ao formato fixo (sem sufixo).

#### (c) Título de PR — Conventional Commits + identificador na descrição

O título do PR segue Conventional Commits em português, com **escopo
obrigatório** e o identificador da Stage/issue na descrição, após um
travessão `—`. Dois formatos, conforme a origem do branch:

- **PR de Stage:** `<tipo>(<escopo>): stage N.M — <descrição>`
  - ✅ `feat(billing): stage 12.10 — relatório de inadimplência`
- **PR de branch** (pós-Stage ou issue avulsa): `<tipo>(<escopo>): issue #<num> — <descrição>`
  - ✅ `fix(tooling): issue #53 — corrigir gate do pre-commit`

O `<escopo>` é o **BC/módulo** da mudança (mesma regra de escopo mínimo
da classe (a) — ASCII/kebab), **nunca** a Stage:

- ❌ `feat(stage-12.10): relatório de inadimplência` — Stage não é escopo.
- ❌ `feat: stage 12.10 — relatório de inadimplência` — escopo ausente.

O número da Stage (`stage N.M`) ou da issue (`issue #<num>`) vai na
**descrição**, depois do `—`, nunca no escopo. Não há validação
programática de título de PR (diferente do subject de commit, que passa
pelo hook `commit-msg`); a conformidade é garantida no code review.
Detalhes operacionais e exemplos `gh pr create`:
[`GIT-WORKFLOW.md`](./GIT-WORKFLOW.md) §Pull Requests.

---

## 5. Versionamento de docs

Docs vivem no git, então o histórico é o versionamento. Mas:

- **Concept/Technical — revisão leve via regressão:** se uma decisão
  mudou enquanto a Stage ainda está em andamento (Fase 3B revelou gap
  no concept; Fase 4 ainda não começou e o technical precisa de ajuste),
  use a **regressão `done → draft`** (§3.2). O git log carrega a
  transição via os commits reservados; não há cópia paralela.
- **Concept/Technical — revisão pesada por arquivamento:** se a Stage
  foi recortada/redirecionada e o artefato anterior não representa mais
  o plano vivo, **mover o atual** para
  `concept.archived-YYYY-MM-DD.md` (idem para `technical.archived-...`),
  marcar `status: archived` no movido, e criar novo. Aplicação
  **manual** pelo dev que detectar a mudança.
- **§7 do `technical.md` (post-execution) é exceção:** editável após
  `status: done` sem regressão nem arquivamento. Ver §3.4.
- **O *corpo da decisão* de um ADR `accepted` não é editado destrutivamente.**
  O corpo (Context / Decision / Alternatives / Consequences) é registro
  histórico — preserva o "porquê decidimos X no tempo T". Reescrevê-lo apaga
  história e é **proibido**. Há **duas** formas **não-destrutivas** de manter um
  ADR honesto sem reescrever o corpo:
  - **A decisão mudou** → criar **novo ADR** com `superseded_by` apontando para o
    antigo; o antigo passa a `superseded`.
  - **A decisão se mantém, mas uma premissa/fato declarado se revelou incorreto**
    → adicionar um **banner de errata** *append-only* no topo do ADR (logo após o
    título), no formato
    `> ⚠️ **Errata (YYYY-MM-DD):** <fato corrigido> — ver <auditoria/ADR>`,
    **sem editar o corpo**. A errata **não** muda `status` (a decisão continua
    válida) e bumpa apenas `updated_at`. Serve para **impedir que um leitor/decisão
    futura tome a premissa errada como verdade** — preservando o registro original
    (marcado), não o apagando. Se a premissa corrigida **derruba** a decisão,
    então não é errata: é `superseded` (caso acima).
- **Roadmap pode ser editado livremente**, mas `updated_at` e
  `last_reviewed_at` devem refletir a realidade.
- **Lockfile de dependências (`uv.lock`):** **versionado** por padrão
  (este template gera aplicações; lock garante reprodutibilidade
  dev/CI/prod e segurança via SBOM). O `scripts/init-project.py` roda
  `make setup` antes do primeiro commit, então o `uv.lock` gerado
  entra no commit inicial. Quem mexer em `pyproject.toml` regenera o
  lock no **mesmo commit** que altera a dep — sem PRs separados de
  "lock-only". Se o projeto algum dia virar biblioteca publicada em
  PyPI, mover `uv.lock` para `.gitignore` (decisão consciente, não
  default). Recomendação espelha [docs oficiais do uv](https://docs.astral.sh/uv/concepts/projects/sync/#checking-the-lockfile).

---

## 6. Tamanhos saudáveis

| Artefato | Tamanho saudável | Sinal de alarme |
|---|---|---|
| `overview.md` | 1–3 páginas | >5 páginas: ninguém lê. |
| `roadmap.md` | 1 página + tabelas com células de **1–2 linhas + ponteiro** | Célula narrativa (história/supersessão inline): mover para ADR/stage docs/§Histórico — o histórico tem casa própria. |
| `concept.md` (por Stage) | 2–5 páginas | >8 páginas: Stage grande demais, dividir. |
| `technical.md` (por Stage) | 3–10 páginas | >15 páginas: Stage grande demais. |
| Stages por Step | 1–8 | ≥ 10: reexaminar o recorte — Step temático coeso pode crescer por acreção, mas conferir se não virou guarda-chuva de temas distintos. |
| Tasks por Stage | 3–12 | ≥ 14: quebrar a Stage. |
| ADR | 1–2 páginas | >3 páginas: decisão grande demais, dividir em ADRs menores. |

Faixas são guia, não barreira rígida. Ultrapassar é sinal para
re-examinar, não para abortar.