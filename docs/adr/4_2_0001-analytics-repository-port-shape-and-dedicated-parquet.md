---
title: ADR 4.2.0001 — Generic AnalyticsRepository port (write/read by (layer, table)) backed by a dedicated Parquet adapter
description: Architecture Decision Record
when-use: Reference before changing the AnalyticsRepository signature, adding per-table methods, or considering reuse of ParquetMedallionStore for silver writes/reads
keywords: [adr, analytics-repository, port, protocol, parquet, silver, partition, append-only, upsert, medallion-store, dedicated-adapter, contract-test]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "4.2.0001"
decision: Define AnalyticsRepository as a generic write/read Protocol dispatching on SILVER_REGISTRY, implemented by a dedicated ParquetAnalyticsRepository that partitions by literal SilverTable.partition_by columns (1..3 levels) rather than reusing ParquetMedallionStore's anchor-derived asset/year partitioning
context_stage: 4.2-silver-repository
---

# ADR 4.2.0001 — Generic AnalyticsRepository port backed by a dedicated Parquet adapter

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

Stage 4.1 delivered the silver schema-as-contract: `SILVER_REGISTRY[("silver",
<table>)] -> SilverTable`, with five tables each carrying `logical_pk`,
`partition_by`, `update_policy`, `schema_version` and a `pandera`
`DataFrameSchema`. Stage 4.2 must add the write/read muscle on top of those
contracts: an out-port plus a Parquet adapter that writes append-only to the
four facts (upsert only for `dim_run`, or via an explicit flag), partitions in
Hive layout, validates `pandera` on write, and reads back with partition
pruning.

Two prior assets shape the decision and two concrete divergences forbid naive
reuse:

- **The MedallionStore precedent (2.1).** `MedallionStore` is a minimal
  structural `Protocol` (`write`/`read` by `(layer, table)`) over stdlib types,
  proven in production with a fake + a parametrized contract test (ADR 2.1.0002).
  Its adapter `ParquetMedallionStore` carries a tested dedup/overwrite engine
  (`_safe_partition`, `_pk_tuples`, per-partition dedup, DuckDB read with
  pruning).
- **The old repo (anti-pattern).** The prior project used a table-shaped
  `AnalyticsRunRepository` ABC with ~13 methods
  (`upsert_dim_run`/`append_fact_*`, `interfaces/analytics_run_repository.py:11`)
  and a dedicated `ParquetAnalyticsRunRepository` that had **no read** and no
  `parent_sweep_id` round-trip.
- **Divergence 1 — literal vs derived partitioning.** `ParquetMedallionStore`
  derives `year` from `meta.year_anchor` and partitions **only** by `asset/year`
  (`parquet_medallion_store.py:148-160`). The silver `SilverTable` deliberately
  has **no** `asset_col`/`year_anchor` (`silver_table.py:9-12`) and partitions by
  **literal payload columns** in 1..3 levels: `(asset,)` for `fact_failures`,
  `(asset, parent_sweep_id)` for `dim_run`/`fact_config`/`fact_split_metrics`,
  and `(asset, feature_set_name, year)` for `fact_oos_predictions` — where `year`
  is a literal `int64` column of the payload, not derived from a temporal anchor.
- **Divergence 2 — schema dispatch surface.** The application must not learn the
  warehouse table catalog; the registry from 4.1 already exists as the dispatch
  seam.

Forces: the project mandates structural `Protocol`s (not ABCs), application
tested with a fake, adapters validated by a contract test, and storage libraries
(`pandas`/`pyarrow`/`duckdb`/`pandera`) confined to the adapter
(`store-no-storage-leak`). The Stage 4.2 non-goal states the repository "persists
generic rows per table" — it must not own prediction semantics (4.3).

## Decision

**Port shape.** Define `AnalyticsRepository` as a **generic structural
`Protocol`** in `features/analytics_store/application/ports/out/analytics_repository.py`:

```python
from collections.abc import Mapping, Sequence
from typing import Protocol

Row = Mapping[str, object]

class AnalyticsRepository(Protocol):
    def write(
        self, *, layer: str, table: str,
        rows: Sequence[Row], allow_upsert: bool = False,
    ) -> None: ...

    def read(
        self, *, layer: str, table: str,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Row]: ...
```

Dispatch is by `SILVER_REGISTRY[("silver", <table>)]`; `update_policy` decides
append vs upsert, with `allow_upsert=True` forcing a conscious upsert. The
~13 per-table methods of the old ABC are dropped. This mirrors the
`MedallionStore` posture exactly (ADR 2.1.0002).

**Adapter shape.** Implement a **dedicated** `ParquetAnalyticsRepository`
(`features/analytics_store/adapters/out/parquet/`) that mirrors the
`ParquetMedallionStore` dedup/overwrite/read engine in *logic* but partitions
by the **literal columns** of `SilverTable.partition_by` (1..3 levels) and
**does not derive any temporal anchor**. It is **not** layered on top of
`ParquetMedallionStore` and does not import it. `data_root` is injected;
instantiation lives only in `composition_root`.

## Alternatives considered

### Alternative A — Per-table methods on the port (port the old ABC)

- **Description:** `upsert_dim_run`, `append_fact_oos_predictions`, … one method
  per silver table, as in the old `AnalyticsRunRepository` ABC.
- **Pros:** explicit per-table API; 1:1 with the prior mental model.
- **Cons:** every new table changes the port; couples application to the table
  catalog; uses an ABC where the project mandates a `Protocol`; far larger
  surface than the consumer (4.3) needs; the registry seam from 4.1 would go
  unused.
