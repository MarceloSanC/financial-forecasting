---
title: ADR 5.2.0002 — Baseline parameters frozen on the train partition per fold; conditioning state advances causally to each decision day
description: Architecture Decision Record
when-use: Reference whenever revisiting how baselines (and, by symmetry, any cohort model) consume the walk-forward partitions — what is estimated where, what may condition on test-block returns — or before introducing per-origin refits
keywords: [adr, baselines, walk-forward, estimation-protocol, frozen-parameters, causal-state, refit, comparability, h2, anti-leakage, modeling]
status: accepted
created_at: 2026-07-15
updated_at: 2026-07-15
adr_id: 5.2.0002
decision: Per fold, baseline parameters (μ̂, φ̂, σ̂_ε of AR(1); μ̂ of historical_mean) are estimated once, exclusively on the train partition; the conditioning state of the preregistered formulas (r_t for AR(1), the EWMA variance recursion, the rolling-quantile window content) advances causally up to each decision day of the test block; there is no per-origin refit inside the test block — mirroring the information protocol of the GBM/TFT so the H2 comparison is like-for-like
context_stage: 5.2-baselines-naive-statistical
---

# ADR 5.2.0002 — Frozen train estimation, causal conditioning state

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The domain doc fixes **what** each baseline emits (§3) but the walk-forward
execution needs one more convention: **when is each quantity computed?** Two
kinds of quantity behave differently:

- **Estimated parameters** — AR(1)'s (μ̂, φ̂, σ̂²_ε), historical_mean's μ̂.
  These are the "training" act of a baseline.
- **Conditioning state** — the r_t that the AR(1) mean conditions on, the
  EWMA recursion σ̂²_{t+1|t} = λσ̂²_{t|t−1} + (1−λ)r_t² (RMTD Eq. [5.3]),
  and the rolling window content of `historical_quantiles`. The preregistered
  formulas are **defined** on the return of the decision day itself.

Forces:

- The 5.1 harness defines `train` as the estimation region, with purge +
  embargo protecting precisely the train/test boundary; each fold's identity
  (`SplitFingerprint`) attests that boundary.
- The candidate (TFT) and the GBM operate under "weights frozen on train,
  observed inputs up to the decision day": at inference the encoder consumes
  the observed series up to t, with parameters untouched since training. The
  H2 comparison must be like-for-like on the information protocol (overview
  §3/§7 — same grão, same cohort; skill `project-scope-principles`, fairness
  lens).
- Returns inside the test block **prior to the decision day** are legitimately
  available at decision time — conditioning on them is causal, not leakage
  (ADR 0.0.0018 rule 1). Conversely, letting **estimation** consume them
  would blur the harness's train semantics.
- Classical forecast evaluation also knows the per-origin-refit protocol
  (Tashman 2000, rolling-origin with updating) — a genuinely defensible
  alternative, hence this ADR.

## Decision

Per fold of the 5.1 harness:

1. **Parameters are estimated once, on the train partition only** — the
   `BaselineForecaster` port makes this structural: `train_end_idx` is the
   estimation boundary, and a test asserts parameter insensitivity to any
   data after it (concept 5.2 I4).
2. **Conditioning state advances causally to each decision day** — for a
   decision at index t in the test block, the AR(1) mean conditions on
   r_t = `returns[t]`, the EWMA recursion runs through r_t, and the rolling
   window ends at t. A truncation-invariance test asserts that nothing after
   t influences the emission at t (concept 5.2 I3).
3. **No per-origin refit inside the test block.** Parameters do not update
   between decision days of the same fold; adaptation across time happens
   through the fold structure itself (expanding train per fold — ADR
   5.1.0001).

## Alternatives considered

### Alternative A — Per-origin refit (rolling-origin with updating)
- **Description:** re-estimate the parameters at every decision day using all
  data up to t (Tashman 2000's updated-origin evaluation; the M-competitions'
  operational style).
- **Pros:** each forecast uses the most information a real operator would
  have; classical and citable.
- **Cons:** the TFT/GBM **cannot** refit per day (cost and protocol) — the
  baselines would enjoy an information advantage inside the test block,
  making the H2 comparison asymmetric; the fold's `split_fingerprint` would
  no longer describe the estimation set of any single prediction; estimation
  reaching into the test block erodes the train-partition semantics the purge
  was built to protect.
- **Why rejected:** comparability of the preregistered family beats
  operational realism here — the baselines exist to be honest comparators,
  not production forecasters.

### Alternative B — Estimate on train + early_stop + calib
- **Description:** freeze parameters per fold but use everything before the
  test gap (not just train) as the estimation window.
- **Pros:** more estimation data; still frozen per fold.
- **Cons:** the ML models must keep early_stop for selection and calib
  untouched for the conformal invariant (ADR 5.1.0002) — their effective
  training set is train; giving baselines the extra blocks re-introduces the
  same asymmetry as Alternative A in milder form, and muddies what "train"
  means per fold.
