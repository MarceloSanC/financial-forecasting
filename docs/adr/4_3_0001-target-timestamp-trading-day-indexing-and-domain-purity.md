---
title: ADR 4.3.0001 — target_timestamp indexed by trading day; pure stdlib domain (no pandas)
description: Architecture Decision Record
when-use: Reference whenever revisiting why target_timestamp is indexed against the dataset session array (not a calendar timedelta nor TradingCalendar.shift), or why the persister carries no pandas dependency
keywords: [adr, target-timestamp, trading-day-indexing, off-by-one, gap-6, domain-purity, multi-horizon-persister, iso-string]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: 4.3.0001
decision: target_timestamp_utc é dataset_timestamps[decision_idx + h] indexado pelo array de sessões (nunca timedelta de calendário nem TradingCalendar.shift), e o domain service trafega timestamps como str ISO importando só stdlib
context_stage: 4.3-prediction-persister
---

# ADR 4.3.0001 — target_timestamp indexed by trading day; pure stdlib domain (no pandas)

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

`fact_oos_predictions` rows must anchor two timestamps per prediction:
`timestamp_utc` (the decision day) and `target_timestamp_utc` (the day the
h-ahead return is realized). In the previous project this convention lived
**distributed and divergent** across two call-sites, producing the most
expensive bug of that codebase:

- The TFT trainer used the **decoder_end_day** as `timestamp_utc`; the baseline
  runner used the **decision_day**. For the same `target_timestamp_utc` at h=1,
  **0 of 685** rows had matching `y_true` between the two pipelines (Gap 6).
- Both computed `target_ts = decision_ts + pd.Timedelta(days=h)` — a
  **calendar** timedelta on a dataset whose rows are **trading sessions** (no
  weekends/holidays). This is the secondary bug E4: a Friday + 1 calendar day
  lands on Saturday, which is not a session, silently shifting the target.

The old `ADR-0003` (Stage R-20, option d) fixed this by fixing the canonical
convention in a single domain service. Porting it, two forces are in play here:

1. **What is the source of truth for "the next trading day"?** The dataset
   timestamp array (already a trading-day grid) vs. an explicit
   `TradingCalendar.shift(decision_day, +h)` (2.4). The persister is a hot,
   per-row operation; coupling it to `TradingSessions` adds an injected
   dependency to a domain service.
2. **Domain purity.** The old service `import pandas as pd` only to call
   `pd.Timestamp(...).isoformat()`. `LAYOUT.md` §3 forbids pandas/pyarrow/torch
   in the domain layer; the new analytics_store domain is gated by
   import-linter (domain-purity) and `scripts/check_layout.py`.

## Decision

**(i) Index the dataset session array directly.** `MultiHorizonPredictionPersister.build`
sets `timestamp_utc = dataset_timestamps[decision_idx]` and
`target_timestamp_utc = dataset_timestamps[decision_idx + h]`, where
`dataset_timestamps` is the dataset's **trading-day grid** (resolved upstream by
the layer that owns 2.4). The "+ h" is an **array index**, i.e. h **sessions**
forward — never `pd.Timedelta(days=h)` and never a `TradingCalendar.shift` call
from inside the service. When `decision_idx + h >= len(dataset_timestamps)` (or
`decision_idx >= len`), it raises `IncompletePredictionWindowError`; `h < 1` or
`decision_idx < 0` raises `ValueError`.

`TradingCalendar` (2.4) remains the **conceptual guarantee** that
`dataset_timestamps` is a session grid, but is **not** an import-time dependency
of the persister. This keeps the service O(1), pure, and trivially testable, and
is exactly what the Friday→Monday test asserts: for a Friday with h=1, the
**calendar** diff between `timestamp_utc` and `target_timestamp_utc` is 3 days
(the weekend is skipped because the dataset already skipped it), proving the
arithmetic is per-session.

**(ii) Timestamps as ISO `str` in the domain.** `dataset_timestamps`,
`timestamp_utc` and `target_timestamp_utc` are plain ISO-8601 UTC strings. The
domain service imports only stdlib (`dataclasses`, `collections.abc`); it does
not parse or construct `datetime`/`pd.Timestamp`. ISO `str` is already the type
of these fields in `PredictionRow` (4.1) and in the `fact_oos_predictions`
schema, so no conversion is lost.

