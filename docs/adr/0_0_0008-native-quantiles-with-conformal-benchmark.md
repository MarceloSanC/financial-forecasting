---
title: ADR 0.0.0008 — Native quantiles as the H1 object, asymmetric split-CQR as coverage benchmark (4 invariants; unweighted variant of record, NexCP ρ = 0.99 sensitivity)
description: Architecture Decision Record
when-use: Reference when questioning why H1 judges the native quantile grid and not a conformalized one, how CQR is applied (asymmetric, per pair, per horizon, per seed), which variant is of record and which is sensitivity, why ACI/EnbPI are out, or how conformal coverage may be worded
keywords: [adr, h1, native-quantiles, conformal, cqr, split-conformal, asymmetric-cqr, nexcp, aci, enbpi, exchangeability, empirical-coverage, calibration-partition, per-horizon, seeds, inference, step-7]
status: accepted
created_at: 2026-10-06
updated_at: 2026-10-06
adr_id: 0.0.0008
decision: H1 judges the candidate's native (rearranged) quantile grid; CQR is a descriptive coverage benchmark applied with the asymmetric split-CQR (Romano et al. 2019, Theorem 2, inflated finite-sample quantile) to the three symmetric pairs, per fold, horizon and seed, on the dedicated embargoed calib partition, always worded as empirical coverage; the unweighted variant is of record and NexCP with fixed weights ρ^(n+1−i), ρ = 0.99, is a preregistered sensitivity; ACI and EnbPI stay out of the confirmatory path.
context_stage: 0.0-global
bounded_context: inference
---

# ADR 0.0.0008 — Native quantiles with a conformal benchmark

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — ratified on 2026-10-06 by delegation of the human (Marcelo),
together with the inference domain doc (issue #150); the Step 7 gate is
closed. Supersedes the roadmap's "variant deferred to the Stage":
the variant of record and the sensitivity are fixed here; Stage 7.2 keeps the
implementation and preregistration details (`7_2_0001`).

## Context

Overview §3/§11 made the native quantile grid the object of H1 and CQR a
comparative benchmark ("the obvious question in a calibration study"), with
four invariants (overview §8 R-CONFORMAL-1) and the variant (split-CQR × NexCP
× not doing it) deferred. Already ratified: the dedicated, disjoint, most
recent, embargoed `calib` partition (ADR 5.1.0002); early-stop never doubles as
calib (modeling §5.3); conformal coverage is empirical, not guaranteed, because
exchangeability fails for returns (ADR 5.1.0002); CQR is neither the H1
yardstick nor in the H2 family (evaluation §4.4, §6.4; ADR 0.0.0054 Alt. B);
baselines do not recalibrate tails empirically because that is the conformal
benchmark's role (ADR 0.0.0052 Alt. C).

What was open: the CQR mechanics on a 7-quantile grid, the variant, the
treatment of horizons, pairs and seeds, and how to compare native and
conformal coverage.

## Decision

1. **Object of H1 = native grid.** H1 judges the candidate's rearranged native
   quantiles (evaluation §2.2, §8.5). The conformal intervals never replace
   them in the verdict.
2. **Mechanics (E): asymmetric split-CQR.** One-sided scores per tail,
   E^lo = q̂_lo − Y and E^hi = Y − q̂_hi, each corrected by its
   ⌈(n+1)(1−α_tail)⌉-th smallest score (the inflated (1−α)(1+1/n) quantile of
   Romano et al. 2019 Eq. (11) — equation numbering not checked against the
   source), α_lo = τ_lo, α_hi = 1 − τ_hi (Theorem 2,
   Eqs. (15)–(16)). Reason: the H1 gate is per tail (ADR 0.0.0011, 6.5.0006),
   and only Theorem 2 yields a per-tail object. Cost: slightly wider intervals
   (paper §6.2). The input pair is the rearranged one (the delivered forecast).
3. **Four invariants.** (i) calibrate only on the dedicated `calib`
   partition; (ii) per fold and per horizon (and per seed, pair, tail);
   (iii) embargo — `calib` ends `max_horizon + embargo` sessions before test;
   (iv) language — every conformal coverage figure is labelled "empirical
   coverage (not guaranteed)". The overview's "language" and the roadmap's
   "empirical coverage" are the same invariant.
4. **Variant of record (C, rung 2): unweighted split-CQR.** It is the default
   of the reference oracle (MAPIE 1.5.0 implements no weights) and recency is
   already provided by the most-recent calib (ADR 5.1.0002).
5. **Sensitivity: NexCP** (Barber et al. 2023 Eqs. (10)–(11), fixed weights
   w_i = ρ^(n+1−i), extended to arbitrary scores in its Appendix A) with
   **ρ = 0.99**, preregistered, profile only. ρ ≤ 0.98 is excluded: with
   n = 252 the mass at +∞ is w̃_{n+1} = (1−ρ)/(1−ρ^(n+1)) = 0.0201 > 0.02,
   so the 0.02 tail would become infinite (derivation); ρ = 0.99 gives 0.0109
   and is the value of the paper's experiments (§5.1).
6. **ACI and EnbPI out (E).** Their guarantees rely on online updates with the
   realized value at each step, incompatible with one calibration per fold.
   ACI's main guarantee is a long-run frequency bound (Gibbs & Candès 2021
   Prop. 4.1) that needs Y observed online; §4.2 shows only *approximate*
   marginal coverage under small drifts in a specific model, and §7 lists
   delayed/batched feedback as an open problem. EnbPI leverages feedback
   (Xu & Xie 2021 §3.1). See also Oliveira et al. 2024 §2.
