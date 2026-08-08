---
title: ADR 5.3.0002 — Early stopping by grid-mean pinball on the dedicated early_stop partition
description: Architecture Decision Record
when-use: Reference whenever revisiting how the GBM selects its number of boosting iterations, or before enabling per-booster early stopping on any quantile model
keywords: [adr, lightgbm, early-stopping, pinball, quantile, early-stop-partition, determinism]
status: accepted
created_at: 2026-07-19
updated_at: 2026-07-19
adr_id: 5.3.0002
decision: Train all K level-boosters of a (fold × horizon) to a fixed ceiling without stopping callbacks, record per-iteration pinball histories on the dedicated early_stop partition, and select a single best iteration m* per (fold × horizon) as the argmin of the grid-mean pinball (ties → smallest iteration); test predictions are emitted truncated at m*.
context_stage: 5.3-gbm-quantile-baseline
bounded_context: modeling
---

# ADR 5.3.0002 — Early stopping by grid-mean pinball on the dedicated early_stop partition

## Status

`accepted`

## Context

The 5.1 harness provides a dedicated `early_stop` partition per fold,
designed precisely so that iterative models can select their stopping point
without touching `calib` (ADR 5.1.0002 — the monitored sub-split
participates in model selection; conformal calibration must stay disjoint).
The GBM is the first consumer of this partition.

Naive per-booster early stopping (LightGBM's `early_stopping` callback,
one independent stop per level) is undermined by three verified problems:

1. **Documented pathology:** LightGBM issue #4870 (open since 2021, "I
   think this is a bug" — maintainer): quantile objective + early stopping +
   small validation set can stop at iteration 1, learning nothing. The
   reporter's conclusion: avoid quantile + early stopping in automated
   pipelines.
2. **Effective sample size at extreme levels:** what governs the variance of
   a τ-quantile estimate is τ·n, not n (Chernozhukov, Fernández-Val & Kaji,
   arXiv:1612.06850, §3.2.3 — rule of thumb τ·n ≥ 30). With τ = 0.02 and an
   early_stop partition of ~200 sessions, τ·n ≈ 4: a per-level stop at the
   extremes would be decided by ~4 effective observations.
3. **Reproducibility:** with multithreading + subsampling the stopping
   iteration is non-deterministic (LightGBM issue #5758). A confirmatory
   design cannot carry that.

A fixed pre-registered iteration count avoids all three but leaves the
dedicated partition idle and freezes model capacity across folds — a
weaker comparator than the harness affords.

## Decision

Per (fold × horizon): train each of the K level-boosters to the ceiling
`num_boost_round_max` with **no stopping callback**, passing the
`early_stop` partition as `valid_sets` with the native `quantile` metric
(the pinball at the booster's own `alpha`) and `record_evaluation` to
capture the per-iteration history. Then select

    m*_h = 1 + argmin_m  (1/K) Σ_k  pinball_history[τ_k][m]

with ties resolved to the smallest m. The `+1` converts the 0-based
history index into LightGBM's 1-based tree count — `predict(num_iteration=0)`
means "use ALL trees", so an unconverted index would silently disable
truncation exactly when the optimum is the first iteration; implementations
must assert `m*_h >= 1`. Emit test predictions with
`predict(num_iteration=m*_h)`. Persist nothing extra: `m*` is returned in
the use-case Result (`best_iteration_by_horizon`) and is a deterministic
function of data + command (concept I4).

The grid-mean criterion aggregates ~K× more evaluation signal than any
single level, so extreme levels never decide alone; and it is
methodologically parallel to the TFT's training loss (sum of pinball over
the quantile grid, Lim et al. 2021 Eq. (24)), which strengthens
candidate × comparator comparability.

## Alternatives considered

### Alternative A — Per-booster early stopping (native callback)
- **Description:** `lgb.early_stopping(rounds)` per level; each booster
  stops independently.
- **Pros:** idiomatic; no post-processing.
- **Why rejected:** inherits #4870 verbatim (same objective, same small-val
  regime); extreme levels stop on τ·n ≈ 4 effective observations; K
  independent stopping points multiply the variance the criterion is
  supposed to remove.

