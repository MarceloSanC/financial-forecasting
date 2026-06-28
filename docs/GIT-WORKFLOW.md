---
title: Git Workflow Padrão
description: Fluxo de versionamento e CI/CD prescritivo para projetos colaborativos
when-use: Consultar antes de qualquer mudança de código. Todos os membros do time devem seguir este fluxo.
keywords: [git, github, workflow, ci-cd, pr, code-review, deploy]
status: done
created_at: 2026-05-12
updated_at: 2026-05-15
---

# Git Workflow Padrão

Fluxo de versionamento e CI/CD para projetos colaborativos. Garante rastreabilidade, qualidade de código, e deploy seguro.

## Princípios fundamentais

1. **Issue-first**: nenhuma alteração começa sem card de issue. O título da issue origina o nome da branch.
2. **Gates bloqueantes**: coverage ≥ 90%, CI verde, aprovação obrigatória. Não pula-se etapa.
3. **Português em commits/PRs/issues; inglês em branches e código**:
   mensagens de commit (subject + body), títulos e corpos de issue,
   títulos e corpos de PR, comentários de code review — todos em
   **português**. Conventional Commits sim, mas com a descrição em PT
   (`feat(auth): adicionar login com Google`). **Nomes de branch em
   inglês** (slug kebab-case, ver [`./CONVENTIONS.md`](./CONVENTIONS.md)
   §1), pois entram em URLs, tabs de IDE e referências de Stage onde
   identificadores estáveis ASCII evitam fricção. Identificadores
   técnicos de código também em inglês.
4. **GitHub CLI (`gh`) preferencial**: usar quando disponível. Fallback para `git` puro se necessário.
5. **Sem deploy manual**: produção só via merge em `main`. Dev só via merge em `develop`. SSH em prod é proibido.
6. **Merge commit preserva história**: NUNCA squash, NUNCA rebase no merge. Branches trazem toda sua contexto.
7. **Uma branch em voo por vez**: não abrir branch nova enquanto a
   anterior estiver sem PR aberto. Ver §"Uma branch em voo por vez"
   adiante para o procedimento de PR parcial quando precisar trocar
   de escopo no meio.

---

## Setup inicial (1x por projeto)

### Branches base

```bash
git branch -M main                    # renomear master pra main (se necessário)
git push -u origin main
git checkout -b develop
git push -u origin develop
```

Configurar `develop` como branch padrão no GitHub (Settings → Branches → Default branch).

### Aliases recomendados

`git sync` atualiza `main` localmente em um passo (fetch com prune, checkout, fast-forward). Útil antes de abrir branch de hotfix (que sai de `main`) ou logo após merge de release.

```bash
git config --local alias.sync '!git fetch --prune origin && git checkout main && git pull --ff-only origin main'
```

- **`--local`** (default no bootstrap): só vale neste repo. Se quiser o alias em todos os seus repos, troque por `--global`.
- **`--ff-only`** garante que o pull falha se houver merge necessário — segurança contra reescrever histórico de `main` por engano.
- **`fetch --prune`** remove refs locais de branches já deletadas no remoto, evitando lixo em `git branch -r`.

> Projetos criados por `scripts/init-project.py` já vêm com esse alias configurado em escopo local.

Uso:

```bash
git sync               # atualiza main local, sai checkado em main
```

### Branch protection rules (Settings → Branches)

Aplicar **identicamente** em `main` e `develop`:

- ✅ Require a pull request before merging
- ✅ Require approvals: **1**
- ✅ Dismiss stale pull request approvals when new commits are pushed
- ✅ Require status checks to pass before merging
  - `test` (CI)
  - `coverage` (≥ 90%)
- ✅ Require branches to be up to date before merging
- ✅ Require conversation resolution before merging
- ❌ Do not allow bypassing the above settings
- ✅ Restrict who can force push (admin only)
- ✅ Restrict who can delete branches (admin only)

### Gates de PR (fonte única)

