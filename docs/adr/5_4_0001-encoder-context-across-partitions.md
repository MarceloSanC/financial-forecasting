---
title: ADR 5.4.0001 — The encoder context window may cross walk-forward partition boundaries; what may not cross is fitting and selection, including fitted preprocessing
description: Architecture Decision Record
when-use: Reference before changing how the TFT (or any sequence model) consumes history across fold partitions, before restricting the lookback window, or before deciding where target normalizers and categorical encoders are fitted
keywords: [adr, anti-leakage, encoder, lookback, context-window, walk-forward, purge, embargo, conformal, calibration-partition, normalizer, train-only-fit]
status: accepted
created_at: 2026-08-09
updated_at: 2026-08-09
adr_id: "5.4.0001"
decision: A decision's encoder context window may read sessions belonging to earlier partitions (including early_stop and calib), restricted to sessions at or before the decision date; calib stays untouched as a source of fitting and of selection, and the fitted transformation of the flow (the target normalizer) is estimated from the training block only and inherited by the other partitions
context_stage: 5.4-tft-trainer
bounded_context: modeling
---

# ADR 5.4.0001 — Encoder context across partitions; fitting and selection do not cross

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stages 5.2 and 5.3 trained models that consume **one row at a time**: a baseline
or a gradient-boosting booster predicting from the features of decision `t`
alone. Under that shape, the harness invariant of ADR 5.1.0002 could be honored
in its most literal form — the `calib` partition was simply never read, by the
use case or by the adapter, and Stage 5.3 proved it by mutation-invariance
tests.

Stage 5.4 introduces the first **sequence** model. A Temporal Fusion Transformer
prediction for decision `t` consumes an encoder window of the preceding
`max_encoder_length` sessions (target history and observed covariates). For the
first decisions of a `test` block, that window necessarily reaches back across
the purge/embargo gap into `calib`, and for larger windows into `early_stop` and
`train`. Two readings collide:

- The literal reading of "calib is untouched" would forbid the window from
  crossing, which would leave the first `max_encoder_length` decisions of every
  test block unpredictable and would not correspond to what a forecaster has
  available at decision time.
- The permissive reading risks silently reintroducing the leakage that the
  four-way partition exists to prevent.

Forces at play:

- **What purging and embargo actually protect.** In López de Prado (2018, §7.4),
  purging removes from the **training** set observations whose *label formation
  window* overlaps the test period; embargo removes training observations
  immediately following it. Both operate on the training set and on labels.
  Neither restricts a test observation's own trailing feature window — in that
  framework features are trailing windows by construction and routinely overlap
  earlier periods.
- **What rolling-origin evaluation assumes.** Tashman (2000) and Bergmeir &
  Benítez (2012) fix that, at each origin, everything up to the origin is
  legitimately available as input. Hewamalage, Ackermann & Bergmeir (2023) state
  explicitly that in rolling-origin setups data moving from test into training
  across iterations is normal, and identify the actual leakage pitfall as
  **preprocessing applied over the whole series before partitioning**
  (smoothing, decomposition, normalization).
- **What split conformal requires.** Lei et al. (2018) and Barber et al. (2023)
  require the **fitted predictor** to be independent of the calibration data:
  the model is fit on the training split and frozen; calibration is used only to
  compute nonconformity scores. Reading calibration-period observations as input
  context neither refits nor reselects anything. What *would* break the
  requirement is fitting or selecting on calib — which is exactly what early
  stopping does, and exactly why ADR 5.1.0002 keeps the two partitions apart.
- **How conformal treats sequence forecasters.** In Stankevičiūtė et al. (2021),
  the "feature" of an example *is* its lookback window; conformal prediction is
  applied on top of it. A trailing window is a covariate, not leakage.
- **Library mechanics.** In `pytorch-forecasting`, the canonical validation/test
  construction constrains the first *decoder* index (`min_prediction_idx`);
  encoder windows still include earlier points belonging to the training period.
  Verified against the index-construction code, not only the docstring.

## Decision

The invariant is stated in **two clauses**, and both are enforced by tests:

1. **Context may cross.** The encoder window of a decision at session `t` may
   read sessions belonging to earlier partitions — `train`, `early_stop`,
   `calib` and the purge/embargo gaps — restricted to sessions **`≤ t`**, `t`
   itself included. This matches Eq. (1) of the paper, where the target and the
   observed covariates are indexed `t−k:t`, and matches what the row-wise
   comparators of 5.2/5.3 do (they consume the feature row of `t`). Crossing a
   partition boundary backwards is not leakage; reading anything **after** the
   decision date is.

   Whether a given decision's window actually reaches a given partition is
   **conditional on the geometry**, not universal: for the test decision at
   offset `j` in its block, with window `L` and `gap = max_horizon + embargo`,
   the window `[t − L + 1, t]` reaches `calib` iff `j ≤ L − gap − 2`,
   `early_stop` iff `j ≤ L − 2·gap − calib_size − 2`, and `train` iff
   `j ≤ L − 3·gap − calib_size − val_size − 2`. The `− 2` is not slack: the
   splitter sets `calib_end = test_start − gap` **exclusive**, so the last
   calibration index is `test_start − gap − 1`, and the window's first session
   is `t − L + 1`. A geometry chosen at the boundary of a looser formula would
   put the window's first session inside the purge gap instead of inside
   `calib`, and the mutation test meant to prove the crossing would pass while
   proving nothing.

2. **Fitting and selection do not cross, and neither does fitted
   preprocessing.** No decision outside `train` enters the fit; no decision
   outside `early_stop` enters the early-stopping monitor; `calib` enters
   neither, remaining reserved for the conformal step. Every **fitted**
   transformation — target normalizer, categorical encoders, any statistic
   estimated from data — is estimated from the training decisions only and
   inherited by the other partitions.

Clause 2 is the operative one. It is the channel through which this design could
actually leak, and it is the pitfall Hewamalage et al. name: a normalizer fitted
over the whole series before partitioning contaminates every split at once,
invisibly, while every structural gate stays green.

## Alternatives considered

### Alternative A — Forbid the context window from crossing partition boundaries

- **Description:** Restrict each decision's encoder window to sessions within its
  own partition; decisions without a full window are dropped.
- **Pros:** The most literal reading of "calib untouched"; trivially auditable.
- **Cons:** Discards the first `max_encoder_length` decisions of every test
  block — with a 60-session window and test blocks of a few dozen sessions, most
  of the out-of-sample evidence disappears; contradicts how the model would
  operate in production, where all past data is available at decision time; has
  no support in the leakage literature, which targets labels and fitting, not
  trailing features.
- **Why rejected:** It buys no additional protection (clause 2 is what protects)
  and pays for it with most of the out-of-sample sample.

### Alternative B — Allow crossing with no explicit invariant (rely on the library defaults)

- **Description:** Build the datasets with the library's standard recipe and
  assume its defaults keep the separation.
- **Pros:** Less code; matches tutorials.
- **Cons:** The library's default normalizer is fitted on whatever frame it is
  given; constructing the validation/test datasets from the full frame instead
  of deriving them from the training dataset silently fits the normalizer over
  the whole series — the exact leak of clause 2, and one that no structural gate
  in this project would catch.
- **Why rejected:** The failure mode is silent and would invalidate the
  calibration reading that the project exists to produce.

### Alternative C — Do nothing / defer the decision to implementation

- **Why not acceptable:** The two readings of the 5.1.0002 invariant lead to
  materially different systems, and the difference is invisible in the artifacts
  produced. Leaving it to implementation means it gets decided by whoever writes
  the adapter, without a record.

## Consequences

### Positive

- The anti-leakage rule becomes precise enough to test: clause 1 predicts that
  mutating pre-decision sessions **changes** predictions; clause 2 predicts that
  mutating `calib` and `test` target values leaves the fit **unchanged**. Both
  are mutation-detectable, so the invariant cannot rot silently.
- Every test decision that has a full context window is predictable, so the
  candidate's evidence base matches the comparators' (5.2/5.3) except for the
  decisions whose window is incomplete — a deficit that is enumerated
  explicitly rather than absorbed silently (concept I16/I17). Under Alternative
  A the deficit would instead be `max_encoder_length` decisions **per test
  block**, which the paired inference of Step 6 would feel directly.
- The conformal premise of ADR 5.1.0002 is preserved with its reason stated,
  rather than by an over-restrictive proxy whose rationale would be lost.

### Negative

