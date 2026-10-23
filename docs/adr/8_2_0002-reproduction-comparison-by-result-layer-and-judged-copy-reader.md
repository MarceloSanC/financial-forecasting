---
title: ADR 8.2.0002 — The reproduction is compared by the result layer by value (digest plus a table-by-table, column-by-column comparison by class R1/R2/R3 with bitwise float equality and max |Δ| always reported), through a pure application comparator, a judged-copy reader on the JudgedGenerationStore port and a read-only CLI subcommand
description: Architecture Decision Record
when-use: Reference before comparing two gold generations, before reading the judged copy's tables (8.2 or 8.3), or when asking why the reproduction is not compared by file bytes or by the generation digest
keywords: [adr, evaluation, reproduction, result-layer, comparison, r1, r2, r3, bitwise, judged-copy, port, cli, provenance]
status: accepted
created_at: 2026-10-23
updated_at: 2026-10-23
adr_id: 8.2.0002
decision: The judged and the reproduced generations are compared on the result layer by value — result_layer_digest of both sides (also against the result_digest recorded by the 8.1 attempt log) and a per-table, per-column comparison whose class (R1 non-float, R3 randomness-dependent float, R2 other float) comes from a declared map, with bitwise float equality and the count and max |Δ| per class reported even when zero; the scorecard is compared by its serialization without the manifest instants; this lives in a pure application function compare_reproduction returning a ReproductionComparison DTO, the judged copy is read as a GoldGeneration by a new JudgedGenerationStore.read_judged_generation method (integrity checked as in find, reused by 8.3), and a read-only audit-reproduction CLI subcommand wires both stores and exits 0 only when bit-identical.
context_stage: 8.2-equivalence-audit
bounded_context: evaluation
---

# ADR 8.2.0002 — Reproduction comparison by result layer, judged-copy reader

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Domain doc §2.2 (R-CAMADAS) compares the result layer and excludes provenance
(timestamps, generation id); §4.6 asks for the comparison "class by class, with
max |Δ| also when it passes — as ADR 7.1.0003 item 5 does for predictions".
ADR 8.1.0004 item 1 already defines the result layer (every table by value plus
the manifest without `started_at`/`finished_at`) and `result_layer_digest`; the
8.1 attempt log recorded `result_digest` `7c7940d4…`. The judged copy's
`generation_digest` covers file bytes, including `MANIFEST.json` instants, so it
necessarily differs for a re-execution. The port `JudgedGenerationStore` has
`find` (integrity + documents) but no reader of the copy's tables; concept 8.1
§14 says the 8.3 reads plots from `judged/<ref>/`, never from `current/`.

## Decision

1. **Equality.** `result_layer_digest(judged) == result_layer_digest(reproduced)
   == 7c7940d4…` plus identity equality (`silver_content` digest, dataset
   fingerprint, ref, partition).
2. **Per-class report.** For every table and column: R1 (non-float: counts,
   decisions, labels, timestamps), R3 (floats depending on random numbers: MCS
   and block-sensitivity p-values, Christoffersen Monte Carlo p-values, H3
   bootstrap bounds), R2 (other floats), from a declared map; floats compared by
   bits; per class the number compared, the number different and max |Δ|
   (numeric only; non-numeric R1 reports the count of differences), reported
   also when zero. The map is complete: every column of every
   `GoldTableSchema` has a declared class (completeness test, no fallback by
   type). `bit_identical` also requires both result-layer digests to equal the
   `expected_result_digest` read from the attempt log.
3. **Scorecard.** `as_mapping()` of both sides without `started_at`/`finished_at`
   inside `manifest_read`; equal, with max |Δ| over numeric leaves.
4. **Where.** `compare_reproduction` (pure, `evaluation/application/use_cases/`)
   → `ReproductionComparison` (`application/dtos/`);
   `JudgedGenerationStore.read_judged_generation(partition, preregistration_ref)`
   with fake, contract suite and the `ParquetGoldStore` real; CLI
   `audit-reproduction` (read-only, no lock, refuses equal roots, checks the copy
   digest against the committed `.judged.toml`, reads the reproduced scorecard
   from `<reproduced>/reproduction/scorecard.json` written by the driver of ADR
   8.2.0001 and never recomputes it, exit 0 only when bit-identical).
5. **No R2 tolerance yet.** u_q and the R2 tolerance (R-ENV) are not implemented:
   no second environment exists (ADR 8.2.0001).

## Alternatives considered

### Alternative A — Compare file bytes or the generation digest
- **Cons:** the manifest instants are provenance; bytes always differ.
- **Why rejected:** wrong layer (R-CAMADAS).

### Alternative B — Digest only
- **Pros:** one line.
- **Cons:** shows neither where nor how much; §4.6 asks for class-by-class max |Δ|.
- **Why rejected:** insufficient for the report and for diagnosis.

### Alternative C — Untested runbook snippet (copy the judged backup into a fake partition and read it with `read_generation`)
- **Pros:** no new `src/` code.
- **Cons:** the citable claim would rest on untested ad-hoc code; reading the
  copy through a fabricated `current/` hides the integrity check.
- **Why rejected:** a claim cited in the TCC needs tested code.

### Alternative D — Comparator in `scripts/` or `tests/`
- **Cons:** outside the hexagonal layers and their gates, or not runnable as a
  tool; the 8.3 and a future R-ENV would duplicate it.
- **Why rejected:** the comparator is generic over `GoldGeneration`.

## Consequences

### Positive
- The report numbers come from tested code; the 8.3 reads the judged copy
  through the same verified path.

### Negative
- One more port method (fake parity, contract test) and one CLI subcommand.

### Neutral / trade-offs accepted
- The class map must be kept in sync with new gold tables; the completeness
  test fails when a column has no declared class.

## References

- Related ADRs: 7.1.0003 (item 5), 8.1.0003, 8.1.0004 (item 1), 8.2.0001
- Domain doc reproduction-equivalence-and-reporting §2.2, §4.2–§4.3, §4.6
