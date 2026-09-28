---
title: ADR 6.1.0005 — A new port-out lands with a one-Task port-coverage baseline entry, removed by the Task that adds its first real adapter
description: Architecture Decision Record
when-use: Reference when a Stage creates a NEW port-out and must keep every Task commit green under the port-coverage gate (T1) while PIPELINE §4.3 forbids creating the port and its adapter in the same Task
keywords: [adr, evaluation, port-coverage, arch-baseline, task-ordering, tdd-inside-out, scoring-backend, tiered-gates]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.1.0005
decision: The Task that creates the ScoringBackend port, its fake and the fake leg of its contract suite also adds a `[[port_coverage.allow]]` entry for `ScoringBackend` in scripts/arch_baseline.toml (motivo + issue 77) and widens the exact-baseline assertion of tests/architecture/test_port_coverage_gate.py to ["Hasher", "ScoringBackend"]; the very next Task, which adds the first real adapter (SklearnScoring) and its contract leg, reverts both — the dead-baseline rule of the gate and the exact-list assertion force the reversal.
context_stage: 6.1-scoring-and-calibration-metrics
bounded_context: evaluation
---

# ADR 6.1.0005 — Transient port-coverage baseline entry between a new port and its first adapter

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 6.1 creates a new port-out, `ScoringBackend` (ADR 6.1.0001), with a fake
and two real adapters. Three project rules meet in the Task plan:

- **PIPELINE §4.3 item 4** — a Task does not create a port and an adapter of
  that port together; the only exception is a trivial port (one method, one
  wrapper adapter). `ScoringBackend` has three methods and two non-trivial
  adapters, so the exception does not apply. Item 5 also asks for the fake
  (and the tests that use it) before the real adapter.
- **RUNBOOK §Gates em camadas (ADR 0.0.0055)** — every Task commit must pass
  T1 (`make check-task`), and T1 runs `scripts/check_port_coverage.py`;
  "T1 vermelho bloqueia o commit".
- **`check_port_coverage.py` (issue #62)** — a `Protocol` under
  `application/ports/out/` without a real adapter citing it, or without a
  `[fake, real]` contract module, is a violation. Known violations live in
  `scripts/arch_baseline.toml` with `motivo` and `issue`; an entry whose
  violation no longer occurs also fails the gate ("baseline morto").

The first two rules make the commit that holds the port and the fake, and no
adapter, unavoidable; the third makes that commit red. No Stage met this
before: every port-out of the repo predates the gate (issue #62, 2026-09-14),
and the only later port change (#68) moved ports whose adapters already
existed.

## Decision

The port Task (port + `FakeScoringBackend` + contract suite with the `fake`
leg) adds

```toml
[[port_coverage.allow]]
key = "ScoringBackend"
motivo = "..."   # port created one Task before its first real adapter (ADR 6.1.0005)
issue = 77
```

to `scripts/arch_baseline.toml`, and, in the same commit, changes the exact
assertion of `test_real_repo_violations_are_exactly_the_declared_baseline`
(`tests/architecture/test_port_coverage_gate.py`, today `violating ==
["Hasher"]`) to `["Hasher", "ScoringBackend"]`, with a comment citing this
ADR. Without the second edit `make check` stays red, because that test pins the
repo's violating ports to the baseline.

The very next Task, which creates `SklearnScoring` and its contract leg,
reverts **both** edits in its commit: it deletes the TOML entry and restores
`["Hasher"]`. Neither reversal can be forgotten: the gate fails on a dead
entry, and the exact-list assertion fails on a stale list. Any Task that does
not need the port (e.g. adding the dependencies the adapters use) goes
**before** the port Task, so the window is exactly one commit, inside one
branch; `develop` never sees the entry.

Both Tasks touch a gate file and `tests/architecture/`, so both run T3
(`make check`) instead of T1, as the RUNBOOK requires.

## Alternatives considered

### Alternative A — Port and first adapter in the same Task

- **Description:** one Task creates the port, the fake, the suite and
  `SklearnScoring`.
- **Pros:** no baseline touch; one T3 run fewer.
- **Cons:** breaks PIPELINE §4.3 item 4 for a non-trivial port; the port shape
  is no longer reviewed on its own, before a library shapes it (skill
  `task-ordering-hex`, anti-example "outside-in bundle").
- **Why rejected:** the docs allow the bundle only for a trivial port.

### Alternative B — Adapter before port

- **Description:** create `SklearnScoring` first (it satisfies the Protocol by
  duck typing), then the port, fake and suite citing it.
- **Pros:** every commit green without a baseline.
- **Cons:** the adapter is written against a contract that does not exist yet
  and before the fake (PIPELINE §4.3 item 5; skill `task-ordering-hex`
  "Don't create the real adapter before the in-memory fake exists").
- **Why rejected:** inverts the ordering rule the docs fix.

### Alternative C — Commit the port Task with T1 red on port-coverage

- **Why rejected:** "T1 vermelho bloqueia o commit" (RUNBOOK); a red commit
  in the history breaks bisect and the per-Task revert guarantee.

## Consequences

### Positive

- Every commit of the Stage passes its gate; both ordering rules hold.
- The debt is visible (motivo + issue in the baseline) and self-expiring (the
  dead-baseline rule).

### Negative

- Two Tasks run T3 (~20 min each) because they touch a gate file.

### Neutral / trade-offs accepted

- The pattern is reusable by any later Stage that creates a non-trivial
  port-out; this ADR is its precedent, not a general permission — the entry
  must be removed by the very next adapter Task.

## Implementation notes

- Stage 6.1 technical: Task 08 adds the dependencies, Task 09 creates the port
  and adds the entry + widens the assertion, Task 10 adds `SklearnScoring` and
  reverts both.
- Files touched in Tasks 09 and 10: `scripts/arch_baseline.toml` and
  `tests/architecture/test_port_coverage_gate.py`
  (`test_real_repo_violations_are_exactly_the_declared_baseline`).
- The `motivo` text and the test comment cite this ADR; `issue = 77`.
- Exit check of the Stage: `grep -n ScoringBackend scripts/arch_baseline.toml
  tests/architecture/test_port_coverage_gate.py` finds nothing.

## References

- [PIPELINE §4.3](../PIPELINE.md); [RUNBOOK-STAGE-LIFECYCLE §Gates em camadas](../RUNBOOK-STAGE-LIFECYCLE.md);
  [LAYOUT §7](../LAYOUT.md) (port-coverage rule).
- Related ADRs: [0.0.0055](./0_0_0055-tiered-quality-gates.md),
  [6.1.0001](./6_1_0001-scoring-libraries-as-oracle-backend-behind-port.md).
- `scripts/check_port_coverage.py`, `scripts/arch_baseline_lib.py`
  (`reconcile`: new and dead entries both fail).
