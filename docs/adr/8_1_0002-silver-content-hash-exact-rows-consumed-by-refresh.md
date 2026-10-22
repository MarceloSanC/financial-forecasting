---
title: ADR 8.1.0002 — The content hash of the silver read is a new shared identity VO `SilverContentHash` over the canonical rows `RefreshGold` consumes (exact floats, content-defined units), recorded in the gold manifest
description: Architecture Decision Record
when-use: Reference before hashing any silver or gold content, before changing what `RefreshGold` reads, when the 8.2 reproduction checks that it read the same input, or when asking why the hash is not the Parquet bytes or the `DatasetContentFingerprint`
keywords: [adr, evaluation, shared, identity, content-hash, silver, fingerprint, value-object, refresh-gold, manifest, exact-floats, canonical-json, parquet, reproducibility, provenance]
status: accepted
created_at: 2026-10-22
updated_at: 2026-10-22
adr_id: 8.1.0002
decision: A new identity VO `SilverContentHash` in `shared/domain/value_objects/` hashes, through the canonical `Hasher`, the rows `RefreshGold` actually consumes after its post-filters — one digest per content-defined unit ((table, parent_sweep_id) for `dim_run`, (table, run_id, year) for fact tables, year read from the row), combined per table and overall — with columns keyed by name, rows in canonical order, floats encoded exactly by `repr` and `None` as null; `RefreshGold` computes it while reading and records it in a new `GoldManifest.silver_content` field, so the hash depends only on the multiset of rows consumed, never on file layout, read order, reader typing or Parquet bytes.
context_stage: 8.1-confirmatory-run
bounded_context: evaluation
---

# ADR 8.1.0002 — Silver content hash: exact rows consumed by the refresh

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The Step 8 domain gate puts "the content hash of the silver tables read" in
the **input identity** of the judged generation (R-CAMADAS, domain doc
reproduction §2.2, §4.5 item 2): without it, "the predictions read are the
same" cannot be checked by the 8.2 reproduction. ADR 6.4.0005 item 9 left the
gap open: "No content hash of the silver in this Stage: it would need a new
shared identity VO (LAYOUT §7) … 8.1 may add a content hash."

Facts that constrain the form:

- LAYOUT §7: identity only through the VOs of `shared/domain/value_objects/`;
  nobody else calls `hasher.hash_mapping` (rule 6 of `check_layout.py`).
- The canonical `Hasher` rounds every float to 10 decimals (ADR 1.4.0001).
  `PreregistrationHash` avoids it by encoding each float as `"float:" + repr(x)`
  before delegating (ADR 6.5.0001).
- `DatasetContentFingerprint` (ADR 5.5.0004) hashes the training grid
  column-wise with the 10-decimal rounding; its value is frozen in the cohort
  spec and referenced by revisions r0–r3 (`realized.dataset_fingerprint`).
- What `RefreshGold` reads (`refresh_gold.py`): `dim_run` of the cohort and of
  the ablation cohort; `fact_oos_predictions` of every feature set of the
  cohort, post-filtered to the cohort's `run_id`s (both splits); the ablation's
  `fact_oos_predictions` year by year, `split = "test"`; and, one candidate run
  at a time, `fact_permuted_predictions` and `fact_vsn_weights`. The silver
  reader may return a superset of a partition; the consumer post-filters
  (`SilverTableReader` contract).
- Measured shape (2026-10-22, schema and counts only): 396 `dim_run` rows;
  1,605,072 `fact_oos_predictions`; 8,655,920 `fact_permuted_predictions`;
  891,490 `fact_vsn_weights`; no null or non-finite float; `year` is `int64`
  inside the files and inferred `int32` by pyarrow hive partitioning (the
  union fails).
- Float32 spacing at x is ≈ 1.19·10⁻⁷·|x| (2⁻²³ relative); it falls below
  10⁻¹⁰ when |x| < ≈ 8.4·10⁻⁴, a range where daily-return quantiles live.

## Decision

