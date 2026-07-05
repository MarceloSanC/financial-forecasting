---
title: Prompt — Execução de Stage em Sessão Única (variante INTERATIVA / human-in-the-loop)
description: Override do PROMPT-stage-single-session para corrida assistida onde o agente executa a Stage e conduz até o PR, mas delega ao humano toda decisão de design — explicando opções e trade-offs antes de cada escolha, perguntando de forma iterativa conforme as dúvidas surgem
when-use: Stages do Step 5+ (ex. 5.2→5.5) e demais fatias com decisões de modelagem/design reais, quando se quer a eficiência da sessão única mas mantendo o humano no comando das escolhas. Não confundir com a variante AUTÔNOMA (auto-merge) nem com o canônico puro.
keywords: [prompt, stage, interactive, human-in-the-loop, semi-autonomous, decisao-assistida]
status: accepted
created_at: 2026-07-05
updated_at: 2026-07-05
---

# Prompt — Execução de Stage em Sessão Única (variante INTERATIVA)

Esta é uma **camada de override** sobre [`./PROMPT-stage-single-session.md`](./PROMPT-stage-single-session.md).
Tudo no prompt canônico continua valendo **exceto** o que esta página redefine.

Diferente da variante [AUTÔNOMA](./PROMPT-stage-single-session-autonomous.md) — que **remove** o gate
humano e faz auto-merge sob o [ADR 0.0.0050](./adr/0_0_0050-autonomous-overnight-mode.md) — esta variante
faz o oposto: **reforça** o gate humano nas decisões de design, mas dá ao agente autonomia de **execução**
(implementa, testa, fecha os gates e conduz até o PR). O humano decide o **design** e faz o **merge**.

> **Posição entre as três variantes:**
> - **Canônico** — human-in-the-loop, protocolo de pergunta enxuto; agente conduz até o PR, humano faz o merge.
> - **Interativa (este doc)** — human-in-the-loop com **disciplina de decisão rica**, agente conduz até o PR, humano faz o merge.
> - **Autônoma** — sem gate humano, agente decide via ADR e faz auto-merge (só stages 1.1→4.3, ADR 0.0.0050).

---

## O que MUDA em relação ao prompt canônico

### 1. Protocolo de decisão assistida (substitui o "PROTOCOLO DE PERGUNTA" do canônico)

O canônico já manda perguntar em bifurcações materiais, mas com um protocolo enxuto. Aqui o protocolo
é **mais rico** e **explicitamente iterativo** — mas a decisão **continua sendo do humano**.

**Não há rodada única de perguntas no início.** As dúvidas de design surgem ao longo do Concept, do
Technical e da Execução por Task. Perceba a lacuna → **pare naquele ponto** → apresente a decisão →
espere a escolha do humano → siga. Repita quantas vezes for preciso. É esperado parar várias vezes.

Ao chegar numa decisão de design com alternativa real (a que a variante autônoma resolveria sozinha
via ADR), **em vez de decidir**, apresente ao humano para ele decidir. A apresentação segue a mesma
disciplina da política de decisão autônoma (memória `autonomous-decision-policy`), só que como **insumo
para o humano**, não como auto-decisão:

- **(a)** liste explicitamente as opções reais (2–4);
- **(b)** para cada uma, os trade-offs com **referência concreta** — nunca afirme sem base
  (doc do projeto, LAYOUT, skill aplicável, ADR anterior, ou fonte externa citável);
- **(c)** avalie o **ganho real** vs o **custo real** de implementação (não superestime o custo);
- **(d)** marque uma **(Recomendada)** — a solução **mais simples** que já entrega boa parte do
  desejado, não prejudica o crescimento do sistema e é **fácil de trocar** depois — com a razão
  de uma linha.

Use `AskUserQuestion` (2–4 opções, recomendada explícita). Prefira perguntar **cedo**, quando a
decisão ainda é barata de mudar, a codar na frente e refazer.

**Registro:** depois que o humano decide, a decisão de design com alternativa real descartada vira
**ADR** (`docs/adr/<N>_<M>_NNNN-<slug>.md`, `status: accepted`), registrando opções, escolha do humano,
trade-offs e reversibilidade. O ADR documenta a decisão **independentemente de quem a tomou** — aqui,
o humano. Decisões pequenas in-scope viram `[decision]`/`[deviation]` na §7 do technical, como no canônico.

**Continua NÃO perguntando** (para não virar burocracia):
- detalhes seguidos por convenção (LAYOUT, CONVENTIONS, skills aplicáveis);
- decisões já fechadas em Overview/Roadmap/Concept/Technical;
- reversíveis triviais (nome de variável local, ordem de imports) — decide e segue, com justificativa
  de 1–2 frases no diff.

