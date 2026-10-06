---
title: ADR 6.6.0002 — Each new-series profile is its own gold table built in the same RefreshGold generation (DM per fold/seed/τ in one table with a dimension column; partial degeneracy over symmetric and adjacent pairs from the 6.1 gate); a profile unit that fails is undefined and never aborts the refresh; the verdict reads none of the tables and the ScorecardProfile reads all of them; RefreshParameters carry the profile values and rules with no backward-compatible manifest reading
description: Architecture Decision Record
when-use: Reference when asking where a scorecard profile of Stage 6.6 is stored, why DM per fold, seed and τ share a table, which quantile pairs the partial degeneracy reports, why a failing profile does not block the gold, why the verdict is independent of the profile tables, or why pre-6.6 gold manifests no longer read
keywords: [adr, evaluation, gold, profile, gold-schema, builders, dm-profiles, mcs-block, christoffersen-monte-carlo, partial-degeneracy, adjacent-pairs, stationarity, scorecard-profile, i12, refresh-parameters, manifest]
status: accepted
created_at: 2026-10-06
updated_at: 2026-10-06
adr_id: 6.6.0002
decision: Stage 6.6 adds eight confirmatory gold tables, each with its schema in gold_schema and one pure-mapping builder in the RefreshGold DAG (same generation, manifest last) — gold_dm_profiles (fold, seed and τ subsets with a dimension column), gold_dm_seed_fraction, gold_mcs_block_sensitivity, gold_christoffersen_monte_carlo, gold_partial_degeneracy (symmetric pairs from DegeneracyGate.pair_collapse_rates plus adjacent pairs from a new public function of the gate module, called only by the profile), gold_differential_acf, gold_differential_breaks and gold_loss_differentials; every profile unit that cannot be computed becomes an undefined row with its reason (known preconditions tested before the call, a ValueError/ArithmeticError raised by the service or backend call itself as error, counted in RefreshGoldResult.profile_error_units) so no profile aborts the refresh; neither the evidence mapper nor the verdict reads the new tables, the ScorecardProfile reads them and gives each declared profile a state (built, not_frozen_in_revision, not_built_here), and a COMPLETED generation missing one of them is corrupt; RefreshParameters gain monte_carlo_draws/seed, mcs_block_sensitivities and profile_parameters as required manifest keys, so pre-6.6 manifests no longer read.
context_stage: 6.6-scorecard-profiles
bounded_context: evaluation
---

# ADR 6.6.0002 — Profile tables, isolated from the verdict on both sides

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — revised on 2026-10-06 after Checkpoint A round 1 (adjacent pairs;
failure isolation; absent table is corruption; manifest compatibility)

## Context