```
[decision:E] 8.1-H1 — new VO or generalize DatasetContentFingerprint
Escolha: new shared VO `SilverContentHash` · Alternativas: generalize `DatasetContentFingerprint` to rows; hash outside a VO
Base: LAYOUT §7 + check_layout rule 6 (identity only through shared VOs); ADR 6.4.0005 item 9 "it would need a new shared identity VO"; DatasetContentFingerprint's value is frozen in the cohort and in r0–r3 — changing its encoding changes an anchored identity (code fact read in this session)
Verificado: não verificado (§4.2) — internal sources
Sensibilidade pré-registrada: nenhuma · Reversível: sim (before the 8.1 run)

[decision:E] 8.1-H2 — exact floats or the hasher's 10-decimal rounding
Escolha: exact (`repr`, as `PreregistrationHash`) · Alternativas: canonical rounding to 10 decimals
Base: ADR 1.4.0001 (rounding to 10 decimals); float32 spacing 2⁻²³·|x| < 10⁻¹⁰ for |x| < ≈ 8.4·10⁻⁴ ⇒ distinct float32 inputs collide under rounding (derivation); an identity that does not distinguish inputs fails R-CAMADAS; ADR 6.5.0001 precedent for exact encoding
Verificado: derivation · Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:E] 8.1-H3 — canonical rows or Parquet bytes
Escolha: canonical rows (columns by name, canonical row order, typed values as the reader delivers them) · Alternativas: sha256 of the Parquet files (DVC style)
Base: Apache Parquet `parquet.thrift` FileMetaData `created_by` ("String for application that wrote this file") — the bytes carry the writer version; measured: `year` int64 in files × int32 under hive inference; ADR 5.5.0004 (content, not Parquet bytes); issue #211 (DVC hashes bytes — counterpart)
Verificado: não verificado (§4.2) — the spec field is cited by name; the measurement was taken in this session
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:E] 8.1-H4 — rows consumed or partitions read
Escolha: the rows `RefreshGold` keeps after its post-filters · Alternativas: every row of each partition read (superset)
Base: Sandve et al. 2013 Rule 1 "every detail that may influence the execution of the step is recorded" — rows of another cohort in the same partition do not influence the step, and appending them (silver is append-only) would change a superset hash without changing the input; SilverTableReader contract (superset allowed, consumer post-filters)
Verificado: herdado (Rule 1 verified in the Step 8 domain gate) · Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] 8.1-H5 — where the hash is computed
Escolha: inside `RefreshGold`, over the same rows it consumes, recorded in `GoldManifest.silver_content` · Alternativas: the orchestrator re-reads the silver and hashes it; a separate use case · Degrau (C): 1 (ADR 6.4.0005 item 8: the manifest is what identifies a generation) and 5
Base: refresh_gold.py read paths (post-filters, year-by-year ablation reads, one candidate run at a time) — a second reader would be a second definition of "what the refresh reads"
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] 8.1-H6 — granularity
Escolha: one digest per content-defined unit — (table, parent_sweep_id) for dim_run, (table, run_id, year) for fact tables with year read from the row — combined per table and overall (DVC `.dir`-like map of hashes) · Alternativas: one hash per table over all rows; one hash per row · Degrau (C): 5, with the unit defined by content so the hash does not depend on how the code chunks its reads
Base: issue #211 (DVC: per-file hash + `.dir` map; MLflow: dataset digest); memory bound — RefreshGold already reduces attribution one run at a time and the ablation one year at a time
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim
```

1. **VO.** `SilverContentHash(value: str)` in
   `shared/domain/value_objects/silver_content_hash.py`, frozen, validated by
   `validate_sha256_hex`; factories `of_unit(hasher, table, rows)` and
   `combine(hasher, digests)`. Payload per unit: the table name and the rows,
   each row a mapping column → value with every `float` replaced by its exact
   encoding (the `PreregistrationHash` rule — shared, not copied), `None` kept
   as null, NaN/±inf refused with `ValueError`; rows in a canonical order
   independent of read order. The combined digest hashes the mapping unit key
   → digest. LAYOUT §7 lists the new VO.
2. **Scope.** Exactly the rows `RefreshGold` consumes after its post-filters,
   for every silver table it reads: `dim_run` (cohort and ablation cohort),
   `fact_oos_predictions` (cohort, both splits; ablation, `split = "test"`),
   `fact_permuted_predictions`, `fact_vsn_weights` — without write-provenance
   columns (`created_at_utc` of `dim_run`, the instant the row was written:
   provenance, which R-CAMADAS excludes from identity; the technical fixes the
   full list by reading the silver schemas). The realized series the refresh
   uses (grid timestamps and target return) enters as one more unit,
   `(realized, asset)`, with exact floats: by the argument of 8.1-H2 the
   rounded `DatasetContentFingerprint` alone does not distinguish realized
   values below ≈ 5·10⁻¹¹; that fingerprint stays in the manifest unchanged
   (it is the anchored identity of the cohort). With a `BLOCKED` refresh,
   only what was read before the checks is hashed (`dim_run`, the cohort's
   `fact_oos_predictions`, the realized).
2b. **Types.** The VO normalizes numeric scalars before encoding (numpy/pandas
   integers → `int`, floats → `float`, `bool` kept, `None` → null) and refuses
   any other type with `ValueError`: the real reader goes DuckDB → pandas
   (e.g. nullable `Int64` for `seed`), and the measured int64/int32 split of
   `year` came from pyarrow hive inference, so the identity must not depend
   on the reader's numeric dtype.
3. **Units.** `(table, parent_sweep_id)` for `dim_run`; `(table, run_id, year)`
   for fact tables, with `year` taken from the row (so a run read in one pass
   or year by year hashes the same). The exact key format and whether the
   per-unit digests live in the manifest or in a file next to it in the
   generation are fixed in the technical; the overall and per-table digests
   are in the manifest.
