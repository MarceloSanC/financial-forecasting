---
title: Prompt — Execução de Issue Avulsa em Sessão Única
description: Prompt para colar em uma nova sessão Chat IDE e implementar uma issue avulsa da tabela de issues do roadmap em sessão única, sem perder gates objetivos
when-use: Issue avulsa da tabela de issues do roadmap com escopo delimitado, sobre fundação já validada, onde o agente analisa o impacto e decompõe a issue (que é ponto de partida, não spec completa) em sessão única
keywords: [prompt, issue, single-session, execucao, lifecycle]
status: draft
created_at: 2026-06-10
updated_at: 2026-08-08
---

# Prompt — Execução de Issue Avulsa em Sessão Única

Variante **colapsada** do [`./RUNBOOK-STAGE-LIFECYCLE.md`](./RUNBOOK-STAGE-LIFECYCLE.md) para
issues avulsas: sem Fases 3A/3B (não há `concept.md` nem `technical.md`), mas com os mesmos
gates objetivos de execução e auditoria de testes. **Uma issue por sessão.**

**Quando usar:** Issue com status `open` na tabela de issues do roadmap, cujo **concept+technical
cabem no corpo da issue** (litmus de forma em [`PIPELINE.md`](./PIPELINE.md) §4.5 — não carrega
conceito novo a definir) e cujo critério de aceite é objetivamente verificável.

**Quando NÃO usar:**
- Issue com status `placeholder` — essas são marcadores de backlog sem DoD definido; implementar
  sem planejamento adequado introduz risco de contradição com o roadmap futuro.
- Issue com status `blocked` — há dependência externa explícita não resolvida.
- Issue que **carrega um conceito** (litmus [`PIPELINE.md`](./PIPELINE.md) §4.5): precisa
  definir modelo/invariante/contrato/regra nova, tem decisão que merece ADR, toca modelo de
  dados ou fronteira de BC, ou o corpo não segura o escopo — nesse caso deve virar uma
  **Stage** própria (concept+technical, mesmo enxutos), encaixada no Step certo do roadmap.

---

## Como usar

1. **Cumprir as pré-condições no projeto:**
   - Branch criada a partir de `develop` atualizada (`fix/<issue>-<slug>` ou
     `feat/<issue>-<slug>` conforme o tipo).
   - Issue existe no GitHub e está `open`.
   - Issue está na tabela de issues do `docs/roadmap.md` com `status: open`.
2. Abrir **nova sessão** Chat IDE na raiz do repositório.
3. Substituir as variáveis `<...>` no prompt abaixo e colar inteiro.

---

## Variáveis a substituir

- `<issue>` — número da issue no GitHub (ex.: `#<issue>`)
- `<branch>` — nome da branch (ex.: `fix/<issue>-<slug>`)
- `<title_humano>` — título legível em PT (ex.: `corrigir validação de status no script de lint`)

---

## ⬇️ Prompt (copiar a partir daqui)

````markdown
# PERSONA

Você é o executor de uma issue avulsa. Vai analisar, decompor e implementar a issue `#<issue>`
em **uma única sessão**, sem Fases 3A/3B (não há artefatos de concept/technical), mas mantendo
os mesmos gates objetivos de execução e auditoria de testes do `docs/RUNBOOK-STAGE-LIFECYCLE.md`.

A descrição da issue é ponto de partida, não spec completa. Sua responsabilidade é entender
o impacto real da mudança, verificar consistência com o código atual e identificar o que
a issue pode ter deixado implícito.

# ISSUE-ALVO

- Issue: `#<issue>`
- Branch: `<branch>`
- Título humano: `<title_humano>`

# CONTEXTO QUE VOCÊ DEVE CARREGAR ANTES DE QUALQUER AÇÃO

`CLAUDE.md` já é carregado pelo harness. Antes de qualquer artefato, **leia**:

- `docs/CONVENTIONS.md` — branches, commits, convenções de código
- `docs/GIT-WORKFLOW.md` — gates de PR e fluxo de branches
- `docs/LAYOUT.md` — regras de dependência e estrutura
- `docs/roadmap.md` — linha da issue `#<issue>` na tabela de issues (BC, camada-alvo, depends_on)
- `gh issue view <issue> --comments` — descrição completa + comentários
- Arquivos de código do BC afetado relevantes para entender o contexto da issue
- ADRs em `docs/adr/` citados na issue **ou relevantes ao BC** (incluir os
  globais `0_0_*`/`1_1_*` e os do mesmo bounded context — têm chance de
  restringir a solução)
- `docs/stages/<dep>/concept.md` das Stages que definiram o BC (identificar em `depends_on`
  da linha da issue no roadmap) — para entender os contratos estabelecidos
- A **§7 (post-execution) do `technical.md`** dessas Stages que definiram o BC:
  ler `[finding]` (alguma foi escalada para esta issue?), `[decision]` e
  `[deviation]` que possam orientar ou restringir a implementação
- Skills indicadas no campo `skills_hint` do roadmap (se presente na linha da issue)

Antes de qualquer operação git, **invoque a skill `git-versioning-pointer`**
para confirmar regra de commit/branch/push aplicável.

# PRÉ-CONDIÇÕES (BLOQUEANTES — VERIFICAR PRIMEIRO)

Execute as verificações abaixo. Se **qualquer** falhar, **PARE** e reporte
exatamente o que está faltando — não tente corrigir sozinho:

```powershell
# 1. Working tree limpo
git status

# 2. Branch correta
git branch --show-current   # deve retornar <branch>

# 3. Issue existe e está OPEN no GitHub
gh issue view <issue> --json number,state,title

# 4. Issue está na tabela de issues do roadmap com status: open
# (ler docs/roadmap.md, seção "Tabela de Issues", confirmar status = open)

# 5. depends_on da issue estão concluídas
# (checar no roadmap.md se cada Stage/issue listada em "Depende de" está done)
```

Pré-condições **não são burocracia**: pular qualquer uma compromete o resto
do fluxo. Trate como gate objetivo.

# FLUXO

## Análise Prévia (OBRIGATÓRIA — antes de qualquer código)

A issue foi criada em um momento específico; o código pode ter evoluído desde então.
Antes de decompor em sub-tasks, responda por escrito:

1. **A issue ainda é válida?** O problema descrito ainda existe no código atual? Se o código
   já foi alterado por outra Stage/issue, o que mudou?
2. **O escopo está claro?** A descrição tem critério de aceite objetivamente verificável?
   Se não → `AskUserQuestion` antes de qualquer código.
3. **Qual o impacto?** Quais módulos, camadas ou contratos são afetados além do ponto
   óbvio descrito na issue? Quem consome o que vai mudar?
4. **Há pré-requisitos ocultos?** Algo precisa existir ou estar correto antes desta
   implementação, além do que está em `depends_on`? **Conferir a §7 das
   `technical.md` das Stages do BC** — algum `[finding]` anterior foi escalado
   para esta issue (ou descreve exatamente este problema)? Se sim, ele é parte
   do escopo, não descoberta nova.
5. **A issue deve virar Stage?** Aplique o litmus de forma de [`PIPELINE.md`](./PIPELINE.md)
   §4.5: se você se pegar redigindo um mini-concept (definindo modelo/invariante/contrato/regra),
   se a issue tem decisão que merece ADR, toca modelo de dados ou fronteira de BC, ou o corpo
   não segura o escopo → **PARE** e reporte. Propor abertura de Stage no Step certo.

Se todos os itens tiverem resposta satisfatória: **apresente ao humano um
resumo didático** (skill `didatic-explanation`, ≤ 1 tela) do que a issue
representa no sistema e da abordagem prevista — dúvida direta via
`AskUserQuestion`; decisão de contexto rico como **bloco numerado** (B1,
B2…) respondido por referência. Só então prossiga para a Decomposição.

## Decomposição de Escopo (substitui Fases 3A + 3B)

Não há `concept.md` nem `technical.md` a escrever. A decomposição é feita inline,
nesta sessão, e não gera commit próprio.

A issue descreve o **problema e o critério de aceite** — não necessariamente os arquivos
exatos a modificar. Sua responsabilidade é ler o código e identificar o que precisa mudar.