ADR 6.5.0008 item 3 sends seven profiles to a follow-up "as new gold tables";
the roadmap leaves open whether the subset DMs are one table each or one table
with a dimension column, and whether the 6.5 `ScorecardProfile` reads them or
8.1 attaches them. ADR 6.4.0001 makes builders pure mappings; ADR 6.4.0005
writes a generation whole with the manifest last; ADR 6.5.0005 makes
`gold_schema` the single owner of table names, keys and read columns and treats
a missing table as corruption; ADR 6.4.0006 forbids domain defaults for refresh
parameters. The 6.1 `DegeneracyGate` already returns `pair_collapse_rates` per
symmetric pair among non-degenerate rows, never persisted. The domain doc §5.1
motivates the partial-degeneracy diagnostic with both a symmetric example
(q_0.25 = q_0.75) and adjacent ties ("boosters por nível podem empatar após a
ordenação"); symmetric rates do not determine adjacent ones, and with a
tolerance > 0 inner gaps ≤ tol can add up to more than tol.

All profiles run inside the one `RefreshGold.__call__` that also writes the
verdict's tables: an exception in a profile would abort the generation and so
the verdict (doc §8.6: "o perfil nunca troca o veredito").

## Decision

`[decision:C] 6.6-T1 — layout of the profile tables`
`Escolha: one table per profile grain; fold/seed/τ in one table with a dimension column · Alternativas: one table per subset dimension; extra columns or key in the 6.4 tables · Degrau (C): 1 (ADR 6.5.0005 — tables the verdict reads stay as they are) e 5`
`Base: roadmap §Stage 6.6 point 3; issue #129 item 7; ADR 6.4.0001`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim (before the first confirmatory refresh)`

`[decision:C] 6.6-T2 — pairs of the partial degeneracy`
`Escolha: symmetric (existing pair_collapse_rates) and adjacent pairs (new public function adjacent_collapse_rates of the gate module, outside the verdict path; DegeneracyReport unchanged), same denominator and tolerance · Alternativas: symmetric only; adjacent only · Degrau (C): 1`
`Base: domain doc §5.1 (symmetric example and adjacent motivation; Zamo & Naveau 2018 §3.2.3); degeneracy_gate.py _pair_collapse_rates`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim (new revision)`

`[decision:C] 6.6-T3 — who reads the profile tables`
`Escolha: ScorecardProfile reads them (complete profile in the ScorecardResult) · Alternativas: 8.1 attaches them next to the scorecard · Degrau (C): 1 (roadmap lists scorecard_profile.py to modify; ADR 6.5.0008 item 5, one artifact)`

`[decision:C] 6.6-T4 — failure of a profile unit`
`Escolha: undefined row with reason; never aborts the refresh · Alternativas: propagate (6.4 C7 policy) · Degrau (C): 1 (doc §8.6 — a profile never changes the verdict)`

`[decision:C] 6.6-T5 — manifest compatibility`
`Escolha: new RefreshParameters keys required (profile_parameters may be null); pre-6.6 manifests are corrupt · Alternativas: optional keys with defaults on read · Degrau (C): 1 (ADR 6.4.0006 — no defaults)`
`Base: no confirmatory gold exists to preserve (blinding)`

1. **Tables** (all carry `asset`, `parent_sweep_id`, `preregistration_ref`; none
   runs when blocked; all in `CONFIRMATORY_TABLES`):
   `gold_dm_profiles` (key horizon, dimension, fold, seed, level, comparator),
   `gold_dm_seed_fraction` (horizon, comparator),
   `gold_mcs_block_sensitivity` (horizon, block_rule, model),
   `gold_christoffersen_monte_carlo` (model, seed, horizon, sample, kind,
   level_low, level_high, includes_degenerate),
   `gold_partial_degeneracy` (model, seed, horizon, sample, pair_kind,
   level_low, level_high), `gold_differential_acf` (horizon, model_a, model_b,
   lag), `gold_differential_breaks` (horizon, model_a, model_b),
   `gold_loss_differentials` (horizon, model_a, model_b, target_timestamp).
2. **Computation stays in the domain:** the fraction of rejecting seeds, the
   block lengths h and ⌈√T⌉, the adjacent collapse rates and every statistic
   come from domain reports (`ProfileReports`, the MCS runs of the use case)
   carried in `GoldInputs`; builders only map.
3. **Failure isolation (write side):** `ProfileReports` (and the use case for
   the backend-dependent MCS runs) turns each failing unit — DM subset, MCS run
   per block rule, Monte Carlo sequence, d_t pair, adjacent-degeneracy series —
   into an undefined row: known preconditions tested by name before the call;
   a `ValueError`/`ArithmeticError` raised by the service or backend call itself
   (only the call is inside the capture; report assembly and mapping are not, so
   a contract bug still raises) as `error` with the message. The count goes to
   `RefreshGoldResult.profile_error_units`. The verdict's tables are produced
   identically. `DegeneracyGate.evaluate` (verdict path) is unchanged; the
   adjacent pairs are computed by the profile.
4. **Isolation (read side):** `evidence_from_generation` and
   `ConfirmatoryScorecard.decide` read none of the eight schemas (tested with a
   spy generation and adversarial profile content). `build_profile` reads them
   by schema with typed accessors and states each declared profile `built`,
   `not_frozen_in_revision` (r0 has no rule for it) or `not_built_here`
   (`NOT_BUILT_HERE` = `{"sharpness_diagram"}`, 8.3). A COMPLETED generation
   missing one of the eight tables is corrupt (`GoldGenerationCorruptError`),
   not an omitted profile — a silent omission would hide an unregistered builder.
5. **Parameters:** `RefreshParameters` gain `monte_carlo_draws`,
   `monte_carlo_seed`, `mcs_block_sensitivities` and `profile_parameters`
   (`ProfileParameters | None`), required in `as_mapping`/`from_mapping`;
   `check_manifest` compares them through the whole mapping.

## Alternatives considered

### Alternative A — One table per subset dimension

- **Why rejected:** three tables with identical columns; the dimension column
  keeps one schema.

### Alternative B — Block-rule key in `gold_mcs_results`, MC columns in `gold_calibration_table`

- **Why rejected:** changes tables the verdict reads; the MC exists only at
  h = 1, so half the calibration rows would carry nulls.

### Alternative C — 8.1 attaches the profile tables

- **Why rejected:** two artifacts for one scorecard and a second reader.

### Alternative D — New per-pair degeneracy service

- **Why rejected:** two writers of one rule; the gate is the owner.

### Alternative E — Propagate profile errors

- **Why rejected:** a profile could then block the verdict of the frozen cohort,
  which cannot be probed before 8.1 (blinding).

## Consequences

### Positive

- The verdict is independent of the profiles on the write side (no profile can
  block or alter the generation's verdict tables) and on the read side.

### Negative

- Eight more builders in the DAG; an `error` row can carry a real bug, made
  visible by its message in the profile.
- Gold generations written before Stage 6.6 no longer read.

## References

- Related ADRs: [6.4.0001](./6_4_0001-gold-builder-dag-graphlib-declared-dependencies.md), [6.4.0005](./6_4_0005-gold-full-refresh-per-cohort-partition.md), [6.4.0006](./6_4_0006-refresh-parameters-explicit-no-domain-defaults.md), [6.5.0005](./6_5_0005-gold-generation-reader-port-manifest-first.md), [6.5.0008](./6_5_0008-profiles-declared-in-preregistration-built-where-inputs-exist.md), [6.1.0003](./6_1_0003-degeneracy-absolute-spread-tolerance.md), [6.6.0001](./6_6_0001-stationarity-diagnostic-acf-and-dm-variance-cusum-frozen-by-blinded-r1.md), [6.6.0003](./6_6_0003-dm-subsets-fold-from-run-raw-p-descriptive.md).
- Domain doc §5.1, §8.6. Issue [#129](https://github.com/MarceloSanC/financial-forecasting/issues/129).
