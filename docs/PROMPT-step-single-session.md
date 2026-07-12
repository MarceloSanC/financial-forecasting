---
title: Prompt — Orquestração de Step em Sessão Mestra (subagentes de contexto zerado + gate de domínio + decisão assistida rica)
description: Sessão mestra human-in-the-loop que conduz um Step inteiro (grupo de Stages) do roadmap sem escrever artefato próprio — despacha subagentes de contexto zerado para cada fase do PROMPT-stage-single-session (Concept, Technical, Execução e os Checkpoints), resolve cada fork de decisão (pesquisa abordagens → decide sozinho via docs+skills ou pergunta ao humano, sempre registrando ADR), roda a auditoria de Stage em subagente separado com tratamento de findings, e — ao OK do humano — faz o merge, limpa a branch/worktree e inicia a próxima Stage.
when-use: Conduzir um Step do roadmap do começo ao fim, quando se quer (a) travar as regras de negócio em fonte oficial antes de codar, (b) isolar cada fase e cada revisão em um subagente de contexto zerado para reduzir viés, (c) manter o humano decidindo só o que os docs não resolvem, com explicação didática, e (d) que o próprio orquestrador conduza cada Stage até o merge, encadeando as Stages do Step.
keywords: [prompt, step, single-session, master, orchestration, subagents, fresh-context, domain-gate, human-in-the-loop, decisao-assistida, adr, stage-audit, bias-mitigation]
status: accepted
created_at: 2026-07-05
updated_at: 2026-07-10
---

# Prompt — Orquestração de Step em Sessão Mestra

Este é o prompt de **nível Step** (entrega de negócio; agrupa Stages). Ele **orquestra** o
prompt de nível Stage já existente — não o reimplementa. Uma sessão mestra conduz o Step inteiro:

- **não escreve artefato próprio** — despacha **subagentes de contexto zerado** para executar
  cada **fase** do [`./PROMPT-stage-single-session.md`](./PROMPT-stage-single-session.md)
  (Concept, Technical, Execução) **e cada Checkpoint** (A/B/C) e a auditoria de testes;
- **resolve cada fork de decisão** que os subagentes encontrarem — pesquisando abordagens e
  **decidindo sozinha** quando os docs do projeto respondem, ou **perguntando ao humano** quando
  não respondem (§2);
- **audita cada Stage** em subagente separado, trata os findings, re-audita e fecha a auditoria
  no PR (§3);
- ao **OK do humano** no relatório, **faz o merge**, limpa branch/worktree e **inicia a próxima
  Stage** (§3.5).

Sucede a antiga variante INTERATIVA (que operava em nível Stage): herda o DNA *human-in-the-loop
com disciplina de decisão rica* e o eleva ao Step, adicionando o **gate de domínio** e a
**orquestração por subagentes de contexto zerado**.

> **Posição entre os prompts de execução:**
> - **Nível Stage** ([`./PROMPT-stage-single-session.md`](./PROMPT-stage-single-session.md)) — executa **uma** Stage (Fase 3A+3B+4) até o PR, numa sessão só.
> - **Nível Step — este doc** — a **sessão mestra** que conduz um Step inteiro, despacha os subagentes de cada fase, e conduz cada Stage do PR ao merge.

---

## Vocabulário: Step × Stage

Fonte: [`./roadmap.md`](./roadmap.md) (nota de legenda).

- **Step** — **entrega de negócio**, sem restrição arquitetural; **agrupa Stages**
  (ex.: *Step 13 — Agente Contas a Receber completo*, Stages 13.1–13.8).
- **Stage** — **unidade técnica atômica** (concept + technical + execução, 3–12 Tasks).

Esta sessão vive no nível **Step**. Cada Stage por dentro ainda roda o ciclo canônico — só que
cada fase dele roda em um subagente próprio (§ Princípio central).

---

## Princípio central — a mestra conduz; subagentes de contexto zerado executam

A sessão mestra é um **maestro**, não um executor. Ela **não** escreve o concept, nem o technical,
nem o código: ela **despacha** cada fase para um **subagente novo, de contexto zerado**, que recebe
**só os caminhos dos arquivos e das fontes** — nunca o histórico da sessão nem o raciocínio de quem
produziu a fase anterior. Para uma Stage, a sequência de subagentes é:

