---
title: ADR 5.4.0002 — One TFT fit per fold with a max_horizon-step decoder, rather than one model per horizon
description: Architecture Decision Record
when-use: Reference before splitting the TFT into per-horizon models, before changing the decoder length, or when comparing the TFT's multi-horizon strategy with the GBM's direct-per-horizon one
keywords: [adr, tft, multi-horizon, decoder, direct-strategy, quantile-loss, lim-2021, artifact-per-fold, comparability]
status: accepted
created_at: 2026-08-09
updated_at: 2026-08-09
adr_id: "5.4.0002"
decision: Train one TFT per fold with a decoder of max_horizon steps and read the requested horizons off the decoder steps, instead of fitting one model per horizon as the GBM baseline does
context_stage: 5.4-tft-trainer
bounded_context: modeling
---

# ADR 5.4.0002 — One fit per fold with a multi-horizon decoder

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

The pilot forecasts two horizons, h+1 and h+7, where the target at horizon `h`
is the **one-day** log return realized at session `t+h` (ADR 3.5.0001 +
4.3.0001) — not a cumulative return, and with no √h rule.

Stage 5.3 chose the **direct** strategy for the GBM: independent boosters per
(quantile level × horizon), with the label shifted to `t+h`
(ADR 5.3.0001). The reason was structural: gradient-boosted trees have no
sequential decoder, so a recursive strategy would require simulating the whole
feature vector at `t+1..t+6` to reach h+7 — infeasible. With H=2 the cost of the
direct strategy was small.

The TFT is a different kind of estimator. Lim et al. (2021) define it as a
multi-horizon quantile forecaster: Eq. (1) predicts `ŷ(q, t, τ)` for every
horizon τ in the decoder, with known covariates indexed up to `t+τ`, and Eq. (24)
trains by minimizing the pinball loss summed over the quantile grid **and all
horizons**. A decoder of `max_horizon` steps therefore produces the h+1 and h+7
predictions from a single fit, as the architecture was designed to.

Forces at play:

- **Cost.** Deep-model training dominates the Stage's compute. One fit per
  horizon doubles training time per fold, doubles the number of checkpoints to
  persist, and doubles what Stage 5.5 must repeat across seeds × folds.
- **Fidelity to the published design.** Splitting into per-horizon models means
  reporting results for something that is not the model the literature
  describes, weakening the "candidate is a TFT" claim the project rests on.
- **Comparability with the GBM.** The paired inference of Step 6 compares
  pinball losses point by point. What it requires is that the two models predict
  the **same target at the same grain and the same aligned timestamps** — not
  that they arrive there by the same internal mechanism.
- **Loss coupling.** With one decoder, gradient signal from every horizon shapes
  shared parameters; horizons are not isolated. That is a property of the
  architecture, not an accident, and it is what Eq. (24) prescribes.

## Decision

Fit **one** TFT per fold, with `max_prediction_length = max_horizon`, and read
the requested horizons off the corresponding decoder steps. One artifact per
fold. The quantile grid is the project's dense grid, passed to the loss.

**Training and monitoring use full-length decoders only**, so the optimized
objective is the paper's. **Prediction uses whatever the panel allows**: the
last fold's test block ends at the last session of the grid, so its final
`max_horizon` decisions have no full decoder. With a fixed decoder those
decisions would be unpredictable altogether, and the candidate would lose h+1
points that the row-wise comparators of 5.2/5.3 do emit — with a test block of a
few dozen sessions that is a visible slice of the evidence, and with the small
blocks used in tests it can be the whole block. The pair (decision `t`, horizon
`h`) is therefore emitted iff `t + h` lies inside the panel, which is exactly
the skip condition Stage 4.3 already applies, so the persisted set of aligned
points coincides with the comparators' by construction rather than by
coincidence.

The asymmetry with the GBM (5.3) is deliberate and is recorded as such: each
model uses the multi-horizon strategy its own structure supports. Comparability
is guaranteed at the level of target definition, grain and alignment (concept
§5, I1), which is where the Step 6 tests actually operate.

## Alternatives considered

