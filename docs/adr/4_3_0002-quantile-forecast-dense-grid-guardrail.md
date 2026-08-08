---
title: ADR 4.3.0002 — QuantileForecast as a dense quantile grid with a generalized monotonic guardrail
description: Architecture Decision Record
when-use: Reference whenever revisiting the shape of QuantileForecast (dense levels + raw_values) or the monotonicity-enforcement rule (sorted-along-levels, applied=order-changed), or its relationship to the degeneration gate
keywords: [adr, quantile-forecast, dense-grid, monotonic-guardrail, enforce-monotonic, value-object, degeneration-gate, h-1]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: 4.3.0002
decision: QuantileForecast é um VO frozen com levels crescentes + raw_values alinhados, e o guardrail força monotonicidade ordenando os valores ao longo dos níveis (sorted), marcando guardrail_applied quando a ordem muda; valores não-finitos/None são preservados sem aplicar
context_stage: 4.3-prediction-persister
bounded_context: analytics_store
---

# ADR 4.3.0002 — QuantileForecast as a dense quantile grid with a generalized monotonic guardrail

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

The probabilistic forecast is a set of quantiles. The previous project hard-coded
exactly three levels — p10/p50/p90 — and enforced monotonicity with
`enforce_monotonic_triplet(p10, p50, p90)`: it sorted the triplet, flagged
`applied` when the order changed, and **preserved** the values (no sort) when any
input was `None` or non-finite.

Two forces shape the new design:

1. **Dense grid.** The human decision H-1 (ledger) keeps the silver
   representation **long/grid-agnostic**, and the foundation decision
   `0_0_0012` densifies the quantile grid to ~7–9 levels (to enable richer
   CRPS/VaR/calibration). A fixed triplet no longer fits; the value object must
   carry an arbitrary ordered grid.
2. **Separation from the degeneration gate.** Monotonicity (q must be
   non-decreasing across levels) is a **persistence guardrail** that may
   reorder. The **degeneration gate** (`q_low == q_high`, a collapsed
   distribution) is a **quality/evaluation** concern that belongs to Step 6 and
   must **not** be masked by reordering. These are different checks and must not
   be conflated here.

## Decision

Introduce `QuantileForecast` as a frozen, stdlib-only value object:

- `levels: tuple[float, ...]` — strictly increasing, unique (e.g. `(0.1, 0.25,
  0.5, 0.75, 0.9)`).
- `raw_values: tuple[float, ...]` — aligned 1:1 to `levels`, the model's raw
  output per level.
- `guardrail_values: tuple[float, ...]` — the monotonicity-enforced values.
- `guardrail_applied: bool`.

A `from_raw(*, levels, raw_values)` factory validates `len(levels) ==
len(raw_values)`, and that `levels` is strictly increasing and unique, then runs
`enforce_monotonic`:

- **All finite:** `guardrail_values = tuple(sorted(raw_values))`;
  `guardrail_applied = (guardrail_values != raw_values)` — exactly the
  old "order changed" semantics, generalized from 3 to N levels.
- **Any non-finite / `None`:** preserve `raw_values` as `guardrail_values` and
  set `guardrail_applied = False` (the old defensive posture). The decision
  about whether such a forecast is acceptable is deferred to Step 6.

Sorting along the levels is total and correct for non-decreasing monotonicity,
and the triplet case (p10/p50/p90) reproduces `enforce_monotonic_triplet`
bit-for-bit. The guardrail **never** equalizes or rejects collapsed quantiles —
`q_low == q_high` passes through unchanged; the degeneration gate is Step 6.

## Alternatives considered

### Alternative A — keep the fixed p10/p50/p90 triplet
- **Description:** port `enforce_monotonic_triplet` as-is with three named fields.
- **Pros:** least change; matches the old code 1:1.
- **Cons:** cannot represent the dense grid required by H-1 / `0_0_0012`; would
  force a schema/VO migration when the grid densifies in Step 5.
- **Why rejected:** the dense grid is already decided; a triplet would need
  rework precisely when the modeling step lands.

### Alternative B — clamp/clip instead of sort (e.g. cumulative max)
- **Description:** enforce monotonicity by replacing each value with the running
  max so far, rather than sorting the whole grid.
- **Pros:** preserves the median position; arguably less disruptive per level.
- **Cons:** diverges from the old `sorted([a,b,c])` semantics (the triplet case
  would no longer reproduce the reference); two reasonable values could be
  "pulled up" asymmetrically; harder to reason about `applied`.
- **Why rejected:** `sorted` is the established, audited behavior; reproducing
  the old triplet exactly is a requirement, and sort is the simplest total order
  that does it. Clamping is a Step-6-grade modeling choice, not a persistence
  guardrail.

### Alternative C — do nothing (persist raw only, no guardrail)
- **Description:** store `value_raw` and skip monotonicity entirely.
- **Pros:** simplest.
- **Cons:** non-monotone quantiles break downstream pinball/calibration math and
  contradict the existing `PredictionRow` contract (4.1), which has
  `value_guardrail` + `guardrail_applied` columns.
- **Why rejected:** the guardrail is part of the 4.1 contract and of the H-1
  decision; raw-only would leave those columns unfillable.

## Consequences

### Positive
- One value object covers both the triplet (today) and the dense grid (Step 5)
  with no schema migration — more rows, never DDL (H-1).
- `guardrail_applied` semantics preserved 1:1 from the old service, keeping
  audit continuity.
- Monotonicity and degeneration stay cleanly separated; Step 6 owns the
  degeneration gate without fighting the guardrail.

### Negative
- `sorted` can reorder more than a minimal local fix in pathological inputs; the
  `applied` flag and the persisted `value_raw` keep this auditable.

### Neutral / trade-offs accepted
- Non-finite/`None` forecasts pass through un-guarded (defensive); their quality
  judgment is intentionally deferred to Step 6.

## Implementation notes

- `src/financial_forecasting/features/analytics_store/domain/value_objects/quantile_forecast.py`
  — frozen dataclass; imports only `dataclasses` and `math` (`isfinite`).
- `test_quantile_forecast_invariants.py` must cover: alignment/strictly-increasing
  validation, disordered grid → reordered + `applied=True`, already-monotone →
  `applied=False`, non-finite/`None` preserved + `applied=False`, and the
  triplet base case matching the old `enforce_monotonic_triplet`.

## References

- Related ADRs: [4.1.0002](./4_1_0002-fact-oos-predictions-long-quantile-format.md)
  (LONG format), [4.3.0001](./4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md)
  (target_timestamp + purity), `0_0_0012` (dense quantile grid, overview §11),
  `0_0_0011` (degeneration gate in the pre-registration — Step 6).
- Old repo: `src/domain/services/quantile_guardrail_service.py:18-60`
  (`enforce_monotonic_triplet`).
- Ledger: `docs/autonomous-run-decision-ledger.md` H-1.
