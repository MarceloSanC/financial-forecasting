# syntax=docker/dockerfile:1.7

# Multi-stage Dockerfile do template whaka-dev-project-template.
#
# Stages:
#   - `builder` (default em dev): contem build tools + dev deps (ruff, mypy,
#     pytest) + tooling de devcontainer (git, make, curl). Usado pelo
#     .devcontainer/devcontainer.json e pelo CI.
#   - `runtime` (deploy): imagem slim sem build tools nem dev deps. Apenas
#     libpq5 (cliente postgres) + venv com deps de producao.
#
# Build manual:
#   docker build --target builder -t <projeto>:dev .   # devcontainer/CI
#   docker build --target runtime -t <projeto>:prod .  # deploy
#
# Por padrao o docker-compose.yml usa `target: builder` (dev). Em deploy real
# substitua para `runtime` ou faca o build direto da stage.

# =============================================================================
# Base comum: python slim + libpq5 + uv
# =============================================================================
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

# libpq5 (cliente postgres compilado) — precisa em runtime tambem para
# psycopg/asyncpg falarem com Postgres.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# uv: gerenciador de pacotes oficial deste template (ver CLAUDE.md).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# =============================================================================
# Stage builder — devcontainer e CI
# =============================================================================
FROM base AS builder

# Build deps (compiladores para wheels nativas) + tooling de devcontainer.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        bash-completion \
        curl \
        git \
        make \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI (gh) — repo oficial do GitHub. curl/git ja vem do bloco acima.
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Completion de shell: o bloco padrao do Debian em /etc/bash.bashrc vem
# comentado, entao instalar o pacote nao basta — o source precisa ser explicito.
# Habilita `git br<TAB>` -> `git branch` (e make, apt, docker, ssh). O `gh` nao
# instala arquivo de completion; gera o dele em runtime.
RUN printf '%s\n' \
        '[ -f /usr/share/bash-completion/bash_completion ] && . /usr/share/bash-completion/bash_completion' \
        'command -v gh >/dev/null && eval "$(gh completion -s bash)"' \
        >> /root/.bashrc

# Cache de deps: copia pyproject + src antes do resto do codigo. Quando
# arquivos fora desses caminhos mudam (tests, docs, scripts), o install de
# deps reusa o layer cacheado.
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
# `uv sync` (interface de PROJETO) e nao `uv pip install`: e o que honra
# [tool.uv.sources], que resolve o torch do indice CPU (ADR 5.4.0003). Com
# `uv pip install` a imagem baixaria a variante CUDA do PyPI. `--locked` exige
# que o uv.lock esteja em dia com o pyproject — daí o COPY do lock acima.
RUN uv sync --locked --extra dev

# Resto do codigo. No devcontainer, docker-compose substitui /app via bind
# mount do host, entao o COPY aqui so importa para CI ou execucoes isoladas.
COPY . .

EXPOSE 8000
CMD ["uvicorn", "financial_forecasting.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# =============================================================================
# Stage runtime — deploy (sem dev deps, sem build tools)
# =============================================================================
FROM base AS runtime

# Usuario nao-root para reduzir blast radius em caso de invasao do container.
RUN groupadd --system app && \
    useradd --system --gid app --no-create-home --shell /bin/bash app

# Install prod-only (sem [dev]) em venv proprio do runtime. Nao reusa o venv
# do builder para garantir que ruff/mypy/pytest nao vazem para producao.
COPY --chown=app:app pyproject.toml uv.lock README.md ./
COPY --chown=app:app src/ ./src/
# Mesmo motivo do builder: `uv sync` honra o indice CPU do torch. `--no-dev`
# mantem ruff/mypy/pytest fora de producao; `--no-editable` reproduz o install
# nao-editavel que o `uv pip install .` fazia aqui.
RUN uv sync --locked --no-dev --no-editable

USER app

EXPOSE 8000
CMD ["uvicorn", "financial_forecasting.main:app", "--host", "0.0.0.0", "--port", "8000"]
