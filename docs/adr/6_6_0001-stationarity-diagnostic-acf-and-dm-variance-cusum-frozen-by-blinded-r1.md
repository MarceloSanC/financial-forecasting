---
title: ADR 6.6.0001 — The stationarity diagnostic of the loss differential d_t is the sample ACF up to min(⌊10·log10 T⌋, T−1) lags plus a CUSUM test of a break in the mean scaled by the primary DM long-run variance (rectangular to h−1, same fallback) with a Kolmogorov p-value at α = 0.05; these rules and the other profile rules r0 does not name are frozen by a blinded revision r1 of the preregistration, anchored before 8.1
description: Architecture Decision Record
when-use: Reference when asking what the d_t stationarity profile computes, why its CUSUM uses the DM long-run variance and not statsmodels' breaks_cusumolsresid or a Bartlett/Newey–West variance, where the lag count comes from, or why revision r1 of the preregistration exists
keywords: [adr, evaluation, stationarity, loss-differential, acf, cusum, long-run-variance, kolmogorov, diebold-mariano, assumption-dm, amendment, r1, blinded, preregistration, profile-parameters]
status: accepted
created_at: 2026-10-06
updated_at: 2026-10-06
adr_id: 6.6.0001
decision: For every model pair of the primary paired loss series per horizon, the stationarity diagnostic that B-FOLDS preregisters is (i) the sample autocorrelations of d_t at lags 1..L with L = min(⌊10·log10 T⌋, T−1), (ii) a CUSUM test of a break in the mean — max_k |Σ_{t≤k}(d_t − d̄)| / (T·sqrt(var̂(d̄))) with var̂(d̄) the primary DM long-run variance (rectangular to h−1, recomputed with h = 1 when ≤ 0), extracted from the DM primitive as one public function — with p-value from the Kolmogorov distribution and rejection at 0.05, and (iii) the d_t series itself as plot input; these rules, the descriptive multiplicity of the DM subsets, the pair kinds of the partial degeneracy and the bootstrap scheme of the MCS block sensitivities are named identifiers of a new optional [profile_parameters] block that only revision r1 (blinded amendment of r0) carries; under r0 the profiles that need them are reported as not frozen. This amends ADR 6.5.0008 item 3 ("no amendment needed").
context_stage: 6.6-scorecard-profiles
bounded_context: evaluation
---

# ADR 6.6.0001 — Stationarity diagnostic of d_t; profile rules frozen by a blinded r1

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — revised on 2026-10-06 after Checkpoint A round 1 (variance of the
CUSUM; scope of the r1 block)

## Context

