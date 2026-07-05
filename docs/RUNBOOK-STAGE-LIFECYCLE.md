---
title: Runbook — Ciclo de vida de uma Stage
description: Procedimento passo a passo para conduzir uma Stage do roadmap, da Fase 3A (Concept) até o merge final, com prompts e comandos prontos
when-use: Toda vez que iniciar uma nova Stage no projeto destino
keywords: [runbook, stage, concept, technical, execucao, lifecycle]
runbook_id: stage-lifecycle
triggers:
  - Stage anterior foi mergeada e a próxima está pronta para iniciar
  - Stage 1.1-bootstrap após bootstrap inicial do projeto
estimated_duration: variável (Stage S: meio dia; M: 1–2 dias; nada acima de M sem dividir)
---

# Runbook — Ciclo de vida de uma Stage

> Runbook em **português** (exceção à convenção em inglês de
> `docs/templates/runbook.md`) por carregar prompts e conteúdo do pipeline
> em PT.

> **Modo padrão de execução:** na prática o ciclo roda via as variantes de
> sessão única —
> [`PROMPT-stage-single-session-autonomous.md`](./PROMPT-stage-single-session-autonomous.md)
> (autônoma; implementa → audita → auto-merge sob o ADR 0.0.0050) e
> [`PROMPT-stage-single-session-interactive.md`](./PROMPT-stage-single-session-interactive.md)
> (interativa, human-in-the-loop) — que colapsam as fases deste runbook numa
> sessão única (implementa → audita; ver PIPELINE §11.1). A execução autônoma
> fica registrada em
> [`autonomous-run-decision-ledger.md`](./autonomous-run-decision-ledger.md).
> Este runbook segue sendo o **procedimento canônico por fases** e a **fonte
> única dos checklists de gate** (Passos 5/7/10) que as variantes reusam.

> **Pré-requisitos de arquivo (importante).** Este runbook assume que os
> seguintes artefatos já existem no projeto destino:
>
> - `docs/PIPELINE.md` e `docs/CONVENTIONS.md` (vêm do `boilerplate/layout-files/docs/`)
> - `docs/templates/` com `stage-concept.md`, `stage-technical.md`, `adr.md`
> - `docs/overview.md` e `docs/roadmap.md` aprovados
> - `tree.txt` (gerado por `scripts/regen_tree.py`)
>
> Todos chegam no projeto destino pelo `RUNBOOK-INIT-PROJECT.md` Passo 6
> (greenfield) ou `RUNBOOK-ADOPT-EXISTING.md` (legado). Se faltar algum,
> retorne para o runbook de inicialização antes de seguir.

## Propósito

Conduzir uma Stage do roadmap (`docs/stages/N.M-<slug>/`) do início
(criar issue + branch) até o fim (merge para `develop`), executando as
Fases 3A (Concept), 3B (Technical) e 4 (Execução), com gates humanos
em cada transição.

Pré-requisito: projeto já inicializado via `RUNBOOK-INIT-PROJECT.md`
(no repositório do template `whaka-dev-project-template`); `docs/overview.md`
e `docs/roadmap.md` aprovados; Stage anterior (se houver) já mergeada.

## Pré-requisitos

- [ ] `gh` instalado e autenticado.
- [ ] Working tree limpo (`git status`).
- [ ] Branch `develop` atualizada (`git pull origin develop`).
- [ ] `docs/roadmap.md` define a Stage `N.M` com todos os campos da
      "Descrição para IA" preenchidos (ver template em
      `templates/roadmap.md`).
- [ ] Stages em `depends_on` estão `done` no roadmap.

## Procedimento

### Passo 1 — Criar issue no GitHub

Identificar a Stage `N.M-<slug>` no roadmap. Criar issue:

```powershell
$N = "<numero-step>"            # ex: 2
$M = "<numero-stage>"           # ex: 3
$slug = "<stage-slug>"          # ex: s3-source-adapter
$title_humano = "<titulo>"      # ex: adicionar S3 source adapter

gh issue create `
  --title "feat: stage $N.$M — $title_humano" `
  --body "Stage $N.$M-$slug — ver docs/roadmap.md e (após criação) docs/stages/$N.$M-$slug/concept.md"
```

