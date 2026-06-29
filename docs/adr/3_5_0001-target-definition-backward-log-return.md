---
title: ADR 3.5.0001 — TargetDefinition is the single owner of the backward 1-step log-return target, indexed by decision_day and aligned with the 4.3 target_timestamp convention
description: Architecture Decision Record
when-use: Reference before changing the target formula or convention, before relocating target computation out of the pure domain service, or before defining target_timestamp in the prediction persister (4.3)
keywords: [adr, target, log-return, backward, decision-day, target-timestamp, off-by-one, domain-service, single-owner, anti-leakage, feature-engineering]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "3.5.0001"
decision: target_return[t] = log(close_t / close_{t-1}) computed BACKWARD; the first row is dropped; the pure domain service TargetDefinition is the single owner of the target; the convention is fixed at the source to align with the 4.3 target_timestamp (timestamp_utc = decision_day), removing the off-by-one that caused a bug in the old project
context_stage: 3.5-dataset-builder-and-contracts
---

# ADR 3.5.0001 — Backward log-return target with a single owner

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

The TFT dataset needs a prediction target: the daily return. Two facts shape the
decision.

1. **Anti-leakage is non-negotiable and the target is log-return** — fixed by the
   foundational ADR `0.0.0018` (rule 5) and the human-closed decision ledger entry
   B-4.3. The target convention must be causal and unambiguous.
2. **A real off-by-one bug happened in the old project.** The old ADR-0003
   (resolution R-20, option *d*) had to *correct* how the decision day maps to the
   predicted return. The fix: index by the decision day, with
   `timestamp_utc = decision_day` and `target_timestamp_utc =
   dataset_timestamps[decision_idx + h]`, and a *backward* `target_return`. With a
   backward target, the `pytorch_forecasting` decoder cell at position `D+h`
   naturally yields `log(close[D+h] / close[D+h-1])`; for `h=1` that is the
   "next-day return after decision" semantics required.

In the old code the target was computed **inline** inside a monolithic build use
case (`build_tft_dataset_use_case.py:563-572`), mixed with assembly, validation
and the quality gate. There was no single, testable owner of the convention, and
two stages (3.5 dataset build and 4.3 prediction persistence) had to agree on the
exact indexing — the very thing that drifted and produced the bug.

Forces:
- The convention must be **identical** on both sides (dataset build here, and the
  `target_timestamp` the persister in 4.3 will write) or the off-by-one returns.
- The hexagonal rules require the dataset-build target to be reproducible in a
  **pure** layer (stdlib-only), independent of pandas, so it can be unit-tested in
  isolation and re-derived as an oracle.

## Decision

Define the target as `target_return[t] = log(close_t / close_{t-1})`, computed
**backward**, with `target_return[0] = None` and the first row dropped at assembly
(because `log(close_0 / close_{-1})` is undefined). The day at index `t` is the
**decision day**: a row carries the features known *as of* `decision_day` and the
backward return realized into that day; downstream the persister (4.3) maps
horizon `h` to `target_timestamp = dataset_timestamps[decision_idx + h]`, so the
two conventions are the same convention stated once.

Make this the responsibility of a **single owner**: a pure domain service
`TargetDefinition` (`domain/services/target_definition.py`), stdlib-only, taking a
`Sequence[float]` of timestamp-ordered closes and returning a position-aligned
`tuple[float | None, ...]`. No other module computes the target. The assembler
(adapter) only *applies* it to the assembled close column and drops the leading
`None` row; the persister (4.3) *consumes* the same convention for
`target_timestamp`.

This both decomposes the old monolith (target out of the inline build) and fixes
the off-by-one **at the source** by giving the convention one authoritative,
testable definition that both stages reference.

## Alternatives considered

### Alternative A — Forward return target (`log(close_{t+1}/close_t)`)
- **Description:** index each row by the day whose *next* return it predicts.
- **Pros:** intuitive "this row predicts tomorrow".
- **Cons:** the last row has no target (drop tail instead of head — symmetric
  cost), and — critically — it does **not** match the `pytorch_forecasting`
  decoder semantics the old code converged on; re-introduces the exact mapping
  ambiguity R-20 fixed. **Why rejected:** contradicts the closed convention
  (ledger B-4.3 / old ADR-0003 option *d*) and risks the off-by-one again.

### Alternative B — Keep the target inline in the build use case (status quo of the old)
- **Description:** compute `np.log(close/close.shift(1))` inside `BuildDataset`.
- **Pros:** least code; matches old verbatim.
- **Cons:** no single testable owner; pandas in the path makes the convention
  hard to unit-test in isolation; the 4.3 persister would have to re-encode the
  same convention independently — the drift that caused the bug. **Why rejected:**
  violates the single-owner goal and the hexagonal purity rule; perpetuates the
  cross-stage duplication.

### Alternative C — Do nothing / status quo
Not acceptable: there would be no authoritative target definition, two stages
would re-implement the indexing independently, and the off-by-one class of bug
stays open.

## Consequences

### Positive
- One authoritative, pure, unit-testable definition of the target convention.
- 3.5 and 4.3 reference the same convention → off-by-one cannot drift between them.
- Stdlib-only service is trivially used as a re-derivation oracle in tests.

### Negative
- A tiny extra indirection (service call) versus the inline one-liner of the old.
- The first row is always dropped — slightly fewer rows than the raw candle count
  (already true in the old; preserved for oracle parity).

### Neutral / trade-offs accepted
- The backward convention is non-obvious ("this row's target is the return *into*
  this day"); documented here and in the concept (I1) so consumers (4.3) read it
  once.

## Implementation notes

- `target_definition.py`: stdlib-only (`math.log`), `Sequence[float] ->
  tuple[float | None, ...]`, `target[0] = None`.
- The assembler applies it to the assembled close column **after** sorting by
  timestamp and **before** the quality gate; drops the leading `None` row.
- 4.3 (`multi_horizon_prediction_persister.py`) must read this ADR before
  defining `target_timestamp` (`timestamp_utc = decision_day`).

## References

- Related ADRs: `0.0.0018` (anti-leakage / log-return target), `3.4.0001`
  (pure causal oracle).
- Decision ledger: B-4.3 (`docs/autonomous-run-decision-ledger.md`).
- Old: `src/use_cases/build_tft_dataset_use_case.py:563-572`; old ADR-0003 (R-20,
  option *d*); old `src/domain/services/multi_horizon_prediction_persister.py`.