7. **Per horizon (E).** Marginal coverage per horizon, each horizon calibrated
   separately (Oliveira et al. 2024 Theorems 1/4; ADR 0.0.0010). Joint
   Bonferroni coverage (Stankevičiūtė et al. 2021 §3.3) is rejected: it
   assumes independent series.
8. **Pairs (C).** All three symmetric pairs, tails independent; primary
   comparison pair (0.10, 0.90), the H1 pair (ADR 6.5.0006). Distributional
   conformal is rejected (it needs F̂ beyond [0.02, 0.98]). Nesting across
   conformalized pairs is not guaranteed (Gupta, Kuchibhotla & Ramdas 2022,
   Tab. 1); the conformal output is **not rearranged** (that would void the
   per-tail guarantee) and the nesting-violation rate is profile. The extreme
   pair (τ·n ≈ 5 in calib) is reported, not excluded.
9. **Seeds (C, rung 1: coherence with ADR 0.0.0010).** Conformalize each seed separately; report the
   mean coverage across seeds, dispersion in the profile (ADR 0.0.0010 item 5).
10. **Dispersion (E).** Report the conditional-coverage reference
    Beta(n+1−l, l), l = ⌊(n+1)α⌋ (Angelopoulos & Bates 2023 §3.2), for n = 252,
    as a reference valid only under exchangeability.
11. **Comparison (C).** Descriptive, reusing evaluation §4 (ĉ(τ), PICP/MPIW,
    Wilson with n = aligned points, hits) without re-derivation; no new
    hypothesis test.
12. **Preregistration.** Variant of record, NexCP ρ, pairs, asymmetry, seed
    treatment, per-horizon rule and comparison metrics are preregistered with
    the 6.5 machinery before any metric on the real cohort (ADR 6.5.0008
    item 6); the form is Stage 7.2's technical decision.

**Declared limit.** Calibrated once per fold, a regime break *inside* the test
window has k = 0 in Barber et al.'s changepoint bound (§4.4) — no bound covers
it. This is why coverage is always empirical.

## Alternatives considered

### Alternative A — Symmetric CQR (Theorem 1)
- **Pros:** narrower intervals with the same pair-level guarantee.
- **Cons:** spreads miscoverage arbitrarily across tails; not comparable tail
  by tail with the native grid, while the H1 gate is per tail.
- **Why rejected:** PICP is invariant to a common shift of both tails
  (evaluation §4.2).