1. Com base na análise prévia e na leitura do código, identificar:
   - Critério de aceite (DoD explícito ou implícito na issue + o que a análise revelou).
   - Arquivos a criar/modificar (derivados do código, não apenas do enunciado da issue).
   - Dependências de código (o que precisa existir antes de cada sub-task).
2. Decompor em **sub-tasks atômicas** (mesmos 5 critérios de Task Atômica do PIPELINE §4.3):
   - Commitável de forma limpa.
   - Tipicamente ≤ 5 arquivos.
   - Checks objetivos definidos.
   - Não mistura criação de port com criação de adapter desse port.
   - Ordem respeita dependências.
3. Listar as sub-tasks em texto antes de codar. Se você se pegar redigindo um mini-concept
   (definindo modelo/contrato/regra) ou o escopo não couber no corpo (litmus
   [`PIPELINE.md`](./PIPELINE.md) §4.5), declare que é Stage e PARE — propor abertura de Stage.
4. Identificar **bifurcações materiais**: decisões ausentes na issue, no roadmap e no
   código existente que afetam contrato, fronteira ou critério de aceite.
   - Se houver: usar `AskUserQuestion` antes de codar.
   - Se não houver: declare "Não identifiquei bifurcações materiais" e siga.

## Execução por Sub-Task

Para cada sub-task em ordem:

1. **Escopo estrito:** só tocar nos arquivos identificados na decomposição para esta sub-task.
   Se na implementação ficar claro que outros arquivos precisam mudar → **PARAR** e perguntar
   via `AskUserQuestion` (pode ser sinal de impacto maior que o esperado).
2. **Identificar lacunas** (decisão de código ausente na issue + LAYOUT + skills):
   - **Reversível barato** (escolha local, trivial mudar) → IA decide, segue,
     registra justificativa de 1–2 frases.
   - **Irreversível ou caro** (port shape, contrato externo, formato persistido) →
     PERGUNTA antes de codar.
3. **Implementar** e dar resumo conciso do que foi feito antes de commitar.
4. **Rodar checks da sub-task.** Se falhar:
   - Ajuste menor (import faltando, type hint) → corrige.
   - Problema de design → PARA e reporta.
5. **Registrar decisão/achado** se algo surgir na execução que não estava na issue:
   - `[decision]` — decisão tomada por lacuna. Registrar no corpo do PR final.
   - `[finding]` — algo que exige Stage ou issue nova. Registrar como comentário
     na issue antes de fechá-la.
   - `[deviation]` — ajuste pequeno claramente in-scope. Registrar no PR body.
6. **Commit:**
   ```bash
   git add <arquivos-da-sub-task>
   git commit -m "<type>(<scope>): <desc> [#<issue>/task-NN]

   Refs #<issue>"
   ```

# AUDITORIA DE TESTES (GATE EXPLÍCITO — NÃO PULAR)

Depois da última sub-task funcional, **antes** do gate de saída,
responda **por escrito**, em ordem:

1. **Caminho feliz coberto?** O critério de aceite da issue tem teste que valida
   o golden path?
2. **Edge cases cobertos?** Cada caso de erro mencionado (ou implícito) na issue
   tem teste dedicado?
3. **Robustez da cobertura:** para cada função/regra crítica alterada, raciocine
   sobre o que ficou *descoberto* — não se limite a um checklist fixo. Uma forma de
   ancorar esse raciocínio: existe alguma mudança simples (trocar uma comparação,
   retornar um default, inverter uma condição, ignorar um branch) que os testes
   *não* detectariam? Se sim, a cobertura é insuficiente. O objetivo é pensar sobre
   o que não está coberto, não responder mecanicamente a uma lista.
4. **Boundaries (in/out ports) cobertos?** Adapters têm contract tests
   (`pytest-with-fakes` §contract)? Use cases testados com fakes dos out ports?
5. **Integração cobre o que unit não cobre?** Há teste exercitando o fluxo
   end-to-end pela API / CLI / job, com adapter real onde aplicável?
6. **Erros do adapter mapeiam corretamente?** Para adapters HTTP, exceções
   de domínio batem com status HTTP esperado?