- The port must receive the **whole panel** rather than per-partition slices
  (concept §7-D5), so the adapter holds data it must not fit on. The guarantee
  moves from "the adapter cannot see it" to "the adapter is contractually
  forbidden and tested for it" — a weaker structural guarantee than 5.3 had.
- Clause 2 requires the derived-dataset construction discipline to be verified
  by a dedicated test rather than assumed from the library's defaults.

### Neutral / trade-offs accepted

- This ADR **narrows** ADR 5.1.0002 without superseding it, and names the clause
  it narrows. That ADR's disjointness rule reads: `calib` "shares no observation
  with `train` or `early_stop`, is **never consulted for early stopping or any
  model selection** … reserved **solely** for computing conformal non-conformity
  scores downstream". The first half is preserved verbatim by clause 2 here. The
  word narrowed is **"solely"**: reading a calibration-period observation as
  *input context* at prediction time is declared not to be a use of the
  partition in the sense that clause forbids, because it neither fits nor
  selects. Under row-wise models (5.2/5.3) the distinction never arose, so the
  stronger reading cost nothing; with a sequence model it would cost most of the
  out-of-sample sample.

## Implementation notes

- Tests that pin the invariant must keep the two channels **separate**, because
  a single prediction-invariance test would confound them. Concretely:
  - **Fit/selection channel:** mutating `calib` and `test` targets leaves
    `best_epoch` and the per-epoch validation-loss history identical. This
    invariance is true and non-vacuous — the splitter arithmetic guarantees that
    no training or monitoring decoder reaches `calib` (for the last training
    decision `t* = te − 1`, `early_stop_start − (t* + max_horizon) = embargo + 1
    ≥ 1`, and the same identity holds between `early_stop` and `calib`).
  - **Context channel (non-vacuity):** mutating sessions `≤ t` that fall inside
    the window of the test decision at offset `j = 0` **changes** that
    decision's prediction. Without this test, the fit/selection invariance above
    would also pass for a model that ignores its inputs.
  - **Normalizer:** asserted **directly** on the fitted parameters (center and
    scale equal the statistic of the training decisions), not by prediction
    invariance under a `calib` mutation — that mutation legitimately changes
    test predictions through the context channel, so an invariance test there
    would only pass for the truncating design this ADR rejected.
- The use case derives the three index sets from the `FoldSplit` and passes them
  with the full panel; the adapter builds the training dataset from decisions in
  `train` only, derives the monitor and prediction datasets from it (inheriting
  fitted transforms), and never constructs a dataset from the full frame.

## References

- Related ADRs:
  [5.1.0002](./5_1_0002-dedicated-calibration-partition.md) (dedicated
  calibration partition — narrowed, not superseded, by this ADR);
  [5.1.0001](./5_1_0001-expanding-window-walk-forward.md);
  [0.0.0018](./0_0_0018-anti-leakage-non-negotiable.md);
  [4.3.0001](./4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md).
- External: López de Prado, M. (2018). *Advances in Financial Machine Learning*,
  §7.4 (purging and embargo). Tashman, L. J. (2000). "Out-of-sample tests of
  forecasting accuracy: an analysis and review". *IJF* 16(4), 437–450.
  Bergmeir, C.; Benítez, J. M. (2012). "On the use of cross-validation for time
  series predictor evaluation". *Information Sciences* 191, 192–213.
  Hewamalage, H.; Ackermann, K.; Bergmeir, C. (2023). "Forecast evaluation for
  data scientists: common pitfalls and best practices". *DMKD* 37(2), 788–832.
  Lei, J.; G'Sell, M.; Rinaldo, A.; Tibshirani, R. J.; Wasserman, L. (2018).
  "Distribution-free predictive inference for regression". *JASA* 113(523),
  1094–1111. Barber, R. F.; Candès, E. J.; Ramdas, A.; Tibshirani, R. J. (2023).
  "Conformal prediction beyond exchangeability". *Annals of Statistics* 51(2),
  816–845. Stankevičiūtė, K.; Alaa, A. M.; van der Schaar, M. (2021).
  "Conformal time-series forecasting". *NeurIPS* 34.
  `pytorch-forecasting` `TimeSeriesDataSet` index construction
  (`min_prediction_idx` constrains the decoder index only).
- Conversation/issue: GitHub issue #57, alignment block B3 (2026-08-09).
