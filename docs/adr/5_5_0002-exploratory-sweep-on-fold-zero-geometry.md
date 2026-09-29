---
title: ADR 5.5.0002 — Both exploratory sweeps (TFT and GBM) run with the same trial budget on a single-fold geometry whose training and early-stopping data coincide with confirmatory fold 0
description: Architecture Decision Record
when-use: Reference before changing the geometry passed to RunTftSweep or RunGbmSweep, before tuning hyperparameters on any data that confirmatory folds later score, before tuning one model and not the other, or before measuring cost or seed variance on held-out data
keywords: [adr, sweep, optuna, exploratory, confirmatory, data-snooping, raschka, walk-forward, expanding-window, fold-zero, isolation, fair-comparison, gbm, tft]
status: accepted
created_at: 2026-09-26
updated_at: 2026-09-27
adr_id: "5.5.0002"
decision: Call RunTftSweep and a new RunGbmSweep with CohortGeometry.exploratory() — n_folds=1, test_size equal to the whole confirmatory OOS tail, same val/calib/embargo — and the same n_trials, so both sweeps train and early-stop on exactly the data of confirmatory fold 0 and never read any block a confirmatory fold scores
context_stage: 5.5-confirmatory-retrain
bounded_context: modeling
---

# ADR 5.5.0002 — Symmetric exploratory sweeps on the fold-0 geometry

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

ADR 5.4.0005 isolates the sweep's **persistence** (nothing written to silver,
objective on early-stop only, `exploratory` tag) but not its **data**.
`RunTftSweep` trains on the **last** fold of the geometry it receives
(`run_tft_sweep.py:185`). Walk-forward windows are expanding (ADR 5.1.0001), so
the last fold's train + early-stop cover the test blocks of folds 0..n-2:
passing the confirmatory geometry would tune on observations the confirmatory
evaluation scores — the optimistic bias of Raschka (2018, §3–4): selection must
use training and validation only, and the final evaluation must use data the
search never touched (domain doc §5.4).

A second asymmetry: Stage 5.3 fixed the GBM at library defaults (zero tuning).
Tuning only the TFT biases the TFT-vs-GBM comparison of hypothesis H2 toward
the TFT.

## Decision

- The runner derives the sweep geometry: `n_folds = 1`,
  `test_size = n_folds_confirmatory × test_size_confirmatory`, `val_size`,
  `calib_size`, `embargo` unchanged. The splitter tiles test blocks from the tail
  (`walk_forward_splitter.py:106-112`), so the sweep's single test block starts
  where confirmatory fold 0's test starts, and its train and early-stop **are**
  fold 0's. The sweeps are fit-only and never read their test block. Equality of
  the train and early-stop tuples is asserted with the real splitter.
- A new `RunGbmSweep` mirrors `RunTftSweep` (same ask-and-tell port, fit-only,
  nothing written to silver, `phase='exploratory'`) and runs with the **same**
  `n_trials` as the TFT sweep (decided by the human, issue #102, B3). Its
  objective is the arithmetic mean, over the cohort's horizons, of the per-horizon
  early-stop loss that the `QuantileModelTrainer` port (5.3) now returns — per
  horizon, the grid-mean pinball at the chosen iteration, which the grid-mean
  early stopping already computes (ADR 5.3.0002). Equal weight per declared
  horizon mirrors the TFT's single objective (`best_val_loss`, the mean loss of
  its multi-horizon decoder). The LightGBM adapter accepts `test_rows=()`
  (fit-only).
  `SearchDimension` stops validating against a fixed `TftTrainingParams`; each
  sweep use case validates the dimensions against its own params type.
- Cost measurement for the human's budget and seed decisions uses one trial of
  each sweep (`n_trials=1`) on this geometry. No statistic is computed on the
  exploratory test block — it is the confirmatory OOS tail.

## Alternatives considered

### Alternative A — Pass the confirmatory geometry (status quo)
- **Why rejected:** trains on confirmatory test data.

### Alternative B — Change `RunTftSweep` to use `folds[0]`
- **Why rejected:** changes a closed Stage's use case; the geometry argument
  already expresses the intent.

### Alternative C — A dedicated pre-sample period excluded from all folds
- **Why rejected:** costs training data in every fold without removing any bias
  (fold 0's training data is never scored).

### Alternative D — Tune only the TFT and declare the asymmetry
- **Why rejected:** decided by the human (B3); unequal tuning effort biases H2.

## Consequences

### Positive
- No confirmatory test observation influences the frozen hyperparameters of
  either model; both models receive comparable tuning effort.
- No code change to `RunTftSweep`'s fold choice.

### Negative
- Hyperparameters are chosen on the smallest training window and a single HPO
  (Bouthillier et al. 2021, App. C.1) — declared limitation.
- `SearchDimension` validation changes in a closed Stage's port (5.4), and the
  `QuantileModelTrainer` result gains an early-stop loss field (5.3).
- The search port has no categorical kind: discrete sets from Lim et al. (2021,
  §6.2) are mapped to int/float ranges, and the attention-head count is fixed
  in the base params instead of searched.

## References

- Related ADRs: [5.1.0001](./5_1_0001-expanding-window-walk-forward.md), [5.3.0002](./5_3_0002-grid-mean-early-stopping.md), [5.4.0005](./5_4_0005-ask-and-tell-sweep-port-and-isolation.md), [5.5.0001](./5_5_0001-frozen-hashed-cohort-spec.md)
- Raschka, S. (2018). Model Evaluation, Model Selection, and Algorithm Selection in Machine Learning. arXiv:1811.12808, §3–4.
- Bouthillier, X. et al. (2021). Accounting for Variance in Machine Learning Benchmarks. MLSys. arXiv:2103.03098, App. C.1.
- Issue #102 (decision B3, 2026-09-27)