Todo PR (incluindo PRs de Stage) precisa passar nos gates abaixo antes do
merge. Esta é a **fonte única** dos gates — [`./PIPELINE.md`](./PIPELINE.md) §9.5 e CLAUDE.md
referenciam esta seção em vez de duplicar a lista:

- **CI verde:** workflow `ci.yml` (lint + typecheck + layout-check +
  tests) deve passar.
- **Coverage ≥ 90%:** materializado em `pyproject.toml`
  `[tool.coverage.report] fail_under = 90`; o pytest falha sozinho se a
  cobertura cair abaixo.
- **+1 aprovação:** code review obrigatório (`Require approvals: 1`).
- **Branch atualizada:** PR precisa estar à frente da base (`Require
  branches to be up to date`).
- **Conversas resolvidas:** todos os comentários do code review devem
  ter status "Resolved".
- **Merge commit obrigatório:** **NUNCA** squash/rebase no merge —
  preserva historicidade auditável (sequência de commits da Stage no
  branch fica visível em `git log --first-parent develop`).

Mudar qualquer um desses números (ex: coverage de 90 → 80, aprovações de
1 → 2) exige edição desta seção como ponto único — os ponteiros não
precisam mudar.

Para confirmar, classe a classe, que cada check rodado por `make check`
realmente falha com exit ≠ 0 (e portanto o CI rejeita o estado quebrado
antes do merge), ver o runbook
[`runbooks/validate-ci-gate.md`](./runbooks/validate-ci-gate.md).

### GitHub Environments (Settings → Environments)

**Environment: `development`**
- Sem required reviewers
- Deploy automático ao fazer merge em `develop`
- Secrets: `DATABASE_URL`, `API_KEY`, etc. (valores de dev)

**Environment: `production`**
- Required reviewers: **todos os membros do time** (aprovação manual)
- Wait timer: 0 (sem delay)
- Secrets: valores de produção (instância de DB diferente, chaves reais)
- Deploy automático ao fazer merge em `main`, após aprovação

### Workflows de CI/CD

Estrutura em `.github/workflows/`:

```
.github/workflows/
├── ci.yml           # Roda em todo PR e push: lint + test + coverage
├── deploy-dev.yml   # Roda em push para develop (automático)
└── deploy-prod.yml  # Roda em push para main (com aprovação)
```

### Issue e PR templates

Criar em `.github/`:

```
ISSUE_TEMPLATE/
├── feature.md       # Features novas
├── bug.md           # Bug reports
└── chore.md         # Manutenção

PULL_REQUEST_TEMPLATE.md
```

---

## Nomes e convenções

### Branches

```
main                                # produção
develop                             # desenvolvimento (default)
├── feat/<num-issue>-<desc>        # feature nova
├── fix/<num-issue>-<desc>         # bug fix
├── refactor/<num-issue>-<desc>    # refatoração
├── docs/<num-issue>-<desc>        # doc de um issue
└── docs/<desc>                    # só documentação geral
```

**Exemplos válidos:**
- `feat/42-add-google-login`
- `fix/57-fix-payments-api-timeout`
- `refactor/89-extract-shipping-service`
- `docs/update-readme-q2`

**Regra:** min. 3 chars após tipo, máx. 50 chars total. Kebab-case, sem acentos.

**Stages do pipeline:** branches de Stage seguem o formato especializado `<tipo>/<num-issue>-<N-M>-<slug>` (ex.: `feat/42-1-1-bootstrap`, `feat/89-2-3-s3-source-adapter`). `N.M` é o id da Stage. Ver [`./CONVENTIONS.md`](./CONVENTIONS.md) §4.

**Revisões pós-Stage:** correções/melhorias criadas **depois que o PR da Stage já foi mergeado** voltam ao formato **genérico** acima — **sem `<N-M>`**. Tipo segue a natureza da mudança (`fix`, `chore`, `docs`, `refactor`), e a branch sai de uma **nova issue**.

