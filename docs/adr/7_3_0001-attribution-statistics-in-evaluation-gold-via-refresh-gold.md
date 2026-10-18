---
title: ADR 7.3.0001 — Family-attribution statistics in the evaluation domain, H3 gold built by RefreshGold from the r3 [h3] block
description: Architecture Decision Record
when-use: Reference when asking where the permutation importance, the LOCO ablation, the paired block bootstrap, the H3 reading rule and the VSN summary are computed, why they are not in the inference domain as the roadmap first said, how RefreshGold reads the ablation cohort, or what the H3 gold tables hold
keywords: [adr, h3, feature-attribution, permutation-importance, loco, ablation, block-bootstrap, basic-interval, contribution-agreement, vsn, evaluation, refresh-gold, gold-tables, roadmap-correction]
status: accepted
created_at: 2026-10-18
updated_at: 2026-10-18
adr_id: 7.3.0001
decision: The H3 computation (loss differentials per family and horizon, shares, paired stationary block bootstrap, basic intervals, sign-agreement reading and VSN summary) lives in the evaluation domain, reusing PinballScore, the SeriesAssembly rule functions, block_length_rule and the McsBackend; RefreshGold builds it in the same generation when the plan carries an [h3] block, reading the confirmatory cohort's permuted predictions and VSN weights and the ablation cohort's partition, and publishes four H3 gold tables that neither the evidence mapper, the verdict nor the ScorecardProfile reads; the roadmap's inference-domain file list for 7.3 is corrected.
context_stage: 7.3-explainability
bounded_context: inference
---

