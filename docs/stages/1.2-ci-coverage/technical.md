---
title: Technical — Stage 1.2 — CI e gate de cobertura efetivo
description: Plano de execução da Stage 1.2 — torna o gate lint+types+layout+testes+cobertura≥90% efetivo no CI e trata o excedente herdado do template
when-use: Consultar durante a Fase 4 (execução) da Stage 1.2; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, ci-coverage, fail_under, gate, fitness-function, template-surplus, omit, pragma, layout-check, github-actions]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 1.2-ci-coverage
stage_title: CI e gate de cobertura efetivo
step_id: 1
step_title: Fundação e fitness arquitetural
depends_on: [1.1-bootstrap]
concept_ref: ./concept.md
issue_id: 7
branch: feat/7-1-2-ci-coverage
tasks_count: 6
---

# Technical — Stage 1.2 — CI e gate de cobertura efetivo

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [1.2/task-NN]`.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, decidir com base concreta (esta corrida é autônoma — ver
>    `docs/adr/0_0_0050-autonomous-overnight-mode.md`), e registrar a
>    decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done) como
>    `[decision]`/`[deviation]`/`[finding]`. Nunca propagar silenciosamente.
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage),
>    fazer commit `stage 1.2: complete` e atualizar `roadmap.md`.
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/7-1-2-ci-coverage`. Não há sub-PRs internos.

## 1. Contexto e estratégia de execução

### Resumo
Esta Stage **não introduz contrato de código** (port/DTO/VO/entidade) — é infraestrutura de
CI/cobertura. Ela faz três coisas, derivadas do `concept.md` §1 e dos ADRs
[1.2.0010](../../adr/1_2_0010-cobertura-no-ci-e-tratamento-do-excedente-herdado.md) /
[1.2.0011](../../adr/1_2_0011-coverage-gate-as-foundational-fitness-function.md):
(a) faz o `fail_under=90` (já declarado no `pyproject.toml`, hoje **inerte** — F3) **efetivamente
disparar** no caminho do CI, pondo `pytest --cov` dentro de `make check`; (b) trata o excedente
herdado do template (hoje a 33.01%) por **poda + omit/exclude_lines + pragma + teste de código vivo**
até a cobertura do código em escopo ficar ≥ 90% **honestamente** (sem inflar sobre lógica de
domínio/application; `adapters/*` nunca entra em `omit`); (c) endurece o `ci.yml` (job único
`lint-and-test` rodando `make check`, `timeout-minutes`, `guard-main-source` preservado) e documenta
o contrato no `README.md`. O veredito é provado por **quebra intencional revertida** (DoD).

### Estado medido (baseline F3, verificado ao vivo)
`pytest --cov` → `FAIL Required test coverage of 90.0% not reached. Total coverage: 33.01%`. O 33% é
dominado pelo excedente herdado (wiring FastAPI, entrypoint, infra diferida), **não** por falta de
teste de domínio. Código genuinamente **vivo e em escopo** hoje: `shared/domain/exceptions/base.py`
(100%) e `shared/domain/value_objects/pagination.py` (0% — VO transversal, precisa de teste). O
restante é wiring/entrypoint/infra-não-consumida (`main.py`, `composition_root.py`,
`shared/infrastructure/{http,logging,config,clock,uuid_generator}`) ou a assunção Postgres
(`database/connection.py`) que o overview §6 declara fora (persistência é Parquet+DuckDB).

### Estratégia
**Ordem inside-out (skill `task-ordering-hex`), mas adaptada a uma Stage de infra:** primeiro a peça
que **deve** subir a cobertura honestamente (teste do VO `Pagination` — código vivo de domínio),
depois a poda do que está fora de escopo, depois a configuração de cobertura (omit/exclude restritos
a wiring), depois o cabeamento do gate no `Makefile` (que faz o `fail_under` disparar), depois o
endurecimento do `ci.yml`, e por fim a documentação. Cada Task deixa `make check` (ou o subconjunto
relevante) verde antes de avançar. A **validação por quebra intencional revertida** acontece na Task
final, com a evidência registrada na §7. Disposição por módulo (operacional, dentro da política do
ADR 1.2.0010 D2):