### Alternative B — Fixed pre-registered num_boost_round
- **Description:** constant iteration count for all folds/levels/horizons.
- **Pros:** maximally simple and deterministic; zero validation dependence.
- **Why rejected:** leaves the dedicated `early_stop` partition idle (the
  harness paid purge+embargo real estate for it); one global capacity
  constant across expanding folds is a guess that weakens the H2 comparator.
  Kept as the natural fallback if R3 (metric history unavailable)
  materializes — the fallback preserves the port contract.

### Alternative C — Do nothing (ceiling only, always predict full model)
- **Why rejected:** equivalent to B with the ceiling as the constant, plus
  overfitting risk at the ceiling; same idle-partition objection.

## Consequences

### Positive
- Uses the dedicated partition for exactly its designed purpose; `calib`
  provably untouched (concept I6, asserted by test).
- Deterministic: no stopping randomness (no subsampling — concept D6), argmin
  with explicit tie-break, O(M) cost via the lib's own eval loop (no O(M²)
  re-prediction).
- Robust at extremes: single m* per (fold × horizon) driven by the whole
  grid.

### Negative
- All boosters train to the ceiling — compute is bounded by
  `num_boost_round_max` even when a per-level stop would have quit earlier.
- A single m* per horizon is a compromise: individual levels might prefer
  different capacities; the grid mean absorbs that (accepted — mirrors the
  TFT, which also selects one stopping epoch for the whole grid).

### Neutral / trade-offs accepted
- The pinball here is a **training-internal criterion computed by the
  library**, never a reported project metric — the evaluation pinball
  (Step 6) remains a domain service with oracle validation, and no metric
  formula is implemented in this Stage.

## Implementation notes

- Native API: `lgb.train(params, train_set, num_boost_round=ceiling,
  valid_sets=[early_stop_set], callbacks=[lgb.record_evaluation(hist)])`;
  metric left as the objective's default (`quantile` at the booster's own
  alpha).
- Non-finite labels are excluded from the early_stop monitor pairs by the
  adapter BEFORE building `valid_sets` (concept I11): LightGBM's native
  eval silently coerces NaN labels to 0, which would corrupt the m*
  selection with phantom zero-return observations.
- Histories must have length == trained iterations (mechanics asserted by
  adapter integration test — risk R3).
- Fallback R3 (history mechanism unusable): regress to Alternative B —
  fixed pre-registered `num_boost_round`, idle partition documented as a
  deviation. Computing per-iteration pinball manually is NOT a valid
  fallback: it would implement an evaluation formula inside this Stage,
  violating the declared scope (concept §1 — no evaluation formula here).

## References

- Related ADRs: 5.1.0002 (dedicated calib partition — the design this ADR
  consumes), 5.3.0001 (per-(level × horizon) boosters)
- Domain doc: `docs/domain/modeling/quantile-model-training.md` §5.3 (early
  stopping as model selection; val monitored ≠ calib)
- External:
  - LightGBM issue #4870 — "Inconsistent behavior of median regression
    (objective = quantile, alpha = 0.5) with early stopping" (open,
    maintainer-acknowledged probable bug). Accessed 2026-07-19.
  - LightGBM issue #5758 — "Early stopping not reproducible when
    nthreads>1" (maintainer guidance: disable subsampling for
    reproducibility). Accessed 2026-07-19.
  - Chernozhukov, V.; Fernández-Val, I.; Kaji, T. (2016). "Extremal
    Quantile Regression: An Overview." arXiv:1612.06850. (§3.2.3: τ·n ≥ 30
    rule of thumb for the effective sample of a τ-quantile.)
  - Lim, B.; Arık, S. Ö.; Loeff, N.; Pfister, T. (2021). *IJF*, 37(4),
    1748–1764, Eq. (24) — TFT trains on the grid-summed pinball.
  - LightGBM `Parameters.rst`: `early_stopping_round`, `metric` default
    behavior ("metric corresponding to specified objective will be used"),
    `record_evaluation` callback. Accessed 2026-07-19.
- Conversation: bifurcação B3, sessão de kickoff da Stage 5.3 (2026-07-19)
