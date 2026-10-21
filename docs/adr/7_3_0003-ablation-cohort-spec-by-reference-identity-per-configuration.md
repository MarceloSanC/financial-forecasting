---
title: ADR 7.3.0003 — Ablation cohort as its own spec referencing the confirmatory cohort by hash, with identity per configuration and the training grid trimmed on the fixed column set
description: Architecture Decision Record
when-use: Reference when writing or reading config/cohorts/aapl_ablation.toml, when asking how the LOCO configurations are named and identified, why their model_version differs, why the grid geometry is identical to the confirmatory one, how the ablation units resume, or what the pilot measures
keywords: [adr, ablation, loco, cohort-spec, cohort-hash, run-id, model-version, feature-set-hash, training-grid, warmup-trim, resumable-units, pilot, modeling]
status: accepted
created_at: 2026-10-18
updated_at: 2026-10-18
adr_id: 7.3.0003
decision: The LOCO ablation is an AblationCohortSpec of its own (config/cohorts/aapl_ablation.toml) that references the confirmatory spec by file, cohort_id and cohort_hash and inherits from it, never copies, the geometry, hyperparameters, horizons, levels, dataset fingerprint and pipeline version; it declares the five configurations (full + minus each family), the frozen family partition, seeds, device and torch build; each configuration trains through the same TrainTft with excluded_family and model_version = tft_quantile_loco_<configuration>, run identity with the subset feature_set_hash, the ablation cohort's own feature_set_name (fs_all_ablation) and the grid trimmed on the full column set; a RunAblationCohort reuses the cohort runner's lock, environment check, ledger and unit classification; a pilot use case measures one configuration × seed × fold without writing silver.
context_stage: 7.3-explainability
bounded_context: inference
---