**Se a resposta a qualquer item for "não satisfeito":**

- Não é overengineering — é cobertura faltante de gap legítimo.
- Proponha testes faltantes (sem pedir aprovação prévia se óbvio).
- Implemente como sub-task extra com commit dedicado:
  `test(<scope>): cobrir <X> [#<issue>/task-NN-extra]`
- Re-execute a auditoria a partir do item 1.

**Loop até todas as respostas serem "sim".** Este é o único loop legítimo
do fluxo — sem ele, o resto dos gates dá falso positivo.

# GATES DE SAÍDA (INEGOCIÁVEIS)

Todos OBRIGATÓRIOS antes do commit de fechamento:

- [ ] `make check` verde localmente.
- [ ] Coverage ≥ 90%: global (`make test-cov`, gate `fail_under`) **e**
      nos arquivos da issue, via cobertura focada
      (`pytest --cov=<paths tocados> --cov-report=term-missing`) —
      a média global não substitui (gate míope).
- [ ] Auditoria de Testes (acima) com todos os itens "sim".
- [ ] `[finding]`s registrados como comentários na issue antes de fechá-la.
- [ ] `docs/roadmap.md` atualizado: linha de `#<issue>` na tabela de issues
      com `status: done`, `updated_at` e `last_reviewed_at` na data de hoje.
- [ ] ADRs novos (se criados) em `status: accepted`.

**Commit de fechamento** (apenas o roadmap — a implementação já está comitada):

```bash
git add docs/roadmap.md
git commit -m "chore(roadmap): fechar issue #<issue>

Refs #<issue>"
```

# PROTOCOLO DE PERGUNTA

**Quando PERGUNTAR (`AskUserQuestion`):**

- Análise prévia revelou ambiguidade no escopo ou critério de aceite.
- Bifurcação material na decomposição (decisão ausente na issue e nos docs).
- Lacuna que afeta **contrato**, **fronteira** ou **critério de aceite**.
- Sub-task precisa tocar arquivo fora do identificado na decomposição.
- Auditoria de testes revelou cobertura insuficiente **com mais de uma
  estratégia razoável**.
- Contradição entre a issue e o código/ADR/roadmap existente.

**Quando NÃO perguntar:**

- Detalhes seguidos por convenção (LAYOUT, CONVENTIONS, skills aplicáveis).
- Decisões já fechadas na descrição da issue ou nos ADRs citados.
- Reversíveis triviais (nome de variável local, ordem de imports).

**Formato:**

- Contexto curto (1–2 frases).
- 2–4 opções com prós/contras de 1 linha cada.
- Uma marcada como **(Recomendada)** + razão de 1 linha.

# REGRA DE PR

**Você ABRE o PR ao final** (`git push` + `gh pr create`) — a sessão que
implementou é quem abre. Antes do push, **sincronize**: `git fetch` +
`git rebase origin/develop` (o `roadmap.md` é o conflito recorrente; ver
GIT-WORKFLOW §Etapa 4). **Você NÃO faz merge** — o merge é do usuário, após
auditoria, salvo pedido explícito. Não execute `gh pr merge`.

**O checklist do PR é um handoff.** Marque **apenas** as caixinhas que você
**validou com certeza**; deixe as demais **desmarcadas**. O corpo do PR
(vindo do template) traz o label de auditoria em `review` (linha
`> **Auditoria:** ...`, CONVENTIONS §3.6) — **preserve-o**: o workflow
`audit-gate` (CI) **falha enquanto o status não for `complete`**, e é a
sessão de auditoria (`issue-audit`) que grava `complete` ao validar o resto.
Não marque por otimismo nem edite o label à mão.

Sua **saída final** = (1) o **PR aberto** e (2) o **relatório** abaixo:

```markdown
## Issue #<issue> — relatório de execução

### 1. Análise prévia
- A issue ainda era válida? Algum drift identificado?
- Impactos além do óbvio descobertos.
- Pré-requisitos ocultos encontrados (se houver).

### 2. Implementação
- Sub-tasks executadas (lista com commit hash de cada uma).
- Arquivos tocados (resumido).
- ADRs criados (se houver).

### 3. Ajustes durante o processo
(vazio se não houve)
- `[decision]` — decisões tomadas por lacuna (incluir no PR body).
- `[finding]` — achados escalados (registrados como comentário na issue).
- `[deviation]` — ajustes pequenos in-scope.

### 4. Auditoria de testes
1. Caminho feliz coberto? <sim/não + evidência>
2. Edge cases cobertos? <...>
3. Robustez da cobertura? <raciocínio sobre o que foi verificado>
4. Boundaries cobertos? <...>
5. Integração cobre o que unit não cobre? <...>
6. Erros do adapter mapeiam corretamente? <...>

### 5. Gates que VOCÊ validou (marque só o que tem certeza)
- [ ] `make check` verde
- [ ] Coverage ≥ 90% no código novo
- [ ] Auditoria de testes todos os itens "sim"
- [ ] Findings registrados na issue
- [ ] `roadmap.md` atualizado (status done)
- [ ] ADRs em `accepted` (se aplicável)

### 6. PR aberto
- Link: <url do PR>
- Corpo carregado do template `.github/PULL_REQUEST_TEMPLATE.md` (fonte
  única): `Closes #<issue>` + resumo + `[decision]`/`[deviation]` +
  checklist com **só o que você validou** marcado + o label de auditoria em
  `review` (CONVENTIONS §3.6) **preservado** (o gate `audit-gate` do CI
  depende dele; a auditoria grava `complete`).
```

**Comandos que você executa** (o merge NÃO):
```powershell
git fetch origin
git rebase origin/develop        # resolver conflito de roadmap se houver
git push -u origin <branch>
gh pr create --base develop --title "<tipo>(<escopo>): issue #<issue> — <title_humano>" --body-file <corpo>
# <escopo> = BC/módulo da mudança (ASCII/kebab), NUNCA a Stage/issue — CONVENTIONS §4(c)
```

Depois do PR aberto, a sessão de auditoria valida e completa o checklist; o
CI roda e **o usuário faz o merge** (salvo pedido explícito).

# CONTRADIÇÕES

Hierarquia de fonte (alta para baixa): **LAYOUT > CONVENTIONS > ADR > Código > Issue**.

A issue é o ponto de partida — se ao ler o código você descobrir que a solução proposta
na issue contradiz um ADR, o LAYOUT ou o contrato estabelecido pelas Stages anteriores,
**PARE**, aponte com referência explícita à fonte conflitante e peça orientação.

**Não silencie contradição. Não tente resolver sozinho contradição com
fonte mais alta na hierarquia.**

# ORDEM DE EXECUÇÃO RESUMIDA

1. Verificar pré-condições.
2. Carregar contexto (ler docs + `gh issue view` + código do BC afetado).
3. **Análise prévia:** validade, impacto, pré-requisitos ocultos, tamanho real do escopo.
4. **Decomposição:** identificar arquivos via leitura de código, listar sub-tasks,
   perguntar se houver bifurcação material.
5. **Execução:** para cada sub-task: implementar → resumo → checks → registrar se
   necessário → commit `<type>(<scope>): <desc> [#<issue>/task-NN]`.
6. **Auditoria de testes:** loop até todos os itens "sim". Testes faltantes
   viram sub-tasks extras com commit dedicado.
7. **Gate de saída:** todos os gates verdes → commit de fechamento do roadmap.
8. **Abrir o PR** (`git fetch` + rebase + `git push` + `gh pr create`) + relatório final.

**PARE no merge.** Você faz push e abre o PR; o **merge é do usuário** (salvo pedido explícito). Não execute `gh pr merge`.
````

---

## Related

- Variante de Stage: [`./PROMPT-stage-single-session.md`](./PROMPT-stage-single-session.md)
- Procedimento canônico: [`./RUNBOOK-STAGE-LIFECYCLE.md`](./RUNBOOK-STAGE-LIFECYCLE.md)
- Pipeline conceitual: [`./PIPELINE.md`](./PIPELINE.md)
- Convenções: [`./CONVENTIONS.md`](./CONVENTIONS.md)
- Git workflow: [`./GIT-WORKFLOW.md`](./GIT-WORKFLOW.md)