| Fase (PROMPT-stage-single-session) | Subagente | Papel |
|---|---|---|
| **3A — Concept** | autor de concept | escreve `concept.md` (+ ADRs de fork, §2) |
| **Checkpoint A** | 2 revisores (lentes distintas) | conformidade · domínio/testabilidade |
| **3B — Technical** | autor de technical | escreve `technical.md` (Tasks + rastreabilidade) |
| **Checkpoint B** | revisor | matriz de rastreabilidade (critério → Task) |
| **4 — Execução** | executor | roda as Tasks em ordem (`make check` por commit) |
| **Checkpoint C** | revisor (por bloco de 2–3 Tasks) | diff × concept/technical/LAYOUT/skills |
| **Auditoria de testes** | auditor de testes | loop até todos "sim" + mutação real |

**Por que isso reduz viés.** O revisor **nunca** compartilha o contexto do autor — não "confia" na
conclusão de quem escreveu porque nunca a viu; re-deriva a partir do artefato. É o mesmo princípio
dos Checkpoints A/B/C do canônico, agora aplicado a **todas** as fases, não só às revisões.

**A mestra é a única que fala com o humano.** Subagentes não têm como perguntar ao usuário — então
todo fork que um subagente não resolve sozinho (§2) **sobe** para a mestra, que pausa e pergunta.
A mestra coleta a saída de cada subagente, trata os forks, e só então despacha o próximo.

> Escale o tamanho de cada fan-out ao peso da fase: fase simples sobre fundação validada → 1
> subagente, voto único; fase de peso (modelo de dados novo, métrica que vai ao usuário) → mais
> subagentes + verificação adversarial (revisor instruído a **refutar**, não confirmar).

---

## 1. Gate de domínio — pré-requisito do Step (bloqueante)

Antes da **primeira** Stage do Step, tem de existir um documento de domínio
**`docs/domain/<bc>/<subdomain>.md`** com **`status: accepted`** cobrindo o escopo do Step
([ADR 0.0.0003](./adr/0_0_0003-formalize-domain-and-audits-doc-categories.md)). Esse doc é a
**camada teórica** que dita *como* cada métrica/regra deve ser calculada e **quais as
particularidades por caso de uso** — é o que o `concept.md` de cada Stage consome. O `<bc>` é
nomeado como em `features/<bc>/` (`market_data`, `feature_engineering`, `modeling`,
`analytics_store`).

> **Por que `domain/` e não `audits/`.** Um doc `audits/`
> ([mesmo ADR](./adr/0_0_0003-formalize-domain-and-audits-doc-categories.md)) diagnostica uma
> **implementação já rodando** contra a realidade do dado — pressupõe código que ainda não existe
> no início do Step. A pesquisa de regras de negócio *que dita como calcular* é **teoria de
> domínio** (`domain/`), consumida **antes** de codar. A auditoria (`audits/` / skill
> `stage-audit`) é a **outra** função, que roda **depois** de cada Stage (§3).

**Barra de fontes (não negociável).** Cada regra, fórmula e particularidade precisa de **citação
rastreável a fonte primária**. A ordem de busca é **fixa** — e o passo 1 não é opcional:

1. **As fontes que o projeto já ratificou.** Este repo **já tem** suas âncoras; não as re-descubra
   nem as reescreva de memória. Procure, nesta ordem:
   - **[`overview.md`](./overview.md) §Referências** — os papers-âncora e as bibliotecas do projeto
     (é a lista canônica; toda fonte de peso do domínio deveria estar aqui);
   - **`## References` dos ADRs** relevantes — os globais (`0_0_*`) e os do **BC do Step** (os do
     mesmo Step e os das Stages já `done`), que carregam a citação completa (autor, ano, capítulo);
   - **`concept.md` das Stages já `done`** do mesmo BC — trazem a fonte já aplicada ao caso de uso.
2. **Só se o passo 1 não cobrir a teoria necessária**, procure fonte nova. Ela precisa ser
   (a) **primária e autoritativa** — paper revisado, livro-texto consagrado, documentação oficial do
   método/biblioteca — e (b) **diretamente ligada ao contexto deste projeto** (os objetivos
   ratificados em [`overview.md`](./overview.md)), não literatura adjacente "que também fala do
   tema". Toda fonte nova que entrar no doc de domínio **é registrada em `overview.md` §Referências**
   no mesmo PR — senão o próximo Step re-pesquisa o que este já achou.

