---
title: ADR 0.0.0002 — Frame the study as probabilistic calibration, not point accuracy
description: Architecture Decision Record
when-use: Reference when questioning what the model is being judged on, when choosing primary metrics/hypotheses, or before reintroducing point-accuracy claims
keywords: [adr, framing, calibration, probabilistic-forecasting, pinball, returns, scope]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "0.0.0002"
decision: The scientific object is the predictive distribution (calibration and sharpness) plus feature-contribution, never point accuracy of the daily-return mean
context_stage: 1.1-bootstrap
---

# ADR 0.0.0002 — Frame the study as probabilistic calibration, not point accuracy

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The project studies a Temporal Fusion Transformer (TFT) on **daily stock returns** (AAPL
pilot, horizons h+1 and h+7, h+30 supplementary). The naïve research instinct — copied
from the prior implementation and from most forecasting tutorials — is to judge a model by
how close its point prediction is to the realized value (RMSE / MAE / directional accuracy on
the conditional mean).

Forces at play:

- For liquid daily equity returns, the **predictable component of the mean is tiny**: out-of-sample
  R² is on the order of ~0.1–1% (Gu–Kelly–Xiu 2020). A study that bets its verdict on point
  accuracy is, with high probability, measuring noise and will produce a non-result that is hard
  to defend as anything other than "the mean is unforecastable" — already known.
- The **predictive distribution**, by contrast, carries real signal: volatility clusters, tail
  behavior and the *shape* of the conditional distribution are far more forecastable than its
  center. Calibration (do the predicted quantiles match empirical frequencies?) and sharpness
  (how tight are the intervals?) are quantities a TFT can plausibly get right and that the
  literature has well-defined, defensible tooling for (pinball loss, PICP, reliability,
  Christoffersen, CRPS).
- The thesis must survive an academic defense. A refutation is acceptable, but only if the
  question being refuted is the *right* question. "Calibrated probabilistic returns" is the
  right question; "beat the market on point forecasts" is not.
- This framing must be fixed **before any business code is written**, because it dictates the
  primary metric (pinball), the gate hypothesis (H1 = calibration), the value objects in the
  domain (quantile forecasts, coverage series) and what counts as success.

## Decision

The **scientific object of this project is the predictive distribution** — its calibration and
sharpness — complemented by a **descriptive analysis of feature-family contribution**. Point
accuracy of the daily-return mean is **not** a success criterion and is **not** a headline claim.

Concretely:

- The **primary metric is pinball loss** over a dense quantile grid (CRPS complementary);
  Diebold–Mariano + Holm + MCS provide the inferential comparison to baselines.
- **H1 (calibration) is the primary object and an eligibility gate**: skill of a mis-calibrated
  model is not compared. **H2 (relative skill)** is judged on pinball, not on point error.
  **H3 (feature contribution)** is descriptive, never causal.
- **Refutation is a valid result.** If the candidate is not better-calibrated or not more
  skillful than the strong baselines, that is reported honestly — the framing makes that an
  informative outcome rather than a failure.

This is a pre-decided foundation (Overview §1, §4, §11) materialized here as a contract consumed
by every downstream stage.

## Alternatives considered

### Alternative A — Point-accuracy framing (status quo / prior implementation)
- **Description:** Judge the model by RMSE/MAE/directional accuracy on the conditional mean of the
  daily return.
- **Pros:** Familiar; trivial to compute; matches most tutorials and the prior codebase.
- **Cons:** Measures a near-unforecastable quantity; almost guaranteed to yield a noise-level
  non-result; not academically defensable as a positive contribution; discards the signal that
  actually exists in the distribution.
- **Why rejected:** It optimizes and reports the wrong target. The mean of daily returns is
  ~unforecastable (R² OOS ~0.1–1%); a study built on it cannot make a defensible claim.

### Alternative B — Trading / economic-value framing
- **Description:** Judge the model by simulated PnL, Sharpe, or a trading backtest.
- **Pros:** Directly "useful"; intuitive to non-technical stakeholders.
- **Cons:** Out of scope (Overview §3 explicitly excludes trading/backtesting/portfolio);
  confounds model quality with execution, costs, and strategy design; invites "beat the market"
  claims the project explicitly disclaims.
- **Why rejected:** Scope and defensibility — it answers a different, harder, and out-of-scope
  question.

### Alternative C — Do nothing / leave framing implicit
- **Description:** Don't fix a framing; let metrics and hypotheses emerge during modeling.
- **Why rejected:** The framing determines the domain value objects, the primary metric, the gate
  hypothesis and the pre-registration. Leaving it implicit invites metric-shopping and p-hacking
  (choosing the framing that looks best after seeing results), which the project structurally
  forbids (Overview §7).

## Consequences

### Positive
- The study targets a quantity that carries real signal and is academically defensable.
- Primary metric (pinball), gate (calibration), and domain value objects all follow directly.
- Refutation becomes informative rather than embarrassing.

### Negative
- Stakeholders expecting a "the model predicts tomorrow's price" deliverable must be re-educated;
  the value object is a distribution, not a number.
- Calibration/sharpness tooling (pinball, Christoffersen, CRPS, conformal) is heavier to implement
  and validate than RMSE.

### Neutral / trade-offs accepted
- We accept reporting *distributional* skill only; we explicitly do not claim point predictability
  of the mean, even if a marginal positive R² appears in some slice.

## References

- Related ADRs: [0.0.0009](./0_0_0009-pinball-primary-crps-complementary.md) (pinball primary),
  [0.0.0005](./0_0_0005-calibration-as-primary-object-and-gate.md) (H1 as gate) — to be authored in
  later stages.
- External: Gu, Kelly, Xiu (2020) "Empirical Asset Pricing via Machine Learning"; Gneiting (2011)
  on proper scoring rules; Koenker & Bassett (1978).
- Overview: `docs/overview.md` §1, §4 (Hipóteses, Critérios de sucesso), §11 (Científicas).
