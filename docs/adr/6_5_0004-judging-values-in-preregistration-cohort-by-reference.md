---
title: ADR 6.5.0004 — Everything that judges lives in the preregistration — values and named rules, the realized source, the window deficits, the models and seeds — while the cohort is only referenced by id and hash; the refresh command is derived from the preregistration by one function, and the scorecard refuses a gold whose manifest, models, seeds, grid or MCS rule disagree with it
description: Architecture Decision Record
when-use: Reference when asking what the preregistration contains, where a refresh or scorecard parameter comes from (preregistration or cohort spec), why the dataset fingerprint appears in both, how the refresh command is built for the confirmatory run, or what the scorecard checks in the gold before judging
keywords: [adr, evaluation, preregistration, cohort, refresh-parameters, refresh-command, window-deficits, dataset-fingerprint, manifest, consistency, identity, rule-identifier, models, seeds]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-30
adr_id: 6.5.0004
decision: The preregistration carries the asset, the cohort reference (cohort_id and full cohort hash), the realized source (the frozen dataset content fingerprint), the evaluated horizons (and the horizons explicitly not evaluated), the quantile grid, the candidate and the comparators by tier, the seeds of every model, the explicit per-model window deficits, every RefreshParameters value, and an enumerated identifier for every rule the scorecard applies (primary metric and secondary roles, DM direction/kernel/lag/small-sample/fallback, MCS statistic and block rule, exclusions, verdict form, success criterion); a single application function refresh_command_from(preregistration, reference) returns the whole RefreshGoldCommand, whose parent_sweep_id is the referenced cohort_id; a versioned-config test checks asset, cohort id and hash, fingerprint, horizons, grid and seeds against the cohort file; BuildConfirmatoryScorecard reads the partition derived from the plan and raises PreregistrationMismatchError when the manifest (partition, preregistration_ref, parameters, horizons, window_deficits, dataset_fingerprint), the model set of the DM, MCS and calibration rows, the seeds per model, the quantile levels, or the MCS statistic and block size differ from the plan.
context_stage: 6.5-preregistration-and-scorecard
bounded_context: evaluation
---

# ADR 6.5.0004 — What the preregistration holds; cohort by reference; gold checked against it

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — revised on 2026-09-30 after Checkpoint A round 1 (C-A1 rule
identifiers; C-M3/A-M3 model and seed sets; B2 asset; B3 one command builder;
B4 MCS rule; h+30).

## Context

Issue #127 (fork C5) asks whether `window_deficits`, `dataset_fingerprint` and
the MCS parameters come from the preregistration or from the cohort spec. The
domain doc §8.2 gives the criterion: the cohort freezes **what** is trained, the
preregistration freezes **how it is judged**, "two hashes with distinct roles".
§8.1 lists, as preregistration content: grid and horizons (primary and
supplementary), the primary metric and the role of each secondary metric, the H2
family with Holm α, DM direction, kernel, lag (h−1) and variance fallback, the
MCS parameters (α, reps, bootstrap, block rule and sensitivity grid, seed), the
H1 gate rule, seed aggregation and the seed list, the realized source, the
absence of exclusion rules, the minimum-violations rule, the logical form of the
verdict and the study's success criterion, and the reference to the cohort hash.

Facts:

- `RefreshParameters` (ADR 6.4.0006) has no default; `RefreshGoldCommand` also
  takes `asset`, `parent_sweep_id`, `horizons`, `window_deficits` and the
  mandatory `dataset_fingerprint` (ADR 6.4.0009). The cohort's `cohort_id` **is**
  its `parent_sweep_id` (ADR 5.5.0001).
- The cohort spec (`config/cohorts/aapl_confirmatory.toml`) carries
  `asset_id = "AAPL"`, `horizons = [1, 7]`, the grid, the TFT seeds 1..10, the
  GBM params with `seed = 0` and `dataset_fingerprint`; h+30 is outside the
  cohort by the human's decision (concept 5.5 §1). It is a `modeling` DTO read by
  a `modeling` CLI adapter; `evaluation` may not import `modeling` at runtime
  (ADR 0.0.0053, LAYOUT §7).
