---
title: ADR 6.4.0007 — Per-series gold reports are persisted for both samples — the model's full series and the horizon's common intersection — per seed, identified by a sample column; the choice and every profile beyond the declared variants are 6.5's
description: Architecture Decision Record
when-use: Reference when reading metrics_by_run or calibration_table and asking which sample a row describes, why there is one row per seed, where the seed averaging of coverage happens, or why a profile (DM per fold/seed/τ, block sensitivities) is not in the gold
keywords: [adr, evaluation, gold, sample, intersection, full-series, seeds, metrics-by-run, calibration-table, scorecard, profile]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-29
adr_id: 6.4.0007
decision: metrics_by_run and calibration_table hold one set of rows per (model, seed, horizon, sample), where sample is model_full (the model × seed series over all its aligned points) or common (the same series cut to the horizon's intersection used by DM and MCS); dm_results and mcs_results exist only on the common sample, with the seed-averaged losses of the 6.2 factory; the declared variants are the two samples, with and without gaps, the DGT partition for h > 1, every band level and every DM variance estimator and MCS scheme passed as parameters; averaging across seeds and the profiles that need other series (DM per fold, per seed, per τ; MCS block sensitivities; partial-degeneracy per pair; width distribution) are not built by 6.4.
context_stage: 6.4-gold-builders-and-quality-gates
bounded_context: evaluation
---

# ADR 6.4.0007 — Both samples, identified

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Concept 6.1 §Fora do escopo left to 6.5 which sample feeds each scorecard
report: the model's whole series or the DM/MCS intersection. The two differ
only by the prefix lost to the candidate's window deficit (domain doc §6.7;
ADR 5.4.0001). Issue #117 (fork C7) asked 6.4 to persist what 6.5 needs to
choose, without choosing.

The domain doc §6.9 (B-SEEDS) splits seeds by statistic: coverage and
degeneracy of the candidate are means across seeds; the H1 gate uses mean
counts with the same n; sequence backtests (LR_ind/LR_cc) are per seed and
go to the profile; DM/MCS use the loss averaged by the 6.2 factory. Concept
6.3 puts the averaging of counts in 6.5. The doc also lists profiles (DM per
fold §6.8, per seed §6.9, per τ §6.4; MCS block sensitivities §6.5;
partial collapse per pair §5.1; the sharpness diagram §4.3) whose inclusion
the preregistration decides.

## Decision

`[decision:C] 6.4-C7 — sample of the per-series reports and scope of variants`
`Escolha: persist both samples per seed with a sample column; only the declared variants; profiles out · Alternativas: common only; model_full only; every profile now · Degrau (C): 1`
`Base: concept 6.1 §Fora do escopo (choice is 6.5's); domain doc §6.9 B-SEEDS (per-seed quantities averaged by the consumer)`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim (gold is rebuilt)`

1. `sample ∈ {model_full, common}` is part of the grain of
   `gold_metrics_by_run` and `gold_calibration_table`; each row also carries
   its `n_points` and first/last `target_timestamp`, so the two samples are
   distinguishable even when they coincide.
2. Rows are per seed (`seed` nullable for deterministic models, S = 1). The
   6.4 computes no mean across seeds of ĉ(τ), counts or degeneracy; 6.5 does
   (B-SEEDS).
3. `gold_dm_results` and `gold_mcs_results` exist only on `common`, built from
   `paired_pinball_losses` (6.2 factory, mean of L_t across seeds).
4. **Declared variants** (what the gate and the primary verdict need, plus
   what the domain doc marks as the sensitivity pair of a persisted
   statistic): both samples; hit sequences with and without gaps; the DGT
   partition for h > 1; one Wilson band per level in `band_levels`; one DM
   family per estimator in `dm_variance_estimators`; one MCS per scheme in
   `mcs_schemes`.
5. **Not built by 6.4** (concept §Fora do escopo; each is a finding candidate
   for 6.5 or 8.3): DM per fold and per seed (needs the per-fold/per-seed
   series), DM per τ (needs per-level losses), MCS block sensitivities l = h
   and l = √T, partial-degeneracy diagnostics per pair, and the distribution
   of interval widths (→ 8.3). Adding one means reusing `SeriesAssembly` and
   the 6.2/6.3 services, not only a builder (ADR 6.4.0001 Consequences).

## Alternatives considered

### Alternative A — Common sample only

- **Why rejected:** would decide for 6.5 that per-model metrics use the
  paired sample, the open question concept 6.1 handed over.

### Alternative B — Full series only

- **Why rejected:** DM/MCS use the common sample; reporting pinball on a
  different sample than the paired test would leave the scorecard unable to
  show them side by side.

### Alternative C — Every profile now

- **Why rejected:** which profiles enter is a preregistration choice (6.5);
  computing them all before it would widen the gold with unused rows and
  inputs that `GoldInputs` does not carry.

## Consequences

### Positive

- 6.5 chooses by filtering, without recomputing, for everything the gate and
  the primary verdict need.

### Negative

- Per-series tables roughly double when the window deficit is non-zero;
  small at pilot scale.
- Profiles kept by the preregistration need work in 6.5 (series + builder).

## References

- Concept 6.1 §Fora do escopo; concept 6.3 (counts averaged in 6.5); domain
  doc §4.3, §5.1, §6.4, §6.5, §6.7, §6.8, §6.9.
- Related ADRs: 5.4.0001, 6.2.0001, 6.3.0004, 6.3.0005, 6.4.0001, 6.4.0003.
