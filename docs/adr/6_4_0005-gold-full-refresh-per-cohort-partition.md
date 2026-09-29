---
title: ADR 6.4.0005 — Gold is regenerated as a whole per cohort — every table and a completion manifest are written to a staging directory and swapped in by directory renames; readers trust only a partition whose manifest exists
description: Architecture Decision Record
when-use: Reference when asking what a rerun of RefreshGold does to existing gold, why gold tables are not incremental, what is left after a failed or blocked refresh, how a reader knows a gold partition is complete, or where the dataset fingerprint and the preregistration reference of a gold are recorded
keywords: [adr, evaluation, gold, full-refresh, idempotence, staging, manifest, atomic-rename, partition, parquet, duckdb, reconstructibility, provenance]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-29
adr_id: 6.4.0005
decision: A GoldStore port publishes a cohort's gold as one generation — RefreshGold computes every report first, the builders map them to tables, and ParquetGoldStore writes all tables into <data_root>/gold/asset=<a>/parent_sweep_id=<p>/.staging/, writes MANIFEST.json last (status COMPLETED or BLOCKED, rows per table, parameters with the preregistration reference, dataset fingerprint and target_return summary, timestamps), then renames current/ to .previous/, renames .staging/ to current/ and deletes .previous/; a failure to delete .previous/ after the swap is a logged warning, not an error; a single writer per cohort is a documented precondition (no lock file); a reader uses a partition only if current/MANIFEST.json exists and reads it before the tables; an exception before the swap leaves the live generation untouched; a blocked refresh publishes a generation that holds only the builders declared runs_when_blocked; asset and parent_sweep_id are validated with the MedallionStore identifier rule before any path is built; incremental refresh and DuckDB COPY … OVERWRITE are rejected.
context_stage: 6.4-gold-builders-and-quality-gates
bounded_context: evaluation
---

# ADR 6.4.0005 — Whole-cohort generations with a completion manifest

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

`overview.md` defines gold as "decisão reconstruível sem re-treino"; the DoD
asks that a rerun over the same inputs yields the same gold. There is no ADR
on gold write policy (ADR 2.1.0001 covers append-only facts only). Issue #117
(P3) left open: incremental vs full refresh, the granularity of DuckDB's
`COPY … (OVERWRITE)` (not verified) and a fingerprint of the inputs.

