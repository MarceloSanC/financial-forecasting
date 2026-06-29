---
title: Technical — Stage 1.5 — Config tipada e tracking de experimentos
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, config-and-tracking, settings, mlflow, experiment-tracker, composition-root, sqlite]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 1.5-config-and-tracking
stage_title: Config tipada e tracking de experimentos
step_id: 1
step_title: Fundação e fitness arquitetural
depends_on: [1.4-identity-and-fingerprints]
concept_ref: ./concept.md
issue_id: 13
branch: feat/13-1-5-config-and-tracking
tasks_count: 8
---

# Technical — Stage 1.5 — Config tipada e tracking de experimentos

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [N.M/task-NN]`, body em bullets,
>    rodapé `Refs #13`.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done)
>    como `[decision]`/`[finding]`/`[deviation]`. Nunca propagar silenciosamente.
> 7. **Fechamento NÃO é desta sessão.** O commit `stage 1.5: complete` e a
>    marcação `done` no `roadmap.md` são feitos pelo ORQUESTRADOR após auditoria
>    independente. Esta sessão entrega a branch com concept/technical/código/
>    testes commitados e gates verdes.
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/13-1-5-config-and-tracking`. Não há sub-PRs internos. Sobre o fluxo Git
> completo ver [`PIPELINE.md`](../../PIPELINE.md) §10.

## 1. Contexto e estratégia de execução

### Resumo
Esta Stage fecha o Step 1 (fundação) entregando **config tipada** e **tracking
de experimentos**. Concretamente: (a) evolui o `Settings` (`pydantic-settings`)
acrescentando `mlflow_tracking_uri`, espelhado em `.env.example`; (b) introduz o
port-out `ExperimentTracker` (`Protocol` mínimo em `shared/application/ports/out`,
sem vazar `mlflow`) com idempotência por `run_id` como invariante de contrato;
(c) implementa o adapter `MlflowTracker` sobre a lib `mlflow` com backend SQLite
local; (d) entrega o `FakeExperimentTracker` in-memory que passa o **mesmo**
contract test parametrizado que o real; (e) evolui o `composition_root` para
instanciar `Settings`, `CanonicalJsonHasher` (1.4) e `MlflowTracker`, expondo-os
via `ApplicationDependencies`; (f) remove `*/composition_root.py` e
`*/shared/infrastructure/config/*` do `[tool.coverage.run].omit` (CARRY 1.2),
ativando a cobertura ≥90% nesses módulos.

### Estratégia
Stage híbrida: parte é **fundação/infra** (config — não há domínio de onde
partir, ordem dirigida pela dependência de infra) e parte é uma **fatia
port→adapter** (inside-out via `task-ordering-hex`). Ordem escolhida e razão
(declarada conforme a skill, pois o default vertical-slice não se aplica
inteiro):

1. **Docs/deps primeiro** (Task 01): registrar a dependência `mlflow` no
   `pyproject`/`uv.lock` e os ADRs já `accepted` — habilita import do adapter nas
   Tasks seguintes sem deixar a árvore vermelha por falta de lib.
2. **Settings** (Task 02): infra de config, sem consumidor de domínio; sai do
   `omit` só na Task 07 para não quebrar cobertura no meio do caminho — mas o
   unit test já entra aqui.
3. **Port + Fake** (Task 03): `Protocol` em `application` + `FakeExperimentTracker`
   in-memory na mesma Task (port e seu fake; **não** o adapter real). O fake
   encapsula o estado mínimo de runs; testável sem `mlflow`.
4. **Adapter real + contract test** (Task 04): `MlflowTracker` sobre `mlflow` +
   contract test parametrizado `[fake, real]` provando paridade e idempotência.
   Port (Task 03) já existe — não mistura criar port com criar adapter.
5. **Wiring** (Task 05): `composition_root` instancia os concretos e expõe via
   `ApplicationDependencies`; teste com `Settings` fake (`tracking_uri` em
   `tmp_path`).
6. **CARRY coverage** (Task 06): remover entradas do `omit` e provar ≥90%.
7. **Import-linter regression** (Task 07): contrato `tracker-no-mlflow-leak`
   blindando que `application` nunca importe `mlflow`.
8. **Gate final** (Task 08): `.env.example` + `make check` ponta a ponta.

Cada Task deixa o build verde: o fake (Task 03) existe antes do adapter real
(Task 04); o port (Task 03) existe antes do wiring (Task 05); a remoção do `omit`
(Task 06) só ocorre depois que os módulos têm teste real exercitando-os.

### Pré-condições
- Stage `1.4-identity-and-fingerprints` em `done`: port `Hasher` e adapter
  `CanonicalJsonHasher` disponíveis (`src/financial_forecasting/shared/adapters/
  out/hashing/canonical_json_hasher.py`).
- Branch `feat/13-1-5-config-and-tracking` em checkout.
- `uv` disponível para resolver/lockar `mlflow`.

### Premissas técnicas
- Python 3.12; `pyproject.toml` já existe com `pydantic-settings`.
- `mlflow` aceita `tracking_uri` SQLite local (`sqlite:///...`) como backend
  store sem servidor e permite resumir um run por `run_id` (`mlflow.start_run(
  run_id=...)`), base da idempotência.
- `Settings` já tem `get_settings()` com `lru_cache`; `composition_root.py`
  (na RAIZ do pacote: `src/financial_forecasting/composition_root.py`) já aceita
  `wire_dependencies(settings: Settings | None = None)`.
- `[tool.coverage.run].fail_under = 90`; `make check`/`make test` rodam com
  `--cov`.

### Estrutura de pastas afetada

```
src/financial_forecasting/
├── composition_root.py                              # MODIFICAR (wiring)
└── shared/
    ├── adapters/out/mlflow/
    │   ├── __init__.py                               # CRIAR
    │   └── mlflow_tracker.py                         # CRIAR (adapter)
    ├── application/ports/out/
    │   └── experiment_tracker.py                     # CRIAR (port Protocol)
    └── infrastructure/config/
        └── settings.py                               # MODIFICAR (+mlflow_tracking_uri)
tests/
├── unit/shared/infrastructure/config/
│   ├── __init__.py                                   # CRIAR
│   └── test_settings.py                              # CRIAR
├── unit/shared/                                      # (test do wiring)
│   └── test_composition_root.py                      # CRIAR
├── fakes/shared/
│   └── in_memory_experiment_tracker.py              # CRIAR (fake)
├── contract/shared/
│   └── test_experiment_tracker_contract.py          # CRIAR (contract parametrizado)
└── architecture/
    └── test_import_contracts.py                      # MODIFICAR (regressão do novo contrato)
pyproject.toml                                        # MODIFICAR (dep mlflow + omit)
uv.lock                                               # MODIFICAR (lock)
.env.example                                          # MODIFICAR (MLFLOW_TRACKING_URI)
.importlinter                                         # MODIFICAR (contrato tracker-no-mlflow-leak)
```

## 2. Tasks

### Task 01 — Adicionar dependência `mlflow` ao projeto

- **Arquivos a criar:** nenhum (ADRs `1_5_0001`/`1_5_0002` já existem `accepted`).
- **Arquivos a modificar:**
  - `pyproject.toml` (bloco `[project].dependencies`)
  - `uv.lock`
- **O que fazer:**
  Acrescentar `mlflow>=2.14` (ou versão estável corrente que suporte
  `sqlite:///` backend store) em `[project].dependencies` e sincronizar o lock
  via `uv lock` / `uv sync`. Não mexer no `omit` ainda (isso é a Task 06).
- **Detalhes técnicos:**
  - `mlflow` é dependência de runtime (o adapter a importa) — vai em
    `[project].dependencies`, não em `dev`.
  - Não fixar versão exata; usar `>=` com piso, alinhado ao estilo das demais
    deps (`fastapi>=0.111`, `pydantic>=2.7`).
- **Critério de aceite:**
  - `python -c "import mlflow"` ok no ambiente.
  - `uv.lock` reflete `mlflow` e suas transitivas; `uv sync --frozen` consistente.
- **Comando de verificação:**
  ```bash
  uv lock && uv sync
  uv run python -c "import mlflow; print(mlflow.__version__)"
  ```
- **Commit sugerido:** `build(deps): adicionar mlflow para tracking de experimentos [1.5/task-01]`

---

### Task 02 — Evoluir `Settings` com `mlflow_tracking_uri` + unit test

- **Arquivos a criar:**
  - `tests/unit/shared/infrastructure/config/__init__.py`
  - `tests/unit/shared/infrastructure/config/test_settings.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/shared/infrastructure/config/settings.py`
- **O que fazer:**
  Acrescentar o campo `mlflow_tracking_uri: str = "sqlite:///mlruns.db"` ao
  `Settings`, com comentário de seção (espelhando o estilo dos demais campos).
  Escrever o unit test cobrindo: (a) defaults (incluindo o novo campo),
  (b) override por variável de ambiente (`MLFLOW_TRACKING_URI` →
  `mlflow_tracking_uri`; e um campo existente como `PORT`), (c) `ValidationError`
  em tipo inválido (`PORT="abc"`).
- **Detalhes técnicos:**
  - O default segue ADR `1_5_0001`/D4: `"sqlite:///mlruns.db"` (relativo).
  - O teste **deve** chamar `get_settings.cache_clear()` entre casos que mexem em
    env (evita vazamento do `lru_cache`); usar `monkeypatch.setenv`/`delenv` e,
    quando precisar evitar leitura do `.env` real, construir `Settings(
    _env_file=None)` ou usar `monkeypatch` no `model_config` — preferir
    `monkeypatch.setenv` + `Settings()` direto e limpar o cache.
  - `ValidationError` vem de `pydantic_core` (`pydantic.ValidationError`).
- **Critério de aceite:**
  - `test_settings.py` cobre defaults, override por env e `ValidationError`
    (C1) com `cache_clear()` entre casos.
  - O arquivo `settings.py` continua coberto ≥90% quando sair do `omit`
    (Task 06).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/shared/infrastructure/config/test_settings.py -v
  uv run mypy --strict src/financial_forecasting/shared/infrastructure/config/settings.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(config): adicionar mlflow_tracking_uri ao Settings [1.5/task-02]`

---

### Task 03 — Port `ExperimentTracker` (Protocol) + `FakeExperimentTracker`

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/application/ports/out/experiment_tracker.py`
  - `tests/fakes/shared/in_memory_experiment_tracker.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:**
  Criar o `Protocol` `ExperimentTracker` com a superfície mínima fixada no ADR
  `1_5_0002` e no concept §4 — `start_run(*, run_name=None, run_id=None) -> str`,
  `log_params(Mapping[str, object]) -> None`, `log_metrics(Mapping[str, float],
  step=None) -> None`, `set_tags(Mapping[str, str]) -> None`,
  `log_artifact(path: str) -> None`, `end_run() -> None` — usando apenas
  `typing`/`collections.abc` (**sem** `import mlflow`). Docstring em PT
  declarando a idempotência por `run_id` (I2) e que `log_*`/`set_tags`/
  `log_artifact`/`end_run` exigem run ativo (C2). Em seguida, escrever o
  `FakeExperimentTracker` in-memory que implementa o contrato: guarda runs por
  `run_id` num dict, gera `run_id` quando não fornecido, **reabre** o run ao
  receber `run_id` já registrado (idempotência), levanta erro de estado em
  operações sem run ativo (C2), e registra `log_artifact` validando que o path
  existe (C4, espelhando o erro de I/O do real) ou documentando a postura no
  contract test.
- **Detalhes técnicos:**
  - O port espelha o estilo do `Hasher` (Protocol com docstrings PT, sem
    decorator). Métodos kw-only onde o ADR fixa (`start_run`).
  - O fake levanta `RuntimeError` (ou exceção dedicada) para "no active run" —
    o mesmo TIPO observável que o adapter real propaga do `mlflow`; alinhar com
    a Task 04 para o contract test ser satisfeito por ambos (ver §5).
  - `log_metrics(step=None)`: o fake acumula por `(metric, step)`.
  - Geração de `run_id` no fake: usar `uuid4().hex` (determinismo não é exigido
    do fake aqui; só a idempotência por `run_id` fornecido).
  - **Não** criar o adapter real nesta Task (regra §4.3: não misturar port com
    adapter do mesmo port).
- **Critério de aceite:**
  - `experiment_tracker.py` é `Protocol` puro (stdlib/`typing`), **sem**
    `import mlflow`.
  - `FakeExperimentTracker` satisfaz estruturalmente o `Protocol` (verificável
    por mypy: anotar uma var `tracker: ExperimentTracker = FakeExperimentTracker()`
    num teste ou no próprio módulo de fake via `if TYPE_CHECKING`).
- **Comando de verificação:**
  ```bash
  uv run mypy --strict \
    src/financial_forecasting/shared/application/ports/out/experiment_tracker.py \
    tests/fakes/shared/in_memory_experiment_tracker.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(tracking): introduzir port ExperimentTracker e fake in-memory [1.5/task-03]`

---

### Task 04 — Adapter `MlflowTracker` + contract test parametrizado

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/adapters/out/mlflow/__init__.py`
  - `src/financial_forecasting/shared/adapters/out/mlflow/mlflow_tracker.py`
  - `tests/contract/shared/test_experiment_tracker_contract.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:**
  Implementar `MlflowTracker(ExperimentTracker)` sobre a lib `mlflow`, recebendo
  `tracking_uri: str` no construtor e configurando o backend
  (`mlflow.set_tracking_uri(tracking_uri)`). Implementar cada método do port
  traduzindo para a API `mlflow` (`mlflow.start_run(run_id=..., run_name=...)`,
  `mlflow.log_params`, `mlflow.log_metrics(..., step=...)`, `mlflow.set_tags`,
  `mlflow.log_artifact`, `mlflow.end_run`), encapsulando o reabrir-por-`run_id`
  (resume) no `start_run`. Escrever o contract test parametrizado sobre
  `[FakeExperimentTracker(), MlflowTracker(tracking_uri=<tmp>)]` (mesma postura
  do `test_hasher_contract.py`), cobrindo: start/end de run, `log_params`,
  `log_metrics(step)`, `set_tags`, `log_artifact` (com arquivo real em
  `tmp_path`), erro sem run ativo (C2) e **idempotência por `run_id`** (I2:
  reabrir o mesmo `run_id` não cria run novo).
- **Detalhes técnicos:**
  - O adapter **nunca** entra em `omit` (concept §5/I7, A3) — conta cobertura
    ≥90% + contract test.
  - `tracking_uri` no teste: `f"sqlite:///{tmp_path}/mlruns.db"` para isolamento
    (D4). Cada execução do contract usa um `tmp_path` próprio (fixture).
  - Idempotência: o teste pega o `run_id` retornado por `start_run()`, fecha o
    run, chama `start_run(run_id=<aquele>)` e verifica que o backend continua com
    **um** run para aquele id (ex.: contar runs via `MlflowClient.search_runs`
    no adapter real; no fake, contar entradas no dict). Encapsular a contagem
    num helper do teste ou em método auxiliar — manter o contract test agnóstico
    de implementação (só usa o port + uma forma de inspecionar o número de runs).
  - **Atenção ao acoplamento do contract test ao backend:** se contar runs
    exigir API específica de cada impl, preferir um método de inspeção mínimo no
    contrato OU verificar a idempotência pela identidade do `run_id` retornado
    (`start_run(run_id=r)` devolve `r`, e um segundo `log_metrics` no run
    reaberto não falha nem duplica) — decidir na execução e registrar como
    `[decision]` se fugir do plano.
  - Mapear erro de "no active run": garantir que o tipo levantado pelo `mlflow`
    e pelo fake casem no `pytest.raises(...)` do contrato (ver §5 fallback).
- **Critério de aceite:**
  - Contract test verde para **ambos** os params (`fake` e `real`), incluindo
    idempotência por `run_id` (I2, I3, A4).
  - `MlflowTracker` não está em `omit`; cobertura ≥90% no módulo.
  - `mlflow` importado **apenas** neste adapter (verificado na Task 07).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/shared/test_experiment_tracker_contract.py -v
  uv run mypy --strict src/financial_forecasting/shared/adapters/out/mlflow/mlflow_tracker.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(tracking): implementar MlflowTracker com backend sqlite local [1.5/task-04]`

---

### Task 05 — Evoluir `composition_root` + teste de wiring

- **Arquivos a criar:**
  - `tests/unit/shared/test_composition_root.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/composition_root.py`
- **O que fazer:**
  Evoluir `ApplicationDependencies` para expor `tracker: ExperimentTracker` e
  `hasher: Hasher`. Em `wire_dependencies(settings=None)`: resolver
  `cfg = settings or get_settings()` e instanciar `CanonicalJsonHasher()` e
  `MlflowTracker(tracking_uri=cfg.mlflow_tracking_uri)`, retornando-os no
  contêiner. Escrever o teste exercitando o wiring com um `Settings` fake
  (`mlflow_tracking_uri = f"sqlite:///{tmp_path}/mlruns.db"`) e verificando que
  `deps.tracker` é `MlflowTracker` e `deps.hasher` é `CanonicalJsonHasher`
  (tipos/instâncias), sem depender do `lru_cache` global (I6).
- **Detalhes técnicos:**
  - `composition_root.py` é o ÚNICO lugar que cria concretos (skill
    `composition-root`, I6). As anotações de tipo dos campos usam os PORTS
    (`ExperimentTracker`, `Hasher`), não os concretos — wiring centralizado,
    contrato exposto.
  - Construir `Settings` fake passando o campo direto: `Settings(
    mlflow_tracking_uri=...)` (pydantic-settings aceita kwargs); injetar via
    `wire_dependencies(settings=fake)`.
  - O teste cobre o caminho real de `wire_dependencies` — necessário para a
    cobertura ≥90% quando `composition_root.py` sair do `omit` (Task 06).
- **Critério de aceite:**
  - `deps.tracker`/`deps.hasher` instanciados a partir de `Settings` injetado
    (A5); tipos verificados.
  - `mypy --strict` verde nos campos tipados pelos ports.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/shared/test_composition_root.py -v
  uv run mypy --strict src/financial_forecasting/composition_root.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(bootstrap): wirar Settings, Hasher e MlflowTracker no composition root [1.5/task-05]`

---

### Task 06 — CARRY 1.2: remover `composition_root` e `config/*` do omit

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:**
  - `pyproject.toml` (`[tool.coverage.run].omit`)
- **O que fazer:**
  Remover do `omit` as entradas `*/composition_root.py` e
  `*/shared/infrastructure/config/*`, ajustando o comentário auditável para
  registrar que a Stage 1.5 as ativa com consumidor real (Tasks 02/05).
  **Manter** em `omit`: `*/main.py`, `http/*`, `logging/*`, `clock/*`,
  `uuid_generator/*`, `ports/out/clock.py`, `ports/out/id_generator.py`
  (sem consumidor real nesta Stage — I7). **Não** acrescentar
  `experiment_tracker.py` ao omit (port-out com consumidor + contract test).
- **Detalhes técnicos:**
  - Após a remoção, rodar a suíte com `--cov` e confirmar `fail_under=90` verde
    **com** `settings.py` e `composition_root.py` contando. Se algum ficar
    <90%, reforçar o teste correspondente (Task 02/05) — mas isso indica teste
    insuficiente, não relaxar o gate.
- **Critério de aceite:**
  - `*/composition_root.py` e `*/shared/infrastructure/config/*` ausentes do
    `omit` (A6); `experiment_tracker.py` **não** está no omit.
  - `make test` (com `--cov`) verde, cobertura ≥90% global.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/ --cov=src/financial_forecasting --cov-report=term-missing
  grep -A30 'tool.coverage.run' pyproject.toml | grep -E 'composition_root|config/\*' || echo "OK: removidos do omit"
  ```
- **Commit sugerido:** `chore(coverage): ativar composition_root e config na cobertura (CARRY 1.2) [1.5/task-06]`

---

### Task 07 — Contrato import-linter: `mlflow` só no adapter

- **Arquivos a modificar:**
  - `.importlinter` (novo contrato `forbidden`)
  - `tests/architecture/test_import_contracts.py` (regressão do novo contrato)
- **O que fazer:**
  Adicionar ao `.importlinter` um contrato `forbidden` (ex.:
  `tracker-no-mlflow-leak`) com `source_modules =
  financial_forecasting.shared.application` (e, por defesa, `shared.domain`) e
  `forbidden_modules = mlflow`, blindando o invariante I4 (a `application` nunca
  importa `mlflow`; ele vive só no adapter). Acrescentar
  `"tracker-no-mlflow-leak"` à tupla `_EXPECTED_CONTRACTS` do teste de regressão
  e, se aplicável, um caso em `_REAL_VIOLATION_CASES` injetando um módulo de
  `application` que importa `mlflow` e exigindo o contrato `broken`.
- **Detalhes técnicos:**
  - `include_external_packages = True` já está setado (necessário para forbidden
    externo) — o contrato `mlflow` casa.
  - Espelhar LAYOUT §3/§6 (a fonte da verdade): se LAYOUT precisar de uma linha
    explicitando "mlflow só no adapter", registrar como `[decision]`/ajuste
    pequeno; senão o contrato deriva diretamente do princípio de pureza de
    application já documentado.
  - O caso de violação real deve injetar em `shared/application/` (não em
    domain, que já é coberto por `domain-purity` se `mlflow` fosse adicionado lá)
    — o alvo do novo contrato é `application`.
- **Critério de aceite:**
  - `uv run lint-imports` verde no repo real com o novo contrato presente (A8).
  - `test_importlinter_declares_expected_contracts` passa com o novo nome.
  - (se incluído) `test_production_contract_reacts_to_real_violation` quebra o
    novo contrato quando `application` importa `mlflow`.
- **Comando de verificação:**
  ```bash
  uv run lint-imports
  uv run pytest tests/architecture/test_import_contracts.py -v
  ```
- **Commit sugerido:** `test(architecture): contrato import-linter mlflow-só-no-adapter [1.5/task-07]`

---

### Task 08 — `.env.example` + gate final da Stage

- **Arquivos a modificar:**
  - `.env.example` (seção `MLflow`)
- **O que fazer:**
  Acrescentar a seção `# MLflow / Experiment tracking` ao `.env.example` com
  `MLFLOW_TRACKING_URI=sqlite:///mlruns.db` (espelhando o default de `Settings`)
  e um comentário em PT explicando que SQLite local é o backend do piloto,
  trocável por env. Rodar o gate completo da Stage (§3) e confirmar tudo verde.
- **Detalhes técnicos:**
  - Espelhamento `.env.example` ↔ `Settings` é convenção do projeto (cabeçalho
    do próprio `.env.example`); o campo precisa aparecer em ASCII com o nome
    exato `MLFLOW_TRACKING_URI`.
  - Esta Task fecha as verificações funcionais — não faz o commit
    `stage 1.5: complete` (fechamento é do orquestrador).
- **Critério de aceite:**
  - `.env.example` contém `MLFLOW_TRACKING_URI` (A1).
  - `make check` e `make test` verdes; cobertura ≥90% (A8).
- **Comando de verificação:**
  ```bash
  grep MLFLOW_TRACKING_URI .env.example
  make check
  ```
- **Commit sugerido:** `docs(config): espelhar MLFLOW_TRACKING_URI no .env.example [1.5/task-08]`

---

## 3. Gate de saída da Stage

> Fechamento (`stage 1.5: complete` + `roadmap.md` done) é do ORQUESTRADOR após
> auditoria independente — NÃO desta sessão. Esta sessão garante o gate verde.

### Verificações automatizadas
```bash
make check                # lint + mypy --strict + import-linter + check_layout + testes (--cov, fail_under=90)
uv run pytest tests/      # todos os testes
uv run lint-imports       # contratos de arquitetura (inclui tracker-no-mlflow-leak)
uv run python -c "import mlflow"   # dep instalada
```

### Verificações funcionais
- [ ] `Settings()` com `MLFLOW_TRACKING_URI` no env resolve `mlflow_tracking_uri`;
      `PORT="abc"` levanta `ValidationError` (C1).
- [ ] `MlflowTracker(tracking_uri="sqlite:///<tmp>/mlruns.db")` registra um run,
      loga params/metrics(step)/tags/artifact e fecha; reabrir o mesmo `run_id`
      não duplica (I2).
- [ ] `wire_dependencies(settings=Settings(mlflow_tracking_uri=<tmp>))` retorna
      `ApplicationDependencies` com `tracker: MlflowTracker` e `hasher:
      CanonicalJsonHasher`.

### Mapeamento invariante ↔ teste

| Invariante (concept §5) | Teste / verificação |
|---|---|
| I1 — Settings valida tipos no boot | `tests/unit/shared/infrastructure/config/test_settings.py` (caso `PORT="abc"` → `ValidationError`) |
| I2 — Idempotência por `run_id` | `tests/contract/shared/test_experiment_tracker_contract.py` (reabrir `run_id` não duplica), param `[fake, real]` |
| I3 — Paridade fake↔real | `test_experiment_tracker_contract.py` parametrizado em `[FakeExperimentTracker, MlflowTracker]` |
| I4 — Port não vaza `mlflow` | `.importlinter` contrato `tracker-no-mlflow-leak` + `tests/architecture/test_import_contracts.py` |
| I5 — Domínio puro | `.importlinter` `domain-purity` (regressão existente) + `check_layout.py` |
| I6 — Wiring centralizado, sem singleton | `tests/unit/shared/test_composition_root.py` (Settings injetado, `tracking_uri` em `tmp_path`) |
| I7 — CARRY 1.2 coverage | `pyproject.toml` `[tool.coverage.run].omit` sem `composition_root`/`config/*`; `make test --cov` ≥90% |
| I8 — Gates verdes | `make check` + `make test` + `lint-imports` verdes |
| C1 — Tipo de config inválido | `test_settings.py` (`pytest.raises(ValidationError)`) |
| C2 — Operação sem run ativo | `test_experiment_tracker_contract.py` (`pytest.raises` em `log_*` sem `start_run`) |

### Checklist de fechamento da Stage
- [ ] Todas as 8 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Cobertura ≥90% nos módulos ativados (`settings.py`, `composition_root.py`,
      `mlflow_tracker.py`, `experiment_tracker.py`)
- [ ] ADRs `1_5_0001` e `1_5_0002` em `status: accepted` (já estão)
- [ ] `concept.md` desta Stage não precisou de retoque material
- [ ] **NÃO** fazer commit `stage 1.5: complete` nem marcar `roadmap.md` done
      (responsabilidade do orquestrador, pós-auditoria)

## 4. Ordem de dependência entre Tasks

```
Task 01 (dep mlflow) ─► Task 02 (Settings) ─► Task 03 (port+fake) ─► Task 04 (adapter+contract)
                                                     │                        │
                                                     └────────► Task 05 (wiring) ◄─┘
                                                                      │
                                                                      ▼
                                                              Task 06 (omit) ─► Task 07 (importlinter) ─► Task 08 (env+gate)
```

- Task 04 depende de Task 03 (port existe antes do adapter; fake existe antes do
  real — `task-ordering-hex`).
- Task 05 depende de 03 (port) e 04 (`MlflowTracker` concreto a wirar).
- Task 06 depende de 02 e 05 (os módulos que saem do omit precisam de teste
  real exercitando-os, senão a cobertura cai).
- Task 07 só precisa do adapter existir (04) para ter o que blindar; posicionada
  após 06 para não interferir na medição de cobertura.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| `mlflow` não expõe resume-por-`run_id` de forma trivial | Encapsular o resume no adapter (`mlflow.start_run(run_id=...)`); se a API exigir `MlflowClient`, usar o client no adapter — o contract test prova o invariante I2 sem o teste conhecer a API; registrar `[decision]` se mudar a forma de inspeção |
| Tipo de erro "no active run" diverge entre `mlflow` e o fake (C2 não casa no `pytest.raises`) | Padronizar no contrato: capturar o erro do `mlflow` no adapter e re-levantar um tipo comum (ex.: `RuntimeError`), e o fake levanta o mesmo; o contract test usa esse tipo. Registrar `[decision]` |
| Contagem de runs para provar idempotência acopla o contract test à impl | Verificar idempotência pela identidade do `run_id` retornado + ausência de erro/duplicação ao reabrir, sem contar runs no backend; decidir na Task 04 e registrar `[deviation]` |
| Cobertura <90% em `composition_root.py`/`settings.py` ao sair do omit | Reforçar `test_composition_root.py`/`test_settings.py` exercitando o caminho real (não relaxar `fail_under`) |
| `mlflow` arrasta deps pesadas/lentas no CI | Backend SQLite local sem servidor; `tmp_path` no contract test; uso restrito a tracking (não serving) — concept §10 |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage (§4 contratos, §5
  invariantes, §6 casos de erro, §7 decisões)
- [`../../overview.md`](../../overview.md) — §6 (restrições), §7 (abordagem),
  §11 (ADR `0_0_0022`/`0_0_0023`)
- [`../../roadmap.md`](../../roadmap.md) — Stage `1.5-config-and-tracking`
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — branches, commits §4, status
- [`../../LAYOUT.md`](../../LAYOUT.md) — §3/§6 regras de import/camadas
- ADRs desta Stage: [`1_5_0001`](../../adr/1_5_0001-mlflow-sqlite-local-tracking.md)
  (MLflow SQLite local), [`1_5_0002`](../../adr/1_5_0002-experiment-tracker-port-shape.md)
  (forma do port)
- Stage 1.4 (consumida): [`../1.4-identity-and-fingerprints/concept.md`](../1.4-identity-and-fingerprints/concept.md)
- Skills aplicáveis: `composition-root`, `pytest-with-fakes`, `task-ordering-hex`,
  `hex-arch-python`, `import-linter-rules`
- Referência de padrão (1.4): `tests/contract/shared/test_hasher_contract.py`,
  `tests/fakes/shared/in_memory_hasher.py`

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas no Passo 10 do
> [`RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.
> Seção pode estar vazia se a execução não produziu notas relevantes.

**Formato de cada entrada** (ADR-like, ordem cronológica):

```markdown
### YYYY-MM-DD — [tag] escopo — Autor
**Contexto:** <o que foi encontrado durante a execução>
**Pergunta:** <o que precisava ser decidido>            <!-- só [decision] -->
**Opções:**                                              <!-- só [decision] -->
- A — <descrição>
- B — <descrição> ✅ recomendada
**Decisão:** B                                           <!-- só [decision] -->
**Razão:** <por que>
```

- `[decision]` — algo não previsto foi decidido durante a execução.
- `[finding]` — gap/observação a tratar em **próxima Stage**.
- `[deviation]` — ajuste pequeno aplicado vs. o plano original.

### 2026-06-29 — [decision] Task 04 — verificação de idempotência agnóstica de backend — Claude (autonomous)
**Contexto:** O contract test precisa provar I2 (idempotência por `run_id`) em `[fake, real]` sem acoplar o teste à API de contagem de runs de cada backend (risco previsto em §5).
**Pergunta:** Como verificar idempotência sem contar runs no backend?
**Opções:**
- A — contar runs via `MlflowClient.search_runs` (real) e `len(dict)` (fake): acopla o contrato à impl, exige hook de inspeção por backend.
- B — verificar pela IDENTIDADE do `run_id`: `start_run(run_id=r)` devolve `r` e um `log_metrics` no run reaberto não falha (prova run ativo/resumido). ✅ recomendada
**Decisão:** B
**Razão:** Mantém o contract test agnóstico (só usa o port), satisfeito identicamente por fake e real; o `mlflow.start_run(run_id=...)` resume o run (não cria outro) e o id devolvido idêntico + log sem erro provam o resume. Alinhado ao fallback pré-declarado na §5.

### 2026-06-29 — [decision] Task 04 — mapear "no active run" para `RuntimeError` no adapter — Claude (autonomous)
**Contexto:** C2 exige que `log_*`/`set_tags`/`log_artifact`/`end_run` sem run ativo falhem com o MESMO tipo observável no fake e no real, para o `pytest.raises` do contrato casar em ambos.
**Pergunta:** Como casar o tipo de erro entre `mlflow` e o fake?
**Opções:**
- A — deixar o `mlflow` decidir (abre run implícito em algumas chamadas; tipo divergente do fake).
- B — o adapter checa `mlflow.active_run() is None` ANTES de delegar e levanta `RuntimeError` (o fake levanta o mesmo). ✅ recomendada
**Decisão:** B
**Razão:** Pré-checar evita o comportamento implícito do `mlflow` (abrir run novo) e garante paridade C2. Simplificou o adapter (removido um context-manager guard que mapeava `MlflowException`), levando o módulo a 100% de cobertura sem branch defensivo morto.

### 2026-06-29 — [deviation] Task 03 — `.pre-commit-config.yaml`: ignorar ANN101/ANN102 no hook ruff pinado — Claude (autonomous)
**Contexto:** O hook `ruff-pre-commit` está pinado em `v0.6.9`, que ainda enforça `ANN101`/`ANN102` (anotação de `self`/`cls`) — regras DEPRECADAS e removidas no ruff corrente (`>=0.15`) que o projeto resolve em `make check`/`make lint` (gate autoritativo). Sem ajuste, o hook reprova o `FakeExperimentTracker` (e o `FakeHasher` já commitado na 1.4), divergindo do gate e do estilo já versionado.
**Razão:** Adicionado `args: [--fix, --extend-ignore, "ANN101,ANN102"]` SÓ ao hook pinado. Não toquei o pin (bumpar para 0.15 arrastaria reformatação de ~10 arquivos fora do escopo desta Stage, via `ruff-format` — churn indevido). `make check` (ruff local) permanece sem warning. Reversível: cai quando o pin for atualizado numa Stage de manutenção dedicada. Commit próprio (`build(pre-commit): ...`), fora da contagem de Tasks.

### 2026-06-29 — [finding] Task 06 — `mlflow.set_tracking_uri` muta `os.environ` (pollution entre testes) — Claude (autonomous)
**Contexto:** Ao tirar `config/*` do omit e rodar a suíte inteira, `test_defaults_include_mlflow_tracking_uri` falhou: `MlflowTracker.__init__` chama `mlflow.set_tracking_uri`, que escreve `os.environ["MLFLOW_TRACKING_URI"]` no processo; como `Settings(_env_file=None)` ainda lê `os.environ`, o `tracking_uri` em `tmp_path` do contract test vazava para o caso de default.
**Tratamento nesta Stage:** A fixture autouse dos testes de `Settings` passou a `monkeypatch.delenv("MLFLOW_TRACKING_URI"/"PORT")` antes de cada caso, isolando o ambiente. Em RUNTIME isso é inócuo: `Settings` é lido uma vez no boot (antes de qualquer tracker ser construído).
**A tratar adiante:** Quando a Stage 5.4 (`TrainTft`) ou testes de integração construírem `MlflowTracker` no mesmo processo que recarrega `Settings`, reavaliar se vale encapsular a leitura de `os.environ` (ex.: `Settings` com `env_ignore_empty`/origem explícita) — não bloqueante agora.

### 2026-06-29 — [decision] Task 04/Gitignore — ignorar `mlruns/` e `mlruns.db` — Claude (autonomous)
**Contexto:** O default `sqlite:///mlruns.db` cria `mlruns.db` na worktree; o `mlflow` materializa artefatos em `./mlruns/` (artifact root default) mesmo com o backend store em `tmp_path` (o contract test loga um artifact).
**Decisão:** Adicionados `mlruns.db` e `mlruns/` ao `.gitignore` (commit `chore(gitignore): ...`, fora da contagem de Tasks). Tracking é local e reconstruível (ADR 1.5.0001) — nada disso é versionado.

<!-- END: post-execution -->