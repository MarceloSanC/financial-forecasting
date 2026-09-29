---
title: ADR 6.4.0003 — The series assembler verifies one observation per point instead of re-running the operationally-latest dedup; alignment rules have one owner that reports findings
description: Architecture Decision Record
when-use: Reference when asking why evaluation does not import or wrap modeling's deduplicate_operationally_latest, what happens to a duplicate forecast in silver, or where contiguity, horizon label, fold/seed coverage and grid equality are checked
keywords: [adr, evaluation, series-assembly, dedup, operationally-latest, alignment, contiguity, intersection, target-timestamp, fold-coverage, modeling]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-29
adr_id: 6.4.0003
decision: The domain service SeriesAssembly treats "one observation per (model, seed, horizon, target_timestamp, quantile_level)" as a precondition enforced by the write-side dedup of the modeling harness and verifies it, reporting any duplicate as an alignment finding; it does not call, wrap or copy modeling's deduplicate_operationally_latest, and it never picks one of two duplicates (a post-hoc choice is a forking path; recovery is a new cohort); the same assembler is the single owner of every alignment rule — split, uniqueness, decision index and horizon label on the session index, complete common grid, consistent guardrail flag, realized present, per-series contiguity with a prefix bounded by the declared window deficit and a common end, fold and seed coverage, family coverage over the requested horizons, orphan runs, single feature set and configuration per model, minimum T — and returns findings instead of raising, so the alignment_check publishes them.
context_stage: 6.4-gold-builders-and-quality-gates
bounded_context: evaluation
---

# ADR 6.4.0003 — One observation per point is verified, not re-deduplicated

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The domain doc (§2.1, §6.7) and the modeling doc (§7 item 2) say: "Há **uma
observação por ponto alinhado** (dedup operationally-latest do harness —
modeling §7 item 2)"; "O dedup operationally-latest (5.1) precede o
pareamento". Issue #117 (fork C3) proposed consuming the dedup owner
(`modeling/domain/services/operationally_latest_dedup.py`) from `evaluation`
through a consumer-owned port (ADR 0.0.0053), not a copy.

Internal evidence (code read, 2026-09-29), **scoped to one invocation of a
writer**:

- each of the three writers (`run_baselines.py`, `train_gbm_quantile.py`,
  `train_tft.py`) dedups the entries of **its own invocation** with key
  `(split, horizon, decision_idx + horizon, quantile_level)` and rank
  `decision_idx`, then asserts `_assert_zero_removal`. Within one invocation
  the silver therefore has one observation per point;
- for a fixed horizon the rank is determined by the key
  (`decision_idx = target_idx − horizon`, ADR 4.3.0001), so two records with
  the same key always tie and `deduplicate_operationally_latest` raises on a
  tie;
- **across invocations** nothing in the writers prevents two runs of the same
  model and seed in one cohort (a repeated invocation with another
  configuration; a partial rerun). Silver is append-only and `run_id`
  differs, so both land. On the silver key the rank still ties, so re-running
  the dedup at read time would still only return its input or raise; a rank
  that breaks the tie (e.g. `dim_run.created_at_utc`, "latest write wins")
  would be a new policy chosen after seeing the predictions;
- the folds' test blocks are contiguous and disjoint (concept 5.1 I7; domain
  doc §6.8), so a legitimate duplicate does not exist inside one cohort.

Data-shape limitation: no silver is materialized in this checkout (5.5 is not
in `develop`); the evidence is the writers' code, and the e2e of this Stage
uses a synthetic silver. The real cohort is checked by 8.1 through the
published alignment findings.

## Decision

`[decision:E] 6.4-C3 — consuming the operationally-latest dedup at read time`
`Escolha: verify uniqueness in the assembler, duplicate = alignment finding, never resolved · Alternativas: consumer-owned port to modeling's dedup; local copy; rank = created_at_utc · Degrau (C): —`
`Base: modeling use cases, rank = decision_idx with key (split, h, decision_idx + h, level) + _assert_zero_removal (code read); domain doc §6.7 "O dedup … precede o pareamento"`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

1. `SeriesAssembly` (domain service, stdlib-only) takes frozen
   `ForecastRecord`s (one silver row joined with its `dim_run` row), the
   cohort's run descriptors (`run_id`, `model_version`, `seed`, `fold`,
   `feature_set_name`, `config_signature` for every `dim_run` row of the
   cohort), the `RealizedReturns` of the asset (ADR 6.4.0004), the requested
   horizons and the declared window deficit per model.
