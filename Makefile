# =============================================================================
# Makefile — Financial Forecasting
# =============================================================================
# Uso: make <target>
# Requer: uv instalado (https://docs.astral.sh/uv/)

.DEFAULT_GOAL := help
.PHONY: help setup install run migrate check check-task check-block lint fmt typecheck layout-check lint-imports fake-parity port-coverage arch-ast docs-check test test-fast test-cov clean worktree docker-build docker-build-prod docker-up docker-down docker-run docker-shell

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
	@printf "%b\n" "  $(GREEN)make check$(RESET)      Lint + typecheck + layout + import-linter + docs + testes c/ cobertura ≥90% (gate completo — 1–3 pontos do plano de gates da Stage e CI)"
	@printf "%b\n" "  $(GREEN)make check-task SLICE=<s>$(RESET) Gates estáticos + testes do slice, sem cobertura/slow (opcional)"
	@printf "%b\n" "  $(GREEN)make check-block$(RESET) Gates estáticos + docs + suíte inteira paralela, sem cobertura (opcional; conta no orçamento)"
	@printf "%b\n" "  $(GREEN)make lint$(RESET)       Roda ruff check (apenas reporta)"
	@printf "%b\n" "  $(GREEN)make fmt$(RESET)        Formata o código com ruff format + ruff check --fix"
	@printf "%b\n" "  $(GREEN)make typecheck$(RESET)  Roda mypy strict"
	@printf "%b\n" "  $(GREEN)make layout-check$(RESET) Valida regras de dependência via scripts/check_layout.py"
	@printf "%b\n" "  $(GREEN)make lint-imports$(RESET) Valida contratos de arquitetura (import-linter / .importlinter)"
	@printf "%b\n" "  $(GREEN)make fake-parity$(RESET)  Reprova lógica idêntica fake<->adapter (scripts/check_fake_parity.py)"
	@printf "%b\n" "  $(GREEN)make port-coverage$(RESET) Exige fake + contract test [fake, real] por port-out (scripts/check_port_coverage.py)"
	@printf "%b\n" "  $(GREEN)make arch-ast$(RESET)    Gates AST: colaborador de use case, determinismo do domínio, literais de schema e VOs (issue #61)"
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
check: lint typecheck layout-check lint-imports fake-parity port-coverage arch-ast docs-check test

# ---------------------------------------------------------------------------
# Gates em camadas (ADR 0.0.0055 emendada pela 0.0.0059 / issues #110, #185).
# `check` acima segue sendo o gate completo: roda nos 1–3 pontos do plano de
# gates da Stage (saída incluída) e no CI. Por Task roda só o pytest dos testes
# da Task. Os alvos abaixo são ferramentas OPCIONAIS, não etapa de rotina —
# e NÃO substituem `check` antes do PR.
#
# PYTEST_PAR: `--dist loadgroup` + os grupos do tests/conftest.py = um arquivo
# por worker (fixtures module-scoped, ex.: o treino real do TFT, rodam uma vez)
# e tests/architecture/ inteiro num worker só (injetam módulos na árvore real).
# ---------------------------------------------------------------------------
PYTEST_PAR := -n auto --dist loadgroup
STATIC_GATES := lint typecheck layout-check lint-imports fake-parity port-coverage arch-ast

# check-task (opcional, com motivo concreto) — gates estáticos + testes SÓ dos
# slices tocados, sem cobertura e sem `slow`. Uso:
#     make check-task SLICE=modeling
#     make check-task SLICE="modeling shared"
# SLICE aceita os slices de features/ e também `shared` e `tooling`.
# tests/architecture/ fica FORA: testa os próprios gates (que já rodam aqui como
# STATIC_GATES) e custa minutos por reconstruir o grafo de imports sem cache.
# Mexer em .importlinter/scripts de gate pede um ponto de `make check` no plano
# de gates (RUNBOOK §Gates em camadas). O guard de SLICE roda ANTES dos gates (sub-make), para falhar em 0 s.
check-task:
	@if [ -z "$(SLICE)" ]; then \
		printf "%b\n" "$(YELLOW)Uso: make check-task SLICE=<slice> [SLICE=\"a b\"]$(RESET)"; exit 2; \
	fi
	@$(MAKE) --no-print-directory $(STATIC_GATES)
	@paths=""; \
	for s in $(SLICE); do \
		case "$$s" in shared|tooling) base="$$s" ;; *) base="features/$$s" ;; esac; \
		found=0; \
		for kind in unit contract integration e2e; do \
			if [ -d "tests/$$kind/$$base" ]; then paths="$$paths tests/$$kind/$$base"; found=1; fi; \
		done; \
		if [ "$$found" = 0 ]; then printf "%b\n" "$(YELLOW)Slice sem testes: $$s$(RESET)"; exit 2; fi; \
	done; \
	echo "uv run pytest $$paths $(PYTEST_PAR) -q -m 'not slow'"; \
	uv run pytest $$paths $(PYTEST_PAR) -q -m "not slow"

# check-block (opcional) — todos os gates estáticos + docs-check + suíte INTEIRA
# (inclui `slow`) em paralelo, sem cobertura. Custa quase o mesmo que `check` e
# conta no orçamento de 1–3 gates completos por Stage.
check-block: $(STATIC_GATES) docs-check
	uv run pytest tests/ $(PYTEST_PAR) -q

