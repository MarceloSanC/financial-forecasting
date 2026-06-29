---
title: ADR 0.0.0022 — Data engine is pandas + DuckDB over Parquet — DuckDB for fast SQL reads and as-of joins, pandas for model-library interop; no Postgres
description: Architecture Decision Record
when-use: Reference before introducing a new data engine, a new storage/query backend, a Postgres dependency, or any in-process join/scan on the data path
keywords: [adr, data-engine, duckdb, pandas, parquet, as-of-join, asof, sql, no-postgres, medallion, read-engine, foundational]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "0.0.0022"
decision: The data engine is pandas + DuckDB over Parquet — DuckDB provides fast columnar SQL reads (partition pruning) and as-of joins over Parquet, pandas provides interop with the model/stat libraries; there is no Postgres; both engines are confined to adapters by the store-no-storage-leak import-linter contract
context_stage: 3.3-fundamentals-asof-join
---

# ADR 0.0.0022 — Data engine = pandas + DuckDB over Parquet

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

> Foundational ADR listed in `overview.md` §11 (`adr_id 0.0.0022`, "Engine de dados =
> pandas + duckdb"). The file did not exist until Stage 3.3 — the first Stage whose
> scope *exercises* a DuckDB **as-of join** (the headline use named in this ADR's
> rationale). It is officialized here, mirroring Stage 3.1's officialization of
> `0.0.0024` and Stage 3.2's of `0.0.0017`/`0.0.0018`. (Stage 2.1 already used DuckDB
> as the medallion **read** engine; this Stage is where the **as-of join** lands.)
> ADR `1.1.0001` (line 132) referenced this file as "to be authored".

## Context

The project persists everything in **Parquet** (medallion bronze/silver/gold,
`overview.md` §6, `0.0.0015`) and explicitly rejects a heavyweight RDBMS for the pilot
(`overview.md` §6: "Persistência **Parquet + DuckDB**; **sem Postgres**").

Forces at play:

- **Two distinct data jobs.** (1) Fast **reads/scans** over partitioned Parquet with
  partition pruning and fast **as-of joins** — a columnar SQL job. (2) **Interop**
  with the Python model/stat libraries (`arch`, `statsmodels`, `scikit-learn`,
  `scoringrules`, `statsforecast`, `LightGBM`, `MAPIE`, `pytorch-forecasting`), which
  speak pandas `DataFrame`. No single library is best at both.
- **DuckDB fits job 1.** Embedded, zero-server, reads Parquet directly with predicate/
  partition pushdown, and has first-class **ASOF JOIN** — exactly the point-in-time
  backward join the fundamentals feature (Stage 3.3) and other temporal merges need.
- **pandas fits job 2.** It is the lingua franca of the model/stat ecosystem; the
  adapters that wrap those libraries already pass `DataFrame`s.
- **No Postgres.** A server RDBMS adds operational weight (a running service,
  migrations, connection management) with no benefit for a single-asset, file-based,
  reproducible pilot. The template's default SQLAlchemy/Postgres assumption was
  explicitly set aside (ADR `1.1.0001`).
- **Engines must not leak into the core.** The hexagonal discipline (`0.0.0019`)
  keeps data libraries in adapters; the `import-linter` `store-no-storage-leak`
  contract already forbids `pandas`/`pyarrow`/`duckdb`/`pandera` in the
  `application`/`domain` layers of `shared` and the feature BCs.

## Decision

**The data engine is pandas + DuckDB over Parquet, with no Postgres.** DuckDB is the
read/scan and **as-of join** engine over partitioned Parquet (partition pruning, fast
columnar SQL, `ASOF JOIN` for backward point-in-time joins); pandas is the interop
layer with the model/stat libraries. Both engines are **confined to adapters** — the
`application` and `domain` layers depend only on `Protocol` ports exchanging
`collections.abc`/primitives, enforced by the `import-linter` `store-no-storage-leak`
contract (which lists `pandas`/`pyarrow`/`duckdb`/`pandera` as forbidden in those
layers). The first concrete read use is the `ParquetMedallionStore` (Stage 2.1,
DuckDB read with partition pruning); the first **as-of join** use is the
`AsofJoinDuckdbAdapter` (Stage 3.3, `ASOF JOIN d.date >= f.effective_date`).

## Alternatives considered

### Alternative A — Postgres (or another server RDBMS) as the data engine

- **Description:** Store and query data in Postgres; use SQLAlchemy.
- **Pros:** Mature SQL, transactions, ecosystem; the template's default.
- **Cons:** Requires a running server, migrations, connection management — operational
  weight with no benefit for a single-asset, reproducible, file-based pilot; reading
  Parquet (the medallion format) back into a server is friction, not help.
- **Why rejected:** `overview.md` §6 explicitly chooses "Parquet + DuckDB; sem
  Postgres"; the pilot is file-based and reproducible. (ADR `1.1.0001` set aside the
  template's SQLAlchemy assumption for exactly this.)

### Alternative B — pandas only (no DuckDB)

- **Description:** Do reads and joins (including as-of) purely in pandas.
- **Pros:** One library; `merge_asof` exists.
- **Cons:** No partition pruning over Parquet partitions (full-frame loads), slower
  large scans, and joins run in the Python process; SQL pushdown is lost. The old repo
  used `pandas.merge_asof` inside a monolith — the very shape this project decomposes.
- **Why rejected:** DuckDB gives pushdown reads and a first-class ASOF JOIN over
  Parquet at near-zero operational cost; pandas remains for model-library interop. The
  two are complementary, not competing.

### Alternative C — DuckDB only (no pandas)

- **Description:** Use DuckDB end-to-end, including feeding models.
- **Pros:** One engine on the data path.
- **Cons:** The model/stat libraries (`arch`, `statsmodels`, `sklearn`, `LightGBM`,
  `pytorch-forecasting`, …) speak pandas, not DuckDB relations; an all-DuckDB path
  would constantly materialize to pandas anyway.
- **Why rejected:** pandas is the interop standard for the modeling stack; keeping it
  for that job is pragmatic.

### Alternative D — Do nothing / leave the engine implicit

- **Why not acceptable:** Leaving the engine unstated invites ad-hoc choices per Stage
  (the prior repo's drift) and an accidental Postgres/SQLAlchemy dependency from the
  template. One foundational statement anchors the read+join path and the
  `store-no-storage-leak` gate.

## Consequences

### Positive

- One fast, embedded SQL engine (DuckDB) for reads and as-of joins over Parquet, with
  partition pruning; pandas retained for model-library interop.
- No server to run — reproducible, file-based, CI-friendly.
- Both engines confined to adapters by `store-no-storage-leak`; the core stays pure
  and engine-agnostic, so either engine is swappable behind its port.

### Negative

- Two engines on the data side (DuckDB + pandas) — a small conceptual surface;
  mitigated by the clear split (DuckDB = read/scan/as-of, pandas = model interop) and
  by both being adapter-only.
- DuckDB SQL (e.g. ASOF JOIN syntax) is pinned to the project's DuckDB version;
  version bumps must re-verify syntax — mitigated by adapter contract tests.

### Neutral / trade-offs accepted

- The exact per-Stage mechanism (DuckDB read in 2.1, DuckDB ASOF JOIN in 3.3, any
  pandas adapter for model interop downstream) is detailed in those Stages' artifacts;
  this ADR states the engine policy, not the SQL.

## Implementation notes

- Read engine: `shared/adapters/out/parquet/parquet_medallion_store.py` (Stage 2.1,
  DuckDB read with partition pruning behind `MedallionStore`).
- As-of join: `features/feature_engineering/adapters/out/duckdb/asof_join_adapter.py`
  (Stage 3.3, `ASOF JOIN d.date >= f.effective_date` behind `AsofJoinAdapter`; ADR
  `3.3.0001`).
- Gate: `.importlinter` `store-no-storage-leak` forbids `pandas`/`pyarrow`/`duckdb`/
  `pandera` in `{shared,market_data,feature_engineering}.{application,domain}`.

## References

- Related ADRs: [3.3.0001](./3_3_0001-duckdb-asof-backward-join.md) (the first as-of
  join exercising this engine), [2.1.0002](./2_1_0002-medallion-store-port-shape.md) /
  [2.1.0001](./2_1_0001-medallion-partition-and-bronze-schemas.md) (the DuckDB read
  engine behind `MedallionStore` over partitioned Parquet),
  [0.0.0019](./0_0_0019-hexagonal-enforced.md) (engines confined to adapters),
  [1.1.0001](./1_1_0001-template-surplus-handling.md) (set aside the template's
  SQLAlchemy/Postgres default for Parquet+DuckDB),
  [1.5.0001](./1_5_0001-mlflow-sqlite-local-tracking.md) (cites this line as
  `0.0.0022`).
- `docs/overview.md` §6 ("Persistência Parquet + DuckDB; sem Postgres"), §7 (libs:
  `pandas`+`duckdb` for transformations and as-of joins), §11 (`0.0.0022` "Engine de
  dados = pandas + duckdb … SQL rápido e as-of joins sobre Parquet"; `0.0.0015`
  medallion Parquet — bronze/silver/gold).
- `docs/autonomous-run-decision-ledger.md` §B line 3.3 (DuckDB ASOF backward).
- External: DuckDB ASOF JOIN documentation; pandas `merge_asof` (the semantics ported
  in Stage 3.3).
