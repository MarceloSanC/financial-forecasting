---
title: ADR 5.1.0001 — Expanding (anchored) window for the walk-forward harness, not a rolling window
description: Architecture Decision Record
when-use: Reference when choosing or revisiting the temporal window scheme of the walk-forward evaluation, or before adding a rolling-window variant
keywords: [adr, walk-forward, expanding-window, anchored, rolling-window, rolling-origin, evaluation, backtest, modeling]
status: accepted
created_at: 2026-07-04
updated_at: 2026-07-04
adr_id: "5.1.0001"
decision: The walk-forward harness uses an expanding (anchored) training window — train grows from the first session each fold — rather than a fixed-length rolling window; rolling stays out of scope as a documented future extension
context_stage: 5.1-walk-forward-harness
bounded_context: modeling
---

# ADR 5.1.0001 — Expanding (anchored) walk-forward window

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 5.1 builds the temporal validation harness that every model in Step 5
(baselines, GBM, TFT) and the confirmatory statistics of Steps 6–7 are trained
and evaluated under. A walk-forward (rolling-origin) protocol repeatedly moves
the forecast origin forward and re-fits, producing a sequence of out-of-sample
test blocks. A first-order design fork is the **training window**:

- **Expanding / anchored:** the training set starts at the first observation and
  grows as the origin rolls forward; each fold trains on all history up to its
  boundary.
- **Rolling / fixed:** the training set has a constant length and slides forward,
  discarding the oldest observations.

Forces at play:

- **Data scarcity.** The pilot is single-asset (AAPL) with ~4000 daily trading
  sessions; the TFT candidate is data-hungry. Discarding early history shrinks an
  already small training set.
- **Non-stationarity.** Financial return series exhibit distribution shift, which
  is the classic argument *for* a rolling window (recent regime only).
- **Confirmatory reproducibility.** The project pre-registers a single, immutable
  temporal protocol before the confirmatory run; the scheme must be defensible and
  parameter-light.
- **Where drift is already handled.** The design absorbs non-stationarity
  elsewhere — per-fold re-fit, an embargo between blocks (ADR 5.1.0002), and the
  recency of the conformal calibration set (Step 7.2) — so the window scheme does
  not have to carry that burden alone.

## Decision

**The harness uses an expanding (anchored) window: every fold's training set
begins at `sessions[0]` and grows with the fold index.** Rolling/fixed-window
evaluation is explicitly out of scope for this Stage and is recorded as a future
extension (a `window` parameter could be added without changing the fold
geometry).

This follows the standard presentation of rolling-origin evaluation, where the
training set "consists only of observations that occurred prior to the
observation that forms the test set" and grows one step at a time (Hyndman &
Athanasopoulos, *Forecasting: Principles and Practice* 3rd ed., §5.10). The
expanding window is favored especially for short series because it leverages the
full data history — the exact regime of this pilot.

## Alternatives considered

### Alternative A — Rolling / fixed-length window

- **Description:** constant-length training window that slides forward.
- **Pros:** more robust to concept drift / non-stationarity; each fit sees only a
  recent, more homogeneous regime.
- **Cons:** discards early history (costly on ~4000 sessions and for a data-hungry
  TFT); introduces a `train_size` hyper-parameter that must itself be justified and
  pre-registered; higher variance per fold from smaller training sets.
- **Why rejected:** the data-scarcity cost is concrete and immediate, while the
  drift it guards against is already mitigated by per-fold re-fit + embargo +
  conformal recency. Not worth the extra tunable in a confirmatory pilot.

### Alternative B — Configurable (both, default expanding)

- **Description:** a `window` parameter supporting expanding and rolling.
- **Pros:** maximal flexibility.
- **Cons:** more code and tests now for a path the pilot will not exercise;
  contradicts the Stage `non_goals` discipline.
- **Why rejected:** YAGNI for the pilot; the extension is cheap to add later
  precisely because the fold geometry is unchanged.

### Alternative C — Do nothing / status quo

- No harness means no defensible OOS protocol — every downstream statistic would
  rest on ad-hoc splitting. Not acceptable (ADR 0.0.0018 rule 4).

## Consequences

### Positive

- Maximizes training data per fold — best use of a short single-asset history.
- One fewer hyper-parameter to justify and pre-register; lower between-fold
  variance.
- Matches the canonical rolling-origin presentation used across the forecasting
  literature — easy to defend in the TCC.

### Negative

- If AAPL exhibits strong regime change, the oldest data may be less
  representative than a rolling window would allow. Accepted, and mitigated by
  embargo + conformal recency rather than by shortening the window.

### Neutral / trade-offs accepted

- Rolling-window evaluation is deferred, not forbidden; adding a `window` option
  later is a localized change.

## Implementation notes

- `WalkForwardSplitter.split` anchors every fold's `train` at `sessions[0]`;
  `test` blocks tile the tail into `n_folds` disjoint blocks of `test_size`.
- Insufficient history for a fold raises `ValueError` (no clamp), consistent with
  the project's "raise, don't fabricate" posture.

## References

- Related ADRs: [0.0.0018](./0_0_0018-anti-leakage-non-negotiable.md) (purge +
  embargo splits, rule 4), [5.1.0002](./5_1_0002-dedicated-calibration-partition.md)
  (embargo + calibration recency that absorb drift).
- External:
  - Hyndman, R. J. & Athanasopoulos, G. (2021). *Forecasting: Principles and
    Practice* (3rd ed.), §5.10 (time series cross-validation on a rolling
    forecasting origin). https://otexts.com/fpp3/tscv.html
  - Tashman, L. J. (2000). *Out-of-sample tests of forecasting accuracy: an
    analysis and review*. International Journal of Forecasting, 16(4), 437–450.
  - Bergmeir, C. & Benítez, J. M. (2012). *On the use of cross-validation for
    time series predictor evaluation*. Information Sciences, 191, 192–213.
  - Hewamalage, H., Ackermann, K. & Bergmeir, C. (2022). *Forecast evaluation for
    data scientists: common pitfalls and best practices*. arXiv:2203.10716.
  - López de Prado, M. (2018). *Advances in Financial Machine Learning*, ch. 7.
- Roadmap: `docs/roadmap.md` Stage 5.1 (`non_goals`: Combinatorial Purged CV
  discarded; rolling not requested).