2. It is the **single owner** of the alignment rules and returns an
   `AlignmentReport` with every finding instead of raising on the first:
   - **split:** only `test` enters; other splits are not evaluated (declared,
     not a finding);
   - **uniqueness** of (model, seed, horizon, target, level) — a duplicate is
     a finding, never resolved by choosing one;
   - **decision index:** `realized.index_of(decision_timestamp) ==
     decision_idx` (the silver keeps `decision_idx`; a mismatch means the
     dataset read is not the one the writer indexed — ADR 6.4.0004);
   - **horizon label:** `index(target) − index(decision) == horizon` on the
     session index (ADR 4.3.0001; the "garantia do builder" of concept 6.1);
   - **grid:** every point carries the complete grid, the same for all
     models of the horizon (concept 5.2 I11);
   - **guardrail flag:** `guardrail_applied` is an int 0/1 in silver, read as
     a bool; the levels of one point must agree (they describe one vector);
   - **realized** present for every target;
   - **contiguity:** each (model, seed, horizon) series occupies consecutive
     session indices; all series of a horizon **end** at the same target (a
     truncated suffix is a finding); a series may **start** later than the
     earliest series of the horizon by at most the declared window deficit of
     its model (enumerated by the trainer — ADR 5.4.0001; 0 when not
     declared). The common sample is the intersection of the intervals, an
     interval by construction;
   - **fold coverage:** the set of `dim_run.fold` values of every (model,
     seed) equals the cohort's fold set;
   - **seed and family coverage:** every (model, seed) of the cohort has a
     series in every requested horizon; a requested horizon absent from the
     silver is a finding; horizons present but not requested are ignored;
   - **orphan run:** a `dim_run` row of the cohort with no `test` prediction is
     a finding;
   - **identity:** `model` is `dim_run.model_version`; a
     `fact_oos_predictions.model_version` that differs from the
     `dim_run.model_version` of its `run_id` is a finding; one
     `feature_set_name` per cohort and one `config_signature` per model (one
     candidate per family, domain doc §6.4);
   - **minimum T** of the common sample: the value objects' own minimums
     (`check_points` T > h; `MIN_BLOCK_LENGTH_OBS`) are read from their
     owners, not re-declared.
3. Without findings, the assembler builds the `CoverageSeries` of both
   samples (full series per model × seed; the same cut to the common sample)
   with `QuantileForecast` constructed **directly** from the persisted
   `value_raw`, `value_guardrail` and `guardrail_applied` — never through
   `from_raw`, which would recompute the guardrail. The value objects keep
   validating what they already validate.
4. `evaluation` imports nothing from `modeling`.

## Alternatives considered

### Alternative A — Consumer-owned port satisfied by the modeling dedup

- **Pros:** the literal reading of "o dedup precede o pareamento" at read
  time; no second rule.
- **Cons:** a port, a fake, a `[fake, real]` contract suite and a wiring edge
  for a call that, on this key, is the identity or a raise.
- **Why rejected:** it cannot change a result; the uniqueness finding
  produces the same outcome (a duplicate blocks the refresh) with the cause
  published, and the dedup policy keeps one owner (modeling).

### Alternative B — Rank by `dim_run.created_at_utc` ("latest write wins")

- **Pros:** would let a repeated invocation replace an earlier one without a
  new cohort.
- **Cons:** the choice of which prediction counts would be made after the
  predictions exist — a researcher degree of freedom (Simmons et al. 2011;
  domain doc §5.3 item 5) and a forking path the preregistration exists to
  close.
- **Why rejected:** the recovery for a polluted cohort is a **new
  `cohort_id`** (a fresh `parent_sweep_id`, which `RunId` already includes —
  ADR 5.2.0004), not a read-time tie-break.

### Alternative C — Local copy of the dedup in evaluation

- **Why rejected:** a second owner of a modeling rule (the issue already
  ruled it out).

### Alternative D — Assembler raises on the first violation

- **Why rejected:** the violation must be published (ADR 6.4.0002); raising
  would leave only a traceback and would make `alignment_check` a second
  writing of the same rules.

## Consequences

### Positive

- One owner per rule: dedup policy in modeling (write side, per invocation),
  alignment in the assembler (read side, per cohort), invariants in the value
  objects.
- A duplicate across invocations is visible in `gold_quality_checks`.

### Negative

- A polluted cohort cannot be repaired in place; it is re-run under a new
  cohort id.

### Reopening triggers

- a writer changes its alignment key or its `operational_rank`;
- the project adopts a legitimate multi-invocation cohort (e.g. resuming a
  partially failed 5.5 run into the same `parent_sweep_id`) whose duplicates
  must be resolved by a preregistered rule.

## References

- Domain doc §2.1, §5.3, §6.4, §6.7, §6.8; modeling doc §7 item 2; concept
  5.1 D5/I7/I9; concept 5.2 I11; concept 6.1 (horizon label is the builder's
  guarantee); ADR 5.4.0001 (enumerated window deficit).
- ADR 0.0.0053 (consumer-owned ports), 4.3.0001 (session index), 5.2.0004
  (run identity includes the cohort), 6.2.0001 (the VO validates, never
  builds).
- Simmons, J. P.; Nelson, L. D.; Simonsohn, U. (2011), Psych. Sci. 22(11).
- Related ADRs: 6.4.0002, 6.4.0004, 6.4.0007.
