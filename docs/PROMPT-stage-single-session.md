---
title: Prompt — Execução de Stage em Sessão Única
description: Prompt para colar em uma nova sessão Chat IDE e rodar Fase 3A + 3B + 4 de uma Stage em uma única sessão, sem perder gates objetivos
when-use: Fluxo padrão de execução de Stage (PIPELINE §11.1, implementa → audita) — Fase 3A+3B+4 em sessão única, com auditoria em sessão separada
keywords: [prompt, stage, single-session, concept, technical, execucao, lifecycle, review, subagents, gates]
status: done
created_at: 2026-06-10
updated_at: 2026-07-05
---

# Prompt — Execução de Stage em Sessão Única

Variante **colapsada** do [`./RUNBOOK-STAGE-LIFECYCLE.md`](./RUNBOOK-STAGE-LIFECYCLE.md):
mesmo fluxo, mesmos gates objetivos, mesmos artefatos — sem as transições
de sessão e sem o gate humano por aprovação textual entre fases (pausa
opcional antes da Fase 4; ver §Fluxo).

**Quando usar:** é o **fluxo padrão** de execução de Stage
(PIPELINE §11.1 — sessão de implementação; a auditoria roda em sessão
separada via `stage-audit`). O ganho é evitar re-hidratar contexto entre
3A → 3B → 4.

**Quando NÃO usar (preferir o runbook multi-sessão, fase a fase):**
- Stage com decisões arquiteturais grandes — sessão dedicada por fase.
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
7. Autovalidar contra o checklist do Passo 5 do runbook (fonte única):
   escopo, decisões rastreáveis, contratos batem com roadmap, critérios
   objetivos, canal de emissão declarado se produz métrica nova (último
   quilômetro), §12 100% sim, ADRs `accepted`, cabe em 3–12 Tasks.
8. **Checkpoint A — revisão do concept por agentes independentes**
   (protocolo em §Revisão por Agentes Independentes). Dois subagentes
   com lentes distintas, em paralelo:
   - **Conformidade:** concept × roadmap × overview × ADRs × §7 das
     dependências — caçar contradições e escopo que vazou.
   - **Domínio/testabilidade:** os conceitos de negócio estão corretos?
     Os critérios de aceite são objetivamente testáveis ou são desejos
     vagos?
   Só seguir depois de registrar a disposição de cada achado.
9. Marcar `status: done` no frontmatter do concept.
10. **Commit** (único — não passar por draft intermediário nesta variante):
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
4. Número saudável: **3–12 Tasks**; **≥ 14** = Stage grande demais — declare e PARE (alarme do CONVENTIONS §6).
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

### Checkpoint B — revisão do technical por agente independente

Antes do commit, um subagente (protocolo em §Revisão por Agentes
Independentes) valida mecanicamente:

- **Matriz de rastreabilidade:** todo critério de aceite do concept
  mapeia em ≥ 1 Task com check objetivo. Critério órfão = achado.
- Caminhos de arquivo conformes a `LAYOUT.md`.
- Cada Task contra os 5 critérios de Task Atômica (PIPELINE §4.3).

Registrar a disposição de cada achado antes de commitar.

**Commit do technical aprovado:**

```bash
git add docs/stages/<N.M>-<slug>/technical.md
git commit -m "stage <N.M>: technical approved

Refs #<issue>"
```

### Pausa opcional de gate humano (fluxo ideal antes da Fase 4)

Se houve **bifurcação material relevante** ou decisão de peso no
concept/technical (ADR novo, contrato novo, modelo de dados), **ofereça
a pausa** via `AskUserQuestion`: "revisar concept+technical agora" vs
"seguir direto para a execução" — recomendada conforme o peso. Se o
usuário pediu a pausa no kickoff, **PARE aqui** e aguarde a revisão dos
dois artefatos. Stage sem decisão de peso: siga direto, sem perguntar.

## Fase 4 — Execução por Task

