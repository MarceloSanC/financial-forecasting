---
title: ADR 6.1.0004 — CoverageMetrics recomputes the degeneracy mask from its own series and embeds the DegeneracyReport, instead of accepting a mask from the caller
description: Architecture Decision Record
when-use: Reference when asking how calibration metrics know which rows are degenerate, why CoverageMetrics takes a tolerance instead of a DegeneracyReport, or how 6.3/6.4 should obtain the mask
keywords: [adr, evaluation, degeneracy-gate, coverage-metrics, mask, picp, mpiw, calibration, invariant]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.1.0004
decision: CoverageMetrics.evaluate(series, tolerance) and interval_widths(series, tolerance, pair) run DegeneracyGate.evaluate on the series they receive and embed the resulting DegeneracyReport in the CoverageReport; no service accepts a degeneracy mask from outside, so a mask computed for one series can never select rows of another.
context_stage: 6.1-scoring-and-calibration-metrics
bounded_context: evaluation
---

# ADR 6.1.0004 — Coverage metrics recompute the degeneracy mask

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Calibration and sharpness metrics (ĉ(τ), PICP, MPIW, per-row widths) use only
the non-degenerate rows (ADR 0.0.0011; domain doc §5.3 item 2). The first
draft of the 6.1 concept let `CoverageMetrics` receive a `DegeneracyReport`
and check only `n_points`/`horizon`. Checkpoint A found the hole: 6.4 builds
every model's series on the same exact `target_timestamp` intersection (doc
§6.7), so the report of model A has the same T, horizon and even timestamps
as the series of model B — the check passes and B's calibration is computed
on A's mask. Closing it with a check needs a fingerprint of the forecast
values.

The gate is a pure, deterministic O(T·K) function of the series and a
tolerance (ADR 6.1.0003), so recomputing it costs nothing measurable.

## Decision

- `CoverageMetrics.evaluate(series, *, tolerance)` and
  `CoverageMetrics.interval_widths(series, *, tolerance, pair)` call
  `DegeneracyGate.evaluate(series, tolerance=tolerance)` themselves.
- `CoverageReport` embeds the `DegeneracyReport` it used (`degeneracy` field),
  so the persisted calibration numbers carry the exact mask, rate and
  tolerance that produced them.
- `DegeneracyReport` validates its own invariants in `__post_init__`
  (mask and `target_timestamps` of length `n_points`, `n_degenerate == sum`,
  `rate == n_degenerate / n_points`) and carries the series' timestamps for
  audit.
- Other consumers that need the mask (6.3 hit sequences) call
  `DegeneracyGate.evaluate` on the same series with the preregistered
  tolerance — the gate is the single owner of the rule.

## Alternatives considered

### Alternative A — Accept a `DegeneracyReport`, check timestamps + a values fingerprint

- **Pros:** the gate runs once per series.
- **Cons:** the fingerprint is a second identity mechanism for the same data
  (identity belongs to the shared VOs, LAYOUT §7 / ADR 5.2.0004); more code,
  more tests, and still a way to pass the wrong object.
- **Why rejected:** recomputation removes the failure mode instead of
  detecting it.

### Alternative B — Accept a `DegeneracyReport`, check only `n_points`/`horizon` (first draft)

- **Why rejected:** does not detect model mix-ups on a common intersection.

### Alternative C — Store the mask inside `CoverageSeries`

- **Cons:** the series would depend on a tolerance that is a preregistration
  parameter, not a property of the data; one series would need re-building
  per tolerance sensitivity.
- **Why rejected:** couples the input VO to a gate parameter.

## Consequences

### Positive

- Mask/series mismatch is impossible by construction.
- Every `CoverageReport` is self-describing (tolerance, rate, mask).

### Negative

- The gate runs twice when a caller wants both the `DegeneracyReport` and the
  `CoverageReport` (negligible cost; the embedded report avoids the second
  call if the caller uses it).

## References

- Related ADRs: [0.0.0011](./0_0_0011-preregistration-invariants-and-h1-gate.md),
  [6.1.0002](./6_1_0002-coverage-series-aligned-input-vo.md),
  [6.1.0003](./6_1_0003-degeneracy-absolute-spread-tolerance.md).
- Domain doc: [`probabilistic-forecast-evaluation.md`](../domain/evaluation/probabilistic-forecast-evaluation.md) §5.3, §6.7.
- Checkpoint A (round 1) of Stage 6.1, finding M2.
