# Financial Forecasting

> Calibração probabilística de previsões de retorno com TFT (piloto AAPL)

---

## Documentação

| Documento | Descrição |
|-----------|-----------|
| [docs/LAYOUT.md](docs/LAYOUT.md) | Convenções de arquitetura — leia antes de codar |
| [docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md) | Fluxo de versionamento e CI/CD |
| [docs/PIPELINE.md](docs/PIPELINE.md) | Pipeline conceitual (Step → Stage → Task, fases, gates) |
| [docs/CONVENTIONS.md](docs/CONVENTIONS.md) | Convenções de frontmatter, branches, commits, versionamento |
| [CLAUDE.md](CLAUDE.md) | Contexto para agentes de IA |
| [docs/](docs/) | Documentação técnica (LAYOUT, GIT-WORKFLOW, PIPELINE, CONVENTIONS, runbook de Stage, ADRs) |

---

## Setup local

Três caminhos suportados: **devcontainer (recomendado)** via VS Code, **Docker Compose direto** (sem IDE), ou **host nativo** (Python local sem Docker).

### Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) + [Docker Compose v2.24+](https://docs.docker.com/compose/install/) — necessário para o devcontainer e para `make docker-*`
- (se for rodar direto no host) Python 3.12+ + [uv](https://docs.astral.sh/uv/) + `make` (GNU Make) + ambiente POSIX (Linux, macOS, ou WSL no Windows)

### Caminho A — Devcontainer (VS Code dentro do container)

Pré-requisito extra: extensão **Dev Containers** do VS Code.

1. Abra a pasta do projeto no VS Code.
2. `Ctrl+Shift+P` → `Dev Containers: Reopen in Container`.
3. VS Code sobe o `docker-compose.yml`, abre o IDE dentro da stage `builder` do Dockerfile (com `uv`, `ruff`, `mypy`, `pytest` já instalados) e roda `make setup` automaticamente via `postCreateCommand`.
4. Use o terminal integrado para os comandos abaixo (`make check`, `make run`, etc.).

### Caminho B — Docker Compose direto (sem devcontainer)

```bash
make docker-build            # builda a stage `builder` com toolchain de dev
make docker-up               # sobe `app` (e `postgres` se o init-project habilitou)
make docker-shell            # bash dentro do container, para rodar `make check`, `make test`
make docker-down             # derruba a stack
```

### Caminho C — Host nativo (sem Docker)

```bash
git clone <repo-url>
cd Financial Forecasting

make setup                    # cria .venv via uv e instala deps
cp .env.example .env          # ajuste credenciais locais
make migrate                  # alembic upgrade head
make check                    # lint + typecheck + testes
```

---

## Comandos principais

| Comando | O que faz |
|---------|-----------|
| `make setup` | Cria `.venv` e instala dependências com `uv` |
| `make install` | Reinstala dependências (após mudança no `pyproject.toml`) |
| `make run` | Sobe o servidor de desenvolvimento com hot-reload |
| `make migrate` | Aplica migrations pendentes (`alembic upgrade head`) |
| `make check` | Roda lint + typecheck (falha o CI se houver erros) |
| `make lint` | Roda `ruff check` — apenas reporta |
| `make fmt` | Roda `ruff format` + `ruff check --fix` |
| `make typecheck` | Roda `mypy` |
| `make test` | Roda todos os testes |
| `make test-cov` | Testes com relatório de cobertura em HTML |
| `make clean` | Remove artefatos de build, cache e `.venv` |
| `make docker-build` | Builda a stage `builder` (devcontainer/CI) — tag `:dev` |
| `make docker-build-prod` | Builda a stage `runtime` (deploy) — tag `:prod` |
| `make docker-up` | Sobe a stack do `docker-compose.yml` em background |
| `make docker-down` | Derruba a stack do `docker-compose.yml` |
| `make docker-run` | Sobe a app em foreground (logs no terminal) |
| `make docker-shell` | Abre bash dentro do container `app` |

---

## Estrutura do código

```
src/financial_forecasting/
├── main.py                  # Entrypoint: inicia uvicorn
├── composition_root.py      # Único lugar que instancia dependências concretas
├── features/                # Vertical slices — um diretório por bounded context (vazio no template)
│   └── <feature>/           # Cada feature do seu projeto (ex.: payments, inventory)
│       ├── domain/          # Entidades, value objects, serviços de domínio, exceções
│       │   ├── entities/
│       │   ├── value_objects/
│       │   ├── services/
│       │   └── exceptions/
│       ├── application/     # Use cases, DTOs, ports (interfaces)
│       │   ├── use_cases/
│       │   ├── dtos/
│       │   └── ports/
│       │       ├── in/      # Ports primários (driving) — atenção: 'in' é keyword Python
│       │       └── out/     # Ports secundários (driven)
│       └── adapters/        # Implementações concretas dos ports
│           ├── in/
│           │   └── http/    # Router FastAPI
│           └── out/
│               └── postgres/ # Repositório SQLAlchemy
└── shared/                  # Preocupações transversais reutilizáveis
    ├── domain/              # Exceções base, value objects genéricos
    ├── application/         # Ports compartilhados (Clock, IdGenerator)
    └── infrastructure/      # Implementações de infraestrutura (DB, HTTP, config, logging)
```

---

## Convenções

- **Arquitetura:** Vertical slices + Ports & Adapters. Veja [docs/LAYOUT.md](docs/LAYOUT.md).
- **Branches:** `feat/<num-issue>-<N-M>-<slug>`, `fix/<num-issue>-<N-M>-<slug>`, `docs/<desc>` — `N.M` é o id da Stage (ver `docs/GIT-WORKFLOW.md` e `docs/CONVENTIONS.md` §4)
- **Commits:** Conventional Commits — `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- **Testes:** Cada camada tem sua suite — `unit/`, `integration/`, `contract/`, `e2e/`
- **Imports:** Sempre absolutos. Nunca importe de `infrastructure` dentro de `domain`.

---

## CI

O pipeline de CI roda, nesta ordem:

1. `make lint` — falha em qualquer violação de estilo
2. `make typecheck` — falha em qualquer erro de tipo
3. `make test` com `-m "not slow"` — roda unit + integration, pula lentos
4. Upload do relatório de cobertura

Para rodar localmente o mesmo check do CI:

```bash
make check && make test
```
