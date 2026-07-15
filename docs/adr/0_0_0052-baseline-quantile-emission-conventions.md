---
title: ADR 0.0.0052 — Baseline quantile-emission conventions (Gaussian μ=0 EWMA, type-7 sample quantile, parametric AR(1), zero_return ≡ random walk)
description: Architecture Decision Record
when-use: Reference before implementing or changing how any Step 5 baseline converts its estimated state into the dense quantile grid, before adding a baseline variant (t-Student EWMA, type-8 quantile), or when questioning why the project has 5 baseline specs instead of 6
keywords: [adr, baselines, quantile-emission, ewma, riskmetrics, type-7, hyndman-fan, ar1, random-walk, zero-return, gaussian, preregistration, modeling]
status: accepted
created_at: 2026-07-14
updated_at: 2026-07-14
adr_id: 0.0.0052
decision: Baselines emit quantiles under four preregistered conventions — EWMA-vol uses Gaussian quantiles with μ=0 (canonical RiskMetrics); all empirical quantiles use Hyndman & Fan type 7 (the R/NumPy default); AR(1) emits parametric Gaussian quantiles from the closed-form h-step mean and variance; and zero_return ≡ driftless random walk of the log-price collapse into a single spec (5 baseline specs) — consolidated in one ADR because they were decided in the same act with the same rationale.
context_stage: 0.0-global
---

# ADR 0.0.0052 — Baseline quantile-emission conventions

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 5.2's DoD requires every baseline to emit the same dense quantile grid
as the candidate (point baselines as a degenerate grid), aligned by
`target_timestamp`. The literature offers **several defensible conventions**
for each conversion (Gaussian vs t-Student tails; 9 sample-quantile types;
parametric vs empirical AR(1) intervals; two readings of "random walk"), and
whichever is chosen changes reported numbers — so the choice must be made
before the confirmatory run, preregistered, and traceable (anti-p-hacking
spine, overview §7).

Forces:

- **Target semantics constrain everything:** the target at horizon h is the
  ONE-day return realized at session t+h, so EWMA variance is flat in h (RMTD
  Eq. [5.18], by induction), AR(1) variance grows toward the unconditional,
  and no √h/√T scaling rule applies (context fixed by ADR 3.5.0001/4.3.0001,
  not decided here).
- **Reproducibility vs source fidelity:** Hyndman & Fan (1996) recommend
  type 8, but every default in the project's stack (R, NumPy, pandas) is
  type 7.
- **Baselines must stay baselines:** an emission convention that already
  recalibrates tails empirically would overlap the role of the conformal
  benchmark (Step 7.2) and blur what H2 compares.
- The full theory (formulas, citations, behavior in h) lives in the domain
  doc [`quantile-model-training.md`](../domain/modeling/quantile-model-training.md)
  §3; this ADR records the decisions and rejected alternatives.

## Decision