| Módulo herdado | Disposição | Razão |
|---|---|---|
| `shared/domain/value_objects/pagination.py` | **testar** (código vivo) | VO de domínio transversal; deve contar |
| `shared/domain/exceptions/base.py` | já 100% | código vivo de domínio |
| `shared/infrastructure/database/connection.py` (+ pacote vazio) | **podar** | assunção SQLAlchemy/Postgres; overview §6 = sem Postgres |
| `main.py`, `composition_root.py` | **omit** | entrypoint / wiring DI — `__main__`, não lógica |
| `shared/infrastructure/http/*` | **omit** | wiring FastAPI consumido só no Step de API |
| `shared/infrastructure/{logging,config}/*` | **omit** | config/boot de infra, não lógica de domínio |
| `shared/infrastructure/{clock,uuid_generator}/*` (concretos) | **omit (diferido)** | adapters de infra ainda **sem consumidor**; reentram quando uma feature os usar (então passam a contar) |
| `shared/application/ports/out/{clock,id_generator}.py` (Protocol `...`) | **exclude_lines `\.\.\.`** | corpo de stub de Protocol, não lógica |
| `*/migrations/*`, `*/scripts/*` | omit (já presente) | fora do pacote de domínio |

> Observação de honestidade (I3): o `omit` dos adapters concretos `clock`/`uuid_generator` é
> **deferido, não permanente** — são infra sem consumidor nesta Stage. Quando uma feature os injetar,
> a Stage consumidora os **remove do `omit`** e eles passam a contar (contract test). `adapters/*` de
> feature **nunca** entra em `omit` (anti-precedente do repo antigo, ADR 1.2.0010 alt. B). Esta
> disposição é registrada como `[decision]` na §7 na execução.

### Pré-condições
- Stage `1.1-bootstrap` em `done` (provê `pyproject.toml` com `fail_under=90`, `Makefile`, `ci.yml`,
  `scripts/check_layout.py`, excedente do template como dívida declarada — ADR 1.1.0001).
- Branch `feat/7-1-2-ci-coverage` em checkout (já criada).
- `uv sync --extra dev` rodado (toolchain disponível: ruff, mypy, pytest, pytest-cov).

### Premissas técnicas
- Python 3.12; `uv` como gerenciador; `pytest-cov>=5.0` já em `[project.optional-dependencies].dev`.
- `make check` já encadeia `lint → typecheck → layout-check → docs-check → test`; basta o alvo `test`
  ganhar cobertura para o gate fechar (ADR 1.2.0010 D1, I7).
- `scripts/check_layout.py` já reprova violação de direção de dependência (verificado na Stage 1.1).
- **Nenhuma** ferramenta do repo antigo (pip/black) é importada — só o **conceito** de gate (I4).
- **Não** se cria `.importlinter` nem `tests/architecture/` (é Stage 1.3 — I6, A7, ADR 1.2.0010 D3).

### Estrutura de pastas afetada

```
financial-forecasting/
├── Makefile                                   # MOD: alvo `test` ganha --cov; test-fast/test-cov mantidos
├── pyproject.toml                             # MOD: [tool.coverage] source/omit/exclude_lines
├── README.md                                  # MOD: seção CI/qualidade + badge + nota import-linter→1.3
├── .github/workflows/ci.yml                   # MOD: timeout-minutes; job único; guard-main-source intacto
├── src/financial_forecasting/
│   └── shared/infrastructure/database/        # REMOVE: connection.py (assunção Postgres) + pacote vazio
└── tests/
    └── unit/shared/domain/value_objects/
        └── test_pagination.py                 # NEW: teste do VO Pagination (código vivo de domínio)
```

## 2. Tasks

