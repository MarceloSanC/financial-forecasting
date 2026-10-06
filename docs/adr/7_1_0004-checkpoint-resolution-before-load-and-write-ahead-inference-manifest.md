---
title: ADR 7.1.0004 — A run's checkpoint is resolved without loading (rule + exactly one `.ckpt` + streamed sha256), every guard runs before the unpickle, and the inference records a write-ahead, merge-only JSON manifest under `data_root`, under the data-root writer lock
description: Architecture Decision Record
when-use: Reference when locating a run's checkpoint, before loading any checkpoint, before persisting checkpoint paths in a table, when asking where the inference's parameters, environment and library versions are recorded, what happens when calib rows exist without a manifest entry, or why `infer` takes the cohort writer lock
keywords: [adr, inference, checkpoint, artifact, run-id, sha256, allowlist, weights-only, unpickle, manifest, write-ahead, provenance, sandve, writer-lock, data-root]
status: accepted
created_at: 2026-10-06
updated_at: 2026-10-06
adr_id: 7.1.0004
decision: Resolution and prediction are two calls — `ResolveTftCheckpoints` derives each fold's `run_id`, locates `<artifacts_root>/tft/<run_id>/*.ckpt` (exactly one) and streams its sha256 without importing or loading anything; `RunInference` then checks the current environment, `dim_run` membership and the manifest's sha256, and only then calls `PredictTftFromCheckpoints` with an allowlist `run_id → expected sha256`, whose adapter reads the bytes once, hashes them, refuses on mismatch and loads from those same bytes; provenance goes to `<data_root>/inference/<cohort_id>/manifest.json`, whose per-run entry is written (status `started`, sha256, environment) before the first calib write and merged afterwards without ever overwriting first-write fields; calib rows present without an entry raise; `infer` holds the `data_root` writer lock.
context_stage: 7.1-inference-engine
bounded_context: inference
---

# ADR 7.1.0004 — Resolution before load; write-ahead inference manifest

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

- Concept 5.4 D9: the best-epoch checkpoint is written under
  `<artifacts_root>/tft/<run_id>/` and logged to the experiment tracker; no
  silver table for artifacts (ADR 1.5.0002). `ModelCheckpoint(save_top_k=1)`
  keeps one file per directory; the 60 cohort directories hold exactly one
  `.ckpt` each (listed 2026-10-06).
- `load_from_checkpoint` in pytorch-forecasting 1.8.0 sets `weights_only=False`
  unless the caller passes it (lightning ≥ 2.6; verified 2026-10-06) —
  unpickling can execute code, "only if you got the file from a trusted source"
  (torch `serialization.py`). A hash checked **after** loading protects nothing;
  every identity guard must run before the unpickle.
- Sandve et al. (2013) Rule 1: "For Every Result, Keep Track of How It Was
  Produced". `fact_oos_predictions` is `strict=True`, schema v1, with no column
  for inference parameters.
- Calib rows are written one decision per call (ADR 7.1.0002); a crash leaves
  some rows written. Their later verification needs the environment they were
  written in (ADR 7.1.0003 item 3), so that record must exist **before** the
  first row does.
- The cohort runner records environment and progress in JSON and serializes
  writers to `data_root` with a lock (ADR 5.5.0003, I12); yearly Parquet
  partitions are rewritten read-modify-write. `artifacts_root` is shared by
  every `data_root` (a backup copy of the data root included), so a record
  keyed only by `cohort_id` under `artifacts_root` would mix silvers.

## Decision

1. **Resolution without load.** `ResolveTftCheckpoints` (modeling use case,
   real of the inference port `CheckpointResolver`) checks the cohort
   declarations and completeness, derives each fold's `run_id` with the
   `TrainTft` identity function, composes the directory with the same rule and
   calls `CheckpointLocator.locate` — a stdlib adapter
   (`modeling/adapters/out/filesystem/checkpoint_locator.py`) whose module
   imports no torch/lightning/pytorch_forecasting — which requires exactly one
   `*.ckpt` (none → `CheckpointNotFoundError`, several →
   `AmbiguousCheckpointError`) and streams its sha256: no unpickle, no
   deep-learning import. It returns `(fold_index, run_id, model_version, path, sha256)`
   per fold. No path is persisted anywhere.
