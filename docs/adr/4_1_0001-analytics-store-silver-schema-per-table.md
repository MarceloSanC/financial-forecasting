---
title: ADR 4.1.0001 — Decompose the analytics silver store into one schema module per table + registry
description: Architecture Decision Record
when-use: Reference whenever adding, changing, or deferring an analytics silver table, or before reintroducing a monolithic schema file
keywords: [adr, analytics-store, silver, schema-per-table, pandera, registry, deferred-tables]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: 4.1.0001
decision: Each analytics silver table gets its own schema module (SilverTable + pandera) wired through a SILVER_REGISTRY keyed by (layer, table), defining only the 5 tables consumed by Steps 1–4 and deferring 8 others.
context_stage: 4.1-silver-schema-per-table
bounded_context: analytics_store
---

# ADR 4.1.0001 — Decompose the analytics silver store into one schema module per table + registry

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

The previous repository concentrated **13 analytics tables in a single
`analytics_store_schema.py` file of 772 LOC**
(`financial-time-series-forecasting/src/infrastructure/schemas/analytics_store_schema.py`),
with one `AnalyticsTableSchema` dataclass (:143-152), all table definitions
inlined, a hand-rolled `validate_table_payload` (:735-772), and a flat
`ANALYTICS_TABLE_SCHEMAS` registry (:674-691). Changing one table meant
reopening the monolith; the validation path was bespoke string/dtype checking
rather than a validated library.

This project already proved a better pattern in Stage 2.1 (bronze): a frozen
`BronzeTable` dataclass pairing a `pandera.DataFrameSchema` with its
logical-PK/partition metadata, plus a `BRONZE_REGISTRY[(layer, table)]` over
which the `ParquetMedallionStore` dispatches, with `pandera` confined to the
adapter by the `store-no-storage-leak` import-linter contract (ADR 2.1.0002).

Forces:

- **Roadmap DoD (Stage 4.1):** "cada tabela silver tem schema próprio +
  `schema_version` + PK declarada; **nenhum mega-schema**".
- **Consistency:** a second, divergent schema-container pattern in the same
  codebase would raise cognitive load and risk drift from LAYOUT.md.
- **Downstream dispatch:** Stage 4.2 (`AnalyticsRepository`) must route writes
  per table without hard-coding each table — a registry is the seam.
- **Scope discipline (ledger §B 4.1):** only the tables consumed by Steps 1–4
  should be defined now; the rest are speculative until Steps 5/7.

## Decision

Model the analytics silver store as **one Python module per table** under
`features/analytics_store/adapters/out/parquet/schemas/`
(`dim_run.py`, `fact_config.py`, `fact_oos_predictions.py`,
`fact_split_metrics.py`, `fact_failures.py`), each exporting a frozen
`SilverTable` (`{name, schema_version, logical_pk, partition_by,
update_policy, schema}`) that pairs a `pandera.DataFrameSchema` (`strict=True`,
`coerce=False`) with its metadata — mirroring `BronzeTable` from Stage 2.1.
`silver_table.py` holds the dataclass; `silver_registry.py` holds
`SILVER_REGISTRY: Mapping[("silver", <table>), SilverTable]` mirroring
`BRONZE_REGISTRY`.

**Scope of tables (ledger §B 4.1):** define **only** the 5 tables consumed by
Steps 1–4 — `dim_run` (upsert), `fact_config`, `fact_oos_predictions`,
`fact_split_metrics`, `fact_failures` (all append-only). **Defer** the
following 8 tables to Steps 5/7, recording them here so the context is not
lost: `inference_runs`, `inference_predictions`, `feature_contrib_local`,
`epoch_metrics` (old `fact_epoch_metrics`), `model_artifacts` (old
`fact_model_artifacts`), `bridge_run_features`, `split_timestamps_ref`,
`fact_run_snapshot`. They serve inference/contribution/epoch concerns outside
the confirmatory scope of Steps 1–4; creating them now would be schema without
a consumer.

`pandera`/`pandas` live **only** in the adapter; the `store-no-storage-leak`
contract is extended to `analytics_store.{application,domain}` so a leak fails
the build.

## Alternatives considered

### Alternative A — Port the monolithic 772-LOC single-file schema as-is

- **Description:** Copy `analytics_store_schema.py` (all 13 tables + manual
  validator) into the new BC, lightly adapted.
- **Pros:** Fastest port; one file to read.
- **Cons:** Violates the explicit Roadmap DoD ("nenhum mega-schema"); carries
  the speculative 8 tables with no consumer; keeps bespoke validation instead
  of `pandera`; diverges from the proven 2.1 pattern.
- **Why rejected:** Directly contradicts the DoD and reproduces the
  anti-pattern this Stage exists to correct.

### Alternative B — One module per table, but no registry (import each table directly)

- **Description:** Per-table modules, but consumers import `DIM_RUN`,
  `FACT_CONFIG`, … directly with no `SILVER_REGISTRY`.
- **Pros:** Slightly less indirection.
- **Cons:** Stage 4.2's repository would hard-code knowledge of every table to
  dispatch by `(layer, table)`; diverges from `BRONZE_REGISTRY`, which already
  proved the dispatch seam.
- **Why rejected:** The registry is cheap and is the exact seam 4.2 needs;
  omitting it just defers the cost to 4.2 with no saving.

### Alternative C — Do nothing / status quo

- **Description:** Leave the analytics store undefined until 4.2 needs it.
- **Why rejected:** 4.2 (repository) and 4.3 (persister) both depend on the
  schema contract; without it, the whole Step 4 is blocked. The contract is the
  unit of value this Stage delivers.

## Consequences

### Positive

- Each table evolves in isolation; `schema_version` bump is local to its
  module.
- Consistent with the bronze pattern (2.1) — one mental model across BCs.
- `SILVER_REGISTRY` gives 4.2 uniform dispatch without table-by-table coupling.
- `pandera` validation replaces the old hand-rolled validator; the 6 old tests
  port to `pandera`-based valid/invalid payload tests.

### Negative

- More files (5 table modules + `silver_table.py` + `silver_registry.py`) vs
  one — slightly more navigation, mitigated by the registry as a single entry
  point.

### Neutral / trade-offs accepted

- The 8 deferred tables are intentionally absent; reintroducing any requires a
  new Stage and (if its shape is non-trivial) its own ADR.

## Implementation notes

- Mirror `shared/adapters/out/parquet/schemas/bronze_schemas.py`: `_UTC_DT`
  literal where applicable, `strict=True`, `coerce=False`, frozen dataclass.
- Fingerprint columns (`config_signature`, `split_fingerprint`,
  `dataset_fingerprint`) and `run_id` are stored as `string` — never recomputed
  here (Stage 1.4 owns them).
- `fact_oos_predictions` uses the LONG quantile format — see
  [ADR 4.1.0002](./4_1_0002-fact-oos-predictions-long-quantile-format.md).

## References

- Related ADRs: [2.1.0002](./2_1_0002-medallion-store-port-shape.md) (port
  shape / `store-no-storage-leak`),
  [2.1.0001](./2_1_0001-medallion-partition-and-bronze-schemas.md) (BronzeTable
  pattern), [1.3.0001](./1_3_0001-import-linter-as-architecture-fitness-function.md)
  (import-linter as fitness function),
  [4.1.0002](./4_1_0002-fact-oos-predictions-long-quantile-format.md).
- External / repo: old
  `financial-time-series-forecasting/src/infrastructure/schemas/analytics_store_schema.py`
  (:143-152, :199-201, :674-691, :735-772).
- Decision ledger: §B 4.1 (5 defined / 8 deferred).