**Não** servem de base: blogs, sites genéricos de "dicas", marketing de software, fórum sem fonte
primária — no máximo apontam *para* a fonte primária, que é a que se cita.

**Se o doc não existe ou não cobre o escopo**, a mestra despacha um **subagente/fan-out de
pesquisa** + **verificação cética adversarial** (rejeita fonte não-primária; tenta refutar cada
fórmula contra a citação; default "insuficiente" se a citação não sustenta) + síntese do rascunho de
`domain/<bc>/<subdomain>.md`. O fan-out **começa varrendo o passo 1** (um subagente inventaria o que
o projeto já ratificou) e só então abre busca externa para as lacunas que sobrarem. O subagente
**retorna** o rascunho + os **forks de pesquisa** (pontos com mais de uma convenção legítima na
literatura) para a mestra tratar por §2.

**HALT de sourcing:** se uma fórmula *load-bearing* (que muda o número que o projeto reporta) não
tiver fonte primária que a sustente, **não invente e não use blog** — PARE e escale ao humano (pode
ser decisão de política do projeto, que vira ADR, não achado de pesquisa). Só declare o gate
cumprido com o doc `accepted`.

---

## 2. Decisão em cada fork — pesquisar → docs resolvem? decidir sozinho : perguntar ao humano

Vale para **todo** subagente operacional (autor de concept/technical, executor) e também para o
**tratador de findings** da auditoria (§3.2). Ao esbarrar em um **fork de decisão** (ponto com mais
de uma abordagem viável):

1. **Pesquisar as abordagens possíveis.** Levantar as alternativas reais, e para cada uma as
   **características** e os **trade-offs** (custo real, reversibilidade, efeito no crescimento do
   sistema, risco, quem paga o custo).
2. **Confrontar com os docs orientadores do projeto.** Buscar a resposta em **todos** os docs de
   `docs/` (inclusive subdiretórios — em especial o **`concept.md` e o `technical.md` da própria
   Stage**, se já existirem, o **doc de domínio**, ADRs, `roadmap.md`, `overview.md`) **e nas skills
   em `.claude/skills/`**.
3. **Bifurcação:**
   - **Docs respondem 100%** → o subagente **decide sozinho** pela abordagem que os docs sustentam,
     e **registra a decisão em ADR** (`docs/adr/<N>_<M>_NNNN-<slug>.md`, `status: accepted`) —
     opções, escolha, trade-offs, reversibilidade, e a **âncora** nos docs que a justifica.
   - **Docs não respondem 100%** → o subagente **pergunta ao humano** (ele mesmo, se seu contexto de
     execução permitir falar com o usuário; senão **sobe o fork para a mestra**, que pergunta),
     detalhando a questão no formato rico abaixo. A **decisão do humano também vira ADR**.

> **Ambos os caminhos geram ADR.** Fork com alternativa real descartada é decisão arquitetural —
> registra-se independentemente de quem decidiu (subagente ancorado nos docs, ou humano).

### Anatomia da pergunta ao humano (obrigatória)

1. **Contexto primeiro** — 2–4 frases explicando *qual é o problema*, em linguagem simples. **Sem
   jargão não intuitivo**; termo técnico inevitável ganha definição de uma linha. O humano entende
   a decisão **antes** de ver as opções.
2. **Abordagens (2–4).** Para cada uma:
   - **Características** — o que essa abordagem *é*, em uma frase.
   - **O que muda no comportamento do sistema** — o efeito concreto e observável de escolhê-la.
   - **Exemplo** — um caso pequeno mostrando *como funciona* naquela abordagem.
3. **Trade-offs profundos** — compare as abordagens em eixos (não em uma linha): custo real de
   implementação (não superestime), reversibilidade, efeito no crescimento, risco, quem paga.
4. **(Recomendada)** — marque **uma**: a **mais simples** que já entrega boa parte do desejado,
   **não prejudica o crescimento** e é **fácil de trocar** depois — com a razão de uma linha.

**Onde escrever cada parte.** O `AskUserQuestion` tem opções curtas — então escreva **contexto,
exemplos e trade-offs no texto da mensagem, ANTES** de chamar a ferramenta; as opções carregam só o
resumo crisp + o marcador **(Recomendada)**. (Este próprio doc foi decidido assim.) Prefira
perguntar **cedo**, quando a decisão ainda é barata de mudar.

### O que NÃO é fork (não vira pergunta nem ADR)

