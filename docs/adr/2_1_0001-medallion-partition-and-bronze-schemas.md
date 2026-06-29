---
title: ADR 2.1.0001 — Hive partition convention (asset/table/year, append-only) and bronze pandera schemas mirroring the real raw data
description: Architecture Decision Record
when-use: Reference before changing the medallion partition layout, the append-only policy on facts, the logical-PK definitions, or the bronze schema dtypes for candle/news/fundamental
keywords: [adr, medallion, hive-partition, append-only, logical-pk, pandera, bronze, candle, news, fundamental, dtypes, reported-date-nullable]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "2.1.0001"
decision: Partition bronze datasets Hive-style as asset=<asset>/<table>/year=<year>, append-only on facts with logical-PK collision detection, and define pandera bronze schemas for candle/news/fundamental that mirror the exact dtypes of the existing raw Parquet (OHLC float32, volume int64, fundamental float64, datetimes UTC, reported_date nullable)
context_stage: 2.1-medallion-storage-contracts
---

# ADR 2.1.0001 — Hive partition convention and bronze pandera schemas mirroring the real raw data

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

Stage 2.1 builds the first real medallion out-adapter. Two things have to be
fixed now because every later Stage that writes or reads bronze depends on them:

1. **A partition layout** that scales to multi-asset while keeping the pilot
   (AAPL) simple, and an **update policy** for facts.
2. **Bronze schema contracts** (via `pandera`) for the three raw tables —
   `candle`, `news`, `fundamental` — so that Stages 2.2/2.3, which re-use the
   raw Parquet already produced by the prior project, can read it back without
   dtype drift.

Forces and constraints:

- **Ledger §B (2.1)** pre-declares: Hive `asset/[feature_set]/year`,
  append-only, pandera schemas for candle/news/fundamental with the old repo's
  columns/dtypes.
- **The old repo's partition layout** is proven:
  `parquet_analytics_run_repository.py:69-73` writes
  `<table>/asset=…/<high-card-key>=…/year=…/<table>.parquet`; append-only with
  collision detection lives at `:103-139`; batch-per-partition at `:155-168`;
  `_safe_partition` (None/empty → sentinel) at `:28-33`. The old bronze dtypes
  are in `candle_parquet_schema.py`, `news_parquet_schema.py`,
  `fundamental_parquet_schema.py`.
- **The real raw data on disk was inspected** (not assumed) in the old repo:
  - `data/raw/market/candles/AAPL/candles_AAPL_1d.parquet` — 4024 rows;
    `open/high/low/close` `float32`, `volume` `int64`, `timestamp`
    `datetime64[ns, UTC]`.
  - `data/raw/news/AAPL/news_AAPL.parquet` — 6921 rows; 8 string columns
    (`asset_id, article_id, headline, summary, source, url, language`) +
    `published_at` `datetime64[ns, UTC]`.
  - `data/processed/fundamentals/AAPL/fundamentals_AAPL.parquet` — 81 rows;
    5 numeric columns `float64`, `fiscal_date_end`/`reported_date`
    `datetime64[ns, UTC]`, **`reported_date` has 17/81 `NaT`** (real, not
    hypothetical).
- **The partition engine** is `pandas + duckdb` (overview §11 / ADR `0.0.0022`):
  writes via `pyarrow`, reads with DuckDB partition pruning.

## Decision

### Partition layout

Bronze datasets are written Hive-style under the medallion root:

```
<medallion-root>/bronze/<table>/asset=<asset>/year=<year>/<table>.parquet
```

The middle key is the **table/layer** itself (the high-cardinality middle key in
the old analytics-store generalizes, for bronze facts, to the table name); the
partition columns are `asset` and `year`. `year` is derived from the table's
time anchor: `timestamp.year` for candle, `published_at.year` for news,
`fiscal_date_end.year` for fundamental. Partition values are sanitized like the
old `_safe_partition` (None/empty → a stable sentinel) so a missing partition
value never produces a broken path.

### Update policy — append-only with logical-PK collision detection

Facts are **append-only**. On `write`, the store recomputes the logical-PK
tuples of the incoming rows against those already stored in the target partition
file(s); a collision raises `DuplicateKeyError` (`ApplicationError` subclass)
unless `overwrite=True` is passed (then the colliding rows are replaced). This is
the old `_write_with_overwrite_policy` semantic, now a contract invariant of the
port (ADR 2.1.0002), not a Parquet detail. Writes are batched per partition path
(bucket rows by destination file) to avoid row-by-row Parquet rewrites.

Logical PKs:

| table | logical PK | partition_by | update policy |
|---|---|---|---|
| `candle` | `(asset, timestamp)` | `(asset, year)` | append-only |
| `news` | `(asset_id, article_id)` | `(asset, year)` | append-only |
| `fundamental` | `(asset_id, report_type, fiscal_date_end)` | `(asset, year)` | append-only |

### Bronze pandera schemas (mirror the real dtypes exactly)

`DataFrameSchema`s live **only** in the adapter
(`shared/adapters/out/parquet/schemas/bronze_schemas.py`) and mirror the dtypes
verified on disk:

- **candle:** `timestamp` `datetime64[ns, UTC]`; `open/high/low/close` `float32`;
  `volume` `int64`. All non-nullable.
- **news:** `asset_id, article_id, headline, summary, source, url, language`
  strings; `published_at` `datetime64[ns, UTC]`. Non-nullable.