4. **Recording.** `GoldManifest` gains `silver_content` (overall, per table,
   per unit), serialized by `as_mapping()` and read by `from_stored`.
   `RefreshGoldResult` gains the published `manifest`. No gold table changes.
5. **Invariant.** The hash depends only on the multiset of rows consumed: not
   on file layout, read order, read granularity, partition typing or Parquet
   bytes; rows of another cohort in the same partition do not change it.

## Alternatives considered

### Alternative A — Generalize `DatasetContentFingerprint` (8.1-H1)
- **Description:** one fingerprint VO for grid and silver.
- **Pros:** one VO less.
- **Cons:** its encoding (10-decimal rounding, column-wise payload) is part of
  an identity frozen in the cohort and in r0–r3; changing it breaks
  `GridFingerprintMismatchError` against the anchored plans; keeping it means
  rounding (Alternative B).
- **Why rejected:** an anchored identity cannot change.

### Alternative B — The hasher's 10-decimal rounding (8.1-H2)
- **Pros:** no float encoding step.
- **Cons:** collides distinct float32 values with |x| < ≈ 8.4·10⁻⁴.
- **Why rejected:** an identity must distinguish distinct inputs.

### Alternative C — sha256 of the Parquet files (8.1-H3)
- **Description:** DVC-style byte hashes per file plus a map.
- **Pros:** fast; no row canonicalization.
- **Cons:** bytes depend on the writer version (`created_by`), compression and
  row-group layout, and file layout depends on the write history; a
  reproduction in another environment would fail identity for a non-content
  reason.
- **Why rejected:** contradicts "content, not bytes" (ADR 5.5.0004) and the
  issue #211 synthesis.

### Alternative D — Hash a sample of rows (MLflow-like digest)
- **Cons:** a change outside the sample goes undetected.
- **Why rejected:** an identity must cover every row consumed.

### Alternative E — Every row of each partition read (8.1-H4)
- **Cons:** appending another cohort's rows to the same partition changes the
  hash without changing the input.
- **Why rejected:** identity of what influences the step (Sandve Rule 1).

### Alternative F — The orchestrator re-reads and hashes (8.1-H5)
- **Pros:** no change to `RefreshGold`.
- **Cons:** a second definition of what the refresh reads (post-filters,
  ablation years, attribution per run), and a window in which the silver read
  for the hash could differ from the silver read for the metrics; twice the
  I/O over ≈ 11 M rows.
- **Why rejected:** the reader of the rows is the right owner.

### Alternative G — One hash per table / per row (8.1-H6)
- **Cons:** per table needs all rows of the table in one payload (memory);
  per row is ≈ 11 M hasher calls and gives no per-run diagnosis.
- **Why rejected:** per content unit bounds memory to one unit and tells the
  8.2 which run differs.

### Alternative H — Do nothing
The 8.2 reproduction could not show it read the same predictions (R-CAMADAS),
and the gap of ADR 6.4.0005 item 9 stays open.

## Consequences

### Positive
- The judged generation identifies its silver input by content, comparably
  across environments that read the same values.
- Per-unit digests localize a difference to a run and a year.

### Negative
- `GoldManifest`, its serialization and `RefreshGoldResult` change (6.4 DTOs);
  tests of 6.4–7.3 that pin manifests need the new field.
- One more pass over every consumed row (≈ 11 M on the real cohort); the cost
  is measured in the real run.

### Neutral / trade-offs accepted
- The hash identifies what the gold read; it does not bind a checkpoint to its
  training data (the `RunId` gap of issue #163 stays there).
- Typed values as the reader delivers them: a reader change that alters a
  value's Python type would change the hash; that is an identity difference to
  diagnose, not to hide.

## Implementation notes

- Reuse the exact float encoding of `PreregistrationHash` (one owner; move the
  helper to `shared/domain/services/` if both VOs need it).
- Golden value test for a small payload; invariance tests for row order,
  column order and read granularity; a test that two adjacent float32 values
  with |x| < 10⁻⁴ hash differently.

## References

- Related ADRs: [1.4.0001](./1_4_0001-canonicalizacao-de-hash-deterministico.md),
  [5.5.0004](./5_5_0004-single-training-grid-warmup-trim.md),
  [6.4.0005](./6_4_0005-gold-full-refresh-per-cohort-partition.md),
  [6.5.0001](./6_5_0001-preregistration-canonical-toml-hashed-value-object.md),
  [8.1.0001](./8_1_0001-confirmatory-run-orchestration-guards-status-replay.md),
  [8.1.0003](./8_1_0003-judged-generation-preserved-copy-run-record-attestation.md)
- Domain: `docs/domain/evaluation/reproduction-equivalence-and-reporting.md` §2.2, §4.5, §9 (R-CAMADAS)
- External: Sandve et al. 2013, Rule 1; Apache Parquet `parquet.thrift`
  (`FileMetaData.created_by`); DVC "Internal files" and MLflow dataset digest
  (issue #211 §Referências)
- Issue: #211; concept 8.1 D4
