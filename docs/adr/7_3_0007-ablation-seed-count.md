---
title: ADR 7.3.0007 — Ablation cohort seed count S = 10 (matching the confirmatory), frozen in preregistration r3
description: Architecture Decision Record
when-use: Reference when filling the ablation spec's seeds, when asking how many seeds the LOCO ablation uses and why, how long the ablation run takes on the RX 7700 XT, or what the pilot measured for the seed-count decision
keywords: [adr, ablation, loco, seeds, seed-count, cohort-spec, preregistration, r3, pilot, cost, gpu, rocm, statistical-power, inference]
status: accepted
created_at: 2026-10-20
updated_at: 2026-10-20
adr_id: 7.3.0007
decision: The LOCO ablation cohort uses S = 10 seeds (seeds [1..10]), matching the confirmatory cohort, for 5 configurations x 6 folds x 10 = 300 training runs; the choice is the human's (concept D9) with the pilot cost in view, made for statistical power and consistency with the model being explained, and is frozen in the ablation spec hash and in preregistration r3.
context_stage: 7.3-explainability
bounded_context: inference
---

# ADR 7.3.0007 — Ablation cohort seed count S = 10

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 7.3 (issue #186), 2026-10-20, Linux phase L3. The seed count is
the human's decision with the pilot cost in view (concept D9; ADR 7.3.0003 leaves
`seeds` empty until the freeze; the Linux-phase roadmap entry L3 asks it before the
freeze). Decided after the L2 pilot (which ran only once C12 — GPU determinism — was
resolved by ADR 7.3.0004 item 5 and the `[decision] C12` of technical §7).

## Context

- The LOCO ablation (concept §1, H3) retrains the TFT once per
  **(configuration × fold × seed)**: 5 configurations (full + minus each of the four
  feature families) × 6 folds × **S** seeds = **30·S** runs. Averaging over seeds
  reduces the training-noise variance of each family's loss differential `d_{f,t}` and
  tightens its bootstrap interval.
- The **confirmatory cohort** — the model H3 explains — uses
  `seeds = [1, 2, …, 10]` (10 seeds; `config/cohorts/aapl_confirmatory.toml`).
- `S` enters the ablation spec hash (ADR 7.3.0003) and is **frozen in preregistration
  r3** (concept §1, L7). Once anchored it cannot change without reopening the
  preregistration, so under-powering is the costlier error.
- **Pilot (L2, GPU, measured):** `full`, seed 1, fold 5 (the last fold = ceiling):
  wall 182.4 s, 17 epochs (best 8 of max 50), 10.73 s/epoch, on the RX 7700 XT
  (ROCm 7.1, `torch 2.13.0+rocm7.1`). The runs are resumable (`RunAblationCohort`
  ledger). A checkpoint is ~27 MiB (confirmatory measurement).
- Per-`S` cost (estimate with early stopping | ceiling without) and checkpoint disk:

  | S | estimate | ceiling | checkpoints (30·S × ~27 MiB) |
  |---|---|---|---|
  | 3 | ~4.6 h | ~13.4 h | ~2.5 GiB |
  | 5 | ~7.6 h | ~22.4 h | ~4 GiB |
  | **10** | **~15.2 h** | **~44.7 h** | **~8 GiB** |

## Decision

`[decision] 7.3-ABLATION-SEEDS — how many seeds the LOCO ablation uses`
`Escolha: S = 10 (seeds [1..10]), igual ao confirmatório · Alternativas: S = 5; S = 3 · Degrau: congelado na r3 (não é reversível depois da âncora)`
`Sensibilidade pré-registrada: o S é parte do que a r3 congela · Reversível: não (após a âncora da r3)`

1. `AblationCohortSpec.seeds = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]` (the same ten seeds as
   the confirmatory cohort). This yields 5 × 6 × 10 = **300** training runs and
   `rows expected 105560 × 10 = 1 055 600` for `ablation-verify`.
2. Rationale: **statistical power** (ten seeds give the most stable family-importance
   estimates and the tightest intervals of the options measured) and **consistency**
   with the confirmatory model being explained (same seed count, easier to describe and
   compare). Because r3 freezes `S`, the choice favours rigour over the hours saved: the
   pilot's realistic estimate is ~15 h (early stopping observed at epoch 17/50), the run
   is resumable, and the ~8 GiB of checkpoints fit after reclaiming regenerable cache on
   the Linux host (the confirmatory's 60 checkpoints stay read-only on the mounted
   source, not copied into the ext4 root).
3. `S` is written into the frozen ablation spec at the freeze (L4, `ablation-freeze`)
   and copied into `config/preregistration/aapl_confirmatory-r3.toml` `[h3.ablation]`
   (L7), both inside their hashes.

## Alternatives considered

### Alternative A — S = 5
- **Cons:** captures most of the signal (30 samples/configuration) but wider intervals
  than S = 10; a reviewer could question under-powering for small family effects.
- **Why rejected:** halves the cost (~7.6 h, ~4 GiB) but r3 freezes `S`; the extra power
  of ten seeds is worth the resumable extra hours for a one-off preregistered analysis.

### Alternative B — S = 3
- **Cons:** detects only large family effects; under-powered for small ones; wide
  intervals.
- **Why rejected:** the cheapest (~4.6 h, ~2.5 GiB) but not defensible as the frozen
  power of a confirmatory-grade explanation.

### Alternative C — S > 10
- **Why rejected:** no precedent (the confirmatory stops at 10); diminishing returns on
  variance for a cost that grows linearly; out of scope for v0.

## Consequences

### Positive
- Same seed count as the confirmatory → consistent, maximally powered of the measured
  options, defensible in the preregistration.

### Negative
- ~15 h of GPU (resumable) and ~8 GiB of checkpoints — the largest of the options.

### Neutral / trade-offs accepted
- `S` is irreversible after the r3 anchor (L7); this ADR is the record of why 10.

## References

- Related ADRs: [7.3.0003](./7_3_0003-ablation-cohort-spec-by-reference-identity-per-configuration.md),
  [7.3.0004](./7_3_0004-device-per-trainer-instance-torch-build-declared.md),
  [7.3.0005](./7_3_0005-h3-preregistration-r3-details.md).
- Concept: `docs/stages/7.3-explainability/concept.md` (§1 H3, D9, risk row "a ablação
  dura mais que o previsto em GPU").
- Technical §7: `[decision] C12` (2026-10-20) with the pilot cost report.
- Issue: [#186](https://github.com/MarceloSanC/financial-forecasting/issues/186).