The gold is f(silver, dataset, parameters) (ADR 6.4.0004): all three must be
recorded (Sandve et al. 2013, Rule 1 "For Every Result, Keep Track of How It
Was Produced"; Rule 6 seeds). The domain doc §8.2 (B-ORDEM) requires the
preregistration to be hashed **before** any confirmatory metric; the gold must
carry that reference so the order is auditable (ADR 6.4.0006).

A first draft discarded the cohort's gold before reading and wrote table by
table. The Checkpoint A review showed that a failure then leaves no gold and a
partial one is indistinguishable from a complete one. The five tables are one
decision artifact and must change together.

Evidence (verified 2026-09-29):

- dbt docs, "About incremental models": "Incremental models are stateful, so
  they're the easiest place to accidentally break idempotence — the
  expectation that re-running a model produces the same result".
- Python docs, `os.replace`: "Rename the file or directory *src* to *dst*. If
  *dst* is a non-empty directory, OSError will be raised … If successful, the
  renaming will be an atomic operation (this is a POSIX requirement)."
- Linux rename(2): "oldpath can specify a directory. In this case, newpath must
  either not exist, or it must specify an empty directory"; `EXDEV` across
  mounts. The page says nothing about durability after a crash.
- Docker docs: no statement, guarantee or caveat about rename atomicity on
  bind mounts (only performance and inotify caveats).
- Probe in this session (dev image, bind mount type `9p` `drvfs` of the
  Windows host): `os.replace(staging, current)` onto a non-empty `current`
  fails with errno 39 (`ENOTEMPTY`); the sequence `current → .previous`,
  `.staging → current`, delete `.previous` leaves only `current` with the new
  content.

## Decision

`[decision:E] 6.4-C5a — incremental or full regeneration`
`Escolha: full regeneration of the cohort · Alternativas: incremental by run_id · Degrau (C): —`
`Base: dbt "the easiest place to accidentally break idempotence" [verified]; overview "gold = decisão reconstruível sem re-treino"`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

`[decision:C] 6.4-C5b — publication mechanism`
`Escolha: staging directory + manifest written last + two directory renames · Alternativas: discard-first then write per table; DuckDB COPY … OVERWRITE; one file per table replaced independently · Degrau (C): 4 (the safest for the claim: a reader never sees a mix of generations)`
`Base: Python os.replace "atomic operation (this is a POSIX requirement)" [verified]; rename(2) directory rule [verified]; bind-mount probe (errno 39, swap works)`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

`[decision:C] 6.4-C5c — what identifies a generation`
`Escolha: manifest with parameters, preregistration reference, dataset fingerprint, rows per table, status and timestamps · Alternativas: no manifest (rows only); content hash of the silver · Degrau (C): 1`
`Base: Sandve et al. 2013 Rules 1 and 6 [verified]; domain doc §8.2 B-ORDEM; LAYOUT §7 (identity only through shared VOs)`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

1. **Partition.** `(asset, parent_sweep_id)` — the cohort (`ScopeSpec.cohort_id`
   maps to `parent_sweep_id`); `parent_sweep_id` is required by
   `RefreshGoldCommand`. Both are validated with the identifier rule of the
   `MedallionStore` read-only pair (`^[A-Za-z0-9._-]+$`, no path separators)
   **before** any path is built; the store refuses anything else.
2. **Layout.** `<data_root>/gold/asset=<a>/parent_sweep_id=<p>/current/`
   holds `<table>.parquet` per published table and `MANIFEST.json`. Every row
   also carries `asset` and `parent_sweep_id` as columns, so a DuckDB query
   does not depend on path parsing (ADR 0.0.0022; engines only in the
   adapter).
3. **Order of side effects** (orchestrator-design: guards before writes):
   validate the build order (ADR 6.4.0001) → validate the identifiers → read →
   assemble → preconditions domain step (k ≥ `MIN_MODELS`, factory only if k
   suffices, per-pair `is_constant` and `validate_block_length_request`,
   backend only for the pairs that pass — ADR 6.4.0002 item 4) → checks → if
   not blocked, every report and the MCS → builders map to tables →
   `GoldStore.publish`. Any exception before `publish` leaves `current/`
   untouched (the previous generation stays live and still self-describes
   what produced it).
4. **Blocked refresh.** The generation holds only the tables of builders
   declared `runs_when_blocked` (today `quality_checks`) and a manifest with
   status `BLOCKED`. The previous generation is replaced, so no stale table
   of an older silver survives next to a failure.
5. **`GoldStore.publish(partition, tables, manifest)`** (port-out; real
   `ParquetGoldStore`): removes a leftover `.staging/` or `.previous/` of an
   interrupted run, writes every table to `.staging/`, writes
   `MANIFEST.json` **last**, renames `current/` (if any) to `.previous/`,
   renames `.staging/` to `current/`, deletes `.previous/`. Rows are sorted by
   the table's key before writing. If deleting `.previous/` fails **after** the
   swap, `publish` logs a warning and returns normally: the new generation is
   already live, and the next `publish` removes the leftover.
6. **Single writer per cohort** is a documented **precondition** of
   `publish` (and of `RefreshGold`): at most one refresh of a given
   `(asset, parent_sweep_id)` runs at a time. No lock file is created
   (`[decision:C]` rung 5, simplest: the pilot has one operator and one
   cohort; a lock would add a stale-lock recovery path).
7. **Readers** (6.5) use a partition only if `current/MANIFEST.json` exists,
   read the manifest first (status, tables present) and only then the
   tables of `current/`. A DuckDB glob over `asset=*/parent_sweep_id=*/`
   without the manifests may read a `BLOCKED` generation or a partition in
   the middle of a swap.
8. **Manifest content.** `status`, `rows_by_table`, the full
   `RefreshParameters` (with `preregistration_ref`, which the four
   confirmatory tables also carry per row — not `gold_quality_checks`), the
   requested horizons, the declared window deficits, the `DatasetFingerprint`
   of the realized input and the `target_return` summary (ADR 6.4.0004 item
   4), the count of cohort runs read, the build order, and the start and
   end timestamps of the refresh. The timestamps come from the injected
   `Clock` and are the only fields that differ between two identical reruns.
9. **No content hash of the silver** in this Stage: it would need a new
   shared identity VO (LAYOUT §7) with no consumer in the DoD; the manifest
   records the cohort id and run count, and 6.5's preregistration hash or 8.1
   may add a content hash.

## Residual risk (declared)

- Between the two renames `current/` does not exist for an instant; a reader
  sees "no gold" (no manifest), never a mix.
- A crash between the renames leaves `.previous/` and/or `.staging/` without
  `current/`; the next refresh removes them and regenerates (the gold is
  rebuildable without retraining).
- A reader that reads the manifest and then the tables could, in theory,
  see tables of a newer generation if a swap happened in between; the
  single-writer precondition and the refresh cadence (manual, per cohort)
  make this a declared residual, not a handled case.
- Durability after a power loss (fsync of the directory) is not guaranteed by
  the sources read and is not attempted: the gold is regenerable, and an
  incomplete generation lacks its manifest.
- Atomicity of a single directory rename on the `9p`/`drvfs` bind mount is
  observed, not documented; correctness does not depend on it because readers
  key on the manifest written last.

## Alternatives considered

### Alternative A — Incremental by `run_id`

- **Why rejected:** DM, Holm and MCS depend on the whole common sample of the
  horizon; one new run changes every row. Incremental logic would be a second,
  stateful path with no speed need at pilot scale.

### Alternative B — Discard first, then write table by table (first draft)

- **Why rejected:** a failure leaves no gold, and a crash mid-way leaves a mix
  that looks complete; the five tables are one artifact.

### Alternative C — DuckDB `COPY … PARTITION_BY … OVERWRITE`

- **Why rejected:** its granularity (whole directory or only the written
  partitions) was not verified, a mistake would delete other cohorts, and it
  replaces tables one at a time — the mix problem again.

### Alternative D — One file per table replaced independently by `os.replace`

- **Why rejected:** each file is atomic, the set is not.

## Consequences

### Positive

- A reader either sees a complete generation with its provenance or nothing;
  cohorts are isolated by directory; reruns converge.

### Negative

- Two copies of a cohort's gold exist during a publish (small at pilot
  scale).

## References

- `overview.md` (medallion, gold); roadmap §Stage 6.4 DoD; issue #117 P3;
  domain doc §8.2.
- dbt docs, "About incremental models".
- Python docs, `os.replace`; Linux man-pages, rename(2); Docker docs, bind
  mounts and WSL 2 best practices (no statement on rename atomicity).
- Sandve, G. K.; Nekrutenko, A.; Taylor, J.; Hovig, E. (2013). "Ten Simple
  Rules for Reproducible Computational Research". PLoS Comput Biol 9(10),
  DOI 10.1371/journal.pcbi.1003285 — Rules 1, 5, 6.
- Related ADRs: 0.0.0022, 2.1.0001, 4.2.0001, 6.4.0001, 6.4.0002, 6.4.0004,
  6.4.0006.