- The writers record `model_version` = `tft_quantile`, `gbm_quantile`
  (`train_gbm_quantile.py`, `MODEL_VERSION`) and `baseline_<family>` with
  `seed = None` (`run_baselines.py`); the cohort runs the GBM once per fold with
  `gbm_params.seed` (`run_confirmatory_cohort.py`).
- `RefreshParameters` does not carry the seed list, the grid, the MCS statistic
  or the block rule; the gold rows do (`gold_mcs_results.statistic`,
  `block_size`, `max_block_estimate`; `seed` and `level_*` columns).
- `window_deficits` shortens the common sample T when larger: a judging
  tolerance, which chosen after seeing results would be an exclusion rule picked
  post hoc (domain doc §5.3 item 5).

## Decision

`[decision:C] 6.5-C5 — where the refresh and scorecard inputs come from, and what is checked`
`Escolha: every judging value and rule in the preregistration (cohort by id + hash; fingerprint, horizons, grid, seeds copied and checked against the cohort); one command builder; manifest, models, seeds, grid and MCS rule checked by the scorecard · Alternativas: read horizons/fingerprint from the cohort spec at run time; split (MCS in the preregistration, deficits and fingerprint in the cohort); rules only as prose · Degrau (C): 1 (domain doc §8.1 lists them as preregistration content; §8.2 roles of the two hashes)`
`Base: domain doc §8.1, §8.2; ADR 5.5.0001; ADR 6.4.0006; ADR 6.4.0009; ADR 0.0.0053`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim, até o hash`

1. **Content** (blocks of the VO; the names are the TOML keys):
   - `asset`; `cohort.cohort_id`, `cohort.cohort_hash` (full);
     `realized.source = "training_grid_target_return"`,
     `realized.dataset_fingerprint`;
   - `horizons = [1, 7]` and `horizons_not_evaluated` with the reason
     (`30`: "not in the cohort", concept 5.5 §1 — doc §8.1 "primários e
     suplementar", §8.8);
   - `quantile_levels`; `candidate`; `comparators.naive`,
     `comparators.strong_statistical`, `comparators.ml` (the three tiers of
     overview §4; ADR 6.5.0007);
   - `seeds.<model>` for **every** model: the candidate's list; `[0]` for
     `gbm_quantile`; `seedless` for the baselines (recorded as `None` by the
     writers);
   - `window_deficits.<model>` for every model (explicit, no implicit 0);
   - every `RefreshParameters` value (ADR 6.5.0009) and the H1 gate values;
   - `blinding_statement` — optional text (ADR 6.5.0010, P1).
2. **Rule identifiers** (each accepted only if the domain implements it;
   ADR 6.5.0001 item 2):

   | Key | Identifier | Rule it names |
   |---|---|---|
   | `primary_metric` | `mean_pinball_grid` | P̄_G per horizon, scale ρ_τ (doc §3.1, conv. #4, #13) |
   | `secondary_roles` | `profile_only` | CRPS_Q, IS_α, ĉ(τ), PICP/MPIW, LR's, VaR are profile (doc §8.1, §8.6) |
   | `dm.direction` | `candidate_lower_loss_one_sided` | H1: E[L_cand − L_comp] < 0 (doc §6.10, conv. #15) |
   | `dm.kernel_lag` | `rectangular_lag_h_minus_1` | conv. #14 (record); Bartlett as sensitivity estimator |
   | `dm.small_sample` | `hln_student_t_T_minus_1` | conv. #14 |
   | `dm.negative_variance_fallback` | `recompute_with_h_1_and_record` | conv. #14b |
   | `mcs.statistic` | `R` | conv. #16 |
   | `mcs.block_rule` | `max_h_ceil_max_bsb` | conv. #16b, ADR 6.2.0005 |
   | `exclusions` | `none` | doc §5.3 item 5, conv. #12 |
   | `seed_aggregation` | `mean_losses_mean_counts` | conv. #19 |
   | `verdict.form` | `h1_gate_then_h2_tree_v1` | ADR 6.5.0007 |
   | `success_criterion` | `h1_not_rejected_in_at_least_one_horizon` | doc §8.8, conv. #28 |

3. **Derivation:** `refresh_command_from(preregistration, reference) ->
   RefreshGoldCommand` (application, `evaluation/application/dtos/`), the only
   place that maps the plan to the refresh: `asset`, `parent_sweep_id` (the
   referenced `cohort_id`), `horizons`, `window_deficits`,
   `dataset_fingerprint` and `RefreshParameters`. The 8.1 orchestrator calls it;
   the gold can only be built on the partition of the cohort the plan names.
4. **Cohort consistency** is a versioned-config test (it reads the two TOML
   files and hashes the cohort through the cohort's own loader and `CohortHash`
   — the test, not `src/`, crosses to `modeling`; the model names come from the
   writers' constants, also only in the test): the preregistration's `asset`,
   `cohort_id`, `cohort_hash`, `dataset_fingerprint`, `horizons`,
   `quantile_levels`, seeds per model and model set equal the cohort's. The
   production code of `evaluation` never reads the cohort file.
5. **Gold consistency** — `BuildConfirmatoryScorecard` takes no partition: it
   reads the one derived from the plan, and before any verdict raises
   `PreregistrationMismatchError` (naming the field) when:
   - the manifest's `partition`, `preregistration_ref`, `parameters`,
     `horizons`, `window_deficits` or `dataset_fingerprint` differ from
     `refresh_command_from(prereg, ref)`;
   - the set of models in `gold_dm_results` (candidate ∪ comparators), in
     `gold_mcs_results` (M0 = candidate ∪ comparators) or in the candidate's and
     comparators' calibration rows differs, in either direction, from the plan's;
   - the seeds found per model differ, in either direction, from `seeds.<model>`;
   - the quantile levels found differ from `quantile_levels`;
   - a `gold_mcs_results` row has `statistic` ≠ the preregistered one or
     `block_size` ≠ max(h, ⌈`max_block_estimate`⌉) for its horizon (the block
     rule re-applied to the persisted estimate).
   The DM direction, kernel/lag, small-sample correction and fallback are fixed
   by the 6.2 services (only the identified variants exist) and are checked
   through the identifiers of item 2 plus the estimator column.

## Alternatives considered

### Alternative A — Horizons and fingerprint read from the cohort spec at run time

- **Why rejected:** `evaluation` would need a `modeling` DTO; the plan would no
  longer state by itself what it judges. The copy is checked (item 4).

### Alternative B — Window deficits in the cohort spec

- **Why rejected:** the cohort hash of r0 is anchored; adding a field changes it
  (ADR 6.4.0009, Alternatives); a deficit is a judging tolerance.

### Alternative C — A separate `RefreshInputs` DTO with a `to_command()`

- **Why rejected:** a second shape of the same command (Checkpoint A, B3).

### Alternative D — Trust the manifest only

- **Why rejected:** the manifest has no seed list, grid, model set or block rule;
  an extra seed in the silver would silently enter the seed means and the DM
  loss series.

## Consequences

### Positive

- One derivation from plan to refresh; a gold made from another cohort, other
  models, other seeds or other rules cannot be scored against this plan.

### Negative

- Fingerprint, horizons, grid and seeds are written in two files; the test of
  item 4 keeps them equal.

## References

- Domain doc §3.1, §5.3, §6.7, §6.10, §8.1, §8.2, §8.8, §10.
- Related ADRs: [0.0.0053](./0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md), [5.4.0001](./5_4_0001-encoder-context-across-partitions.md), [5.5.0001](./5_5_0001-frozen-hashed-cohort-spec.md), [6.2.0005](./6_2_0005-mcs-block-length-ceiling-integer.md), [6.4.0006](./6_4_0006-refresh-parameters-explicit-no-domain-defaults.md), [6.4.0009](./6_4_0009-realized-from-modeling-training-grid-via-consumer-port.md), [6.5.0001](./6_5_0001-preregistration-canonical-toml-hashed-value-object.md), [6.5.0007](./6_5_0007-verdict-logical-form-and-decision-readiness.md), [6.5.0010](./6_5_0010-human-decisions-blinding-threshold-deviation-winner.md).
- Issue [#127](https://github.com/MarceloSanC/financial-forecasting/issues/127) (fork C5); Checkpoint A round 1.