### Alternative B — NexCP as the variant of record
- **Pros:** explicit protection against drift.
- **Cons:** the weight choice has no source for daily returns ("how to choose
  weights optimally … future work", Barber §4.3); the bound still depends on
  unknown TV distances; no weighted oracle in MAPIE.
- **Why rejected:** kept as preregistered sensitivity instead.

### Alternative C — Not doing CQR
- **Why rejected:** contradicts overview §3/§11 (ratified benchmark).

### Alternative D — ACI / EnbPI in the confirmatory path
- **Why rejected:** see Decision 6.

### Alternative E — Conformalize the seed average
- **Pros:** valid (Romano §4; Fakoor et al. 2023 §5.3).
- **Cons:** evaluates an ensemble, not the candidate; ADR 0.0.0010 rejected
  prediction ensembles for changing the object.
- **Why rejected:** coherence with ADR 0.0.0010.

## Consequences

### Positive
- The obvious examiner question ("would a conformal recalibration fix it?")
  is answered by a preregistered, per-tail, per-horizon benchmark.
- Native calibration (H1) and conformal coverage never get mixed in the verdict.

### Negative
- 3 pairs × 2 tails × 2 horizons × 6 folds × 10 seeds calibrations, plus the
  NexCP sensitivity.
- n = 252 per calib gives wide fold-to-fold dispersion (e.g. 0.939–0.978 for
  the 96 % pair); results must be read with that reference.
- Inference (Stage 7.1) must emit calib-partition predictions, which no
  trainer emits today.

### Neutral / trade-offs accepted
- MAPIE is not pinned in `uv.lock`; its exact role (backend vs oracle) is
  Stage 7.2's decision (ADR 0.0.0056 / 6.1.0001 pattern).

## References

- Romano, Y.; Patterson, E.; Candès, E. (2019). "Conformalized Quantile Regression". *NeurIPS 32*. arXiv:1905.03222. (Eqs. (9), (11) — equation numbering not checked; Theorems 1–2; §4; §6.2.)
- Barber, R. F.; Candès, E. J.; Ramdas, A.; Tibshirani, R. J. (2023). "Conformal prediction beyond exchangeability". *Annals of Statistics*, 51(2), 816–845. DOI: 10.1214/23-AOS2276. (Eqs. (10)–(11); §4.1 Theorem 2; §4.3–§4.4; §5.1; Appendix A.)
- Lei, J. et al. (2018). *JASA*, 113(523), 1094–1111. DOI: 10.1080/01621459.2017.1307116.
- Oliveira, R. I.; Orenstein, P.; Ramos, T.; Romano, J. V. (2024). *JMLR*, 25(225). arXiv:2203.15885. (§2; Theorems 1, 4, 6.)
- Gibbs, I.; Candès, E. (2021). *NeurIPS 34*. arXiv:2106.00170. (Eq. (2); Prop. 4.1; §4.2; §7.)
- Xu, C.; Xie, Y. (2021). *ICML*, PMLR 139. arXiv:2010.09107. (§3.1; §4.1.)
- Stankevičiūtė, K.; Alaa, A. M.; van der Schaar, M. (2021). "Conformal time-series forecasting". *NeurIPS 34*. (§3.3; Fig. 1.)
- Gupta, C.; Kuchibhotla, A. K.; Ramdas, A. (2022). *Pattern Recognition*, 127, 108496. DOI: 10.1016/j.patcog.2021.108496. (Table 1.)
- Angelopoulos, A. N.; Bates, S. (2023). *Foundations and Trends in Machine Learning*. DOI: 10.1561/2200000101. (§3.2; App. D.)
- Chernozhukov, V.; Wüthrich, K.; Zhu, Y. (2021). *PNAS*. DOI: 10.1073/pnas.2107794118.
- Stocker, M.; Małgorzewicz, W.; Fontana, M.; Ben Taieb, S. (2025). arXiv:2511.13608 (preprint — context only).
- Full citations, locators and the derivations: [inference domain doc §4, §10.1, §11](../domain/inference/conformal-benchmark-and-feature-attribution.md).
- [ADR 5.1.0002](./5_1_0002-dedicated-calibration-partition.md),
  [ADR 0.0.0010](./0_0_0010-paired-inference-dm-holm-mcs.md),
  [ADR 0.0.0011](./0_0_0011-preregistration-invariants-and-h1-gate.md),
  [ADR 0.0.0052](./0_0_0052-baseline-quantile-emission-conventions.md),
  [ADR 0.0.0054](./0_0_0054-evaluation-domain-doc-scope-and-boundary.md),
  [ADR 6.5.0006](./6_5_0006-scorecard-inputs-gate-from-seed-mean-counts.md),
  [ADR 6.5.0008](./6_5_0008-profiles-declared-in-preregistration-built-where-inputs-exist.md),
  [ADR 0.0.0057](./0_0_0057-inference-domain-doc-scope-and-boundary.md).
- Originating issue: [#150](https://github.com/MarceloSanC/financial-forecasting/issues/150).
