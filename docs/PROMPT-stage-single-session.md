---
title: Prompt — Execução de Stage em Sessão Única (variante experimental)
description: Prompt para colar em uma nova sessão Chat IDE e rodar Fase 3A + 3B + 4 de uma Stage em uma única sessão, sem perder gates objetivos
when-use: Stages pequenas/médias (3–6 Tasks) sobre fundação já validada, onde o overhead de re-hidratar contexto entre fases supera o benefício
keywords: [prompt, stage, single-session, concept, technical, execucao, lifecycle]
status: draft
created_at: 2026-06-10
updated_at: 2026-06-10
---

# Prompt — Execução de Stage em Sessão Única

Variante **colapsada** do [`./RUNBOOK-STAGE-LIFECYCLE.md`](./RUNBOOK-STAGE-LIFECYCLE.md):
mesmo fluxo, mesmos gates objetivos, mesmos artefatos — sem as transições
de sessão e sem o gate humano por aprovação textual entre fases.

**Quando usar:** Stages pequenas/médias (3–6 Tasks), tipicamente sobre
fundação já validada (ex.: Stage 1.2 após 1.1 mergeada). O ganho é evitar
re-hidratar contexto entre 3A → 3B → 4.

**Quando NÃO usar:**
- Stage com decisões arquiteturais grandes — prefira sessão dedicada por fase.
- Stage com `gate_mode: strict` declarado no roadmap por motivo explícito.
- Primeiro contato com um Bounded Context novo.

---

## Como usar

1. **Cumprir as Pré-condições no projeto** (Passos 1–3 do runbook canônico):
   - Issue criada no GitHub (`gh issue create`).
   - Branch criada a partir de `develop` atualizada (`feat/<issue>-<N-M>-<slug>`).
   - Pasta `docs/stages/<N.M>-<slug>/` criada com `concept.md` e `technical.md`
     esqueletos a partir de `templates/`.
   - Commit inicial `stage <N.M>: conceptual draft`.
2. Abrir **nova sessão** Chat IDE na raiz do repositório.
3. Substituir as variáveis `<...>` no prompt abaixo e colar inteiro.

---

## Variáveis a substituir

- `<N.M>` — identificador da Stage (ex.: `1.2`)
- `<slug>` — slug da Stage (ex.: `domain-skeleton`)
- `<issue>` — número da issue no GitHub (ex.: `7`)
- `<branch>` — nome da branch (ex.: `feat/7-1-2-domain-skeleton`)
- `<title_humano>` — título legível em PT (ex.: `esqueleto do domínio de Pedidos`)

---

## ⬇️ Prompt (copiar a partir daqui)

````markdown
# PERSONA

Você é o orquestrador completo de uma Stage. Vai executar Fases 3A (Concept),
3B (Technical) e 4 (Execução por Task) em sequência, em **uma única sessão**,
seguindo `docs/RUNBOOK-STAGE-LIFECYCLE.md` mas colapsando as transições de
sessão e os gates por aprovação textual — **exceto onde o gate é objetivo
e inegociável** (ver §Gates inegociáveis).

# STAGE-ALVO

- Stage: `<N.M>-<slug>`
- Issue: `#<issue>`
- Branch: `<branch>`
- Título humano: `<title_humano>`

# CONTEXTO QUE VOCÊ DEVE CARREGAR ANTES DE QUALQUER AÇÃO

`CLAUDE.md` já é carregado pelo harness. Antes de gerar qualquer artefato,
**leia** (não apenas mencione):

- `docs/PIPELINE.md` — fases e gates conceituais
- `docs/CONVENTIONS.md` — frontmatter, branches, commits, regressão de status
- `docs/GIT-WORKFLOW.md` — gates de PR e fluxo de branches
- `docs/LAYOUT.md` — regras de dependência e estrutura
- `docs/RUNBOOK-STAGE-LIFECYCLE.md` — procedimento canônico (esta sessão é variante)
- `docs/roadmap.md` — recorte da Stage `<N.M>` e dependências
- `tree.txt` — estado atual do repo
- Para cada Stage em `depends_on` da `<N.M>`: `docs/stages/<dep>/concept.md`
- Para cada Stage em `depends_on` (e Stages do **mesmo BC** que não sejam
  dependência formal): a **§7 (post-execution) do `technical.md`** — ler as
  entradas `[finding]` (alguma foi escalada para esta Stage?), `[decision]`
  e `[deviation]` que possam restringir ou orientar o concept
