---
title: ADR 6.5.0005 — The gold is read through a consumer port GoldGenerationReader.read_generation, implemented by the ParquetGoldStore that owns the layout (fake InMemoryGoldGenerationReader); the gold schema (table names, keys, consumed columns) and the assembly of a read generation have one owner in the application; the adapter only does I/O, manifest first, without hive partitioning
description: Architecture Decision Record
when-use: Reference when reading gold tables from any consumer (6.5 scorecard, 8.1, 8.3), when asking who owns the gold table names, keys and columns, why the reader lives in the same adapter as the writer, how an empty table is read, or what a BLOCKED or missing generation does to the scorecard
keywords: [adr, evaluation, gold, reader, port, manifest, gold-schema, hive-partitioning, pyarrow, duckdb, empty-table, blocked, parquet-gold-store, port-coverage]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-30
adr_id: 6.5.0005
decision: A port-out GoldGenerationReader with one method read_generation(*, partition) -> GoldGeneration lives in application/ports/out/gold_generation_reader.py, which re-exports GoldManifestNotFoundError and GoldGenerationCorruptError defined in dtos/refresh_gold.py next to GoldGeneration.from_stored (no import cycle); its real is ParquetGoldStore.read_generation (the module cites the port by name) and its fake is InMemoryGoldGenerationReader in tests/fakes/features/evaluation/; a new application module dtos/gold_schema.py is the single owner of each gold table's name, key and the columns consumers read, imported by the five builders and by the reader; GoldGeneration.from_stored(manifest_mapping, rows_by_table) in the DTO module is the single assembly of a read generation — it rebuilds the manifest with GoldManifest.from_mapping (inverse of as_mapping, refusing a top-level preregistration_ref that differs from the parameters'), builds the GoldTables with the schema's keys, fills zero-row tables from rows_by_table and runs check_generation — so fake and real share it; the adapter only reads files (MANIFEST.json first, pyarrow partitioning=None); a BLOCKED generation is returned and refused by the use case with GoldNotReadyError.
context_stage: 6.5-preregistration-and-scorecard
bounded_context: evaluation
---

# ADR 6.5.0005 — Gold generation reader, schema owner, manifest first

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — revised on 2026-09-30 after Checkpoint A round 1 (A-A2 port shape
and fake name; A-M1 schema owner; A-M2 single assembly; B5, B7).

## Context

ADR 6.4.0005 publishes a cohort's gold as one generation with `MANIFEST.json`
written last, and says the reader "uses a partition only if
`current/MANIFEST.json` exists and reads it before the tables". Stage 6.4 found
(technical 6.4 §7, `[finding]` Task 08) that `pyarrow.parquet.read_table` infers
hive partitions from the `asset=`/`parent_sweep_id=` path segments and fails to
merge them with the row columns of the same name, and that a zero-row table is
written with an empty schema. The roadmap §Stage 6.5 note repeats the rules.

Facts from the code (Checkpoint A round 1):

- The table keys live as private `_KEY` constants in each builder module
  (`adapters/out/duckdb/gold_builders/*.py`); the columns a consumer reads have no
  owner at all.
- `check_port_coverage` recognizes a fake only by class name `Fake<Port>` or
  `InMemory<Port>` (`scripts/check_port_coverage.py`, `fake_names`) and a real
  only if its module cites the port by name (`real_adapter_classes`); a Protocol
  method `read` would not match a real method `read_generation` structurally.
- `check_generation` (`dtos/refresh_gold.py`) is already the single coherence
  check of a generation, used by both stores on write.

The rules are those of **every** gold reader (6.5, 8.1, 8.3). The layout already
has one owner: `ParquetGoldStore` (`partition_root`, `current_dir`,
`MANIFEST_NAME`).

## Decision

`[decision:C] 6.5-C4 — shape and home of the gold reader`
`Escolha: port GoldGenerationReader.read_generation; real ParquetGoldStore.read_generation, fake InMemoryGoldGenerationReader; gold_schema.py owns names/keys/columns; GoldGeneration.from_stored is the one assembly (reusing check_generation); adapter does only file I/O · Alternativas: separate ParquetGoldReader class; DuckDB SQL reader; reader per consumer; parsing in each store · Degrau (C): 1 (ADR 6.4.0005 reader rule; technical 6.4 §7 finding Task 08; LAYOUT §4 one owner) e 5`
`Base: ADR 6.4.0005 Decision; technical 6.4 §7 [finding] Task 08; scripts/check_port_coverage.py fake_names/real_adapter_classes`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