- Detalhes seguidos por convenção (LAYOUT, CONVENTIONS, skills aplicáveis).
- Decisões já fechadas em Overview/Roadmap/Domain/Concept/Technical.
- Reversíveis triviais **sem alternativa real** (nome de variável local, ordem de imports) — decide
  e segue, com justificativa de 1–2 frases no diff (ou `[decision]` na §7 do technical).

Regra de ouro: **pergunta** resolve escolha de design não coberta pelos docs; **HALT** resolve
contradição/irreversível. Nunca use pergunta cosmética para empurrar ao humano algo que a convenção
já resolve, nem silencie sob "reversível trivial" algo que muda contrato/fronteira/critério de
aceite.

### HALT-and-park (contradição / irreversível)

Hierarquia de fontes (alta→baixa): **Overview > Roadmap > Domain > Concept > Technical > Código**.
Ao encontrar contradição com fonte superior, contrato externo irreversível e ambíguo, fórmula sem
fonte oficial (§1), ou gate objetivo que não fecha após tentativa honesta de correção: **PARE**,
deixe a working tree estável, aponte com referência explícita à fonte conflitante e escale.
Não force progresso; não use ADR para enterrar contradição que deveria parar.

---

## 3. Fechamento da Stage — auditoria → tratamento → re-auditoria → relatório → merge

Ao fim da execução de uma Stage (Tasks commitadas, gates de saída verdes, **PR aberto** pelo
subagente executor conforme o canônico), a mestra conduz o ciclo de fechamento.

### 3.1 Auditoria em subagente (read-only)

A mestra despacha um **subagente auditor** de contexto zerado que roda a skill
[`stage-audit`](../.claude/skills/stage-audit/SKILL.md) em modo **julgamento read-only** (Fases
A–D-bis) e **retorna o template de resposta** — as **6 seções + status global + conclusão** da Fase
E da skill:

1. Overview e conceitos · 2. Tasks → arquivos → o que entrega · 3. Gates de saída (invariante↔teste)
· 4. Decisões que impactam arquitetura · 5. **Findings/melhorias classificados por escopo** ·
6. Aprendizados → skills.

O auditor **não conserta** — o anti-viés depende de ele formar o veredito **sem a mão no conserto**
(senão racionaliza o próprio verde). Ele só julga e reporta.

### 3.2 Tratamento de findings em subagente separado

A mestra despacha um **novo subagente** (a *fase de aplicação* da skill) para tratar os findings e
observações, decidindo cada um **com base nos docs e skills, exatamente como §2** (docs resolvem →
corrige e, se houver decisão de fork, ADR; não resolvem 100% → pergunta ao humano). Classificação
**por escopo** (regra da skill):

- **Mudança pequena, de escopo igual ou muito próximo** → corrige **na própria Stage** (push na
  branch do PR). **Não** abre issue-branch-pr só para correção pontual — cerimônia desproporcional.
- **Vira issue separada** **somente** se for **implementação futura** (necessária ou especulativa)
  **ou** escopo de **nova Stage** (capacidade/módulo/dependência novos). Buscar o backlog antes
  (`gh issue list --search`) para não fragmentar.

### 3.3 Re-auditoria (loop até validar)

Depois do tratamento, o subagente refaz a análise: **está tudo validado para fechar a Stage?**
- **Não** → repete **§3.2** (tratar o que sobrou) e re-audita.
- **Sim** → **fecha a auditoria no PR como a skill manda**: comentário com o veredito (status global
  + gates numéricos + fixes aplicados com hash) e o **label de auditoria gravado como `complete`**
  (linha `> **Auditoria:** ...`, CONVENTIONS §3.6) — é o que **destrava o merge** (o workflow
  `audit-gate` do CI falha enquanto não for `complete`).

### 3.4 Relatório ao humano (formato da stage-audit)

Com a auditoria `complete`, a mestra entrega ao humano um **relatório completo e didático do que foi
implementado na Stage**, no **mesmo formato do relatório da skill `stage-audit`** (as 6 seções da
Fase E + status global + conclusão): linguagem clara para quem não acompanhou, jargão glosado, fato
com `arquivo:linha`/comando→resultado, e a lente de **valor entregue + qualidade de design**. Este
relatório **é o gate de aprovação humana**.

### 3.5 Merge, limpeza e próxima Stage