### Alternative A — One TFT per horizon (mirror the GBM's direct strategy)

- **Description:** Fit an independent TFT for h+1 and another for h+7, each with
  a single-step decoder pointed at the respective offset.
- **Pros:** Literal symmetry with the 5.3 design; per-horizon capacity is not
  shared, so a horizon cannot be degraded by the other's gradient.
- **Cons:** Doubles training cost per fold and per seed, which Stage 5.5
  multiplies; produces two artifacts per fold to version and reload; a
  single-step decoder pointed at `t+7` discards the intermediate structure the
  architecture is built to exploit; departs from the published training
  objective, weakening the claim that the candidate is a TFT.
- **Why rejected:** It pays double the project's dominant compute cost to buy
  symmetry of mechanism, which no downstream test requires.

### Alternative B — Recursive strategy (predict h+1, feed it back to reach h+7)

- **Description:** Roll a one-step model forward seven times.
- **Pros:** One small model.
- **Cons:** Requires simulating the entire unknown covariate vector at each
  intermediate step (55 registry features, including indicators and sentiment);
  accumulates error across steps; is the strategy the GBM Stage already rejected
  as structurally infeasible for the same reason.
- **Why rejected:** Infeasible for this feature set, and worse where feasible.

### Alternative C — Do nothing / defer to implementation

- **Why not acceptable:** The decoder length determines the port's contract, the
  artifact count per fold, and the cost model of Stage 5.5. It cannot be left
  implicit.

## Consequences

### Positive

- One fit, one artifact and one checkpoint restoration per fold — the cost model
  Stage 5.5 multiplies stays as small as the design allows.
- The candidate is trained under the objective its paper defines, so the
  project's central claim needs no qualification.
- Adding the supplementary h+30 horizon later costs a decoder length change, not
  a new model.

### Negative

- Horizons share parameters, so the h+1 and h+7 fits are not independent: a
  configuration that suits one may compromise the other, and the aggregate loss
  cannot distinguish the two during early stopping.
- The TFT and the GBM reach their multi-horizon predictions by different
  mechanisms, which must be stated whenever the comparison is reported.

### Neutral / trade-offs accepted

- Decoder steps between the requested horizons (2..6) are computed and
  discarded. They cost compute but are what makes the training objective the
  paper's; discarding them is a reporting decision, not a modeling one.

## Implementation notes

- The port receives `max_horizon` and `horizons` separately: the first sets the
  decoder length, the second selects which steps are emitted. `horizons` must be
  contained in `1..max_horizon` (concept §6, C4).
- Variable-length prediction is expressed with the library's
  `min_prediction_length` on the prediction dataset only; the training and
  monitoring datasets keep `min_prediction_length == max_prediction_length ==
  max_horizon`. The emitted set is pinned by an acceptance criterion (concept
  A12/A13) against the arithmetic rule and against what Stage 5.3 persists for
  the same fold, so a regression to a fixed decoder is detectable.
- The quantile grid reaches the loss unchanged, so emitted grids align 1:1 with
  `quantile_levels`; crossing is still possible and the guardrail of ADR 4.3.0002
  is applied per (decision × horizon) by the use case.

## References

- Related ADRs:
  [5.3.0001](./5_3_0001-direct-per-level-horizon-boosters.md) (the GBM's direct
  per-horizon strategy — the deliberate asymmetry);
  [3.5.0001](./3_5_0001-target-definition-backward-log-return.md);
  [4.3.0001](./4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md);
  [4.3.0002](./4_3_0002-quantile-forecast-dense-grid-guardrail.md).
- External: Lim, B.; Arık, S. Ö.; Loeff, N.; Pfister, T. (2021). "Temporal Fusion
  Transformers for interpretable multi-horizon time series forecasting".
  *International Journal of Forecasting* 37(4), 1748–1764 — Eq. (1) and Eq. (24).
  Ben Taieb, S.; Atiya, A. F. (2016). "A bias and variance analysis for
  multistep-ahead time series forecasting". *IEEE TNNLS* 27(1), 62–76.
- Conversation/issue: GitHub issue #57, alignment block B2 (2026-08-09).
