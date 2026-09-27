---
title: ADR 0.0.0010 — Paired inference: DM/HLN per comparator, Holm over the comparators of a horizon, MCS with stationary bootstrap; seeds and folds
description: Architecture Decision Record
when-use: Reference when questioning the paired loss, the Holm family, the DM negative-variance fallback, the MCS bootstrap and block rule, how folds are combined, or how multiple seeds enter the tests
keywords: [adr, diebold-mariano, hln, holm, mcs, bootstrap, block-length, seeds, folds, paired-inference, evaluation, step-6]
status: proposed
created_at: 2026-09-26
updated_at: 2026-09-26
adr_id: 0.0.0010
decision: Paired loss = grid-average pinball per point; one one-sided DM (rectangular lag h−1, HLN, t_{T−1}) per (candidate, comparator, horizon); Holm family = the B comparators of a horizon, independent of the comparators' own H1; MCS with stationary bootstrap and block = max(h, max Politis–White b_sb); folds concatenated; S seeds enter as the pointwise mean of losses; the deterministic GBM enters once.
context_stage: 0.0-global
bounded_context: evaluation
---

# ADR 0.0.0010 — Paired inference (DM/HLN, Holm, MCS)

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`proposed` — flips to `accepted` with the evaluation domain doc (ADR 0.0.0054).

## Context

Overview §11 planned "DM (HAC/HLN, one-sided) + Holm + MCS, lib + oracle".
The domain doc (§6) left five forks — B-FAMILIA, B-DM, B-MCS, B-FOLDS,
B-SEEDS — all class C (convention) and all prior to any confirmatory data.
Closed on 2026-09-26 (doc §10.1).

## Decision

1. **Family (B-FAMILIA, rung 1).** Loss L_t = grid-average pinball; one DM per
   (candidate, comparator, horizon); Holm family = the B comparators within a
   horizon (FWER per horizon, coherent with "never aggregate across
   horizons"). DM per τ is a descriptive profile. A comparator that fails its
   own H1 **stays** in the family and in the MCS set: the H1 gate only decides
   the candidate's eligibility; filtering comparators on an observed result
   would make the family data-dependent (White 2000 §2).
2. **DM variance fallback (B-DM, rung 2).** Rectangular window, lag h−1, HLN
   factor, t_{T−1}; if the long-run variance is ≤ 0 with h > 1, follow the R
   `forecast::dm.test` oracle (warns and recomputes with h = 1) and record the
   occurrence. Bartlett is a sensitivity.
3. **MCS (B-MCS, rungs 2 and 4).** Statistic 'R', α_MCS = 0.10, reps ≥ 1,000;
   stationary bootstrap (the `arch` default); block = max(h, the largest
   Politis–White b̂_sb among the pairwise differentials of the horizon) — the
   most persistent, hence most conservative, floored at h because the MA(h−1)
   dependence of the differential is structural and the roadmap already sets
   block lengths "≥ h". Sensitivities: l = h, l = √T, moving-block (the
   variant used by Hansen, Lunde & Nason 2011). The `arch` default √T is not
   used as the rule because its own docstring asks for a block "chosen to be
   appropriate for the data".
4. **Folds (B-FOLDS, rung 1).** Concatenate the test blocks into one contiguous
   series per horizon (expanding scheme, ADR 5.1.0001), with a preregistered
   stationarity diagnostic of d_t and DM per fold as profile. The rolling-window
   requirement of Giacomini & White (2006) is a declared limitation; Hansen,
   Lunde & Nason report recursive and rolling pseudo-MCS results "very similar".
5. **Seeds (B-SEEDS, rung 4).** The candidate's series is the pointwise mean of
   the losses across seeds — conservative versus a prediction ensemble, since
   the pinball is convex (Jensen). Coverage and degeneracy are seed means; the
   Wilson band's n is the number of non-degenerate aligned points (≈ T), never
   S·T; the H1 gate and its count-based sensitivities use seed-mean counts;
   transition-based backtests (LR_ind, LR_cc) are per seed, in the profile. The GBM is deterministic in the current adapter
   (`deterministic=True`, no bagging, no feature subsampling), so it enters
   once; Stage 5.5 proves it with a "two seeds → identical predictions"
   contract test. The **number** of candidate seeds is a P decision (GPU cost)
   taken when the cohort is frozen (5.5).

## Alternatives considered

- Global Holm family H × B; family per τ; sub-families per baseline tier —
  rejected (mixes horizons / too conservative under strong dependence / needs
  two claims).
- DM 1995's "treat negative variance as 0 and reject" — rejected: breaks
  oracle equivalence (ADR 0.0.0021).
- Automatic bandwidth (Newey–West 1994) — rejected: detaches the lag from the
  preregistered MA(h−1) structure.
- Rolling-window cohort just for inference — rejected: cost, and supersedes
  ADR 5.1.0001.
- Prediction ensemble across seeds; single fixed seed — rejected (changes the
  object / optimistic by Jensen; discards seed variance).

## Consequences

- Positive: every choice has an oracle or a declared rung; sensitivities are
  preregistered, not chosen after the fact.
- Negative: the recursive-scheme limitation stays declared; the MCS block rule
  aggregates C(k,2) block lengths by a convention without primary source.
- Stage 5.5 DoD gains the GBM determinism contract test.

## References

- Diebold & Mariano (1995); Harvey, Leybourne & Newbold (1997); Holm (1979);
  Hansen, Lunde & Nason (2011), read in CREATES RP 2010-76 (note 11 for the
  recursive scheme); Politis & White (2004); White (2000); Giacomini & White
  (2006); Bouthillier et al. (2021).
- R `forecast::dm.test` (`R/DM2.R`); `arch.bootstrap.MCS`,
  `optimal_block_length`.
- Doc: [`probabilistic-forecast-evaluation.md`](../domain/evaluation/probabilistic-forecast-evaluation.md) §6, §10.1.
- Issue [#78](https://github.com/MarceloSanC/financial-forecasting/issues/78).