# ADR 7.3.0003 — Ablation cohort spec by reference, identity per configuration

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 7.3 concept (issue #186), 2026-10-18. Closes items 3 and 5
of the research findings of the issue.

## Context

- P-ABLACAO (human, 2026-10-06; ADR 0.0.0007 item 4): LOCO with retraining,
  N + 1 = 5 configurations, its own frozen and hashed cohort, the full model
  retrained in the same environment, "each configuration uses the candidate's
  frozen training procedure"; device and torch build enter the hash.
- `CohortSpec` (Stage 5.5) carries the sweeps, GBM, baselines and provenance
  and requires all of them to be frozen; its hash is the identity of the
  anchored `aapl_confirmatory-r0-665f45d9169a`. Precedent of an optional field
  absent from the payload: `dataset_start` (#122).
- `TrainTft` reads the whole registry (`load_tft_panel`), uses
  `feature_set_hash()` of the whole registry and `MODEL_VERSION =
  "tft_quantile"` in the `RunId`. The cohort run index and the
  `SeriesAssembly` key series by `(model_version, seed)`
  (`run_confirmatory_cohort.py` `cohort_model_keys`; `series_assembly.py`
  L282): five configurations with the same seed under one `model_version`
  collide.
- `feature_set_hash(specs)` already accepts an alternative mapping
  (`feature_registry.py`); the subset hashes are distinct (measured
  2026-10-18: price 7631c0ae…, technical b75eca48…, sentiment 5f737061…,
  fundamental c58b322f…; full 7df0e1b4…).
- ADR 5.5.0004: one training grid, trimmed on a fixed column set. Trimming on
  the subset's columns would move the first usable session whenever the
  dropped family had the longest warm-up (fundamental YoY: 252), changing the
  fold geometry between configurations.

## Decision

`[decision:C] 7.3-ABL-SPEC — shape and identity of the ablation cohort`
`Escolha: own spec referencing the confirmatory by hash; model_version per configuration; subset feature_set_hash; a feature_set_name of the ablation cohort (`fs_all_ablation`, the same for the 5 configurations); grid trimmed on the full set · Alternativas: CohortSpec + optional ablation block; copy of the confirmatory TOML; one model_version with a configuration column · Degrau: 1 (ADR 6.5.0004 reference by id + hash; ADR 5.5.0004; ADR 5.2.0004 identity slots) e 5`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim até o freeze do cohort de ablação`

1. **`AblationCohortSpec`** (`modeling/application/dtos/ablation_cohort_spec.py`),
   loaded from `config/cohorts/aapl_ablation.toml`: `name`, `revision`,
   `base_cohort_file`, `base_cohort_id`, `base_cohort_hash`, the five
   `configurations` in fixed order (`full`, `minus_price`, `minus_technical`,
   `minus_sentiment`, `minus_fundamental`), each with `excluded_family`,
   `model_version` and the subset `feature_set_hash`; `family_partition`
   (family → feature list, frozen); `seeds` ([P], empty in the draft);
   `device`; `torch_build` (None in the draft; ADR 7.3.0004). The loader reads
   the base file, recomputes its hash and refuses a mismatch with
   `base_cohort_hash`, and refuses a partition or a subset hash different from
   the registry's. Everything else the training needs (geometry,
   `tft_params`, horizons, levels, `dataset_fingerprint`, `pipeline_version`)
   comes **from the base spec**, never from the ablation file. The ablation
   declares its own `feature_set_name = "fs_all_ablation"` (in its hash): the
   ablation rows then live in their own partition of `fact_oos_predictions`
   (partitioned by `feature_set_name`), and the confirmatory refresh's
   `_read_records` (`refresh_gold.py` L370–384, which reads every
   `feature_set_name` of the cohort's runs) never loads them (Checkpoint A
   round 2). `is_frozen()` = seeds non-empty and `torch_build` set. `hash_payload()`
   covers every field; `cohort_id = <name>-r<revision>-<12 hex>` is the
   `parent_sweep_id` of every ablation run.
2. **One training flow.** `TrainTftCommand` gains `excluded_family: str | None
   = None` and `model_version: str = MODEL_VERSION`. With the defaults,
   features, `feature_set_hash`, `config_signature`, `run_id` and every
   persisted value of the confirmatory runs are unchanged (a test pins the
   `run_id` of a confirmatory fold). With `excluded_family = f`: the panel is
   read and trimmed by `build_training_grid` on the **full** column set and only
   then f's columns leave the matrix; the `RunId` slot `feature_set_hash` is
   the subset hash; `model_version = tft_quantile_loco_<configuration>` (the
   full reference is `tft_quantile_loco_full`, distinct from the candidate's
   `tft_quantile`); the command refuses `excluded_family = f` with any other
   `model_version` than `tft_quantile_loco_minus_<f>`, and `excluded_family =
   None` with one outside {`tft_quantile`, `tft_quantile_loco_full`}. The known features (calendar), the past target and the
   relative time index stay in every configuration (C6).
3. **`RunAblationCohort`** (`modeling/application/use_cases/run_ablation_cohort.py`):
   units `tft:<configuration>:seed=<s>`, configurations outer and seeds inner;
   before any training, the base declarations through
   `check_cohort_declarations` (with the base device), the ablation device against the
   **observed** hardware keys of the probe and the torch build against its
   `torch` version (ADR 7.3.0004 item 3), and the geometry fit. The
   lock, the environment snapshot (first run records, resume compares), the
   ledger and the classification of a unit (ledger → reconferred; silver
   complete → `verified_completed`; partial → error) are **extracted** from
   `RunConfirmatoryCohort` into a shared module (both runners import it; the
   confirmatory runner never imports the ablation one), not copied;
   `recorded_run_problems`
   runs over the unit's `(model_version, seed)` keys. CLI subcommands
   `ablation-pilot`, `ablation-run`, `ablation-verify`, `ablation-freeze`.
4. **Pilot** (`MeasureAblationCost`): the `full` configuration (the largest
   input) on the **last fold** (the expanding window gives it the largest
   training set, `walk_forward_splitter.py`), one seed, through the same
   `TftTrainer`; nothing is written to silver or `dim_run`, the predictions
   are discarded unscored. It reports wall time, epochs run, best epoch,
   `seconds_per_epoch`, the frozen `max_epochs`, device and torch build; the
   **ceiling** is `5 · n_folds · S · max_epochs · seconds_per_epoch` (largest
   input, largest training set, every unit running to `max_epochs`); the
   projection from the observed wall time (`5 · n_folds · S · wall_seconds`) is
   labelled **estimate**, not ceiling (Checkpoint A, A-D6). It is the input of
   the human's seed decision (P, reserved).

## Alternatives considered

### Alternative A — `CohortSpec` with an optional `ablation` block (#122 pattern)
- **Pros:** one loader, one runner.
- **Cons:** the ablation file must still carry sweeps, GBM, baselines and
  provenance to be "frozen", i.e. a copy of the confirmatory one that can drift
  (P-ABLACAO requires the same procedure); `is_frozen` and the runner's units
  would branch on the block.
- **Why rejected:** a reference by hash makes "same procedure" structural
  (rung 1, ADR 6.5.0004 pattern) and leaves the confirmatory DTO untouched.

### Alternative B — One `model_version` and a configuration column
- **Cons:** `dim_run`, the cohort run index and the `SeriesAssembly` would all
  need a new key component; schema change of persisted tables.
- **Why rejected:** `model_version` is already a `RunId` slot and the series
  key; a value per configuration costs nothing (rung 5).

### Alternative C — `feature_set_name` per configuration, or the base's
- **Cons (per configuration):** the run index and the refresh query by
  `feature_set_name`, so the runner and the refresh would loop over five
  partitions. **Cons (the base's `fs_all`):** the ablation rows would share
  the confirmatory partition, so every confirmatory refresh (even r2) would
  read ~1 M ablation rows and filter them out.
- **Why rejected:** one name per cohort separates the partitions; the subset
  identity already lives in the `RunId` (`feature_set_hash`) and in
  `config_signature` (`feature_names`).

### Alternative D — Trim the grid on the subset's columns
- **Why rejected:** fold geometry would differ between configurations (ADR
  5.5.0004); the paired comparison L^{−f} − L^{full} needs the same decisions.

### Alternative E — Pilot as a normal run of a draft cohort with one seed
- **Cons:** 6 folds instead of 1 and rows in silver under a draft `cohort_id`.
- **Why rejected:** the human decided "1 seed × 1 fold" (P-ABLACAO).

## Consequences

### Positive
- The confirmatory spec, its hash and its runs are untouched; the ablation
  procedure equals the candidate's by construction.
- The same training code produces the candidate and the five configurations.

### Negative
- A second spec type, loader and runner entry point; the runner's
  classification is extracted into shared functions (refactor with the 5.5
  tests as the net).

### Neutral / trade-offs accepted
- `feature_set_name` tells the cohort apart, not the configuration;
  `model_version` does.

## References

- Related ADRs: [0.0.0007](./0_0_0007-h3-family-contribution-across-horizons.md),
  [5.2.0004](./5_2_0004-canonical-run-identity-via-run-id-and-config-signature.md),
  [5.5.0001](./5_5_0001-frozen-hashed-cohort-spec.md),
  [5.5.0003](./5_5_0003-resumable-cohort-units-atomic-ledger.md),
  [5.5.0004](./5_5_0004-single-training-grid-warmup-trim.md),
  [6.5.0004](./6_5_0004-judging-values-in-preregistration-cohort-by-reference.md),
  [7.3.0004](./7_3_0004-device-per-trainer-instance-torch-build-declared.md).
- Inference domain doc §5.5.
- Issue: [#186](https://github.com/MarceloSanC/financial-forecasting/issues/186).