- **fundamental:** `asset_id, report_type, source` strings; `fiscal_date_end`
  `datetime64[ns, UTC]` (non-nullable); **`reported_date` `datetime64[ns, UTC]`
  NULLABLE** (NaT allowed — the real data has 17/81 NaT); `revenue, net_income,
  operating_cash_flow, total_shareholder_equity, total_liabilities` `float64`.

The schemas formalize, in `pandera`, the column-set/dtype intent the old repo
expressed loosely via the `*_PARQUET_DTYPES` dicts and an ad-hoc set-difference
column check (`parquet_candle_repository.py:75-83`).

## Alternatives considered

### Alternative A — Single flat directory per table (no Hive partitions)

- **Description:** One Parquet file (or directory) per table, no `asset=`/
  `year=` partitioning.
- **Pros:** Simplest path layout; trivial to write.
- **Cons:** No partition pruning on read (DuckDB would scan everything); does not
  scale to multi-asset; loses the proven old layout.
- **Why rejected:** Defeats the DoD ("leitura por partição filtra por asset")
  and the multi-asset-ready goal; the cost of Hive partitioning is near-zero
  given the old code already demonstrates it.

### Alternative B — Pyarrow native dataset partitioning (`partition_cols=`)

- **Description:** Let `pyarrow.dataset`/`write_to_dataset` own the partition
  layout and discovery instead of deriving paths ourselves.
- **Pros:** Less path-building code; standard Hive discovery.
- **Cons:** Append-only-with-logical-PK-collision is not a native pyarrow
  primitive — we still need the read-existing/detect-collision/merge cycle, so
  pyarrow-managed partitioning fights the per-partition collision check; harder
  to control the exact `<table>.parquet` filename the old repo used; less
  control for batch-per-partition.
- **Why rejected:** The collision policy is the load-bearing semantic; explicit
  path derivation (mirroring the old `_*_path` helpers) keeps that policy simple
  and testable. Pyarrow still does the actual file write.

### Alternative C — Loosely-typed schema check (set-difference of columns), no pandera

- **Description:** Keep the old style (`parquet_candle_repository.py:75-83`):
  assert the column set matches, ignore dtypes.
- **Pros:** No new dependency for validation logic.
- **Cons:** Does not catch dtype drift (e.g. `float64` vs `float32`, tz-naive vs
  UTC) — exactly the failure that would silently break 2.2/2.3 reading the raw;
  no nullability contract (`reported_date`).
- **Why rejected:** Dtype/nullability fidelity is the whole point of mirroring
  the real data; `pandera` is already an adopted dependency (overview §11) and
  gives a declarative, testable contract.

### Alternative D — Do nothing / status quo

- **Why not acceptable:** Without a fixed partition convention and bronze schema
  contracts, 2.2/2.3 would each invent their own, drift apart, and the
  multi-asset/append-only goals of Step 2 would have no foundation.

## Consequences

### Positive

- Multi-asset-ready layout with partition pruning on read, proven by the old
  repo; append-only protects facts from silent overwrite.
- Bronze schemas pin the exact dtypes of the existing raw, so 2.2/2.3 read it
  back with zero drift; `reported_date` nullability is contractually explicit.
- The collision policy is a single, testable invariant shared by fake and real.

### Negative

- Explicit path derivation per table is a little code to maintain (vs delegating
  to pyarrow dataset discovery).
- `float32` OHLC limits numeric precision; accepted because it matches the
  source-of-truth raw and downstream features were built on it in the old repo.

### Neutral / trade-offs accepted

- The `<table>` middle key (rather than a feature_set/sweep key as in the old
  analytics-store) is the right generalization for bronze facts; silver/gold may
  introduce richer middle keys under their own ADRs (out of scope here).
- `year` partition granularity (not month/day) — adequate for daily candles and
  low-volume fundamentals; revisable if a higher-frequency table appears.

## Implementation notes

- A small frozen dataclass per table (mirroring the old
  `AnalyticsTableSchema`: `logical_pk`/`partition_by`/`update_policy`) pairs the
  `pandera` `DataFrameSchema` with its PK/partition metadata, forming the
  `(layer, table)` registry the port (ADR 2.1.0002) dispatches on.
- The integration test asserts the real Hive directory structure
  (`asset=…/year=…`), dtype round-trip, append-only collision, and that a
  `{"asset": …}` filter returns only that asset.

## References

- Related ADRs:
  [2.1.0002 — MedallionStore port shape](./2_1_0002-medallion-store-port-shape.md);
  [0.0.0021 — per-unit contract tests with oracle](./0_0_0021-per-unit-contract-tests-with-oracle.md).
- Overview §11 — `0.0.0022` (engine de dados = pandas + duckdb).
- Ledger §B (2.1): Hive `asset/[feature_set]/year`, append-only, pandera bronze.
- Conversation/issue: GitHub issue #15.
- Old repo:
  `financial-time-series-forecasting/src/adapters/parquet_analytics_run_repository.py:28-33,69-73,103-139,155-168`
  (sanitized partition values, Hive path, append-only collision, batch-per-partition);
  `src/infrastructure/schemas/{candle,news,fundamental}_parquet_schema.py` (dtypes);
  `src/infrastructure/schemas/analytics_store_schema.py:143-152`
  (`AnalyticsTableSchema` frozen dataclass — concept formalized here for bronze);
  `src/adapters/parquet_candle_repository.py:75-83` (set-difference column check — replaced by pandera).
- Real data inspected: `data/raw/market/candles/AAPL/candles_AAPL_1d.parquet`,
  `data/raw/news/AAPL/news_AAPL.parquet`,
  `data/processed/fundamentals/AAPL/fundamentals_AAPL.parquet`.
