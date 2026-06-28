---
name: orchestrator-design
description: >
  Patterns for orchestrators / pipeline runners / entrypoints that sequence use cases and adapters
  WITHOUT embedding domain logic — idempotency/replay, deterministic failure-status, observability,
  side-effect ordering. Use when designing or refactoring a runner (main_*, CLI, scheduler, the
  walk-forward harness, gold builders) that spans multiple use cases/repos/adapters. Triggers (PT/EN):
  "orquestrador", "runner", "harness", "encadear use cases", "idempotência", "replay", "rerun seguro",
  "status parcial", "partial failure", "pipeline runner", "sequenciar etapas". Defers layer/import
  rules to hex-arch-python and wiring to composition-root.
metadata:
  status: draft
  applies_when:
    step: [2, 4, 5, 6, 7, 8]
    camada_alvo: [application, adapters/out]
---

# Orchestrator / Pipeline-Runner Design

An orchestrator **coordinates** — it sequences use cases and adapters and maps their outcomes to a
final status. It must hold **zero domain rules**: any calculation, gate, or business decision lives
in the domain/use case it calls. In this repo, orchestrators are the entrypoints and pipeline runners
(`main_*`, CLI, the walk-forward harness, gold builders, the confirmatory run) — the things that turn
a sequence of pure steps into a reproducible, auditable execution.

This skill owns **coordination semantics only**. It defers:
- import direction / layer boundaries → `hex-arch-python`
- where concrete instances are built → `composition-root`
- Task ordering inside a Stage → `task-ordering-hex`
- what counts as a valid result → `model-performance-and-research-advisor`

## Boundary rule (the one that matters)

The orchestrator may **branch, sequence, retry, and persist** — it may not **compute domain truth**.
If you find a metric, threshold, calibration check, or selection rule inside a runner, it's in the
wrong place: move it into a domain service / use case and have the runner call it. The runner only
decides *what to call next* and *what status to emit*.

## Idempotency & replay (non-negotiable for this project)

Decision artifacts must be reconstructible **without retrain**, so every runner that writes must be
safe to re-run:
- **Stable keys.** Key writes by `run_id` + `config_signature` + `split_fingerprint` (+ pré-registro
  hash for confirmatory runs). Re-running the same logical step with the same keys must not duplicate.
- **Duplicate-safe writes.** Upsert/append with the key, never blind insert; silver is append-only,
  gold is rebuildable — a rebuild must converge, not accumulate.
- **Resume emits a plan.** Before a resume/cleanup touches anything, emit a plan/report artifact;
  support a dry-run that performs **no** deletes. Cleanup must be idempotent.
- **Side effects after gates.** Order stages so validation/guards run *before* any persistence; never
  write then validate.

## Deterministic status model

Every runner returns an explicit, auditable final status — `ok` / `partial_failed` / `failed` (or the
project equivalent), with the stage→status mapping defined up front. Ambiguous "it kind of worked"
outcomes are a bug. A `partial_failed` must name which stages failed and which succeeded.

## Observability

Stage-level logs with: stage name, elapsed time, counts in/out, and an explicit failure reason on
error. The point is post-hoc auditability of a confirmatory run, not chatter — enough to reconstruct
*what ran, over what scope, with what result* from logs + persisted keys.

## Design checklist

1. Define the orchestration contract: inputs, outputs, ordered stages, final status model.
2. Map boundaries — confirm every domain decision sits in a use case, not the runner.
3. Implement flow: sequencing, branch conditions, retries/timeouts, compensation where needed.
4. Make it idempotent: stable keys, duplicate-safe writes, deterministic replay.
5. Add observability: per-stage logs + failure reasons.
6. Map stage outcomes → deterministic final status.
7. Cover with runner-focused tests (use fakes of out ports — see `pytest-with-fakes`).

## Common failures → fixes

- Runner computes a metric/threshold → move it into the domain/use case; runner just calls it.
- Side effect before a validation gate → reorder; guard before write.
- Retry produces duplicates → add idempotency key + upsert/append policy.
- Ambiguous final status → define explicit stage→status mapping.
- Resume/cleanup with no plan artifact → emit plan + report, support dry-run.

## When NOT to use

- A single isolated domain rule change (no cross-flow coordination).
- A pure adapter with no sequencing.
- Wiring-only questions (use `composition-root`).
