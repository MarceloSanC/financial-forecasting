---
title: ADR 5.5.0004 — All models train and decide on one grid, produced by a single training-dataset reader that trims the missing-value prefix and rejects interior missing values
description: Architecture Decision Record
when-use: Reference before changing how any modeling use case reads the TFT dataset, before feeding rows with NaN to a model, or before imputing missing feature values
keywords: [adr, dataset, warmup, nan, missing-values, trim, grid, single-reader, tft, gbm, baselines, fair-comparison]
status: accepted
created_at: 2026-09-27
updated_at: 2026-09-27
adr_id: "5.5.0004"
decision: Replace the four copies of _load_dataset with one training-dataset reader in the modeling slice that trims the prefix up to the first row where every modeling column (enabled registry features, calendar features, target_return — a fixed set, not per cohort) is finite, raises InteriorMissingValuesError (with per-feature counts) on any later missing value, and returns the rows plus a content fingerprint
context_stage: 5.5-confirmatory-retrain
bounded_context: modeling
---

# ADR 5.5.0004 — Single training grid: one reader, prefix trim, no silent imputation

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

- The dataset keeps warm-up rows as `NaN` (ADR 3.5.0002 keeps NaN in storage).
  The longest registry `warmup_count` is 252 (`revenue_yoy_growth`,
  `net_income_yoy_growth`, `feature_registry.py:611,620`), counted from the
  first as-of report, so the expected prefix is ~300–330 rows (measured at
  materialization). The quality
  gate tolerates up to 2% interior NaN per feature
  (`composition_root.py:161`).
- pytorch-forecasting's `TimeSeriesDataSet` rejects NaN
  (`_timeseries.py:128-146`, installed version). The TFT adapter slices frames
  from row 0 (`pf_tft_trainer.py:412-448`), so every TFT training on the real
  dataset would fail. LightGBM accepts NaN, so without a common rule the GBM
  would train on rows the TFT never sees and the Step 6 paired comparison would
  lose its common basis.
- Four modeling use cases carry their own copy of the dataset read
  (`run_baselines.py`, `train_gbm_quantile.py`, `train_tft.py`,
  `run_tft_sweep.py`; issue #99). A rule placed in one copy would not reach the
  others.

## Decision

- One training-dataset reader in the modeling slice replaces the four copies
  (form fixed in the Stage technical under LAYOUT). Behaviour outside the trim is
  preserved and pinned by characterization tests written before the extraction.
- The reader trims the **prefix** up to the first row where every modeling
  column is finite (pure domain rule `usable_start`). The column set is fixed,
  not per cohort: all enabled registry features, the calendar features and
  `target_return` (the TFT rejects a NaN target too). Today it equals what the
  GBM and the TFT consume (`train_gbm_quantile.py:198-206`,
  `train_tft.py:181-205`), so no command of a closed Stage changes. Test blocks
  are tiled from the tail, so the trim shortens training windows and never moves
  OOS blocks. **Declared behaviour change:** the baselines, which use no
  features, now start at the same row as the models.
- A missing value **after** the prefix raises `InteriorMissingValuesError` with
  per-feature counts. The policy for interior gaps is decided with a measurement
  of the real dataset if they occur — never by silent imputation.
- The reader returns the rows and a `DatasetContentFingerprint` (content-based,
  not file bytes) used by the cohort freeze.
- The dataset's storage is unchanged.

**Implementation note (2026-09-27, Stage 5.5 Task 06):** the single reader is a
pure domain service, `build_training_grid(rows, *, columns)` in
`modeling/domain/services/training_grid.py`. It returns the trimmed rows; the
`DatasetContentFingerprint` is computed by the application caller (hashing lives
only in `shared/domain/value_objects`, `check_layout` rule 6), and each use case
keeps a thin `_load_dataset` that reads the store (asset partition), checks
emptiness with its own error code and delegates to the service.

## Alternatives considered

### Alternative A — Drop warm-up rows in `BuildDataset`
- **Why rejected:** changes the 3.5 dataset contract (4023 rows, regression
  parity) and storage decided in ADR 3.5.0002.

### Alternative B — Forward-fill or zero-fill missing values
- **Why rejected:** invents values for undefined indicators (warm-up has no past
  to fill from) and hides data problems.

### Alternative C — Trim inside each of the four use cases
- **Why rejected:** repeats the rule four times in the copies the refactor
  removes; decided by the human to absorb #99 instead (issue #102, 2026-09-27).

### Alternative D — Per-model trims (TFT trims, GBM keeps NaN rows)
- **Why rejected:** models would train on different sets.

## Consequences

### Positive
- Every model sees the same decision grid; the TFT can train on real data.
- The dataset read exists once; issue #99 closes with this Stage.

### Negative
- Training windows shrink by the longest warm-up (~300–330 rows).
- Refactor touches three closed Stages' use cases (guarded by characterization
  tests).

## References

- Related ADRs: [3.5.0002](./3_5_0002-regime-features-nan-warmup-dtype.md), [5.1.0001](./5_1_0001-expanding-window-walk-forward.md), [5.5.0002](./5_5_0002-exploratory-sweep-on-fold-zero-geometry.md)
- pytorch-forecasting — `TimeSeriesDataSet` NA validation (`_timeseries.py`).
- Issues #99, #102 (Checkpoint A, 2026-09-27)