- ADRs em `docs/adr/` relevantes: os globais (prefixos `0_0_*`, `1_1_*`),
  os dos itens em `depends_on` **e os do mesmo bounded context** desta
  Stage — mesmo que a relação não esteja em `depends_on`, têm chance de
  restringir uma decisão do concept
- Skills aplicáveis (campo `skills_hint` da Stage no `roadmap.md`)

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

# 3. Issue existe e está OPEN
gh issue view <issue> --json number,state,title

# 4. Estrutura da Stage existe
Test-Path "docs/stages/<N.M>-<slug>/concept.md"
Test-Path "docs/stages/<N.M>-<slug>/technical.md"

# 5. depends_on done — checar no docs/roadmap.md cada item de depends_on
#    da Stage <N.M> está marcado como status: done
```

Pré-condições **não são burocracia**: pular qualquer uma compromete o resto
do fluxo. Trate como gate objetivo.

# FLUXO

## Fase 3A — Concept

1. Carregar contexto (lista acima).
2. Identificar **bifurcações materiais**: decisões cujo conteúdo NÃO é
   recuperável de Overview/Roadmap/código existente.
3. Se houver bifurcações: usar `AskUserQuestion` em blocos temáticos
   (escopo, contratos, erros, decisões técnicas, dependências, riscos),
   com 2–4 opções, **recomendada explícita + razão de uma linha**.
   Saturação = 2 perguntas seguidas com "tanto faz" → pare de perguntar.
4. Se não houver: declare "Não identifiquei bifurcações materiais nesta Stage"
   e gere o concept direto.
5. Escrever `docs/stages/<N.M>-<slug>/concept.md` seguindo `templates/stage-concept.md`.
   Frontmatter conforme `CONVENTIONS.md` §2. Seções inaplicáveis **removidas**
   (não escrever "N/A").
6. Para cada decisão maior com alternativa real descartada → ADR em
   `docs/adr/<N>_<M>_NNNN-<slug>.md` (`templates/adr.md`, `status: accepted`).
7. Autovalidar contra checklist do Passo 5 do runbook (PIPELINE §7.4):
   escopo, decisões rastreáveis, contratos batem com roadmap, critérios
   objetivos, §12 100% sim, ADRs `accepted`, cabe em 3–8 Tasks.
8. Marcar `status: done` no frontmatter do concept.
9. **Commit** (único — não passar por draft intermediário nesta variante):
   ```bash
   git add docs/stages/<N.M>-<slug>/concept.md docs/adr/<N>_<M>_*.md
   git commit -m "stage <N.M>: conceptual approved

   Refs #<issue>"
   ```

## Fase 3B — Technical

1. Escrever `docs/stages/<N.M>-<slug>/technical.md` seguindo
   `templates/stage-technical.md`. Frontmatter conforme `CONVENTIONS.md` §2
   (incluindo `stage_id`, `step_id`, `depends_on`, `concept_ref`, `issue_id`,
   `branch`, `tasks_count`).
2. Cada Task **deve** cumprir os 5 critérios de Task Atômica (PIPELINE §4.3):
   - Commitável de forma limpa.
   - Tipicamente ≤ 5 arquivos.
   - Checks objetivos definidos.
   - Não mistura criação de port com criação de adapter desse port.
   - Ordem respeita dependências.
3. Para Stages targeting domain/application/adapters, aplicar skill
   `task-ordering-hex` (TDD inside-out, cada commit deixa o build verde).
4. Número saudável: **3–8 Tasks**. Se > 8, declare Stage grande demais e PARE.
5. Incluir §7 "Execução" com marcadores
   `<!-- BEGIN: post-execution -->` / `<!-- END: post-execution -->` (vazios).
6. Marcar `status: done` no frontmatter do technical.

### Verificação de gap no Concept (UMA PASSADA — sem loop)

Depois de escrever o technical, releia o concept e responda **uma vez**:

- Algum critério de aceite do concept ficou impossível de mapear em Task?
- Algum contrato declarado no concept foi contradito pelas Tasks?
- O technical introduziu decisão arquitetural que deveria ser ADR?

**Critério para regredir o concept** (regressão custa commit + re-aprovação):
APENAS se a resposta muda **contrato**, **fronteira da Stage**, ou
**critério de aceite**. Refinamento de detalhe que não muda contrato
**NÃO** regride — vira `[decision]`/`[deviation]` em §7 durante execução.

**Não entre em loop.** Esta verificação acontece **uma vez**. Se passou,
seguir.

Se gap material identificado (raro):

```bash
# 1. Concept volta para draft
# (editar docs/stages/<N.M>-<slug>/concept.md ajustando o gap + status: draft)
git add docs/stages/<N.M>-<slug>/concept.md
git commit -m "chore(concept): revert to draft -- revision-from-technical: <motivo curto>

