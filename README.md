# Financial Forecasting

> Calibração probabilística de previsões de retorno com TFT (piloto AAPL)

![CI](https://github.com/MarceloSanC/financial-forecasting/actions/workflows/ci.yml/badge.svg)

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

## Decisões de fundação

Quatro decisões científico-arquiteturais foram fixadas no bootstrap (Stage 1.1) e são consumidas por todas as Stages seguintes. Cada uma vive como ADR `accepted` em [docs/adr/](docs/adr/):

| ADR | Decisão |
|-----|---------|
| [0.0.0002](docs/adr/0_0_0002-probabilistic-calibration-framing.md) | Enquadramento = calibração probabilística (distribuição preditiva + contribuição de features), nunca acurácia pontual do retorno médio. |
| [0.0.0019](docs/adr/0_0_0019-hexagonal-enforced.md) | Fronteiras hexagonais enforçadas por ferramenta que quebra o build (`scripts/check_layout.py` desde a 1.1), não por code review. |
| [0.0.0020](docs/adr/0_0_0020-statistics-in-domain-over-value-objects.md) | Estatística confirmatória como serviços de domínio puros sobre value objects; bibliotecas numéricas atrás de ports, em adapters. |
| [0.0.0021](docs/adr/0_0_0021-per-unit-contract-tests-with-oracle.md) | Correção verificada por unidade contra oráculo (fixture analítica + lib/R), nunca snapshot global byte-idêntico. |

> O excedente herdado do template (infra web/DB, composition root, ports stub) é mantido como débito declarado — ver [ADR 1.1.0001](docs/adr/1_1_0001-template-surplus-handling.md).

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
make check                    # gate completo: lint + typecheck + layout + docs + testes c/ cobertura ≥90%
```

---

## Comandos principais

| Comando | O que faz |
|---------|-----------|
| `make setup` | Cria `.venv` e instala dependências com `uv` |
| `make install` | Reinstala dependências (após mudança no `pyproject.toml`) |
| `make run` | Sobe o servidor de desenvolvimento com hot-reload |
| `make migrate` | Aplica migrations pendentes (`alembic upgrade head`) |
| `make check` | Gate completo — lint + typecheck + layout-check + docs-check + testes com cobertura ≥ 90% (falha o CI se qualquer um falhar) |
| `make lint` | Roda `ruff check` — apenas reporta |
| `make fmt` | Roda `ruff format` + `ruff check --fix` |
| `make typecheck` | Roda `mypy --strict` |
| `make test` | Roda todos os testes medindo cobertura (gate ≥ 90%) |
| `make test-fast` | Roda testes sem cobertura, pulando os `slow` (loop local rápido) |
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

## CI e gate de qualidade

O CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) roda um **único job de gate**
(`lint-and-test`) que executa `make check` em todo push para `main`/`develop` e em todo Pull
Request. **Um PR reprova (CI vermelho) se violar qualquer uma destas cinco fronteiras:**

| # | Fronteira | Ferramenta (passo de `make check`) |
|---|-----------|------------------------------------|
| 1 | Estilo / lint | `ruff check` (`make lint`) |
| 2 | Tipos | `mypy --strict` (`make typecheck`) |
| 3 | Direção de dependência hexagonal | `scripts/check_layout.py` (`make layout-check`) |
| 4 | Suíte de testes | `pytest` (`make test`) |
| 5 | Cobertura **< 90%** | `pytest --cov` + `fail_under=90` no `pyproject.toml` (`make test`) |

> **CI verde ⟹ todas as fronteiras seguraram.** O gate de cobertura mede apenas **código vivo e em
> escopo**: wiring/DI, entrypoint (`__main__`) e infra herdada do template ainda sem consumidor ficam
> em `omit` (lista auditável no `pyproject.toml`); `adapters/*` **nunca** é omitido (têm contract test
> e devem contar). Um job ortogonal `guard-main-source` garante que PRs para `main` só venham de
> `develop`/`hotfix/*`.

Para rodar **localmente o mesmo veredito do CI** (sem drift — é o mesmo comando):

```bash
make check
```

> **Nota — contratos de import:** a direção de dependência já é gateada por
> `scripts/check_layout.py`. Os **contratos `import-linter` formais** (`.importlinter`,
> `tests/architecture/`) chegam na **Stage 1.3** (`1.3-architecture-contracts`); nesta Stage (1.2) o
> "contrato de import" é o `check_layout.py`.
