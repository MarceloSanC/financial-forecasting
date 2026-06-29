---
title: Concept — Stage 1.5 — Config tipada e tracking de experimentos
description: Evoluir Settings com tracking URI, introduzir o port ExperimentTracker + adapter MLflow (SQLite local) e evoluir o composition root para wirar Settings, Hasher e MlflowTracker
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; revisar antes de executar config/tracking/wiring
keywords: [concept, config-and-tracking, settings, pydantic-settings, mlflow, experiment-tracker, composition-root, wiring, sqlite]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 1.5-config-and-tracking
stage_title: Config tipada e tracking de experimentos
step_id: 1
step_title: Fundação e fitness arquitetural
depends_on: [1.4-identity-and-fingerprints]
---

# Concept — Stage 1.5 — Config tipada e tracking de experimentos

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.

## 1. Escopo

### Dentro do escopo

- **Evoluir `Settings`** (`pydantic-settings`, fronteira `infrastructure/config`):
  acrescentar o campo `mlflow_tracking_uri: str` (default `"sqlite:///mlruns.db"`),
  espelhado em `.env.example` (`MLFLOW_TRACKING_URI`), validando tipos no boot.
- **Introduzir o port-out `ExperimentTracker`** (`Protocol` em
  `shared/application/ports/out/experiment_tracker.py`): semântica mínima de
  tracking de experimentos — abrir/fechar run, logar params/metrics(step)/tags,
  logar artifact — com **idempotência por `run_id`** como invariante de contrato,
  **sem vazar tipos do `mlflow`**.
- **Adapter `MlflowTracker`** (`shared/adapters/out/mlflow/mlflow_tracker.py`):
  implementação concreta do port sobre a lib `mlflow`, com `tracking_uri` SQLite
  local vindo de `Settings`.
- **`FakeExperimentTracker`** in-memory (`tests/fakes/shared/`) que passa o
  **mesmo** contract test que o `MlflowTracker` (paridade fake↔real).
- **Unit test de `Settings`** (defaults, override por env, validação de tipo).
- **Evoluir `composition_root.py`**: instanciar `Settings`, `CanonicalJsonHasher`
  (consumido de 1.4) e `MlflowTracker`, expondo-os via `ApplicationDependencies`.
- **Adicionar a dependência `mlflow`** ao `pyproject.toml` (+ `uv.lock`).
- **CARRY da Stage 1.2:** remover de `[tool.coverage.run].omit` as entradas
  `*/composition_root.py` e `*/shared/infrastructure/config/*` — reentram na
  cobertura porque esta Stage as ativa com consumidor real.
- **ADR(s)** `1_5_NNNN` `accepted` registrando as decisões não-triviais.

### Fora do escopo (explicitamente)

- DVC, hydra, servidor MLflow remoto (apenas SQLite **local**) — `non_goals`
  do roadmap.
- Persistência silver e schemas (Stage 4.1); DuckDB gold (Step 6).
- Qualquer use case de feature/pipeline ou consumidor de treino do tracker
  (o `TrainTft` consome `ExperimentTracker` só na Stage 5.4).
- Configuração de logging (`shared/infrastructure/logging/*` já existe;
  permanece em `omit` — só alinhar se estritamente necessário).
- `clock.py`/`id_generator.py` permanecem em `omit` (sem consumidor real
  nesta Stage).

### Vínculo com o roadmap

Esta Stage fecha o **Step 1 — Fundação e fitness arquitetural**
([`roadmap.md`](../../roadmap.md) §Stage 1.5). Entrega as duas peças que
faltavam à fundação: **config tipada** (Settings espelhando `.env`, validada
no boot) e **tracking de experimentos** atrás de um port hexagonal, ativando
ao mesmo tempo o **composition root real** que consome a identidade
determinística da Stage 1.4 (`Hasher`). Desbloqueia a Stage 2.1
(`MedallionStore` consome `Settings`) e a Stage 5.4 (`TrainTft` consome
`ExperimentTracker`).

## 2. Objetivo da Stage

Ao fim desta Stage, `Settings` carrega config de `env`/`.env` validando tipos
no boot (tipo errado → `ValidationError`), e o `MlflowTracker` registra um run
local (backend SQLite) atrás do port `ExperimentTracker`, com um
`FakeExperimentTracker` in-memory passando exatamente o mesmo contract test
(incluindo idempotência por `run_id`), tudo wirado pelo `composition_root`.

## 3. Contexto e premissas

### Contexto

