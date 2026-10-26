---
title: ADR 8.4.0001 — A production round is its own frozen cohort, derived from a versioned production model that inherits the confirmatory hyperparameters, retrained on one fold over fresh data under its own data root, served without a gold generation
description: Architecture Decision Record
when-use: Reference when asking what a production round is, why its cohort_id changes with the data, why it retrains instead of predicting from the confirmatory checkpoints, why it trains on a single fold, why it publishes no gold, or why the cohort runner accepts hyperparameters swept on another dataset only for production
keywords: [adr, inference, modeling, production-cohort, round, retraining, frozen-hyperparameters, cohort-spec, cohort-hash, single-fold, gold-scope, batch-prediction, freshness]
status: accepted
created_at: 2026-10-25
updated_at: 2026-10-25
adr_id: 8.4.0001
decision: Each run of the production job is a round with its own data root and its own frozen CohortSpec, derived by CohortSpec.production_round(observed dataset fingerprint) from the versioned production model config/cohorts/aapl_production.toml — the confirmatory r0 spec with name aapl_production, geometry n_folds = 1, its own seeds and dataset_start, and no dataset_fingerprint — so the cohort_id (CohortHash of the spec) changes with the data and the API serves a round through the unchanged serve_inference_for; every round retrains the baselines, the GBM and the TFT seeds with the frozen confirmatory hyperparameters and no new sweep; the round publishes no gold, so the API serves the native grid with the conformal and explainability blocks unavailable; the training reuses RunConfirmatoryCohort through a production factory that sets inherited_hyperparameters=True, which drops only the check that the sweeps ran on the cohort's dataset, and takes the environment snapshot over the versioned production model.
context_stage: 8.4-production-cohort-job
bounded_context: inference
---