Refs #<issue>"

# 2. Concept ajustado + status: done
git add docs/stages/<N.M>-<slug>/concept.md docs/adr/<N>_<M>_*.md
git commit -m "stage <N.M>: conceptual approved

Refs #<issue>"

# 3. Technical ajustado também, se necessário (commit único do technical aprovado)
```

**Commit do technical aprovado:**

```bash
git add docs/stages/<N.M>-<slug>/technical.md
git commit -m "stage <N.M>: technical approved

Refs #<issue>"
```

## Fase 4 — Execução por Task

Para cada Task em ordem:

1. **Escopo estrito:** só tocar nos arquivos listados em "Arquivos a
   criar/modificar" da Task. Se precisar tocar algo extra → **PARAR** e
   perguntar via `AskUserQuestion`.
2. **Identificar lacunas** (decisão de código ausente em Concept+Technical+LAYOUT+skills):
   - **Reversível barato** (escolha local, trivial mudar) → IA decide, segue,
     registra justificativa de 1–2 frases no diff.
   - **Irreversível ou caro** (port shape, contrato externo, formato persistido) →
     PERGUNTA antes de codar.
3. **Implementar** (apresentar diff ao humano antes do commit — não comitar
   por iniciativa própria).
4. **Rodar checks da Task.** Se falhar:
   - Ajuste menor (import faltando, type hint) → corrige.
   - Problema de design → PARA e reporta.
5. **Registrar em §7 do technical** qualquer entrada surgida na execução,
   conforme RUNBOOK Passo 8 (entre marcadores `BEGIN/END: post-execution`):
   - `[decision]` — decisão tomada com base em pergunta.
   - `[finding]` — escalado para próxima Stage.
   - `[deviation]` — ajuste pequeno claramente in-scope (continua exigindo
     pergunta).
6. **Commit:**
   ```bash
   git add <arquivos-da-task>
   git commit -m "<type>(<scope>): <desc> [<N.M>/task-NN]

   Refs #<issue>"
   ```

# AUDITORIA DE TESTES (GATE EXPLÍCITO — NÃO PULAR)

Depois da última Task funcional, **antes** do gate de saída da Stage,
responda **por escrito**, em ordem:

1. **Caminho feliz coberto?** Cada critério de aceite do concept tem teste
   que valida o golden path?
2. **Edge cases do concept cobertos?** Cada caso de erro declarado nos
   §casos-de-erro/§invariantes do concept tem teste dedicado?
3. **Bug silencioso (mutation mental):** para cada função / regra de negócio
   crítica, pergunte:
   - Se eu trocasse `==` por `!=` aqui, algum teste falharia?
   - Se eu retornasse o default em vez de calcular, algum teste falharia?
   - Se eu inverter a ordem de validações, algum teste falharia?
   - Se eu ignorar uma branch condicional, algum teste falharia?
   "Não" em qualquer item indica cobertura insuficiente.
4. **Boundaries (in/out ports) cobertos?** Adapters têm contract tests
   (`pytest-with-fakes` §contract)? Use cases testados com fakes dos out
   ports?
5. **Integração cobre o que unit não cobre?** Há teste exercitando o fluxo
   end-to-end pela API / CLI / job, com adapter real onde aplicável?
6. **Erros do adapter mapeiam corretamente?** Para adapters HTTP, exceções
   de domínio batem com status HTTP esperado?

**Se a resposta a qualquer item for "não satisfeito":**

- Não é overengineering — é cobertura faltante de gap legítimo.
- Proponha testes faltantes ao humano (sem pedir aprovação prévia se óbvio).
- Implemente como Task extra com commit dedicado:
  `test(<scope>): cobrir <X> [<N.M>/task-NN-extra]`
- Re-execute a auditoria a partir do item 1.

**Loop até todas as respostas serem "sim".** Este é o único loop legítimo
do fluxo — sem ele, o resto dos gates dá falso positivo.

# GATES DE SAÍDA DA STAGE (INEGOCIÁVEIS)

Todos OBRIGATÓRIOS antes de você reportar a Stage como pronta para o commit
final `stage <N.M>: complete` (que **o usuário** fará manualmente — ver abaixo):

- [ ] `make check` verde localmente.
- [ ] `make test-cov` mostra coverage ≥ 90% no código novo da Stage
      (não na média do repo — no diff da Stage).
- [ ] `python scripts/check_technical_postexec.py docs/stages/<N.M>-<slug>/technical.md` verde.
- [ ] Auditoria de Testes (acima) com todos os itens "sim".
- [ ] §7 do technical reflete o que realmente aconteceu na execução.
- [ ] Findings escalados (`[finding]`) têm Stage candidata identificada.
- [ ] `docs/roadmap.md` atualizado: Stage `<N.M>` com `status: done`,
      `updated_at` e `last_reviewed_at` na data de hoje.
- [ ] ADRs novos em `status: accepted`.
- [ ] `concept.md` não precisa retoque retrospectivo (se precisa: abrir
      TODO ou Stage de correção; não silenciar).

Comando do lint da §7 antes de reportar:

```powershell
python scripts/check_technical_postexec.py "docs/stages/<N.M>-<slug>/technical.md"
```

**Commit final — NÃO É VOCÊ QUEM FAZ.**

Você atualiza o conteúdo do `docs/roadmap.md` (status `done`, `updated_at`,
`last_reviewed_at`), mas **deixa a mudança no working tree, sem commitar**. O
commit final `stage <N.M>: complete` é **manual**, feito pelo usuário **depois**
de uma auditoria humana — que tipicamente encontra fixes que precisam entrar
antes de fechar a Stage. Comitar `complete` por iniciativa própria fecharia a
Stage prematuramente.

Deixe `git status` mostrando claramente o que está pendente de commit (inclusive
o `docs/roadmap.md` editado) e inclua no relatório o comando sugerido para o
usuário rodar após a auditoria:

```bash
git add docs/roadmap.md
git commit -m "stage <N.M>: complete