A fundação (Step 1) precisa de config tipada e de tracking de experimentos
antes de qualquer pipeline de dados/modelo. A Stage 1.4 entregou a identidade
determinística (`Hasher` + value objects `RunId`/`DatasetFingerprint`/
`ConfigSignature`/`SplitFingerprint`); esta Stage liga essa identidade ao
tracking: cada experimento é um *run* com `params`/`metrics`/`artifacts`,
rastreável por `run_id` e complementando os fingerprints da 1.4.

O **repo antigo** (`financial-time-series-forecasting`) **não usava MLflow**
(grep vazio) nem `pydantic-settings` — usava um *analytics-store* Parquet
manual (`parquet_analytics_run_repository.py`) e config via YAML+JSON
(`path_resolver.py`, `os.getenv("DATA_ROOT")`). Logo, MLflow e `Settings` são
**construção fresca** conforme overview ADR `0_0_0022`/`0_0_0023`. O old serve
**apenas como fonte da semântica de domínio** (run → `dim_run`; params →
`fact_config`; metrics com step → `fact_*_metrics`; artifacts →
`fact_model_artifacts`; **idempotência por `run_id`** =
`upsert_dim_run` dedup, `parquet_analytics_run_repository.py:170-185`), não de
implementação.

### Premissas

- A lib `mlflow` aceita `tracking_uri` SQLite local (`sqlite:///...`) como
  backend store sem servidor, e permite reabrir/atualizar um run existente por
  `run_id` (base para a idempotência).
- O `CanonicalJsonHasher` (adapter de 1.4) está disponível e estável para ser
  instanciado no composition root.
- `Settings` já tem `get_settings()` com `lru_cache`; o template do
  `composition_root` já aceita `wire_dependencies(settings: Settings | None)`.

### Dependências

- `1.4-identity-and-fingerprints`: o port `Hasher` e o adapter
  `CanonicalJsonHasher` são **consumidos** pelo `composition_root` (injeção do
  concreto no único lugar de wiring).

## 4. Contratos

### Introduzidos

- **`Settings`** (`value-object` de config — fronteira `infrastructure/config`)
  — EVOLUÍDO. Campos espelhando `.env.example` (`app_name`, `debug`,
  `database_url`, `host`, `port`, `log_level`) **+ NOVO**
  `mlflow_tracking_uri: str` (default `"sqlite:///mlruns.db"`). Valida tipos no
  boot (`pydantic`). `get_settings()` com `lru_cache` permanece.

- **`ExperimentTracker`** (`port-out`, `Protocol` em
  `shared/application/ports/out/experiment_tracker.py`) — INTRODUZIDO.
  Superfície mínima, tipos primitivos/`Mapping`, **sem importar `mlflow`**:

  ```python
  from collections.abc import Mapping
  from typing import Protocol

  class ExperimentTracker(Protocol):
      def start_run(
          self, *, run_name: str | None = ..., run_id: str | None = ...
      ) -> str: ...
      def log_params(self, params: Mapping[str, object]) -> None: ...
      def log_metrics(
          self, metrics: Mapping[str, float], step: int | None = ...
      ) -> None: ...
      def set_tags(self, tags: Mapping[str, str]) -> None: ...
      def log_artifact(self, path: str) -> None: ...
      def end_run(self) -> None: ...
  ```

  - `start_run` retorna o `run_id` ativo (string). Quando recebe um `run_id`
    existente, **reabre** o mesmo run em vez de criar outro (idempotência).
  - `log_*`/`set_tags` aplicam-se ao run ativo; chamá-los sem run ativo é
    caso de erro (ver §6).
  - A assinatura exata (kw-only, defaults, `step: int | None`) é fixada no
    [ADR 1.5.0002](../../adr/1_5_0002-experiment-tracker-port-shape.md).

- **`MlflowTracker`** (`adapter` em
  `shared/adapters/out/mlflow/mlflow_tracker.py`) — INTRODUZIDO. Implementa
  `ExperimentTracker` sobre `mlflow`, recebendo `tracking_uri` (SQLite local)
  de `Settings`. **Nunca** entra em `omit`; sempre conta cobertura + contract
  test.

- **`ApplicationDependencies` / `wire_dependencies(settings: Settings | None)`**
  (bootstrap) — EVOLUÍDO. `ApplicationDependencies` passa a expor
  `tracker: ExperimentTracker` e `hasher: Hasher`, instanciados no
  `composition_root` (único lugar que cria concretos).

### Consumidos

- **`Hasher`** (`port-out`) — declarado na Stage `1.4-identity-and-fingerprints`;
  o concreto `CanonicalJsonHasher` é instanciado no `composition_root`.

## 5. Invariantes e regras

