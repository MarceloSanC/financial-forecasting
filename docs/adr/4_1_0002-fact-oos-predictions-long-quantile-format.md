---
title: ADR 4.1.0002 — Store fact_oos_predictions in a long, grid-agnostic quantile format
description: Architecture Decision Record
when-use: Reference whenever touching the fact_oos_predictions schema, the quantile representation, or the prediction persister (Stage 4.3)
keywords: [adr, fact-oos-predictions, quantile, long-format, grid-agnostic, H-1, pandera]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: 4.1.0002
decision: fact_oos_predictions stores one row per quantile level (quantile_level in the PK, with value_raw/value_guardrail/guardrail_applied), forbidding hardcoded per-quantile columns.
context_stage: 4.1-silver-schema-per-table
bounded_context: analytics_store
---

# ADR 4.1.0002 — Store fact_oos_predictions in a long, grid-agnostic quantile format

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

The previous repository hardcoded the quantile grid into
`fact_oos_predictions` as fixed columns
`quantile_p10/p50/p90` plus `quantile_p10_post_guardrail/p50/p90` and a
`quantile_guardrail_applied` flag
(`financial-time-series-forecasting/src/infrastructure/schemas/analytics_store_schema.py:393-399`).
This wide layout pins the grid to exactly 3 levels at the schema level: moving
to a denser grid (~7–9 levels — overview ADR 0_0_0012) would require a DDL/schema
migration and rewriting every reader.

Two project-level decisions constrain this Stage:

- **Human decision H-1 (closed, immutable)** — decision ledger line 27: the
  silver quantile representation is **long / grid-agnostic**:
  `(quantile_level, value_raw, value_guardrail)`; the schema must **not** bind
  the dense grid. The exact grid (~7–9) is fixed later, in Step 5.
- **Stage 4.1 DoD** — schemas must not block growth; the wide 3-column layout
  is precisely the growth-blocking anti-pattern to correct.

The choice within "long" is between a **long row-per-quantile** layout and a
**JSON-array** column holding all levels per prediction.

## Decision

`fact_oos_predictions` uses the **long, grid-agnostic** format: **one row per
quantile level**, with `quantile_level` as part of the logical PK and the
value columns `value_raw`, `value_guardrail`, `guardrail_applied`. The full
logical PK is
`(run_id, split, horizon, timestamp_utc, target_timestamp_utc, quantile_level)`;
partitioning is `(asset, feature_set_name, year)`; `update_policy` is
`append-only`.

It is **forbidden** to port the old per-quantile columns
(`quantile_p10/p50/p90` and their `_post_guardrail` variants). The grid is data,
not schema: adding or changing quantile levels in Step 5 adds rows, never
columns.

The anchor columns `decision_idx`, `timestamp_utc`, `target_timestamp_utc`
remain in the schema as the contract (mechanical > procedural, per the old
ADR-0003), but the off-by-one fill logic belongs to Stage 4.3, not here.

## Alternatives considered

### Alternative A — Wide, hardcoded per-quantile columns (the old layout)

- **Description:** `quantile_p10/p50/p90 (+_post_guardrail)` columns as in the
  old repo.
- **Pros:** One row per (run, split, horizon, timestamp); fewer rows; familiar.
- **Cons:** Pins the grid in the schema; moving to ~7–9 levels needs a
  migration and reader changes; directly violates H-1.
- **Why rejected:** Forbidden by the closed human decision H-1; reproduces the
  growth-blocking anti-pattern this Stage corrects.

### Alternative B — JSON-array column (all levels serialized per prediction row)

- **Description:** One row per prediction with a `quantiles_json` column
  holding the level→value map.
- **Pros:** Grid-agnostic; one row per prediction.
- **Cons:** Not queryable/partitionable per level without deserialization;
  `pandera` can only validate the blob as a string, not cell-by-cell;
  aggregation by quantile level (the whole point for calibration/pinball) needs
  unpacking.
- **Why rejected:** Long is equally grid-agnostic but stays queryable,
  partitionable, and validatable per cell. The only cost of long over
  JSON-array is more rows and one extra PK column — both cheap.

### Alternative C — Do nothing / defer the table

- **Description:** Leave `fact_oos_predictions` undefined until Step 5 fixes the
  grid.
- **Why rejected:** Steps 1–4 consume this table (it is in the §B 4.1 defined
  set); the long format is exactly what lets us define it now without knowing
  the final grid.

## Consequences

### Positive

- The dense grid (~7–9) is decided in Step 5 with **zero schema migration** —
  more rows, no DDL.
- Each (level, value) is validatable cell-by-cell by `pandera` (`strict=True`).
- Queryable/partitionable per quantile level for calibration and pinball
  analysis downstream.

### Negative

- More rows than the wide layout (one per level instead of one per prediction).
- `quantile_level` adds one column to the logical PK.

### Neutral / trade-offs accepted

- We accept row multiplication as the price of a grid that changes without DDL.
- `value_raw` vs `value_guardrail` separation keeps both the model output and
  the monotonicity-corrected value auditable per level.

## Implementation notes

- `quantile_level` recommended as `float64` (numeric level, e.g. `0.1`,
  `0.5`, `0.9`); `guardrail_applied` as `int64` flag (mirror old
  `quantile_guardrail_applied`); finalized in `technical.md` §2.
- Tests must assert both the **presence** of `quantile_level` in the PK and the
  **absence** of any `quantile_p*` column (regression guard against reverting
  to the wide layout).

## References

- Related ADRs:
  [4.1.0001](./4_1_0001-analytics-store-silver-schema-per-table.md)
  (schema-per-table + registry).
- External / repo: old
  `financial-time-series-forecasting/src/infrastructure/schemas/analytics_store_schema.py:393-399`
  (wide layout being replaced); old
  `ADR-0003-multi-horizon-prediction-persister.md` (anchor / `decision_idx`
  convention).
- Decision ledger: H-1 (line 27), §B 4.1 (line 42), §B 4.3 (line 44).
