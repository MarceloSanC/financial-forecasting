---
title: ADR 1.5.0002 — ExperimentTracker as a minimal structural Protocol that does not leak mlflow types
description: Architecture Decision Record
when-use: Reference before changing the ExperimentTracker port signature, adding methods, or letting mlflow (or any tracker library) types cross into the application layer
keywords: [adr, experiment-tracker, port, protocol, hexagonal, mlflow, run-id, idempotency, contract-test]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "1.5.0002"
decision: Define ExperimentTracker as a minimal structural Protocol (start_run/log_params/log_metrics(step)/set_tags/log_artifact/end_run) over primitive/Mapping types, with idempotency by run_id as a contract invariant and no mlflow types leaking into application
context_stage: 1.5-config-and-tracking
---

# ADR 1.5.0002 — ExperimentTracker as a minimal structural Protocol that does not leak mlflow types

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

Stage 1.5 introduces experiment tracking behind a hexagonal out-port. The
backend is MLflow with a local SQLite store (ADR 1.5.0001), but the application
layer must not depend on `mlflow`: the tracker must be swappable, testable with
an in-memory fake, and validated by a contract test shared between fake and real
(same posture as Stage 1.4 / ADR `0_0_0021`).

Forces and constraints:

- **Hexagonal rules of this Stage.** Ports are `Protocol`s (structural), not
  ABCs; the application tests with a **fake** of the port, adapters get a
  **contract test**; `domain/` stays stdlib-only; `mlflow` lives only in the
  adapter (`check_layout.py` + `import-linter` are the gate).
- **Downstream consumer is known.** Stage 5.4 (`TrainTft`) consumes
  `ExperimentTracker` (roadmap §Stage 5.4 `contratos_consumidos`). It needs to
  log params, metrics over training steps, tags, and model artifacts per run —
  nothing more for the pilot.
- **Domain semantics from the old repo.** The old Parquet analytics-store
  modeled run/params/metrics/artifacts as `dim_run`/`fact_config`/
  `fact_*_metrics`/`fact_model_artifacts` with **dedup by `run_id`**
  (`upsert_dim_run`, `parquet_analytics_run_repository.py:170-185`). That
  idempotency-by-`run_id` is the semantic to preserve — as a *contract*, not a
  Parquet detail.

## Decision

Define `ExperimentTracker` as a **minimal structural `Protocol`** in
`shared/application/ports/out/experiment_tracker.py`, exchanging only primitive
and `Mapping` types — **never** `mlflow` objects/types:

```python
from collections.abc import Mapping
from typing import Protocol

class ExperimentTracker(Protocol):
    def start_run(
        self, *, run_name: str | None = None, run_id: str | None = None
    ) -> str: ...
    def log_params(self, params: Mapping[str, object]) -> None: ...
    def log_metrics(
        self, metrics: Mapping[str, float], step: int | None = None
    ) -> None: ...
    def set_tags(self, tags: Mapping[str, str]) -> None: ...
    def log_artifact(self, path: str) -> None: ...
    def end_run(self) -> None: ...
```

Rationale for the signature:

- **`start_run` returns the active `run_id` (str).** When given an existing
  `run_id`, it **resumes** that run rather than creating a duplicate —
  **idempotency by `run_id`** is a contract invariant, verified by the contract
  test on both implementations.
- **Keyword-only `run_name`/`run_id` with defaults** so callers opt into either
  (name a fresh run, or resume by id) without positional ambiguity.
- **`log_metrics(..., step: int | None = None)`** carries the step dimension
  (training-step metrics) the old `fact_*_metrics` had.
- **`log_params(Mapping[str, object])`** accepts heterogeneous param values
  (the adapter stringifies for the backend); metrics are `float`, tags are
  `str`.
- **`log_artifact(path: str)`** takes a filesystem path; the adapter handles the
  backend upload. `end_run()` closes the active run.
- The exact translation to `mlflow` API calls (`set_tracking_uri`, `start_run`,
  `log_params`, `log_metrics`, `set_tags`, `log_artifact`, `end_run`, resume by
  `run_id`) is **adapter-internal**.

## Alternatives considered

### Alternative A — ABC mirroring the old AnalyticsRunRepository (dim/fact methods)

- **Description:** Port a class hierarchy (ABC) with ~8 methods matching
  `dim_run`/`fact_config`/`fact_*_metrics`/`fact_model_artifacts` and a
  `DuplicateKeyError`.
- **Pros:** 1:1 with the prior project's mental model.
- **Cons:** Couples the application to a medallion table schema; leaks the
  warehouse model into `application`; uses an ABC where this Stage mandates a
  structural `Protocol`; far larger surface than the consumer (5.4) needs.
- **Why rejected:** Violates the Protocol-not-ABC posture and the
  minimal-and-swappable principle; the dedup/idempotency semantics are kept as a
  *contract invariant* instead of a table-shaped API.

### Alternative B — Expose mlflow's run/context objects through the port

- **Description:** Let `start_run` return an `mlflow.ActiveRun` (or accept
  mlflow types).
- **Pros:** Less translation code in the adapter.
- **Cons:** `import mlflow` would cross into `application`; breaks
  swappability and the layer gate; the fake would have to fabricate mlflow
  objects.
- **Why rejected:** Directly violates invariant I4 (port must not leak
  `mlflow`); `import-linter`/`check_layout.py` would (correctly) fail.

### Alternative C — Do nothing / no port (call mlflow directly)

- **Why not acceptable:** Use cases would depend on `mlflow`, untestable without
  the real backend, non-swappable — defeats the hexagonal foundation Step 1
  exists to establish.

## Consequences

### Positive

- Application and use cases depend only on a tiny, primitive-typed `Protocol`;
  the tracker is swappable and fakeable.
- A single contract test guarantees fake↔real parity, including idempotency by
  `run_id`.
- The port surface matches exactly what Stage 5.4 needs — no speculative API.

### Negative

- The adapter carries translation glue (stringifying params, resume-by-`run_id`
  logic) instead of passing mlflow objects through.

### Neutral / trade-offs accepted

- We accept a deliberately small surface now; if a future consumer needs more
  (e.g. nested runs, metric history readback), the port grows under a new ADR.

## Implementation notes

- The fake (`tests/fakes/shared/in_memory_experiment_tracker.py`) stores runs/
  params/metrics/tags/artifacts in dicts keyed by `run_id`; resuming an existing
  `run_id` mutates the same entry (idempotency). The contract test
  (`tests/contract/shared/test_experiment_tracker_contract.py`) is parametrized
  over `[fake, real]` and asserts the same behavior for both.
- Operating on the active run without a prior `start_run` is an error condition
  (concept.md §6 C2): the adapter propagates mlflow's "no active run" error and
  the fake raises an equivalent state error.

## References

- Related ADRs:
  [1.5.0001 — MLflow SQLite local tracking](./1_5_0001-mlflow-sqlite-local-tracking.md);
  [1.4.0001 — canonical hashing](./1_4_0001-canonicalizacao-de-hash-deterministico.md);
  [0.0.0021 — per-unit contract tests with oracle](./0_0_0021-per-unit-contract-tests-with-oracle.md).
- Conversation/issue: GitHub issue #13.
- Old repo: `financial-time-series-forecasting/src/interfaces/analytics_run_repository.py`
  (ABC + `DuplicateKeyError`) and
  `.../adapters/parquet_analytics_run_repository.py:170-185` (`upsert_dim_run`
  dedup by `run_id`) — source of the run/params/metrics/artifacts + idempotency
  semantics migrated here from ABC→Protocol.
