---
title: ADR 2.1.0002 — MedallionStore as a minimal structural Protocol that does not leak pandas/pyarrow/duckdb/pandera
description: Architecture Decision Record
when-use: Reference before changing the MedallionStore port signature, adding operations, or letting any storage/dataframe library type cross into the application layer
keywords: [adr, medallion-store, port, protocol, hexagonal, pandas, pyarrow, duckdb, pandera, append-only, duplicate-key, contract-test]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "2.1.0002"
decision: Define MedallionStore as a minimal structural Protocol (write/read partitioned datasets) over stdlib/collections.abc types, with append-only + dedup-by-logical-PK + partition filtering as contract invariants and no pandas/pyarrow/duckdb/pandera types leaking into application
context_stage: 2.1-medallion-storage-contracts
bounded_context: shared
---

# ADR 2.1.0002 — MedallionStore as a minimal structural Protocol that does not leak pandas/pyarrow/duckdb/pandera

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

Stage 2.1 introduces the first real out-adapter of the medallion pipeline: a
store that writes and reads partitioned Parquet datasets across the bronze/
silver/gold layers. The concrete adapter uses `pyarrow` for partitioned writes
and `duckdb` for partition-pruned reads (overview §11 / ADR `0.0.0022`, "engine
de dados = pandas + duckdb"), and validates incoming data with `pandera`
bronze schemas. The application layer, however, must not depend on any of these
libraries: the store must be swappable, testable with an in-memory fake, and
validated by a contract test shared between fake and real (same posture as
Stage 1.4/1.5 / ADR `0.0.0021`).

Forces and constraints:

- **Hexagonal rules of this project.** Ports are `Protocol`s (structural), not
  ABCs; the application tests with a **fake** of the port, adapters get a
  **contract test**; `domain/` stays stdlib-only; data/ML libraries live only
  in adapters (`check_layout.py` + `import-linter` are the gate). The
  `domain-purity` contract already forbids `pandas`/`pyarrow` in `domain`; this
  Stage extends the same posture to the `application` layer for
  `pandas`/`pyarrow`/`duckdb`/`pandera` (mirroring the `tracker-no-mlflow-leak`
  contract added in Stage 1.5).
- **Downstream consumers are known.** Stages 2.2 (`IngestCandles`) and 2.3
  (news/fundamentals ingestion) consume `MedallionStore` to write bronze facts
  (roadmap `contratos_consumidos: [MedallionStore (2.1)]`); 3.x/4.x read
  partitioned data back. They need to (a) write a batch of rows to a
  `(layer, table)` dataset partitioned by `asset`/`year`, append-only with
  collision detection, and (b) read a `(layer, table)` dataset filtered by
  partition (at minimum by `asset`).
- **Domain semantics from the old repo.** The old Parquet analytics-store wrote
  facts with append-only-plus-collision semantics and a `DuplicateKeyError`
  (`parquet_analytics_run_repository.py:103-139`), batched per partition path
  (`:155-168`). That append-only/dedup-by-logical-PK is the semantic to preserve
  — as a *contract*, not a pandas/Parquet detail. The old port was an
  `ABC`/`@abstractmethod` (`interfaces/analytics_run_repository.py:11`); this
  project mandates a `Protocol`.

## Decision

Define `MedallionStore` as a **minimal structural `Protocol`** in
`shared/application/ports/out/medallion_store.py`, exchanging only stdlib and
`collections.abc` types (`Mapping`, `Sequence`) — **never** `pandas`/`pyarrow`/
`duckdb`/`pandera` objects/types. Two operations cover what the consumers need:

```python
from collections.abc import Mapping, Sequence
from typing import Protocol

Row = Mapping[str, object]

class MedallionStore(Protocol):
    def write(
        self,
        *,
        layer: str,
        table: str,
        rows: Sequence[Row],
        overwrite: bool = False,
    ) -> None: ...

    def read(
        self,
        *,
        layer: str,
        table: str,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Row]: ...
```

Rationale for the signature:

- **Rows are `Sequence[Mapping[str, object]]`** (plain dict-like records), not
  DataFrames. The adapter materializes them into a `pyarrow`/`pandas` table and
  validates against the bronze `pandera` schema for `(layer, table)`; the fake
  keeps them in memory. Neither leaks a dataframe type across the port.
- **`write` is append-only with logical-PK collision detection.** Re-writing a
  row whose logical PK already exists raises `DuplicateKeyError`
  (`ApplicationError` subclass, ADR-local) unless `overwrite=True`. The logical
  PK and the partition scheme per `(layer, table)` are defined by the bronze
  schema registry (ADR 2.1.0001), not chosen by the caller — the caller does not
  pass partition columns explicitly; the store derives the Hive path
  (`asset=…/year=…`) from the row + schema.
- **`read` returns rows filtered by partition.** `filters` is a partition
  predicate (e.g. `{"asset": "AAPL"}`, optionally `year`); the adapter pushes it
  down to DuckDB so only the matching partition files are scanned (partition
  pruning) — it never loads the whole dataset. Returning `Sequence[Row]` keeps
  the dataframe inside the adapter.
- **`layer`/`table` are `str`** (`"bronze"` + `"candle"`/`"news"`/
  `"fundamental"`). Validating that a `(layer, table)` pair is known is the
  adapter's job (unknown pair → error, concept §6).

The exact translation to `pyarrow` writes, `duckdb` SQL with partition pruning,
and `pandera` validation is **adapter-internal**.

## Alternatives considered

### Alternative A — ABC mirroring the old AnalyticsRunRepository (dim/fact methods)

- **Description:** Port a class hierarchy (`ABC`) with one method per medallion
  table (`upsert_dim_run`, `append_fact_oos_predictions`, …), as in
  `interfaces/analytics_run_repository.py`.
- **Pros:** 1:1 with the prior project's mental model; tables are explicit.
- **Cons:** Couples the application to the full warehouse table catalog; every
  new table changes the port; uses an `ABC` where this project mandates a
  structural `Protocol`; far larger surface than the consumers need; leaks the
  medallion schema into `application`.
- **Why rejected:** Violates the Protocol-not-ABC posture and the
  minimal-and-swappable principle. A single generic `write/read(layer, table)`
  with a schema registry keeps the table catalog inside the adapter while
  preserving the append-only/dedup semantics as a contract invariant.

### Alternative B — Pass DataFrames (pandas/pyarrow) through the port

- **Description:** `write(layer, table, df: pandas.DataFrame)` /
  `read(...) -> pandas.DataFrame`.
- **Pros:** Less marshalling code in the adapter; callers that already hold a
  DataFrame pass it straight through.
- **Cons:** `import pandas`/`pyarrow` would cross into `application`; breaks
  swappability and the layer gate; the fake would have to depend on pandas; the
  consumers (use cases in 2.2/2.3) would become pandas-coupled at the
  application layer.
- **Why rejected:** Directly violates the layer-purity invariant; the new
  `import-linter` contract for `application` (mirroring `tracker-no-mlflow-leak`)
  would (correctly) fail.

### Alternative C — Do nothing / no port (call pyarrow/duckdb directly)

- **Why not acceptable:** Use cases would depend on `pyarrow`/`duckdb`,
  untestable without real files, non-swappable — defeats the hexagonal
  foundation Step 1 established and that this Stage is the first to exercise with
  a real out-adapter.

## Consequences

### Positive

- Application and use cases depend only on a tiny, stdlib-typed `Protocol`; the
  store is swappable (a future object-store/Delta backend is a new adapter) and
  fakeable.
- A single contract test guarantees fake↔real parity, including append-only,
  collision-by-logical-PK, partition filtering, and schema round-trip.
- The port surface matches exactly what 2.2/2.3 need — no speculative table API.

### Negative

- The adapter carries marshalling glue (rows ↔ Arrow/pandas tables, schema
  lookup, Hive path derivation) instead of passing DataFrames through.
- `Sequence[Mapping]` is less ergonomic than a DataFrame for very large reads;
  acceptable for the pilot (single-asset, daily-frequency data) and revisable
  under a new ADR if a streaming/columnar read becomes necessary.

### Neutral / trade-offs accepted

- A deliberately small surface now (`write`/`read` only). No `delete`, no schema
  migration, no transactions across tables — these grow under new ADRs if a
  consumer needs them.

## Implementation notes

- The fake (`tests/fakes/shared/fake_medallion_store.py`) keeps an in-memory
  `dict[(layer, table, partition-key) -> list[Row]]`, enforces append-only +
  `DuplicateKeyError` by recomputing logical-PK tuples, and filters on `read` by
  the same partition predicate the adapter prunes on.
- The real adapter (`ParquetMedallionStore`) is instantiated **only** in
  `composition_root`; `ApplicationDependencies` exposes the field typed by the
  port `MedallionStore`, never the concrete.
- Operating on an unknown `(layer, table)` pair, or reading a missing dataset,
  are error conditions documented in concept.md §6.

## References

- Related ADRs:
  [2.1.0001 — medallion partition + bronze schemas](./2_1_0001-medallion-partition-and-bronze-schemas.md);
  [1.5.0002 — ExperimentTracker port shape](./1_5_0002-experiment-tracker-port-shape.md)
  (same Protocol-not-ABC, no-leak posture);
  [0.0.0021 — per-unit contract tests with oracle](./0_0_0021-per-unit-contract-tests-with-oracle.md).
- Overview §11 — `0.0.0022` (engine de dados = pandas + duckdb).
- Conversation/issue: GitHub issue #15.
- Old repo: `financial-time-series-forecasting/src/interfaces/analytics_run_repository.py:11`
  (ABC — NOT replicated, replaced by Protocol) and
  `.../adapters/parquet_analytics_run_repository.py:103-139,155-168`
  (append-only + `DuplicateKeyError` + batch-per-partition — semantics migrated
  here from a table-shaped ABC to a generic `(layer, table)` Protocol).