`target_return` stays **backward** (`target_return[t] = log(close[t]/close[t-1])`),
so the caller supplies `y_true(h) = target_return[decision_idx + h]`. The
persister does not compute `y_true`; it only guarantees that `decision_day` and
`target` are separated by exactly h sessions — zero off-by-one across pipelines.

## Alternatives considered

### Alternative A — `TradingCalendar.shift(decision_day, +h)` inside the service
- **Description:** the persister injects `TradingCalendar` (2.4) and derives the
  target by shifting h sessions over the canonical calendar.
- **Pros:** robust even if `dataset_timestamps` were ever not a clean session
  grid; single source of truth for session arithmetic.
- **Cons:** couples a pure domain service to `TradingSessions`; heavier per-row
  cost; needs the full calendar in scope for what is already encoded in the
  dataset array; harder to unit-test in isolation.
- **Why rejected:** the dataset **is** the trading-day grid by construction
  (premise from 2.4 upstream), so indexing the array is already correct and
  O(1). The extra robustness does not pay for the coupling here, and indexing
  the array is what makes the Friday→Monday evidence provable. Simple-and-swappable:
  if the dataset grid ever becomes untrustworthy, migrating to `shift` is a
  localized change.

### Alternative B — calendar timedelta (`decision_ts + timedelta(days=h)`)
- **Description:** the old approach — add h calendar days.
- **Pros:** no array lookup.
- **Cons:** **this is bug E4** — lands on weekends/holidays, misaligns target.
- **Why rejected:** it is the root cause this Stage exists to eliminate.

### Alternative C — keep pandas `Timestamp` in the domain (status quo / old)
- **Description:** port the old service verbatim, `import pandas as pd`.
- **Pros:** least code change from the reference.
- **Cons:** violates `LAYOUT.md` §3 and the domain-purity gate; pandas only used
  for `.isoformat()` on values that are already ISO strings.
- **Why rejected:** purity is enforced by import-linter + `check_layout.py`;
  ISO `str` carries the same information with zero conversion.

## Consequences

### Positive
- Single, pure, O(1) owner of the `target_timestamp` convention; the Gap 6 / E4
  bug is fixed at the source and locked by tests (h=1, h=7, Friday→Monday).
- Domain layer stays stdlib-only — passes domain-purity, import-linter,
  `check_layout.py`, mypy `--strict`.
- Backward `target_return` + `target_return[decision_idx + h]` guarantees
  byte-level alignment between any future model and baseline pipelines.

### Negative
- The correctness of `target_timestamp_utc` **depends on** `dataset_timestamps`
  being a genuine session grid; a malformed input would index the wrong session
  without the service detecting it (only out-of-range is caught).

### Neutral / trade-offs accepted
- `TradingCalendar` (2.4) is a conceptual guarantee, not an enforced dependency
  of the persister — a deliberate, reversible coupling decision.

## Implementation notes

- `src/financial_forecasting/features/analytics_store/domain/services/multi_horizon_prediction_persister.py`
  — `@staticmethod build(*, decision_idx, horizon, dataset_timestamps)`; two
  bound checks before indexing; no `import pandas`.
- Tests must replicate the old evidence: `test_prediction_persister_target_timestamp.py`
  with (a) h=1/h=7 exactly h sessions apart, (b) Friday→Monday calendar diff ≠ h,
  (c) year-of-partition = year of decision_day across a year boundary, (d) bound
  raises.

## References

- Related ADRs: [4.1.0002](./4_1_0002-fact-oos-predictions-long-quantile-format.md)
  (LONG format), [4.3.0002](./4_3_0002-quantile-forecast-dense-grid-guardrail.md)
  (dense-grid guardrail).
- Old repo: `docs/01_architecture/decisions/ADR-0003-multi-horizon-prediction-persister.md`
  (option d); `src/domain/services/multi_horizon_prediction_persister.py`;
  `tests/unit/domain/services/test_multi_horizon_prediction_persister.py:144-164`.
- Ledger: `docs/autonomous-run-decision-ledger.md` §B 4.3.
