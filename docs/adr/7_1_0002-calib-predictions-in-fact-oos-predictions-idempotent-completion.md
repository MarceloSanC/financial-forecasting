---
title: ADR 7.1.0002 — Calibration-partition predictions are rows of `fact_oos_predictions` with `split = "calib"` under the training run's `run_id`, written by idempotent completion; the cohort run index counts only `split = "test"`
description: Architecture Decision Record
when-use: Reference before persisting any non-test prediction, before changing how the cohort runner counts a run's rows, when a re-run of the inference meets rows that already exist, or when 7.2 asks where the calib predictions live
keywords: [adr, inference, calib, fact-oos-predictions, split, run-id, append-only, idempotency, resume, cohort-run-index, verify, conformal]
status: accepted
created_at: 2026-10-06
updated_at: 2026-10-06
adr_id: 7.1.0002
decision: The candidate's calib predictions are persisted through the existing `PersistPredictions` into `silver.fact_oos_predictions` with `split = "calib"`, the same `run_id` and `model_version = "tft_quantile"` as the fold's training run, raw and guardrailed values on the same row (no DDL); each decision is written only if absent and, if present, its whole row is re-verified (values under the reproduction criterion of ADR 7.1.0003 with the mode set by the environment of the first write, other columns by equality), with the run's manifest entry written ahead of the first calib write and the final count re-read from silver, so re-running is safe and resumes a partial emission; and the `ParquetCohortRunIndex` (cohort `run`/`verify` of 5.5) counts only `split = "test"` rows, so calib rows never change a completed unit's count.
context_stage: 7.1-inference-engine
bounded_context: inference
---

# ADR 7.1.0002 — Calib predictions in `fact_oos_predictions`, idempotent completion

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The CQR of 7.2 needs the candidate's predictions on each fold's `calib` block
(ADR 5.1.0002; domain doc inference §3.4, A4). Today every writer persists only
`split = "test"`. Facts that constrain where and how:

- `fact_oos_predictions` is long and grid-agnostic, PK `(run_id, split, horizon,
  timestamp_utc, target_timestamp_utc, quantile_level)`, append-only, "mais
  linhas, nunca DDL" (ADR 4.1.0002); `split` is a PK column and `PredictionRow`
  already documents labels other than `"test"`. `calib` and `test` sessions are
  disjoint (ADR 5.1.0002), so calib rows of a run never collide with its test
  rows.
- The single owner of `target_timestamp` and of the long-row mapping is
  `PersistPredictions` (ADR 4.3.0001); the guardrail is `QuantileForecast.from_raw`
  (ADR 4.3.0002, reused — domain doc A3).
- `PersistPredictions` writes **one decision per call**, and the Parquet adapter
  rewrites the decision's year partition atomically; a crash between calls
  leaves a prefix of decisions written. Append-only means a partial emission
  cannot be deleted, and re-writing an existing key raises `DuplicateKeyError`.
- Measured on 2026-10-06 (code reading): `ParquetCohortRunIndex.recorded_runs`
  counts **every** fact row of a run and collects every `target_timestamp`; the
  cohort `run` (resume, `CompletedUnitCorruptedError`) and `verify`
  (`recorded_run_problems`: expected row count and identical target sets across
  models) would both turn red as soon as calib rows exist under the training
  `run_id`. The evaluation side is already safe: `SeriesAssembly` keeps only
  `split == "test"`.

## Decision

1. **Where:** `silver.fact_oos_predictions`, `split = "calib"`, through the
   inference's consumer port `PredictionPersister` satisfied by
   `analytics_store.PersistPredictions` (ADR 0.0.0053). `run_id`,
   `model_version`, `asset`, `feature_set_name` and `schema_version` are the
   fold's training run's — the calib rows *are* that run's predictions on another
   partition. `value_raw` and `value_guardrail` go on the same row, as for test.
2. **Idempotent completion, per decision, with write-ahead provenance:** before
   the first calib write of a run, its manifest entry is written with status
   `started`, the checkpoint sha256 and the current environment as first-write
   fields (ADR 7.1.0004 item 4). The use case reads the run's existing calib
   rows; for each calib decision, rows present → the **whole row** is compared
   with the new one: `value_raw` and `value_guardrail` under the criterion of ADR
   7.1.0003, with the mode chosen against the environment in which **those rows**
   were first written (manifest); `guardrail_applied` by equality only in
   `strict` (in `tolerance` two nearly tied quantiles may cross or not within
   the tolerance, and `value_guardrail` under tolerance already bounds the
   effect); `model_version`, `asset`, `feature_set_name`, `schema_version`,
   `timestamp_utc`, `target_timestamp_utc` always by equality (mismatch raises,
   nothing is written);
   rows absent → written. Calib rows present with no manifest entry for the run
   → `CalibProvenanceMissingError` (fail closed). A decision is all-or-nothing
   (one `PersistPredictions` call = one atomic partition write). Re-running a
   completed inference writes zero rows and re-proves equality; re-running
   after a crash completes the missing decisions and keeps the first-write
   environment. A `started` entry is resumed **only** if the current non-code
   environment equals its first-write environment; otherwise
   `InferenceEnvironmentError`, telling the operator to resume in the original
   environment — so every row of a run is born in the one environment the
   manifest records.
