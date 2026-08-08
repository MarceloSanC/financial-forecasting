---
title: ADR 1.5.0001 — Experiment tracking via MLflow with a local SQLite backend store
description: Architecture Decision Record
when-use: Reference before changing the experiment-tracking backend, the tracking_uri default, or considering a remote MLflow server / hosted SaaS tracker
keywords: [adr, mlflow, tracking, experiment, sqlite, run-id, sweeps, observability]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "1.5.0001"
decision: Adopt MLflow as the experiment tracker behind the ExperimentTracker port, with a local SQLite backend store (tracking_uri default sqlite:///mlruns.db from Settings), built fresh
context_stage: 1.5-config-and-tracking
bounded_context: shared
---

# ADR 1.5.0001 — Experiment tracking via MLflow with a local SQLite backend store

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

The pilot needs to track training experiments — parameters, metrics over steps,
tags, and artifacts — and to compare sweeps when re-training the TFT and the GBM
baselines (Step 5). This complements the deterministic identity built in Stage
1.4 (`RunId`/`DatasetFingerprint`/`ConfigSignature`/`SplitFingerprint`): each
experiment is a *run* whose params/metrics/artifacts must be auditable and
reproducible, keyed by `run_id`.

Forces and constraints:

- **Single-box pilot (AAPL).** No SaaS budget, no remote infrastructure to
  operate; the project runs on one developer/CI box (overview §6).
- **Foundational decision pre-declared.** Overview §11 lists `0_0_0023`
  ("Tracking = MLflow local (SQLite)") and §6 states "Tracking **MLflow**
  (backend SQLite local)"; the autonomous-run ledger §A (line 1.5) and §B
  pre-declare MLflow + composition_root + MLflow SQLite local, citing overview
  ADR 0022/0023. The concrete justification was deferred to this Stage's ADR.
- **No legacy implementation to reuse.** The old repo
  (`financial-time-series-forecasting`) did **not** use MLflow (grep returned
  empty); it used a hand-rolled Parquet *analytics-store*
  (`parquet_analytics_run_repository.py`) with `dim_run`/`fact_config`/
  `fact_*_metrics`/`fact_model_artifacts` tables and manual dedup by `run_id`
  (`upsert_dim_run`, lines 170-185). So tracking is built **fresh** here; the
  old store is only the source of the **domain semantics** (run/params/metrics/
  artifacts + idempotency by `run_id`), not of the implementation.
- **Hexagonal boundary.** Tracking must sit behind a port
  (`ExperimentTracker`), so the backend choice must be swappable without
  touching the application layer (the port shape is ADR 1.5.0002).

## Decision

Adopt **MLflow** (new dependency) as the experiment tracker, with a **local
SQLite backend store** addressed by a `tracking_uri` (default
`"sqlite:///mlruns.db"`) carried by `Settings` and overridable via the
`MLFLOW_TRACKING_URI` env var. The concrete `MlflowTracker` adapter implements
the `ExperimentTracker` port; the backend is purely local — no remote MLflow
server, no hosted SaaS. Tests isolate runs with `sqlite:///<tmp_path>/mlruns.db`.

Idempotency by `run_id` (re-registering the same `run_id` does not duplicate the
run — it resumes/updates) is preserved as a contract invariant, replicating the
old `upsert_dim_run` dedup semantics, and is verified by the contract test on
both the real adapter and the in-memory fake.

## Alternatives considered

### Alternative A — Keep the old Parquet analytics-store (hand-rolled)

- **Description:** Reimplement the old `dim_run`/`fact_*` Parquet tables with
  manual dedup.
- **Pros:** Mirrors the prior project exactly; no new dependency.
- **Cons:** High cost to re-implement dim/fact + dedup by hand; **no UI** to
  compare sweeps; reinvents what MLflow gives for free; couples tracking to a
  bespoke table schema.
- **Why rejected:** Cost without the comparison/observability benefit; overview
  already chose MLflow (`0_0_0023`). The old store's value is its *semantics*,
  which we keep, not its implementation.

### Alternative B — Remote MLflow tracking server

- **Description:** Run a standalone MLflow tracking server (HTTP) with a managed
  backend.
- **Pros:** Shared, multi-user, scales beyond one box.
- **Cons:** Requires infrastructure to deploy/operate (server + DB + artifact
  store); explicit **non_goal** of this Stage (`servidor MLflow remoto`).
- **Why rejected:** No benefit for a single-box AAPL pilot; pure operational
  cost. Trivially adoptable later by changing `tracking_uri` (the port hides it).

### Alternative C — Hosted SaaS (Weights & Biases / Neptune)

- **Description:** Use a third-party hosted experiment tracker.
- **Pros:** Polished UI, zero local ops.
- **Cons:** External SaaS dependency, account/network coupling, outside the
  overview's stack; cost without academic-reproducibility benefit.
- **Why rejected:** Out of the overview scope; conflicts with the no-SaaS,
  reproducible-on-one-box constraint.

### Alternative D — Do nothing / status quo

- **Description:** Defer tracking entirely.
- **Why not acceptable:** Step 5 (re-training + sweeps) and Stage 5.4
  (`TrainTft` consumes `ExperimentTracker`) need params/metrics/artifacts logged
  and comparable; without tracking the confirmatory scorecard loses
  reproducibility and sweep comparison. The foundation Step 1 must deliver it.

## Consequences

### Positive

- Free sweep-comparison UI + structured logging of params/metrics(step)/tags/
  artifacts, complementing `run_id`/fingerprints from Stage 1.4.
- Local-only, single-box, no SaaS or server to operate — reproducible for the
  TCC.
- SQLite backend is the simplest local store; swapping to Postgres/remote server
  later is a one-line `tracking_uri` change behind the port.

### Negative

- New heavy-ish dependency (`mlflow`) in the dependency tree and CI.
- SQLite single-writer backend is not built for concurrent multi-writer use
  (acceptable for a single-box pilot).

### Neutral / trade-offs accepted

- We accept building tracking fresh (no reuse of the old Parquet store), keeping
  only its domain semantics.
- We defer remote/multi-user tracking and any DVC/hydra integration.

## Implementation notes

- `tracking_uri` lives in `Settings.mlflow_tracking_uri`; the `MlflowTracker`
  adapter (`shared/adapters/out/mlflow/`) receives it and calls
  `mlflow.set_tracking_uri` + start/log/end. The adapter is the only place
  `mlflow` is imported (enforced by `check_layout.py` + `import-linter`).
- Idempotency by `run_id`: `start_run(run_id=...)` resumes an existing run
  instead of creating a duplicate; contract-tested on fake and real.

## References

- Related ADRs:
  [1.5.0002 — ExperimentTracker port shape](./1_5_0002-experiment-tracker-port-shape.md);
  [1.4.0001 — canonical hashing](./1_4_0001-canonicalizacao-de-hash-deterministico.md);
  overview `0_0_0022` (pandas+duckdb), `0_0_0023` (this line).
- External: MLflow Tracking docs (SQLite backend store via `tracking_uri`).
- Conversation/issue: GitHub issue #13; autonomous-run ledger §A (line 1.5), §B.
- Old repo: `financial-time-series-forecasting/src/adapters/parquet_analytics_run_repository.py:170-185`
  (`upsert_dim_run` dedup by `run_id` — source of the idempotency semantics).
