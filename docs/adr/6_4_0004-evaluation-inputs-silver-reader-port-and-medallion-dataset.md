---
title: ADR 6.4.0004 — RefreshGold reads silver through a consumer-owned SilverTableReader port and the realized target_return through the shared MedallionStore read-only dataset pair, fingerprinted with DatasetFingerprint; no realized-return port is created
description: Architecture Decision Record
when-use: Reference when asking how evaluation reads fact_oos_predictions/dim_run without importing analytics_store, where the realized y_t comes from, how the gold records which dataset it used, or why no dedicated realized-return port exists
keywords: [adr, evaluation, silver, analytics-store, medallion-store, dataset-tft, target-return, realized, dataset-fingerprint, consumer-owned-port, bc-independence]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-29
adr_id: 6.4.0004
decision: RefreshGold depends on a SilverTableReader Protocol declared in evaluation/application/ports/out whose filters are partition predicates only and whose result may be a superset that the consumer post-filters, satisfied structurally by analytics_store's ParquetAnalyticsRepository and wired only in the composition root; the cohort is read from dim_run by (asset, parent_sweep_id), its single feature_set_name selects the fact_oos_predictions partition, and model identity is dim_run.model_version; the realized return is read once, by one evaluation-side function, through the shared MedallionStore on the read-only pair ("processed", "dataset_tft"), joined by the ISO string of the session timestamp, and identified by a DatasetFingerprint recorded in the gold manifest and in gold_quality_checks; evaluation imports neither analytics_store's application layer nor feature_engineering.
context_stage: 6.4-gold-builders-and-quality-gates
bounded_context: evaluation
---

# ADR 6.4.0004 — Inputs of the gold refresh

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The refresh needs two inputs:

1. **Silver** (`fact_oos_predictions`, `dim_run`), served by the
   `AnalyticsRepository` of `analytics_store` (ADR 4.2.0001). The roadmap lists
   `AnalyticsRepository` in 6.4's `contratos_consumidos`. ADR 0.0.0053 item 2
   (and its "Consequences": "When evaluation/inference arrive: define their
   ports in their own `application/ports/out/`, let `analytics_store` satisfy
   them") forbids importing the supplier's port for behavior. The real
   `read` pushes only partition columns down and ignores other filter keys
   (`parquet_analytics_repository.py`, read path; Checkpoint A probe with
   `run_id` as filter returned the whole partition).
2. **Realized** y_t: `fact_oos_predictions` has no realized column; the domain
   doc §2.1 and §10 #1 (ADR 4.3.0001) fix "realizado = `target_return`
   persistido, juntado por `target_timestamp`; a avaliação nunca recomputa o
   alvo". Issue #117 anticipated a new realized-return port (fork C4).

Internal evidence (code read, 2026-09-29): the shared `MedallionStore`
already serves the read-only pair `("processed", "dataset_tft")`
(`ParquetMedallionStore`, concept 5.2 D3, which rejected a dedicated
`DatasetSource` port as "duplicaria a fronteira de storage para o mesmo dado").
`RunBaselines._load_dataset` reads it and builds the session keys as
`timestamp.isoformat()`; those same strings become `target_timestamp_utc`
through `MultiHorizonPredictionPersister` (`dataset_timestamps[decision_idx +
h]`, ADR 4.3.0001). The row parsing (`_timestamp_of`, `_target_return_of`) is
copied in four modeling writers — issue #99 owns that extraction.

The dataset is not versioned: it can be rebuilt between the training run and
the refresh (ADR 4.3.0001 records the dependency). The gold must say which
dataset it joined (Sandve et al. 2013, Rule 1).

## Decision

`[decision:E] 6.4-C4 — source and port of the realized return`
`Escolha: shared MedallionStore, pair ("processed","dataset_tft"), join by isoformat of the session timestamp · Alternativas: new realized-return port + adapter; realized column added to silver · Degrau (C): —`
`Base: concept 5.2 D3 "Um port dedicado (DatasetSource) duplicaria a fronteira de storage"; domain doc §2.1 "lê o realizado persistido e o junta pela chave de alinhamento"; run_baselines._load_dataset (code read)`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

`[decision:C] 6.4-C4b — shape of the silver port`
`Escolha: consumer-owned SilverTableReader mirroring read(layer, table, filters), partition-only filters, superset result · Alternativas: import AnalyticsRepository; semantic port satisfied by a new analytics_store use case · Degrau (C): 1`
`Base: ADR 0.0.0053 item 2 and Consequences`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

`[decision:C] 6.4-C4c — identity of the realized input`
`Escolha: DatasetFingerprint (existing shared VO) over the rows read · Alternativas: new shared fingerprint VO; nothing recorded · Degrau (C): 1`
`Base: LAYOUT §7 "Identidade só pelos VOs de shared/domain/value_objects/"; ADR 1.4.0001`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

1. **`SilverTableReader`** (port-out, `evaluation/application/ports/out/`):
   `read(*, layer: str, table: str, filters: Mapping[str, object] | None =
   None) -> Sequence[Mapping[str, object]]`. Contract: `filters` are
   **partition predicates only**; the result may contain rows outside any
   non-partition condition the consumer cares about, and the consumer
   post-filters. The fake reproduces this (it applies only partition keys).
   Real: `ParquetAnalyticsRepository`, by duck typing. `[fake, real]` contract
   suite (LAYOUT §7, `port-coverage`).
2. **Cohort read.** `dim_run` with `{asset, parent_sweep_id}` gives the
   cohort's runs; model = `model_version`, plus `seed`, `fold`,
   `feature_set_name`, `config_signature`. The cohort must have exactly one
   `feature_set_name` (else an alignment finding, ADR 6.4.0003); it selects
   the `fact_oos_predictions` partition read with `{asset,
   feature_set_name}`; rows whose `run_id` is not in the cohort are dropped.
3. **Realized read.** One function of the evaluation application reads
   `("processed", "dataset_tft")` with `{"asset": asset}` through the shared
   `MedallionStore`, maps each row to `(timestamp.isoformat(), target_return)`
   and builds the frozen `RealizedReturns` (sessions in order + returns).
   `evaluation` cannot import a modeling helper (`bc-independence`), so this
   is the slice's own single reader, not a consumer of the modeling copies.
   Issue #99 (single dataset read) is the declared floor: its single point
   would have to live in an owner that `evaluation` may import (shared, or the
   `feature_engineering` slice that produces the dataset, through a declared
   data edge or a consumer-owned port); #99 records 6.4 as a fifth consumer.
4. **Fingerprint.** The same read computes `DatasetFingerprint.compute` with
   `asset`, `timestamp_min`, `timestamp_max`, `row_count`, `close_sum`,
   `volume_sum` of the rows read (the dataset carries `close` and `volume`),
   through the injected `Hasher` (the VO is the only caller of the hasher,
   LAYOUT §7). The `MedallionStore` does not expose the file hash, so
   `parquet_file_hash` receives the declared literal
   `not-exposed-by-medallion-store` until issue #120 lands. Because the
   fingerprint's payload sums `close` and `volume`, not the target, the same
   read also produces a **descriptive summary of the consumed column** over
   the sessions read: count, `math.fsum` of `target_return`, first and last
   session (no hash, no shared change). Fingerprint and summary go to the
   manifest (ADR 6.4.0005) and to the `realized_provenance` result (ADR
   6.4.0002).
5. **Data edge.** The only new cross-slice import is the declared data edge
   of the assembler constructing `QuantileForecast` directly (ADR 6.1.0002
   item 3, same VO, new module) — ADR 6.4.0003 item 3.

## Alternatives considered

### Alternative A — Dedicated realized-return port and adapter

- **Why rejected:** concept 5.2 D3 already rejected a second storage boundary
  for the same dataset; the shared port covers it with no new adapter.

### Alternative B — Import `AnalyticsRepository` from `analytics_store`

- **Why rejected:** ADR 0.0.0053 item 2 (and its rejected alternative "Ports
  defined in the supplier … imported by the consumer").

### Alternative C — Semantic port (`read_cohort_predictions`) satisfied by a
new `analytics_store` use case

- **Why rejected:** a use case in another slice for a filtered read; the
  generic read already has a real implementation and a contract to test it.

### Alternative D — Realized column in silver

- **Why rejected:** schema change of a 4.1 fact and a second copy of the
  target; the doc says evaluation reads the persisted target.

### Alternative E — Build `QuantileForecast` inside a new `CoverageSeries`
constructor instead of adding an edge

- **Pros:** no new `bc-independence` entry (the existing edge of
  `coverage_series` would carry it).
- **Cons:** changes the public contract of the 6.1 VO (a second way to build
  it from raw tuples) for a wiring convenience.
- **Why rejected:** the new edge is data-only, declared one by one, and the
  rule of ADR 0.0.0053 item 3 is exactly that.

## Consequences

### Positive

- The join key is the same string on both sides by construction (same
  `isoformat()` path of the same store); the e2e asserts it, and the
  decision-index rule (ADR 6.4.0003) detects a dataset that shifted.
- A rebuilt dataset with different prices, rows or range changes the
  recorded fingerprint; a changed target column changes the recorded
  `target_return` summary.

### Negative

- The application knows three column names of the dataset (`timestamp`,
  `target_return`, and `close`/`volume` for the fingerprint).
- Until #120, a dataset change that preserves the structural sums and the
  target sum is not detected (the decision-index rule still catches a shifted
  session grid).

## References

- Domain doc §2.1, §10 #1; ADR 4.3.0001; ADR 4.2.0001; ADR 0.0.0053; ADR
  1.4.0001; concept 5.2 D3; LAYOUT §3, §7; issues #99, #120.
- Sandve, G. K. et al. (2013), PLoS Comput Biol 9(10), DOI
  10.1371/journal.pcbi.1003285 — Rule 1.
- Related ADRs: 6.1.0002, 6.4.0002, 6.4.0003, 6.4.0005.
