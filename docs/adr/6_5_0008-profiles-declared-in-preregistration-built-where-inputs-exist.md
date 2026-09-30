---
title: ADR 6.5.0008 — The preregistration declares every profile with its parameters; Stage 6.5 builds only the profiles readable from the gold plus the seed-mean sensitivities of the gate; profiles that need new series go to a dedicated follow-up issue before 8.1 and the sharpness diagram to 8.3; the scorecard is emitted as a DTO with one serialization and persisted by 8.1
description: Architecture Decision Record
when-use: Reference when asking which profile or sensitivity the 6.5 scorecard shows, why DM per fold, per seed or per τ, the MCS block sensitivities, the partial-degeneracy diagnostic or the Monte Carlo Christoffersen p-value are not in it, where their parameters are frozen, or where the scorecard is written
keywords: [adr, evaluation, scorecard, profile, sensitivity, dm-per-fold, dm-per-seed, dm-per-tau, mcs-block, christoffersen-monte-carlo, partial-degeneracy, sharpness, persistence, last-mile]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-30
adr_id: 6.5.0008
decision: The preregistration lists every profile of the domain doc with its parameters (MCS block sensitivities l = h and l = ⌈√T⌉, Monte Carlo Christoffersen draws and seed, DM per fold, per seed and per τ, stationarity diagnostic of d_t, partial degeneracy per pair, sharpness diagram), so all are protocol analyses; the 6.5 scorecard computes the gate sensitivities from seed-mean counts, the power, and the profile readable from the gold (both Wilson levels, both samples, with/without gaps, all comparators' calibration, per-seed LR_ind/LR_cc and the fraction of seeds rejecting, DM Bartlett, MCS moving-block, DM effect with CI, pinball/CRPS/IS/PICP/MPIW/VaR descriptors); the profiles that need new series (DM per fold/seed/τ, MCS block sensitivities, partial degeneracy per pair, stationarity diagnostic of d_t, Monte Carlo p-values) are a follow-up issue in evaluation to land before 8.1; the sharpness diagram stays in 8.3; the scorecard is a frozen result DTO with a single as_mapping serialization, and its persistence as the gold artifact gold_model_comparison_confirmatory_scorecard is done by 8.1.
context_stage: 6.5-preregistration-and-scorecard
bounded_context: evaluation
---

# ADR 6.5.0008 — Profiles declared now, built where their inputs exist

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — revised on 2026-09-30 after Checkpoint A round 1 (B10 destination
of the scorecard; profile items from C-BAIXA and P4)

## Context

Stage 6.4 forwarded profiles it did not build (concept 6.4 §Fora do escopo;
ADR 6.4.0007 item 5): DM per fold and per seed and the fraction of seeds
rejecting (doc §6.8, §6.9), DM per τ (§6.4), MCS block sensitivities l = h and
l = ⌈√T⌉ (§6.5), partial degeneracy per pair (§5.1), Monte Carlo Christoffersen
p-values (§7.6, `draws` and `seed` preregistered) and the width distribution
(§4.3, 8.3). Each needs series and a builder, not only a builder: the per-fold
and per-seed DM need `fold` carried into the samples and the 6.2 services run
per subset; DM per τ needs per-level losses; block sensitivities need new MCS
runs.

ICH E9 §5.1: only analyses "envisaged in the protocol (including amendments)"
are confirmatory; a profile never changes the verdict (doc §8.6), so **when** it
is computed does not affect the claim, provided **what** it is was declared
before. Stage 6.5 already holds about twelve tasks (concept §12). The roadmap
names a gold artifact `gold_model_comparison_confirmatory_scorecard`; the last
mile rule asks where new outputs are emitted; roadmap 8.1 produces "os artefatos
gold confirmatórios e o veredito".

## Decision

`[decision:C] 6.5-C7 — which profiles enter 6.5 and which go elsewhere`
`Escolha: declare all in the preregistration; build in 6.5 only what the gold holds plus the gate sensitivities and power; new-series profiles → follow-up issue before 8.1; sharpness → 8.3 · Alternativas: build every profile in 6.5; drop the new-series profiles; build them in 8.1 · Degrau (C): 1 (ADR 6.4.0007 "which profiles enter is a preregistration choice"; doc §8.6 profile never changes the verdict) e 5 (smallest Stage that closes the verdict)`
`Base: ICH E9 §5.1 "analyses envisaged in the protocol (including amendments)"; ADR 6.4.0007 item 5; concept 6.4 §Fora do escopo`
`Sensibilidade pré-registrada: — (this decision is about profiles) · Reversível: sim`

`[decision:C] 6.5-EMIT — emission channel of the scorecard`
`Escolha: frozen result DTO with one as_mapping; persisted by 8.1 · Alternativas: sixth gold builder inside RefreshGold; a ScorecardStore port in 6.5 · Degrau (C): 1 (concept 6.4: no adapter-in or persistence "antes da 8.1" when no consumer asks) e 5`
`Base: roadmap §Stage 8.1 description; concept 6.4 §Fora do escopo (CLI); ADR 6.4.0005 (a gold generation is written whole, manifest last — a scorecard appended later would break it)`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

1. **Declared in the preregistration** (with parameters): MCS block
   sensitivities `{h, sqrt_T}` and scheme sensitivity `moving_block`; DM
   Bartlett; Monte Carlo Christoffersen at h+1 (`draws`, `seed`); DM per fold,
   per seed (fraction rejecting at α), per τ; the stationarity diagnostic of
   d_t that B-FOLDS preregisters (ACF, plot, breaks — doc §6.8, Diebold 2015
   §2.2); partial degeneracy per pair; sharpness diagram; the
   with/without-gaps variants.
2. **Built in 6.5** (`ScorecardProfile`): everything in ADR 6.5.0006 items 4, 5
   and 7; per horizon and model the descriptors of `gold_metrics_by_run` (pinball
   per τ and P̄_G, CRPS_Q, IS per pair, ĉ(τ), PICP/MPIW, degeneracy rate,
   guardrail rate) on both samples, the candidate's as seed means with the
   per-seed spread; `gold_calibration_table` at 95 %; per-seed LR_ind/LR_cc and
   the fraction of seeds rejecting; DM Bartlett and MCS moving-block with their
   disagreements with the primary reading; each DM row's `fallback_applied`;
   the comparators' mean degeneracy rate and whether it is above the H1
   threshold (doc §5.3 item 4, reported, never filtering the family); the
   outcome per tier and whether the candidate has the lowest P̄_G
   (ADR 6.5.0007 items 4–5); and, per DM, the **effect with its
   CI** (doc §6.8: "o pré-registro reporta efeito + IC, não só p"): d̄ and the
   95 % interval d̄ ± t_{T−1, 0.975} · (d̄ / statistic), so the interval uses
   exactly the variance and HLN scaling of the reported statistic (undefined
   when the statistic is 0, reported as such).
3. **Follow-up issue** (evaluation, before 8.1; opened by the Stage's master
   session): DM per fold / per seed / per τ, MCS block sensitivities, partial
   degeneracy per pair, the stationarity diagnostic of d_t, Monte Carlo
   p-values — reusing `SeriesAssembly` and the
   6.2/6.3 services, each as new gold tables; their parameters are those of the
   anchored preregistration (no amendment needed to compute them).
4. **8.3:** sharpness diagram and plots.
5. **Emission:** `ScorecardResult` (application result DTO; `ConfirmatoryScorecard`
   is the domain service that builds its verdict) with a single
   `as_mapping()`; 8.1 writes it as `gold_model_comparison_confirmatory_scorecard`
   **outside** the generation directory it read — e.g. under
   `gold/asset=<a>/parent_sweep_id=<p>/scorecard/<preregistration_ref>/`, never
   inside `current/`, which the next refresh swaps out whole (ADR 6.4.0005) —
   recording the manifest it read (roadmap line of 8.1 updated).
6. **Not frozen here:** H3 (feature contribution, ≥ 2 of 3 methods) and the
   conformal benchmark (CQR) are also read by 8.1, but their rules belong to the
   Stages that own them — the CQR variant is deliberated and preregistered by
   7.2 (roadmap "Lacunas conhecidas"; overview §11), H3's reading by 7.3. This
   preregistration covers H1 and H2; the roadmap line of 8.1 records that the
   run needs all of them anchored.

## Alternatives considered

### Alternative A — Build every profile in 6.5

- **Why rejected:** four new series pipelines plus builders would push the Stage
  well past the task ceiling for analyses that cannot change the verdict.

### Alternative B — Drop the new-series profiles

- **Why rejected:** the domain doc calls them preregistered sensitivities
  (B-MCS, B-FOLDS, B-SEEDS, FC6); dropping them is a change of plan.

### Alternative C — Scorecard as a sixth builder of `RefreshGold`

- **Why rejected:** the refresh would have to load and verify the plan and the
  anchor; the gold (evidence) and the verdict (judgment) would stop being
  separable, and a new plan revision would force a new refresh.

## Consequences

### Positive

- 6.5 closes the verdict and every input it needs; the protocol names every
  profile before any metric.

### Negative

- Until the follow-up issue lands, the scorecard's profile is partial; 8.1 must
  not run before it (a dependency to record in the roadmap).

## References

- Domain doc §4.3, §5.1, §6.4, §6.5, §6.8, §6.9, §7.6, §8.6; ICH E9 (1998) §5.1.
- Related ADRs: [6.4.0005](./6_4_0005-gold-full-refresh-per-cohort-partition.md), [6.4.0007](./6_4_0007-gold-persists-both-samples-identified.md), [6.5.0006](./6_5_0006-scorecard-inputs-gate-from-seed-mean-counts.md), [6.5.0007](./6_5_0007-verdict-logical-form-and-decision-readiness.md).
- Issue [#127](https://github.com/MarceloSanC/financial-forecasting/issues/127) (fork C7, scope item 6).
