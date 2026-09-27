# CLAUDE.md — Contexto para Agentes de IA

Este arquivo fornece contexto essencial para que agentes de IA (Claude Code, Copilot, etc.)
entendam o projeto antes de fazer qualquer mudança. Leia-o inteiro antes de codar.

---

## Visão Geral do Projeto

**Financial Forecasting** — Calibração probabilística de previsões de retorno com TFT (piloto AAPL)

Pipeline de previsão probabilística de retornos diários com TFT quantílico, em arquitetura hexagonal e medalhão (bronze/silver/gold). Avaliação estatística confirmatória (pinball, DM/MCS/Holm, calibração e conformal) como serviços de domínio apoiados em bibliotecas validadas contra oráculo; piloto AAPL, multi-asset-ready.

---

## Stack Técnica

Dependências e versões: `pyproject.toml`. Convenção fora do default: SQLAlchemy só **Core** — sem ORM declarativo.

---

## Arquitetura

Este projeto segue **Vertical Slices** com **Ports & Adapters (Hexagonal)** dentro de cada slice.

Consulte [docs/LAYOUT.md](docs/LAYOUT.md) para as regras completas de dependência, estrutura de pastas
e convenções de nomenclatura. **Antes de criar qualquer arquivo novo, verifique onde ele se
encaixa no docs/LAYOUT.md.**

**Regras críticas de dependência:** fonte única em [docs/LAYOUT.md §3](docs/LAYOUT.md). Não duplicar aqui — diverge ao longo do tempo. A IA deve sempre conferir LAYOUT.md antes de criar imports.

---

## Contexto Atual

<!-- Atualize esta seção com o estado atual do projeto antes de iniciar uma sessão de IA -->

- **Decisões arquiteturais recentes (ADRs):** veja `docs/adr/`

---

## Convenções de Git

Fonte da verdade: [docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md). Resumo do essencial:

- **Branches:** `feat/<num-issue>-<N-M>-<slug>`, `fix/...`, `refactor/...`, `docs/<desc>`. Saem de `develop` (hotfix sai de `main`). **Slug em inglês** (kebab-case ASCII; entra em URLs/tabs). Formato e regras completas: [docs/CONVENTIONS.md](docs/CONVENTIONS.md) §4.
- **Commits:** Conventional Commits **em português** com **escopo mínimo obrigatório** (`<tipo>(<escopo>): <descrição>`) — escopo em ASCII/kebab, descrição em PT acentuado. Body em bullet points. `Refs #<num-issue>` no rodapé. 1 commit = 1 mudança lógica em **um** escopo. Hook `commit-msg` valida o subject (`make setup` instala). Detalhes em [docs/CONVENTIONS.md](docs/CONVENTIONS.md) §4.
- **Branches em paralelo:** sem limite de quantidade; só não se cria branch em conflito direto com outra em voo; cada uma na sua worktree criada por `python scripts/worktree-new.py <branch> --no-setup --no-vscode`. Checkout principal sempre livre em `develop` (hook `git_guard` recusa criar/trocar branch nele). Critérios e PR parcial: [docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md) §"Branches em voo".
- **PRs e issues:** título e corpo em **português**, no formato do commit; PRs contra `develop`. **Gates de PR (CI verde, coverage, aprovações, merge commit):** fonte única em [docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md) §Gates.
- **Idioma:** PT em commits, títulos de issue/PR, corpos de issue/PR e code review. **EN em nomes de branch** e identificadores de código (escopo do commit também ASCII). Docs em `docs/` em PT.
- **Antes de `git push`:** rodar `git log origin/<base>..HEAD` (`<base>` = branch de origem, normalmente `develop`); se houver commits de outros escopos pegando carona, rebasear em `origin/<base>` antes de abrir PR. Ver [docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md) §Etapa 4.

Detalhes operacionais (setup inicial, branch protection, release, hotfix, code review): ver [docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md).

---

## Comandos Úteis

Alvos do `Makefile` (`make help` lista todos). `make check` é o gate bloqueante completo (lint, typecheck, layout, import-linter, fake-parity, port-coverage, docs e testes).

### Docker / devcontainer

O projeto vem com Docker desde o dia 1 (`Dockerfile` multi-stage + `docker-compose.yml`). Há três caminhos para desenvolver:

- **Devcontainer (recomendado):** VS Code → `Dev Containers: Reopen in Container`. Sobe a stage `builder` do `Dockerfile` via `docker-compose.yml`, com `uv`/`ruff`/`mypy`/`pytest` já instalados.
- **Compose direto:** `make docker-up` sobe `app` (e `postgres` se habilitado no `init-project`); `make docker-shell` entra no container.
- **Host nativo:** `make setup` + `make run` direto no host (sem Docker).

`docker-compose.yml` traz `postgres` e `redis` comentados por default. `scripts/init-project.py` descomenta `postgres` automaticamente quando o projeto escolhe `banco=postgres`; `redis` é descomentado manualmente quando precisar.

#### Pré-requisito: daemon do Docker no ar (host Windows)

Sem daemon, `Dev Containers: Reopen/Rebuild in Container` falha **sem erro claro** (parece que "não carrega"). Se o Docker Desktop estiver com *"Start Docker Desktop when you sign in"* desligado, ele não volta sozinho após reboot:

```powershell
.\scripts\docker-start.ps1        # sobe o Docker Desktop e espera o daemon (idempotente)
.\scripts\docker-start.ps1 -Up    # + docker compose up -d
```

Rode no terminal do **host** — dentro do devcontainer não existe daemon de onde chamar (ovo e galinha). A correção definitiva é ligar o autostart nas settings do Docker Desktop; o script é rede de segurança.

`docker-compose.override.yml` (camada de dev, versionada) monta `~/.claude` do host em `/root/.claude` (reusa login e histórico de sessões do Claude) e força `WATCHFILES_FORCE_POLLING=true` — inotify não propaga em bind mount no Windows/WSL2, e sem polling o reloader do uvicorn morre e derruba o container.

---

## Notas para o Agente

1. **Não crie arquivos** fora das convenções do docs/LAYOUT.md sem justificativa explícita.
2. **Não importe** de camadas proibidas — mypy e o script `scripts/check_layout.py` vão pegar.
3. **Sempre escreva testes** junto com o código — unit para domínio/application, integration para adapters.
4. **O diretório `in/`** é uma keyword Python. Use importlib ou injete via FastAPI Depends. Veja docs/LAYOUT.md §8.
5. **Composition root** (`composition_root.py`) é o único lugar onde instâncias concretas são criadas.
6. **Use cases** recebem e retornam DTOs — nunca entidades de domínio para fora da camada application.
