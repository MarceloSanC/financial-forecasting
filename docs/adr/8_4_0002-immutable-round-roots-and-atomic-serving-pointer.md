---
title: ADR 8.4.0002 — The production job writes each dated round into an immutable root of its own under a production-root lock, publishes it by atomically and monotonically replacing a serving.env pointer only after verify passes, and the API switches cohorts by recreating its container with that pointer; scheduling is an external cron or Task Scheduler calling an idempotent CLI command
description: Architecture Decision Record
when-use: Reference when asking how the publication window of ADR 6.4.0005 is handled for the production job, how the API switches to a new round, what happens when a round fails halfway or two rounds overlap, how a rerun of the same round behaves, why a round is named by a date, where the scheduler runs, or what the production root layout is
keywords: [adr, inference, production-job, scheduler, cron, idempotency, resume, lock, atomic-rename, os-replace, serving-pointer, data-root, publication-window, restart, monotonic]
status: accepted
created_at: 2026-10-25
updated_at: 2026-10-25
adr_id: 8.4.0002
decision: The CLI subcommand production-round (--production-root, --round YYYY-MM-DD[.N], --raw-root, --cohort) validates every argument before writing anything, refuses a production root equal to, inside or containing <repo_root>/data/cohorts/ (resolved, case-insensitive), holds the cohort ledger's single-writer lock on the production root for the whole command, writes a round only under <production-root>/rounds/<round>/ (inputs copied, derived layers, silver, artifacts, mlruns.db, cohort.toml) with Settings data_root, artifacts_root and mlflow_tracking_uri pointing into the round, marks the materialization with a .materialized file written last and redoes an unmarked one from scratch, resumes everything else through the cohort runner, and only after the round's verify prints OK replaces <production-root>/serving.env (DATA_ROOT and SERVING_COHORT_FILE, absolute container paths) through a uniquely named temporary file and os.replace, and only if no pointer exists, the pointer already names this round, or this round sorts after the named one; the API reads the pointer once at start-up, so switching cohorts is recreating its container with docker run --env-file, and no process reads a root while it is written — the ADR 6.4.0005 window does not arise; the remaining risk is the recreation gap, measured and accepted; scheduling is a host cron line or Windows Task Scheduler task, with no orchestrator and no compose change.
context_stage: 8.4-production-cohort-job
bounded_context: inference
---

