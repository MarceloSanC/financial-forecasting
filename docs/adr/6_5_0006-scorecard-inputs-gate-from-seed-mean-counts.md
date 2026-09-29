---
title: ADR 6.5.0006 — The scorecard reads, per horizon, the candidate's per-seed tail counts of the primary 80 % pair on the model_full sample with degenerate rows masked, averages them across seeds and recomputes the Wilson 97.5 % gate, the 3-state LR_uc and the DGT partition from the mean counts; it reads DM (rectangular) and MCS (stationary) as primary and their Bartlett and moving-block variants as profile; the gate's power is computed exactly on the effective n
description: Architecture Decision Record
when-use: Reference when asking which gold rows feed the H1 gate and H2, which sample and variant the scorecard uses, where the seed averaging happens, what the 95 % and 97.5 % Wilson levels are for, how the gate's sensitivities and power are computed, or which DM estimator and MCS scheme are primary
keywords: [adr, evaluation, scorecard, h1-gate, wilson, seeds, mean-counts, sample, model-full, common, lr-uc-three-state, dgt, power, multinomial, dm, mcs, primary, profile]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-29
adr_id: 6.5.0006
decision: Per horizon the H1 gate uses the candidate's gold_calibration_table rows of kind lower_tail at τ_l = 0.10 and upper_tail at τ_u = 0.90, sample model_full, includes_degenerate false, no DGT offset; the scorecard averages n_violations and n_observed across seeds and applies WilsonBand at 0.975 to each tail with the mean counts (never S·T), plus the seed-mean degeneracy rate against the preregistered threshold; the 3-state LR_uc (χ²(2), α 0.05) and, for h > 1, the DGT partition (each of the 2h sub-series tails at Wilson level 1 − 0.05/(2h)) are sensitivities from the same mean counts; the 95 % band and the common sample are profile; H2 reads gold_dm_results with the rectangular estimator and gold_mcs_results with the stationary scheme as primary, Bartlett and moving-block as profile; the gate's power against the preregistered minimum deviation is the exact multinomial probability of failing the gate at n = round(mean n_observed).
context_stage: 6.5-preregistration-and-scorecard
bounded_context: evaluation
---

# ADR 6.5.0006 — Scorecard inputs and the gate from seed-mean counts

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

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
  discordance is reported, not arbitrated.
- §4.4 / conv. #10 (B-BANDAS): 95 % for an isolated test (profile), 97.5 % per
  tail in the gate; n = aligned non-degenerate points, with S seeds their mean,
  never S·T.
- §6.9 / conv. #19 (B-SEEDS): the gate and its sensitivities use counts only,
  averaged across seeds, with the same n; transition statistics are per seed,
  profile.
- §5.3 item 2 / ADR 6.3.0004: calibration metrics only on non-degenerate rows —
  the masked variant (`includes_degenerate = false`); the variant with the
  degenerate rows included is the "sem lacunas" profile.
- §7.4 (B-H7) and DGT 1998 §6: "a test with size bounded by α can be obtained by
  performing h tests, each of size α/h".
- Conv. #14: rectangular kernel (lag h−1, HLN, t_{T−1}) is the record, Bartlett
  sensitivity; conv. #16b: stationary bootstrap primary, moving-block
  sensitivity.
- ADR 6.3.0005: the count kernels (`WilsonBand`, `lr_uc_three_state`,
  `kupiec_pof`) accept real mean counts for exactly this use.

What the doc leaves open is the **sample** the gate reads and how power is
computed.

## Decision

`[decision:C] 6.5-C6 — sample and variant of each scorecard input`
`Escolha: gate on model_full, masked variant, full series; H2 on the common sample (only one persisted); common and "sem lacunas" as profile · Alternativas: gate on the common sample; gate on the unmasked variant · Degrau (C): 1 (§5.3 item 2 fixes the masked variant) e 4 (model_full has n ≥ common: a narrower band rejects calibration at least as often — the conservative side for a "not rejected" claim)`
`Base: domain doc §4.4, §5.3, §6.7, §8.5; ADR 6.3.0004; ADR 6.4.0007`
`Sensibilidade pré-registrada: gate recomputed on the common sample, shown in the profile · Reversível: sim, até o hash`

`[decision:E] 6.5-C8 — Wilson level of the gate and of the profile`
`Escolha: 97.5 % per tail in the gate, 95 % in the profile · Alternativas: 95 % in the gate · Degrau (C): —`
`Base: domain doc §4.4 and §10 conv. #10 "97,5 % por cauda no gate"; §8.5 Bonferroni over the two tails`
`Sensibilidade pré-registrada: nenhuma · Reversível: não depois do hash`

`[decision:E] 6.5-PAIR — primary central pair of the gate`
`Escolha: (0.10, 0.90) — the 80 % pair of the cohort grid · Alternativas: (0.25, 0.75); (0.02, 0.98) · Degrau (C): —`
`Base: domain doc §8.5 "Par recomendado: 80 % … não as caudas τ_1/τ_K"; §7.3 (power of tail tests with ~10 expected violations)`
`Sensibilidade pré-registrada: nenhuma no gate; every pair in the H1 profile · Reversível: não depois do hash`

`[decision:E] 6.5-POWER — how the gate's power is computed`
`Escolha: exact multinomial over (lower, upper) tail counts at integer n = round(mean n_observed), acceptance = both Wilson 97.5 % bands contain their nominal · Alternativas: normal approximation; Monte Carlo · Degrau (C): —`
`Base: domain doc §8.5 table "cálculo próprio, binomial e multinomial exatas" — the doc's own power figures are exact; the three-cell multinomial is elementary (§10.1 B-GATE-H1)`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

1. **Gate rows** (per horizon h, candidate): `gold_calibration_table` with
   `kind = lower_tail`, `level_low = τ_l` and `kind = upper_tail`,
   `level_low = τ_u`, `sample = model_full`, `includes_degenerate = false`,
   `dgt_offset = null`, one band level (any — the scorecard reads only
   `n_violations` and `n_observed`). For each preregistered seed there must be
   exactly one row per tail, else `GoldGenerationCorruptError`; a seed in the
   gold that the plan does not list is a `PreregistrationMismatchError`
   (ADR 6.5.0004 item 4).
2. **Seed means:** c̄_l, c̄_u, n̄ = arithmetic means over the candidate's seeds;
   the two tails share n̄ (same series). Degeneracy: mean over seeds of the
   `degeneracy_rate` of the same rows. The band's point estimate is therefore
   c̄/n̄ (ratio of means) — the input the count kernels were built for
   (ADR 6.3.0005) — and not the mean of the per-seed rates ĉ_s that doc §6.9
   words; the two coincide when every seed has the same number of
   non-degenerate points and differ only through seed-varying degeneracy, which
   the threshold keeps small. The scorecard reports the mean of rates beside it
   in the profile.
3. **Gate:** `WilsonBand.evaluate(horizon=h, count=c̄, n=n̄, nominal=rate,
   band_level=0.975)` per tail (nominal 0.10 each); pass ⇔ both contain the
   nominal ∧ mean degeneracy ≤ threshold. A band "not applicable" (n̄ = 0) fails
   the gate.
4. **Sensitivities** (profile, never verdict): `lr_uc_three_state(lower_count=c̄_l,
   upper_count=c̄_u, n=n̄, lower_rate=0.10, upper_rate=0.10)` with
   `chi_square_sf(df=2)` at α_gate = 0.05; for h > 1, the DGT rows
   (`dgt_offset = k`, `dgt_step = h`, k = 0..h−1) averaged across seeds, each
   sub-series tail with a Wilson band at level 1 − 0.05/(2h); the sensitivity
   passes iff all 2h bands contain the nominal; the gate recomputed on `common`.
   Every disagreement with the gate is listed. `H1Result` carries n̄, the
   horizon's common T (doc §6.7: "T é reportado por horizonte") and the band's
   `serial_dependence_warning` (true for h > 1, doc §4.4).
5. **Power:** `H1GatePower` (domain service) returns the probability of
   **failing** the gate under each preregistered deviation form (width
   under- and over-coverage; location — the forms and δ are the preregistered
   minimum deviation, concept fork P3) at n = round(n̄). The mean counts are real
   while the power uses an integer n: the rounding is declared in the report.
6. **H2 rows:** `gold_dm_results` with `variance_estimator = rectangular`,
   `candidate` = the preregistered candidate, one row per preregistered
   comparator (else corrupt); `rejected` is Holm-adjusted at the preregistered
   α. `gold_mcs_results` with `scheme = stationary`; `included` of the
   candidate. Bartlett and moving-block rows go to the profile, with their
   disagreements listed.
7. **Comparators' calibration** (profile of H1, doc §6.4): read directly from
   their rows (S = 1), both levels.

## Alternatives considered

### Alternative A — Gate on the `common` sample

- **Pros:** the same points as DM/MCS.
- **Cons:** the candidate's calibration would depend on which other models have
  forecasts at a date; fewer points (a wider band) make "not rejected" easier.
- **Why rejected:** degree 4; kept as sensitivity.

### Alternative B — Recompute the gate from the silver

- **Why rejected:** the gold already holds the counts; recomputing would be a
  second writing of the hit rule (issue #127, reflection 1a).

### Alternative C — Normal-approximation power

- **Why rejected:** the doc's power figures are exact; with ~150 expected
  violations per tail the approximation is close, but exact costs little and
  matches the doc's table.

## Consequences

### Positive

- The gate is a pure function of persisted counts and the plan; every
  sensitivity uses the same counts, so a disagreement is informative.

### Negative

- The power uses an integer n while the gate uses a real n̄; the difference is at
  most half a point and is declared.

## References

- Domain doc §4.4, §5.3, §6.9, §7.4, §8.5, §10 conv. #10, #14, #16b, #19, #23, #26.
- Diebold, F. X.; Gunther, T. A.; Tay, A. S. (1998), International Economic Review 39(4), §6.
- Related ADRs: [0.0.0011](./0_0_0011-preregistration-invariants-and-h1-gate.md), [6.3.0004](./6_3_0004-mask-gaps-break-transitions.md), [6.3.0005](./6_3_0005-count-kernels-accept-mean-counts.md), [6.4.0007](./6_4_0007-gold-persists-both-samples-identified.md).
- Issue [#127](https://github.com/MarceloSanC/financial-forecasting/issues/127) (forks C6, C8).