# ADR 8.4.0001 — Production round: own frozen cohort, retrained, without gold

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 8.4 concept (issue #202), 2026-10-25. The owner delegated
the Stage without stops. Items 1, 4, 5 and the seeds in item 2 are preference
decisions taken by the session with a written reason, **pending ratification
by the owner** (concept 8.4 D1, D2, D3, D7). Item 6 closes by convention (skill
`evidence-resolution`).

## Context

- The inference API (Stage 7.4) serves the persisted `split = "test"` rows of
  one configured cohort and builds `ServeInference` once, at start-up, from
  `SERVING_COHORT_FILE` and `DATA_ROOT` (ADR 7.4.0001 items 1 and 8; concept
  7.4 D8). `serve_inference_for` only needs a frozen `CohortSpec`: it derives
  the `cohort_id` from the `CohortHash` of the spec.
- The confirmatory cohort is frozen. New sessions change the
  `DatasetContentFingerprint` (its hash includes the timestamps), and the
  runner refuses (`DatasetMismatchError`). `check_cohort_declarations` also
  refuses a spec whose `provenance.dataset_fingerprint` differs from its
  `dataset_fingerprint` ("sweeps ran on a different dataset than the one
  declared for the run"), which is I4 of Stage 5.5.
- `GitRuntimeEnvironmentProbe` reads `git rev-parse HEAD:<cohort file>` and
  refuses a cohort file outside the repository.
- The 7.1 prediction port (`CheckpointGridPredictor`) predicts whole partitions
  per fold of a seed and has no mode for dates outside the cohort's grid. ADR
  7.1.0003 rejected re-persisting the test block from checkpoints.
- Cost measured in Stage 5.5: 1.5–2.9 h per TFT seed over 6 folds, baselines
  823 s, GBM 235 s, sweeps ~10 h (runbook `confirmatory-cohort-aapl`, Steps 7
  and 9). Measured in this Stage for one fold at the last cut: see technical
  8.4 §7, `[measurement]`.
- The conformal gold needs a preregistration revision with a `[conformal]`
  block and the `calib` partition written by `infer` (ADRs 6.4.0006, 7.1.0002,
  7.2.0003). The H3 gold needs the ablation cohort (ADRs 7.3.0003, 7.3.0006).

## Decision

1. **A round is a cohort.** `[decision]` P (D1). The production job writes
   each round under `<production-root>/rounds/<round>/`, with its own silver,
   artifacts, ledger and lock. The round's spec is a regular frozen
   `CohortSpec` written to `<round>/cohort.toml`. Its `cohort_id`
   (`aapl_production-r<revision>-<hash12>`) changes whenever the data changes,
   because the dataset fingerprint is part of the hashed payload (ADR
   5.5.0001). The `revision` of the production model changes only when the
   model itself changes. Production rounds have no public anchor (tag + issue
   comment): unlike the confirmatory cohort, they back no claim.
2. **Versioned production model.** `config/cohorts/aapl_production.toml` is
   the confirmatory r0 spec with `name = "aapl_production"`,
   `geometry.n_folds = 1` (same `test_size`, `val_size`, `calib_size`,
   `embargo`), its own `seeds` and `dataset_start = 2010-04-20`, and **without**
   `dataset_fingerprint`. Every other field, including `tft_params`,
   `gbm_params`, `provenance` and the sweep plan, equals r0. A test compares
   them field by field. Without a dataset fingerprint the model is not frozen,
   so the confirmatory `run` refuses it (`CohortNotFrozenError`).
3. **Derivation, never edition.** `CohortSpec.production_round(fingerprint)`
   returns the model with `dataset_fingerprint` set. It refuses a model that
   already has one or that lacks any other freeze field. The job computes the
   fingerprint with the same `load_training_grid` + `grid_fingerprint` the
   `freeze` and the runner use, and refuses to overwrite an existing round
   spec that differs from the derived one.
4. **Retrain on one fold every round, no new sweep.** `[decision]` P (D2). The
   round runs the same units as the confirmatory cohort (five baselines, GBM,
   one TFT unit per seed) with the frozen hyperparameters, on one fold whose
   test block is the last 252 sessions of the grid (the persister drops the
   last `h` decisions, whose target is beyond the panel: 251 at h+1, 245 at
   h+7). One fold suffices because production does not estimate performance;
   it serves the most recent block. The geometry stays the confirmatory one,
   so the distance between the end of training and each served decision
   (547 to 797 sessions with gap = 14) is the one every evaluated fold had:
   the served model is the evaluated configuration in the evaluated lead
   regime. Shrinking `val`/`calib` would make it fresher at the price of a
   regime nobody evaluated; that stays an owner's option. Keeping the
   baselines and the GBM costs minutes and keeps the round spec a complete
   cohort, so `verify` applies unchanged.
5. **No gold.** `[decision]` P (D3). The round runs no `RefreshGold`. The API
   serves the native grid per seed with both gold blocks `unavailable` ("gold
   não publicado"), as ADR 7.4.0001 item 5 already specifies. A later
   production gold would be published inside the round's root before the
   serving pointer switches (ADR 8.4.0002).
6. **Same runner, inheritance declared.**
   `[decision:C] 8.4-RUNNER — how the round trains`
   `Escolha: RunConfirmatoryCohort with a named parameter inherited_hyperparameters (default False), set only by the composition root's production_cohort_for · Alternativas: a parallel production runner over cohort_unit_runner; relaxing the check for every cohort · Degrau (C): 5`
   `Base: run_confirmatory_cohort.py and cohort_unit_runner.py (units, classification, lock, ledger already shared since ADR 7.3.0003 item 3); the only confirmatory rule that does not hold in production is I4's sweep-dataset equality`
   `Sensibilidade pré-registrada: nenhuma · Reversível: sim`
   With `True`, `check_cohort_declarations` skips only the equality between
   the sweeps' fingerprint and the declared one. The observed-equals-declared
   fingerprint, `feature_set_hash`, `pipeline_version`, device, geometry,
   clean tree and resume environment checks stay. The probe takes the
   versioned production model as the cohort file, so its content hash anchors
   the round and an uncommitted change to it is refused.

## Alternatives considered

### Alternative A — Predict new dates from the frozen confirmatory checkpoints
- **Description:** keep the confirmatory models and add a mode that predicts
  dates after the cohort's test from the fold-5 checkpoints, without training.
- **Pros:** no training cost per round; the served model is exactly one the
  study evaluated.
- **Cons:** needs a new prediction mode and port shape in modeling/inference
  (today it predicts whole partitions per fold); the predicted rows would need
  a run identity that no training of the round produced, against recording how
  each served result was produced (Sandve et al. 2013, rule 1; ADR 7.1.0003);
  the model's training window ends at the confirmatory fold-5 cut and ages
  without bound as rounds go by; and the dataset of the new dates still has to
  be materialized.
- **Why rejected:** more new code and a weaker provenance than retraining with
  the existing runner, for a model that grows stale. Retraining on one fold
  costs the measured time in technical §7.

### Alternative B — One growing production cohort under a fixed data root
- **Description:** append each round's sessions to one production cohort that
  the API keeps reading.
- **Pros:** one path, no pointer.
- **Cons:** the `cohort_id` is the hash of the spec and must change with the
  data anyway; appending to the silver the API reads brings back the
  concurrency window of ADR 6.4.0005 for the silver; a failed round would
  leave the served root half-written.
- **Why rejected:** an immutable root per round is simpler and isolates
  failures (ADR 8.4.0002).

### Alternative C — Re-run the sweeps every round
- **Description:** a full `sweep` + `freeze` per round, so the hyperparameters
  match the round's data.
- **Pros:** the confirmatory I4 would hold unchanged.
- **Cons:** ~10 h per round (runbook Step 7); the served model would no longer
  use the hyperparameters the study evaluated.
- **Why rejected:** cost and drift from the evaluated configuration.

### Alternative D — Publish the conformal and H3 gold every round
- **Description:** run `infer` and `RefreshGold` (and the ablation) on each
  round.
- **Pros:** the API would serve intervals and the explainability block.
- **Cons:** needs a production preregistration revision and the ablation
  cohort (days of compute); none of it is required to serve predictions.
- **Why rejected:** out of the v0 need; the 7.4 contract already covers a
  missing gold.

### Alternative E — Do nothing
- The API keeps serving only the confirmatory test dates; the human's B1
  decision in Stage 7.4 asked for a scheduled job.

## Consequences

### Positive
- No change to the API, to `serve_inference_for` or to the cohort file schema.
- Each round has a full provenance: its spec, data fingerprint, ledger,
  environment snapshot and checkpoints live under its root.
- The confirmatory guarantees stay the default; production needs an explicit
  factory.

### Negative
- Each round costs the measured retraining time plus the FinBERT
  materialization.
- The served intervals are only the native quantiles; no conformal interval
  and no explainability in production.

### Neutral / trade-offs accepted
- The production model can drift from r0 only by a deliberate edit, caught by
  the field-by-field test.

## Implementation notes

- `CohortSpec.production_round` in `modeling/application/dtos/cohort_spec.py`.
- `inherited_hyperparameters` in `cohort_unit_runner.check_cohort_declarations`
  and `RunConfirmatoryCohort.__init__`; factory `production_cohort_for` in the
  composition root.
- The job command and the round layout: ADR 8.4.0002.

## References

- Related ADRs: 5.5.0001, 5.5.0003, 6.4.0005, 6.4.0006, 7.1.0001, 7.1.0002,
  7.1.0003, 7.2.0003, 7.3.0003, 7.3.0006, 7.4.0001, 8.4.0002.
- Sandve, G. K.; Nekrutenko, A.; Taylor, J.; Hovig, E. (2013). "Ten Simple
  Rules for Reproducible Computational Research". PLoS Comput Biol 9(10),
  DOI 10.1371/journal.pcbi.1003285 — Rule 1.
- Huyen, C. (2022). *Designing Machine Learning Systems*. O'Reilly — ch. 7,
  "Batch Prediction Versus Online Prediction".
- Issue #202; concept 8.4 D1–D3, D5, D7.