# ADR 7.3.0001 — Attribution statistics in evaluation, gold via RefreshGold

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 7.3 concept (issue #186), 2026-10-18. Item 2 of the
research findings of the issue ("where the computation lives").

## Context

The roadmap block of 7.3 lists `PermutationImportance`, `AblationAnalysis` and
`ContributionAgreement` under `features/inference/domain/services/`, and
`PinballScore` (6.1) among the consumed contracts. Every quantity of H3 is a
statistic of predictions against the realized return (inference domain doc
§5.4–§5.7):

- d_{f,t}(h) = L_t^{perm f}(h) − L_t(h) and L_t^{−f}(h) − L_t^{full}(h), with L_t
  the grid-average pinball of the rearranged vector (evaluation §2.4) — the
  function `PinballScore.per_point_losses` owns it;
- the paired stationary block bootstrap, with the block rule of the MCS
  (`block_length_rule`, ADR 6.2.0005) and the indices of the `McsBackend`
  (ADR 6.2.0004) — both in evaluation;
- the realized series, read once by `RefreshGold` from the modeling training
  grid (ADR 6.4.0009);
- the alignment rules of silver rows (horizon = target index − decision index,
  no duplicates, complete levels), owned by `series_assembly.py` and made public
  functions by Stage 7.2 (ADR 7.2.0003 item 4).

`inference` and `evaluation` are independent slices: behavior crosses only
through a consumer-owned port, data through declared edges (ADR 0.0.0053). An
inference-domain service cannot call `PinballScore` nor the MCS block rule
without a behavioral import that `bc-independence` forbids, so it would need a
second pinball and a second block rule. ROADMAP-3: "o BC `evaluation` força
cada métrica/teste a ser serviço de domínio sobre value object". Stage 7.2 drew
the same line for conformal: the calibrator (a transformation of the grid)
stays in inference, the coverage (a metric) is in evaluation, and the gold comes
from `RefreshGold` (ADRs 7.2.0003, 7.2.0004).

The ablation cohort is a separate cohort partition (`parent_sweep_id` = its own
`cohort_id`, ADR 7.3.0003), while `RefreshGold` today reads one partition.

## Decision

`[decision:C] 7.3-WHERE — where the H3 statistics live`
`Escolha: evaluation domain + RefreshGold, four gold tables · Alternativas: inference domain (roadmap text); a separate H3 job; computing on demand in 8.1 · Degrau: 1 (ADR 0.0.0053, ADR 6.4.0009, ADR 7.2.0003/7.2.0004, ROADMAP-3; one definition of pinball and of the block rule)`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim até a primeira geração real (8.1); depois, as tabelas são formato persistido`

1. **Domain (evaluation, stdlib).**
   - `AttributionAssembly` builds, per method, a `FamilyLossDifferentials`
     value object: for each family f ∈ {price, technical, sentiment,
     fundamental} and horizon h ∈ {1, 7}, the series d_{f,t}(h) over the
     **decision points present in both horizons** (pairing key, ADR 7.3.0005),
     already averaged over seeds (pointwise) and, for permutation, over the K_p
     permutations. It reuses `PinballScore.per_point_losses` over
     `CoverageSeries` built directly from the persisted values (never
     `from_raw`), and the public rule functions of `series_assembly.py`; a
     violation becomes an `undefined` method with its reason, never an
     `AlignmentFinding` (H3 is outside the H1→H2 verdict path).
   - `FamilyContribution` computes I_f(h) = mean_t d_{f,t}(h), s_f(h) =
     I_f(h) / Σ_g I_g(h), Δ_f = s_f(7) − s_f(1), the bootstrap replicas of Δ_f
     over one `BootstrapIndices`, and the basic interval at level
     1 − α/|families| (ADR 7.3.0005), with the non-positive-total rule.
   - `ContributionAgreement` applies the reading rule (ADR 0.0.0007 item 6;
     ADR 7.3.0005): heterogeneous per method; H3 sustained when, for at least
     one family, both intervals exclude 0 (strictly) on the side of the sign of
     Δ̂_f and both Δ̂_f have the same sign (ADR 7.3.0005 H3-READ).
   - `VsnSummary` aggregates the encoder VSN weights (inference domain doc §5.3).
2. **Bootstrap plan, one for everything.** The block is
   `block_length_rule(horizon=max(horizons), max_estimate=max b̂)` with b̂ the
   `McsBackend.optimal_block_length` of each of the 16 series (2 methods × 4
   families × 2 horizons); one `McsBackend.bootstrap_indices(n_obs=T, block,
   reps, seed, scheme=stationary)` call serves both methods, all families and
   both horizons. An `ArithmeticError` from the backend, or a series that fails
   `validate_block_length_request`, makes the H3 reading `undefined` with the
   reason — never a number.
3. **`RefreshGold`.** With an `[h3]` block in the plan (r3, ADR 7.3.0005),
   after the horizon reports and only when the generation is not BLOCKED:
   reads `fact_permuted_predictions` and `fact_vsn_weights` of the candidate's
   runs and `dim_run` + test rows of `fact_oos_predictions` of the ablation
   cohort partition named in the block (asset of the plan, `parent_sweep_id` =
   the ablation `cohort_id`); runs the steps of items 1–2; maps everything to
   evaluation-owned records in `GoldInputs.h3_reports`. Any H3 failure is a
   row with `status = undefined` and a reason and never aborts the refresh nor
   changes another table. `RefreshParameters` gains the required key
   `h3_parameters: H3Parameters | None` (`None` before r3), filled only by
   `refresh_command_from` and compared by `check_manifest`; the manifest also
   lists the ablation `cohort_id` read. Manifests written before this Stage no
   longer read (no real gold exists — the 6.6 D6 rule).
4. **Gold tables** (schema in `gold_schema`, one pure-mapping builder each, in
   `GOLD_SCHEMAS` and `CONFIRMATORY_TABLES`, not `runs_when_blocked`; zero rows
   without `[h3]`):
   - `gold_h3_importance` — per (method, family, horizon, seed or seed mean,
     permutation index or permutation mean): I_f(h), n points (profile rows
     carry the seed / permutation dispersion);
   - `gold_h3_shares` — per (method, family): s_f(1), s_f(7), Δ_f, interval
     bounds, level, side (sign of Δ̂_f), excludes_zero, per-family status and
     reason, count of replicas with Σ* ≤ 0 per horizon (kept as ±∞, ADR
     7.3.0005 H3-NEG); an infinite bound is stored as null with
     `lower_infinite`/`upper_infinite` (7.2 pattern);
   - `gold_h3_reading` — one row: heterogeneous per method, sustained,
     agreeing families, block, b̂ max, reps, seed, T, replicas with Σ* ≤ 0 per
     method and horizon, label
     `"descritiva (sem claim causal)"`, status, reason;
   - `gold_h3_vsn` — per (variable or family): p10, p50, p90, n decisions,
     label `"horizonte-invariante; descreve quanto o modelo usa cada família"`.
   Neither the evidence mapper, the `ScorecardVerdict` nor the
   `ScorecardProfile` reads them: `BuildConfirmatoryScorecard(revision=3)`
   yields the same verdict as revision 2 (tested on synthetic silver).
5. **Roadmap corrected.** The 7.3 block names these files and contracts; the
   inference-domain services and the inference `vsn_weight_extractor.py` leave
   the list (the extractor is ADR 7.3.0002); 8.1 consumes the H3 tables of the
   `RefreshGold` derived from the latest anchored revision.

## Alternatives considered

### Alternative A — Services in the inference domain (roadmap text)
- **Pros:** matches the original file list; the "explainability" Stage keeps
  its statistics in its own BC.
- **Cons:** needs a second pinball, a second block rule and a second bootstrap
  index source (or behavioral imports `bc-independence` forbids); the inference
  domain would also need the realized series, which only evaluation reads.
- **Why rejected:** two definitions of the same statistic (rung 1: ADR 0.0.0053,
  ROADMAP-3, the 7.2 precedent). The roadmap is corrected by this Stage, as the
  7.1 and 7.2 concepts corrected their file lists.

### Alternative B — A separate H3 job/command with its own outputs
- **Why rejected:** a second reader of silver and grid and a second publication
  path; the gold generation and its manifest are the single place where cohort
  results appear (ADR 6.4.0005; same reason as ADR 7.2.0003 Alt. D).

### Alternative C — A separate gold refresh of the ablation cohort, combined later
- **Why rejected:** the reading needs both methods with the same bootstrap
  indices; two generations would need a third step that joins them and two
  manifests to check. One generation that reads two partitions is simpler.

### Alternative D — Do nothing until 8.1
- **Why rejected:** 8.1 is orchestration (roadmap 8.1; ADR 7.2.0003 Alt. E);
  the H3 computation is a 7.3 capability and must be testable on synthetic
  silver before the real run.

## Consequences

### Positive
- One pinball, one block rule, one index generator for H1/H2 and H3.
- H3 is rebuilt from silver + grid + the anchored plan in the same generation
  as everything else; no torch on the refresh path (permuted predictions are
  persisted, ADR 7.3.0002).

### Negative
- `RefreshGold` reads a second cohort partition and two new silver tables; the
  permuted table is ~8.7 M rows for the real cohort (K_p = 10), so the reading
  is done one run at a time — `run_id` is a partition column of both new
  tables (ADR 7.3.0002 item 4), the only filter the Parquet repository pushes
  down — and `AttributionAssembly` and `VsnSummary` consume per-run reductions
  (`PermutedRunLosses`, `AblationRunLosses`, `VsnRunWeights`), never the
  records; the ablation partition of `fact_oos_predictions` (no `run_id` in its
  partitioning) is read once per `year` and reduced per run inside each block; the ablation rows sit in their own `feature_set_name` partition
  (ADR 7.3.0003), so the confirmatory read never loads them (Checkpoint A,
  A-C3 and round 2; memory test with `tracemalloc` in the concept).
- Four gold tables to maintain; old manifests stop reading.

### Neutral / trade-offs accepted
- The Stage tests the whole path on synthetic silver only; the first real
  refresh is 8.1's (blinding).

## References

- Related ADRs: [0.0.0007](./0_0_0007-h3-family-contribution-across-horizons.md),
  [0.0.0053](./0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md),
  [6.2.0004](./6_2_0004-mcs-procedure-in-domain-over-backend-bootstrap-indices.md),
  [6.2.0005](./6_2_0005-mcs-block-length-ceiling-integer.md),
  [6.4.0005](./6_4_0005-gold-full-refresh-per-cohort-partition.md),
  [6.4.0009](./6_4_0009-realized-from-modeling-training-grid-via-consumer-port.md),
  [6.6.0002](./6_6_0002-profile-tables-isolated-from-the-verdict.md),
  7.2.0003 and 7.2.0004 (Stage 7.2, issue #158),
  [7.3.0002](./7_3_0002-permuted-predictions-and-vsn-via-modeling-port-persisted-in-silver.md),
  [7.3.0003](./7_3_0003-ablation-cohort-spec-by-reference-identity-per-configuration.md),
  [7.3.0005](./7_3_0005-h3-preregistration-r3-details.md).
- Inference domain doc §5.4–§5.8, §7.
- Issue: [#186](https://github.com/MarceloSanC/financial-forecasting/issues/186).