Refs #<issue>"
```

# PROTOCOLO DE PERGUNTA

**Quando PERGUNTAR (`AskUserQuestion`):**

- Decisão material com alternativas reais, ausente nos docs.
- Lacuna que afeta **contrato**, **fronteira** ou **critério de aceite**.
- Escopo estrito violado (Task precisa tocar arquivo fora da lista).
- Auditoria de testes revelou cobertura insuficiente **com mais de uma
  estratégia razoável**.
- Contradição entre fontes (Overview vs Roadmap vs Concept vs código).

**Quando NÃO perguntar:**

- Detalhes seguidos por convenção (LAYOUT, CONVENTIONS, skills aplicáveis).
- Decisões já fechadas em Overview/Roadmap/Concept/Technical.
- Reversíveis triviais (nome de variável local, ordem de imports).

**Formato:**

- Contexto curto (1–2 frases).
- 2–4 opções com prós/contras de 1 linha cada.
- Uma marcada como **(Recomendada)** + razão de 1 linha.

**Nuance importante:** "estritamente necessário" não significa "pergunte
o mínimo a qualquer custo". Gap legítimo (afeta contrato, segurança,
critério de aceite) DEVE virar pergunta — não tratar como burocracia.
O que evitar é **overengineering** e **refinamento cosmético**, não
validação de gap real.

# REGRA DE FECHAMENTO E PR (CRÍTICA — NÃO VIOLAR)

**VOCÊ NUNCA FECHA A STAGE NEM ABRE PR.** Não execute o commit final
`stage <N.M>: complete`. Não execute `gh pr create`. Não execute `git push`.
Não execute `gh pr merge`.

O commit final e o PR são feitos **manualmente pelo usuário**, na mesma etapa,
**após auditoria humana** — que normalmente encontra fixes a aplicar antes de
fechar. Seu trabalho termina com os gates verdes, o `roadmap.md` editado no
working tree (sem commit) e o relatório abaixo.

Sua **saída final** é um **relatório** com a estrutura abaixo:

```markdown
## Stage <N.M>-<slug> — relatório de execução

### 1. Implementação
- Tasks executadas (lista com commit hash de cada uma).
- Arquivos tocados (resumido).
- ADRs criados / atualizados.

### 2. Ajustes durante o processo
(vazio se não houve)
- Regressões de concept/technical (com motivo).
- Entradas em §7 (`[decision]`/`[finding]`/`[deviation]`).
- Findings escalados (com Stage candidata).