Ao **OK do humano** no relatório, a mestra executa o fechamento (invocar `git-versioning-pointer`
antes das operações git):

```bash
gh pr merge <num> --merge --delete-branch          # merge + apaga a branch remota
git checkout develop && git pull origin develop && git remote prune origin
python scripts/worktree-rm.py <worktree>           # se a Stage rodou em worktree dedicada
```

Depois: **inicia a próxima Stage** do Step (volta ao Princípio central, despachando os subagentes de
fase). O ciclo se repete até a última Stage.

> **Override consciente da skill.** A `stage-audit` diz "nunca faz merge — é do usuário, salvo
> pedido explícito". Aqui o **OK do humano no relatório (§3.4) É o pedido explícito**: a decisão
> irreversível continua sendo do humano (ele aprova); o orquestrador só **executa** o merge que ele
> autorizou. Sem o OK, não há merge.

### Fechamento do Step

Quando **todas** as Stages do Step estiverem mergeadas: atualizar o **status do Step** na Tabela de
Steps do `docs/roadmap.md` (`in_progress` → `done`, `last_reviewed_at` hoje) e entregar o
**relatório do Step** — o que entregou de negócio, as Stages/PRs, os ADRs (forks decididos), e o doc
de domínio que passou a `accepted`.

---

## Fluxo do Step (ordem de execução)

1. **Pré-condições do Step.** Ler `docs/roadmap.md` (recorte do Step: Stages, `depends_on`, BC);
   confirmar que o Step de que depende está `done`. Invocar `git-versioning-pointer` antes de git.
2. **Gate de domínio (§1).** Doc `domain/<bc>/<subdomain>.md` `accepted` cobre o escopo? Não →
   fan-out de pesquisa → tratar forks por §2 → humano ratifica → doc `accepted`. **Sem isso, nenhuma
   Stage começa.**
3. **Para cada Stage do Step, em ordem de dependência:**
   1. Despachar os **subagentes de fase** (Princípio central): Concept → Checkpoint A → Technical →
      Checkpoint B → Execução → Checkpoint C → Auditoria de testes. Cada **fork** é resolvido por
      **§2** (subagente decide via docs+skills, ou sobe à mestra que pergunta ao humano); toda
      decisão de fork vira **ADR**. A execução fecha os gates de saída e **abre o PR** (canônico).
   2. **Auditoria (§3.1)** em subagente → **tratamento de findings (§3.2)** em subagente →
      **re-auditoria (§3.3)** em loop → **auditoria `complete` no PR**.
   3. **Relatório ao humano (§3.4).** Humano dá **OK** → **merge + limpeza (§3.5)**.
   4. Inicia a **próxima Stage**.
4. **Fechamento do Step (§ acima).** Todas as Stages mergeadas → Step `done` no roadmap + relatório
   do Step.

---

## O que NÃO muda (herdado do prompt de nível Stage)

Por dentro de cada fase, **tudo** do canônico continua valendo:

- Carregar contexto antes de agir; pré-condições bloqueantes (working tree limpo, branch correta,
  issue OPEN, estrutura da Stage, `depends_on` **mergeado em develop**).
- Fases 3A/3B/4, critérios de Task Atômica, 3–12 (ou ROADMAP-1) Tasks, escopo estrito por Task.
- **Checkpoints A/B/C** e **auditoria de testes por subagente independente** (loop até todos "sim",
  com mutação real) — aqui são exatamente os subagentes de fase; **nunca** pulados.
- §7 post-execution (`[decision]`/`[finding]`/`[deviation]`); gates de saída inegociáveis com
  **evidência colada**; regra de idioma de código.
- Hierarquia de contradições e o dever de não silenciá-las.

---

## Related

- Nível Stage — canônico: [`./PROMPT-stage-single-session.md`](./PROMPT-stage-single-session.md)
- Issue avulsa: [`./PROMPT-issue-single-session.md`](./PROMPT-issue-single-session.md)
- Categorias `domain/` (pré-requisito do Step) e `audits/` (pós-Stage): [ADR 0.0.0003](./adr/0_0_0003-formalize-domain-and-audits-doc-categories.md)
- Auditoria (pós-Stage): skill `.claude/skills/stage-audit/SKILL.md`
- Pipeline conceitual: [`./PIPELINE.md`](./PIPELINE.md) · Git: [`./GIT-WORKFLOW.md`](./GIT-WORKFLOW.md)