- ✅ `fix/103-fix-s3-credentials-error` (correção pós-Stage 2.3, nova issue #103)
- ✅ `docs/107-document-post-stage-branch-pattern` (doc pós-Stage, nova issue #107)
- ❌ `fix/103-2-3-fix-s3-credentials-error` (`<N-M>` não pertence — a Stage 2.3 já fechou)

O `<N-M>` no nome identifica a **execução da Stage**; depois que ela fechou, o trabalho passa a ser bug/chore/doc normal e a rastreabilidade fica no `Refs #<num-issue>` do commit. Ver §"Defeito descoberto após merge para main" e [`./CONVENTIONS.md`](./CONVENTIONS.md) §4.

### Commits

**Formato:**
```
<tipo>(<escopo>): <descrição imperativa em português>

- <detalhe 1>
- <detalhe 2>

Refs #<num-issue>
```

**Tipos:**
| Tipo | Quando |
|---|---|
| `feat` | Nova funcionalidade |
| `fix` | Correção de bug |
| `refactor` | Refatoração (sem mudança de comportamento) |
| `test` | Adicionar/ajustar testes |
| `docs` | Documentação |
| `style` | Formatação (sem mudança lógica) |
| `perf` | Melhoria de performance |
| `chore` | Manutenção geral |
| `ci` | Mudanças em CI/CD |
| `build` | Mudanças em build/deps |

**Exemplos prontos:**

```
feat(auth): adicionar login com Google

- Integrar OAuth 2.0 com authlib
- Criar endpoint POST /auth/google/callback
- Adicionar campo google_id ao User
- Persistir tokens em user_sessions

Refs #42
```

```
fix(payment): corrigir timeout na API de pagamentos

- Aumentar timeout de 5s para 30s
- Adicionar retry com backoff exponencial (3 tentativas)
- Logar tentativas falhadas com nível WARNING

Refs #57
```

**Regra:** 1 commit = 1 mudança lógica. Se fez 5 coisas, 5 commits.

### Pull Requests

**Título:** Conventional Commits em português (ver §Princípios
fundamentais #3), com **escopo obrigatório** e o identificador da
Stage/issue na descrição, após um travessão `—`. Dois formatos:

- **PR de Stage:** `<tipo>(<escopo>): stage N.M — <descrição>`
  - ex.: `feat(billing): stage 12.10 — relatório de inadimplência`
- **PR de branch (pós-Stage / issue avulsa):** `<tipo>(<escopo>): issue #<num> — <descrição>`
  - ex.: `fix(tooling): issue #53 — corrigir gate do pre-commit`

Em ambos o `<escopo>` é o BC/módulo da mudança (ASCII/kebab), **nunca**
a Stage — mesma regra de escopo mínimo dos commits (CONVENTIONS §4(a)).
O número da Stage/issue vai na descrição, depois do `—`, não no escopo.
Não há gate de CI sobre o título de PR; a conformidade é garantida no
code review. Detalhes e exemplos: CONVENTIONS §4(c).

**Corpo:**
```markdown
Closes #<num-issue>

## O que muda
<resumo 2–4 frases>

## Como testar
1. <passo 1>
2. <passo 2>
3. <resultado esperado>

## Checklist
- [ ] Testes passando
- [ ] Coverage ≥ 90% no código alterado
- [ ] Lint sem erros
- [ ] Documentação atualizada (se aplicável)
- [ ] Migrations adicionadas (se aplicável)

## Screenshots
<se for mudança visual>

## Notas para reviewer
<pontos de atenção, decisões de design>
```

---

## Fluxo de trabalho (etapas)

### Etapa 1: Criar issue

**Antes de criar, buscar duplicata:** rodar `gh issue list --search "<termos do escopo>"` (use `--state all` se suspeitar que já foi resolvido) e conferir se não existe issue com o **mesmo escopo** — ou cujo escopo **comporta** este trabalho. Se houver, reaproveitar em vez de abrir card concorrente; só criar nova quando nenhuma encaixa. (Issue duplicada fragmenta a rastreabilidade do `Refs #`/`Closes #`.)

**Registrar melhoria futura como issue.** Toda melhoria/gap identificado que **não entra no escopo atual** deve virar **issue** — não ficar só num docstring, comentário de código ou `[finding]` em `technical.md`/`concept.md` (registro solto tem risco de esquecimento permanente; a issue é o que garante que o ponto volta à pauta). Se a melhoria ainda é **abstrata/incerta** (não se sabe se será mesmo necessária):

- marque a incerteza **explicitamente no corpo** — uma seção `## Incerteza` descrevendo o que ainda não se sabe — e, opcionalmente, a label `status: speculative`;
- declare o **momento previsto** de reavaliação: uma **condição de disparo** (ex.: "quando surgir o 3º consumidor deste helper", "quando o domínio modelar `<condição futura>`"). Momento previsto ≠ compromisso de data;
- **não** descreva a solução proposta como definitiva. Registre-a como **ponto de partida** e deixe explícito que **deve ser reavaliada no momento da implementação** — premissas e contexto podem ter mudado.

Descrever claramente:
- **Contexto:** por que estamos fazendo isso?
- **Critérios de aceite:** comportamento esperado (checklist)
- **Tarefas técnicas:** passos de implementação (se conhecidos)

Exemplo:
```markdown
## Contexto
Usuários de Google querem autenticação automática via Google Account.

## Critérios de aceite
- [ ] Usuário pode clicar em "Login com Google" na página de login
- [ ] Após autenticação, é redirecionado para dashboard
- [ ] Seus dados de Google (nome, email) são salvos automaticamente
- [ ] Coverage ≥ 90% nos testes de auth

## Tarefas técnicas
- [ ] Setup OAuth app no Google Cloud
- [ ] Integrar biblioteca authlib
- [ ] Criar model GoogleUser
- [ ] Implementar callback endpoint
```

Criar com (título e corpo em português):
```bash
gh issue create --title "feat: adicionar login com Google" --body "..."
```

### Etapa 2: Criar branch

Atualizar `develop`:
```bash
git checkout develop
git pull origin develop
```

Criar branch a partir do título da issue (slug **em inglês**, ver §Princípios fundamentais #3):
```bash
git checkout -b feat/42-add-google-login
```

**Gate:** `git branch --show-current` mostra o nome correto.

### Etapa 3: Implementar (loop)

1. **Sempre verificar branch antes de codificar:**
   ```bash
   git branch --show-current
   ```
   Se for `develop`/`main`, voltar para Etapa 2.

2. **Implementar incrementalmente, em escopo mínimo:**
   - Escrever código
   - Rodar testes: `pytest` ou `pnpm test`
   - Rodar lint: `ruff check` / `biome check`
   - Commitar com **escopo mínimo**: 1 commit = 1 mudança lógica
     numa única feature/módulo/BC. Se tocou em 3 escopos diferentes,
     são 3 commits. Subject e body em **português** (ver §Princípios
     fundamentais #3); body em bullet points (≥ 1 bullet). Padrão
     detalhado em [`./CONVENTIONS.md`](./CONVENTIONS.md) §4(a).
   - O hook `commit-msg` (instalado em `make setup`) valida o
     subject contra o padrão antes de aceitar o commit. Se rejeitar,
     ler a mensagem e ajustar — não tem como "passar por cima".

3. **Verificar coverage:**
   ```bash
   pytest --cov
   ```
   Mínimo: **90%** no código novo/alterado.

**Gates antes de sair desta etapa:**
- [ ] Critérios de aceite da issue atendidos
- [ ] Testes passando
- [ ] Coverage ≥ 90%
- [ ] Lint sem erros
- [ ] Working tree limpo (`git status` limpo)

Se qualquer falhar: **PARAR** e corrigir antes de prosseguir.

### Etapa 4: Push e abrir PR

**Antes do push, conferir base remota.** O branch precisa carregar
apenas commits do escopo dele — nada de "carona" de outro escopo (fix
solto, ajuste de bootstrap, commit de outra Stage). Listar commits que
o branch adiciona sobre a base:

```bash
git fetch --prune origin
git log --oneline origin/<base>..HEAD       # <base> = develop (feat/fix/refactor) ou main (hotfix)
git log --oneline origin/main..HEAD         # sanity check broader: tudo no branch que main ainda não tem
```

Para a Stage `feat/42-add-google-login`, `<base>` é `develop`. Para um
`hotfix/99-...`, é `main`.

- **Saída esperada:** só os commits do branch (Conventional + tags
  `[N.M/...]` se for Stage; reserved gate commits se aplicável).
- **Se aparecer commit fora do escopo** (ex.: `fix: sync boilerplate
  fixes` sem `Refs #` e sem tag): rebasear em `origin/<base>` para
  mover esses commits para fora do branch, ou movê-los para um PR
  próprio. Não empurre carona junto da Stage.

```bash
git rebase origin/<base>                    # se houver carona
```

Quando o `git log origin/<base>..HEAD` mostrar só commits do escopo:

```bash
git push -u origin feat/42-add-google-login
```

Abrir PR contra `develop` (não main; título em português, com escopo +
identificador da issue na descrição — ver §Pull Requests / CONVENTIONS §4(c)):
```bash
gh pr create --base develop --title "feat(auth): issue #42 — adicionar login com Google" --body "..."
```

**Gates:**
- [ ] `git log origin/<base>..HEAD` mostra **apenas** commits do escopo do branch
- [ ] PR aberto e link disponível

### Etapa 5: Review + CI

Verificar status:
```bash
gh pr checks      # CI
gh pr view        # comentários e aprovações
```

**Se CI falhou:** voltar para Etapa 3, corrigir e fazer novo commit.

**Se faltam aprovações:** aguardar review de outro dev. Não mergear sem aprovação.

**Se há comentários:** responder e fazer commits adicionais se necessário.

**Gates:**
- [ ] CI verde (todos os checks passando)
- [ ] ≥ 1 aprovação de outro dev
- [ ] Sem comentários não-resolvidos

### Etapa 6: Merge

Garantir que a branch está atualizada:
```bash
gh pr view --json mergeable
```

Se "BEHIND":
```bash
git fetch origin
git merge origin/develop
git push
```

Fazer merge commit (NUNCA squash):
```bash
gh pr merge <num> --merge --delete-branch
```

**Gate:** PR mergeado em develop, branch deletada.

### Etapa 7: Cleanup

```bash
git checkout develop
git pull origin develop
git remote prune origin
```

Verificar:
- [ ] Issue fechada automaticamente
- [ ] Deploy em dev disparado (verificar em GitHub Actions)
- [ ] Card no project board movido para "Done"

---

## Release (deploy em produção)

Quando a equipe decide promover `develop` para `main`:

1. Criar PR de release (título e corpo em português):
   ```bash
   gh pr create --base main --head develop --title "release: 2026-05-12" --body "Inclui PRs #42, #57, #89"
   ```

2. Listar PRs incluídos:
   ```bash
   gh pr list --base develop --state merged --limit 30
   ```

3. Obter aprovação + CI verde (mesmo gate de qualidade).

4. Merge commit em main:
   ```bash
   gh pr merge <num> --merge
   ```

5. Workflow de `deploy-prod` dispara automaticamente.

6. Aprovadores clicam em "Review deployments" no GitHub Actions e aprovam.

7. Deploy executa (automático após aprovação).

**Pré-requisitos de release:**
- [ ] Todas as PRs em develop estão verdes há ≥ 2 horas
- [ ] Migrations foram testadas em dev
- [ ] Backup automático do banco de produção confirmado
- [ ] Rollback plan documentado (se houver migrations)

---

## Uma branch em voo por vez

**Regra (Princípios fundamentais #7):** enquanto a branch atual não
estiver com PR aberto, **não criar branch nova** para outro escopo.
Trabalho paralelo em dois escopos diferentes — mesmo "rapidinho" —
costuma:

- misturar commits dos dois escopos via working tree não-limpo
  (`git stash` muitas vezes vira `git stash drop` errado);
- gerar PRs simultâneos disputando o mesmo gate humano de review;
- esconder progresso real — branch antiga vai ficando esquecida
  enquanto a "urgente" cresce e nunca volta.

**Fluxo padrão:** terminar a branch atual → abrir PR → começar a
próxima. Ponto.

### Trabalho paralelo legítimo: `git worktree`

A regra "uma branch em voo por vez" trata de **um único checkout
misturando dois escopos**. Quando o paralelismo é legítimo (ex.: PR da
branch anterior está em review aguardando aprovação, e você quer
começar a próxima), o mecanismo aceito é criar uma **worktree
separada** — cada worktree é um checkout independente, então não há
working tree compartilhado, não há `git stash`, não há risco de
misturar commits.

```bash
make worktree BRANCH=feat/42-add-google-login
```

O target roda `scripts/worktree-new.py`, que num único comando:

- valida o nome da branch contra CONVENTIONS.md §4;
- confere que a issue existe no GitHub (`gh issue view`);
- cria a worktree em `../<repo>-worktrees/<branch>/` saindo de
  `origin/<base>` (auto: `develop`, ou `main` para `hotfix/...`);
- copia `.env`/`.env.local` do checkout principal;
- **gera portas livres no `.env` da worktree** (`APP_PORT`,
  `POSTGRES_PORT`, `REDIS_PORT`) para o devcontainer/docker compose da
  paralela não brigar com o da principal por bind no host;
- roda `make setup` (uv venv + deps + pre-commit hooks);
- abre uma nova janela do VS Code na worktree.

Flags úteis (passar via `ARGS='...'`):

- `--create-issue --issue-title "feat: ..."` — cria a issue antes
  (substitui o `<num>` por placeholder `-`, ex.: `feat/-add-foo`).
- `--no-setup` / `--no-vscode` / `--no-env` / `--no-port-assign` — opt-outs.
- `--base main` — força base remota (default já cuida de hotfix).

#### Por que o devcontainer não conflita entre worktrees

O `docker-compose.yml` do template foi desenhado para ser
**worktree-safe**:

- **Sem `container_name:` fixos.** O Compose usa o `--project-name`
  (= nome da pasta da worktree) como prefixo automático, gerando
  nomes únicos por worktree: `sandbox-test-app-1` na principal vs.
  `feat-1-foo-app-1` na paralela. Definir `container_name:` quebra
  esse mecanismo, então o template intencionalmente omite.
- **Portas do host parametrizadas.** As linhas de `ports:` usam
  `${APP_PORT:-8000}:8000`, `${POSTGRES_PORT:-5432}:5432`,
  `${REDIS_PORT:-6379}:6379`. O default preserva o comportamento de
  uma única worktree, e o `worktree-new.py` sobrescreve via `.env` na
  paralela. O lado *dentro* do container continua sempre 8000/5432/6379
  — só o lado do host muda.

Se adicionar um serviço novo ao compose com porta exposta no host
(ex.: mailhog), inclua a variável correspondente em `PORT_DEFAULTS`
dentro de `scripts/worktree-new.py` para entrar na rotação de
auto-atribuição.

Quando o PR daquela worktree mergear, remover worktree + branch local:

```bash
python scripts/worktree-rm.py <branch>      # remove worktree + branch local (--dry-run mostra o que faria; --force pula o check de sync)
# ou, manualmente:
git worktree remove ../<repo>-worktrees/<branch>
```

Detalhes e todas as flags: `python scripts/worktree-new.py --help` e
`python scripts/worktree-rm.py --help`.

### Quando precisar trocar de escopo no meio (com PR parcial)

**Só fazer isso quando o usuário pedir explicitamente.** Não é
proatividade — é exceção justificada (bloqueio externo, prioridade
mudou, descobriu trabalho urgente que precede o atual).

Procedimento:

1. **Estabilizar a branch atual.** Working tree limpo, todos os
   commits prontos seguindo o padrão de §Commits (1 commit = 1
   mudança lógica, escopo mínimo, body em bullets).
2. **Conferir base remota** — `git log origin/<base>..HEAD` mostra
   só commits do escopo da branch (ver Etapa 4). Rebasear em
   `origin/<base>` se houver carona.
3. **Abrir PR parcial** com título prefixado (português):
   ```bash
   gh pr create --base develop --draft --title "feat(auth): issue #42 — adicionar login com Google (parcial — checkpoint)" --body "..."
   ```
   - Usar `--draft` para sinalizar que não está pronto para review.
   - No corpo, listar **o que já está pronto** e **o que falta**
     (checklist com `[x]` / `[ ]`). Se for Stage, citar quais Tasks
     do `technical.md` já estão fechadas.
   - Não pedir review ainda. PR draft existe para travar a posição
     do trabalho, não para consumir tempo de revisor.
4. **Voltar para `develop`** (ou `main` em hotfix) e criar a branch
   nova:
   ```bash
   git checkout develop && git pull
   git checkout -b feat/<num-issue>-<N-M>-<slug>   # a nova
   ```
5. **Implementar a nova branch ao fim** — PR contra `develop`,
   review, merge normal.
6. **Voltar para a branch parcial.** Sair do `draft`, completar
   trabalho restante, novos commits seguindo escopo mínimo:
   ```bash
   git checkout feat/<branch-parcial>
   git merge develop                # absorver o que entrou
   # ... continuar implementação ...
   gh pr ready                      # tira do draft, pede review
   ```
7. **Merge da branch parcial normal** — mesmo gate de PR de §Gates
   de PR.

**Importante:**

- **PR parcial não passa para review enquanto draft.** Manter draft
  até a branch estar completa (todos os critérios de aceite da
  issue atendidos).
- **PR parcial não dispensa gates.** Quando sair do draft, mesmos
  gates: CI verde, coverage ≥ 90%, 1 aprovação, sem comentários
  abertos.
- **Não usar isso como rotina.** Se acontecer mais de 1 vez por
  mês, o problema está no recorte das Stages/issues — escopo maior
  do que o necessário. Discutir em retro.

---

## Hotfix (bug urgente em produção)

Branch sai de `main`, não de `develop`:

```bash
git sync                                                # atualiza main local (ver §Aliases recomendados)
git checkout -b hotfix/99-fix-critical-checkout-error
```

Implementar com **mesmo rigor** (testes, coverage, lint).

Abrir PR contra `main` (título em português; branch em inglês):
```bash
gh pr create --base main --title "fix(checkout): issue #99 — erro crítico no checkout" --body "..."
```

Review acelerado mas **NUNCA pulado**.

Após merge em main, fazer back-merge em develop:
```bash
git checkout develop && git pull
git merge main
git push
```

Isso garante que o fix não se perde em próximas releases.

---

## Defeito descoberto após merge para main

Cenário: PR passou no review, foi mergeado, está em produção, e
descobre-se um bug. **Não reescrever histórico.**

- **Urgente** (afeta produção ou bloqueia usuários): seguir o fluxo de
  Hotfix acima.
- **Não-urgente** (pode aguardar próxima release): abrir nova issue
  (`fix: ...`) e tratar como bug normal — branch a partir de `develop`
  no formato **genérico** `fix/<num-issue>-<slug>` (sem `<N-M>`, mesmo
  se a Stage de origem era `N.M`; ver §Branches → "Revisões pós-Stage"),
  PR contra `develop`, release subsequente carrega o fix para `main`.

Em ambos os casos: documentar na issue **o que escapou** e **como
deveria ter sido detectado no review**. Lições alimentam o checklist de
PR review.

---

## Como revisar código (code review)

Quando revisor:

1. **Ler issue e PR**: entender contexto e critérios de aceite.

2. **Conferir mudanças:**
   - [ ] Código resolve o problema descrito?
   - [ ] Mudanças batem com título/descrição do PR?
   - [ ] Testes cobrem cenários positivos **e negativos**?
   - [ ] Coverage é ≥ 90%?

3. **Apontar problemas:**
   - **Bloqueante:** quebra funcionalidade, introduz bug, security issue
   - **Não-bloqueante (nit):** estilo, clareza, performance, debt técnico

4. **Sugerir:**
   ```bash
   gh pr review <num> --approve           # aprovar
   gh pr review <num> --request-changes   # pedir mudanças
   gh pr comment <num> --body "comentário"  # comentar
   ```

Exemplo de feedback construtivo:
> "A lógica está correta, mas o nome `tmp_user` é vago. Sugerir `validated_user` ou `user_after_oauth`. Nit."

---

## Comportamento bloqueante (regra absoluta)

**PARE** se detectar qualquer um desses cenários:

- Tentativa de push direto em `main` ou `develop`
- Tentativa de merge **sem** CI verde
- Tentativa de merge **sem** ≥ 1 aprovação
- Coverage < 90% em código novo
- Branch errada para a operação (ex: `feat/x` em vez de branch de feature)
- Squash ou rebase no merge (deve ser merge commit)
- Working tree com mudanças não commitadas em momento crítico
- Push de branch com carona de outro escopo: `git log origin/<base>..HEAD` mostra commits que não pertencem ao escopo declarado do branch (ver Etapa 4)
- Mensagem de commit fora do padrão Conventional Commits **em português** (descrição em PT, escopo em snake/kebab ASCII) ou sem `Refs #<num-issue>` no rodapé quando há issue associada
- Nome de branch **fora de inglês ASCII kebab-case** (ex.: `feat/42-adicionar-login` ou `feat/42-Add-Login` — deve ser `feat/42-add-google-login`; ver §Princípios fundamentais #3 e [`./CONVENTIONS.md`](./CONVENTIONS.md) §1)
- Tentativa de criar branch nova **no mesmo checkout** enquanto a branch atual não tem PR aberto (mesmo `--draft`). Exceções: (a) branches **sem correlação/conflito** (escopos disjuntos) em worktrees separadas (ver §"Uma branch em voo por vez" → §Trabalho paralelo legítimo); (b) usuário pediu **explicitamente** o fluxo de PR parcial (ver §"Uma branch em voo por vez")
- Body de commit de Task sem bullets, ou commit agrupando vários escopos diferentes (deve quebrar em commits separados por escopo mínimo)
- Iniciar uma Stage (criar branch da Stage, pasta `docs/stages/N.M-<slug>/`, ou rodar prompt da Fase 3A) **sem que a issue correspondente já exista** no backlog do GitHub. Verificação: `gh issue view <num>` deve retornar a issue. Issue-first é Princípio fundamental #1; sem issue verificável, parar e criar a issue primeiro (ver [`./RUNBOOK-STAGE-LIFECYCLE.md`](./RUNBOOK-STAGE-LIFECYCLE.md) Passo 1 + `scripts/check_stage_issue.py` em `make docs-check`)

**Ação:** Explicar o problema, sugerir correção, e exigir confirmação explícita se insistir:

> "⚠️ Coverage é 73%, mínimo é 90%. Para prosseguir mesmo assim, confirme: **confirmo prosseguir**"

---

## Quick reference

```bash
# Issues (título e corpo em português)
gh issue create --title "feat: ..." --body "..."
gh issue list --assignee @me
gh issue view <num>

# Branches (slug em inglês) e commits (subject + body em português; Refs no rodapé)
git checkout -b feat/42-short-slug-in-english
git add .
git commit -m "feat(escopo): descrição curta em português

- bullet 1
- bullet 2

Refs #42"

# Antes do push (conferir base remota — Etapa 4)
git fetch --prune origin
git log --oneline origin/develop..HEAD     # ou origin/main..HEAD em hotfix
git rebase origin/develop                  # se houver carona de outro escopo

# PRs
gh pr create --base develop --title "..." --body "..."
gh pr checks                    # status do CI
gh pr view                      # detalhes
gh pr review --approve          # aprovar
gh pr merge <num> --merge --delete-branch  # merge commit + cleanup

# Deploy
git sync                                 # atualiza main local
gh pr create --base main --head develop  # criar release PR

# Cleanup
git checkout develop && git pull
git remote prune origin
```

---

## Materiais complementares

- [GitHub Docs: About branches](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-branches)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [GitHub Docs: Branch protection rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule)