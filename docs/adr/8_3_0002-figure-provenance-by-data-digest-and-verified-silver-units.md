---
title: ADR 8.3.0002 — Figure provenance is proved by the plotted data (a per-figure record with the data digest, the judged generation digest, the source table/document and key, and the generator commit), not by the image hash; the two per-point figures read the silver and the realized series verified unit by unit against the judged silver_content, restricted to the units of the runs read
description: Architecture Decision Record
when-use: Reference before drawing a figure from the gold or the silver, when asking what proves where a figure came from, or why the fan chart and the sharpness diagram may read the silver
keywords: [adr, evaluation, plots, provenance, data-digest, figure-record, silver-content, judged-generation, sandve-rule-7, p8-persist]
status: accepted
created_at: 2026-10-24
updated_at: 2026-10-24
adr_id: 8.3.0002
decision: Each figure gets a JSON record next to its PDF with data_digest (sha256 of the canonical serialization of the renderer-agnostic FigureSpec), generation_digest of the judged copy (checked against the committed .judged.toml), preregistration_ref, partition, source references (table or document, key filter, fields), silver units used with their digests, the closed list of omitted elements, the generator code identity (code.src, code.uv_lock — no HEAD commit hash) and renderer identity; the PDF hash is informative only; an element the judged copy does not persist is omitted from a closed per-figure list, never recomputed; the fan chart and the sharpness diagram read dim_run and fact_oos_predictions of the cohort and the realized grid, recompute each unit digest with the SilverContentAccumulator and require equality with the judged silver_content for exactly the (table, run_id) pairs read, hashed over all rows before any split filter (ablation runs and the permuted/VSN tables sharing a candidate run_id excluded from the expectation), refusing to write anything otherwise.
context_stage: 8.3-plots-and-final-report
bounded_context: evaluation
---

# ADR 8.3.0002 — Provenance by data digest; silver verified by unit

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Doc §6.1 item 1 (P8-PERSIST) requires every figure to be drawn from the
preserved judged generation "ou do dado persistido de onde ela foi construída
(predições e realizado do silver, identificados pelo hash de conteúdo — §4.5)",
quoting Sandve et al. 2013 Rule 7 ("note which data formed the basis of a given
plot and how this data could be reconstructed"). The gold has no per-point
quantiles or widths, so the OOS fan chart and the sharpness box plot can only
come from the silver. Image bytes depend on the matplotlib/FreeType version even
for identical data (pytest-mpl documents this), so an image hash proves nothing
about origin across environments. The 8.1 manifest carries `silver_content`
(per-unit digests, ADR 8.1.0002); in 8.2 the equivalence scaffold failed
because its expectation took every `fact_oos_predictions|…` unit, including the
600 ablation units it never read (technical 8.2 §7, E4 finding).

## Decision

1. **Record per figure** (`docs/reports/figures/<id>.json`, sorted keys, LF):
   `data_digest` = sha256 of `FigureSpec.canonical_bytes()` (single owner),
   `generation_digest`, `preregistration_ref`, partition, `sources`
   (table/document, key filter, fields), `silver_units` (key → digest, only for
   silver-based figures), omitted elements, generator `code.src` and
   `code.uv_lock`, renderer `identity()`. No timestamps, hosts, absolute paths
   or HEAD commit hash (committing the outputs must not change them).
2. **Judged copy check:** the `find` digest must equal the committed
   `.judged.toml`; tables come only from `read_judged_generation` (never
   `current/`).
3. **Silver check:** read with the refresh's post-filter (asset, cohort run ids);
   recompute unit digests with `SilverContentAccumulator` over **all** rows of
   each unit, before any `split` filter (the refresh hashes test and calib);
   expected = for every **(table, run_id) pair read**, all judged keys
   `<table>|<run_id>|*` and only those, plus `dim_run|<cohort>` and
   `realized|<asset>`. Judged units of pairs not read — ablation runs, and
   `fact_permuted_predictions`/`fact_vsn_weights` units that share a candidate
   `run_id` (Checkpoint A, CA-3) — are not expected. Any difference →
   `SilverContentMismatchError`, nothing written.
4. The PDF sha256 may appear in the record only as informative.
5. **Omissions:** an element of the catalog that the judged copy does not
   persist (the candidate's Wilson band outside the gate, the paired native
   series of the conformal figure, the aggregated Beta reference, bootstrap
   intervals of I_f and s_f, the ACF confidence band, τ = 0.5 in the
   calibration) is omitted, from a closed per-figure list fixed in concept 8.3
   D13 and tested; persisted per-seed values may be drawn as labelled
   descriptive dispersion. Nothing is recomputed (doc §6.1 item 5).

## Alternatives considered

### Alternative A — Image hash / pixel baseline as proof
- **Cons:** changes with library versions while the data is equal; equality
  across versions would not prove the data either.
- **Why rejected:** wrong layer (doc §2.2: identity vs. result vs. provenance).

### Alternative B — Gold only
- **Cons:** the fan chart and the sharpness diagram cannot be drawn.
- **Why rejected:** drops two catalog rows the doc explicitly allows from silver.

### Alternative C — Read the silver without verification
- **Cons:** a later silver rewrite would silently change a figure attributed to
  the judged generation.
- **Why rejected:** violates "identificados pelo hash de conteúdo".

## Consequences

### Positive
- Anyone can recompute `data_digest` from the judged copy and compare.

### Negative
- The use case reads the cohort silver (the same volume the refresh reads).

### Neutral / trade-offs accepted
- Byte-identical PDFs are guaranteed only in the same environment (ADR 8.3.0003).

## References

- Domain doc §2.2, §4.5, §6.1; Sandve et al. 2013 Rule 7
- ADRs 8.1.0002, 8.1.0003, 8.2.0002 item 4; technical 8.2 §7 (E4 finding)
- Concept 8.3 D4, D5
