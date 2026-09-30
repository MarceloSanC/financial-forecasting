---
title: ADR 6.5.0009 — Values of the AAPL preregistration fixed by the project's conventions or by evidence — Holm α 0.05, one-sided DM with the rectangular record and Bartlett sensitivity, MCS 'R' at α 0.10 with 1,000 stationary-bootstrap reps and block max(h, ⌈max b̂_sb⌉) with l = h and l = ⌈√T⌉ sensitivities, min_violations 2, degeneracy tolerance 1e-12, Wilson 97.5 %/95 %, Monte Carlo draws 999, fixed seeds, horizons (1, 7) with h+30 not evaluated, no exclusions; the degeneracy threshold and the deviation scenarios are the human's (ADR 6.5.0010)
description: Architecture Decision Record
when-use: Reference when filling or reviewing config/preregistration/aapl_confirmatory-r0.toml, or when asking why a preregistered number has the value it has and which values came from the researcher
keywords: [adr, evaluation, preregistration, values, alpha, holm, dm, mcs, reps, seed, block, sqrt-t, min-violations, tolerance, wilson, monte-carlo, exclusions, horizons]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-30
adr_id: 6.5.0009
decision: The AAPL preregistration r0 fixes, as convention or evidence, dm_alpha 0.05, DM one-sided "candidate lower loss" with estimators (rectangular primary, bartlett sensitivity) and the variance fallback of conv. #14b, MCS statistic R, α 0.10, reps 1,000, schemes (stationary primary, moving_block sensitivity), block max(h, ⌈max b̂_sb⌉) with sensitivities l = h and l = ⌈√T⌉ (integer, T the horizon's common T), mcs_seed 127, band levels (0.975 gate, 0.95 profile), primary pair (0.10, 0.90), min_violations 2, degeneracy tolerance 1e-12 in units of y, Monte Carlo draws 999 with seed 128 at h+1, seed aggregation by mean with the cohort's seeds (TFT 1..10, GBM 0, baselines seedless), realized source = the frozen training-grid fingerprint, window deficits 0 for every model, horizons (1, 7) with 30 declared not evaluated, no exclusion rule and no extra T minimum beyond the band's own applicability; the degeneracy threshold (1 %) and the power deviation scenarios (primary ±5 p.p. + 0.2σ, secondary ±3 p.p. + 0.1σ) are the human's decisions recorded in ADR 6.5.0010, and the content of the optional blinding statement is still the human's to decide.
context_stage: 6.5-preregistration-and-scorecard
bounded_context: evaluation
---

# ADR 6.5.0009 — Conventional and evidence-fixed values of the preregistration

> **Nota (2026-09-30, Stage 6.5 Task 12):** "≤ 5 % false failure" é o alvo nominal do Bonferroni; a taxa exata é ≈ 5 % (0,0506 em n = 1 512) — ver technical 6.5 §7 `[finding]` T-F11. O valor `dm_alpha` = 0,05 não muda.

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — revised on 2026-09-30 after Checkpoint A round 1 (√T rounding,
dm_alpha anchor, horizons, human values moved to ADR 6.5.0010).

## Context

`RefreshParameters` (ADR 6.4.0006) and the scorecard need numbers the domain doc
calls "pré-registráveis" (§4.4, §5.1, §5.3, §6.1, §6.4, §6.5, §7.6, §8.5). The
triage of skill `evidence-resolution`: a value fixed by a ratified convention or
by evidence is E/C and closed here; a threshold with no convention in the field,
whose choice is a point on a risk curve, is P — those were answered by the human
(ADR 6.5.0010). No metric value of the cohort has been seen by anyone (technical
6.4 §7), so no C becomes P by having seen data.

## Decision

| Field | Value | Class · rung | Base |
|---|---|---|---|
| `dm_alpha` (Holm, per horizon) | 0.05 | C · 1 | the significance level the project already fixed for every confirmatory test — the H1 gate's ≤ 5 % false failure (ADR 0.0.0011, Bonferroni 97.5 % per tail), the 3-state LR_uc at 5 % (doc §8.5), α(N+1) at 0.05 (conv. #22); Holm 1979 Thm 1 controls FWER at any chosen α, so the value is a coherence choice, not a result of the method |
| DM direction | `candidate_lower_loss_one_sided` (H1: E[L_cand − L_comp] < 0) | E | doc §6.10, conv. #15 |
| DM estimators | `rectangular` primary (lag h−1, HLN, t_{T−1}), `bartlett` sensitivity | C · 1 | conv. #14 |
| DM variance ≤ 0 with h > 1 | recompute with h = 1, record (`fallback_applied`) | C · 2 | conv. #14b (R `dm.test`) |
| MCS statistic, α | `R`, 0.10 | C · 1 | conv. #16 (HLN 2011 report M̂*₉₀%) |
| `mcs_reps` | 1,000 | C · 3 | HLN 2011 §5.1 (B = 1,000); `MIN_MCS_REPS` |
| MCS schemes | `stationary` primary, `moving_block` sensitivity | C · 1 | conv. #16b |
| Block rule | l = max(h, ⌈max b̂_sb⌉); sensitivities l = h and l = ⌈√T⌉ | C · 1 | conv. #16b; ADR 6.2.0005 (the block is an integer, rounded **up**, so √T is rounded the same way) |
| `mcs_seed` | 127 | C · 5 | arbitrary, fixed before any metric (ADR 6.4.0006 item 3) |
| Band levels | 0.975 (gate), 0.95 (profile) | E | conv. #10 |
| Primary pair | (0.10, 0.90) | E | doc §8.5 (ADR 6.5.0006) |
| `min_violations` | 2 | C · 3 | Christoffersen & Pelletier (2004) §5: "we do not use Monte Carlo samples with zero or one VaR violations" (domain doc §7.6) |
| `degeneracy_tolerance` | 1e-12 (units of y) | C · 5 | item 2 |
| Monte Carlo (h+1 profile) | `draws` 999, `seed` 128 | C · 5 | α(N + 1) integer at α 0.05 (doc §7.6); Dufour's test is exact for any such N |
| Seeds | mean of losses and of counts; TFT 1..10, `gbm_quantile` 0, baselines seedless | E | conv. #19; cohort r0; writers' code (ADR 6.5.0004) |
| Realized source | `target_return` of the training grid with the cohort's fingerprint (full value in the file) | E | ADR 6.4.0009; cohort r0 |
| `window_deficits` | 0 for every model | C · 1 | item 3 |
| Horizons | evaluated (1, 7); 30 declared "not in the cohort" | E | cohort r0; concept 5.5 §1 (human decision); doc §8.1, §8.8 |
| Exclusions | `none` | E | doc §5.3 item 5, conv. #12 |
| T minimum of the gate | none beyond the band's applicability (n̄ > 0); power always reported | C · 5 | item 4 |

