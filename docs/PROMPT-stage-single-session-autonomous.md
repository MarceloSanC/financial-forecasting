---
title: Prompt — Execução de Stage em Sessão Única (variante AUTÔNOMA overnight)
description: Override do PROMPT-stage-single-session para corrida autônoma overnight 1.1→4.3, onde o agente fecha e mergeia a Stage sem gate humano, com auditoria de contexto-limpo no lugar da aprovação
when-use: Apenas na corrida autônoma overnight autorizada pelo ADR 0.0.0050 (stages 1.1→4.3). Não usar em Step 5+.
keywords: [prompt, stage, autonomous, overnight, auto-merge, adr-0050]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
---

# Prompt — Execução de Stage em Sessão Única (variante AUTÔNOMA)

Esta é uma **camada de override** sobre [`./PROMPT-stage-single-session.md`](./PROMPT-stage-single-session.md).
Tudo no prompt canônico continua valendo **exceto** o que esta página redefine.
Autorizada e governada pelo [ADR 0.0.0050](./adr/0_0_0050-autonomous-overnight-mode.md).

> **Pré-condição absoluta:** o ADR 0.0.0050 está `accepted`. Se não estiver, **PARE** — esta variante não se aplica.

---

## O que MUDA em relação ao prompt canônico

### 1. Protocolo de pergunta → decisão autônoma

O prompt canônico manda **PARAR e perguntar** (`AskUserQuestion`) em várias lacunas.
Nesta variante, **a fase de perguntas já aconteceu** (rodada inicial, antes da corrida).
A partir daqui, **NÃO pergunte**. Em vez disso:

- **Lacuna/decisão reversível ou barata** → decida você mesmo seguindo a política de decisão
  autônoma (memória `autonomous-decision-policy`): (a) liste explicitamente as opções,
  (b) pesquise os trade-offs de cada uma com **referência concreta** — nunca afirme sem base,
  (c) avalie o **ganho real** vs o **custo real** de implementação (não superestime o custo),
  (d) prefira a solução **mais simples** que já entrega boa parte do desejado, não prejudica o
  crescimento do sistema e é **fácil de trocar** depois. Registre a decisão num **ADR**
  (`docs/adr/<N>_<M>_NNNN-<slug>.md`, `status: accepted`) com opções, trade-offs e reversibilidade.
- **HALT-and-park** (pare a Stage e, como a cadeia é dependente, a corrida) **apenas** em:
  - contradição com fonte de hierarquia superior (Overview > Roadmap > Concept > Technical),
  - contrato externo **irreversível** e ambíguo (formato persistido, contrato público),
  - gate objetivo que **não fecha** depois de tentativa honesta de correção.
  Ao dar HALT: deixe a working tree estável, escreva o motivo em `§7` do technical e num
  resumo claro, e **não** force progresso.

Regra de ouro: ADR resolve **escolha de design**; HALT resolve **contradição/irreversível**.
Nunca use ADR para enterrar uma contradição que deveria parar a corrida.

### 2. Dados e APIs externas (stages 2.2 / 2.3 / 3.2)

- Use **somente os dados já existentes** em `data/` (copiados do repo anterior:
  `raw/`, `processed/`, `analytics/`). **Não busque dados novos** das APIs.
- Chaves de API existem só para **smoke-test de conectividade** já validado na prep.
- Testes de integração que dependem de chamada externa ao vivo devem rodar contra
  **fakes/fixtures** dos dados existentes — não contra a API ao vivo (evita rate-limit/rede
  travarem a corrida unattended).

### 3. Fechamento, PR e merge — AGORA É VOCÊ QUEM FAZ

Isto **substitui integralmente** a seção "REGRA DE FECHAMENTO E PR" e o "Commit final — NÃO É
VOCÊ QUEM FAZ" do prompt canônico.

Depois de **todos** os gates de saída verdes (idênticos ao canônico: `make check`,
coverage ≥ 90% no diff da Stage, `check_technical_postexec.py`, auditoria de testes em todos
os itens "sim", §7 fiel, findings com Stage candidata, ADRs `accepted`):

1. Atualizar `docs/roadmap.md` (Stage `done`, `updated_at`, `last_reviewed_at` na data de hoje).
2. Commit final:
   ```bash
   git add docs/roadmap.md
   git commit -m "stage <N.M>: complete

   Refs #<issue>"
   ```
3. Conferir base remota (GIT-WORKFLOW Etapa 4) e rebasear a **própria** branch sobre
   `origin/develop` **se** houver carona de outro escopo. **Nunca** force-push em
   `develop`/`main`; **nunca** reescrever história já mergeada.
4. Push + PR contra `develop` (título/corpo em PT, formato GIT-WORKFLOW §Pull Requests):
   ```bash
   git push -u origin <branch>
   gh pr create --base develop --title "feat(<escopo>): stage <N.M> — <title_humano>" --body "..."
   ```
5. **Auditoria de contexto-limpo ANTES do merge** (substitui a "1 aprovação"): a Stage é
   auditada por um agente de **contexto fresco** rodando a skill `stage-audit`. Se a auditoria
   apontar **blocker**, corrija e re-audite; só prossegue com a auditoria sem blocker.
6. Esperar CI verde (`gh pr checks`) e mergear com **merge commit** (NUNCA squash/rebase):
   ```bash
   gh pr merge <num> --merge --delete-branch
   ```
7. Cleanup e sync para a próxima Stage:
   ```bash
   git checkout develop && git pull origin develop && git remote prune origin
   ```

> A auditoria imparcial (passo 5) e os gates objetivos são o que torna o auto-merge seguro.
> Pular qualquer um quebra a justificativa do ADR 0.0.0050.

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
- Governança: [`./adr/0_0_0050-autonomous-overnight-mode.md`](./adr/0_0_0050-autonomous-overnight-mode.md)
- Auditoria: `.claude/skills/stage-audit/SKILL.md`
- Git: [`./GIT-WORKFLOW.md`](./GIT-WORKFLOW.md)