Regra de ouro: **pergunta** resolve escolha de design; **HALT** resolve contradição/irreversível.
Nunca use uma pergunta cosmética para empurrar ao humano algo que a convenção já resolve, nem
silencie sob "reversível trivial" algo que muda contrato/fronteira/critério de aceite.

### 2. HALT-and-park (contradição / irreversível)

Mantém a hierarquia de contradições do canônico (Overview > Roadmap > Concept > Technical > Código) e
o dever de não silenciá-las. Ao encontrar contradição com fonte superior, contrato externo irreversível
e ambíguo, ou gate objetivo que não fecha após tentativa honesta de correção: **PARE**, deixe a working
tree estável, aponte com referência explícita à fonte conflitante e peça orientação. Não force progresso
e não use ADR para enterrar uma contradição que deveria parar.

### 3. Fechamento, PR e merge — VOCÊ CONDUZ ATÉ O PR; O HUMANO FAZ O MERGE

Isto **detalha** a seção de fechamento e PR do canônico (que agora também abre o PR e deixa o merge
para o humano). Como no canônico e diferente do autônomo (agente faz tudo, inclusive merge):
aqui o agente vai **até o PR aberto e auditado**, e o **merge é do humano**.

Depois de **todos** os gates de saída verdes (idênticos ao canônico: `make check`, coverage ≥ 90% no
diff da Stage, `check_technical_postexec.py`, auditoria de testes em todos os itens "sim", §7 fiel,
findings com Stage candidata, ADRs `accepted`):

1. Atualizar `docs/roadmap.md` (Stage `done`, `updated_at`, `last_reviewed_at` na data de hoje).
2. Commit final:
   ```bash
   git add docs/roadmap.md
   git commit -m "stage <N.M>: complete

   Refs #<issue>"
   ```
3. Conferir base remota (GIT-WORKFLOW Etapa 4) e rebasear a **própria** branch sobre `origin/develop`
   **se** houver carona de outro escopo. **Nunca** force-push em `develop`/`main`; **nunca** reescrever
   história já mergeada.
4. Push + PR contra `develop` (título/corpo em PT, formato GIT-WORKFLOW §Pull Requests):
   ```bash
   git push -u origin <branch>
   gh pr create --base develop --title "feat(<escopo>): stage <N.M> — <title_humano>" --body "..."
   ```
5. **Auditoria de contexto-limpo** por um agente de contexto fresco rodando a skill `stage-audit`. Se
   apontar **blocker**, corrija e re-audite; só considere o PR pronto para revisão humana sem blocker.
6. **PARE no PR aberto e auditado.** **NÃO** rode `gh pr merge`. Entregue o relatório final (estrutura
   do canônico) informando: número do PR, resultado do `stage-audit`, estado do `gh pr checks`, e o
   comando de merge sugerido para o humano rodar após sua revisão:
   ```bash
   gh pr merge <num> --merge --delete-branch    # o HUMANO roda, após revisar
   git checkout develop && git pull origin develop && git remote prune origin
   ```

> O que torna seguro o agente conduzir até o PR (e não além) é a combinação de gates objetivos +
> auditoria imparcial `stage-audit` + **revisão e merge humanos**. O merge é o passo irreversível e
> permanece com o humano — por isso esta variante **não** precisa do ADR 0.0.0050.

---

## O que NÃO muda (continua valendo do prompt canônico)

- Carregar contexto antes de agir; invocar `git-versioning-pointer` antes de operação git.
- Pré-condições bloqueantes (working tree limpo, branch correta, issue OPEN, estrutura da Stage,
  `depends_on` **mergeado em develop** — não só `done` no roadmap).
- Fases 3A (Concept) e 3B (Technical), critérios de Task Atômica, 3–12 (ou ROADMAP-1) Tasks.
- Escopo estrito por Task; §7 post-execution (`[decision]`/`[finding]`/`[deviation]`).
- **Checkpoints A/B/C** (revisão por agentes independentes de contexto zerado) e **auditoria de testes
  por subagente independente** (loop até todos "sim", com mutação real nas funções críticas) — gates
  explícitos, não pular.
- Hierarquia de contradições e o dever de não silenciá-las.

---

## Related

- Base canônica: [`./PROMPT-stage-single-session.md`](./PROMPT-stage-single-session.md)
- Variante autônoma (auto-merge, 1.1→4.3): [`./PROMPT-stage-single-session-autonomous.md`](./PROMPT-stage-single-session-autonomous.md)
- Auditoria: `.claude/skills/stage-audit/SKILL.md`
- Git: [`./GIT-WORKFLOW.md`](./GIT-WORKFLOW.md)
