---
name: git-versioning-pointer
description: Skill de NAVEGAÇÃO para regras de versionamento (git + docs) — invocar ANTES de qualquer operação git/GitHub no repo (`git checkout -b`, `git commit`, `git push`, `gh pr create`, `gh pr merge`, `git rebase`, hotfix, release) ou ao revisar commit/PR alheio. Não contém regras — aponta o trecho exato de `docs/GIT-WORKFLOW.md`, `docs/CONVENTIONS.md` e `scripts/check_commit_msg.py` que governa a operação. Triggers em PT — "vou commitar", "abrir PR", "criar branch", "fazer push", "merge", "rebase", "hotfix", "release", "vou rodar git X". Lean toward triggering — custo de consultar é baixo, custo de produzir artefato fora do padrão (revert/rebase) é alto, e a Stage 1.1 já provou que docs sozinhos não bastam.
metadata:
  status: accepted
  applies_when:
    camada_alvo: [any]
---

# Versioning Pointer

Skill de **navegação** para as regras de versionamento (git + docs).
**Não contém regras** — aponta o trecho exato dos docs onde elas estão.
Isso evita drift: docs são a fonte única; esta skill só te leva lá.

## Como usar

Identifique a operação git/GitHub prestes a acontecer. Salte para a
seção correspondente. Cada uma traz três blocos:

1. **LER** — trechos exatos a consultar antes da operação.
2. **CHECK** — comandos pré-operação (não estão nos docs; complementam).
3. **GOTCHA** — falha conhecida a evitar (do incidente da Stage 1.1).

---

## 🚦 Iniciar uma Stage (antes de qualquer passo do RUNBOOK)

- **LER:** `docs/RUNBOOK-STAGE-LIFECYCLE.md` Passo 1 + `docs/CONVENTIONS.md` §3 (regra de pré-requisito de Fase 3A) + `docs/GIT-WORKFLOW.md` §Princípios fundamentais #1 (Issue-first)
- **CHECK (bloqueante):**
  ```bash
  gh issue view <num> --json number,title,state
  # Falha = STOP. Criar a issue antes de qualquer outra coisa
  # (branch, pasta da Stage, prompt do Concept).
  ```
  Validação programática em CI / local: `make docs-check` roda `scripts/check_stage_issue.py` (best-effort com `gh`; lê `issue_id` do frontmatter do `technical.md` de cada Stage).
- **GOTCHA:** sem issue no backlog, **a Stage nem começa**. Não criar branch, não criar `docs/stages/N.M-<slug>/`, não rodar prompt da Fase 3A. Issue-first é Princípio fundamental #1 do `GIT-WORKFLOW.md`.

## 🎫 Criar issue (`gh issue create`)

- **LER:** `docs/GIT-WORKFLOW.md` §Etapa 1 (Criar issue) + §Princípios fundamentais #1 (Issue-first)
- **CHECK (antes de criar):**
  ```bash
  gh issue list --search "<termos do escopo>" --state open    # já existe issue igual?
  gh issue list --search "<termos do escopo>" --state all     # inclua closed se suspeitar que já foi resolvido
  ```
  Se já houver issue com o **mesmo escopo** — ou cujo escopo **comporta** este trabalho — reaproveitar em vez de abrir card concorrente. Só `gh issue create` quando nenhuma encaixa.
- **GOTCHA:** issue duplicada fragmenta a rastreabilidade (`Refs #`/`Closes #` apontando pra cards concorrentes pelo mesmo trabalho). Buscar no backlog é **pré-requisito** do `gh issue create`. Pós-Stage exige **nova** issue (não a da Stage), mas mesmo aí cheque antes se já não existe uma cobrindo o bug/chore.
- **GOTCHA (melhoria derivada de épico/sub-issue):** ao registrar uma melhoria/correção que **nasce auditando outra issue** (item de épico, follow-up de uma sub-issue ainda aberta), antes de abrir card de refactor/follow-up confira se já há **sub-issue aberta cujo escopo comporta** a nota — e **anexe nela** (ex.: dobrar a observação no ponto de toque correspondente) em vez de abrir issue concorrente quase-idêntica. Issue derivada de escopo sobreposto é a forma mais comum de fragmentação porque parece "nova" no calor da auditoria.
- **GOTCHA (linha no roadmap):** `gh issue create` **não termina** sem a linha correspondente na **tabela do `docs/roadmap.md`** (BC, camada-alvo, status, depende-de). Criar a issue e registrar a linha são **um ato só** — issue criada sem a linha deixa a execução começar com pré-condição furada (vira deviation na sessão seguinte).