### 3. Auditoria de testes
1. Caminho feliz coberto? <sim/não + evidência>
2. Edge cases do concept cobertos? <...>
3. Mutation mental (bug silencioso)? <...>
4. Boundaries cobertos? <...>
5. Integração cobre o que unit não cobre? <...>
6. Erros do adapter mapeiam corretamente? <...>

### 4. Gates de saída
- [x] `make check` verde
- [x] Coverage ≥ 90% no código novo
- [x] `check_technical_postexec.py` verde
- [x] §7 reflete execução real
- [x] Findings com Stage candidata
- [x] `roadmap.md` atualizado
- [x] ADRs em `accepted`

### 5. Fechamento e PR (o usuário faz manualmente, após auditoria)

**Pendências no working tree** (rodar `git status` e listar aqui o que falta
commitar — em especial o `docs/roadmap.md` editado).

**Título:**
```
feat: stage <N.M> — <title_humano>
```

**Descrição:**
```
Closes #<issue>

## Stage <N.M>-<slug>

<resumo de 2–3 linhas do que foi implementado>

Ver `docs/stages/<N.M>-<slug>/concept.md` e `technical.md`.

## Checklist
- [x] Tasks implementadas conforme technical.md
- [x] make check verde
- [x] Coverage ≥ 90% no código novo
- [x] roadmap.md atualizado (status done)
- [x] ADRs em accepted
- [x] Auditoria de testes em todos os itens "sim"
```

**Comandos sugeridos para o usuário rodar (após a auditoria e eventuais fixes):**
```powershell
# 1. Commit final que fecha a Stage (manual, pós-auditoria)
git add docs/roadmap.md
git commit -m "stage <N.M>: complete

Refs #<issue>"

# 2. Push e abertura do PR
git push -u origin <branch>
gh pr create --base develop --title "..." --body "..."
```
```

O usuário fará a auditoria, aplicará fixes se preciso, fará o commit final
`stage <N.M>: complete`, o `git push`, abrirá o PR, vai esperar CI/aprovação e
fará o merge. **Você não toca em nenhuma dessas etapas.**

# CONTRADIÇÕES

Hierarquia de fonte (alta para baixa): **Overview > Roadmap > Concept >
Technical > Código**.

Se a qualquer momento descobrir:
- Concept contradiz Overview/Roadmap/código existente → PARE, aponte com
  referência explícita à fonte conflitante, peça orientação.
- Technical contradiz Concept/LAYOUT → PARE, aponte, peça orientação.
- Implementação contradiz Technical/Concept → PARE, aponte, peça orientação.

**Não silencie contradição. Não tente resolver sozinho contradição com
fonte mais alta na hierarquia.**

# ORDEM DE EXECUÇÃO RESUMIDA

1. Verificar pré-condições.
2. Carregar contexto (ler docs listados).
3. **Fase 3A**: gerar concept (perguntas se houver bifurcação material) →
   ADRs se aplicável → commit `stage <N.M>: conceptual approved`.
4. **Fase 3B**: gerar technical → verificação de gap (uma passada) →
   ajustar concept SE gap material → commit `stage <N.M>: technical approved`.
5. **Fase 4**: para cada Task: implementar → checks → registrar §7 se
   necessário → commit `<type>(<scope>): <desc> [<N.M>/task-NN]`.
6. **Auditoria de testes**: loop até todos os itens "sim". Testes faltantes
   viram Tasks extras com commit dedicado.
7. **Gate de saída**: todos os gates verdes → atualizar `roadmap.md` no working
   tree (**sem commitar**). O commit final `stage <N.M>: complete` é manual,
   feito pelo usuário após auditoria.
8. **Relatório final** + recomendação de fechamento/PR.

**PARE aqui.** Não faça o commit `complete`. Não faça push. Não abra PR. Não merge.
````

---

## Related

Caminhos relativos a este arquivo (`docs/PROMPT-stage-single-session.md` no projeto destino):

- Procedimento canônico: [`./RUNBOOK-STAGE-LIFECYCLE.md`](./RUNBOOK-STAGE-LIFECYCLE.md)
- Pipeline conceitual: [`./PIPELINE.md`](./PIPELINE.md)
- Convenções: [`./CONVENTIONS.md`](./CONVENTIONS.md)
- Git workflow: [`./GIT-WORKFLOW.md`](./GIT-WORKFLOW.md)
- Variante para **issue avulsa** (sem concept/technical): [`./PROMPT-issue-single-session.md`](./PROMPT-issue-single-session.md)
- Templates de Stage: [`./templates/`](./templates/)