- **Why rejected:** symmetry of the information protocol across the cohort is
  the point; the marginal data gain is small under expanding windows.

### Alternative C — Freeze the conditioning state at train end too
- **Description:** parameters AND state frozen at `train_end_idx`; every
  decision day of the test block reuses the same r_train_end / σ̂² / window.
- **Pros:** maximal separation of train and test.
- **Cons:** contradicts the preregistered formulas themselves — the emission
  is defined conditioning on the decision day's return (domain doc §3.5/§3.6:
  r_t, σ̂²_{t+1|t}); it would also desync the baselines from the TFT, whose
  encoder consumes observations up to the decision day. Conditioning on past
  observations is not leakage (ADR 0.0.0018 rule 1).
- **Why rejected:** it "protects" against something that is not a threat and
  breaks the formulas as preregistered.

### Alternative D — Do nothing / leave it to the implementation
- **Description:** let the adapter do whatever is convenient.
- **Cons:** the protocol changes reported numbers and the meaning of the
  H2 tests; silent choice is the preregistration leak the methodology forbids
  (overview §7).
- **Why rejected:** same rationale as ADR 0.0.0052 Alternative F.

## Consequences

### Positive
- Baselines, GBM and TFT share one information protocol per fold — the H2
  comparison is like-for-like and simple to state in the thesis.
- `train_end_idx` in the port makes the convention structural and testable
  (parameter-insensitivity + truncation-invariance tests), not documental.
- `dim_run` rows per (spec × fold) carry a `split_fingerprint` that truly
  describes the estimation set of every prediction of that run.

### Negative
- Baselines forgo intra-test-block parameter updates a real operator would
  perform — accepted: they are preregistered comparators, and the fold
  structure (expanding train) already provides re-estimation across time.

### Neutral / trade-offs accepted
- The EWMA has no estimated parameter (λ preregistered), so for it the
  decision reduces to the causal-state rule; its recursion seed is
  numerically irrelevant (decays as λⁿ) and is fixed as σ̂²₁ = r₁² in the
  Stage concept (D4), documented rather than preregistered.

## Implementation notes

- Port contract: `BaselineForecaster.forecast(..., train_end_idx=...,
  decision_indices=...)` — see concept 5.2 §4.
- Tests (scoped to what each family actually estimates — concept 5.2 I4):
  - (a) **Parameter freeze:** for `ar1` and `historical_mean`, mutate
    `returns[train_end_idx + 1:]` → the **estimated parameters**
    (μ̂, φ̂, σ̂²_ε; μ̂) are unchanged. For `ewma_vol`, `historical_quantiles`
    and `zero_return` nothing is estimated — the freeze assertion is that
    λ and W come from the `BaselineSpec` and are never re-estimated.
    Emission-invariance corollary only where the formula permits it: for
    `historical_mean`/`zero_return`, any post-train mutation leaves the
    emission unchanged; for `ar1`, mutating
    `returns[train_end_idx + 1 : t]` **excluding the conditioning r_t**
    leaves the emission at t unchanged. (For `ewma_vol` and
    `historical_quantiles` the emission legitimately depends on the causal
    path/window — asserting emission invariance there would be wrong.)
  - (b) **Truncation invariance (causality):** truncate `returns` right
    after decision t → emission at t unchanged; parametrized over all
    5 families.
- The same protocol statement should be reused verbatim by Stages 5.3/5.4
  (their trainers already behave this way by construction).

## References

- Related ADRs: [5.1.0001](./5_1_0001-expanding-window-walk-forward.md)
  (expanding train per fold), [5.1.0002](./5_1_0002-dedicated-calibration-partition.md)
  (calib untouched by selection), [0.0.0018](./0_0_0018-anti-leakage-non-negotiable.md)
  (causal timing; purge/embargo), [0.0.0052](./0_0_0052-baseline-quantile-emission-conventions.md)
  (emission conventions), [5.2.0001](./5_2_0001-baseline-math-in-domain-statsforecast-ar1-fit.md)
  (where the math lives, same Stage), [5.2.0003](./5_2_0003-historical-quantiles-window-252.md)
  (the rolling window whose content advances causally, W = 252, same Stage).
- Internal: domain doc [`quantile-model-training.md`](../domain/modeling/quantile-model-training.md)
  §2.5/§3.5/§3.6/§5.4 (Raschka exploratory/confirmatory discipline);
  concept 5.1 §4–§7; `docs/overview.md` §3/§7.
- External: Tashman, L. J. (2000). "Out-of-sample tests of forecasting
  accuracy: an analysis and review". *IJF* 16(4) (the rejected per-origin
  updating protocol); Raschka, S. (2018), arXiv:1811.12808 (selection uses
  train+val only; evaluation once with frozen choices).
- Originating issue: [#51](https://github.com/MarceloSanC/financial-forecasting/issues/51).