1. `[decision:C] 6.5-VALUES — conventional values of the r0 preregistration`
   `Escolha: the table above · Alternativas: dm_alpha 0.10; mcs_reps 10,000; min_violations 5 (the 6.4 test literal); tolerance 0.0 or 1e-9; √T rounded to nearest · Degrau (C): per row`
   `Base: per row`
   `Sensibilidade pré-registrada: those in the table (Bartlett, moving-block, l = h, l = ⌈√T⌉) · Reversível: não depois do hash`
2. **Tolerance.** Degenerate means the grid is a Dirac (doc §5.1); the tolerance
   only absorbs floating-point residue. Point baselines emit one number for every
   level (ADR 0.0.0052), spread exactly 0. For returns of magnitude ~10⁻² the
   float64 spacing is ~10⁻¹⁸ and the float32 spacing (torch's default dtype, which
   the TFT adapter does not override) is ~10⁻⁹–10⁻¹⁰, so two distinct model
   outputs differ by far more than 10⁻¹² while arithmetic residue of equal values
   stays far below it. The hash encodes 1e-12 exactly (ADR 6.5.0001 item 3).
3. **Window deficits.** The cohort trains every model on one grid with encoder
   context across partitions (ADR 5.4.0001, ADR 5.5.0004); the declared deficit of
   every model is 0, written explicitly per model (ADR 6.5.0004 item 1).
4. **T minimum.** With 6 folds × 252 sessions the effective n per horizon is of
   the order of 1,500 non-degenerate points (from the geometry, not measured); the
   declared power is the honest statement of what the gate can detect at the n
   the scorecard measures, so a separate threshold would add a number without
   adding information.

## Alternatives considered

- **`dm_alpha` 0.10:** more permissive than every other confirmatory test of the
  project.
- **`mcs_reps` 10,000:** lower Monte Carlo noise at ~10× cost; HLN use 1,000 and
  the ladder stops at rung 3.
- **`min_violations` 5:** the 6.4 test literal, not a decision; C&P 2004 is the
  source the domain doc cites.
- **Tolerance 0.0 / 1e-9:** 0.0 is brittle to residue in point baselines; 1e-9 is
  close to the float32 spacing of real TFT outputs.
- **√T rounded to nearest:** the block of the primary rule is rounded up
  (ADR 6.2.0005); one rounding rule for every block length.

## Consequences

### Positive

- Every number has a written reason before any metric.

### Negative

- The r0 file cannot be anchored until the human decides whether it carries a
  blinding statement (ADR 6.5.0010).

## References

- Domain doc §4.4, §5.1, §5.3, §6.1, §6.4, §6.5, §6.9, §6.10, §7.6, §8.1, §8.5, §8.8, §10.
- Hansen, P. R.; Lunde, A.; Nason, J. M. (2011), Econometrica 79(2), §5.1.
- Christoffersen, P.; Pelletier, D. (2004), Journal of Financial Econometrics 2(1), §5.
- Holm, S. (1979), Scandinavian Journal of Statistics 6(2).
- Related ADRs: [0.0.0010](./0_0_0010-paired-inference-dm-holm-mcs.md), [0.0.0011](./0_0_0011-preregistration-invariants-and-h1-gate.md), [0.0.0052](./0_0_0052-baseline-quantile-emission-conventions.md), [5.4.0001](./5_4_0001-encoder-context-across-partitions.md), [6.1.0003](./6_1_0003-degeneracy-absolute-spread-tolerance.md), [6.2.0005](./6_2_0005-mcs-block-length-ceiling-integer.md), [6.4.0006](./6_4_0006-refresh-parameters-explicit-no-domain-defaults.md), [6.5.0001](./6_5_0001-preregistration-canonical-toml-hashed-value-object.md), [6.5.0004](./6_5_0004-judging-values-in-preregistration-cohort-by-reference.md), [6.5.0006](./6_5_0006-scorecard-inputs-gate-from-seed-mean-counts.md), [6.5.0010](./6_5_0010-human-decisions-blinding-threshold-deviation-winner.md).