- **I1 — Settings valida tipos no boot.** Carregar config de `env`/`.env`
  resolve cada campo no seu tipo declarado; valor de tipo inválido
  (ex.: `PORT="abc"`) levanta `ValidationError` na construção de `Settings`.
- **I2 — Idempotência por `run_id`.** Registrar o mesmo `run_id` duas vezes
  **não duplica** o run (reabre/atualiza, no-op de criação). Preservada e
  verificada **em ambas** as implementações pelo contract test. Herdada da
  semântica `dim_run`/dedup do old (`upsert_dim_run`).
- **I3 — Paridade fake↔real.** `FakeExperimentTracker` e `MlflowTracker` passam
  o **mesmo** contract test parametrizado (mesma postura da Stage 1.4 /
  ADR `0_0_0021`).
- **I4 — Port não vaza `mlflow`.** Nenhum `import mlflow` na camada
  `application`; o port troca apenas tipos primitivos/`Mapping`. `mlflow` vive
  só no adapter; `pydantic`/`pydantic-settings` só em `infrastructure/config`.
  `check_layout.py` + `import-linter` são gate.
- **I5 — Domínio permanece puro.** `domain/` continua stdlib-only; o
  `ExperimentTracker` é port de `application` e não recebe/devolve entidades de
  domínio.
- **I6 — Wiring centralizado, sem singleton global.** Concretos
  (`CanonicalJsonHasher`, `MlflowTracker`) são criados **apenas** no
  `composition_root`; testes injetam `Settings` fake com `tracking_uri` em
  `tmp_path` (sem depender do `lru_cache` global).
- **I7 — CARRY 1.2 (coverage).** `*/composition_root.py` e
  `*/shared/infrastructure/config/*` **saem do `omit`** e passam a contar
  cobertura (≥90%). O port `experiment_tracker.py` **não** entra em `omit`
  (port-out com consumidor + contract test). `clock.py`/`id_generator.py`/
  `logging/*` permanecem em `omit` (sem consumidor real nesta Stage).
- **I8 — Gates verdes.** `mypy --strict` e `ruff` verdes; `make check` e
  `make test` verdes; cobertura ≥90% nos módulos ativados.

## 6. Casos de erro e exceções

- **C1 — Tipo de config inválido.** `PORT` (ou outro campo) com valor não
  coercível ao tipo declarado → `pydantic_core.ValidationError` na construção
  de `Settings` (fail-fast no boot). Testado no unit de Settings.
- **C2 — `log_*`/`set_tags`/`log_artifact`/`end_run` sem run ativo.**
  Operação sobre o run ativo sem `start_run` prévio → erro (o adapter propaga o
  erro de "no active run" do `mlflow`; o fake levanta o mesmo tipo de erro de
  estado). O contrato declara que essas operações exigem um run ativo.
- **C3 — `start_run` com `run_id` inexistente no backend.** Tratado como abrir
  um run novo identificado por aquele `run_id` (não é erro); a idempotência é
  sobre *não duplicar* quando o mesmo `run_id` é reaberto, não sobre exigir
  pré-existência.
- **C4 — `log_artifact` com path inexistente.** Propaga o erro de I/O da
  implementação subjacente (não silencia). Borda fora do happy-path do contract
  test obrigatório; documentada no contrato.

## 7. Decisões técnicas relevantes

### D1 — Tracking = MLflow com backend SQLite local

- **O quê:** Adotar `mlflow` (dependência nova) com `tracking_uri` SQLite local
  (default `sqlite:///mlruns.db` via `Settings`), construído fresco. Rejeitadas:
  (a) manter o analytics-store Parquet manual do old; (b) servidor MLflow
  remoto; (c) W&B/Neptune (SaaS).
- **Por quê:** Pré-declarado no ledger §B (linha 1.5) e na tabela §11 do
  overview (ADR `0_0_0023`). MLflow local dá UI de comparação de *sweeps* +
  log de params/metrics/artifacts **sem SaaS nem servidor**, complementando
  `run_id`/fingerprints (1.4). SQLite é o backend local mais simples-e-trocável
  (trocar para Postgres/servidor depois só muda `tracking_uri`). O old não
  usava MLflow, então é construção fresca — serve só como fonte da semântica
  run/params/metrics + idempotência por `run_id`.
- **Fonte:** Overview §11 (`0_0_0023`) e §6; Ledger §A linha 1.5 e §B;
  old `parquet_analytics_run_repository.py:170-185`.
- **ADR:** [`../../adr/1_5_0001-mlflow-sqlite-local-tracking.md`](../../adr/1_5_0001-mlflow-sqlite-local-tracking.md)

### D2 — Forma do port `ExperimentTracker` (Protocol mínimo, sem vazar mlflow)