**Arquivo de estado (anti-perda de contexto):** antes da primeira Task,
criar no diretório temporário da sessão (scratchpad — **fora do repo**)
uma tabela `Task → status → hash do commit`, atualizada após cada
commit. Após qualquer compactação de contexto, reconstruir o estado a
partir dela e de `git log --oneline origin/develop..HEAD` antes de
continuar — os hashes do relatório final saem daí, não da memória.

Para cada Task em ordem:

1. **Re-hidratar:** reler a Task no `technical.md` e a seção de
   contratos do `concept.md` antes de implementar. Nunca implementar
   de memória — especialmente após compactação de contexto.
2. **Escopo estrito:** só tocar nos arquivos listados em "Arquivos a
   criar/modificar" da Task. Se precisar tocar algo extra → **PARAR** e
   perguntar via `AskUserQuestion`.
3. **Identificar lacunas** (decisão de código ausente em Concept+Technical+LAYOUT+skills):
   - **Reversível barato** (escolha local, trivial mudar) → IA decide, segue,
     registra justificativa de 1–2 frases no diff.
   - **Irreversível ou caro** (port shape, contrato externo, formato persistido) →
     PERGUNTA antes de codar.
4. **Implementar** (apresentar diff ao humano antes do commit — não comitar
   por iniciativa própria).
5. **Rodar checks da Task.** Baseline inegociável: **`make check` verde
   antes de todo commit**, além dos checks específicos da Task. Se falhar:
   - Ajuste menor (import faltando, type hint) → corrige.
   - Problema de design → PARA e reporta.
6. **Registrar em §7 do technical** qualquer entrada surgida na execução,
   conforme RUNBOOK Passo 8 (entre marcadores `BEGIN/END: post-execution`):
   - `[decision]` — decisão tomada com base em pergunta.
   - `[finding]` — escalado para próxima Stage.
   - `[deviation]` — ajuste pequeno claramente in-scope (continua exigindo
     pergunta).
7. **Commit** (e atualizar o arquivo de estado com o hash):
   ```bash
   git add <arquivos-da-task>
   git commit -m "<type>(<scope>): <desc> [<N.M>/task-NN]

   Refs #<issue>"
   ```

**Checkpoint C — revisão por bloco de Tasks:** a cada 2–3 Tasks
commitadas (ou uma única vez ao final, se a Stage tem ≤ 4 Tasks), um
subagente revisa o diff acumulado do bloco
(`git diff <hash-do-último-checkpoint>..HEAD`) contra concept +
technical + LAYOUT (protocolo em §Revisão por Agentes Independentes).
Correções viram commit `fix(<scope>): <desc> [<N.M>/task-NN-fix]`.

**Regressão mid-stage:** se uma Task revelar que Task anterior foi
implementada errada:

- Erro local (não muda design) → commit
  `fix(<scope>): <desc> [<N.M>/task-NN-fix]` + entrada `[deviation]`
  em §7.
- Erro que invalida decisão de §1–§6 do technical → **PARAR** e
  perguntar via `AskUserQuestion`; pode exigir regressão do technical.

# REVISÃO POR AGENTES INDEPENDENTES (CHECKPOINTS A/B/C)

Esta variante colapsou os gates humanos do runbook canônico; os
checkpoints são o substituto do olhar externo. Sem eles, a variante
não é "runbook colapsado" — é "runbook sem revisão". Regras:

- **Contexto zerado:** cada revisor é um subagente novo (Agent tool),
  que recebe SÓ os caminhos dos arquivos e das fontes — nunca o
  histórico da sessão nem o raciocínio do autor. O autor não revisa o
  próprio artefato: a sessão que escreveu vai "verificar" com o mesmo
  raciocínio que gerou o erro.