2. **Guards in the consumer, before any load.** `RunInference` checks, in this
   order: current environment (probe: `code_dirty`), cohort environment
   recorded, then per run: membership in `dim_run` of the frozen cohort
   (`parent_sweep_id = cohort_id`, `model_version`, seed, fold), and sha256
   equal to the manifest's when the manifest already has the run.
3. **Allowlisted prediction, hash and load the same bytes.**
   `PredictTftFromCheckpoints` receives `allowed: run_id → expected sha256`; a
   derived `run_id` not in it raises `UnknownRunError` without loading; the
   adapter reads the file's bytes **once**, hashes them with the stdlib streaming hash
   function of the port module `checkpoint_locator.py` (shared by locator and
   trainer without an adapter-to-adapter import), raises `ArtifactChangedError` on mismatch, and otherwise passes
   `io.BytesIO(bytes)` to `load_from_checkpoint` — what is loaded is exactly
   what was hashed, with no window in between. Verified on the pinned image:
   lightning 2.6.5 `pytorch/core/saving.py` L55 (`checkpoint_path: Union[_PATH,
   IO]`) and L65 (`pl_load(checkpoint_path, …)`), `fabric/utilities/cloud_io.py`
   L51–56 ("any sort of BytesIO or similar" → `torch.load`).
4. **Write-ahead, merge-only manifest.** Consumer port `InferenceManifest`
   (`recorded(cohort_id)`, `record_run(cohort_id, run_id, entry)`), JSON adapter
   in `inference/adapters/out/filesystem/`, file
   `<data_root>/inference/<cohort_id>/manifest.json` — next to the silver it
   describes, under the same lock; a copy of the data root carries its own
   manifest. Writes go through a temporary file + `os.replace`.
   - Header: cohort id, the cohort's recorded environment.
   - Per run, **first-write fields** (set once, never overwritten by a later
     merge): checkpoint sha256, the environment snapshot and inference settings
     under which the run's first calib row was written, `first_written_at`.
     A `started` entry is resumed only when the current non-code environment
     equals this first-write environment; otherwise `InferenceEnvironmentError`
     (resume in the original environment), so the recorded environment
     describes every row of the run.
   - Per run, **last-verification fields** (replaced on each run of `infer`):
     status (`started` → `completed`), path, current environment and settings
     (batch size, `num_workers`, accelerator, threads, deterministic flag,
     `torch.backends.cpu.get_cpu_capability()`, platform, scikit-learn
     version), `normalizer_center` and `normalizer_scale`, reproduction mode,
     reason, `forced` (true only when a justified `--cross-environment` was given
     **and** the non-code keys are equal — with a differing key the flag changes
     nothing and `forced` stays false; the justification text is stored), values compared, max |Δ|, max |Δ|/scale, calib rows written and
     verified, timestamp from the `Clock`.
   - The entry is written with status `started` **before** the first calib
     write of that run and set to `completed` only after the silver re-read
     confirms the count (ADR 7.1.0002 item 3).
   - **Missing entry with calib rows present** → `CalibProvenanceMissingError`:
     the rows cannot be verified without knowing the environment they were born
     in; remediation is restoring the manifest (it travels with the data root).
5. **Writer lock.** `RunInference` acquires the `data_root` writer lock through
   the consumer port `CohortLedger` (`acquire_writer`, `release_writer`,
   `environment`) satisfied structurally by `JsonCohortProgressLedger`, and
   releases it in `finally`; `--break-stale-lock` is the same explicit operator
   decision as in the 5.5 CLI.

## Alternatives considered

### Alternative A — One port that derives, loads and predicts (first draft)
- **Cons:** the consumer could only check `dim_run`, the manifest and the
  environment **after** the unpickle had already happened (Checkpoint A, round 1,
  blocker).
