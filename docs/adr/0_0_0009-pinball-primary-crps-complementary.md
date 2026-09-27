---
title: ADR 0.0.0009 — Pinball as primary metric; CRPS reported as 2 × grid-average pinball, never as independent evidence
description: Architecture Decision Record
when-use: Reference when questioning which score decides H2, how "CRPS" is computed from a finite quantile grid, why it is not compared to published CRPS values, or which oracle validates it
keywords: [adr, pinball, crps, quantile-grid, scoringrules, scoring-rule, evaluation, step-6]
status: proposed
created_at: 2026-09-26
updated_at: 2026-09-26
adr_id: 0.0.0009
decision: The primary metric is the grid-average pinball loss (ρ_τ scale, equal weights). The reported CRPS is the uniform-quadrature estimator CRPS_Q = 2 × grid-average pinball on the common grid, labelled as such, used only for scale and per-τ profile, never as a second verdict and never compared to published CRPS.
context_stage: 0.0-global
bounded_context: evaluation
---

# ADR 0.0.0009 — Pinball primary; CRPS_Q complementary

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`proposed` — flips to `accepted` with the evaluation domain doc (ADR 0.0.0054).

## Context

Overview §11 planned "pinball primary + CRPS complementary". With a finite
grid of ~7 levels, "CRPS" only exists through an estimator, and three families
exist (uniform quadrature; quantiles as an ensemble; interpolated quantile
function with tail conventions). Fork **B-CRPS** of the evaluation domain doc
(§3.2), class C (convention), closed on 2026-09-26.

## Decision

- **Primary metric:** P̄_G, the grid-average pinball, ρ_τ scale (no factor 2),
  equal weights, per horizon.
- **CRPS reported:** CRPS_Q = 2·P̄_G, uniform quadrature on the common grid.
  Always labelled "CRPS_Q = 2 × grid-average pinball (equal weights)". Its role
  is (i) scale in units of y, comparable to the MAE of the project's point
  baselines, and (ii) the per-τ profile. With a common grid it carries the
  **same ordering** as P̄_G for every model and observation (same DM, same
  MCS): it is **not** independent evidence.
- **Not comparable to published CRPS:** Berrisch & Ziel (2023, Eq. (9)) justify
  the approximation only "for an equidistant dense grid"; the project grid is
  neither.
- **Oracle:** `scoringrules.crps_quantile` (verified in 0.11.0: `2 * mean` of
  the pinball over the passed levels, equal weights, no interpolation). Stage
  6.1 **pins** the version in `pyproject.toml`/`uv.lock` (not a dependency
  today).

Decision record (doc §10.1): `[decision:C] B-CRPS`, rung 2 (oracle default).

## Alternatives considered

### Alternative A — Quantiles as an ensemble (INT/NRG/PWM/Fair)
- **Cons:** ignores the τ levels; biased for regular levels; ties make the
  estimators "inaccurate … biased" (Zamo & Naveau 2018 §3.2.3).
- **Why rejected:** a new metric with its own bias and no exact Dirac case.

### Alternative B — Linear spline quantile function + tail convention
- **Cons:** the number depends on how [0, τ_1) and (τ_K, 1] are extrapolated.
- **Why rejected:** the "extra" distributional information comes from a
  convention, not from the data.

### Alternative C — Report "CRPS" unqualified and compare to literature
- **Why rejected:** unsupported by the source of the approximation (dense,
  equidistant grid).

## Consequences

- Positive: one number less to reconcile; exact Dirac fixture
  (CRPS_Q = |y − x| on a symmetric grid); a library oracle.
- Negative: no cross-paper CRPS comparison; the grid decides what CRPS_Q means.
- Stage 6.1 must add `scoringrules` pinned.

## References

- Berrisch, J.; Ziel, F. (2023). "CRPS learning". *Journal of Econometrics*
  237(2). arXiv:2102.00968v3, §3.1 Eq. (9).
- Bracher et al. (2021), App. A Eq. (6); Gneiting & Raftery (2007) §4.2.
- Doc: [`probabilistic-forecast-evaluation.md`](../domain/evaluation/probabilistic-forecast-evaluation.md) §3.2, §10.1.
- Issue [#78](https://github.com/MarceloSanC/financial-forecasting/issues/78).