Four conventions govern how the Step 5 baselines (Stage 5.2) convert their
estimated state into the project's dense quantile grid. All were decided by
the human (Marcelo) on 2026-07-14 at the Step 5 domain-gate session, on top of
research verified adversarially against primary sources (issue
[#47](https://github.com/MarceloSanC/financial-forecasting/issues/47)):

1. **EWMA-vol → Gaussian quantiles with μ = 0.** The EWMA volatility baseline
   emits q̂_τ = σ̂·Φ⁻¹(τ), with zero mean — the canonical RiskMetrics
   formulation (RiskMetrics Technical Document 1996 derives the recursion
   assuming zero sample mean, Eq. [5.3] p. 81; location-scale conversion per
   McNeil-Frey-Embrechts 2005, Eq. (2.19)).
2. **Sample quantiles = Hyndman & Fan type 7, everywhere.** Every empirical
   quantile computed by a baseline uses type 7 (h = (n−1)p + 1), the default
   of R, NumPy and pandas — fixed and preregisterable across all baselines.
3. **AR(1) → parametric Gaussian quantiles.** Conditional mean
   μ + φ^h(r_t − μ) plus the closed-form h-step forecast-error standard
   deviation (Box-Jenkins 5th ed., Eq. (5.1.16), §5.1.1, p. 132, ψ₀ = 1;
   Hamilton 1994, ch. 4 §4.2, pp. 77–85), converted with Gaussian z_τ.
4. **zero_return ≡ driftless random walk of the log-price → one spec.** With
   the target fixed as the 1-day return realized at t+h
   ([ADR 3.5.0001](./3_5_0001-target-definition-backward-log-return.md) +
   [ADR 4.3.0001](./4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md)),
   the driftless RW of the log-price implies r̂_{t+h} = 0 for all h — identical
   to `zero_return`. Stage 5.2 therefore implements **5 distinct baseline
   specs**, and adjusts the roadmap's "6 baselines" wording in its own PR.

The four conventions are **consolidated in a single ADR** because they were
decided in the same act with the same rationale (fixing the baseline emission
surface before Stage 5.2), following the precedent of
[ADR 0.0.0003](./0_0_0003-formalize-domain-and-audits-doc-categories.md)
Alternative A (same-act decisions do not get one ADR each).

## Alternatives considered

### Alternative A — t-Student (or both) for the EWMA conversion
- **Description:** emit EWMA quantiles with standardized-t tails
  (q̂_τ = σ̂·t_ν⁻¹(τ), rescaling σ̂ by √((ν−2)/ν) since the t's σ is a scale
  parameter, not the standard deviation — McNeil-Frey-Embrechts §4.4.2,
  pp. 161–162), either instead of or alongside the Gaussian.
- **Pros:** heavy conditional tails are a documented stylized fact of returns;
  likely better tail calibration at τ = 0.05/0.95.
- **Cons:** requires choosing/estimating ν (a new degree of freedom to
  preregister); departs from the canonical RiskMetrics formulation; a
  Gaussian-EWMA whose tails miscalibrate is itself an **informative** result
  (it is what the TFT/conformal should beat), not a defect to patch.
- **Why rejected:** parsimony and fidelity to the canonical source. Registered
  as a **speculative future improvement** (speculative issue
  [#48](https://github.com/MarceloSanC/financial-forecasting/issues/48)),
  triggered only if Step 6 calibration analysis shows the parametric
  baselines' tails limit the interpretation of H2.

### Alternative B — Type-8 sample quantile (the paper's recommendation)
- **Description:** use Hyndman & Fan's median-unbiased type 8
  (h = (n + 1/3)p + 1/3) instead of type 7.
- **Pros:** fidelity to the primary source's own recommendation;
  approximately median-unbiased regardless of distribution.
- **Cons:** not the default of any library in the stack — every consumer must
  remember to override, and any accidental default silently diverges from the
  preregistered spec; with rolling windows n ≳ 250 the difference is
  negligible except slightly at extreme τ.
- **Why rejected:** reproducibility of the whole stack wins for a baseline;
  type 8 registered as an optional sensitivity in the same speculative future
  issue as Alternative A.

### Alternative C — Empirical per-horizon residual quantiles for AR(1)
- **Description:** emit q̂_τ(h) = r̂_{t+h|t} + Q̂_τ({ê_{s,h}}), the empirical
  quantile of in-sample h-step forecast errors.
- **Pros:** drops the normality assumption; possibly asymmetric intervals.
- **Cons:** requires horizon-specific residual sets with enough mass at
  τ = 0.05; and empirically recalibrating intervals from held-out errors is
  functionally what the conformal benchmark (CQR, Stage 7.2) does — the
  baseline would duplicate the role of a different, preregistered component.
- **Why rejected:** keeps AR(1) a textbook parametric baseline; empirical
  recalibration stays where it belongs (conformal, Step 7.2).

### Alternative D — Naive-on-returns, or keeping both random-walk specs
- **Description:** either read "random walk" as the naive method applied to
  the **returns series** (r̂_{t+h} = r_t — the FPP3 §5.2 `RW()` reading), or
  keep `random_walk` and `zero_return` as two separate specs.
- **Pros:** naive-on-returns is a genuinely distinct predictor; keeping both
  specs matches the roadmap's original "6 baselines" wording.
- **Cons:** naive-on-returns treats the returns series itself as a random
  walk — mis-specified for approximately serially-uncorrelated daily returns,
  so it adds a knowingly broken comparator; keeping both specs duplicates one
  predictor under two names (identical point forecast and bands for the 1-day
  target), inflating the comparison family with a redundant member.
- **Why rejected:** the project fixes the "driftless RW of the log-price"
  reading, under which the collapse is mathematically exact — one spec,
  honestly labeled "zero_return ≡ RW without drift". The label ambiguity is
  documented in the domain doc (§3.2).

### Alternative E — One ADR per convention
- **Description:** four separate ADRs, one per decision.
- **Pros:** each ADR minimal and independently supersedable.
- **Cons:** the four decisions share one act, one motivation (fix the emission
  surface before 5.2) and one evidence base (the same verified research);
  four ADRs would repeat the context four times and cross-reference each
  other — the "eco divergente" CONVENTIONS §0 warns against.
- **Why rejected:** precedent of ADR 0.0.0003 Alternative A: same-act,
  same-rationale decisions are consolidated. Cheaply reversible — a future
  change to one convention supersedes only the affected item via a new ADR.

### Alternative F — Do nothing / decide at implementation time
- **Description:** leave the conversions to whatever the Stage 5.2
  implementation happens to pick.
- **Pros:** zero ceremony now.
- **Cons:** every one of these choices changes reported numbers; deciding them
  silently inside an implementation PR would make them neither preregistered
  nor traceable — exactly the p-hacking surface the project's methodology
  forbids (overview §7).
- **Why rejected:** emission conventions are load-bearing methodology, not
  implementation detail.

## Consequences

### Positive
- Stage 5.2 has an unambiguous, preregisterable emission spec for all five
  baselines; no convention is chosen inside an implementation PR.
- Every convention is traceable to a verified primary source and to the human
  decision that picked it.
- The comparison family shrinks to five genuinely distinct baselines
  (no duplicated predictor).

### Negative
- Gaussian tails on EWMA/AR(1) will likely under-cover at extreme τ for fat-
  tailed daily returns — accepted as an informative property of the baselines
  (documented in the domain doc §3.6), at the cost of a predictable
  calibration finding.
- The roadmap's "6 baselines" wording is stale until Stage 5.2 adjusts it
  (deliberately deferred to that Stage's PR).

### Neutral / trade-offs accepted
- Type 7 over the paper-recommended type 8: reproducibility over source
  fidelity, difference negligible at n ≳ 250 except slightly at extreme τ.
- **Speculative future improvements** (single speculative issue
  [#48](https://github.com/MarceloSanC/financial-forecasting/issues/48)):
  t-Student EWMA variant (with the √((ν−2)/ν)
  rescale, QRM §4.4.2) and type-8 sensitivity for the rolling-quantiles
  baseline. Trigger condition: after the confirmatory cohort, IF Step 6
  calibration analysis shows the parametric baselines' tails limit the
  interpretation of H2.

## Implementation notes

- Formulas, per-horizon behavior and full citations: domain doc
  [`quantile-model-training.md`](../domain/modeling/quantile-model-training.md)
  §3 (baselines) and §2 (fundamentals).
- Point baselines (zero_return, historical_mean) emit the **degenerate grid**;
  that convention predates this ADR (roadmap 5.2 DoD +
  [ADR 4.3.0002](./4_3_0002-quantile-forecast-dense-grid-guardrail.md)) and is
  only *grounded* (not decided) here.
- The "6 baselines" → 5 specs wording fix in the roadmap happens in Stage
  5.2's PR, not this one. It must cover **both** occurrences in
  `docs/roadmap.md`: the Stage 5.2 DoD **and** the Stage 5.5 DoD (each says
  "6 baselines").

## References

- Related ADRs: [ADR 3.5.0001](./3_5_0001-target-definition-backward-log-return.md)
  (target = backward 1-day log-return);
  [ADR 4.3.0001](./4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md)
  (target_timestamp by session indexing);
  [ADR 4.3.0002](./4_3_0002-quantile-forecast-dense-grid-guardrail.md)
  (dense grid + monotonic guardrail);
  [ADR 0.0.0051](./0_0_0051-modeling-domain-doc-scope-and-boundary.md)
  (scope of the domain doc, same session);
  [ADR 0.0.0003](./0_0_0003-formalize-domain-and-audits-doc-categories.md)
  (consolidation precedent, Alternative A).
- Internal: roadmap Stage 5.2 DoD (degenerate grid, alignment);
  [`docs/domain/modeling/quantile-model-training.md`](../domain/modeling/quantile-model-training.md) §3.
- External (primary sources, verified against the documents):
  - J.P. Morgan/Reuters (1996). *RiskMetrics — Technical Document*, 4th ed.
    (Eq. [5.3] §5.2.1 p. 81, zero-mean derivation; Eq. [5.18] p. 86;
    λ = 0.94 §5.3.2.2 pp. 99–100).
  - McNeil, A. J.; Frey, R.; Embrechts, P. (2005). *Quantitative Risk
    Management*. Princeton UP. (Eqs. (2.19)–(2.20) §2.2.2 pp. 39–40;
    √((ν−2)/ν) rescale §4.4.2 pp. 161–162; Historical Simulation §2.3.2
    Eq. (2.32) p. 50.)
  - Hyndman, R. J.; Fan, Y. (1996). "Sample Quantiles in Statistical
    Packages". *The American Statistician*, 50(4), 361–365.
    DOI: 10.1080/00031305.1996.10473566.
  - Hamilton, J. D. (1994). *Time Series Analysis*. Princeton UP.
    (Ch. 4, §4.2, pp. 77–85.)
  - Box, G. E. P.; Jenkins, G. M.; Reinsel, G. C.; Ljung, G. M. (2015). *Time
    Series Analysis: Forecasting and Control*, 5th ed., Wiley.
    (Eq. (5.1.16), §5.1.1, p. 132.)
  - Campbell, J. Y.; Lo, A. W.; MacKinlay, A. C. (1997). *The Econometrics of
    Financial Markets*. Princeton UP. (Ch. 2 §2.1, RW1–RW3.)
  - Hyndman, R. J.; Athanasopoulos, G. (2021). *Forecasting: Principles and
    Practice*, 3rd ed., OTexts. (§5.2 naive/"random walk" label; §5.5
    intervals.)
  - Gu, S.; Kelly, B.; Xiu, D. (2020). "Empirical Asset Pricing via Machine
    Learning". *RFS*, 33(5), 2223–2273. DOI: 10.1093/rfs/hhaa009. (Zero
    benchmark, Eq. (19) pp. 2245–2246.)
- Originating issue:
  [#47](https://github.com/MarceloSanC/financial-forecasting/issues/47).
