---
title: ADR 5.1.0002 — Dedicated calibration partition, disjoint from early-stop, adjacent to test, embargoed
description: Architecture Decision Record
when-use: Reference when placing/sizing the conformal calibration set in a fold, or before letting early stopping or model selection touch the calibration block
keywords: [adr, conformal, cqr, calibration-set, early-stopping, exchangeability, recency, embargo, walk-forward, coverage, modeling]
status: accepted
created_at: 2026-07-04
updated_at: 2026-07-04
adr_id: "5.1.0002"
decision: Each fold's validation region is split into an early-stop block and a dedicated calibration block that is disjoint from early-stop/training, placed as the most recent block immediately before the test (separated by purge+embargo), and never consulted for model selection
context_stage: 5.1-walk-forward-harness
---

# ADR 5.1.0002 — Dedicated calibration partition (disjoint, recent, embargoed)

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The walk-forward harness (Stage 5.1) must, per the roadmap, partition each fold's
validation region into an **early-stop** block and a **dedicated calibration**
block. The calibration block exists to serve the conformal benchmark of Step 7.2
(Conformalized Quantile Regression, CQR, via MAPIE). Three sub-decisions have to
be made and justified for the thesis: (i) whether calibration may share data with
training/early-stopping, (ii) where in time the calibration block sits, and
(iii) whether it is separated from the test block.

Forces at play:

- **Split-conformal validity rests on independence.** Split (inductive) conformal
  prediction and CQR fit the model on a *proper training set* and compute
  non-conformity scores on a **disjoint calibration set**; the finite-sample
  marginal coverage guarantee follows from that separation of roles. Using the
  calibration set for any model-selection decision — including **early stopping** —
  breaks the independence and voids the guarantee.
- **Exchangeability fails for time series.** The coverage guarantee assumes
  exchangeability, which temporal dependence and distribution shift violate;
  empirically, split-conformal coverage degrades (e.g. from a nominal 0.90 to
  ~0.84) when a shift occurs at the test boundary, because a stale calibration
  quantile is unrepresentative of post-shift errors.
- **Recency is the remedy.** Time-series conformal methods restore coverage by
  weighting recent residuals ("the recent past matters most"), which argues for
  the calibration block being the **most recent** validation data, immediately
  before the test.
- **Temporal coupling must be cut.** Adjacent-in-time calibration and test points
  are serially dependent; finance practice inserts a purge+embargo gap to decouple
  them (López de Prado 2018), which Step 7.2's DoD already requires ("com
  embargo").
- **The project already labels coverage empirical.** Step 7.2 reports **empirical**
  coverage (not "guaranteed"), acknowledging the exchangeability caveat — the
  calibration design must be honest about the same caveat.

## Decision

**Each fold's validation region is split into `early_stop` and a dedicated
`calib` block, with:**

1. **Disjointness.** `calib` shares no observation with `train` or `early_stop`,
   and is **never** consulted for early stopping or any model selection — it is
   reserved solely for computing conformal non-conformity scores downstream.
2. **Recency.** `calib` is the **most recent** validation block, placed
   immediately before `test` (order: `train → early_stop → calib → test`), so it
   best represents the test distribution under non-exchangeability.
3. **Embargo.** `calib` is separated from `test` (and from `early_stop`) by a
   purge+embargo gap of `max_horizon + embargo` trading sessions, decoupling the
   serially-dependent boundary.

The block size is exposed as an explicit `calib_size` parameter of `split(...)`
so the calibration budget per fold is controllable and pre-registrable.

## Alternatives considered

### Alternative A — Fold calibration into the validation set (no dedicated block)

- **Description:** reuse the early-stop/validation data as the calibration set.
- **Pros:** simpler; no extra partition.
- **Cons:** the model selects on the same data used to calibrate — the calibration
  scores are contaminated by information the model already exploited, breaking the
  independence that conformal coverage depends on.
- **Why rejected:** it silently invalidates the coverage claim, exactly the kind of
  silent-wrong-answer the project rejects; contradicts Step 7.2's "não no
  early-stop".

