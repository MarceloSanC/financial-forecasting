---
title: ADR 5.2.0003 — Rolling window of 252 trading sessions for the historical_quantiles baseline
description: Architecture Decision Record
when-use: Reference whenever revisiting the width of the historical_quantiles rolling window, before adding a window-sensitivity variant, or when questioning why the baseline uses ~1 trading year instead of a longer or expanding window
keywords: [adr, baselines, historical-quantiles, rolling-window, 252, historical-simulation, basel, type-7, preregistration, modeling]
status: accepted
created_at: 2026-07-15
updated_at: 2026-07-15
adr_id: 5.2.0003
decision: The historical_quantiles baseline computes its type-7 empirical quantiles over a rolling window of W = 252 trading sessions (~1 trading year) ending at each decision day — human-decided on 2026-07-15 (resolution of fork F1 of the Stage 5.2 concept), anchored on the regulatory Historical Simulation convention (Basel market-risk framework, ≥250-day observation floor) and on ADR 0.0.0052's n ≳ 250 note; W = 500 and the expanding window were rejected
context_stage: 5.2-baselines-naive-statistical
bounded_context: modeling
---

# ADR 5.2.0003 — historical_quantiles rolling window = 252 trading sessions

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The domain doc [`quantile-model-training.md`](../domain/modeling/quantile-model-training.md)
§3.7 preregisters *how* the `historical_quantiles` baseline estimates
(Hyndman & Fan type 7 — [ADR 0.0.0052](./0_0_0052-baseline-quantile-emission-conventions.md))
and *what it is* (Historical Simulation: the empirical distribution of a
historical window, an **unconditional** method — QRM §2.3.2, Eq. (2.32)), and
describes the window as **rolling** ("janela rolante"). It does **not** fix
the window width W.

Forces:

- **W changes reported numbers** — a short window yields tails that react to
  recent regimes; a long window yields stable but stale tails. By the same
  criterion that produced ADR 0.0.0052 ("whichever is chosen changes reported
  numbers — so the choice must be made before the confirmatory run,
  preregistered"), W is preregisterable methodology and therefore a **human
  decision**, not an implementation detail.
- **Tail mass at the extreme grid levels.** With τ = 0.05-ish levels in the
  dense grid, W must put enough observations below the extreme quantile for
  the type-7 interpolation to be meaningful (W = 252 → ~13 points below
  τ = 0.05).
- **Type-7 vs type-8 sensitivity.** ADR 0.0.0052 (Alternative B) notes the
  difference is negligible for **n ≳ 250** except slightly at extreme τ —
  the preregistered estimator choice was argued in exactly this window-size
  region.
- **Role in the hierarchy.** The pair {EWMA (conditional), historical_quantiles
  (unconditional-but-local)} separates the value of conditioning on recent
  volatility from the value of estimating empirical tails (domain doc §3.7);
  a window that never forgets would blur that contrast.

This fork (F1 of the Stage 5.2 concept) was escalated to the human and
decided by **Marcelo on 2026-07-15**.

## Decision

**W = 252 trading sessions (~1 trading year).** At each decision day t, the
baseline computes the type-7 sample quantiles of the last 252 returns
available up to and including t (`returns[t-251 .. t]`), and emits them
directly as the grid, identical for every horizon h (unconditional method).

Anchors:

- **Regulatory convention:** the Basel market-risk framework's Historical
  Simulation practice uses an observation-period floor of at least ~250
  business days (~1 year) — cited here as the established regulatory
  convention for HS windows, not as a verbatim quotation of a specific
  paragraph.
- **Internal coherence:** ADR 0.0.0052's "n ≳ 250" note — the region where
  the preregistered type-7 choice was argued to be insensitive.
- **Method identity:** QRM §2.3.2 (Historical Simulation over a window of
  the recent past); domain doc §3.7 ("janela rolante").

The width is fixed in the canonical factory
(`BaselineSpec.canonical_five(historical_quantiles_window=252)`); the
parameter remains overridable only for tests and future sensitivity analyses
(same posture as the type-8 sensitivity of ADR 0.0.0052 / speculative issue
[#48](https://github.com/MarceloSanC/financial-forecasting/issues/48)).

## Alternatives considered

### Alternative A — W = 500 (~2 trading years)
- **Description:** a two-year rolling window, common in risk-management
  practice for smoother Historical Simulation estimates.
- **Pros:** more observations in the extreme tails (~25 below τ = 0.05);
  more stable quantile paths.
- **Cons:** slower to adapt to regime changes (a crisis takes two years to
  leave the window); no citable floor/convention as crisp as the ~250-day
  regulatory one; weakens the deliberate contrast with the conditional EWMA.
- **Why rejected:** stability is not the baseline's job — being an honest,
  standard, reactive-enough unconditional comparator is; the 252 anchor is
  the one with an external convention behind it.

### Alternative B — Expanding window (the fold's entire train partition)
- **Description:** no new parameter — reuse the expanding train window
  (ADR 5.1.0001) as the quantile window, like `historical_mean` does.
- **Pros:** zero additional preregistered number; maximal sample size.
- **Cons:** contradicts the domain doc's own description of the spec as
  **rolling** (§3.7); mixes decades of regimes into the tails, making the
  baseline ever-more-static as folds advance; erases the
  conditional-vs-unconditional-but-local contrast the hierarchy is built on
  (the spec would collapse toward a "global empirical distribution" reading
  that QRM's HS does not describe).
- **Why rejected:** fidelity to the preregistered spec identity beats saving
  one parameter.

### Alternative C — Do nothing / decide at implementation time
- **Description:** let the Stage 5.2 implementation pick a width.
- **Cons:** W changes reported numbers; a silent in-PR choice is precisely
  the preregistration leak ADR 0.0.0052 exists to prevent (overview §7).
- **Why rejected:** same rationale as ADR 0.0.0052 Alternative F.

## Consequences

### Positive
- The last free parameter of the five baseline specs is preregistered before
  any confirmatory number exists; the emission surface of Stage 5.2 is now
  fully closed (conventions: ADR 0.0.0052; math placement: 5.2.0001;
  estimation protocol: 5.2.0002; window: this ADR).
- The choice is traceable to a human decision with an external regulatory
  anchor and internal coherence with the type-7 decision.

### Negative
- ~13 observations below τ = 0.05 make the extreme-tail estimates noisier
  than W = 500 would give — accepted: tail noise of an honest unconditional
  baseline is informative, not a defect to patch (same posture as the
  Gaussian-tail acceptance in ADR 0.0.0052).

### Neutral / trade-offs accepted
- A window-width sensitivity (e.g. W = 500) can join the type-8 sensitivity
  in speculative issue [#48](https://github.com/MarceloSanC/financial-forecasting/issues/48)
  under the same trigger (only if Step 6 calibration analysis shows the
  baselines' tails limit the interpretation of H2).
- With W = 252 < any fold's train length (expanding, anchored at the dataset
  start), the "insufficient window" error path (Stage 5.2 concept C1) is a
  guard, not an expected occurrence.

## Implementation notes

- Factory default: `BaselineSpec.canonical_five(historical_quantiles_window=252)`
  (Stage 5.2 concept §4); the `window >= 20` VO validation is a lower bound
  for constructibility, not the preregistered value.
- The window ends **at** the decision day t (includes r_t) — consistent with
  the causal-state rule of [ADR 5.2.0002](./5_2_0002-frozen-train-estimation-causal-state.md).
- Fewer than 252 returns available up to t → raise (raise-don't-fabricate,
  ADR 0.0.0018).

## References

- Related ADRs: [0.0.0052](./0_0_0052-baseline-quantile-emission-conventions.md)
  (type-7 decision and the n ≳ 250 note),
  [5.2.0001](./5_2_0001-baseline-math-in-domain-statsforecast-ar1-fit.md)
  (where the type-7 math lives),
  [5.2.0002](./5_2_0002-frozen-train-estimation-causal-state.md)
  (causal window content), [5.1.0001](./5_1_0001-expanding-window-walk-forward.md)
  (expanding train — the rejected Alternative B's window),
  [0.0.0018](./0_0_0018-anti-leakage-non-negotiable.md) (raise, no clamp).
- Internal: domain doc [`quantile-model-training.md`](../domain/modeling/quantile-model-training.md)
  §3.7; Stage 5.2 concept §7 D6 / §13 (fork F1, human decision 2026-07-15).
- External: McNeil, A. J.; Frey, R.; Embrechts, P. (2005). *Quantitative Risk
  Management*. Princeton UP. (§2.3.2, Eq. (2.32) — Historical Simulation over
  a window.) Basel market-risk framework — regulatory convention of a
  ≥250-business-day observation floor for Historical Simulation (cited as
  convention, not verbatim text). Hyndman, R. J.; Fan, Y. (1996). "Sample
  Quantiles in Statistical Packages". *The American Statistician*, 50(4).
- Originating issue: [#51](https://github.com/MarceloSanC/financial-forecasting/issues/51);
  fork resolution recorded 2026-07-15 (Checkpoint A session).
