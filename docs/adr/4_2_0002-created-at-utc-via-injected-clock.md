---
title: ADR 4.2.0002 — Fill dim_run.created_at_utc at write-time via an injected Clock
description: Architecture Decision Record
when-use: Reference before adding write-time timestamp columns to silver tables, or before calling datetime.now() inside the analytics repository adapter
keywords: [adr, created-at-utc, clock, dim_run, write-time, run-record, determinism, fake-clock, pandera, nullable]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "4.2.0002"
decision: Fill dim_run.created_at_utc in the RunRecord->row mapper of ParquetAnalyticsRepository using a Clock injected via the constructor (SystemClock in production, FakeClock in tests), never a hardcoded datetime.now() in the adapter or the domain
context_stage: 4.2-silver-repository
---

# ADR 4.2.0002 — Fill dim_run.created_at_utc at write-time via an injected Clock

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

The Stage 4.1 schema for `dim_run` declares a column `created_at_utc` as
`string`, `nullable=False` (`dim_run_schema.py`). The domain value object that
carries a run's metadata, `RunRecord` (4.1, `run_record.py`), **does not** have a
`created_at_utc` field — by design, `RunRecord` is a frozen, stdlib-only VO whose
identity is the logical PK (`run_id`), and a creation timestamp is not part of
that identity. This was recorded as **OBS-1** in the 4.1 findings carried into
4.2.

Consequence: when `ParquetAnalyticsRepository` maps a `RunRecord` into a
`dim_run` row, the `created_at_utc` cell is missing, and the mandatory `pandera`
validation on write (`strict=True`, `coerce=False`) **fails**. The timestamp must
be produced somewhere at write-time.

Forces and constraints:

- **Domain purity.** `domain/` is stdlib-only and must not read the wall clock;
  `RunRecord` must not grow a non-identity, environment-derived field. A creation
  timestamp is a *write-time persistence concern*, naturally an adapter
  responsibility.
- **Determinism in tests.** A hardcoded `datetime.now()` in the adapter makes the
  written value non-deterministic, so the contract/integration tests could not
  assert the exact `created_at_utc` and the `pandera` round-trip would depend on
  wall-clock timing.
- **Existing infrastructure.** Stage 1.5 already provides a `Clock` port
  (`shared/application/ports/out/clock.py`, `now() -> datetime` UTC) and a
  `SystemClock` adapter (`shared/infrastructure/clock/system_clock.py`). The
  project's standing rule is that nothing calls `datetime.now()` directly — time
  is always obtained through an injected `Clock` (clock.py docstring).

## Decision

Fill `dim_run.created_at_utc` **in the `RunRecord -> row` mapper of
`ParquetAnalyticsRepository`**, using a **`Clock` injected via the adapter
constructor**. In production the composition root injects `SystemClock()`; in
tests a `FakeClock` returning a fixed UTC `datetime` makes the written value
deterministic. The adapter formats `clock.now()` as an ISO-8601 UTC `string`
(the column's declared dtype) at write-time. `datetime.now()` is **never** called
directly in the adapter or the domain.

`RunRecord` stays unchanged (no `created_at_utc` field). The fake repository
takes the same injected `Clock` so the contract test asserts identical
write-time behavior for fake and real.

## Alternatives considered

### Alternative A — Add `created_at_utc` to the `RunRecord` VO

- **Description:** Give `RunRecord` a `created_at_utc` field, populated by the
  caller before persistence.
- **Pros:** the row mapper becomes a pure field copy; no Clock in the adapter.
- **Cons:** pushes a non-identity, environment-derived timestamp into a frozen
  domain VO whose equality is by value — two otherwise-identical runs created at
  different instants would compare unequal; forces every caller to source the
  time; tempts the domain toward reading the clock.
- **Why rejected:** Violates the "VO identity = logical PK" principle (4.1 I9)
  and mixes a write-time concern into the domain.

### Alternative B — Hardcode `datetime.now(UTC)` in the adapter

- **Description:** The mapper calls `datetime.now(tz=UTC)` inline.
- **Pros:** zero wiring; no extra constructor argument.
- **Cons:** non-deterministic written value → tests cannot assert
  `created_at_utc` and become timing-dependent; directly violates the project
  rule that time comes through an injected `Clock`; would be the only place in the
  codebase reading the wall clock directly.
- **Why rejected:** Loses test determinism and breaks the standing Clock
  convention for zero benefit (the Clock already exists).

### Alternative C — Make `created_at_utc` nullable in the schema

- **Description:** Relax the column to `nullable=True` and leave it empty.
- **Pros:** no timestamp logic at all.
- **Cons:** changes the 4.1 contract (already `done`), loses audit information
  (when a run row was persisted), and defeats the purpose of the column.
- **Why rejected:** Would regress a ratified schema contract to avoid a trivial,
  already-available injection.

### Alternative D — Do nothing

- **Why not acceptable:** the `pandera` validation of `dim_run` fails on every
  write — the repository cannot persist `dim_run` at all.

## Consequences

### Positive

- `dim_run` validates and persists; `created_at_utc` is deterministic in tests
  (`FakeClock`) and real in production (`SystemClock`).
- Domain stays pure: `RunRecord` carries no environment-derived field; the
  timestamp is an explicit adapter (write-time) concern.
- Zero new infrastructure — reuses the `Clock`/`SystemClock` from 1.5.

### Negative

- The adapter (and the fake) gains a `clock` constructor argument and a small
  mapper responsibility (formatting the timestamp), slightly widening their API.

### Neutral / trade-offs accepted

- `created_at_utc` is a write-time stamp, not the logical run-creation time from
  any upstream system; acceptable for the audit purpose of the column. If a
  source-of-truth creation time becomes needed, it would be a new column fed by
  the caller under a new ADR.

## Implementation notes

- Inject `clock: Clock` into `ParquetAnalyticsRepository.__init__` and into
  `FakeAnalyticsRepository`; the composition root wires `SystemClock()`.
- The mapper applies only to `dim_run` (the only table with a write-time
  `created_at_utc`); other tables map their payload columns straight through.
- Format: `clock.now()` (tz-aware UTC) serialized to an ISO-8601 `string` to match
  the column dtype (`coerce=False` means the adapter must produce the exact type).

## References

- Related ADRs:
  [4.2.0001 — AnalyticsRepository port shape + dedicated Parquet adapter](./4_2_0001-analytics-repository-port-shape-and-dedicated-parquet.md);
  [4.1.0001 — silver schema per table](./4_1_0001-analytics-store-silver-schema-per-table.md)
  (where `dim_run.created_at_utc` and `RunRecord` were defined, raising OBS-1);
  [1.5.0002 — ExperimentTracker port shape](./1_5_0002-experiment-tracker-port-shape.md)
  (same injected-port, no-direct-side-effect posture).
- Code: `features/analytics_store/adapters/out/parquet/schemas/dim_run_schema.py`
  (`created_at_utc`, `nullable=False`);
  `features/analytics_store/domain/value_objects/run_record.py` (no
  `created_at_utc`); `shared/application/ports/out/clock.py`;
  `shared/infrastructure/clock/system_clock.py`.
- Conversation/issue: GitHub issue #36; 4.1 findings OBS-1.
