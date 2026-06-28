# CLAUDE.md — Contexto para Agentes de IA

Este arquivo fornece contexto essencial para que agentes de IA (Claude Code, Copilot, etc.)
entendam o projeto antes de fazer qualquer mudança. Leia-o inteiro antes de codar.

---

## Visão Geral do Projeto

**Financial Forecasting** — Calibração probabilística de previsões de retorno com TFT (piloto AAPL)

Pipeline de previsão probabilística de retornos diários com TFT quantílico, em arquitetura hexagonal e medalhão (bronze/silver/gold). Avaliação estatística confirmatória (pinball, DM/MCS/Holm, calibração e conformal) como serviços de domínio apoiados em bibliotecas validadas contra oráculo; piloto AAPL, multi-asset-ready.

---

## Stack Técnica

| Camada | Tecnologia |
|--------|-----------|
| Framework HTTP | FastAPI 0.111+ |
| Servidor ASGI | Uvicorn |
| ORM / banco | SQLAlchemy 2.0+ (Core, sem ORM declarativo) |
| Migrations | Alembic |
| Validação | Pydantic v2 |
| Configuração | pydantic-settings |
| Python | 3.12 |
| Gerenciador de pacotes | uv |
| Linter/Formatter | Ruff |
| Checagem de tipos | mypy strict |
| Testes | pytest + pytest-asyncio + httpx |

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

- **Sprint/milestone atual:** _preencher_
- **Funcionalidades em desenvolvimento:** _preencher_
- **Débitos técnicos conhecidos:** _preencher_
- **Decisões arquiteturais recentes (ADRs):** veja `docs/adr/`

---

## Convenções de Git

Fonte da verdade: [docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md). Resumo do essencial:

- **Branches:** `feat/<num-issue>-<N-M>-<slug>`, `fix/...`, `refactor/...`, `docs/<desc>`. Saem de `develop` (hotfix sai de `main`). **Slug em inglês** (kebab-case ASCII; entra em URLs/tabs). Formato e regras completas: [docs/CONVENTIONS.md](docs/CONVENTIONS.md) §4.
- **Commits:** Conventional Commits **em português** com **escopo mínimo obrigatório** (`<tipo>(<escopo>): <descrição>`) — escopo em ASCII/kebab, descrição em PT acentuado. Body em bullet points. `Refs #<num-issue>` no rodapé. 1 commit = 1 mudança lógica em **um** escopo. Hook `commit-msg` valida o subject (`make setup` instala). Detalhes em [docs/CONVENTIONS.md](docs/CONVENTIONS.md) §4.
- **Branches em paralelo:** uma branch em voo por vez. Não abrir branch nova enquanto a anterior não tem PR aberto. Procedimento de PR parcial (draft) só quando o usuário pedir explicitamente — ver [docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md) §"Uma branch em voo por vez".
- **PRs e issues:** título e corpo em **português**, no formato do commit; PRs contra `develop`. **Gates de PR (CI verde, coverage, aprovações, merge commit):** fonte única em [docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md) §Gates.
- **Idioma:** PT em commits, títulos de issue/PR, corpos de issue/PR e code review. **EN em nomes de branch** e identificadores de código (escopo do commit também ASCII). Docs em `docs/` em PT.
- **Antes de `git push`:** rodar `git log origin/<base>..HEAD` (`<base>` = branch de origem, normalmente `develop`); se houver commits de outros escopos pegando carona, rebasear em `origin/<base>` antes de abrir PR. Ver [docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md) §Etapa 4.

Detalhes operacionais (setup inicial, branch protection, release, hotfix, code review): ver [docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md).

---

## Comandos Úteis

```bash
make setup      # configura o ambiente pela primeira vez
make run        # sobe o servidor local com hot-reload
make migrate    # aplica migrations pendentes
make check      # lint + typecheck (bloqueante)
make fmt        # formata o código automaticamente
make test       # roda todos os testes
make test-cov   # testes com relatório de cobertura HTML
make clean      # limpa artefatos de build e cache
```

### Docker / devcontainer

O projeto vem com Docker desde o dia 1 (`Dockerfile` multi-stage + `docker-compose.yml`). Há três caminhos para desenvolver:

- **Devcontainer (recomendado):** VS Code → `Dev Containers: Reopen in Container`. Sobe a stage `builder` do `Dockerfile` via `docker-compose.yml`, com `uv`/`ruff`/`mypy`/`pytest` já instalados.
- **Compose direto:** `make docker-up` sobe `app` (e `postgres` se habilitado no `init-project`); `make docker-shell` entra no container.
- **Host nativo:** `make setup` + `make run` direto no host (sem Docker).

```bash
make docker-build       # builda a stage `builder` (dev/CI) — tag :dev
make docker-build-prod  # builda a stage `runtime` (deploy) — tag :prod
make docker-up          # sobe a stack em background
make docker-down        # derruba a stack
make docker-shell       # bash dentro do container app
```

`docker-compose.yml` traz `postgres` e `redis` comentados por default. `scripts/init-project.py` descomenta `postgres` automaticamente quando o projeto escolhe `banco=postgres`; `redis` é descomentado manualmente quando precisar.

---

## Notas para o Agente

1. **Não crie arquivos** fora das convenções do docs/LAYOUT.md sem justificativa explícita.
2. **Não importe** de camadas proibidas — mypy e o script `scripts/check_layout.py` vão pegar.
3. **Sempre escreva testes** junto com o código — unit para domínio/application, integration para adapters.
4. **O diretório `in/`** é uma keyword Python. Use importlib ou injete via FastAPI Depends. Veja docs/LAYOUT.md §8.
5. **Composition root** (`composition_root.py`) é o único lugar onde instâncias concretas são criadas.
6. **Use cases** recebem e retornam DTOs — nunca entidades de domínio para fora da camada application.