- **Why rejected:** the guard order is the point of the guards.

### Alternative B — Allowlist only (no separate resolution call)
- **Description:** the consumer passes allowed `run_id`s and expected hashes
  read from `dim_run`/manifest; the modeling raises before load.
- **Cons:** on the first run there is no expected hash to pass (the manifest is
  empty), so the hash would be computed and trusted in the same call that
  loads; the consumer could not record the sha256 before the load.
- **Why rejected:** kept as item 3 (defense in depth) on top of resolution.

### Alternative C — Persist the checkpoint path (silver column/table, cohort ledger)
- **Cons:** DDL or a modeling-ledger schema change to store what a rule
  derives; an absolute path breaks when `artifacts_root` moves; ADR 1.5.0002
  rejected an artifact table.
- **Why rejected:** the rule plus "exactly one file" detects the same
  ambiguities without new state.

### Alternative D — Resolve or record through the MLflow tracker
- **Cons:** observability whose failure is absorbed by design (C8 of 5.4); not
  a source of truth nor a citable dossier artifact.
- **Why rejected:** Rule 1 asks for a durable record next to the result.

### Alternative E — New silver table for inference provenance
- **Cons:** DDL, schema registry entry, pandera schema and repository dispatch
  for a handful of values per run; the cohort's equivalent record already lives
  in JSON (ADR 5.5.0003 — rung 1).
- **Why rejected:** disproportionate.

### Alternative F — Manifest under `artifacts_root`, overwritten per invocation (first draft)
- **Cons:** mixes records of different data roots; a crash between calib writes
  and the end-of-run write leaves rows without provenance; an overwrite loses
  the environment the rows were born in (Checkpoint A, round 1).
- **Why rejected:** replaced by items 4.

### Alternative G — Verify calib rows without an entry in tolerance mode
- **Cons:** would accept rows of unknown origin as the candidate's calib.
- **Why rejected:** the rule in item 4 fails closed.

### Alternative H — No lock
- **Why not acceptable:** `infer` concurrent with `run` (or another `infer`)
  can drop rows from a shared yearly partition.

## Consequences

### Positive
- No checkpoint is unpickled before identity, membership and environment are
  established; a swapped file between resolution and load is refused.
- Every calib row can be traced to a checkpoint hash and to the environment it
  was written in, across crashes and re-runs.

### Negative
- Two modeling use cases and two consumer ports instead of one.
- The first inference cannot prove the checkpoint is the one the trainer wrote
  (no hash at training time); the test reproduction (ADR 7.1.0003) is the
  behavioral proof.
- Losing the manifest makes existing calib rows unverifiable until it is
  restored.

### Neutral / trade-offs accepted
- The inference slice depends structurally on modeling adapters for the lock
  and the probe (wired only in the composition root; no import).

## References

- Related ADRs: [1.5.0002](./1_5_0002-experiment-tracker-port-shape.md),
  [5.5.0003](./5_5_0003-resumable-cohort-units-atomic-ledger.md),
  [0.0.0053](./0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md),
  [7.1.0001](./7_1_0001-checkpoint-prediction-supplied-by-modeling-through-consumer-port.md),
  [7.1.0002](./7_1_0002-calib-predictions-in-fact-oos-predictions-idempotent-completion.md),
  [7.1.0003](./7_1_0003-reproduction-contract-strict-same-environment-tolerance-across.md)
- External: pytorch-forecasting 1.8.0 `models/base/_base_model.py` L812–832;
  torch 2.13 `serialization.py` L76–81; Sandve, Nekrutenko, Taylor & Hovig
  (2013), PLoS Comput Biol 9(10):e1003285, Rule 1.
- Concept 5.4 D9; issue [#153](https://github.com/MarceloSanC/financial-forecasting/issues/153);
  Checkpoint A round 1 (A-C1/A-D1, A-C3/A-D2, A-C8/A-D5).