- **Why rejected:** Violates the Protocol-not-ABC and minimal-surface posture
  (same reasoning as ADR 2.1.0002 alternative A). A generic `write/read` plus the
  registry keeps the catalog inside the adapter while preserving append-only/
  upsert semantics as contract invariants.

### Alternative B — Reuse ParquetMedallionStore under the hood (compose, not duplicate)

- **Description:** Build `ParquetAnalyticsRepository` as a thin wrapper that
  delegates persistence to the existing `ParquetMedallionStore`.
- **Pros:** no copied dedup code; one storage engine to maintain.
- **Cons:** `ParquetMedallionStore` hardcodes anchor-derived `asset/year`
  partitioning (`parquet_medallion_store.py:148-160`) and reads `meta.asset_col`/
  `meta.year_anchor`, which `SilverTable` does not provide. Supporting silver's
  literal 1..3-level partitions (`(asset,)`, `(asset, parent_sweep_id)`,
  `(asset, feature_set_name, year)`) would require **refactoring the bronze
  store** and **coupling silver↔bronze**, so a change for silver could regress
  bronze ingestion (2.2/2.3).
- **Why rejected:** The coupling and refactor cost outweighs the ~40 lines of
  copied, already-tested dedup logic. A dedicated adapter decouples silver's
  evolution; the old repo was also dedicated.

### Alternative C — Generalize ParquetMedallionStore to literal partitions and share it

- **Description:** Extend `BronzeTable`/`SilverTable` to a common abstraction
  with optional literal `partition_by`, and make one store serve both layers.
- **Pros:** single store long-term; no duplication.
- **Cons:** introduces a shared partitioning abstraction across two BCs before a
  second consumer proves the shape; risks over-generalizing; touches a `done`,
  contract-tested adapter (2.1) under a Stage whose target is 4.2 only.
- **Why rejected:** Premature unification. If a third partitioning consumer
  appears, a future ADR can extract the common engine; for now keep it simple and
  swappable.

### Alternative D — Do nothing / call pyarrow+duckdb directly from the use case

- **Why not acceptable:** the 4.3 persister (and Step 5 baselines/trainers) would
  depend on `pyarrow`/`duckdb`, be untestable without real files and non-
  swappable — defeats the hexagonal foundation and the `store-no-storage-leak`
  gate.

## Consequences

### Positive

- Application/4.3 depend only on a tiny stdlib-typed `Protocol`; the repository is
  swappable and fakeable; a single contract test guarantees fake↔real parity
  (append-only, collision-by-PK, upsert, pruning, `parent_sweep_id` round-trip).
- Silver partitioning evolves independently of bronze; no silver↔bronze coupling.
- The port surface matches exactly what 4.3 needs — no speculative table API; the
  registry from 4.1 is the dispatch seam.

### Negative

- ~40 lines of dedup/overwrite logic are mirrored from `ParquetMedallionStore`
  rather than shared; a future bug fix in one engine must be considered for the
  other.
- The adapter carries marshalling glue (rows ↔ pandas tables, registry lookup,
  Hive path derivation over 1..3 literal levels) instead of delegating.

### Neutral / trade-offs accepted

- Deliberately small surface now (`write`/`read` only): no `delete`, no schema
  migration, no cross-table transactions — these grow under new ADRs if a
  consumer needs them.
- Two Parquet stores coexist (bronze `MedallionStore`, silver
  `AnalyticsRepository`); acceptable while their partitioning models differ.

## Implementation notes

- Mirror `_safe_partition` (None/empty → `__none__`), `_pk_tuples`, per-partition
  dedup + overwrite, and the DuckDB read with pruning + schema projection from
  `parquet_medallion_store.py`. Derive the Hive path from
  `SilverTable.partition_by` (1..3 `col=value` segments), not from arguments.
- Unknown `(layer, table)` → `ApplicationError` (mirror `MedallionStore._table`);
  do not let the registry `KeyError` escape raw.
- `read` re-translates the `__none__` sentinel back to `None` for
  `parent_sweep_id` (the old repo had no read; this Stage adds the round-trip).
- The `created_at_utc` write-time concern of `dim_run` is decided separately in
  [ADR 4.2.0002](./4_2_0002-created-at-utc-via-injected-clock.md).

## References

- Related ADRs:
  [2.1.0002 — MedallionStore port shape](./2_1_0002-medallion-store-port-shape.md)
  (same generic-Protocol-over-ABC, no-storage-leak posture);
  [4.1.0001 — silver schema per table](./4_1_0001-analytics-store-silver-schema-per-table.md)
  (the registry/`SilverTable` consumed here);
  [4.2.0002 — created_at_utc via injected Clock](./4_2_0002-created-at-utc-via-injected-clock.md);
  [0.0.0021 — per-unit contract tests with oracle](./0_0_0021-per-unit-contract-tests-with-oracle.md).
- Code: `shared/adapters/out/parquet/parquet_medallion_store.py:148-160,200-262`
  (anchor-derived partition + read with pruning — divergence/mirror reference);
  `features/analytics_store/adapters/out/parquet/schemas/silver_table.py:9-12`
  (no `asset_col`/`year_anchor`); `.../schemas/silver_registry.py` (dispatch seam).
- Conversation/issue: GitHub issue #36.
- Old repo: `financial-time-series-forecasting/src/interfaces/analytics_run_repository.py:11`
  (ABC, ~13 methods — NOT replicated);
  `.../src/adapters/parquet_analytics_run_repository.py:103-168` (dedup/overwrite/
  batch-per-partition engine — logic mirrored, generalized to registry dispatch).
