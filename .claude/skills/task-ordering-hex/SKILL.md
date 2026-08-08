---
name: task-ordering-hex
description: Default ordering of Tasks within a Stage — TDD inside-out so each commit leaves the build green. Load on Fase 3B (synthesizing technical.md) and Fase 4 (execution) for vertical-slice Stages or Stages targeting domain or application.
metadata:
  status: draft
  applies_when:
    camada_alvo: [multi]
    stage_kind: vertical-slice
---

# Skill: Task ordering in Hexagonal (TDD inside-out)

Defines the **default order of Tasks** inside a Stage so every commit
leaves the build green and respects layer dependencies. Procedure
guidance — complements §4.3 of PIPELINE, which states the
**dependency rules** ("port before adapter, schema before migration")
but does not prescribe which layer to start from.

## Default order (vertical-slice Stage)

1. `domain/` — entities, value objects, invariants — **with unit tests in the same commit**.
2. `application/` — port out (`Protocol`) + use case + **in-memory fake** for the port + **use case test using the fake** — same commit or consecutive Tasks.
3. `adapters/out/<tech>/` — real implementation of the port + **contract test** proving the adapter satisfies the Protocol.
4. `adapters/in/<tech>/` — router/handler/CLI + **integration test** end-to-end.
5. `bootstrap/` — wiring in the composition root, replacing the fake with the real adapter.

## DO

- Every Task leaves the build green — lower layer + tests exist before upper layer that depends on it.
- Fakes before real adapters: use case is testable without external infra in CI.
- When the default does not apply, **declare the chosen order in the preamble of `technical.md`** with a short reason.

## DON'T

- Don't create a use case before the port out it consumes exists.
- Don't create the real adapter (Postgres, S3, HTTP client) before the in-memory fake exists and the use case is tested with the fake.
- Don't bundle port creation + adapter creation in the same commit (already a hard rule in §4.3). Exception only when both are trivial (1 method, wrapper) and declared in `technical.md`. **This rule only holds for a NEW port.** EXTENDING an existing `Protocol` forces every implementation (real adapter included) into the same commit — structural typing makes mypy reject the build until all implementers match the new shape. Plan the task radius accordingly.
- Don't apply the default blindly to Stages that are not vertical slices (see Exceptions).

## Exceptions (default does not apply)

| Stage kind | Natural order | Reason |
|---|---|---|
| Foundation / bootstrap (`1.1-bootstrap`, DI, logging, config) | Infra first: config → logging → DI container → health endpoint | No domain to start from; order driven by infra dependency. |
| Adapter-only on a consolidated BC (e.g., new S3 source on a BC whose `domain`/`application` are done) | Contract test on the existing port → adapter → wiring | `domain` and `application` already tested; reentering inside-out duplicates work. |
| Bug fix via Stage | Regression test on the broken layer → fix → revalidate adjacent layers | Order is driven by the defect, not by the dependency graph. |
| Schema / data migration | New schema → migration → updated adapter → use case (if changed) | Persistence first because it is the source of constraints. |

In any exception, **declare the chosen order and reason in the preamble of `technical.md`** (1–2 sentences).

## Example — vertical-slice Stage

Stage `2.1-create-order` in BC `orders`. `technical.md` produces:

```
task-01  feat(orders/domain): Order + OrderItem + invariants            [2.1/task-01]
         files:  src/orders/domain/order.py
                 src/orders/domain/order_item.py
                 tests/unit/orders/domain/test_order.py
         check:  pytest tests/unit/orders/domain/

task-02  feat(orders/application): port + use case + fake               [2.1/task-02]
         files:  src/myproject/features/orders/application/ports/out/order_repository.py
                 src/myproject/features/orders/application/use_cases/create_order.py
                 tests/fakes/features/orders/in_memory_order_repository.py
                 tests/unit/features/orders/application/test_create_order.py
         check:  pytest tests/unit/features/orders/application/

task-03  feat(orders/adapters/out): PostgresOrderRepository + contract  [2.1/task-03]
         files:  src/orders/adapters/out/postgres/order_repository.py
                 tests/contract/orders/test_postgres_order_repository.py
         check:  pytest tests/contract/orders/

task-04  feat(orders/adapters/in): POST /orders + integration test      [2.1/task-04]
         files:  src/orders/adapters/in/http/orders_router.py
                 tests/integration/orders/test_create_order_endpoint.py
         check:  pytest tests/integration/orders/

task-05  feat(orders/bootstrap): wire CreateOrder in composition root   [2.1/task-05]
         files:  src/bootstrap/composition.py
         check:  make check
```

After task-02 the Stage already has a verified use case even without Postgres running; reverting task-04 does not break the domain.

## Anti-example — outside-in bundle

```
task-01  feat(orders): POST /orders + Order + Postgres repo + use case
```

Mixes 4 layers in one commit. Use case has no isolated test. Port shape is shaped by SQL, not by the domain. Rollback impossible without losing the whole feature.

## Anti-example — adapter before fake

```
task-03  feat(orders/adapters/out): PostgresOrderRepository
task-04  feat(orders/application): CreateOrder use case + test against real Postgres
```

CI is now coupled to Postgres for a test that could be a unit test. Invert: fake in task-03, real adapter in task-04.