### Alternative B — Calibration first, early-stop adjacent to test

- **Description:** order `train → calib → early_stop → test`.
- **Pros:** keeps the early-stopping metric closest to the deployment horizon.
- **Cons:** the calibration block becomes the *oldest* validation data — most
  exposed to distribution shift, degrading conformal coverage under
  non-exchangeability.
- **Why rejected:** conformal coverage is the reason the calibration block exists;
  sacrificing its recency to marginally improve early-stopping proximity is the
  wrong trade.

### Alternative C — No embargo between calibration and test

- **Description:** place `calib` immediately adjacent to `test` with no gap.
- **Pros:** maximal, most-recent calibration data.
- **Cons:** serial dependence between adjacent calibration and test points leaks
  information and inflates apparent coverage.
- **Why rejected:** Step 7.2 requires an embargo; finance practice mandates it.

### Alternative D — Do nothing / status quo

- Without a dedicated, correctly-placed calibration set, the Step 7.2 conformal
  benchmark cannot be run honestly. Not acceptable.

## Consequences

### Positive

- The conformal benchmark rests on a methodologically sound calibration set:
  independent of model fitting/selection, recent, and embargoed.
- The `calib`/`early_stop` split is a structural invariant of `FoldSplit`
  (disjoint fields), so a downstream misuse (calibrating on early-stop data) is
  caught by construction and by Step 7.2's `test_conformal_calib_set_dedicated`.
- Traceable to primary sources for the thesis.

### Negative

- Consumes validation budget: a dedicated `calib` block plus two embargo gaps
  reduce the data available for training and early stopping per fold. Accepted as
  the cost of a defensible coverage claim.

### Neutral / trade-offs accepted

- Coverage remains **empirical**, not guaranteed, because exchangeability is
  violated; the design maximizes empirical coverage (recency + embargo) but does
  not pretend to restore the finite-sample guarantee. Weighted/non-exchangeable
  variants (NexCP) are deliberated in Step 7.2, not here.

## Implementation notes

- `FoldSplit` carries `early_stop` and `calib` as separate, disjoint tuples;
  invariants I1/I2/I5 (concept §5) are enforced in `__post_init__`.
- The purge width is `scope.max_horizon`; the embargo is the `embargo` parameter;
  both are resolved in trading sessions via `TradingCalendar.shift_trading_days`.

## References

- Related ADRs: [0.0.0018](./0_0_0018-anti-leakage-non-negotiable.md) (embargo,
  target alignment), [5.1.0001](./5_1_0001-expanding-window-walk-forward.md)
  (window scheme), [5.1.0003](./5_1_0003-split-fingerprint-four-way-calib.md)
  (fingerprinting the 4-way split).
- External (basis for the TCC):
  - Romano, Y., Patterson, E. & Candès, E. (2019). *Conformalized Quantile
    Regression*. NeurIPS. arXiv:1905.03222. (proper training set disjoint from
    calibration set; exchangeability → marginal coverage; ~70–90% train.)
  - Barber, R. F., Candès, E. J., Ramdas, A. & Tibshirani, R. J. (2023).
    *Conformal prediction beyond exchangeability*. Annals of Statistics, 51(2).
    (weighting to favor recent data under non-exchangeability.)
  - *A Gentle Introduction to Conformal Time Series Forecasting* (2025).
    arXiv:2511.13608. (coverage degradation under shift; exponential-decay /
    recency weighting; block conformal.)
  - Lei, J., G'Sell, M., Rinaldo, A., Tibshirani, R. J. & Wasserman, L. (2018).
    *Distribution-free predictive inference for regression*. JASA. (split
    conformal calibration/training separation.)
  - López de Prado, M. (2018). *Advances in Financial Machine Learning*, ch. 7
    (purge + embargo).
- Roadmap: `docs/roadmap.md` Stage 7.2 DoD (dedicated calib, not early-stop, per
  fold/horizon, with embargo; empirical coverage).
