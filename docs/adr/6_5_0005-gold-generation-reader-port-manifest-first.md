---
title: ADR 6.5.0005 — The gold is read through a consumer port GoldGenerationReader, implemented by the ParquetGoldStore that owns the layout; the reader reads MANIFEST.json first, rebuilds the manifest with the inverse of its single serialization, reads each table as one file without hive partitioning, takes zero-row tables from rows_by_table, and refuses a partition without manifest or with status BLOCKED
description: Architecture Decision Record
when-use: Reference when reading gold tables from any consumer (6.5 scorecard, 8.1, 8.3), when asking why the reader lives in the same adapter as the writer, how an empty table is read, or what a BLOCKED or missing generation does to the scorecard
keywords: [adr, evaluation, gold, reader, port, manifest, hive-partitioning, pyarrow, duckdb, empty-table, blocked, parquet-gold-store]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-29
adr_id: 6.5.0005
decision: A port-out GoldGenerationReader.read(partition) -> GoldGeneration (application/ports/out, owned by evaluation as consumer) is satisfied by ParquetGoldStore through a new read_generation method, keeping the gold layout and the manifest file name in one adapter; the reader loads current/MANIFEST.json first (GoldManifestNotFoundError if absent), rebuilds GoldManifest with GoldManifest.from_mapping — the inverse of as_mapping, next to it, round-trip tested — and returns the manifest plus one GoldTable per entry of rows_by_table, read as a single file with pyarrow partitioning=None (zero-row tables returned empty from the manifest count, not from the file schema); a table named in rows_by_table but missing on disk, or a row count different from the manifest, raises GoldGenerationCorruptError; the reader returns BLOCKED generations as they are and BuildConfirmatoryScorecard raises GoldNotReadyError for them.
context_stage: 6.5-preregistration-and-scorecard
bounded_context: evaluation
---

# ADR 6.5.0005 — Gold generation reader, manifest first

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

ADR 6.4.0005 publishes a cohort's gold as one generation with `MANIFEST.json`
written last, and says the reader "uses a partition only if
`current/MANIFEST.json` exists and reads it before the tables". Stage 6.4 found
(technical 6.4 §7, `[finding]` Task 08) that `pyarrow.parquet.read_table` infers
hive partitions from the `asset=`/`parent_sweep_id=` path segments and fails to
merge them with the row columns of the same name, and that a zero-row table is
written with an empty schema. The roadmap §Stage 6.5 note repeats the three
rules. The `GoldStore` port docstring names 6.5 as the reader.

The rules are those of **every** gold reader (6.5 scorecard, 8.1, 8.3): kept in
each consumer they would be written several times (issue #127, reflection 1c).
The layout (`gold/asset=<a>/parent_sweep_id=<p>/current/`, file names, manifest
name) already has one owner: `ParquetGoldStore` (`partition_root`,
`current_dir`, `MANIFEST_NAME`). The manifest has one serialization,
`GoldManifest.as_mapping()`.

## Decision

`[decision:C] 6.5-C4 — shape and home of the gold reader`
`Escolha: consumer port GoldGenerationReader satisfied by ParquetGoldStore.read_generation; manifest first; GoldManifest.from_mapping as the inverse of as_mapping; no hive inference; zero-row tables from rows_by_table; BLOCKED returned and refused by the use case · Alternativas: separate ParquetGoldReader class; DuckDB SQL reader; reader per consumer · Degrau (C): 1 (ADR 6.4.0005 reader rule; technical 6.4 §7 finding Task 08; LAYOUT §4 one owner) e 5`
`Base: ADR 6.4.0005 Decision; technical 6.4 §7 [finding] Task 08 (ArrowTypeError "Unable to merge: Field asset has incompatible types")`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

1. **Port** `GoldGenerationReader` (`application/ports/out/gold_generation_reader.py`):
   `read(*, partition: GoldPartition) -> GoldGeneration`. `GoldGeneration`
   (DTO, `application/dtos/`): `manifest: GoldManifest`,
   `tables: Mapping[str, GoldTable]` (one per `rows_by_table` key).
2. **Real:** `ParquetGoldStore.read_generation` in the existing module (writer
   and reader of one layout in one adapter; the class satisfies two ports, as
   `ParquetAnalyticsRepository` satisfies `SilverTableReader`). Reads with
   `pyarrow.parquet.read_table(path, partitioning=None)`; builds each
   `GoldTable` with the key the builders declared (the key tuples move from the
   builder modules to one public constant per table so writer and reader share
   them).
3. **Manifest inverse:** `GoldManifest.from_mapping(mapping)` and
   `RefreshParameters.from_mapping(mapping)` next to `as_mapping()` in
   `dtos/refresh_gold.py`; property test: `from_mapping(as_mapping(m)) == m`.
   The reader never interprets JSON keys itself.
4. **Errors:** no `current/MANIFEST.json` → `GoldManifestNotFoundError`
   (partition never published or mid-swap); a `rows_by_table` table absent on
   disk, or a row count that differs → `GoldGenerationCorruptError`. A
   `BLOCKED` manifest is returned as is (8.3 may want to show why); the scorecard
   refuses it with `GoldNotReadyError` ("BLOCKED não vira scorecard").
5. **Fake + contract:** `InMemoryGoldStore` gains the same `read_generation`;
   the contract suite runs `[fake, real]`, publishing through `publish` and
   reading back, including a zero-row table, a `BLOCKED` generation and a missing
   manifest.

## Alternatives considered

### Alternative A — A separate `ParquetGoldReader` class

- **Why rejected:** would repeat the layout and manifest name, or import them
  from the writer module (adapter → adapter, LAYOUT §3).

### Alternative B — Read through DuckDB SQL

- **Pros:** DuckDB is the gold's query engine (ADR 0.0.0022).
- **Cons:** the scorecard needs rows, not queries; one more engine in the path
  for the same file reads; `hive_partitioning = false` would still be needed.
- **Why rejected:** degree 5; ad hoc DuckDB queries stay available to 8.3.

### Alternative C — Each consumer reads its own way

- **Why rejected:** the three rules would be written per consumer.

## Consequences

### Positive

- One place knows the gold layout; every consumer inherits the manifest-first,
  no-hive and empty-table rules.

### Negative

- `ParquetGoldStore` grows a read path; the port-coverage baseline counts one
  more port with one real.

## References

- Related ADRs: [0.0.0022](./0_0_0022-data-engine-pandas-duckdb.md), [0.0.0053](./0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md), [6.4.0005](./6_4_0005-gold-full-refresh-per-cohort-partition.md).
- Technical 6.4 §7 `[finding]` Task 08; roadmap §Stage 6.5 "Leitura do gold (nota da 6.4)".
- Issue [#127](https://github.com/MarceloSanC/financial-forecasting/issues/127) (fork C4).