# ---------------------------------------------------------------------------
# lint — verifica estilo e regras sem modificar arquivos
# ---------------------------------------------------------------------------
lint:
	uv run ruff check src/ tests/ scripts/ .claude/hooks/

# ---------------------------------------------------------------------------
# fmt — formata e corrige automaticamente o que for possível
# ---------------------------------------------------------------------------
fmt:
	uv run ruff format src/ tests/ scripts/ .claude/hooks/
	uv run ruff check --fix src/ tests/ scripts/ .claude/hooks/

# ---------------------------------------------------------------------------
# typecheck — checagem estática de tipos
# ---------------------------------------------------------------------------
# Alvos em `[tool.mypy] files` do pyproject (fonte única: src + tests/contract +
# tests/fakes, issue #204). O hook do pre-commit roda este mesmo `uv run mypy`
# (hook `local`, issue #222): mesma versão, mesmos alvos.
typecheck:
	uv run mypy

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
# fake-parity / port-coverage — fitness functions da REDE DE SEGURANÇA (issue #62,
# onda 3). `fake-parity` reprova bloco de lógica idêntico >= 15 linhas entre um fake
# de tests/fakes/** e um adapter (a suíte [fake, real] rodando duas cópias da mesma
# regra); `port-coverage` reprova port-out sem fake ou sem contract test [fake, real].
# Baseline declarado em scripts/arch_baseline.toml (motivo + issue obrigatórios;
# entrada morta reprova). Exit != 0 => `make check`/CI vermelhos.
# ---------------------------------------------------------------------------
fake-parity:
	uv run python scripts/check_fake_parity.py

port-coverage:
	uv run python scripts/check_port_coverage.py

# ---------------------------------------------------------------------------
# arch-ast — fitness functions da onda 2 (issue #61): regras que o import-linter
# não expressa, porque olham chamada, anotação, literal e construção, não import.
# `check_use_case_deps` reprova colaborador de use case que seja use case de outro
# slice ou adapter concreto; `check_domain_determinism` reprova relógio, acaso
# global, ambiente e I/O sob */domain/; `check_schema_literals` reprova as
# coordenadas do dataset TFT redeclaradas no modeling; `check_vo_invariants`
# reprova VO congelado sem __post_init__. Mesmo baseline declarado
# (scripts/arch_baseline.toml). Exit != 0 => `make check`/CI vermelhos.
# ---------------------------------------------------------------------------
arch-ast:
	uv run python scripts/check_use_case_deps.py
	uv run python scripts/check_domain_determinism.py
	uv run python scripts/check_schema_literals.py
	uv run python scripts/check_vo_invariants.py

# ---------------------------------------------------------------------------
# docs-check — valida (1) que technical.md `done` só mudou dentro da §7
# post-execution desde o gate da Fase 3B (CONVENTIONS §3.4), (2) que
# toda Stage tem issue correspondente no backlog do GitHub (CONVENTIONS
# §3 + GIT-WORKFLOW.md §Princípios fundamentais #1; best-effort — pula se
# `gh` não está autenticado), (3) que todo ADR declara um
# `bounded_context` do conjunto do roadmap (CONVENTIONS §2), (3b) que
# nenhum número de ADR se repete e o `adr_id` bate com o nome do arquivo
# (CONVENTIONS §1, issue #190), (4) que concept tocando concern transversal declara o teste da solução mais
# direta no §12 (RUNBOOK Passo 1b/5) e (5) que os docs normativos vivos
# (docs/ + templates + runbooks + os SKILL.md de .claude/skills/) não
# carregam padrões conhecidos de drift (ponteiros/frases defasadas).
# ---------------------------------------------------------------------------
docs-check:
	uv run python scripts/check_technical_postexec.py
	uv run python scripts/check_stage_issue.py
	uv run python scripts/check_adr_bounded_context.py
	uv run python scripts/check_adr_numbering.py
	uv run python scripts/check_concept_directness.py
	uv run python scripts/check_docs_pointers.py
	uv run python scripts/check_harness.py

# ---------------------------------------------------------------------------
# test — roda toda a suite de testes MEDINDO cobertura (gate ≥ 90%).
# É o alvo que `make check` (e portanto o CI) executa: o --cov aqui faz o
# fail_under=90 do pyproject DISPARAR (sem --cov o gate fica inerte — F3).
# Fonte única da verdade: o que o dev roda local == o que o CI roda (I7).
# Paralelo via xdist (ADR 0.0.0055): o pytest-cov combina a cobertura dos
# workers, então o fail_under=90 continua valendo sobre a suíte inteira.
# ---------------------------------------------------------------------------
test:
	uv run pytest tests/ $(PYTEST_PAR) -v --cov=src/financial_forecasting --cov-report=term-missing

# ---------------------------------------------------------------------------
# test-fast — pula testes slow e NÃO mede cobertura (loop local rápido).
# Não dispara o gate de cobertura; use `make test`/`make check` para o gate.
# ---------------------------------------------------------------------------
test-fast:
	uv run pytest tests/ $(PYTEST_PAR) -q -m "not slow"

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