> Faixa saudável: **3–8 Tasks**. Esta Stage tem **6**.

### Task 01 — Testar o VO `Pagination` (código vivo de domínio)

- **Arquivos a criar:**
  - `tests/unit/shared/domain/value_objects/__init__.py` (e `__init__.py` intermediários que faltarem)
  - `tests/unit/shared/domain/value_objects/test_pagination.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** escrever testes unitários para `Pagination` (`shared/domain/value_objects/pagination.py`),
  o único VO de domínio vivo hoje a 0%. Cobrir: construção default; `offset = (page-1)*page_size`;
  `limit == page_size`; `__post_init__` rejeita `page < 1` (`ValueError`); rejeita `page_size < 1` e
  `> MAX_PAGE_SIZE` (`ValueError`); imutabilidade (frozen → `dataclasses.FrozenInstanceError` ao
  atribuir). Marcar com `@pytest.mark.unit`.
- **Detalhes técnicos:**
  - Importar `from financial_forecasting.shared.domain.value_objects.pagination import Pagination, MAX_PAGE_SIZE`.
  - `pagination.py` deve ficar **100%** coberto (17 stmts → 0 miss).
  - Teste de domínio puro: sem I/O, sem mock, sem fake (não há port aqui — é VO).
- **Critério de aceite:**
  - `pytest tests/unit/shared/domain/value_objects/test_pagination.py` passa; cobertura de
    `pagination.py` = 100%.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/shared/domain/value_objects/test_pagination.py -v \
    --cov=src/financial_forecasting/shared/domain/value_objects/pagination.py --cov-report=term-missing
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `test(pagination): cobrir VO Pagination com testes unitários [1.2/task-01]`

---

### Task 02 — Podar a assunção Postgres (`database/connection.py`)

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar / remover:**
  - REMOVE `src/financial_forecasting/shared/infrastructure/database/connection.py`
  - REMOVE `src/financial_forecasting/shared/infrastructure/database/__init__.py` e o diretório
    `database/` se ficar vazio (não há outro consumidor).
- **O que fazer:** remover a fábrica de `Engine` SQLAlchemy/Postgres. Overview §6 fixa persistência em
  Parquet+DuckDB (sem Postgres) e o overview §3 manda "não reaproveitar implementações anteriores";
  nenhum módulo importa `connection.build_engine` em runtime (só aparece em docstring de
  `composition_root.py`). Verificar com grep que não há import vivo antes de remover.
- **Detalhes técnicos:**
  - Antes de remover: `grep -rn "database.connection\|build_engine" src/ tests/` deve retornar **só**
    a docstring de `composition_root.py` (texto, não import executável). Se houver import real,
    **parar** e registrar `[decision]` na §7.
  - Não tocar `composition_root.py` nesta Task (o `_` = settings já roda sem o engine).
- **Critério de aceite:**
  - `database/connection.py` não existe mais; `make check` (lint+typecheck+layout) continua verde
    (sem import quebrado); smoke import da app ainda funciona.
- **Comando de verificação:**
  ```bash
  test ! -f src/financial_forecasting/shared/infrastructure/database/connection.py
  uv run mypy src/
  uv run python scripts/check_layout.py
  uv run python -c "import financial_forecasting.composition_root"
  ```
- **Commit sugerido:** `refactor(infra): remover fábrica de engine Postgres fora de escopo [1.2/task-02]`

---

### Task 03 — Configurar `[tool.coverage]` honesto (source + omit + exclude_lines)

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:**
  - `pyproject.toml` — `[tool.coverage.run]` e `[tool.coverage.report]`.
- **O que fazer:** ajustar a configuração de cobertura para medir **código vivo e em escopo**
  (ADR 1.2.0010 D2; I3, A3):
  - `[tool.coverage.run] source = ["src/financial_forecasting"]` (fixar no pacote — A3).
  - `omit` restrito a **wiring/entrypoint/infra-diferida**:
    `main.py`, `composition_root.py`,
    `*/shared/infrastructure/http/*`, `*/shared/infrastructure/logging/*`,
    `*/shared/infrastructure/config/*`, `*/shared/infrastructure/clock/*`,
    `*/shared/infrastructure/uuid_generator/*`, e os já presentes `*/migrations/*`, `*/scripts/*`.
    **Nunca** `adapters/*`.
  - `exclude_lines` defensivos (precedente repo antigo `pyproject` L68-83, validado): `pragma: no cover`,
    `if __name__ == .__main__.:`, `raise NotImplementedError`, `raise AssertionError`,
    `if TYPE_CHECKING:`, `\.\.\.` (corpo de stub de Protocol — cobre `clock.py`/`id_generator.py`).
  - Manter `fail_under = 90`, `show_missing = true`, `skip_covered = false` intactos.
- **Detalhes técnicos:**
  - O `omit` é a **lista auditável** de "o que a cobertura não mede" (ADR 1.2.0010 Consequences). Cada
    entrada é wiring/DI/`__main__`/infra-sem-consumidor — não lógica de domínio/application.
  - Após esta Task, com a Task 01 feita e a Task 02 podada, a cobertura do **código vivo restante**
    (`exceptions/base.py` + `pagination.py`) deve ficar ≥ 90% (esperado ~100%).
- **Critério de aceite:**
  - `pytest --cov` reporta cobertura ≥ 90% e **passa** (não dispara `FAIL`); nenhuma entrada de
    `omit` cobre lógica de domínio/application; `adapters` ausente de `omit`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/ --cov=src/financial_forecasting --cov-report=term-missing
  grep -n "adapters" pyproject.toml || echo "OK: adapters NAO esta em omit"
  ```
- **Commit sugerido:** `chore(coverage): medir só código vivo via omit/exclude restritos a wiring [1.2/task-03]`

---

### Task 04 — Tornar o gate de cobertura efetivo no `make check` (corrige F3)

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:**
  - `Makefile` — alvos `test`, `test-fast`, `test-cov`.
- **O que fazer:** pôr `--cov` no alvo que o CI roda, mantendo o loop local rápido (ADR 1.2.0010 D1;
  I2, I7, A1):
  - `test:` → `uv run pytest tests/ -v --cov=src/financial_forecasting --cov-report=term-missing`
    (agora `make check → test` dispara `fail_under=90`).
  - `test-fast:` → mantém **sem** `--cov` (`uv run pytest tests/ -v -m "not slow"`) para o loop local.
  - `test-cov:` → mantém o relatório HTML (`--cov-report=html --cov-report=term-missing`).
  - Atualizar o texto do `help` se necessário para refletir que `make test`/`make check` medem
    cobertura.
- **Detalhes técnicos:**
  - **Uma só fonte da verdade:** o que o dev roda localmente (`make check`) == o que o CI roda (I7).
    Cobertura entra **dentro** de `make check` via `test`, não em passo separado pulável.
  - Não criar alvo `ci-test` separado (alternativa A rejeitada no ADR 1.2.0010).
- **Critério de aceite:**
  - `make check` executa `pytest --cov` e fica **verde** (cobertura ≥ 90% após Tasks 01–03);
    `make test-fast` roda sem cobertura.
- **Comando de verificação:**
  ```bash
  make check
  grep -q -- "--cov=src/financial_forecasting" Makefile && echo "OK: cov no alvo test"
  ```
- **Commit sugerido:** `build(makefile): medir cobertura no alvo test para o gate disparar no CI [1.2/task-04]`

---

### Task 05 — Endurecer `.github/workflows/ci.yml` (timeout; job único; guard preservado)

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:**
  - `.github/workflows/ci.yml`.
- **O que fazer:** endurecimento operacional (ADR 1.2.0011; D5; I5, A4):
  - Adicionar `timeout-minutes` por job (`guard-main-source` e `lint-and-test`) — precedente repo
    antigo `ci.yml` (`timeout-minutes: 40/20`); usar valores conservadores (ex.: `5` para o guard,
    `15` para `lint-and-test`).
  - Manter **um único** job de gate `lint-and-test` rodando `make check` (que após a Task 04 já inclui
    cobertura) — **não** fragmentar em jobs `needs:` (alternativa B rejeitada).
  - Preservar `guard-main-source` intacto e a toolchain `uv`/`setup-uv`/`setup-python`.
  - Atualizar o nome do passo de gate para refletir cobertura (ex.: "Run gate completo (lint +
    typecheck + layout-check + docs-check + tests + coverage)").
- **Detalhes técnicos:**
  - YAML deve permanecer válido; nenhum step novo de cobertura separado (a cobertura está em
    `make check`).
- **Critério de aceite:**
  - `ci.yml` válido (parse YAML OK); `timeout-minutes` presente nos dois jobs; job único
    `lint-and-test` roda `make check`; `guard-main-source` inalterado.
- **Comando de verificação:**
  ```bash
  uv run python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML OK')"
  grep -c "timeout-minutes" .github/workflows/ci.yml
  ```
- **Commit sugerido:** `ci(workflow): adicionar timeout-minutes e refletir cobertura no gate único [1.2/task-05]`

---

### Task 06 — Documentar o contrato no `README.md` + validar o gate por quebra revertida (DoD)

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:**
  - `README.md` — seção CI/qualidade.
- **O que fazer (duas partes na mesma Task — ambas docs/validação, sem código de produção):**
  1. **README** (A6): reescrever a seção `## CI` para descrever o **contrato real**: um PR reprova se
     violar **ruff** OU **mypy --strict** OU **`scripts/check_layout.py`** (direção de dependência
     hexagonal) OU **pytest** OU **cobertura < 90%**; comando local idêntico ao CI = `make check`;
     badge de status do workflow `ci`
     (`![CI](https://github.com/MarceloSanC/financial-forecasting/actions/workflows/ci.yml/badge.svg)`);
     nota explícita de que os **contratos import-linter formais chegam na Stage 1.3** (o "contrato de
     import" da 1.2 é o `check_layout.py`). Corrigir a descrição obsoleta atual ("Upload do relatório
     de cobertura" / `make check && make test`) para o contrato novo. Coerente com `CLAUDE.md` e
     `GIT-WORKFLOW.md`.
  2. **Validação por quebra intencional revertida** (A5, DoD; I1/I2) — para **cada** modo de falha,
     introduzir a quebra, confirmar que `make check` (ou o subcheck) fica **VERMELHO**, **reverter**, e
     registrar a evidência (comando + saída resumida) na §7 como `[decision]`/nota de validação:
     - (a) **lint** — inserir uma violação ruff trivial → `make lint` falha → reverter.
     - (b) **tipo mypy** — anotação incompatível → `make typecheck` falha → reverter.
     - (c) **violação de import** (`layout-check`) — import que viola a direção hexagonal →
       `make layout-check` falha → reverter.
     - (d) **cobertura < 90%** — remover/esvaziar um teste de `test_pagination.py` (ou adicionar
       statement não coberto) → `pytest --cov` dispara
       `FAIL Required test coverage of 90.0% not reached` → reverter.
     Nenhuma quebra é commitada — só revertida; a evidência fica na §7.
- **Detalhes técnicos:**
  - A §7 post-execution só pode ser preenchida **após** a Task estar `done` e dentro dos marcadores
    `BEGIN/END: post-execution` (validado por `scripts/check_technical_postexec.py` em `make
    docs-check`).
  - **`.importlinter` e `tests/architecture/` NÃO são criados** (A7, I6).
- **Critério de aceite:**
  - README documenta o contrato (5 checks) + badge + nota import-linter→1.3; as 4 quebras provaram
    VERMELHO e foram revertidas (evidência na §7); estado final `make check` **VERDE**;
    `make docs-check` não reprova.
- **Comando de verificação:**
  ```bash
  grep -q "badge.svg" README.md && echo "OK: badge"
  grep -qi "1.3" README.md && echo "OK: nota import-linter 1.3"
  test ! -f .importlinter && test ! -d tests/architecture && echo "OK: nada de import-linter (1.3)"
  make check
  make docs-check
  ```
- **Commit sugerido:** `docs(readme): documentar contrato do gate de CI e cobertura ≥90% [1.2/task-06]`

---

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber `stage 1.2: complete` e ser mergeada em
> `develop`.

### Verificações automatizadas
```bash
make check                # lint + typecheck + layout-check + docs-check + test(--cov) ≥90% — TUDO verde
uv run pytest tests/ --cov=src/financial_forecasting --cov-report=term-missing   # cobertura ≥90% passa
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML OK')"
test ! -f .importlinter && test ! -d tests/architecture && echo "non_goal 1.3 respeitado"
```

### Verificações funcionais
- [ ] `make check` dispara `pytest --cov` e o `fail_under=90` é exercitado (antes do tratamento do
      excedente, o gate REPROVAVA a 33% — comprovado no baseline). (I2, A1)
- [ ] Cobertura final ≥ 90% medida **apenas** sobre código vivo; `adapters/*` ausente de `omit`;
      nenhuma exclusão sobre lógica de domínio/application. (I3, A2)
- [ ] As 4 quebras intencionais (lint, tipo, import/layout, cobertura<90%) provaram VERMELHO e foram
      revertidas; evidência na §7. (I1, A5, DoD)
- [ ] README descreve o contrato + badge + nota import-linter→1.3. (A6)
- [ ] `.importlinter`/`tests/architecture/` não criados. (A7, I6)

### Mapping invariante ⟷ Task/teste (gate de saída)

| Invariante (concept §5) | Onde é garantido | Verificação |
|---|---|---|
| **I1** — CI verde ⟹ todas as fronteiras seguraram | Task 05 (job único `make check`) + Task 06 (quebra revertida das 5 fronteiras) | `make check` verde; §7 registra VERMELHO→VERDE de lint/tipo/layout/cobertura |
| **I2** — `fail_under=90` efetivamente exercitado (não inerte) | Task 04 (`--cov` no `test`) | quebra (d) cobertura<90% dispara `FAIL Required test coverage` e é revertida |
| **I3** — cobertura reflete código VIVO e em escopo | Task 01 (testa VO vivo) + Task 02 (poda) + Task 03 (omit/exclude só wiring; adapters contam) | `grep adapters pyproject.toml` vazio; lista `omit` auditável = só wiring/infra-diferida |
| **I4** — toolchain preservada | Tasks 04/05 (uv + ruff + mypy + pytest; sem pip/black) | `Makefile`/`ci.yml` usam só `uv run`; nenhuma dep nova de ferramenta |
| **I5** — um único job de gate basta | Task 05 (job único `lint-and-test`; guard ortogonal) | `ci.yml` sem `needs:` encadeado; `guard-main-source` intacto |
| **I6** — 1.2 NÃO introduz `.importlinter`/`tests/architecture/` | Task 06 (asserção de ausência) | `test ! -f .importlinter && test ! -d tests/architecture` |
| **I7** — `make check` local == veredito do CI | Task 04 (cobertura dentro de `make check`) | mesmo comando local e no `ci.yml` (`make check`), sem step de cobertura separado |

### Checklist de fechamento da Stage
- [ ] Todas as 6 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch (lint+type+layout+docs+cobertura≥90%)
- [ ] §7 preenchida com a evidência das 4 quebras revertidas
- [ ] Commit final `stage 1.2: complete` aplicado
- [ ] `roadmap.md` atualizado: Stage 1.2 `done`, `updated_at`/`last_reviewed_at` no mesmo merge
- [ ] ADRs 1.2.0010 e 1.2.0011 em `status: accepted` (já estão)
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo

## 4. Ordem de dependência entre Tasks

A ordem listada em §2 já respeita as dependências (inside-out adaptado: código vivo → poda →
config → gate → CI → docs/validação):

```
Task 01 (testar VO) ─┐
Task 02 (podar)      ─┼─► Task 03 (config coverage) ─► Task 04 (cov no make check) ─► Task 05 (ci.yml) ─► Task 06 (README + validação DoD)
```

- Task 03 depende de 01 e 02 (a cobertura ≥90% só fecha após o VO testado e a poda do Postgres).
- Task 04 depende de 03 (sem `omit`/`exclude` corretos, `--cov` no `make check` reprovaria).
- Task 06 (validação por quebra) depende de 04+05 (o gate precisa estar cabeado e efetivo para a
  quebra provar VERMELHO).

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Poda de `database/connection.py` quebra import/layout/mypy | grep por import vivo **antes** de remover (Task 02); se houver consumidor real, parar e registrar `[decision]` na §7; reverter a remoção |
| `omit`/`exclude_lines` acabam cobrindo lógica real (inflam o número) | revisão na Task 03: cada entrada é wiring/`__main__`/infra-sem-consumidor; `adapters/*` proibido; lista auditável no `pyproject.toml` (I3) |
| Gate continua inerte por `--cov` no alvo errado | quebra intencional (d) na Task 06: baixar cobertura **tem** que deixar `make check` VERMELHO; se não deixar, o cabeamento está errado |
| Cobertura ≥90% não fecha mesmo após poda+teste (mais código vivo que o esperado) | medir com `--cov-report=term-missing`; testar o que for genuinamente lógica de domínio/application; só então omit (nunca sobre domínio); se persistir, registrar `[finding]` para a Stage consumidora |
| Drift entre `make check` local e CI | cobertura entra **dentro** de `make check` (Task 04), não em step separado no `ci.yml` (I7) |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage
- [`../../overview.md`](../../overview.md) — §3 (não-reaproveitar), §4 (fronteiras / ≥90%), §6 (sem Postgres; domínio puro), §7 (enforcement-as-test)
- [`../../roadmap.md`](../../roadmap.md) — Stage 1.2 (DoD, `non_goals`); Stage 1.3 (import-linter formal)
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — branches, commits (§4), frontmatter (§2/§3)
- ADRs desta Stage: [`1.2.0010`](../../adr/1_2_0010-cobertura-no-ci-e-tratamento-do-excedente-herdado.md), [`1.2.0011`](../../adr/1_2_0011-coverage-gate-as-foundational-fitness-function.md)
- ADRs relacionados: [`1.1.0001`](../../adr/1_1_0001-template-surplus-handling.md), [`0.0.0019`](../../adr/0_0_0019-hexagonal-enforced.md), [`0.0.0021`](../../adr/0_0_0021-per-unit-contract-tests-with-oracle.md), [`0.0.0050`](../../adr/0_0_0050-autonomous-overnight-mode.md)
- Skills aplicáveis: `task-ordering-hex` (ordem inside-out), `pytest-with-fakes` (teste de domínio — Task 01 é VO puro, sem port), `import-linter-rules` (referência para a Stage 1.3)

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável após `status: done`** —
> alterações fora dos marcadores `BEGIN/END: post-execution` são rejeitadas via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at` **não muda** com edições aqui —
> cada entrada carrega data + autor. Seção pode estar vazia se a execução não produziu notas.
>
> **Regra de decisão (corrida autônoma — ADR 0.0.0050).** Ao encontrar algo não previsto no Concept
> ou neste Technical, **decidir sozinho** com base concreta (repo antigo / paper / doc), registrar
> aqui como `[decision]`/`[deviation]`/`[finding]` e seguir. As 4 quebras intencionais revertidas (A5)
> são registradas aqui como evidência do gate.

<!-- preencher na Fase 4; remover este placeholder se vazio -->

<!-- END: post-execution -->
