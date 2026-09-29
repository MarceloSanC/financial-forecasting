---
title: ADR 6.4.0002 — Quality checks run through a domain registry with declared severity; alignment and statistical preconditions are blocking errors, degeneracy and realized provenance are reported; results persist in gold_quality_checks
description: Architecture Decision Record
when-use: Reference when adding a quality check, when asking why a refresh published only gold_quality_checks, whether a degeneracy rate can stop the pipeline, or how a constant loss differential or an undefined block length is reported
keywords: [adr, evaluation, quality-checks, registry, severity, alignment, contiguity, degeneracy, mcs-preconditions, provenance, gold, persistence]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-29
adr_id: 6.4.0002
decision: Quality checks are domain objects registered in a QualityCheckRegistry, each with a declared severity (ERROR blocks the dependent gold tables, WARN never blocks) producing frozen QualityCheckResult values with outcome PASS, FAIL, REPORTED or SKIPPED; alignment_check (ERROR) translates the assembler's AlignmentReport, statistical_preconditions (ERROR) owns a domain step that runs before the loss factory and the McsBackend — k ≥ MIN_MODELS, then per pair is_constant and validate_block_length_request, with only ArithmeticError from the backend converted — and reports k < 2, a constant pairwise loss differential and an undefined or invalid block-length estimate as failures instead of exceptions, degeneracy_check (WARN) reports the rate of every (model, seed, horizon) full series or is SKIPPED with its reason when the assembly failed, and realized_provenance (WARN) reports the DatasetFingerprint and a target_return summary of the realized input; results are aggregated per (check, finding kind, horizon, model, seed) and published as gold_quality_checks on every refresh.
context_stage: 6.4-gold-builders-and-quality-gates
bounded_context: evaluation
---

# ADR 6.4.0002 — Quality check severity and persistence

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Two project rules fix the severity of the two checks the roadmap names:

- domain doc §6.7: an interior gap in the common `target_timestamp` sample
  "é **violação de invariante da 6.4**, não caso de pareamento" — HAC and the
  block bootstrap assume a contiguous series, so no gold table may be built
  over it;
- domain doc §5.3 items 3–4 and §10 #12: the degeneracy rate per (model,
  horizon) is **always** reported, no row is excluded, and the threshold that
  turns it into a verdict is preregistered and applied by 6.5 (ADR 0.0.0011).

The statistical services have data-dependent preconditions that are not
bugs: the MCS needs k ≥ 2 and var(L_i − L_j) > 0 for every pair (doc §6.5,
convention #16; `ModelConfidenceSet.evaluate` raises), and the block-length
estimate needs a series that passes `validate_block_length_request` and a
finite b̂_sb (`ArchMcs` may raise `ArithmeticError` on a series that passes the
validator — ADR 6.2.0004). On real data these are properties of the cohort,
and an exception would leave only a traceback.

The doc does not say how the result is stored. Simmons et al. (2011, req. 5)
and ICH E9 §5.2 ("should be documented") — both already cited by the doc —
ask for the record, not only a log line.

External practice (verified 2026-09-29): dbt `severity` is "`error` or `warn`
(default: `error`)"; `dbt build` skips downstream resources on a failing
test, and a `warn` test does not cause the skip. Breck et al. (2019, §1):
"Catching data errors early is thus important"; "on-calls tend to ignore
alerts that are either spammy or not actionable" — two levels, not one.

## Decision

`[decision:E] 6.4-C2a — severity of alignment, preconditions and degeneracy`
`Escolha: alignment and statistical preconditions = ERROR (block); degeneracy and provenance = WARN, outcome REPORTED · Alternativas: all blocking; all warnings; preconditions as exceptions · Degrau (C): —`
`Base: domain doc §6.7 "violação de invariante da 6.4"; §5.3 item 3 "sempre reportada"; §6.5 var(L_i − L_j) > 0; dbt severity "default: error" [verified]`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

`[decision:C] 6.4-C2b — form of the persisted result`
`Escolha: own gold table gold_quality_checks, one row per (check, finding kind, horizon, model, seed) with an occurrence count and one example · Alternativas: one row per finding; columns on each gold table; log only · Degrau (C): 1`
`Base: domain doc §5.3 item 3 (Simmons et al. 2011 req. 5; ICH E9 §5.2 "should be documented")`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim (gold is rebuilt from silver)`

1. `QualityCheckRegistry` (domain service) holds checks in a fixed order;
   `run(context) -> tuple[QualityCheckResult, ...]`; `is_blocking(results)`
   is true iff some result has severity ERROR and outcome FAIL. A check
   declares its `name` and `severity`.
2. `QualityCheckResult` (frozen VO, `domain/value_objects/`): `check`,
   `severity`, `outcome` (`PASS | FAIL | REPORTED | SKIPPED`), `kind` (the
   finding kind, or the measured quantity), scope (`horizon`, `model`,
   `seed`, each optional), `occurrences` (int ≥ 1), `value` (optional float)
   and `detail` (str: the first occurrence). The grain of the table is
   (check, kind, horizon, model, seed): several findings of the same kind in
   one scope are **aggregated** into one row with their count, so the key is
   unique and the table stays readable.
3. `alignment_check` (ERROR) translates the `AlignmentReport` of the series
   assembler (ADR 6.4.0003) into results: one `FAIL` per (kind, scope), or one
   `PASS` per horizon with T as `value`. It re-derives nothing.
4. `statistical_preconditions` (ERROR) owns a **domain step that runs before
   the factory and the backend**, because both validate these conditions by
   raising (`paired_pinball_losses` raises for k < `MIN_MODELS`;
   `ArchMcs.optimal_block_length` calls `validate_block_length_request`
   first):
   - (i) k ≥ `MIN_MODELS` (public constant of its first owner, the
     `PairedLossSeries` VO, which the `paired_pinball_losses` factory now
     imports instead of keeping its own copy) is checked before the factory is
     called;
   - (ii) per pair of the seed-averaged `PairedLossSeries`, `is_constant` on
     the differential and `validate_block_length_request` (public, 6.2) are
     evaluated in the domain; a failing pair gets an undefined estimate
     **without** calling the backend;
   - (iii) only the pairs that pass reach `McsBackend.optimal_block_length`;
     the use case converts **only** `ArithmeticError` into an undefined
     estimate — every other exception propagates.

   `FAIL` for k < 2 and for each undefined estimate (with its cause); `PASS`
   otherwise; `SKIPPED` when the assembly failed.
5. `degeneracy_check` (WARN) runs `DegeneracyGate.evaluate` (6.1) on the
   **full** series (`model_full` sample) of every (model, seed, horizon) with
   the refresh's tolerance and emits `REPORTED` with the rate as `value`; it
   never fails (the threshold is 6.5's). When the assembly failed there are no
   series: it emits one `SKIPPED` result whose `detail` names the reason.
6. `realized_provenance` (WARN) emits one `REPORTED` result carrying the
   `DatasetFingerprint` of the realized input and a descriptive summary of the
   consumed `target_return` (count of sessions read, `math.fsum` of the
   values, first and last session — ADR 6.4.0004 item 4) in `detail`, with
   the `math.fsum` as `value`.
7. A blocked refresh publishes only the builders declared
   `runs_when_blocked` — today `quality_checks` (ADR 6.4.0005).

## Alternatives considered

### Alternative A — Degeneracy as a blocking check

- **Why rejected:** would apply a threshold before the preregistration fixes
  it (6.5) and would block the point baselines, degenerate by specification
  (ADR 0.0.0052; domain doc §5.3 item 2).

### Alternative B — Statistical preconditions as exceptions

- **Why rejected:** a constant differential or an undefined b̂_sb is a
  property of the cohort, not a defect of the code; the cause must be
  published like an alignment failure. Only genuine bugs propagate.

### Alternative C — One row per finding

- **Why rejected:** hundreds of identical rows for one systematic cause (e.g.
  a whole fold missing) hide the other causes; the aggregated row keeps the
  count and an example.

### Alternative D — Result columns on each gold table; log only

- **Why rejected:** blocked tables would have nowhere to hold the cause; a log
  is not part of the reconstructible gold.

## Consequences

### Positive

- A blocked refresh still publishes an auditable artifact saying why.
- New checks are one class and one registry entry.

### Negative

- `REPORTED` and `SKIPPED` are outcomes that consumers must understand; the
  6.5 scorecard reads `REPORTED` as a measurement and `SKIPPED` as "not
  available because of a blocking cause".

## References

- Domain doc §5.3, §6.5, §6.7, §10 #12, #16, #17.
- Simmons, J. P.; Nelson, L. D.; Simonsohn, U. (2011), Psych. Sci. 22(11),
  req. 5; ICH E9 §5.2.
- Breck, E.; Polyzotis, N.; Roy, S.; Whang, S. E.; Zinkevich, M. (2019).
  "Data Validation for Machine Learning". SysML 2019, §1.
- dbt docs, `severity` and `dbt build`.
- Related ADRs: 0.0.0011, 6.1.0003, 6.2.0004, 6.4.0001, 6.4.0003, 6.4.0004,
  6.4.0005.