- **Prompt adversarial:** instruir o revisor a ENCONTRAR erros ("tente
  refutar"), nunca a confirmar. Revisor convidado a aprovar, aprova.
- **Filtro de severidade:** o revisor só reporta o que muda contrato,
  comportamento ou cobertura. Estilo/cosmético não é achado.
- **Disposição explícita para todo achado:** `corrigido` (com commit),
  `refutado` (com evidência citada — linha/fonte que refuta), ou
  `escalado` (vira `AskUserQuestion`). **Proibido descartar achado em
  silêncio.** As disposições entram no relatório final.
- **Cap de 2 rodadas por checkpoint.** Divergência persistente entre
  autor e revisor → `AskUserQuestion`. O único loop sem cap do fluxo
  continua sendo a Auditoria de Testes.
- **Alívio condicional:** Stage com `gate_mode: batch` sobre fundação
  validada pode reduzir o Checkpoint A a 1 revisor (lente de
  conformidade). Checkpoint C e a regra de evidência dos gates NUNCA
  são opcionais.

# AUDITORIA DE TESTES (GATE EXPLÍCITO — NÃO PULAR)

Depois da última Task funcional, **antes** do gate de saída da Stage,
**delegar a auditoria a um subagente que não escreveu os testes**
(contexto zerado; recebe código + testes + concept + este
questionário). O autor não se autoaudita — responder "sim" de memória
é o falso verde clássico. O subagente responde **por escrito**, em ordem:

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
   **Mutação real (não só mental):** para as 2–3 funções mais críticas
   da Stage, não responder de memória — aplicar a mutação de verdade
   (editar → rodar `make test` → reverter) e colar o resultado.
   Mutação que não derruba nenhum teste = cobertura insuficiente
   comprovada.
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

**Regra de evidência:** um gate só conta como verificado se a **saída
literal do comando** (últimas linhas + exit code) estiver colada no
relatório final. Gate sem saída colada = gate não executado — afirmar
"passou" sem evidência é falso verde.

Todos OBRIGATÓRIOS antes do commit final `stage <N.M>: complete`:

- [ ] `make check` verde localmente.
- [ ] Coverage ≥ 90%: global (`make test-cov`, gate `fail_under`) **e**
      nos arquivos da Stage, via cobertura focada
      (`pytest --cov=<paths da Stage> --cov-report=term-missing`) —
      a média global não substitui (gate míope). **Medição por arquivo**
      (não existe diff-cover no projeto):
      ```powershell
      # arquivos de src/ tocados pela Stage
      git diff --name-only (git merge-base origin/develop HEAD) HEAD -- src/
      # cobertura por arquivo
      uv run pytest tests/ --cov=src/financial_forecasting --cov-report=term-missing
      ```
      Cada arquivo tocado deve aparecer com ≥ 90% na tabela do
      `term-missing`. Arquivo abaixo disso → cobrir ou justificar por
      escrito no relatório.
- [ ] `python scripts/check_technical_postexec.py docs/stages/<N.M>-<slug>/technical.md` verde.
- [ ] Auditoria de Testes (acima) com todos os itens "sim".
- [ ] Checkpoints A, B e C executados, com **todos os achados
      dispostos** (`corrigido`/`refutado`/`escalado`).
- [ ] **Verificação end-to-end:** fluxo da Stage exercitado pelo
      entrypoint real (API/CLI/job) quando houver superfície de
      runtime — testes passando não substituem executar o fluxo.
- [ ] §7 do technical reflete o que realmente aconteceu na execução.
- [ ] Findings escalados (`[finding]`) têm Stage candidata identificada.
- [ ] `docs/roadmap.md` atualizado: Stage `<N.M>` com `status: done`,
      `updated_at` e `last_reviewed_at` na data de hoje.
- [ ] ADRs novos em `status: accepted`.
- [ ] `concept.md` não precisa retoque retrospectivo (se precisa: abrir
      TODO ou Stage de correção; não silenciar).

Comando do lint da §7 antes do commit final:

```powershell
python scripts/check_technical_postexec.py "docs/stages/<N.M>-<slug>/technical.md"
```

**Commit final:**

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

# REGRA DE PR

**Você ABRE o PR ao final** (`git push` + `gh pr create`) — a sessão que
implementou é quem abre. Antes do push, **sincronize**: `git fetch` +
`git rebase origin/develop` (o `roadmap.md` é o conflito recorrente; ver
GIT-WORKFLOW §Etapa 4). **Você NÃO faz merge** — o merge é do usuário, salvo
pedido explícito. Não execute `gh pr merge`.

**O checklist do PR é um handoff.** Marque **apenas** as caixinhas que você
**validou com certeza**; deixe as demais **desmarcadas** e registre no corpo
que o PR **precisa de auditoria antes de aceitar/mergear** — a sessão de
auditoria valida o resto e completa o checklist. Não marque por otimismo.

Sua **saída final** = (1) o **PR aberto** e (2) o **relatório** abaixo:

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

### 3. Revisões por agentes independentes
- Checkpoint A (concept): <achados + disposição de cada um>
- Checkpoint B (technical): <achados + disposição de cada um>
- Checkpoint C (blocos de Tasks): <achados + disposição de cada um>
(disposições: `corrigido` com hash / `refutado` com evidência / `escalado`)

### 4. Auditoria de testes (executada por subagente independente)
1. Caminho feliz coberto? <sim/não + evidência>
2. Edge cases do concept cobertos? <...>
3. Mutação (mental + real nas funções críticas)? <resultado das mutações reais>
4. Boundaries cobertos? <...>
5. Integração cobre o que unit não cobre? <...>
6. Erros do adapter mapeiam corretamente? <...>

### 5. Gates que VOCÊ validou (com evidência colada — sem evidência, gate não conta)
- [ ] `make check` verde — <últimas linhas da saída + exit code>
- [ ] Coverage ≥ 90% por arquivo tocado — <linhas relevantes do term-missing>
- [ ] `check_technical_postexec.py` verde — <saída>
- [ ] Checkpoints A/B/C com achados dispostos
- [ ] Verificação end-to-end — <o que foi exercitado + resultado>
- [ ] §7 reflete execução real
- [ ] Findings com Stage candidata
- [ ] `roadmap.md` atualizado
- [ ] ADRs em `accepted`

### 6. PR aberto
- Link: <url do PR>
- Corpo carregado do template `.github/PULL_REQUEST_TEMPLATE.md` (fonte
  única): `Closes #<issue>` + resumo + checklist com **só o que você
  validou** marcado + nota "⚠️ precisa de auditoria antes do merge".
```

**Comandos que você executa** (o merge NÃO):
```powershell
git fetch origin
git rebase origin/develop        # resolver conflito de roadmap se houver
git push -u origin <branch>
gh pr create --base develop --title "feat(<escopo>): stage <N.M> — <title_humano>" --body-file <corpo>
# <escopo> = BC/módulo da mudança (ASCII/kebab), NUNCA a Stage — CONVENTIONS §4(c)
```

Depois do PR aberto, a sessão de auditoria valida e completa o checklist; o
CI roda e **o usuário faz o merge** (salvo pedido explícito).

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
   ADRs se aplicável → **Checkpoint A** (2 subagentes, lentes distintas) →
   commit `stage <N.M>: conceptual approved`.
4. **Fase 3B**: gerar technical → verificação de gap (uma passada) →
   ajustar concept SE gap material → **Checkpoint B** (matriz de
   rastreabilidade) → commit `stage <N.M>: technical approved`
   → **pausa opcional de gate humano** (se houve decisão de peso).
5. **Fase 4**: criar arquivo de estado; para cada Task: re-hidratar →
   implementar → checks + `make check` → registrar §7 se necessário →
   commit `<type>(<scope>): <desc> [<N.M>/task-NN]` → atualizar estado.
   **Checkpoint C** a cada 2–3 Tasks.
6. **Auditoria de testes** (subagente independente + mutação real):
   loop até todos os itens "sim". Testes faltantes viram Tasks extras
   com commit dedicado.
7. **Gate de saída**: todos os gates verdes **com evidência colada** →
   commit `stage <N.M>: complete`.
8. **Abrir o PR** (`git fetch` + rebase + `git push` + `gh pr create`) +
   relatório final (com disposições dos checkpoints).

**PARE no merge.** Você faz push e abre o PR; o **merge é do usuário** (salvo pedido explícito). Não execute `gh pr merge`.
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