The domain doc preregisters, under B-FOLDS (§6.8), a "diagnóstico de
estacionariedade de d_t" for the DM/MCS that run on concatenated expanding-scheme
folds, citing Diebold (2015, §2.2): "One can plot the loss differential series,
examine its sample autocorrelations and spectrum, test it for unit roots and
other nonstationarities including trend, structural evolution, and structural
breaks." Neither Diebold nor the domain doc fixes the number of lags or a break
test, and revision r0 lists the profile by name only (audit finding F7 of Stage
6.5, issue #129). r0 also names no rule for the multiplicity of the DM subsets,
for which quantile pairs the partial degeneracy reports, nor for the bootstrap
scheme the MCS block sensitivities run on. Computing them with
choices made now, outside the anchored plan, would be a post-registration degree
of freedom.

ADR 6.5.0008 item 3 said the follow-up profiles need "no amendment"; issue #129
criterion 3 said the same. Both predate F7. The human chose (Passo 1b, B1,
2026-10-06) to freeze the missing rules through a blinded amendment, the path
ICH E9 §5.1 supports: the analysis plan "should be finalised before breaking the
blind". ADR 6.5.0002 defines amendments as new revision files with
`blind_status`.

d_t is MA(h−1) by construction at h = 7. `statsmodels.stats.diagnostic.breaks_cusumolsresid`
(v0.15.0) scales the cumulated residuals by `sqrt(sum(resid**2))`, an iid
variance, so its 1.63/1.36/1.22 critical values (Kolmogorov quantiles, "sup abs
of Brownian Bridge" in its source comment) do not hold for d_t. A Bartlett /
Newey–West variance with a bandwidth near h−1 underestimates the long-run
variance of an MA(h−1): with ρ_j = (7−j)/7 at h = 7 it gives 5γ0 against 7γ0,
an actual size near 14 % at nominal 5 % (Checkpoint A, finding D1).

## Decision

`[decision:C] 6.6-ST1 — lags of the ACF of d_t`
`Escolha: L = min(⌊10·log10 T⌋, T − 1) · Alternativas: min(10, T/5) (FPP3 §5.4); h − 1; ⌈√T⌉; ln T · Degrau (C): 2`
`Base: statsmodels@0.15.0 tsa.stattools.acf "if nlags is None: nlags = min(int(10 * np.log10(nobs)), nobs - 1)" (the oracle of the test)`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim (new revision)`

`[decision:C] 6.6-ST2 — break test on d_t`
`Escolha: CUSUM of the mean scaled by the long-run variance, Kolmogorov p-value · Alternativas: iid-scaled OLS-CUSUM (statsmodels breaks_cusumolsresid); Andrews sup-F / Bai–Perron; Giacomini–Rossi fluctuation test · Degrau (C): 4 and 5`
`Base: Diebold 2015 §2.2 (no named test); statsmodels@0.15.0 breaks_cusumolsresid iid scaling (E: excludes the iid version); long-run-variance variant: under weak dependence S_⌊rT⌋/(σ_LR√T) ⇒ Brownian bridge (FCLT; derivation) [SEM-FONTE-PRIMÁRIA]`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

`[decision:C] 6.6-ST3 — long-run variance of the CUSUM`
`Escolha: the primary DM variance — rectangular to h − 1, recomputed with h = 1 when ≤ 0 (one public function shared with the DM) · Alternativas: Bartlett with m = max(h−1, ⌊4(T/100)^{2/9}⌋); Bartlett h − 1 · Degrau (C): 1`
`Base: r0 rules.dm.kernel_lag = "rectangular_lag_h_minus_1" and rules.dm.negative_variance_fallback = "recompute_with_h_1_and_record"; the rectangular window to h − 1 is consistent for the structural MA(h−1) dependence (DM 1995; domain doc §6.1); Bartlett near h−1 under-covers it (Checkpoint A D1)`
`Sensibilidade pré-registrada: nenhuma (horizon_used persisted) · Reversível: sim`

`[decision:C] 6.6-ST4 — α of the break test`
`Escolha: 0.05 (= r0 dm.alpha) · Alternativas: 0.10 (MCS α) · Degrau (C): 1`
`Sensibilidade pré-registrada: nenhuma (p-value persisted) · Reversível: sim`

1. **Scope:** every pair of `PairedLossSeries.model_pairs()` of the common sample
   per horizon (the same seed-mean losses the primary DM and MCS read) — the DM
   pairs and the d_ij the MCS assumes stationary (HLN 2011, Assumption 2).
2. **ACF:** ρ̂_k = Σ_{t=k+1}^{T}(d_t − d̄)(d_{t−k} − d̄) / Σ_t(d_t − d̄)²
   (`adjusted=False`), k = 1..L. Constant d_t → undefined.
3. **CUSUM:** S_k = Σ_{t≤k}(d_t − d̄), k = 1..T; statistic
   B = max_k |S_k| / (T·sqrt(var̂(d̄))), where var̂(d̄) = σ̂²_LR/T is the value of
   `dm_long_run_variance` (the code the DM primitive already runs, made public
   and called by both); p = P(K > B), K the Kolmogorov distribution
   (2Σ_{j≥1}(−1)^{j−1}e^{−2j²B²} for large B, the theta series for small B,
   always in [0, 1]); rejected ⇔ p ≤ 0.05; the break location is the target
   timestamp at argmax |S_k|; `horizon_used` records the fallback.
4. **Persisted:** ACF per lag, the CUSUM row and the d_t series (plot input for
   8.3) — three gold tables (ADR 6.6.0002).
5. **Freezing:** `[profile_parameters]` of `aapl_confirmatory-r1.toml` (`amends`
   = the r0 reference, `blind_status = "blinded"`) carries
   `subset_multiplicity` (ADR 6.6.0003), `partial_degeneracy_pairs` (ADR
   6.6.0002), `mcs_block_sensitivity_scheme` (the MCS block sensitivities run on
   the primary scheme only, one factor at a time around the primary reading —
   domain doc §6.5; HLN 2011 fn. 14) and `[profile_parameters.stationarity]` with `acf_max_lag`,
   `break_test` and `break_alpha`. Each identifier is accepted by the
   `Preregistration` VO only if the domain implements it (`PROFILE_RULE_CATALOG`,
   as `RULE_CATALOG`). The block is optional: r0 has none and its hash is
   unchanged. The block goes to `RefreshParameters.profile_parameters` and the
   manifest, so `check_manifest` compares it; every field of the block is
   required. Under r0 (`None`) the DM subsets, the seed fraction, the MCS block
   sensitivities, the partial degeneracy and this diagnostic are built empty and
   their seven declared profiles are reported "not frozen in this revision"
   (state taken from the plan, never from an empty table); only the Monte Carlo
   p-values, whose values are all in r0, run. The `break_test` identifier fixes
   "CUSUM scaled by the DM variance with the plan's primary estimator", which the
   service receives from `RefreshParameters.dm_variance_estimators[0]`.
6. **Anchor:** r1 is anchored (ADR 6.5.0003) as the last step of Stage 6.6,
   after the test audit.
7. **Never the verdict:** the diagnostic is a profile (doc §8.6); it does not
   gate the DM or the MCS.

## Alternatives considered

### Alternative A — Label the profiles exploratory (no amendment)

- **Why rejected:** contradicts B-FOLDS, which decided the diagnostic is
  preregistered; the human chose the amendment (B1).

### Alternative B — iid-scaled OLS-CUSUM (statsmodels default)

- **Why rejected:** size not controlled under the MA(h−1) dependence of d_t.

### Alternative C — Bartlett / Newey–West long-run variance

- **Why rejected:** with bandwidth near h−1 it shrinks the autocovariances that
  define the MA(h−1) variance; over-rejects at h = 7.

### Alternative D — Giacomini–Rossi fluctuation test

- **Why rejected:** adds a window fraction μ with its own critical-value table;
  tests relative-performance instability, a different question from the premise
  check Diebold describes.

### Alternative E — Sup-F (Andrews) or Bai–Perron multiple breaks

- **Why rejected:** trimming parameter and non-standard critical values; no
  oracle in the pinned dependencies.

## Consequences

### Positive

- The profile rules are protocol-defined before 8.1; the diagnostic checks the
  DM premise with the very variance the DM uses; the oracle (statsmodels `acf`,
  uniform-kernel HAC, `breaks_cusumolsresid` at h = 1, `scipy.stats.kstwobign`)
  is in the existing dev dependencies.

### Negative

- The long-run-variance CUSUM has no primary source in the project; its size is
  asymptotic. It is a descriptive profile, reported with the full ACF.
- 8.1 judges by r1 (chain r0 → r1).

## References

- Diebold (2015), doi:10.1080/07350015.2014.983236, §2.2; domain doc §6.1, §6.2, §6.8, §11.3.
- ICH E9 (1998) §5.1; Ploberger & Krämer (1992), doi:10.2307/2951597 (not accessed).
- statsmodels v0.15.0: `tsa/stattools/_stattools.py` (acf), `stats/sandwich_covariance.py` (S_hac_simple), `stats/diagnostic.py` (breaks_cusumolsresid).
- Related ADRs: [6.5.0002](./6_5_0002-amendment-as-new-revision-file.md), [6.5.0003](./6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md), [6.5.0008](./6_5_0008-profiles-declared-in-preregistration-built-where-inputs-exist.md) (item 3 amended), [6.6.0002](./6_6_0002-profile-tables-isolated-from-the-verdict.md), [6.6.0003](./6_6_0003-dm-subsets-fold-from-run-raw-p-descriptive.md).
- Issue [#129](https://github.com/MarceloSanC/financial-forecasting/issues/129) (criterion 3 superseded by B1).
