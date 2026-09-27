---
title: ADR 5.5.0003 — The confirmatory run resumes by unit through an atomic, locked ledger verified against silver row counts, and silver partitions are written atomically
description: Architecture Decision Record
when-use: Reference before changing how the cohort runner decides a unit is done, before retrying a failed unit, before adding idempotency to the prediction persister, or before changing how the Parquet analytics repository rewrites a partition
keywords: [adr, resumable, idempotency, replay, ledger, atomic-write, os-replace, lock, append-only, partial-failure, row-count, cohort, orchestration, parquet]
status: accepted
created_at: 2026-09-26
updated_at: 2026-09-27
adr_id: "5.5.0003"
decision: Split the cohort into units (baselines, gbm, one tft unit per seed); keep a per-cohort JSON ledger written by temp-file + os.replace with rows per run_id; hold a single-writer O_EXCL lock per data_root for materialize and run; classify units absent from the ledger by reading the cohort's dim_run and prediction counts through a consumer-owned port (orphan dim_run → rerun, full expected count → verified complete, anything else → fail closed); re-verify counts of completed units on resume; and make ParquetAnalyticsRepository write each partition through a temp file + os.replace
context_stage: 5.5-confirmatory-retrain
bounded_context: modeling
---

# ADR 5.5.0003 — Resumable cohort units, atomic ledger and atomic silver writes

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

A confirmatory cohort is hours of training. Facts from the code:

- An identical rerun of a training use case raises `DuplicateKeyError` from
  `fact_oos_predictions` (append-only; Stage 5.4 C7 pinned it "for 5.5").
- `dim_run` is **upsert** (`dim_run_schema.py:60`). The TFT writes it only after
  training all folds; the GBM (`train_gbm_quantile.py:255-282`) and the baselines
  (`run_baselines.py:221-301`) write it inside their loops, so a training failure
  can leave orphan `dim_run` rows with no predictions — safe to rerun.
- `ParquetAnalyticsRepository._write_partition` reads, concatenates and
  `pq.write_table`s **in place** (`parquet_analytics_repository.py:109-112,
  226-250`). `fact_oos_predictions` has one file per (asset, feature set, year)
  holding rows of every unit, and a TFT unit rewrites it once per decision
  (~1512 times). A crash mid-write truncates rows of units already complete.
- The silver has no surgical delete.
- The use case must not receive another slice's `AnalyticsRepository` (ADR
  0.0.0053: the consumer defines the port).

Practice: atomic commit per task and re-execution of only what did not complete
(Dean & Ghemawat 2008, §3.3); DVC `repro` skips unchanged stages and removes
partial outputs before re-running.

## Decision

- **Units:** `baselines` → `gbm` → `tft:seed=<s>` (declared order).
- **Ledger** (`CohortProgressLedger`): JSON under
  `artifacts_root/cohorts/<cohort_id>/` (`artifacts/` becomes git-ignored),
  written to a temp file then `os.replace`; stores `{run_id: rows}` per unit and
  the environment snapshot.
- **Single writer per `data_root`:** the run takes an `O_EXCL` lock on the
  `data_root` — not per cohort — because the yearly `fact_oos_predictions` files
  are shared by every cohort and revision and an atomic write does not isolate
  concurrent writers. The lock records pid, host and start time; a stale lock
  (crash) is removed only explicitly (`--break-stale-lock`).
- **Classification of a unit absent from the ledger** (`CohortRunIndex`, a
  consumer-owned port satisfied by `analytics_store`; attribution by
  `(model_version, seed)`; the port returns the fold and prediction count per
  `run_id`): no `dim_run` → run; orphan `dim_run`, zero predictions → run
  (upsert); all expected runs present (`n_folds` for TFT/GBM, `5 × n_folds` for
  baselines), each with the expected row count of its fold (the last fold has
  fewer rows: its last `h` decisions have no target) → mark
  `verified_completed` without training; anything else →
  `PartialCohortUnitError`, remediated by `revision += 1` (ADR 5.5.0001).
- **Resume check:** completed units are re-verified against silver counts;
  divergence → `CompletedUnitCorruptedError`.
- **Environment:** a resume with any difference in the recorded snapshot
  (library versions, device, CPU, threads, code identity) aborts. Code identity
  is the git content hash of `src/`, `uv.lock` and the cohort file — not HEAD's
  SHA, so documentation commits during the Stage do not block a resume; tracked
  uncommitted changes in those paths are refused, untracked files do not count.
- **Atomic silver writes:** `_write_partition` writes to
  `<file>.parquet.tmp-<pid>` in the same directory (a suffix the read glob
  `**/*.parquet` does not match), removes leftovers of a previous crash, and
  `os.replace`s it.

## Alternatives considered

### Alternative A — Idempotent persister (skip existing rows)
- **Why rejected:** changes append-only semantics of Stages 4.2/4.3/5.x and
  hides genuine duplicates.

### Alternative B — Treat every unit found in silver but absent from the ledger as partial
- **Why rejected:** would abort retryable orphans (GBM/baselines) and complete
  units whose ledger write was interrupted, forcing a new revision and
  re-running every unit (Checkpoint A).

### Alternative C — Redesign the silver PK/replay (ADR 5.2.0004 D5)
- **Why rejected:** evaluated in issue #99 — no gain with a single cohort.

### Alternative D — Do nothing
- **Why rejected:** a late failure would cost the whole budget, and a rerun under
  the same `cohort_id` fails on `DuplicateKeyError`.

## Consequences

### Positive
- A crash costs at most the unit in progress; completed units cannot be
  corrupted by a later crash (atomic partition writes) or silently trusted
  (count re-verification).

### Negative
- A genuinely partial unit forces a new revision, re-running every unit.
- Reading prediction counts scans the cohort's year partitions (acceptable at
  pilot scale).

## References

- Related ADRs: [0.0.0053](./0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md), [5.2.0004](./5_2_0004-canonical-run-identity-via-run-id-and-config-signature.md), [5.5.0001](./5_5_0001-frozen-hashed-cohort-spec.md)
- Dean, J.; Ghemawat, S. (2008). MapReduce: simplified data processing on large clusters. CACM 51(1), §3.3. doi:10.1145/1327452.1327492
- DVC documentation — `dvc repro`. Python documentation — `os.replace`.
- Issue #102; Stage 5.2 technical §7 (2026-07-18); Stage 5.4 concept C7.