3. **Completeness, by re-reading:** after a run, the silver is re-read and calib
   rows present = `calib_size × |horizons| × |quantile_levels|` (the calib block
   is always followed by embargo and test, so the emission rule I16 never
   truncates it); otherwise `IncompleteCalibError` and the entry stays
   `started`; on success it becomes `completed`.
4. **Cohort index counts only test rows.** `ParquetCohortRunIndex` filters
   `split == "test"` before counting rows and collecting target timestamps; the
   `CohortRunIndex` port doc states "linhas de teste"; the fake
   `InMemoryCohortRunIndex` takes a `split` and discards non-test entries, so the
   `[fake, real]` suite covers the rule. Completed units keep their recorded
   counts; the 5.5 `verify` stays green after the inference. (A 5.5 `run` already
   refuses to resume after any commit to `src/` because `code.src` differs; the
   `verify` is what depends on this filter.)
5. **Order inside a run:** the test reproduction (ADR 7.1.0003) is checked
   **before** any calib row of that run is written — calib is only emitted from
   an artifact whose test prediction reproduces.

## Alternatives considered

### Alternative A — New silver table for calib predictions
- **Pros:** zero interaction with the cohort index.
- **Cons:** a second definition of the same long row (schema, PK, owner of
  `target_timestamp`), DDL that ADR 4.1.0002 avoided by design, and 7.2 would
  read two tables for one object.
- **Why rejected:** the long table already has `split` in the PK for this.

### Alternative B — A new `run_id` for the inference run
- **Pros:** calib rows separable by identity.
- **Cons:** needs a `dim_run` row per inference run and an identity scheme for
  "inference of run X" (a new slot or a hand-rolled hash — forbidden by LAYOUT
  §7 / ADR 5.2.0004); 7.2 would have to join two identities to pair calib with
  test of the same model.
- **Why rejected:** the predictions come from the same artifact; one identity is
  the truthful one.

### Alternative C — Fail on any existing calib row (no completion)
- **Pros:** simplest write path.
- **Cons:** after a crash the run is stuck forever (append-only, no delete);
  remediation would be a new cohort revision — retraining 60 models to recover a
  prediction pass.
- **Why rejected:** prediction is deterministic (ADR 7.1.0003), so completing
  and verifying is both safe and cheaper.

### Alternative D — Skip units recorded as done in a ledger, without re-verifying
- **Cons:** trusts a side file over the silver (the 5.5 resume re-checks counts
  for this reason, ADR 5.5.0003); loses the free re-proof of determinism.
- **Why rejected:** reading the run's rows is cheap and stronger.

### Alternative E — Do nothing about the cohort index
- **Why not acceptable:** the first calib write would make `verify` report every
  TFT run as having the wrong row count and different target sets, and a cohort
  `run` would raise `CompletedUnitCorruptedError` — a false corruption alarm on
  the confirmatory cohort.

## Consequences

### Positive
- No DDL; 7.2 reads calib and test of the same `run_id` from one table.
- Re-running `infer` is a verification, not a hazard.

### Negative
- The run index's notion of "a run's rows" narrows to test rows; any future
  consumer that wants all splits must read the fact table itself.
- Per-decision writes mean ~252 partition rewrites per run (same cost profile as
  the trainers' test emission).

### Neutral / trade-offs accepted
- Comparators (baselines, GBM) get no calib rows: the CQR is applied to the
  candidate only (domain doc §2.1, §4); emitting comparator calib would be a
  separate decision.

## References

- Related ADRs: [4.1.0002](./4_1_0002-fact-oos-predictions-long-quantile-format.md),
  [4.3.0001](./4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md),
  [4.3.0002](./4_3_0002-quantile-forecast-dense-grid-guardrail.md),
  [5.1.0002](./5_1_0002-dedicated-calibration-partition.md),
  [5.5.0003](./5_5_0003-resumable-cohort-units-atomic-ledger.md),
  [0.0.0053](./0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md),
  [7.1.0003](./7_1_0003-reproduction-contract-strict-same-environment-tolerance-across.md)
- Code: `analytics_store/adapters/out/parquet/parquet_cohort_run_index.py`,
  `modeling/application/use_cases/run_confirmatory_cohort.py`
  (`recorded_run_problems`), `evaluation/domain/services/series_assembly.py` L155.
- Conversation/issue: [#153](https://github.com/MarceloSanC/financial-forecasting/issues/153).