**Saída esperada:** URL da issue + número atribuído (ex.: `#42`).
Anotar o número — vai entrar no nome do branch e no rodapé dos commits.

**Gate de saída do Passo 1 — issue DEVE existir antes de qualquer passo
seguinte.** Verificar live no GitHub:

```powershell
gh issue view $issue --json number,title,state
# Deve retornar JSON com number == $issue. Se falhar
# ("GraphQL: Could not resolve to an issue" ou "no issues found"),
# PARAR aqui — repetir Passo 1 (a issue precisa existir no backlog
# antes de criar branch, criar pasta da Stage ou rodar o prompt do
# Concept).
```

Sem issue confirmada no backlog: **não criar branch (Passo 2),
não criar pasta da Stage (Passo 3), não iniciar Fase 3A (Passo 4)**.
Issue-first é princípio bloqueante ([`./GIT-WORKFLOW.md`](./GIT-WORKFLOW.md)
§Princípios fundamentais #1).

### Passo 2 — Criar branch a partir de develop

> **Pré-condição (Passo 1):** `$issue` é o número de uma issue que
> **já existe** no backlog do GitHub — confirmado por `gh issue view
> $issue`. Se você não tem o número, voltar ao Passo 1.

```powershell
$issue = "<num-issue>"          # ex: 42 — confirmado por gh issue view
$N_M_kebab = "$N-$M"            # ex: 2-3

git checkout develop
git pull origin develop
git checkout -b "feat/$issue-$N_M_kebab-$slug"
# Exemplo: feat/42-2-3-s3-source-adapter
```

### Passo 3 — Criar pasta da Stage

```powershell
New-Item -ItemType Directory -Force -Path "docs/stages/$N.$M-$slug" | Out-Null
Copy-Item docs/templates/stage-concept.md "docs/stages/$N.$M-$slug/concept.md"
Copy-Item docs/templates/stage-technical.md "docs/stages/$N.$M-$slug/technical.md"
```

> ADRs desta Stage **não** vão num subdir local — vivem em
> `docs/adr/N_M_NNNN-<slug>.md` (pasta única para Stage e globais; ver
> [`../CONVENTIONS.md`](../CONVENTIONS.md) §1). Se `docs/adr/` ainda
> não existe (projeto novo sem bootstrap ADRs), criar:
> `New-Item -ItemType Directory -Force -Path "docs/adr" | Out-Null`.

Commit do esqueleto:

```powershell
git add "docs/stages/$N.$M-$slug/"
git commit -m "stage $N.$M: conceptual draft

Refs #$issue"
```

### Passo 4 — Fase 3A: Concept

Abrir nova sessão Chat IDE neste repositório. Anexar mentalmente os
arquivos relevantes (CLAUDE.md ativo já cobre LAYOUT.md, tree.txt,
roadmap.md, concept.md atual). Se a Stage tem `depends_on`, abrir os
`concept.md` correspondentes e a §7 (post-execution) dos `technical.md`
(de `depends_on` e de Stages do mesmo BC) para findings/decisões pendentes.

Colar o prompt:

````markdown
# PERSONA

Você é um Analista de Conceito de Arquitetura Hexagonal. Sua função é
produzir o Concept de uma única Stage do roadmap, em markdown. Você
não escreve código nesta fase.

# CONTEXTO QUE VOCÊ TEM

- `docs/overview.md` — visão geral aprovada
- `docs/roadmap.md` — recorte da Stage atual e vizinhas diretas
- `concept.md` de Stages anteriores listadas em `depends_on` (apenas)
- **§7 (post-execution) dos `technical.md`** das Stages em `depends_on`
  (e de Stages do **mesmo BC** ainda que não sejam dependência formal):
  ler as entradas `[finding]` (alguma foi escalada para esta Stage?),
  `[decision]` e `[deviation]` que possam restringir ou orientar o concept
- ADRs relevantes — não só os de `depends_on`: incluir os **globais**
  (`0_0_*`, `1_1_*` da Stage 1.1-bootstrap) e os do **mesmo bounded
  context** desta Stage, mesmo que a relação não esteja em `depends_on`
  (têm chance de restringir uma decisão do concept)
- `tree.txt`, `LAYOUT.md`, `CONVENTIONS.md`
- Skills aplicáveis (ver `skills_hint` da Stage)
- Arquivos do código existente, consultáveis sob demanda

Antes de qualquer pergunta, abra os arquivos que a tree indica como
relevantes. Decisões já tomadas no código são fonte primária e NÃO são
perguntáveis.

# PRINCÍPIO DE PERGUNTA

Uma pergunta materialmente válida é aquela cuja resposta determina o
conteúdo do Concept de forma não recuperável de Overview, Roadmap ou
código existente.

Não pergunte:
- O que já está decidido no Overview, Roadmap ou código.
- Nomes, formatos triviais ou estilo (seguem LAYOUT e convenções).
- Detalhes de implementação (pertencem à Fase 3B/4).
- Preferências subjetivas sem impacto no contrato da Stage.

# CONDUÇÃO

Em blocos temáticos quando útil. Tipicamente:
1. Escopo e fronteiras.
2. Contratos e invariantes.
3. Casos de erro.
4. Decisões técnicas relevantes (alternativas reais descartadas → ADR).
5. Dependências e integração com Stages anteriores.
6. Riscos e premissas.

Uma pergunta por vez quando independentes; várias juntas só quando a
resposta de uma muda a formulação das outras. Sem limite de turnos —
o limite é a saturação (2 perguntas consecutivas com resposta
"qualquer", "tanto faz", ou usuário repetindo conteúdo anterior).

# CASO ESPECIAL — STAGE TRIVIAL

Se, após análise inicial, não houver bifurcação material, declare:
"Não identifiquei bifurcações materiais nesta Stage." Gere o Concept
direto. Peça confirmação humana antes de finalizar.

# CONTRADIÇÕES

Se uma resposta contradiz decisão prévia do Overview, Roadmap ou
código, pare imediatamente. Aponte com referência explícita à fonte
conflitante. Não tente resolver sozinho.

# FORMATO DE SAÍDA

Use o template `docs/templates/stage-concept.md`, salvar em
`docs/stages/N.M-<slug>/concept.md`. Frontmatter conforme
`CONVENTIONS.md` §2. Seções inaplicáveis devem ser REMOVIDAS (não
escreva "N/A").

Decisões maiores com alternativa real descartada DEVEM virar ADR em
`docs/adr/N_M_NNNN-<slug>.md` (ex.: `docs/adr/2_3_0001-stream-vs-batch.md`)
usando `docs/templates/adr.md`. Pasta única para ADRs de Stage e globais;
o prefixo `N_M` no filename é o separador. Referenciar o ADR no
Concept pelo `adr_id` (ex.: `2.3.0001`).
````

### Passo 5 — Gate humano: Concept

Checklist (**fonte única** — PIPELINE §7.4 aponta para cá):

- [ ] Escopo e Fora de Escopo correspondem à Stage do Roadmap.
- [ ] Toda decisão em §7 do concept (Decisões técnicas) tem fonte rastreável.
- [ ] Contratos declarados batem com `contratos_introduzidos` do Roadmap.
- [ ] Critérios de aceitação são objetivos e testáveis.
- [ ] Checklist de validação interna (§12 do concept) 100% "sim".
- [ ] ADRs identificados como necessários foram escritos (`accepted`).
- [ ] Stage cabe em ~3–12 Tasks (`CONVENTIONS.md` §6); se cresceu além disso, dividir antes de seguir.
- [ ] Frontmatter completo; `status: done`.

**Aprovado:**

```powershell
git add "docs/stages/$N.$M-$slug/concept.md" "docs/adr/$($N)_$($M)_*.md"
git commit -m "stage $N.$M: conceptual approved

Refs #$issue"
```

> **Concept aprovado ≠ congelado.** Se a Fase 3B (Passo 6) revelar gap
> material aqui, é esperado regredir o concept para `draft` (CONVENTIONS
> §3.2) e re-aprovar. Não tratar como falha do processo — é o loop de
> design fazendo o trabalho dele.

### Passo 6 — Fase 3B: Technical

Mesma sessão (ou nova com concept.md no contexto). O **draft** do
`technical.md` pode começar enquanto o concept ainda está em revisão
(útil para encontrar gaps de design cedo); o **gate** (Passo 7) exige
`concept.status == done`.

**Loop de revisão entre Concept e Technical.** Se o draft do technical
revelar gap material no concept, regredir o concept para `draft`
(CONVENTIONS §3.2):

```powershell
# Editar docs/stages/$N.$M-$slug/concept.md ajustando o gap + status: draft
git add "docs/stages/$N.$M-$slug/concept.md"
git commit -m "chore(concept): revert to draft -- revision-from-technical: <motivo curto>

Refs #$issue"
```

Após corrigir, re-aprovar (commit `stage $N.$M: conceptual approved`)
e voltar a este Passo 6.

Colar:

````markdown
# PERSONA

Você é um Tech Lead sênior especializado em planejamento de
implementação. Sua função é traduzir o Concept aprovado de uma Stage
em sequência de Tasks executáveis (1 Task = 1 commit).

# CONTEXTO QUE VOCÊ TEM

- `docs/stages/N.M-<slug>/concept.md` (obrigatório)
- `docs/overview.md` (referência)
- ADRs em `docs/adr/` (filtrar pelo prefixo `N_M_` para esta Stage,
  e relevantes de Stages anteriores — especialmente `0_0_*` e
  `1_1_*` para Stages early-stage, e prefixos de Stages em
  `depends_on`)
- `tree.txt`, `LAYOUT.md`, `CONVENTIONS.md`
- Skills aplicáveis
- `concept.md` de Stages anteriores: avaliar caso a caso. Anexar
  quando esta Stage consome contratos/conceitos lá. `technical.md`
  anterior raramente necessário.
- Arquivos do código existente, consultáveis sob demanda

# OBJETIVO

Produzir lista ordenada de Tasks. Cada Task descreve:
- Arquivos a criar/modificar (caminhos exatos, conformes a LAYOUT.md).
- Conteúdo material da Task (o que será feito, sem código completo).
- Critério de aceite objetivo.
- Comando(s) de verificação.

A ordem entre Tasks segue skills de ordenação aplicáveis (ex.:
`task-ordering-hex` para Stage de fatia vertical). Quando o default
da skill não se aplica (fundação, adapter-only, bug fix, migração),
declarar a ordem escolhida e o motivo no preâmbulo do `technical.md`.

# CRITÉRIO DE TASK ATÔMICA (resumo — fonte: PIPELINE.md §4.3)

1. Commitável de forma limpa.
2. Tipicamente ≤ 5 arquivos. Acima disso, justificar (rename mecânico
   ou similar) ou quebrar a Task.
3. Checks objetivos definidos.
4. Não mistura criação de port com criação de adapter desse port.
   Exceção apenas quando ambos triviais e declarada no `technical.md`.
5. Ordem respeita dependências internas.

# PRINCÍPIO DE PERGUNTA

Você pode produzir DIRETO, sem nova rodada de perguntas, se o Concept
está sólido. Se encontrar lacuna ou ambiguidade no Concept que afeta
a quebra, PARE e sinalize — pode ser necessário voltar à Fase 3A.

Não pergunte:
- Detalhes triviais (nomes de variáveis, ordem de parâmetros) — seguem convenções.
- Decisões já fechadas no Concept.

# CONTRADIÇÕES

Se o Concept contradiz LAYOUT.md ou código existente, pare e aponte
antes de gerar Tasks.

# FORMATO DE SAÍDA

Use o template `docs/templates/stage-technical.md`, salvar em
`docs/stages/N.M-<slug>/technical.md`. Frontmatter conforme
`CONVENTIONS.md` §2 (campos `stage_id`, `stage_title`, `step_id`,
`step_title`, `depends_on`, `concept_ref`, `issue_id`, `branch`,
`tasks_count`).

Para cada Task: arquivos a criar/modificar, descrição, detalhes
técnicos, critério de aceite, comando de verificação em bloco bash,
mensagem de commit sugerida no formato:
`<type>(<scope>): <desc> [N.M/task-NN]` com rodapé `Refs #<issue>`.

Inclua no fim:
- Ordem de dependência entre Tasks (se não óbvia).
- Riscos e fallbacks.
- Gate de saída da Stage (verificações automatizadas + funcionais +
  checklist de fechamento).

Antes de finalizar, valide internamente cada Task contra os 5
critérios. Task que falha deve ser quebrada.
````

Após a IA gerar o `technical.md`, comitar como draft (PIPELINE §8 / CONVENTIONS §4):

```powershell
git add "docs/stages/$N.$M-$slug/technical.md"
git commit -m "stage $N.$M: technical draft

Refs #$issue"
```

### Passo 7 — Gate humano: Technical

Checklist (**fonte única** — PIPELINE §8.4 aponta para cá):

- [ ] Cada Task cumpre os 5 critérios de Task Atômica (§4.3).
- [ ] Caminhos batem com `LAYOUT.md`.
- [ ] Checks objetivos cobrem cada Task.
- [ ] Ordem respeita dependências.
- [ ] Riscos identificados são razoáveis.
- [ ] Gate de saída da Stage definido (testes + critério funcional).
- [ ] Número de Tasks saudável (3–12; ≥ 14 = Stage grande demais).
- [ ] §7 "Execução" presente com marcadores
      `<!-- BEGIN: post-execution -->` / `<!-- END: post-execution -->`
      (vazia ou contendo apenas placeholder).
- [ ] `concept.status == done` neste momento.
- [ ] Frontmatter completo (incluindo `issue_id` e `branch`); `status: done`.

**Aprovado:**

```powershell
git add "docs/stages/$N.$M-$slug/technical.md"
git commit -m "stage $N.$M: technical approved

Refs #$issue"
```

> **Technical aprovado ≠ congelado fora de §7.** Se, antes da Fase 4
> começar, surgir gap no plano, regredir para `draft` com
> `chore(technical): revert to draft -- revision-from-execution: <motivo>`
> (CONVENTIONS §3.2). Já durante a Fase 4, ajustes vão para §7 (não
> mudam o status) ou caem no Troubleshooting.

### Passo 8 — Fase 4: Execução por Task

**Pré-condição rígida (verificar antes de iniciar):**

```powershell
# Ambos devem estar 'done'
Select-String "^status:\s*done" "docs/stages/$N.$M-$slug/concept.md"
Select-String "^status:\s*done" "docs/stages/$N.$M-$slug/technical.md"
```

Se qualquer um não estiver `done`, **não iniciar a execução** — voltar
ao Passo 5 ou Passo 7 conforme o caso.

Abrir 1 sessão Chat IDE para a Stage inteira (não 1 por Task — overhead
de re-iniciar contexto a cada Task é alto). Compactação dentro da
sessão é permitida.

Para cada Task em ordem, colar:

````markdown
# PERSONA

Você é um engenheiro de software sênior implementando uma única Task
de uma Stage. Você escreve código que respeita LAYOUT.md, é type-safe,
testado e commitável de forma limpa.

# CONTEXTO QUE VOCÊ TEM

- `docs/stages/N.M-<slug>/technical.md` — Task atual
- `docs/stages/N.M-<slug>/concept.md`
- ADRs da Stage
- `tree.txt`, `LAYOUT.md`, `CONVENTIONS.md`
- Skills aplicáveis
- Arquivos do código existente

# OBJETIVO

Implementar EXATAMENTE a Task descrita. Nada além, nada aquém.

# ESCOPO ESTRITO

Você só pode tocar nos arquivos listados em "Arquivos a criar" e
"Arquivos a modificar" da Task atual.

Se descobrir que precisa tocar em outro arquivo, PARE. Reporte:
- Qual arquivo extra você precisaria tocar.
- Por quê.
- Sugestão: o `technical.md` desta Stage
  (`docs/stages/N.M-<slug>/technical.md`) deve ser revisado antes de
  prosseguir.

# §7 DO TECHNICAL — REGRA DE PERGUNTA ANTES DA NOTA

Se durante a execução você encontrar algo **não previsto** no
`technical.md` (§1–§6) ou no `concept.md`:

1. PARE a implementação. Não decida sozinho, não "ajuste e siga".
2. Pergunte ao humano via `AskUserQuestion` (ou equivalente):
   - Contexto curto do que foi encontrado.
   - 2–4 opções com prós/contras de uma linha cada.
   - Uma marcada como **recomendada** + razão.
3. Aplique a decisão do humano.
4. Registre a entrada em §7 do `technical.md` (entre os marcadores
   `<!-- BEGIN: post-execution -->` e `<!-- END: post-execution -->`)
   com header `### YYYY-MM-DD — [tag] escopo — Autor`:
   - `[decision]` — decisão tomada com base na pergunta.
   - `[finding]` — escalado para próxima Stage (não decidido agora).
   - `[deviation]` — ajuste pequeno claramente in-scope (continua exigindo
     pergunta; o "pequeno" não dispensa).
5. **Só §7 do technical é editável após `status: done` — enquanto a
   Stage não mergeou.** Durante a execução, mudanças em §1–§6 exigem
   regressão `technical → draft` (CONVENTIONS §3.2) e re-aprovação. O
   `updated_at` do frontmatter **não muda** com edições em §7. **Após o
   merge** da Stage, o technical vira doc de referência mutável e o gate
   `check_technical_postexec` deixa de checá-lo (CONVENTIONS §3.4).

**Na dúvida sobre se algo é pequeno o suficiente para decidir sozinho:
pergunte.** Nunca propague em silêncio.

# PRINCÍPIO DE PERGUNTA

Antes de implementar, identifique decisões de código não presentes no
contexto (Concept + Technical + LAYOUT + skills).

Heurística de reversibilidade:
- Reversível barato (escolha local, trivial de mudar): a IA decide,
  segue, e documenta a decisão como justificativa breve no diff.
- Irreversível ou caro de reverter (port shape, contrato externo,
  formato de dado persistido): pergunte antes de codar.

Não pergunte:
- Detalhes seguidos por convenção.
- Decisões já fechadas em qualquer doc.

# LACUNAS

Se descobrir decisão material ausente de qualquer doc, e essa decisão
tem alternativas reais, PARE. Use o protocolo da seção anterior
(pergunta + registro em §7 como `[decision]`). Decisões com alternativa
real descartada precisam virar **ADR** após resposta do humano — não
basta o registro em §7. Se a lacuna é grande demais para resolver via
§7 (afeta o plano em §1–§6), regredir o technical para `draft`
(CONVENTIONS §3.2) ou voltar à Fase 3A.

# ORDEM DE OPERAÇÃO

1. Abra os arquivos relevantes (listados na Task + dependências óbvias).
2. Identifique decisões ausentes; pergunte se houver (regra de
   reversibilidade acima).
3. Implemente.
4. Rode cada check listado na Task. Se algum falhar:
   - Corrija se for ajuste menor (import faltando, type hint).
   - Pare e reporte se for problema de design.
5. Apresente o diff completo ao humano antes do commit.

# CONTRADIÇÕES

Se ao implementar você descobrir que a Doc Técnica contradiz Concept,
LAYOUT.md ou código existente, pare e aponte. Não silencie a
contradição.

# FORMATO DA SAÍDA

Para cada arquivo criado/modificado:
1. Caminho exato.
2. Conteúdo final (ou diff, se modificação).
3. Justificativa curta para decisões não óbvias (1–2 frases).

Após apresentar todos os arquivos, peça revisão humana antes do commit.
NÃO comite por iniciativa própria.

Mensagem de commit conforme CONVENTIONS.md §4:
`<type>(<scope>): <description> [N.M/task-NN]` com rodapé `Refs #<issue>`.
````

### Passo 9 — Gate humano por Task

Para cada Task implementada, revisar diff antes do commit (PIPELINE §9.4):

- [ ] Apenas arquivos listados na Task foram tocados.
- [ ] Checks listados na Task passam.
- [ ] Código respeita `LAYOUT.md` (camada certa, sem imports proibidos).
- [ ] Decisões justificadas batem com Concept.
- [ ] Mensagem de commit no formato correto.

**Modo de gate por Stage** (declarado em `roadmap.md` campo `gate_mode`
— **semântica completa: PIPELINE §9.4**):
- `strict` (default): revisar antes de cada commit.
- `batch`: agente commita Tasks em sequência; humano revisa o conjunto
  ao final da Stage. Permitido apenas para implementação rotineira
  sobre fundação validada. Mudar para `batch` exige justificativa no
  `concept.md` ou ADR.

**Aprovado (modo strict):**

```powershell
# IA escreve os arquivos
make check          # rodar todos os checks
git add <arquivos-da-task>
git commit -m "<type>(<scope>): <desc> [$N.$M/task-NN]

Refs #$issue"
```

### Passo 10 — Gate de saída da Stage

Após a última Task, executar o checklist canônico de fechamento
(**fonte única** — PIPELINE §9.5 aponta para cá).

> **Verificação end-to-end (último quilômetro).** Uma Stage que produz **dado
> ou artefato novo** consumível por fora (endpoint HTTP, arquivo em `results/`,
> tabela) não termina ao persistir + cobrir com teste unitário: **o merge exige
> verificação end-to-end** — a requisição real ao endpoint retorna o código
> esperado **com o dado presente** (ou o artefato nasce no caminho esperado com
> o conteúdo esperado). Teste unitário **não basta** — o gate é a resposta
> real.

- [ ] `make check` verde localmente.
- [ ] Verificações funcionais do `technical.md` §3 cumpridas.
- [ ] **Se a Stage produz dado/artefato novo consumível por fora:** foi feita
      **verificação end-to-end** — a requisição real ao endpoint retorna o
      código esperado **com o dado presente**, seguindo a receita do
      `technical.md` §3 (endpoint/artefato, campos, nomes e valores esperados).
      Teste unitário **não basta** — o gate é a resposta real.
- [ ] **`python scripts/check_technical_postexec.py` verde** — confirma
      que, desde `stage $N.$M: technical approved`, o diff do
      `technical.md` ficou restrito à §7 (entre os marcadores
      `BEGIN/END: post-execution`). Ver bloco de comando abaixo.
- [ ] §7 do `technical.md` reflete o que realmente aconteceu na
      execução (entradas `[decision]`/`[finding]`/`[deviation]` com header
      `### data — [tag] escopo — autor`).
- [ ] Findings escalados (`[finding]`) têm Stage candidata identificada.
- [ ] Commit final `stage N.M: complete` no branch (ver bloco abaixo).
- [ ] PR contra `develop` aberto e mergeado, seguindo gates do
      GIT-WORKFLOW (CI verde, coverage ≥ 90%, +1 aprovação, merge
      commit) — execução no Passo 11.
- [ ] `roadmap.md` atualizado: Stage marcada `done`, `updated_at` e
      `last_reviewed_at` no **mesmo merge da Stage** (preferível) ou em
      PR de docs imediatamente subsequente. Responsável: dev que fez o
      merge.
- [ ] ADRs novos (se houve) em `status: accepted`.
- [ ] Runbooks operacionais criados se aplicável.
- [ ] `concept.md` não precisa de retoque retrospectivo (se precisa,
      abrir TODO ou nova Stage de correção).

Lint da §7 (executar antes do commit final):

```powershell
python scripts/check_technical_postexec.py "docs/stages/$N.$M-$slug/technical.md"
```

Commit final:

```powershell
git add docs/roadmap.md
git commit -m "stage $N.$M: complete

Refs #$issue"
```

### Passo 11 — Abrir PR contra develop

A **sessão que implementou abre o PR**. **Antes do push, sincronize**
(GIT-WORKFLOW §Etapa 4): `git fetch` + `git rebase origin/develop` — resolve
cedo o conflito recorrente de `roadmap.md`.

```powershell
git fetch origin
git rebase origin/develop        # resolver conflito de roadmap se houver
git push -u origin "feat/$issue-$N_M_kebab-$slug"

$bc = "<escopo>"   # BC/módulo da mudança (ASCII/kebab), NUNCA a Stage — CONVENTIONS §4(c)
gh pr create --base develop --title "feat($bc): stage $N.$M — $title_humano"
# Corpo carregado do template .github/PULL_REQUEST_TEMPLATE.md (fonte única).
# Preencha as seções e marque no checklist SÓ o que você validou com certeza;
# deixe o resto desmarcado + nota "⚠️ precisa de auditoria antes do merge".
# (Sessão headless: passar --body-file com o template preenchido.)
```

**O merge é do usuário** (salvo pedido explícito) — após auditoria da Stage
(skill `stage-audit`, que aplica fixes no PR se preciso e **registra o
veredito no PR**: comentário + "⚠️"→"✅") + CI verde e +1
aprovação:

```powershell
gh pr merge <num-pr> --merge --delete-branch
```

### Passo 12 — Cleanup

```powershell
git checkout develop
git pull origin develop
git remote prune origin
```

Próxima Stage: voltar ao Passo 1 com a próxima `N.M` do roadmap.

## Verificação

```powershell
# Branch deletada local e remotamente
git branch -a | Select-String "$N-$M"   # nada deve retornar

# Issue fechada automaticamente pelo PR
gh issue view $issue                    # deve mostrar state CLOSED

# Roadmap reflete status
Get-Content docs/roadmap.md | Select-String "$N\.$M.*done"
```

## Troubleshooting

| Sintoma | Causa provável | Resolução |
|---|---|---|
| Fase 3B revela lacuna no Concept | Concept incompleto | Regredir concept para `draft` via `chore(concept): revert to draft -- revision-from-technical: <motivo>` (CONVENTIONS §3.2). Atualizar Concept. Re-aprovar com `stage N.M: conceptual approved`. Voltar a 3B. **Nova sessão não obrigatória.** |
| Fase 4 (não iniciada) — gap no Technical | Technical precisa ajuste antes da execução | Regredir technical para `draft` via `chore(technical): revert to draft -- revision-from-execution: <motivo>`. Ajustar. Re-aprovar. |
| Fase 4 — algo não previsto encontrado durante execução | Decisão/observação ausente nos docs | IA **pergunta** com `AskUserQuestion` (2–4 opções + recomendada). Registra entrada em §7 do `technical.md` (`[decision]`/`[finding]`/`[deviation]`). Nunca decide em silêncio. |
| Fase 4 — Task estoura escopo (precisa tocar arquivo extra) | Technical incompleto | IA para e pergunta. Humano decide: regredir technical (§1–§6), aceitar exceção registrada em §7 como `[decision]`, ou abortar Task. |
| Fase 4 revela problema **grande** no Concept | Concept tem decisão errada | Stop. Voltar à Fase 3A explicitamente em nova sessão (PIPELINE §12.2). Regressão simples não cobre. |
| Fase 4 revela problema no Roadmap | Stage está mal recortada | Pausar. Nova sessão com Overview + Roadmap. Replanejar Stages afetadas. |
| `check_technical_postexec.py` falha | Edição fora de §7 no `technical.md` após `done` | Reverter as linhas tocadas fora dos marcadores. Se a mudança era legítima, abrir regressão (`chore(technical): revert to draft -- ...`) ou arquivar a versão atual (CONVENTIONS §5). |
| Stage descartada antes do merge | Mudou de plano | `gh pr close <num>`. Issue fechada com label `wontfix` ou `superseded`. Mover `docs/stages/N.M-<slug>/` para `docs/stages/_archived/` com nota. |
| Defeito descoberto após merge para main | Bug em produção | Ver `GIT-WORKFLOW.md` §"Defeito descoberto após merge para main". |

## Related

Caminhos relativos a este arquivo (`docs/RUNBOOK-STAGE-LIFECYCLE.md` no projeto destino):

- Variante em sessão única — **autônoma** (implementa → audita → auto-merge, ADR 0.0.0050): [`./PROMPT-stage-single-session-autonomous.md`](./PROMPT-stage-single-session-autonomous.md)
- Variante em sessão única — **interativa** (human-in-the-loop): [`./PROMPT-stage-single-session-interactive.md`](./PROMPT-stage-single-session-interactive.md)
- Prompt canônico de sessão única (base das duas variantes): [`./PROMPT-stage-single-session.md`](./PROMPT-stage-single-session.md)
- Registro da execução autônoma (decision ledger): [`./autonomous-run-decision-ledger.md`](./autonomous-run-decision-ledger.md)
- Variante em sessão única para **issue avulsa** (sem concept/technical): [`./PROMPT-issue-single-session.md`](./PROMPT-issue-single-session.md)
- Pipeline conceitual: [`./PIPELINE.md`](./PIPELINE.md)
- Convenções: [`./CONVENTIONS.md`](./CONVENTIONS.md)
- Git workflow: [`./GIT-WORKFLOW.md`](./GIT-WORKFLOW.md)
- Arquitetura: [`./LAYOUT.md`](./LAYOUT.md)
- Templates: [`./templates/`](./templates/)
