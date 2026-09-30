---
title: ADR 6.5.0006 — The scorecard reads, per horizon, the candidate's per-seed tail counts of the primary 80 % pair on the model_full sample with degenerate rows masked, averages them across seeds and recomputes the Wilson 97.5 % gate, the 3-state LR_uc and the DGT partition from the mean counts; it reads DM (rectangular) and MCS (stationary) as primary and their Bartlett and moving-block variants as profile; the gate's power against each preregistered deviation is computed exactly on the effective n
description: Architecture Decision Record
when-use: Reference when asking which gold rows feed the H1 gate and H2, which sample and variant the scorecard uses, where the seed averaging happens, what the 95 % and 97.5 % Wilson levels are for, how the gate's sensitivities and power are computed, how a location deviation in σ becomes tail rates, or which DM estimator and MCS scheme are primary
keywords: [adr, evaluation, scorecard, h1-gate, wilson, seeds, mean-counts, sample, model-full, common, lr-uc-three-state, dgt, power, binomial, deviation, dm, mcs, primary, profile]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-30
adr_id: 6.5.0006
decision: Per horizon the H1 gate uses the candidate's gold_calibration_table rows of kind lower_tail at τ_l = 0.10 and upper_tail at τ_u = 0.90, sample model_full, includes_degenerate false, no DGT offset; the scorecard averages n_violations, n_observed and degeneracy_rate across the preregistered seeds and applies WilsonBand at 0.975 to each tail with the mean counts (never S·T) and the mean degeneracy rate against the preregistered threshold (1 %, ADR 6.5.0010); the 3-state LR_uc (χ²(2), α 0.05) and, for h > 1, the DGT partition (rows with the same sample and variant, each of the 2h sub-series tails at Wilson level 1 − 0.05/(2h)) are sensitivities from the same kind of mean counts; the 95 % band, the common sample and the comparators' calibration and degeneracy pass/fail are profile; H2 reads gold_dm_results with the rectangular estimator and gold_mcs_results with the stationary scheme as primary, Bartlett and moving-block as profile; the gate's power is the exact probability of failing it under each preregistered TailDeviation (explicit true tail rates; location shifts converted from σ with the normal model of doc §8.5) at n = round(mean n_observed), computed through the conditional-binomial decomposition of the three-cell multinomial.
context_stage: 6.5-preregistration-and-scorecard
bounded_context: evaluation
---

# ADR 6.5.0006 — Scorecard inputs and the gate from seed-mean counts

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — revised on 2026-09-30 after Checkpoint A round 1 (P2/P3 values
from ADR 6.5.0010; σ → rate conversion; B6 DGT filter; B11 power algorithm;
profile of comparators' degeneracy; decision-reviewer notes on n̄, T and the
serial-dependence warning).

## Context

ADR 6.4.0007 persists per-seed rows for two samples (`model_full`, `common`),
with and without gaps, the DGT partition for h > 1 and one Wilson band per level;
it leaves to 6.5 the seed averaging and the choice of sample and variant
(issue #127, forks C6 and C8). The domain doc fixes most of the rule:

- §8.5 / conv. #26 (B-GATE-H1): per horizon, candidate only, each tail of the
  primary central pair in the Wilson band at 97.5 % (Bonferroni over two tails)
  and degeneracy rate ≤ threshold; "Par recomendado: 80 % (~50 violações
  esperadas por cauda em T = 500), **não** as caudas τ_1/τ_K (~10 violações)";
  3-state LR_uc and, at h+7, the DGT partition are preregistered sensitivities;
  discordance is reported, not arbitrated; the power table is computed with the
  truth N(μ, σ²) against the quantiles of N(0, 1).
- §4.4 / conv. #10 (B-BANDAS): 95 % for an isolated test (profile), 97.5 % per
  tail in the gate; n = aligned non-degenerate points, with S seeds their mean,
  never S·T.
- §6.9 / conv. #19 (B-SEEDS): the gate and its sensitivities use counts only,
  averaged across seeds, with the same n; transition statistics are per seed,
  profile.
- §5.3 item 2 / ADR 6.3.0004: calibration metrics only on non-degenerate rows —
  the masked variant (`includes_degenerate = false`); the unmasked variant is the
  "sem lacunas" profile. §5.3 item 4: the threshold fails H1 for distributional
  models; comparators stay in the family (§6.4), so their pass/fail is profile.
- §7.4 (B-H7) and DGT 1998 §6: "a test with size bounded by α can be obtained by
  performing h tests, each of size α/h".
- Conv. #14: rectangular kernel is the record, Bartlett sensitivity; conv. #16b:
  stationary bootstrap primary, moving-block sensitivity.
- ADR 6.3.0005: the count kernels (`WilsonBand`, `lr_uc_three_state`,
  `kupiec_pof`) accept real mean counts for exactly this use.

## Decision

`[decision:C] 6.5-C6 — sample and variant of each scorecard input`
`Escolha: gate on model_full, masked variant, full series; DGT sensitivity on the same sample and variant; H2 on the common sample (only one persisted); common and "sem lacunas" as profile · Alternativas: gate on the common sample; gate on the unmasked variant · Degrau (C): 1 (§5.3 item 2 fixes the masked variant) e 4 (model_full has n ≥ common: a narrower band rejects calibration at least as often — the conservative side for a "not rejected" claim)`
`Base: domain doc §4.4, §5.3, §6.7, §8.5; ADR 6.3.0004; ADR 6.4.0007`
`Sensibilidade pré-registrada: gate recomputed on the common sample, shown in the profile · Reversível: sim, até o hash`

`[decision:E] 6.5-C8 — Wilson level of the gate and of the profile`
`Escolha: 97.5 % per tail in the gate, 95 % in the profile · Alternativas: 95 % in the gate`
`Base: domain doc §4.4 and §10 conv. #10 "97,5 % por cauda no gate"; §8.5 Bonferroni over the two tails`
`Sensibilidade pré-registrada: nenhuma · Reversível: não depois do hash`

`[decision:E] 6.5-PAIR — primary central pair of the gate`
`Escolha: (0.10, 0.90) — the 80 % pair of the cohort grid · Alternativas: (0.25, 0.75); (0.02, 0.98)`
`Base: domain doc §8.5 "Par recomendado: 80 % … não as caudas τ_1/τ_K"; §7.3 (power of tail tests with ~10 expected violations)`
`Sensibilidade pré-registrada: nenhuma no gate; every pair in the H1 profile · Reversível: não depois do hash`

`[decision:E] 6.5-POWER — how the gate's power is computed`
`Escolha: exact probability of failing the gate over the three-cell multinomial (lower violation, upper violation, inside) at integer n = round(mean n_observed), computed as Σ_l P(L = l)·P(U ∈ A_u | L = l) with U | L = l ~ Binomial(n − l, p_u/(1 − p_l)); acceptance = both Wilson 97.5 % bands contain their nominal · Alternativas: normal approximation; Monte Carlo; the O(n²) double sum`
`Base: domain doc §8.5 table "cálculo próprio, binomial e multinomial exatas"; the conditional factorization of the multinomial is elementary. Reproduced in-session at n = 500: pass 0.959 (calibrated), 0.160 (0.2σ), 0.004 (0.3σ), 0.420 (75 %), 0.464 (85 %) — the doc's table`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

`[decision:C] 6.5-SIGMA — how a location deviation in σ becomes tail rates`
`Escolha: the TOML stores explicit true tail rates for every scenario; for a location scenario of δσ they are (Φ(−z_{0.9} − δ), 1 − Φ(z_{0.9} − δ)) with the normal model of §8.5, computed with statistics.NormalDist and recomputed by a unit test · Alternativas: store δ and derive the rates in the domain; store only a label · Degrau (C): 1 (doc §8.5 defines the location scenario with the normal truth) e 5`
`Base: domain doc §8.5 ("verdade N(μ, σ²) e previsão com os quantis de N(0, 1)")`
`Sensibilidade pré-registrada: nenhuma · Reversível: não depois do hash`

1. **Gate rows** (per horizon h, candidate): `gold_calibration_table` with
   `kind = lower_tail`, `level_low = τ_l` and `kind = upper_tail`,
   `level_low = τ_u`, `sample = model_full`, `includes_degenerate = false`,
   `dgt_offset = null`, one band level (any — the scorecard reads only
   `n_violations`, `n_observed` and `degeneracy_rate`). The rule of ADR 6.5.0004
   item 5 applies, in its order: a seed absent from or extra in these rows versus
   the plan is a `PreregistrationMismatchError` (checked first); a seed that is
   present but lacks exactly one row for a tail is a `GoldGenerationCorruptError`.
2. **Seed means:** c̄_l, c̄_u, n̄ = arithmetic means over the candidate's seeds;
   the two tails share n̄ (same series); degeneracy = mean of the per-seed
   `degeneracy_rate`. The band's estimate is c̄/n̄ (ratio of means, the input the
   count kernels were built for — ADR 6.3.0005), not the mean of the per-seed
   rates ĉ_s that doc §6.9 words; the two coincide when every seed has the same
   number of non-degenerate points; the mean of rates goes to the profile beside
   it.
3. **Gate:** `WilsonBand.evaluate(horizon=h, count=c̄, n=n̄, nominal=0.10,
   band_level=0.975)` per tail; pass ⇔ both contain the nominal ∧ mean
   degeneracy ≤ threshold. A band "not applicable" (n̄ = 0) fails the gate.
   `H1Result` carries n̄, the horizon's common T (doc §6.7) and the band's
   `serial_dependence_warning` (true for h > 1, doc §4.4).
4. **Sensitivities** (profile, never verdict):
   `lr_uc_three_state(lower_count=c̄_l, upper_count=c̄_u, n=n̄, lower_rate=0.10,
   upper_rate=0.10)` with `chi_square_sf(df=2)` at 0.05; for h > 1, the DGT rows
   (`dgt_offset = k`, `dgt_step = h`, k = 0..h−1, **`sample = model_full`,
   `includes_degenerate = false`**) averaged across seeds, each sub-series tail
   with a Wilson band at level 1 − 0.05/(2h), passing iff all 2h bands contain the
   nominal; the gate recomputed on `common`. Every disagreement with the gate is
   listed.
5. **Power:** `H1GatePower` returns, for each preregistered `TailDeviation`
   (label + true lower and upper violation rates), the probability of failing the
   gate at n = round(n̄), by the conditional decomposition above. The scenarios
   are those of ADR 6.5.0010 (P3): primary ±5 p.p. width (rates 0.125/0.125 and
   0.075/0.075) and 0.2σ location (≈ 0.0692/0.1397); secondary ±3 p.p.
   (0.115/0.115, 0.085/0.085) and 0.1σ (≈ 0.0836/0.1187) — the exact values are
   the TOML's, recomputed by the unit test of 6.5-SIGMA. The integer n versus
   the real n̄ is declared in the report; for h > 1 the report says the power
   assumes independent hits and is optimistic (doc §4.4).
6. **H2 rows:** `gold_dm_results` with `variance_estimator = rectangular` and
   the preregistered candidate, one row per preregistered comparator;
   `rejected` is Holm-adjusted at the preregistered α. `gold_mcs_results` with
   `scheme = stationary`; `included` of the candidate. Bartlett and moving-block
   rows go to the profile, with their disagreements, and so does each DM row's
   `fallback_applied` (conv. #14b).
7. **Comparators' calibration** (profile of H1, doc §6.4): read from their rows
   (S = 1), both levels, with their mean degeneracy rate and whether it is above
   the same threshold — reported, never filtering the family.

## Alternatives considered

### Alternative A — Gate on the `common` sample

- **Why rejected:** the candidate's calibration would depend on which other models
  have forecasts at a date; fewer points make "not rejected" easier (degree 4);
  kept as sensitivity.

### Alternative B — Recompute the gate from the silver

- **Why rejected:** the gold already holds the counts; recomputing would be a
  second writing of the hit rule (issue #127, reflection 1a).

### Alternative C — Normal-approximation power

- **Why rejected:** the doc's power figures are exact and exact costs little.

## Consequences

### Positive

- The gate is a pure function of persisted counts and the plan; every
  sensitivity uses the same counts, so a disagreement is informative.

### Negative

- The power uses an integer n while the gate uses a real n̄ (at most half a point,
  declared).

## References

- Domain doc §4.4, §5.3, §6.4, §6.7, §6.9, §7.4, §8.5, §10 conv. #10, #14, #14b, #16b, #19, #23, #26.
- Diebold, F. X.; Gunther, T. A.; Tay, A. S. (1998), International Economic Review 39(4), §6.
- Related ADRs: [0.0.0011](./0_0_0011-preregistration-invariants-and-h1-gate.md), [6.3.0004](./6_3_0004-mask-gaps-break-transitions.md), [6.3.0005](./6_3_0005-count-kernels-accept-mean-counts.md), [6.4.0007](./6_4_0007-gold-persists-both-samples-identified.md), [6.5.0004](./6_5_0004-judging-values-in-preregistration-cohort-by-reference.md), [6.5.0010](./6_5_0010-human-decisions-blinding-threshold-deviation-winner.md).
- Issue [#127](https://github.com/MarceloSanC/financial-forecasting/issues/127) (forks C6, C8); Checkpoint A round 1.
