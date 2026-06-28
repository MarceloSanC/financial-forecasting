# Pipeline de Desenvolvimento Iterativo Guiado por IA

> Documentação operacional consolidada. Cobre da ideia inicial ao commit,
> com prompts pré-definidos, regras de condução de sessão e gates humanos.
> Alinhada aos templates em [`templates/`](./templates/) e às regras de
> [`CONVENTIONS.md`](./CONVENTIONS.md).

---

## Introdução

### Propósito

Este documento descreve **como conduzir um projeto de software do zero ao
código**, usando IA como copiloto em todas as fases. Define:

- A sequência de fases (Overview → Roadmap → Concept → Technical → Execução).
- Onde cada fase roda (template vs. projeto destino).
- Os prompts canônicos para conduzir cada fase.
- Os gates humanos que separam fases.
- Os artefatos produzidos, com referência ao template correspondente em [`templates/`](./templates/).
- Como tratar contradições, retornos de fase e exceções.

Regras de **nomenclatura, frontmatter, status, branches, commits e
tamanhos** vivem em [`CONVENTIONS.md`](./CONVENTIONS.md) — este documento
remete sem duplicar.

### Escopo

- **Stack alvo:** backend Python em Arquitetura Hexagonal com *vertical
  slicing* por bounded context. O pipeline em si é reaproveitável para
  outras stacks.