1. **Port** (`application/ports/out/gold_generation_reader.py`):
   `GoldGenerationReader.read_generation(*, partition: GoldPartition) ->
   GoldGeneration`; the module re-exports the two errors of item 5.
2. **Schema owner** (`application/dtos/gold_schema.py`): for each of the five
   tables, its name, its key tuple and the columns a consumer reads. The builders
   import name and key from it (their private `_KEY` constants disappear); the
   reader and the scorecard's evidence mapper read columns only through it.
3. **Single assembly:** `GoldGeneration.from_stored(manifest: Mapping,
   rows_by_table: Mapping[str, Sequence[Row]]) -> GoldGeneration` in the DTO
   module:
   - `GoldManifest.from_mapping` (with `RefreshParameters.from_mapping`), the
     inverse of `as_mapping`, next to it; it refuses a manifest whose top-level
     `preregistration_ref` differs from `parameters.preregistration_ref` (B5);
   - one `GoldTable` per `rows_by_table` key, built with the schema's key; a
     table listed with 0 rows is an empty table, whatever the file schema;
   - `check_generation` (existing) on the result.
   Fake and real both call it; neither parses JSON or builds tables itself.
4. **Real:** `ParquetGoldStore.read_generation` in the existing module (its
   docstring cites `GoldGenerationReader`): reads `current/MANIFEST.json`, then
   each listed table with `pyarrow.parquet.read_table(path, partitioning=None)`
   (to Python rows), and calls `from_stored`. **Fake:**
   `InMemoryGoldGenerationReader` in `tests/fakes/features/evaluation/`, holding
   published generations (it can be fed from an `InMemoryGoldStore`). The
   contract suite imports the fake and cites `ParquetGoldStore`, runs `[fake,
   real]` publishing and reading back, including a zero-row table, a column that
   is `None` in every row, a `BLOCKED` generation and a missing manifest (B7). The
   Parquet type of an all-`None` column (null vs int64) is forwarded to 8.3 as a
   reader concern for ad hoc DuckDB queries.
5. **Errors** (defined in `dtos/refresh_gold.py`, next to `from_stored`, which
   raises the second — so the DTO module never imports the port; re-exported by
   the port module for adapters and callers): no `current/MANIFEST.json` →
   `GoldManifestNotFoundError`; a listed table absent on disk, a row count that
   differs from `rows_by_table`, or rows that fail `check_generation` →
   `GoldGenerationCorruptError`. A `BLOCKED` manifest is returned as is (8.3 may
   show why); the scorecard refuses it with `GoldNotReadyError`.

## Alternatives considered

### Alternative A — A separate `ParquetGoldReader` class

- **Why rejected:** would repeat the layout and manifest name, or import them
  from the writer module (adapter → adapter, LAYOUT §3).

### Alternative B — Read through DuckDB SQL

- **Why rejected:** the scorecard needs rows, not queries; one more engine in the
  path; ad hoc DuckDB queries stay available to 8.3 (degree 5).

### Alternative C — Each store parses the manifest and builds tables

- **Why rejected:** two writings of the assembly (fake and real) that can drift
  (A-M2).

### Alternative D — Keys stay private in the builders; the reader repeats them

- **Why rejected:** a second writing of each key; no owner for the consumed
  columns (A-M1).

## Consequences

### Positive

- One place knows the layout (adapter), one the schema (application), one the
  assembly (DTO); every consumer inherits the manifest-first, no-hive and
  empty-table rules.
- The port-coverage gate counts the port with its real and fake without a
  baseline entry.

### Negative

- The five builders change their imports (a mechanical edit in 6.4 files).

## References

- Related ADRs: [0.0.0022](./0_0_0022-data-engine-pandas-duckdb.md), [0.0.0053](./0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md), [6.4.0005](./6_4_0005-gold-full-refresh-per-cohort-partition.md).
- Technical 6.4 §7 `[finding]` Task 08; roadmap §Stage 6.5 "Leitura do gold (nota da 6.4)".
- Issue [#127](https://github.com/MarceloSanC/financial-forecasting/issues/127) (fork C4); Checkpoint A round 1.