- **O quê:** `Protocol` em `application/ports/out` com superfície mínima
  (`start_run`/`log_params`/`log_metrics(step)`/`set_tags`/`log_artifact`/
  `end_run`), tipos primitivos/`Mapping`, **idempotência por `run_id`** como
  invariante de contrato; tradução para tipos do `mlflow` fica no adapter.
  Rejeitada: port ABC espelhando os ~8 métodos `dim/fact` do
  `AnalyticsRunRepository` antigo (acopla ao modelo de tabelas, vaza o esquema
  medalhão para a `application`, viola a postura Protocol-não-ABC).
- **Por quê:** O hexagonal da Stage exige `Protocol` estrutural testável por
  fake + contract test. A superfície mínima cobre o que a Stage 5.4 (`TrainTft`)
  precisa (params/metrics/artifacts por run) e é trocável sem tocar
  `application`. A idempotência por `run_id` replica a semântica de
  `dim_run`/dedup do old, agora como **contrato** e não detalhe de Parquet.
- **Fonte:** `hex-arch-python` / `pytest-with-fakes`; old
  `analytics_run_repository.py` + `parquet_analytics_run_repository.py:170-185`;
  roadmap §Stage 5.4 (`contratos_consumidos: [..., ExperimentTracker (1.5)]`).
- **ADR:** [`../../adr/1_5_0002-experiment-tracker-port-shape.md`](../../adr/1_5_0002-experiment-tracker-port-shape.md)

### D3 — composition_root consome Settings via `wire_dependencies(settings=None)`

- **O quê:** Manter a assinatura existente
  `wire_dependencies(settings: Settings | None)`; resolver
  `settings or get_settings()` e instanciar `CanonicalJsonHasher` e
  `MlflowTracker(settings.mlflow_tracking_uri)` **dentro** do `composition_root`
  (único lugar que cria concretos), expondo via `ApplicationDependencies`.
  Testes injetam `Settings` fake com `tracking_uri` em `tmp_path`.
- **Por quê:** Skill `composition-root` — wiring centralizado, sem singleton
  global; a injeção opcional de `Settings` já existe no template e permite teste
  determinístico (`tracking_uri` isolado por `tmp`). Decisão de baixo risco,
  alinhada ao bootstrap atual — não merece ADR próprio (segue a fundação já
  registrada).
- **Fonte:** `composition_root.py` atual (linha 33, assinatura já existente);
  skill `composition-root`.

### D4 — default do `mlflow_tracking_uri` = `"sqlite:///mlruns.db"`

- **O quê:** Default relativo `"sqlite:///mlruns.db"` no `Settings`,
  sobrescrevível por `MLFLOW_TRACKING_URI` no `.env`. Em testes o
  contract/wiring usa `sqlite:///<tmp_path>/mlruns.db` para isolamento.
- **Por quê:** SQLite local é o caminho mais simples para o piloto single-box;
  arquivo relativo mantém o tracking junto ao repo/worktree, trocável por env
  sem tocar código. Coberto pelo ADR 1.5.0001 — não exige ADR separado.
- **Fonte:** Overview §11 (`0_0_0023`); brief desta Stage.

## 8. Integrações

### Internas (com outras Stages/módulos)

- `shared/adapters/out/hashing` (1.4): o `composition_root` instancia
  `CanonicalJsonHasher` e o expõe como `Hasher`.
- `shared/infrastructure/config` (Settings): fornece `mlflow_tracking_uri` ao
  `composition_root`, que repassa ao `MlflowTracker`.
- `bootstrap` (`composition_root`): único ponto de criação de concretos.

### Externas

- **`mlflow`** (lib): backend store SQLite local via `tracking_uri`. Contrato
  esperado: criar/abrir run, logar params/metrics(step)/tags, logar artifact,
  encerrar run; reabertura por `run_id` sem duplicação. Sem servidor remoto,
  sem auth.

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| API do `mlflow` não expõe idempotência por `run_id` de forma trivial | M | M | Encapsular o reabrir-por-`run_id` no adapter (start_run com run_id existente → resume); contract test prova o invariante em ambas as impls; trocável sem tocar application |
| `mlflow` arrasta dependências pesadas/lentas no CI | M | B | Backend SQLite local sem servidor; usar tmp_path no teste; restringir uso a tracking (não serving) |
| Vazamento de tipo `mlflow` para a application | B | A | Port só com primitivos/`Mapping`; `check_layout.py` + `import-linter` barram import de `mlflow` fora do adapter |
| Cobertura <90% nos módulos que saem do omit | M | M | Unit de Settings + teste de `wire_dependencies` com Settings fake exercitando o caminho real; contract test cobre o adapter |

## 11. Critérios de aceitação

- [ ] **A1** — `Settings` tem `mlflow_tracking_uri: str` default
  `"sqlite:///mlruns.db"`, espelhado em `.env.example` (`MLFLOW_TRACKING_URI`);
  unit test cobre defaults, override por env e `ValidationError` em tipo
  inválido (`PORT="abc"`), limpando `get_settings.cache_clear()` entre casos.
- [ ] **A2** — `ExperimentTracker` existe como `Protocol` em
  `shared/application/ports/out/experiment_tracker.py` (stdlib/`typing` only,
  docstring PT declarando idempotência por `run_id`, **sem** `import mlflow`).
- [ ] **A3** — `MlflowTracker` implementa o port sobre `mlflow` com
  `tracking_uri` SQLite local; **não** está em `omit`; cobertura ≥90%.
- [ ] **A4** — `FakeExperimentTracker` in-memory passa o **mesmo** contract test
  parametrizado que `MlflowTracker`, cobrindo start/end, log_params,
  log_metrics(step), set_tags, log_artifact e **idempotência por `run_id`**.
- [ ] **A5** — `composition_root` expõe `tracker: ExperimentTracker` e
  `hasher: Hasher`; `wire_dependencies(settings)` instancia
  `MlflowTracker(settings.mlflow_tracking_uri)` e `CanonicalJsonHasher`; teste
  exercita o wiring com `Settings` fake (`tracking_uri` em `tmp_path`) e verifica
  tipos/instâncias.
- [ ] **A6** — `*/composition_root.py` e `*/shared/infrastructure/config/*`
  **removidos** do `[tool.coverage.run].omit`; `experiment_tracker.py` **não**
  está em `omit`.
- [ ] **A7** — `mlflow` em `[project].dependencies`; `uv.lock` sincronizado;
  `python -c "import mlflow"` ok.
- [ ] **A8** — `check_layout.py` + `import-linter` verdes (nenhum `import mlflow`
  fora do adapter); `mypy --strict` e `ruff` verdes; `make check` e `make test`
  verdes; cobertura ≥90% nos módulos ativados.
- [ ] **A9** — ADRs `1_5_0001` (MLflow SQLite local) e `1_5_0002` (forma do port)
  com `status: accepted`.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? (Settings,
  ExperimentTracker, MlflowTracker, ApplicationDependencies — §4)
- [x] Toda decisão em §7 tem fonte rastreável? (overview §11, ledger §A/§B,
  old paths, skills)
- [x] Toda integração externa tem contrato definido? (`mlflow` — §8)
- [x] Decisões com alternativa real descartada têm ADR escrito? (D1→1.5.0001,
  D2→1.5.0002)
- [x] Dependências de Stages anteriores estão satisfeitas? (1.4 `done`; Hasher
  disponível)
- [x] Stage cabe em ~3–8 Tasks? (8 Tasks no technical: deps → Settings →
  port+fake → adapter+contract → wiring → coverage-omit → import-linter →
  env+gate — dentro da faixa)
- [x] Riscos críticos têm mitigação plausível? (§10)
- [x] O port não vaza tipos do `mlflow` e o domínio permanece puro? (I4, I5)

## 13. Questões em aberto

- Nenhuma bloqueante. A semântica exata de "resume run por `run_id`" no `mlflow`
  é detalhe de implementação a fixar no `technical.md`/execução — o contrato
  (idempotência por `run_id`) já está declarado.

## 14. Referências

- [`../../overview.md`](../../overview.md) — §6 (restrições), §7 (abordagem),
  §11 (ADR `0_0_0022`/`0_0_0023`).
- [`../../roadmap.md`](../../roadmap.md) — Stage `1.5-config-and-tracking` e
  vizinhas (2.1, 5.4).
- [`../../autonomous-run-decision-ledger.md`](../../autonomous-run-decision-ledger.md)
  — §A linha 1.5, §B.
- ADRs desta Stage:
  [`1.5.0001`](../../adr/1_5_0001-mlflow-sqlite-local-tracking.md),
  [`1.5.0002`](../../adr/1_5_0002-experiment-tracker-port-shape.md).
- Stage 1.4 (consumida): [`../1.4-identity-and-fingerprints/concept.md`](../1.4-identity-and-fingerprints/concept.md);
  ADR [`1.4.0001`](../../adr/1_4_0001-canonicalizacao-de-hash-deterministico.md).
- Old (semântica de domínio, não implementação):
  `financial-time-series-forecasting/src/interfaces/analytics_run_repository.py`,
  `.../adapters/parquet_analytics_run_repository.py:170-185`.
