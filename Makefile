# =============================================================================
# Makefile — Financial Forecasting
# =============================================================================
# Uso: make <target>
# Requer: uv instalado (https://docs.astral.sh/uv/)

.DEFAULT_GOAL := help
.PHONY: help setup install run migrate check lint fmt typecheck layout-check lint-imports docs-check test test-fast test-cov clean worktree docker-build docker-build-prod docker-up docker-down docker-run docker-shell

# Tag das imagens Docker. Mesmo nome usado em docker-compose.yml `image:` para
# reusar o cache de layer (`make docker-build` e `make docker-up` produzem a
# mesma imagem). `init-project.py` substitui `financial_forecasting` pelo nome do pacote
# escolhido, resultando em `<pkg>-app`.
DOCKER_IMAGE := financial_forecasting-app

# Cor para output legível
BOLD  := \033[1m
RESET := \033[0m
GREEN := \033[32m
YELLOW := \033[33m

# ---------------------------------------------------------------------------
# help — lista todos os targets disponíveis
# ---------------------------------------------------------------------------
help:
	@printf "%b\n" ""
	@printf "%b\n" "$(BOLD)Financial Forecasting — comandos disponíveis$(RESET)"
	@printf "%b\n" ""
	@printf "%b\n" "  $(GREEN)make setup$(RESET)      Cria .venv e instala todas as dependências"
	@printf "%b\n" "  $(GREEN)make install$(RESET)    Reinstala dependências (após mudar pyproject.toml)"
	@printf "%b\n" "  $(GREEN)make run$(RESET)        Sobe o servidor de desenvolvimento com hot-reload"
	@printf "%b\n" "  $(GREEN)make migrate$(RESET)    Aplica migrations pendentes (alembic upgrade head)"
	@printf "%b\n" "  $(GREEN)make check$(RESET)      Lint + typecheck + layout + import-linter + docs + testes c/ cobertura ≥90% (gate completo — usado no CI)"
	@printf "%b\n" "  $(GREEN)make lint$(RESET)       Roda ruff check (apenas reporta)"
	@printf "%b\n" "  $(GREEN)make fmt$(RESET)        Formata o código com ruff format + ruff check --fix"
	@printf "%b\n" "  $(GREEN)make typecheck$(RESET)  Roda mypy strict"
	@printf "%b\n" "  $(GREEN)make layout-check$(RESET) Valida regras de dependência via scripts/check_layout.py"
	@printf "%b\n" "  $(GREEN)make lint-imports$(RESET) Valida contratos de arquitetura (import-linter / .importlinter)"
	@printf "%b\n" "  $(GREEN)make docs-check$(RESET)  Valida §7 post-exec dos technical.md (CONVENTIONS §3.4)"
	@printf "%b\n" "  $(GREEN)make test$(RESET)       Roda todos os testes medindo cobertura (gate ≥ 90%)"
	@printf "%b\n" "  $(GREEN)make test-fast$(RESET)  Roda testes sem cobertura, pulando os slow (loop local rápido)"
	@printf "%b\n" "  $(GREEN)make test-cov$(RESET)   Testes com relatório de cobertura HTML + gate ≥ 90%"
	@printf "%b\n" "  $(GREEN)make clean$(RESET)      Remove artefatos de build, cache e .venv"
	@printf "%b\n" ""
	@printf "%b\n" "  $(GREEN)make worktree BRANCH=<n>$(RESET)  Cria worktree em ../<repo>-worktrees/<branch>, instala deps e abre VS Code"
	@printf "%b\n" "                              (extras: BASE=<base> ARGS='--no-setup --no-vscode ...')"
	@printf "%b\n" ""
	@printf "%b\n" "  $(GREEN)make docker-build$(RESET)      Builda a stage 'builder' (devcontainer/CI) — tag :dev"
	@printf "%b\n" "  $(GREEN)make docker-build-prod$(RESET) Builda a stage 'runtime' (deploy) — tag :prod"
	@printf "%b\n" "  $(GREEN)make docker-up$(RESET)         Sobe a stack (app + serviços ativos no compose) em background"
	@printf "%b\n" "  $(GREEN)make docker-down$(RESET)       Derruba a stack do docker-compose"
	@printf "%b\n" "  $(GREEN)make docker-run$(RESET)        Sobe a app em foreground (logs no terminal)"
	@printf "%b\n" "  $(GREEN)make docker-shell$(RESET)      Abre bash dentro do container app"
	@printf "%b\n" ""

# ---------------------------------------------------------------------------
# setup — primeira vez: cria o ambiente e instala tudo
# ---------------------------------------------------------------------------
setup:
	uv sync --locked --extra dev
	@if [ -f .pre-commit-config.yaml ]; then \
		uv run pre-commit install --install-hooks --hook-type pre-commit --hook-type commit-msg ; \
		printf "%b\n" "  Pre-commit + commit-msg hooks instalados (ver .pre-commit-config.yaml)" ; \
	else \
		printf "%b\n" "  .pre-commit-config.yaml ausente — hooks NÃO instalados (opt-out no init)." ; \
	fi
	@printf "%b\n" ""
	@printf "%b\n" "$(GREEN)✓ Ambiente pronto!$(RESET) Ative com: source .venv/bin/activate"
	@printf "%b\n" "  Copie e ajuste as variáveis: cp .env.example .env"

# ---------------------------------------------------------------------------
# install — atualiza dependências sem recriar o venv
#
# SEM `--locked` de propósito: este é o alvo de "mudei o pyproject.toml", e
# `--locked` falharia exatamente nesse caso. Ele re-resolve e ATUALIZA o
# `uv.lock` — que entra no commit junto com a mudança do pyproject. O
# `--locked` fica em `setup`, no Dockerfile, no devcontainer e no CI, onde o
# objetivo é reproduzir o conjunto revisado, não mudá-lo.
# ---------------------------------------------------------------------------
install:
	uv sync --extra dev

# ---------------------------------------------------------------------------
# run — servidor de desenvolvimento
# ---------------------------------------------------------------------------
run:
	uv run uvicorn financial_forecasting.main:app --reload --host 0.0.0.0 --port 8000

# ---------------------------------------------------------------------------
# migrate — aplica todas as migrations pendentes
# ---------------------------------------------------------------------------
migrate:
	uv run alembic upgrade head

# ---------------------------------------------------------------------------
# check — gate completo (bloqueante no CI): lint + typecheck + layout-check +
# lint-imports + docs-check + test (com cobertura ≥ 90% via --cov no alvo
# `test`). É a fonte única da verdade do veredito: o que o dev roda local == o
# que o CI roda (I7). `lint-imports` roda antes de `test` para falhar cedo e
# barato (Stage 1.3): viola a fronteira hexagonal => build vermelho.
# ---------------------------------------------------------------------------
check: lint typecheck layout-check lint-imports docs-check test

# ---------------------------------------------------------------------------
# lint — verifica estilo e regras sem modificar arquivos
# ---------------------------------------------------------------------------
lint:
	uv run ruff check src/ tests/ scripts/

# ---------------------------------------------------------------------------
# fmt — formata e corrige automaticamente o que for possível
# ---------------------------------------------------------------------------
fmt:
	uv run ruff format src/ tests/ scripts/
	uv run ruff check --fix src/ tests/ scripts/

# ---------------------------------------------------------------------------
# typecheck — checagem estática de tipos
# ---------------------------------------------------------------------------
typecheck:
	uv run mypy src/

# ---------------------------------------------------------------------------
# layout-check — valida regras de dependência (docs/LAYOUT.md §3)
# ---------------------------------------------------------------------------
layout-check:
	uv run python scripts/check_layout.py

# ---------------------------------------------------------------------------
# lint-imports — fitness function de arquitetura (docs/LAYOUT.md §3/§6 via
# .importlinter). COMPLEMENTA `layout-check` (não substitui): cobre direção de
# camadas e a fronteira indireta do composition_root que o check_layout.py não
# enxerga. Exit != 0 em violação => `make check`/CI vermelhos (Stage 1.3).
# ---------------------------------------------------------------------------
lint-imports:
	uv run lint-imports

# ---------------------------------------------------------------------------
# docs-check — valida (1) que technical.md `done` só mudou dentro da §7
# post-execution desde o gate da Fase 3B (CONVENTIONS §3.4), (2) que
# toda Stage tem issue correspondente no backlog do GitHub (CONVENTIONS
# §3 + GIT-WORKFLOW.md §Princípios fundamentais #1; best-effort — pula se
# `gh` não está autenticado), (3) que todo ADR declara um
# `bounded_context` do conjunto do roadmap (CONVENTIONS §2), (4) que
# concept tocando concern transversal declara o teste da solução mais
# direta no §12 (RUNBOOK Passo 1b/5) e (5) que os docs normativos vivos
# (docs/ + templates + runbooks + os SKILL.md de .claude/skills/) não
# carregam padrões conhecidos de drift (ponteiros/frases defasadas).
# ---------------------------------------------------------------------------
docs-check:
	uv run python scripts/check_technical_postexec.py
	uv run python scripts/check_stage_issue.py
	uv run python scripts/check_adr_bounded_context.py
	uv run python scripts/check_concept_directness.py
	uv run python scripts/check_docs_pointers.py

# ---------------------------------------------------------------------------
# test — roda toda a suite de testes MEDINDO cobertura (gate ≥ 90%).
# É o alvo que `make check` (e portanto o CI) executa: o --cov aqui faz o
# fail_under=90 do pyproject DISPARAR (sem --cov o gate fica inerte — F3).
# Fonte única da verdade: o que o dev roda local == o que o CI roda (I7).
# ---------------------------------------------------------------------------
test:
	uv run pytest tests/ -v --cov=src/financial_forecasting --cov-report=term-missing

# ---------------------------------------------------------------------------
# test-fast — pula testes slow e NÃO mede cobertura (loop local rápido).
# Não dispara o gate de cobertura; use `make test`/`make check` para o gate.
# ---------------------------------------------------------------------------
test-fast:
	uv run pytest tests/ -v -m "not slow"

# ---------------------------------------------------------------------------
# test-cov — testes com relatório de cobertura em HTML (gate ≥ 90% via pyproject)
# ---------------------------------------------------------------------------
test-cov:
	uv run pytest tests/ --cov=src/financial_forecasting --cov-report=html --cov-report=term-missing
	@printf "%b\n" ""
	@printf "%b\n" "$(GREEN)Relatório gerado em: htmlcov/index.html$(RESET)"

# ---------------------------------------------------------------------------
# worktree — cria worktree git pronta pra implementação (issue → branch →
# venv → VS Code). Uso:
#     make worktree BRANCH=feat/42-add-google-login
#     make worktree BRANCH=fix/57-timeout BASE=develop
#     make worktree BRANCH=feat/42-add-google-login ARGS='--no-setup --no-vscode'
# Detalhes e flags: `python scripts/worktree-new.py --help`.
# ---------------------------------------------------------------------------
worktree:
	@if [ -z "$(BRANCH)" ]; then \
		printf "%b\n" "$(YELLOW)Uso: make worktree BRANCH=<tipo>/<num>-<slug> [BASE=develop|main] [ARGS='...']$(RESET)" ; \
		exit 1 ; \
	fi
	uv run python scripts/worktree-new.py $(BRANCH) $(if $(BASE),--base $(BASE),) $(ARGS)

# ---------------------------------------------------------------------------
# docker-build — builda a stage 'builder' (devcontainer e CI)
# ---------------------------------------------------------------------------
docker-build:
	docker build --target builder -t $(DOCKER_IMAGE):dev .

# ---------------------------------------------------------------------------
# docker-build-prod — builda a stage 'runtime' (deploy)
# ---------------------------------------------------------------------------
docker-build-prod:
	docker build --target runtime -t $(DOCKER_IMAGE):prod .

# ---------------------------------------------------------------------------
# docker-up — sobe a stack inteira em background
# ---------------------------------------------------------------------------
docker-up:
	docker compose up -d

# ---------------------------------------------------------------------------
# docker-down — derruba a stack
# ---------------------------------------------------------------------------
docker-down:
	docker compose down

# ---------------------------------------------------------------------------
# docker-run — roda a app em foreground (com logs no terminal)
# ---------------------------------------------------------------------------
docker-run:
	docker compose up app

# ---------------------------------------------------------------------------
# docker-shell — abre bash dentro do container app
# ---------------------------------------------------------------------------
docker-shell:
	docker compose exec app bash

# ---------------------------------------------------------------------------
# clean — remove artefatos gerados
# ---------------------------------------------------------------------------
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ htmlcov/ .coverage coverage.xml tree.txt
	@printf "%b\n" "$(YELLOW)Artefatos removidos.$(RESET)"
