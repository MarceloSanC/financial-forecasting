---
title: ADR 6.6.0003 — DM per fold, per seed and per τ run the 6.2 DM on subsets of the primary paired series as descriptive profiles (raw p, rejection at the raw α, no multiplicity correction); the fold of a point is the fold of the run that predicted it, carried by SeriesAssembly and checked across series without blocking; the fraction of rejecting seeds excludes undefined seeds from its denominator
description: Architecture Decision Record
when-use: Reference when asking how DM per fold, per seed or per τ is computed, where the fold label comes from, why the subsets carry no Holm correction, what happens to a fold that is too short, non-contiguous or labelled inconsistently, or how the fraction of rejecting seeds is defined
keywords: [adr, evaluation, diebold-mariano, dm-per-fold, dm-per-seed, dm-per-tau, fold, series-assembly, multiplicity, subsets, b-folds, b-seeds, descriptive-profile]
status: accepted
created_at: 2026-10-06
updated_at: 2026-10-06
adr_id: 6.6.0003
decision: SeriesAssembly carries in HorizonSamples the fold of every common-sample point (the dim_run fold of the run that produced the forecast) when all series agree, and None with the first diverging target when they do not — never an alignment finding, because only the per-fold profile needs it; DmProfiles runs DieboldMariano.compare with the preregistered primary estimator, candidate against each comparator, on (a) each fold window of the primary paired series in temporal order, (b) the paired series with one candidate seed in place of the seed mean, comparators unchanged, and (c) the paired series of the pinball loss at one quantile level; every subset is descriptive — raw p and rejected iff p ≤ α, no correction within or across subsets (rule named in r1); a subset is undefined with its reason when T is too short, a differential is constant, fold labels diverge or a fold is not contiguous; the fraction of rejecting candidate seeds per horizon and comparator is n_rejecting / (n_seeds − n_undefined), null when every seed is undefined.
context_stage: 6.6-scorecard-profiles
bounded_context: evaluation
---

# ADR 6.6.0003 — DM on subsets: fold from the run, descriptive raw p

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — revised on 2026-10-06 after Checkpoint A round 1 (no Holm in the
subsets; fold never blocks; seed-fraction denominator)

## Context

B-FOLDS (domain doc §6.8) concatenates the folds into one series and reports
"DM por fold … como perfil descritivo"; B-SEEDS (§6.9) puts the per-seed DM and
the fraction of seeds rejecting in the profile; §6.4: "DM por nível τ é perfil
descritivo, sem inferência corrigida". ADR 6.4.0001 §Negative notes the
per-fold and per-seed DM need `fold` carried into the samples. The cohort has 6
folds of 252 test points, 10 candidate seeds and a 7-level grid. The DM raises
when a differential is constant after its fallback. Any alignment finding of
`SeriesAssembly` empties the assembled cohort and blocks the refresh — and with
it the verdict.

## Decision

`[decision:E] 6.6-DM2 — origin of the fold label`
`Escolha: the fold of the run that produced the forecast, checked across series without blocking · Alternativas: infer the fold from the target date; cut by decision index; a blocking alignment finding · Degrau (C): —`
`Base: concept 5.1 I7 (contiguous, disjoint test blocks shared by the cohort); domain doc §6.8 (per-fold DM = stability across re-estimations); doc §8.6 (a profile never changes the verdict — so it cannot block it)`

`[decision:C] 6.6-DM1 — multiplicity of the subsets`
`Escolha: raw p and rejection at the raw α; no correction within or across subsets; named in r1 · Alternativas: Holm within each subset; Holm over all subsets of a dimension · Degrau (C): 1`
`Base: domain doc §6.4 "sem inferência corrigida"; §6.8 "perfil descritivo"; ICH E9 §5.6 "an explanation of why adjustment is not thought to be necessary should be set out in the analysis plan"`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim (new revision)`

`[decision:C] 6.6-DM3 — candidate series in the per-seed DM`
`Escolha: seed s of the candidate; comparators as in the primary reading (mean over their seeds) · Alternativas: mean of the other seeds · Degrau (C): 1`
`Base: domain doc §6.9 B-SEEDS`

`[decision:C] 6.6-DM4 — denominator of the seed fraction`
`Escolha: n_rejecting / (n_seeds − n_undefined), n_undefined persisted, null if all undefined · Alternativas: n_rejecting / n_seeds · Degrau (C): 4`
`Base: an undefined seed is not evidence of non-rejection; issue #129 item 2 "fração de seeds que rejeitam a α"`

1. `HorizonSamples.common_folds` — one label per common-sample point when all
   series agree; else `None` with `fold_mismatch_detail`. `fold = None` is a
   label like any other (one fold).
2. Fold subsets are the contiguous windows of the primary `PairedLossSeries`
   (`window`), in temporal order of their first point; a label appearing in two
   separate runs → `fold_not_contiguous`. τ subsets come from
   `paired_pinball_losses(level=τ)`; seed subsets from `paired_pinball_losses`
   with the candidate restricted to one seed.
3. Only `dm.primary_estimator` and `dm.alpha`; one `DieboldMariano.compare` per
   (subset, comparator).
4. Undefined subset reasons: `too_short` (`check_points` fails),
   `constant_differential` (the DM's `is_constant`, after fallback),
   `fold_label_mismatch`, `fold_not_contiguous`, `error` (any other
   `ValueError`/`ArithmeticError`, ADR 6.6.0002 item 3).

## Alternatives considered

### Alternative A — Infer the fold from the target date

- **Why rejected:** a second owner of the fold boundaries outside the montage;
  at h = 7 a target near a boundary would be attributed by date to the next fold
  although the forecast came from the previous model.

### Alternative B — Holm within or across subsets

- **Why rejected:** the subsets are descriptive (§6.4, §6.8); corrected
  inference would invent a claim the plan does not make.

### Alternative C — Fold mismatch as a blocking alignment finding

- **Why rejected:** the primary pairing is by target and does not need the fold;
  blocking would let a profile veto the verdict.

## Consequences

### Positive

- Every subset DM is the 6.2 DM on a slice of the same series; the per-fold view
  uses the folds the models were actually re-estimated on; nothing about folds
  can block the verdict.

### Negative

- Raw p-values over many subsets will show some rejections by chance; they are
  labelled descriptive.

## References

- Domain doc §6.4, §6.8, §6.9, §8.6; ICH E9 (1998) §5.6.
- Related ADRs: [6.2.0001](./6_2_0001-paired-loss-series-single-aligned-matrix-vo.md), [6.4.0001](./6_4_0001-gold-builder-dag-graphlib-declared-dependencies.md), [6.6.0001](./6_6_0001-stationarity-diagnostic-acf-and-dm-variance-cusum-frozen-by-blinded-r1.md), [6.6.0002](./6_6_0002-profile-tables-isolated-from-the-verdict.md).
- Issue [#129](https://github.com/MarceloSanC/financial-forecasting/issues/129).