- **Tamanho alvo:** um repositório por projeto. Monorepos exigem ajuste
  (ver [§14 Itens em aberto](#14-itens-em-aberto)).
- **Modelo de execução:** solo ou time pequeno, com humano fazendo gate
  de cada fase e cada commit.

### Público-alvo

- **Devs** que executam o pipeline.
- **Tech leads** que revisam gates.
- **IA (Claude Code, Codex)** que consome os artefatos como contexto.

---

## Sumário

1. [Visão geral](#1-visão-geral)
2. [Princípios fundamentais](#2-princípios-fundamentais)
3. [Pré-requisitos do projeto](#3-pré-requisitos-do-projeto)
4. [Vocabulário e critérios de atomicidade](#4-vocabulário-e-critérios-de-atomicidade)
5. [Fase 1 — Overview](#5-fase-1--overview)
6. [Fase 2 — Roadmap](#6-fase-2--roadmap)
7. [Fase 3A — Concept (por Stage)](#7-fase-3a--concept-por-stage)
8. [Fase 3B — Technical (por Stage)](#8-fase-3b--technical-por-stage)
9. [Fase 4 — Execução (por Task)](#9-fase-4--execução-por-task)
10. [Fluxo Git](#10-fluxo-git)
11. [Condução de sessões](#11-condução-de-sessões)
12. [Tratamento de exceções](#12-tratamento-de-exceções)
13. [Skills canônicas](#13-skills-canônicas)
14. [Itens em aberto](#14-itens-em-aberto)
15. [Checklist operacional](#15-checklist-operacional)
16. [Glossário](#glossário)

---

## 1. Visão geral

### 1.1 Fluxo macro

```
Fase 1 — Overview                                          (Chat IDE no template)
   │  produz: projects/<projeto-slug>/overview.md
   ▼
Fase 2 — Roadmap                                           (Chat IDE no template)
   │  produz: projects/<projeto-slug>/roadmap.md  (Steps → Stages)
   ▼
Para cada Stage, em ordem linear (Chat IDE no projeto destino):
   │
   ├─ Fase 3A — Concept                                    (questionário focado)
   │     produz: docs/stages/N.M-<slug>/concept.md
   │     gate humano  →  status: done
   │
   ├─ Fase 3B — Technical                                  (lista de Tasks)
   │     produz: docs/stages/N.M-<slug>/technical.md
   │     gate humano  →  status: done
   │     ⇄ pode forçar concept.status → draft (regressão; CONVENTIONS §3.2)
   │
   └─ Fase 4 — Execução                                    (task a task = commits)
         pré-requisito: concept.status == done E technical.status == done
         produz: código + testes
         gate humano por Task (revisão de diff antes do commit)
         §7 do technical.md cresce com [decision]/[finding]/[deviation]
```

> **Início da Fase 3B é flexível.** O draft do `technical.md` pode
> começar enquanto o `concept.md` ainda está em `draft` — útil para
> validar o plano em paralelo à revisão do concept. O gate da Fase 3B
> (`stage N.M: technical approved`) sim exige `concept.status == done`
> no momento. **Início da Fase 4 é rígido**: ambos `done` (CONVENTIONS §3.2).

> **A unidade de ciclo é a Stage**, não o Step. Step agrupa Stages no
> Roadmap para fins de comunicação de negócio, mas não tem
> `concept.md`/`technical.md` próprios e não vira branch.

### 1.2 Onde cada fase roda

| Fase | Onde | Por quê |
|---|---|---|
| 1. Overview | Chat IDE no repo `whaka-dev-project-template` | Acesso a templates, ADRs padrão, CONVENTIONS, skills; persiste em diretório do template. |
| 2. Roadmap | Chat IDE no repo `whaka-dev-project-template` | Mesma sessão/contexto da Fase 1; persiste em diretório do template. |
| 3A. Concept | Chat IDE no repo do projeto destino | Precisa de filesystem (tree, LAYOUT, código existente, template, ADRs anteriores). |
| 3B. Technical | Chat IDE no repo do projeto destino | Precisa de filesystem, tree, arquivos. |
| 4. Execução | Chat IDE no repo do projeto destino | Edição de código. |

**Transição Fase 2 → Fase 3A:** após overview e roadmap aprovados no
template, inicia-se o repositório do projeto destino copiando
boilerplate + templates + os dois artefatos. Procedimento detalhado em
[§14](#14-itens-em-aberto). Materializado em
[`RUNBOOK-INIT-PROJECT.md`](./RUNBOOK-INIT-PROJECT.md) Passos 6–8
(greenfield) ou [`RUNBOOK-ADOPT-EXISTING.md`](./RUNBOOK-ADOPT-EXISTING.md)
(legado).

### 1.3 Artefatos produzidos

| Artefato | Caminho | Template |
|---|---|---|
| Overview | `docs/overview.md` | [`templates/overview.md`](./templates/overview.md) |
| Roadmap | `docs/roadmap.md` | [`templates/roadmap.md`](./templates/roadmap.md) |
| Concept (por Stage) | `docs/stages/N.M-<slug>/concept.md` | [`templates/stage-concept.md`](./templates/stage-concept.md) |
| Technical (por Stage) | `docs/stages/N.M-<slug>/technical.md` | [`templates/stage-technical.md`](./templates/stage-technical.md) |
| ADR (quando aplicável) | `docs/adr/N_M_NNNN-<slug>.md` (mesma pasta para ADRs de Stage e globais; prefixo `N_M` no filename é o separador) | [`templates/adr.md`](./templates/adr.md) |
| Runbook (quando aplicável) | `docs/runbooks/<slug>.md` | [`templates/runbook.md`](./templates/runbook.md) |
| Código + testes | `src/`, `tests/` | — |

Todo artefato passa por gate humano antes de ser considerado `done`.
Ver [`CONVENTIONS.md`](./CONVENTIONS.md) §3 para a tabela de mapeamento
gate↔commit↔status.

---

## 2. Princípios fundamentais

Princípios abaixo são contrato. Toda fase, prompt e gate os respeita.
Quando houver conflito entre uma decisão local e um princípio, o
princípio vence.

1. **Generator ≠ Validator.** Quem gera não valida no mesmo turno.
   Checks objetivos rodam em separado (lint, type, test, layout).
2. **Enforcement estrutural > prompt.** Regras de arquitetura são
   codificadas em ferramentas (`import-linter`, `check_layout.py`,
   `mypy --strict`). Prompt é guia, não barreira.
3. **Decisão sem fonte = pergunta esquecida.** Toda decisão em uma doc
   deve rastrear Overview, Roadmap, código existente ou pergunta
   respondida.
4. **Preferível incompleto bem feito do que completo mal descrito.**
   Vale para Roadmap, concept, technical e código.
5. **Stage é a unidade de ciclo.** Concept → technical → execução
   acontece por **Stage**, não por Step inteiro.
6. **Linearidade estrita.** Sem paralelismo entre Stages. No modo solo,
   também não há paralelismo entre Steps. Em time, dois devs só tocam
   Stages de Steps diferentes em paralelo se as dependências do Roadmap
   permitirem.
7. **Bifurcação material define pergunta.** A IA pergunta se, e só se,
   precisaria escolher entre alternativas materialmente diferentes sem
   critério no contexto.
8. **Contradição trava.** Se uma resposta contradiz decisão prévia
   (Overview/Roadmap/código), a IA para e aponta. Não tenta resolver
   autonomamente.
9. **Git é o substrato.** Um branch por Stage, commits espelham gates e
   Tasks, aprovações = commits/merges. Sem máquina de estado paralela.
10. **Contexto cirúrgico.** Tree + LAYOUT + skills + doc atual + arquivos
    consultados sob demanda. Sem reler Overview/Roadmap inteiros a cada
    interação.
11. **Retorno de fase = nova sessão.** Quando uma fase posterior revela
    problema em fase anterior, abre-se nova sessão com o artefato a
    montante + nota do problema. Nunca emendar no meio de sessão de
    fase posterior.

---

## 3. Pré-requisitos do projeto

Antes da Fase 1, o repositório precisa do substrato mínimo.

### 3.1 Estrutura e LAYOUT

- `tree.txt` (gerado por `scripts/regen_tree.py`) descreve a árvore
  vertical com hexagonal interno.
- [`LAYOUT.md`](./boilerplate/layout-files/docs/LAYOUT.md) é contrato: mapeia tipo de artefato →
  caminho, regras de dependência entre camadas, nomenclatura,
  política de shared kernel. Referenciado por todos os prompts da IDE e
  validado por `scripts/check_layout.py`.

### 3.2 `CLAUDE.md` (contexto-raiz)

Arquivo na raiz, lido automaticamente pelo agent.

```markdown
# CLAUDE.md

Projeto: <nome>
Arquitetura: Hexagonal com vertical slicing por feature.

## Contexto sempre carregado (cirúrgico — Princípio 10)
- LAYOUT.md (convenções obrigatórias)
- tree.txt (estrutura atual)
- docs/stages/N.M-<slug>/concept.md (Stage atual, quando aplicável)
- docs/stages/N.M-<slug>/technical.md (Stage atual, quando aplicável)
- .claude/skills/ — descobertas automaticamente por descrição

## Carregar sob demanda (não pré-carregar)
- docs/overview.md — apenas quando Fase exige contexto de negócio não
  presente no concept.md
- docs/roadmap.md — apenas quando precisa entender vizinhança da Stage
  ou alterar plano

## Comandos úteis
- Checagem completa: `make check`
- Regenerar tree:    `python scripts/regen_tree.py`
- Validar layout:    `python scripts/check_layout.py`

## Antes de qualquer mudança
1. Verifique LAYOUT.md para a localização correta.
2. Verifique tree.txt para o estado atual.
3. Abra apenas os arquivos relevantes para a Task.
```

### 3.3 `CONVENTIONS.md`

Regras prescritivas de nomenclatura, frontmatter, status, branches,
commits e versionamento de docs. Ver
[`CONVENTIONS.md`](./CONVENTIONS.md).

### 3.4 Enforcement determinístico

Configurado na Stage `1.1-bootstrap`. Sem isso, o pipeline amplifica
desvios.

- **import-linter** com contratos refletindo `LAYOUT.md`.
- **mypy --strict** em `domain/` e `application/`.
- **ruff** para style.
- **pytest** com pastas separadas (`unit`, `integration`, `contract`, `e2e`).
- **pre-commit hook** rodando os quatro acima.
- **CI local (`make check`)** que reproduz o pre-commit.

### 3.5 Skills

Diretório `.claude/skills/<nome>/SKILL.md` (formato oficial Claude
Code). Cada skill é uma pasta com `SKILL.md` dentro. Ver
[§13 Skills canônicas](#13-skills-canônicas) para catálogo, formato e
protocolo de carregamento.

### 3.6 Templates

Diretório [`templates/`](./templates/) contém os formatos de saída dos
prompts. **Ao gerar um artefato, copiar o template e preencher**, em vez
de partir do zero.

---

## 4. Vocabulário e critérios de atomicidade

Três níveis hierárquicos, do macro ao micro:

| Nível | Definição | Granularidade típica | Onde mora |
|---|---|---|---|
| **Step** | Entrega de negócio ou recurso. **Descrição não-técnica**, sem restrição arquitetural. Agrupa Stages que produzem juntas o resultado de negócio. | Dias a semanas. | Seção do `roadmap.md` (apenas). |
| **Stage** | **Unidade de ciclo concept→technical→execução**. Atômica do ponto de vista técnico (foco coeso: camada-alvo principal **ou** fatia vertical end-to-end em 1 BC; ver §4.2). Equivale a 1 branch que vai do `conceptual draft` ao `complete` e mergeia em `develop`. | Horas a 2–3 dias. | `docs/stages/N.M-<slug>/` |
| **Task** | Subdivisão da execução = **1 commit**. | Minutos a poucas horas. | Item dentro do `technical.md` da Stage. |

### 4.1 Por que Step não tem restrição arquitetural

O Step é a unidade de comunicação para stakeholders ("o que o time
entrega esta quinzena"). Pode atravessar várias camadas e mais de um
bounded context — é normal um Step "Onboarding de usuário" tocar em
domain, application, adapters in/http e adapters out/persistence. **A
restrição arquitetural mora na Stage**, não no Step.

Forçar restrição arquitetural no Step gera Steps minúsculos e
fragmentados, que não comunicam valor de negócio.

### 4.2 Critério de Stage atômica

Stage é válida se, e só se, satisfaz todos:

1. Tem **um foco coeso**: ou (a) uma **camada-alvo principal** do
   hexagonal (`domain`, `application`, `adapters/in/http`,
   `adapters/out/<tech>`, `shared/infrastructure`, `bootstrap`) — típico
   de Stages de fundação (BC novo, ports compartilhados, integração
   transversal coesa como bootstrap de logging ou configuração de DI),
   **ou** (b) uma **fatia vertical** de funcionalidade end-to-end dentro
   de um único bounded context — típico de Stages de entrega (nova
   entidade/feature em BC já existente). Mistura dos dois = duas Stages.
2. Tem **um único `definition_of_done` testável**. Se a DoD precisa de
   "e" no meio, são duas Stages.
3. Ports introduzidos são consumidos por algo dentro da Stage **ou**
   declarados em Stage anterior que termina antes.
4. Sem deliverables em mais de um bounded context.
5. Complexidade estimada ≤ M. Se L/XL, **quebrar antes da Fase 3A**.

> **Fonte única.** Este é o critério canônico. Fase 2, Fase 3A e gates
> referenciam esta seção — não redefinem.

### 4.3 Critério de Task atômica

Cada Task deve:

1. Ser **commitável de forma limpa** (estado consistente entre commits).
2. Tocar tipicamente **≤ 5 arquivos**. Acima disso, revisar se é uma
   única Task — pode ser exceção legítima (rename mecânico, formatação
   em massa) ou Task grande demais que precisa ser quebrada.
3. Ter **checks objetivos** definidos (ex.: `mypy passa`,
   `pytest tests/unit/.../test_X.py passa`, `import-linter passa`).
4. Não misturar criação de port com criação de adapter desse port
   (Tasks separadas). **Exceção** permitida quando ambos são triviais
   (1 método, 1 adapter wrapper) e a exceção está **declarada
   explicitamente** no `technical.md` da Stage.
5. Respeitar dependências internas (port antes do use case que o
   consome; teste com fake antes de adapter real; schema antes de
   migration).

### 4.4 Numeração e slugs

Ver [`CONVENTIONS.md`](./CONVENTIONS.md) §1 para regras completas. Resumo:

- **Step** `N` — sequencial, sem zero-padding.
- **Stage** `N.M` — `M` é ordem dentro do Step `N`.
- **Task** `task-NN` — zero-padded.
- **ADR** — nome do arquivo: `N_M_NNNN-<slug>.md` (ex.:
  `2_3_0001-stream-vs-batch.md`) em `docs/adr/`; `adr_id` no
  frontmatter: `N.M.NNNN` (ex.: `2.3.0001`). `N.M` herda da Stage;
  `NNNN` é sequencial **dentro do prefixo `N_M`** (4 dígitos, não
  recicla) — o prefixo no filename é o separador namespace, **sem
  subpasta por Stage**. Cross-ref usa o `adr_id` completo — sem
  ambiguidade entre Stages.
- **Slug** em kebab-case inglês; o número `N.M` é prefixo de pasta/branch
  e **não conta como palavra do slug**.

---

## 5. Fase 1 — Overview

### 5.1 Objetivo

Produzir documento auditável com problema, escopo, domínio, stack,
arquitetura, requisitos e restrições. Input canônico da Fase 2.

### 5.2 Onde roda

Chat IDE no próprio repositório `whaka-dev-project-template`. Não há
código do projeto destino ainda — o template é o contexto (CONVENTIONS,
templates, ADRs padrão, skills). O `overview.md` gerado é persistido
em um diretório do template (ver [§14](#14-itens-em-aberto)).

### 5.3 Prompt da Fase 1

A IA cobre, em blocos temáticos (4–8 perguntas por bloco), todas as
seções aplicáveis de [`templates/overview.md`](./templates/overview.md).
Persona, princípios de pergunta, condução, contradições, condição de
parada e formato de saída descritos no prompt.

**Prompt completo para copy-paste:** [`RUNBOOK-INIT-PROJECT.md`](./RUNBOOK-INIT-PROJECT.md)
§Passo 2.

### 5.4 Gate humano — Overview

Humano revisa `docs/overview.md`. Checklist:

- [ ] Todas as seções **aplicáveis** do `templates/overview.md` estão materialmente preenchidas (seções inaplicáveis foram removidas, não escritas como "N/A").
- [ ] Premissas (`ASSUM-N`) listadas são aceitáveis ou foram esclarecidas.
- [ ] Não há contradição interna.
- [ ] Linguagem ubíqua está correta (termos do negócio reconhecíveis).
- [ ] Stack pinada com versões, não com "recente" ou "compatível".
- [ ] Frontmatter completo conforme `CONVENTIONS.md`; `status: done`.

Aprovado → commit `docs(overview): approved` → Fase 2.

---

## 6. Fase 2 — Roadmap

### 6.1 Objetivo

Quebrar o Overview em **Steps** (entregas de negócio). Cada Step contém
uma sequência de **Stages** atômicas. Cada Stage será o ciclo
concept → technical → execução da Fase 3A em diante.

### 6.2 Onde roda

Chat IDE no próprio repositório `whaka-dev-project-template`, mesma
sessão da Fase 1 ou nova (com `overview.md` da Fase 1 já presente no
filesystem). O `roadmap.md` gerado é persistido no mesmo diretório do
`overview.md` (ver [§14](#14-itens-em-aberto)).

### 6.3 Prompt da Fase 2

A IA quebra o Overview em Steps (entregas de negócio) e Stages (unidades
atômicas), validando contra os 5 critérios de Stage Atômica (§4.2) +
limite de 3–8 Tasks por Stage. Inclui diagrama Mermaid de dependências
e premissas `ROADMAP-N` numeradas.

**Prompt completo para copy-paste:** [`RUNBOOK-INIT-PROJECT.md`](./RUNBOOK-INIT-PROJECT.md)
§Passo 4.

### 6.4 Gate humano — Roadmap

Humano revisa `docs/roadmap.md`. Checklist:

- [ ] Cada Step entrega resultado de negócio reconhecível por
      stakeholder não-técnico.
- [ ] Cada Stage cumpre os 5 critérios de Stage Atômica (§4.2).
- [ ] Ordem respeita dependências: port antes de adapter, schema antes
      de migration, use case antes de endpoint.
- [ ] Descrição estruturada de cada Stage tem todos os campos
      preenchidos.
- [ ] Stages na granularidade certa (não há "criar conexão E criar
      schema E criar endpoint" numa Stage só).
- [ ] Lacunas conhecidas e premissas (`ROADMAP-N`) são aceitáveis.
- [ ] Pelo menos a Stage `1.1-bootstrap` está com escopo claro para
      abrir Fase 3A.
- [ ] Frontmatter completo; `last_reviewed_at` setado.

Aprovado → commit `docs(roadmap): approved` → começar Stage 1.1.

---

## 7. Fase 3A — Concept (por Stage)

### 7.1 Objetivo

Produzir documento conceitual da Stage atual, definindo escopo,
objetivo, contratos, invariantes, decisões e critérios de aceitação.
**Sem código nesta fase.**

### 7.2 Onde roda

Chat IDE. Concept depende de filesystem (tree, LAYOUT, código
existente, template, ADRs anteriores — globais e do mesmo BC — e a §7
post-execution das `technical.md` de Stages relacionadas).

### 7.3 Prompt da Fase 3A

A IA produz o Concept da Stage cobrindo escopo, contratos, invariantes,
casos de erro, decisões técnicas (alternativas reais → ADR) e riscos.
Carrega contexto cirúrgico (concept.md atual, ADRs relevantes — globais
e do mesmo BC —, §7 post-execution das `technical.md` de Stages
relacionadas para findings/decisões pendentes, código existente sob
demanda). Stage trivial: declara explicitamente e gera direto.
Contradição com Overview/Roadmap/código → para e aponta.

**Prompt completo para copy-paste:** [`RUNBOOK-STAGE-LIFECYCLE.md`](./boilerplate/layout-files/docs/RUNBOOK-STAGE-LIFECYCLE.md)
§Passo 4. No projeto destino, o caminho passa a ser
`docs/RUNBOOK-STAGE-LIFECYCLE.md` (boilerplate copia o arquivo para
`docs/`).

### 7.4 Gate humano — Concept

Checklist:

- [ ] Escopo e Fora de Escopo correspondem à Stage do Roadmap.
- [ ] Toda decisão em §7 (Decisões técnicas) tem fonte rastreável.
- [ ] Contratos declarados batem com `contratos_introduzidos` do Roadmap.
- [ ] Critérios de aceitação são objetivos e testáveis.
- [ ] Checklist de validação interna (§12 do template) 100% "sim".
- [ ] ADRs identificados como necessários foram escritos (`accepted`).
- [ ] Stage cabe em ~3–8 Tasks (ver `CONVENTIONS.md` §6); se cresceu
      além disso, dividir antes de seguir.
- [ ] Frontmatter completo; `status: done`.

Aprovado → commit `stage N.M: conceptual approved` → Fase 3B.

> **Regressão permitida.** Se a Fase 3B (technical) revelar gap material
> aqui, o concept pode voltar a `draft` via commit
> `chore(concept): revert to draft — revision-from-technical: <motivo>`
> (CONVENTIONS §3.2). Re-aprovação segue o mesmo gate. Início da Fase 4
> exige ambos `done` simultaneamente.

---

## 8. Fase 3B — Technical (por Stage)

### 8.1 Objetivo

Quebrar o Concept aprovado da Stage em sequência de **Tasks**
executáveis por Claude Code/Codex. **1 Task = 1 commit.** Checks
objetivos rodam entre Tasks.

### 8.2 Onde roda

Chat IDE no projeto destino.

### 8.3 Prompt da Fase 3B

A IA traduz o Concept aprovado em sequência ordenada de Tasks
(1 Task = 1 commit), validando contra os 5 critérios de Task Atômica
(§4.3). A ordem das Tasks segue skills de ordenação aplicáveis (ex.:
`task-ordering-hex` para Stage de fatia vertical) — ver §13. ADRs
anteriores relevantes carregados; concepts anteriores caso a caso.
Lacuna no Concept → para e sinaliza loop reverso para 3A.

**Prompt completo para copy-paste:** [`RUNBOOK-STAGE-LIFECYCLE.md`](./boilerplate/layout-files/docs/RUNBOOK-STAGE-LIFECYCLE.md)
§Passo 6.

### 8.4 Gate humano — Technical

Checklist:

- [ ] Cada Task cumpre os 5 critérios de Task Atômica (§4.3).
- [ ] Caminhos batem com `LAYOUT.md`.
- [ ] Checks objetivos cobrem cada Task.
- [ ] Ordem respeita dependências.
- [ ] Riscos identificados são razoáveis.
- [ ] Gate de saída da Stage definido (testes + critério funcional).
- [ ] Número de Tasks saudável (3–8; ≥ 10 = Stage grande demais).
- [ ] `concept.status == done` neste momento (gate da Fase 3B exige).
- [ ] §7 "Execução" presente com marcadores `BEGIN/END: post-execution`
      vazia ou contendo apenas placeholder.
- [ ] Frontmatter completo; `status: done`.

Aprovado → commit `stage N.M: technical approved` → Fase 4.

> **Regressão permitida.** Se na Fase 4, antes da execução começar,
> for percebido gap no plano, o technical pode voltar a `draft` via
> `chore(technical): revert to draft — revision-from-execution: <motivo>`
> (CONVENTIONS §3.2). Já durante a execução, ajustes pequenos vão para
> §7 do technical (sem mudar status); ajustes grandes seguem §12.2.

---

## 9. Fase 4 — Execução (por Task)

### 9.1 Objetivo

Executar cada Task do `technical.md` em ordem. **1 Task = 1 commit.**
Humano revisa o diff antes de cada commit. Quando todas as Tasks passam
e o gate de saída da Stage é cumprido, a Stage é commitada com
`stage N.M: complete` e mergeada em `develop` (promoção para `main`
acontece apenas na release — ver GIT-WORKFLOW).

### 9.2 Onde roda

Chat IDE no projeto destino.

### 9.3 Prompt da Fase 4 (por Task)

A IA implementa exatamente a Task descrita, com escopo estrito aos
arquivos listados. Heurística de reversibilidade: reversível barato
= segue + documenta; irreversível = pergunta. Lacuna material em
qualquer doc → para e reporta (loop reverso para 3A com ADR). Apresenta
diff antes do commit; humano comita.

**Pré-condição rígida (Passo 8 do runbook):** `concept.status == done`
**e** `technical.status == done` simultaneamente. Início bloqueado se
qualquer um estiver em `draft`.

**Pergunta antes da nota.** Ao encontrar durante a execução algo não
previsto nos artefatos, **pausar**, levantar pergunta com 2–4 opções
e uma recomendada (via `AskUserQuestion`), e só então registrar a
entrada em §7 do `technical.md` (categorias `[decision]`/`[finding]`/
`[deviation]` — ver CONVENTIONS §3.4 e template §7).

**Prompt completo para copy-paste:** [`RUNBOOK-STAGE-LIFECYCLE.md`](./boilerplate/layout-files/docs/RUNBOOK-STAGE-LIFECYCLE.md)
§Passo 8.

### 9.4 Gate humano por Task

Humano revisa o diff antes do commit. Checklist:

- [ ] Apenas arquivos listados na Task foram tocados.
- [ ] Checks listados na Task passam.
- [ ] Código respeita `LAYOUT.md` (camada certa, sem imports proibidos).
- [ ] Decisões justificadas batem com Concept.
- [ ] Mensagem de commit no formato `CONVENTIONS.md` §4(a).

**IA pré-revisora (opcional).** Uma sessão/modelo independente do
gerador pode pré-revisar o diff e produzir um relatório (itens do
checklist + achados). O humano confere o relatório, não o diff inteiro.
**Humano permanece decisor final** — IA pré-revisora não substitui o
gate, apenas reduz carga de leitura.

**Modo de gate por Stage.** O nível de revisão é declarado na Stage no
roadmap (campo `gate_mode` em "Descrição para IA"):
- `strict` (default) — humano revisa diff **antes de cada commit**.
  Recomendado para Stages críticas: `1.1-bootstrap`, contratos novos,
  migrations, decisões irreversíveis.
- `batch` — agente commita Tasks em sequência; humano revisa o
  conjunto ao final da Stage (antes do gate de saída §9.5). Permitido
  apenas para Stages de implementação rotineira sobre fundação já
  validada.
Stage sem `gate_mode` declarado → `strict`. Mudar para `batch` exige
justificativa no `concept.md` ou ADR.

Aprovado → commit `<type>(<scope>): <desc> [N.M/task-NN]` → próxima
Task. **Rejeitado antes do commit:** agent reescreve. **Rejeitado depois
do commit:** vira novo commit (`fix(...)` ou `refactor(...)`), nunca
amend após gate.

### 9.5 Gate de saída da Stage

Após a última Task, executar o checklist de fechamento do
`technical.md` §3:

- [ ] `make check` verde localmente.
- [ ] Verificações funcionais do `technical.md` §3 cumpridas.
- [ ] `python scripts/check_technical_postexec.py` verde — confirma que,
      desde o commit `stage N.M: technical approved`, o diff do
      `technical.md` ficou restrito à seção §7 (entre os marcadores
      `BEGIN/END: post-execution`).
- [ ] §7 do `technical.md` reflete o que realmente aconteceu na execução
      (entradas `[decision]`/`[finding]`/`[deviation]` com header `data — [tag] escopo — autor`).
- [ ] Findings escalados (`[finding]`) têm Stage candidata identificada.
- [ ] Commit final `stage N.M: complete` no branch.
- [ ] PR contra `develop` aberto e mergeado, seguindo os
      [gates de PR de GIT-WORKFLOW](./boilerplate/layout-files/docs/GIT-WORKFLOW.md#gates-de-pr-fonte-única)
      (CI verde, coverage, aprovações, merge commit).
- [ ] `roadmap.md` atualizado: Stage marcada `done`, `updated_at` e
      `last_reviewed_at` no **mesmo merge da Stage** (preferível) ou em
      PR de docs imediatamente subsequente. Responsável: dev que fez o
      merge.
- [ ] ADRs novos (se houve) em `status: accepted`.
- [ ] Runbooks operacionais criados se aplicável.
- [ ] `concept.md` não precisa de retoque retrospectivo (se precisa,
      abrir TODO ou nova Stage de correção).

→ Próxima Stage.

---

## 10. Fluxo Git

Substrato de versionamento e gates. Sem máquina de estado paralela.

**Fonte única para PR, CI, coverage, branch protection, deploy:**
[`GIT-WORKFLOW.md`](./boilerplate/layout-files/docs/GIT-WORKFLOW.md). Esta
seção descreve apenas o que é **específico do pipeline da Stage**:
modelo issue+branch, sequência de commits dentro do branch, classes de
commit. Regras de **nomenclatura, frontmatter, status e versionamento
de docs** vivem em [`CONVENTIONS.md`](./CONVENTIONS.md) §4 e §5.

### 10.1 Modelo issue + branch

**Uma Stage = uma issue + um branch.**

- Para iniciar a Stage: criar issue no GitHub com título referenciando
  `Stage N.M` e a descrição. GitHub atribui o número da issue.
- Branch criado a partir de `develop` (base padrão; ver GIT-WORKFLOW).
- Formato do branch: `feat/<num-issue>-<N-M>-<slug>` — `N.M` em kebab
  (Stage 2.3 → `2-3`). Tipo segue GIT-WORKFLOW (`feat` para Stage nova,
  `fix` para correção via Stage, etc.; em geral `feat`).

Exemplo:
- Issue #42, título: `feat: stage 2.3 — adicionar S3 source adapter`
- Branch: `feat/42-2-3-s3-source-adapter`

Do `conceptual draft` ao `complete`, tudo no mesmo branch. PR contra
`develop` quando a Stage termina (gate de saída cumprido §9.5).

```
develop
 │
 ├── branch: feat/42-1-1-bootstrap            (Issue #42)
 │     ├── stage 1.1: conceptual draft
 │     ├── stage 1.1: conceptual approved      ← gate humano (3A)
 │     ├── stage 1.1: technical draft
 │     ├── stage 1.1: technical approved       ← gate humano (3B)
 │     ├── feat(bootstrap): ... [1.1/task-01]  ← gate humano por Task
 │     ├── feat(bootstrap): ... [1.1/task-02]
 │     ├── ...
 │     └── stage 1.1: complete
 │── PR → develop                              (gates GIT-WORKFLOW)
 │
 ├── branch: feat/57-1-2-domain-model          (Issue #57)
 │     └── ...
 │── PR → develop
 │
 └── branch: docs/<change-desc>    (mudanças só de docs, fora de Stage)
```

Promoção de `develop` para `main` ocorre na release (ver GIT-WORKFLOW).

### 10.2 Commits no branch da Stage

Formato detalhado de cada classe de commit (Conventional Commits +
mensagens reservadas + exceções de bootstrap): **fonte única em
[`CONVENTIONS.md`](./CONVENTIONS.md) §4**.

O que é específico do pipeline (e não de Git) — **sequência dos commits
no branch da Stage:**

1. `stage N.M: conceptual draft` (gerado no Passo 3 do runbook)
2. `stage N.M: conceptual approved` (gate humano Fase 3A)
3. `stage N.M: technical draft` (após gerar `technical.md`)
4. `stage N.M: technical approved` (gate humano Fase 3B)
5. `feat(scope): desc [N.M/task-NN]` × N — uma por Task da Fase 4
6. `stage N.M: complete` (gate de saída §9.5)

**Intercalações possíveis** (entre 2↔4 e 4↔5; CONVENTIONS §3.2):
- `chore(concept): revert to draft — revision-from-technical: <motivo>` +
  subsequente `stage N.M: conceptual approved` (concept regredido e
  re-aprovado).
- `chore(technical): revert to draft — revision-from-execution: <motivo>` +
  subsequente `stage N.M: technical approved` (technical regredido antes
  de iniciar a Fase 4).

Cada commit acima carrega `Refs #<num-issue>` no rodapé. Detalhes de
formato e nomenclatura — `CONVENTIONS.md` §4.

### 10.3 Regras

- **Sem rebase nem squash** no merge — historicidade auditável. Merge
  commit obrigatório (premissa GIT-WORKFLOW).
- Cada gate humano é um commit (reservado) ou um merge. A mensagem é o
  registro da aprovação.
- Branch de Stage só abre PR para `develop` após `stage N.M: complete`
  e gate de saída cumprido (§9.5). PR segue gates do GIT-WORKFLOW (CI
  verde, coverage ≥ 90%, +1 aprovação).
- ADRs em `proposed` podem ser commitados na Stage; viram `accepted` no
  merge para `develop`.
- Stage descartada antes do merge: PR fechado (`gh pr close`), issue
  fechada com label `wontfix` ou `superseded`, e
  `docs/stages/N.M-<slug>/` movido para `docs/stages/_archived/` com
  nota explicando o motivo.

---

## 11. Condução de sessões

Todas as fases rodam em Chat IDE (ver §1.2). Esta seção cobre quando
abrir nova sessão e padrões de condução.

### 11.1 Quando abrir nova sessão

| Situação | Nova sessão? | Motivo |
|---|---|---|
| Início do projeto (Fase 1) | Sim, nova | Sessão limpa, sem viés. |
| Iniciar Fase 2 após Fase 1 | Pode continuar | Contexto vivo é útil. |
| Iniciar nova Stage (Fase 3A) | Sim, nova | Cada Stage é contexto fechado. |
| Continuar Fase 3A/3B da mesma Stage no mesmo dia | Não, continua | Contexto vivo é útil. |
| Voltar a uma Stage após dias | Sim, nova | Memória expira; recarregar artefatos. |
| Fase 4 (execução) | 1 sessão por Stage (não por Task) | Overhead de re-iniciar contexto a cada Task é alto. |
| Retorno de fase (loop reverso) | Sim, nova, anexando ambos artefatos | Forçar revisão limpa. |

**Regra de bolso:** sessão com >40 turnos **ou** mudança de fase →
abrir nova. Permitir compactação dentro da sessão antes de abrir nova
quando faz sentido.

### 11.2 Padrões de condução

Já embutidos nos prompts das Fases 1, 2 e 3A:

- **Blocos temáticos** (4–8 perguntas por bloco).
- **Sinaliza saturação** antes de propor o corte.
- **Não inventa contexto** — usa `TODO`, `ASSUM-N`, `ROADMAP-N`.
- **Aponta contradições** assim que aparecem.

---

## 12. Tratamento de exceções

### 12.1 Contradição detectada pela IA

Em qualquer fase, se a IA detecta contradição entre:

- Resposta do humano e Overview/Roadmap/código.
- Concept e `LAYOUT.md`.
- Technical e Concept.

→ IA **para imediatamente**, aponta a contradição com referência
explícita à fonte conflitante, pede reconciliação. Não tenta resolver
autonomamente.

Se a decisão muda artefato a montante, seguir §12.2.

### 12.2 Loop reverso (erro descoberto em fase anterior)

| Situação | Ação |
|---|---|
| Fase 3B revela lacuna no Concept | Regressão leve: commit `chore(concept): revert to draft — revision-from-technical: <motivo>` (CONVENTIONS §3.2). Atualizar Concept. Re-aprovar com `stage N.M: conceptual approved`. Voltar a 3B. **Nova sessão não obrigatória** — basta recarregar o Concept revisto no contexto. |
| Fase 4 (ainda não começou) revela problema no Technical | Regressão leve: commit `chore(technical): revert to draft — revision-from-execution: <motivo>` (CONVENTIONS §3.2). Ajustar. Re-aprovar. Só então Passo 8. |
| Fase 4 (já iniciada) — algo não previsto e dá pra decidir agora | Pausar, perguntar com opções (AskUserQuestion), aplicar decisão, registrar em §7 do `technical.md` com `[decision]` (CONVENTIONS §3.4). Não muda status. |
| Fase 4 (já iniciada) — gap a tratar em outra Stage | Registrar em §7 como `[finding]` com Stage candidata. Seguir a Task atual se desbloqueado. |
| Fase 4 (já iniciada) — desvio pequeno aplicado | Registrar em §7 como `[deviation]`. Continua. |
| Fase 4 revela problema **grande** no Technical (não comporta §7) | Pausar execução. Nova sessão. Refazer Technical da parte afetada (regressão se ainda válido; arquivamento se Stage foi recortada — CONVENTIONS §5). |
| Fase 4 revela problema no Concept | Stop. Não ajustar implementando — voltar à Fase 3A explicitamente (nova sessão). |
| Stage em execução revela problema no Roadmap | Pausar Stage, nova sessão com Overview + Roadmap, replanejar Stages afetadas. |
| Fase 4 (ou qualquer fase posterior) revela problema no Overview | Stop. Nova sessão Fase 1 com `overview.md` + nota do problema. Atualizar Overview. **Revalidar o Roadmap em seguida** — pode invalidar Stages já planejadas. Só depois retomar fase posterior. |

**Regras duras:**
- Retorno de fase **com regressão leve** (`done → draft`) **não** exige
  nova sessão — basta recarregar o artefato revisto no contexto.
- Retorno de fase **pesado** (refazer parte significativa do artefato a
  montante; envolver Roadmap ou Overview) **sempre** exige nova sessão.
- Em qualquer caso, **fase a montante primeiro** quando houver loops sobrepostos.

**Loops reversos sobrepostos.** Se a fase atual revela problema em
múltiplas fases a montante (ex.: Concept e Roadmap ambos têm lacuna), a
ordem é **fase a montante primeiro**: corrigir Roadmap → revalidar
Concept (regressão `done → draft` se necessário) → retomar fase atual.
Nunca pular um nível.

**Princípio:** não silenciar dívida. Se algo está errado a montante,
volta-se a montante. Fases a jusante só seguem após reconciliação.

### 12.3 Stage trivial

Quando a IA, ao iniciar Fase 3A, identifica que não há bifurcação
material:

1. Declara explicitamente: *"não identifiquei bifurcações materiais
   nesta Stage"*.
2. Gera o Concept direto.
3. Humano confirma (ou aponta o que faltou perguntar) antes do gate.

Mesmo mecanismo em Fase 3B e 4 quando o trabalho é mecânico.

### 12.4 Task que estoura escopo

Se durante Fase 4 a IA percebe que precisa tocar arquivo fora do escopo:

1. **Para** a implementação.
2. **Pergunta** ao humano com `AskUserQuestion`: 2–4 opções (incluindo
   "ajustar `technical.md`", "aceitar exceção pontual", "abortar Task"),
   uma recomendada + razão.
3. Aplica a decisão.
4. Registra a decisão em §7 do `technical.md` como `[decision]` (ou,
   se virou ajuste do plano em §1–§6, faz regressão `technical → draft`
   conforme §3.2).

**Princípio:** scope creep é resolvido fora do código, não dentro. E
nunca é resolvido silenciosamente — ou pergunta + §7, ou regressão.

### 12.5 Política de retry em Fase 4

> [A confirmar com prática em projeto real]

Sugestão inicial: **3 tentativas** com erros progressivamente reportados.
Na 4ª, pausa obrigatória — humano decide se ajusta `technical.md`, abre
ADR para revisão de design, ou aborta a Task.

---

## 13. Skills canônicas

Diretório `.claude/skills/<nome-kebab>/SKILL.md`. Cada skill é uma
**pasta** com arquivo `SKILL.md` dentro (formato oficial Claude Code).

**Protocolo de carregamento (duas vias complementares):**

1. **Discovery automática (oficial Claude Code):** o agente lê `name` +
   `description` do frontmatter de cada skill e decide carregar quando
   o contexto casa. Por isso a `description` deve cobrir tanto o que a
   skill faz quanto **quando carregá-la**.
2. **Hint explícito do pipeline:** o `name` da skill aparece em
   `skills_hint` da Stage no roadmap, forçando carregamento
   independente da descoberta automática.

**Lifecycle.** Skills criadas durante a execução de uma Stage nascem com
`metadata.status: draft`. Promoção a `accepted` requer que a skill seja
referenciada em `skills_hint` de ≥ 2 Stages independentes. Skills com
decisões imutáveis do projeto (ex.: regras de import do hexagonal)
podem nascer `accepted`.

**Escopo.** Regras locais a um bounded context são modeladas como skill
com `metadata.applies_when.bounded_context == X`, não como nova
categoria de doc.

| Skill | Quando carregar | Conteúdo principal | Nasce |
|---|---|---|---|
| `hex-arch-python` | Toda Stage (global) | Direção de imports, separação de camadas, Protocols como ports | accepted |
| `fastapi-thin-adapter` | Stage cuja `camada_alvo` é `adapters/in/http/` | Router fino, schemas Pydantic só no adapter, mapeamento de exceções | draft |
| `repository-pattern` | Stage cuja `camada_alvo` é `adapters/out/<persistence>/` | Implementação de port out, mappers, transações | draft |
| `pytest-with-fakes` | Stage cuja `camada_alvo` é `domain` ou `application` | Fake in-memory de port out, contract tests | draft |
| `import-linter-rules` | Stage `1.1-bootstrap` e quando regras mudam | Como ler/atualizar contratos | accepted |
| `ddd-tactical-patterns` | Stage cuja `camada_alvo` é `domain` | Entity vs Value Object, agregados, invariantes | draft |
| `composition-root` | Stage que adiciona wiring | Onde injetar, evitar singletons | draft |
| `task-ordering-hex` | Fase 3B em Stage de fatia vertical (camada_alvo cobre ≥ 2 camadas em 1 BC) | Ordem default das Tasks: TDD inside-out (domain → application com fakes → adapters → bootstrap); exceções para fundação, adapter-only, bug fix, migração | draft |

### Formato de cada skill (formato β)

`.claude/skills/<nome>/SKILL.md`:

```markdown
---
name: <nome-kebab>                # oficial (default = nome do diretório)
description: <1–2 frases que cobrem propósito + quando carregar>  # oficial; usado para discovery
metadata:                         # campo oficial dedicado a dados arbitrários
  status: draft | accepted | archived
  applies_when:                   # matching estruturado do pipeline
    camada_alvo: [<valor>, ...]   # lista YAML — ver schema abaixo
    stage_kind: <vertical-slice | mono-layer | any>   # opcional
    bounded_context: <nome-bc>    # opcional
    fase: [<1 | 2 | 3A | 3B | 4>] # opcional, lista
---

# <Nome legível>

<Texto livre — orientações operacionais, exemplos, contra-exemplos.
Sem schema rígido. Conteúdo que ajuda a IA a aplicar a skill ao
contexto atual.>
```

**Schema de `applies_when` (canônico):**

| Campo | Tipo | Valores |
|---|---|---|
| `camada_alvo` | lista YAML | `domain`, `application`, `adapters/in/http`, `adapters/out`, `adapters/out/<persistence>`, `shared/application`, `shared/infrastructure`, `bootstrap`, `multi` (cobre ≥ 2 camadas), `any` (wildcard) |
| `stage_kind` | string | `vertical-slice` (≥ 2 camadas em 1 BC), `mono-layer` (1 camada), `any` |
| `bounded_context` | string | nome do BC (`payments`, `inventory`, …) ou `any` |
| `fase` | lista YAML | `1`, `2`, `3A`, `3B`, `4` ou `any` |

- **Sentinela `any`:** declara explicitamente que a skill carrega independente
  do valor desse eixo. Use lista com `any` único (`[any]`) ou string `any` quando
  o campo aceita string.
- **Listas:** sempre que houver ≥ 1 valor possível, use lista YAML. Para 1 valor,
  lista de tamanho 1 (`[domain]`) ou string única — ambos válidos, mas lista é
  preferida pelo matching estruturado.
- **Ausência de campo:** equivale a "não restringe esse eixo" (semântica idêntica
  a `[any]`). Prefira `[any]` quando a intenção é explícita.

**Exceção ao frontmatter padrão.** Skills são **exceção** à regra de
`created_at`/`updated_at` de `CONVENTIONS.md` §2 — não carregam essas datas no
frontmatter. Histórico fica no git; lifecycle é expresso por `metadata.status`
(`draft → accepted → archived`).

Campos `name` e `description` são consumidos pelo Claude Code para
discovery automática. `metadata` é o slot oficialmente dedicado a
dados arbitrários — o pipeline usa para lifecycle (`status`) e matching
estruturado (`applies_when`). Sem warnings de linter.

---

## 14. Itens em aberto

Pontos a confirmar com prática em projeto real:

1. **Política de retry em Fase 4** (§12.5). Sugestão de 3 tentativas é
   inicial; validar.
2. **Conteúdo definitivo das skills canônicas.** §13 lista nomes e
   conteúdo principal; o material de cada skill ainda será escrito.
3. **Formato de `scripts/check_layout.py`.** `LAYOUT.md` é prosa
   estruturada. Validação por script pode exigir arquivo paralelo
   (`layout.lock.yaml`) ou parser do MD.
4. **Multi-projeto / monorepo.** Pipeline assume um repositório por
   projeto.
5. **Onboarding tardio.** Hipótese: leitura sequencial de `overview.md`
   + `roadmap.md` + concepts/technicals aprovados é suficiente.
6. ~~Setup do projeto destino a partir do template.~~ **Resolvido.**
   Procedimento detalhado em [`RUNBOOK-INIT-PROJECT.md`](./RUNBOOK-INIT-PROJECT.md)
   (projeto novo) e [`RUNBOOK-ADOPT-EXISTING.md`](./RUNBOOK-ADOPT-EXISTING.md)
   (adoção em projeto existente). Decisões fixadas: caminho
   `projects/<projeto-slug>/`; cópia via `scripts/init-project.py`;
   múltiplos projetos no template suportados (1 diretório por projeto);
   diretório `projects/<slug>/` permanece no template como histórico
   após init do destino.

---

## 15. Checklist operacional

Esta seção é apenas índice. **Procedimentos passo a passo com comandos
e prompts copy-paste vivem nos runbooks.**

### Para iniciar projeto novo

→ Seguir [`RUNBOOK-INIT-PROJECT.md`](./RUNBOOK-INIT-PROJECT.md).

Cobre: criar diretório `projects/<slug>/` no template; Fase 1
(Overview) com gate; Fase 2 (Roadmap) com gate; inicializar
repositório do projeto destino com cópia de boilerplate + templates +
artefatos; setup GitHub (branch protection, environments, CI);
próxima ação = primeira Stage no projeto destino.

### Para adotar o template em projeto existente

→ Seguir [`RUNBOOK-ADOPT-EXISTING.md`](./RUNBOOK-ADOPT-EXISTING.md).

Cobre: congelar estado pré-adoção em release versionada; gerar
overview/roadmap considerando o existente como contexto (não como
decisão imutável); migração para o padrão tratada como Step(s) normais
do roadmap; cópia seletiva de boilerplate.

### Para cada Stage do roadmap

→ Seguir [`RUNBOOK-STAGE-LIFECYCLE.md`](./boilerplate/layout-files/docs/RUNBOOK-STAGE-LIFECYCLE.md).

Cobre: criar issue + branch `feat/<issue>-<N-M>-<slug>`; Fase 3A
(Concept) com gate; Fase 3B (Technical) com gate; Fase 4 (Execução
por Task) com gate por Task ou `batch` conforme `gate_mode`; commit
`stage N.M: complete`; PR contra `develop` com gates GIT-WORKFLOW.

### Substrato do template (uma vez por projeto destino)

Cópias do template para o projeto destino — detalhado no Passo 6 do
RUNBOOK-INIT-PROJECT (ou Passo 8 do RUNBOOK-ADOPT-EXISTING):

- `CLAUDE.md`, `README.md`, `Makefile`, `pyproject.toml`,
  `.pre-commit-config.yaml`, `scripts/`, `src/`, `tests/`, `migrations/`,
  `.github/`,
  `docs/{LAYOUT.md, GIT-WORKFLOW.md, RUNBOOK-STAGE-LIFECYCLE.md, PIPELINE.md, CONVENTIONS.md, adr/}` —
  de `boilerplate/layout-files/`.
- `.claude/settings.local.json` + skills selecionadas (em `.claude/skills/`) —
  vindos da **raiz do template** (`.claude/`). O boilerplate NÃO contém
  `.claude/`; `init-project.py` (Passo 6 do RUNBOOK-INIT-PROJECT) copia o
  `settings.local.json` da raiz e popula `skills/` conforme os bundles
  selecionados em `scripts/skill-bundles.toml`. Schema das skills é
  validado no CI por `.github/workflows/validate-claude-skills.yml`.
- `templates/` — para futuras Stages.
- `docs/overview.md` e `docs/roadmap.md` — gerados nas Fases 1 e 2.

---

## Glossário

- **Step:** entrega de negócio ou recurso. Agrupa Stages no Roadmap. Sem
  `concept.md`/`technical.md` próprio. **Sem restrição arquitetural.**
- **Stage:** unidade de ciclo concept→technical→execução. Atômica
  (foco coeso: camada-alvo principal **ou** fatia vertical end-to-end em
  1 BC; 1 DoD; 1 bounded context; complexidade ≤ M). Equivale a 1 branch.
- **Task:** subdivisão da execução da Stage = 1 commit.
- **Concept:** documento conceitual da Stage
  (`docs/stages/N.M-<slug>/concept.md`).
- **Technical:** plano executável da Stage
  (`docs/stages/N.M-<slug>/technical.md`).
- **Gate humano:** ponto de revisão obrigatório entre fases.
  Materializado como commit reservado ou merge.
- **ADR (Architecture Decision Record):** registro de decisão com
  alternativas e consequências. Escrito em inglês
  ([`templates/adr.md`](./templates/adr.md)).
- **Runbook:** procedimento operacional passo-a-passo, em inglês
  ([`templates/runbook.md`](./templates/runbook.md)).
- **Bifurcação material:** ponto onde a IA precisaria escolher entre
  alternativas materialmente diferentes sem critério no contexto. Define
  o que é pergunta válida.
- **Saturação:** estado em que perguntas novas começam a render respostas
  redundantes ou "tanto faz". Sinal para fechar a fase.
- **Loop reverso:** mecanismo de voltar a uma fase anterior quando uma
  fase posterior revela problema. Sempre em nova sessão.
- **`ASSUM-N`, `ROADMAP-N`:** premissas adotadas em Overview e Roadmap,
  numeradas, para casos em que uma decisão foi tomada sem resposta
  explícita do usuário.