## 🌿 `git checkout -b` (criar branch)

- **LER:** `docs/GIT-WORKFLOW.md` §Branches (incluindo "Revisões pós-Stage") + §"Uma branch em voo por vez" (inclui §Trabalho paralelo legítimo: `git worktree` — 2ª branch só em worktree separada via `make worktree BRANCH=...` / `scripts/worktree-new.py` quando escopos disjuntos); `docs/CONVENTIONS.md` §1 (slug em EN) + §4 (formato de branch de Stage e pós-Stage)
- **CHECK:**
  ```bash
  git branch --show-current                        # se != develop/main, voltar
  gh pr list --head $(git branch --show-current)   # PR aberto na branch atual?
  gh issue view <num>                              # toda branch (Stage ou pós-Stage) exige issue
  ```
- **GOTCHA:** se a branch atual não tem PR aberto, **terminá-la primeiro** (Princípio #7). PR parcial em draft é exceção e só sob pedido explícito do usuário.
- **GOTCHA (Stage):** branch de Stage exige issue pré-existente no GitHub (Princípio #1 + CONVENTIONS §3). Se `gh issue view <num>` falha, **não criar branch** — voltar e criar a issue primeiro (RUNBOOK-STAGE-LIFECYCLE Passo 1).
- **GOTCHA (pós-Stage):** branch criada **depois que o PR da Stage já foi mergeado** volta ao formato **genérico** `<tipo>/<num-issue>-<slug>` — **SEM `<N-M>`**. O `<N-M>` é só durante a execução da Stage. Pós-Stage = bug/chore/doc normal, com **nova issue** (não a issue original da Stage). Ver GIT-WORKFLOW §Branches → "Revisões pós-Stage".

## ✍️ `git commit -m`

- **LER:** `docs/CONVENTIONS.md` §4(a) (formato + escopo mínimo + bullets) + §4(b) (reserved gate commits) + §3.2 (regressão `done → draft`); `docs/GIT-WORKFLOW.md` §Commits
- **CHECK:** hook `commit-msg` (de `scripts/check_commit_msg.py`) valida no `git commit`. Antes de re-aprovar algo já `approved`:
  ```bash
  git log --grep="stage N.M:.*approved" --oneline $(git branch --show-current)
  ```
  Se já houver `approved` anterior, fazer `chore(concept|technical): revert to draft — …` PRIMEIRO.
- **GOTCHA:** `[N.M/post-done]` **não existe** — só `[N.M/task-NN]` (Task numerada) ou `[N.M/--]` (off-task com justificativa no body). "Fix rapidinho" não vai junto: ou é `[N.M/--]` com justificativa, ou sai do branch.

## ⬆️ `git push` (qualquer push de branch)

- **LER:** `docs/GIT-WORKFLOW.md` §Etapa 4 → "Antes do push, conferir base remota" + §Comportamento bloqueante
- **CHECK:**
  ```bash
  git fetch --prune origin
  git log --oneline origin/<base>..HEAD        # <base> = develop (feat/fix) ou main (hotfix)
  git rebase origin/<base>                     # sync sempre na base atualizada (não só se houver carona)
  ```
- **GOTCHA (carona):** branch solo por > 1 sessão costuma ter commit de outro escopo perdido. Sempre cheque antes do primeiro push. Push direto em `main`/`develop` é bloqueado por branch protection.
- **GOTCHA (sync/roadmap):** rebase na base **atualizada** antes de **todo** push (não só quando há carona) — mantém as implementações sequenciais e resolve **cedo** o conflito recorrente de `roadmap.md` (várias Stages/issues editam a mesma tabela), em vez de estourar no merge.

## 🚀 `gh pr create`

- **LER:** `docs/GIT-WORKFLOW.md` §Pull Requests + §Etapa 4 + §"Uma branch em voo por vez" (procedimento PR parcial)
- **CHECK:** Etapa 3 fechada (testes verdes, coverage ≥ 90%, lint, working tree limpo) **E** Etapa 4 fechada (`git log origin/<base>..HEAD` sem carona).
- **GOTCHA (título):** formato obrigatório `<tipo>(<escopo>): issue #<num> — <descrição>` (branch avulsa/pós-Stage) ou `<tipo>(<escopo>): stage N.M — <descrição>` (Stage). O identificador `issue #<num> —` / `stage N.M —` é o que mais escapa — **não montar de memória nem espelhar o título da issue**. Escopo = BC, nunca a Stage. **Sem validação programática** (o hook `commit-msg` cobre só commit, não título de PR), então só o code review pega — confira CONVENTIONS §4(c) ANTES do `gh pr create`.
- **GOTCHA:** PR parcial em draft **só sob pedido explícito do usuário**. Título prefixado `... (parcial — checkpoint)` + flag `--draft`.

## 🔀 `gh pr merge`

- **LER:** `docs/GIT-WORKFLOW.md` §Gates de PR + §Etapa 6 + §Comportamento bloqueante
- **CHECK:**
  ```bash
  gh pr view --json mergeable,statusCheckRollup,reviewDecision
  gh pr checks
  ```
- **GOTCHA:** merge commit obrigatório. **NUNCA** `--squash`, **NUNCA** `--rebase`. Comando: `gh pr merge <num> --merge --delete-branch`.

## 🩹 hotfix

- **LER:** `docs/GIT-WORKFLOW.md` §Hotfix + §Defeito descoberto após merge para main
- **GOTCHA:** branch sai de `main` (não de `develop`). Após merge em main, **back-merge em develop** para não perder o fix em próximas releases.

## 🌐 release (`develop → main`)

- **LER:** `docs/GIT-WORKFLOW.md` §Release
- **GOTCHA:** todas as PRs em develop verdes há ≥ 2h; migrations testadas em dev; backup confirmado; rollback plan documentado (se houver migrations).

---

## Mapa rápido (qual seção tem o quê)

| Procura por... | Está em |
|---|---|
| Formato de branch | `GIT-WORKFLOW.md` §Branches + `CONVENTIONS.md` §1 |
| Branch pós-Stage (sem `<N-M>`) | `GIT-WORKFLOW.md` §Branches → "Revisões pós-Stage" + `CONVENTIONS.md` §4 |
| Conventional Commits (formato) | `GIT-WORKFLOW.md` §Commits + `CONVENTIONS.md` §4(a) |
| Reserved gate commits (`stage N.M: ...`) | `CONVENTIONS.md` §4(b) |
| Regressão `done → draft` | `CONVENTIONS.md` §3.2 |
| Tag `[N.M/--]` (off-task) | `CONVENTIONS.md` §4(a) → subseção |
| Seção §7 post-execution do technical.md | `CONVENTIONS.md` §3.4 |
| Gates de PR | `GIT-WORKFLOW.md` §Gates de PR |
| PR parcial em draft (procedimento) | `GIT-WORKFLOW.md` §"Uma branch em voo por vez" |
| Worktrees paralelas (2ª branch, escopos disjuntos) | `GIT-WORKFLOW.md` §"Uma branch em voo por vez" → §Trabalho paralelo legítimo: `git worktree`; `make worktree BRANCH=...` (`scripts/worktree-new.py` / `worktree-rm.py`) |
| Hotfix | `GIT-WORKFLOW.md` §Hotfix |
| Release | `GIT-WORKFLOW.md` §Release |
| Comportamento bloqueante | `GIT-WORKFLOW.md` §Comportamento bloqueante |
| Setup inicial do repo | `GIT-WORKFLOW.md` §Setup inicial |
| Regex do hook commit-msg | `scripts/check_commit_msg.py` |
| Validador "Stage exige issue" | `scripts/check_stage_issue.py` (em `make docs-check`) |
| Iniciar Stage (passo 1: issue) | `RUNBOOK-STAGE-LIFECYCLE.md` Passo 1 + `CONVENTIONS.md` §3 |
| Buscar issue duplicada antes de criar | `GIT-WORKFLOW.md` §Etapa 1 + esta skill §Criar issue |

---

## Loop recursivo

Quando esta skill falhar em prevenir um novo desvio, **fortaleça o GOTCHA
inline da operação** correspondente — coloque a regra acionável no ponto de
uso (onde ela é lida no momento da ação). Se nenhuma seção cobre o caso, crie
o GOTCHA na operação certa. **Não** acumular um histórico de incidentes: o que
reforça cumprimento é a regra inline, não o relato do erro passado.