# ADR 8.4.0002 — Immutable round roots and an atomic serving pointer

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 8.4 concept (issue #202), 2026-10-25. Items 1–3 close by
evidence; item 5 by convention; item 4 (where the scheduler runs) is a
preference decision taken by the session, **pending ratification by the
owner** (concept 8.4 D4). Revised after Checkpoint A (two independent
reviewers): round names as dates, a production-root lock, a monotonic and
uniquely staged pointer, the per-round tracking store and the exact
recreation command.

## Context

- ADR 6.4.0005 publishes a gold generation by two directory renames
  (`current/ → .previous/`, `.staging/ → current/`). Between them, a reader
  sees no manifest ("gold não publicado"), and a reader that reads the
  manifest and then the tables could see a newer generation if a swap happens
  in between. Stage 7.4 accepted that risk because the refresh is manual and
  rare (concept 7.4 §8). Issue #202 asks the scheduled job to handle it:
  "publish in another `data_root` and switch the API configuration, or have an
  atomic read of the generation", or measure and accept it in writing.
- The API reads `SERVING_COHORT_FILE` and `DATA_ROOT` through `Settings` and
  builds `ServeInference` once in `create_app` (concept 7.4 D8). A `KEY=value`
  file passed to `docker run --env-file` configures it without code. The
  compose `--env-file` option only feeds interpolation of the compose file, and
  the compose `app` service mounts the dev venv without the `sentiment` extra
  and runs uvicorn with `--reload`.
- Python docs, `os.replace`: "If successful, the renaming will be an atomic
  operation (this is a POSIX requirement)". ADR 6.4.0005 records that on the
  Windows host's `9p`/`drvfs` bind mount this is observed, not documented.
- The `materialize` step is not idempotent: ingestion appends to the bronze
  and refuses a duplicate key (`DuplicateKeyError`; runbook
  `confirmatory-cohort-aapl`, Step 4). The cohort `run` is resumable per unit
  (ADR 5.5.0003) and takes the single-writer lock of its `data_root`
  (`<data_root>/.writer.lock`, `O_CREAT | O_EXCL`, with `--break-stale-lock`
  for an orphan).
- `validate_path_identifier` accepts `.` and `..` (pattern
  `^[A-Za-z0-9._-]+$`), harmless where the identifier is always prefixed
  (`asset=<a>`), not where it becomes a directory name on its own.
- Every TFT training logs to MLflow (`Settings.mlflow_tracking_uri`, default
  `sqlite:///mlruns.db` relative to the working directory) and copies its
  checkpoint to the MLflow artifact store, which with a SQLite backend sits in
  `./mlruns/` of the working directory.
- Issue #202 classes "where the scheduler runs" as an infrastructure decision
  outside v0.

## Decision

1. **Immutable round roots, validated before any write.** `[decision:E]` A
   round writes only under `<production-root>/rounds/<round>/`: `raw/` and
   `processed/fundamentals/` (copies of the inputs), `.materialized`,
   `bronze/`, `processed/dataset_tft/`, `silver/`, `artifacts/` (checkpoints and
   ledger), `mlruns.db` (tracking) and `cohort.toml` (the round spec, ADR
   8.4.0001). The command builds the process `Settings` with `data_root`,
   `artifacts_root` and `mlflow_tracking_uri` inside the round. Outside the
   production root the job writes only the MLflow artifact copy in `./mlruns/`
   of the working directory, like every training of the project. Before
   writing anything the command validates the round name, the three inputs and
   the production root, which may not be equal to, inside or contain
   `<repo_root>/data/cohorts/` (where the confirmatory and ablation cohorts
   live, the convention stated in `cli.py`), comparing resolved paths without
   case.
2. **Atomic, monotonic pointer after verify.** `[decision:E]` After `verify`
   prints `OK`, the command writes a uniquely named temporary file
   (`tempfile.mkstemp`) next to the pointer, with exactly two lines
   (`DATA_ROOT=<abs round root>`, `SERVING_COHORT_FILE=<abs round
   root>/cohort.toml`), and replaces `serving.env` with `os.replace`. It
   publishes only if there is no pointer, the pointer already names this round,
   or this round sorts after the named one; an older round ends verified with
   `not published`. A failed `verify` exits 1 and leaves the pointer
   byte-identical; a failed write leaves it intact and removes the temporary.
3. **Switch by recreating the API container; the ADR 6.4.0005 window does not
   arise.** `[decision:E]` After a run that printed `published`, the operator
   (or the scheduled script) removes the API container and starts it again with
   `docker run -d --env-file <production root on the host>/serving.env …`. The
   process never reads a root that is being written: the round's root is
   complete before the pointer names it, the previous root is untouched, and
   the API reads the pointer only at start-up, so correctness does not depend on
   the rename being atomic on the bind mount. The round publishes no gold (ADR
   8.4.0001 item 5), so the two-rename swap never runs on a served root; a later
   production gold would be published inside the round before the switch.
   **Residual risk, measured and accepted:** while the container is recreated
   the API does not answer (the time is recorded in technical 8.4 §7,
   `[measurement]`). The project has one operator and no availability target,
   so a short gap at a scheduled time is accepted. A rolling switch (two API
   processes behind a proxy) is out of v0.
4. **Scheduling outside the code.** `[decision]` P (D4). The job is the
   idempotent CLI command, run by `docker run --rm` of the dev image with a
   venv volume that has the `sentiment` extra, the Hugging Face cache and the
   checkout mounted. Scheduling is a host cron line or a Windows Task Scheduler
   task that runs it with `--round $(date +%F)` and, if it published, recreates
   the API container. The runbook `production-cohort-job.md` carries the exact
   commands. No orchestrator, no new compose service, no compose change.
5. **Round identity, exclusion and resume.** `[decision:C]` A round is named
   by an ISO date with an optional `.N` suffix to redo a day
   (`2026-10-25`, `2026-10-25.1`): the scheduler produces it without reading
   data, it orders rounds for item 2, and it rules out `.` and `..`. The whole
   command holds the cohort ledger's single-writer lock on the production root
   (the round's own lock is taken by the runner inside it), so two rounds never
   overlap and the same round triggered twice fails fast without deleting
   anything; an orphan lock needs `--break-stale-lock` after the operator
   confirms the owner died. Rerunning the same round while code, environment
   and model are unchanged: a marked materialization is skipped; an unmarked
   one deletes the round's copied inputs and derived layers and starts over; an
   equal round spec is kept, a different one is an error; the runner skips
   completed units and resumes the rest; `verify` runs again; the pointer obeys
   item 2. A round that cannot resume (environment changed, partial or
   corrupted unit) is replaced by a new round name, never by raising the
   model's `revision`. Rung 5 (the simplest): naming rounds by input content
   would need a file hash outside the shared identity value objects for a
   deduplication the operator gets by not scheduling a round without new
   inputs.

## Alternatives considered

### Alternative A — Atomic read of the gold generation
- **Description:** make the gold reader pin a generation (a versioned
  directory per generation plus a pointer file) so a concurrent swap cannot mix
  generations.
- **Pros:** would also fix the residual risk of ADR 6.4.0005 for the
  confirmatory refresh.
- **Cons:** changes the `ParquetGoldStore` and its readers (evaluation and the
  API) for a job that publishes no gold.
- **Why rejected:** not needed once the job never publishes into a served
  root; it stays a candidate if the confirmatory refresh ever becomes
  recurrent.

### Alternative B — Hot reload of the API configuration
- **Description:** the API watches `serving.env` and rebuilds
  `ServeInference` when it changes.
- **Pros:** no restart gap.
- **Cons:** changes the serving path (`create_app`, `register_http_routes`);
  issue #202 criterion 3 forbids a code change in the API; adds mutable state to
  the process.
- **Why rejected:** criterion 3 and the 7.4 D8 decision to build the use case
  once.

### Alternative C — Compose service for the job and `env_file` for the API
- **Description:** add a `production-job` service and point the `app` service's
  `env_file` at `serving.env`.
- **Pros:** shorter commands.
- **Cons:** changes the compose file every developer and gate uses; the `app`
  service and every `docker compose run` would inherit the round's `DATA_ROOT`.
- **Why rejected:** `docker run` with explicit mounts keeps the dev compose
  untouched.

### Alternative D — A scheduler service or orchestrator
- **Description:** a dedicated container with a scheduler, or Airflow/Prefect.
- **Pros:** retries and history in one place.
- **Cons:** a new long-running service for a weekly job of one asset; the
  issue places it outside v0.
- **Why rejected:** skill `project-scope-principles`; the CLI command is what
  an orchestrator would call anyway.

### Alternative E — Do nothing (accept the window)
- **Why rejected:** a recurring publication into a served root would turn a
  rare risk into a weekly one; the round roots remove it at no extra cost.

## Consequences

### Positive
- A failed, interrupted or older round never affects what the API serves.
- The previous round stays available for rollback: point `serving.env` back
  (by hand, documented in the runbook) and recreate the API.

### Negative
- Disk grows by one round per run until the operator deletes old rounds (the
  runbook says how; no automatic retention).
- A short unavailability at each switch.

### Neutral / trade-offs accepted
- The pointer carries absolute container paths, so the job and the API mount
  the production root at the same container path.

## References

- Related ADRs: 5.5.0003, 6.4.0005, 7.4.0001, 8.4.0001.
- Python docs, `os.replace`; `tempfile.mkstemp`.
- Issue #202 (Restrição conhecida); concept 7.4 D8 and §8; concept 8.4 D4,
  D6, D8; LAYOUT §3 note on `operational-evolution-policy.md`.
