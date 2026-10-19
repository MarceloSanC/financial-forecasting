---
title: ADR 7.2.0003 — Conformal intervals computed on demand (no silver table) by an inference use case behind an evaluation-owned port, inside RefreshGold, with two conformal gold tables in the same generation
description: Architecture Decision Record
when-use: Reference when asking where conformal intervals are stored, who calls CalibrateConformal, why there is no silver table for them, how RefreshGold assembles the calib/test units, or what the conformal gold tables hold
keywords: [adr, conformal, cqr, on-demand, silver, gold, refresh-gold, consumer-owned-port, use-case, assembly, refresh-parameters, manifest, gold-tables]
status: accepted
created_at: 2026-10-17
updated_at: 2026-10-17
adr_id: 7.2.0003
decision: Conformal corrections and limits are never persisted in silver; RefreshGold assembles, from the silver rows it already reads and the realized training grid, one unit per (fold, seed, horizon) of the candidate (split = "calib" rows as calib, split = "test" rows as test), calls the inference use case CalibrateConformal through a ConformalCalibration port declared in evaluation/application/ports/out (its command/result DTOs cross as one declared data edge), measures coverage with ConformalCoverage, and publishes gold_conformal_corrections and gold_conformal_coverage in the same generation, with the r2 [conformal] block carried by RefreshParameters and the manifest; a unit that cannot be computed becomes an undefined or error row and never aborts the refresh.
context_stage: 7.2-conformal-cqr
bounded_context: inference
---

# ADR 7.2.0003 — Conformal intervals on demand, gold via RefreshGold

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 7.2 concept (issue #158), 2026-10-17. Closes fork (b) of
the issue. A first draft moved the gold integration to 8.1 by Task count; the
orchestrator rejected that cut (Task count is a reference, not a gate, and 8.1
only runs the confirmatory pipeline), so the integration is part of 7.2.

## Context

The calib predictions are in `silver.fact_oos_predictions` with
`split = "calib"` (ADR 7.1.0002), and `RefreshGold` already reads every split
of the cohort's partition (the `SeriesAssembly` keeps only `test`). The
realized series is the modeling training grid, read once by `RefreshGold`
(ADR 6.4.0009). Profiles are born in `RefreshGold` as gold tables of the same
generation (ADR 6.6.0002). `inference` and `evaluation` are independent
slices: behavior crosses only through a port owned by the consumer, data as
declared edges (ADR 0.0.0053). Silver tables exist only for facts with a
consumer (ADR 4.1.0001). A conformal unit is cheap (≤ 253 scores per tail) and
deterministic given silver + grid + plan, so a silver copy would be a cache,
not a fact.

## Decision

`[decision:C] 7.2-WHERE — where conformal intervals live`
`Escolha: on demand inside RefreshGold through an evaluation-owned port satisfied by an inference use case; two gold tables · Alternativas: silver table of conformal limits; a gold builder computing CQR; CQR in the evaluation domain; a separate conformal job; deferring the integration to 8.1 · Degrau: 1 (ADR 4.1.0001, 6.4.0009, 6.6.0002, 0.0.0053; roadmap places ConformalCalibrator in inference/domain) e 5`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim até a primeira geração real (8.1); depois, as tabelas são formato persistido`

1. **No silver table** for corrections or conformal limits.
2. **`CalibrateConformal`** (`inference/application/use_cases/`): a command of
   primitive DTOs — one unit per (fold, seed, horizon) with calib points
   (decision and target timestamps, guardrailed grid by level, realized) and
   test points (timestamps, guardrailed grid) — plus pairs, variants and ρ. It
   builds the domain VOs (dedicated calib and embargo), calls
   `ConformalCalibrator` per (pair, tail, variant) and returns corrections,
   ranks, infinite flags, the Beta reference and the conformal limits of every
   test point. It reads and writes nothing. Each `ConformalUnitResult`
   carries `status` ∈ {`ok`, `undefined`, `error`} and a `reason`, with
   corrections, Beta and limits `None` when not `ok`: an incomplete input
   (calib point without realized, grid without the pair's levels) is
   `undefined`; a `ValueError`/`ArithmeticError` from the VO or the calibrator
   is caught **per unit** and becomes `error`. Only command errors raise
   `ValueError`, before any unit: duplicate (fold, seed, horizon), unknown
   variant, invalid or missing ρ for NEXCP, non-symmetric pair or τ_lo ∉ (0; 0.5). One bad unit
   never hides the others (Checkpoint A, A-D1).
3. **Consumer port** `ConformalCalibration` in
   `evaluation/application/ports/out/` (`__call__(command) -> result`), fake
   in `tests/fakes/`, `[fake, real]` contract whose real leg is
   `CalibrateConformal` (LAYOUT §7, #93). The command/result DTOs are the
   supplier's and are imported at runtime only by `refresh_gold`: one declared
   data edge `evaluation.application.use_cases.refresh_gold →
   inference.application.use_cases.calibrate_conformal` in `bc-independence`
   (ADR 0.0.0053 item 3, the same class as the 7.1 command-DTO edges).
4. **Assembly.** A new domain service `ConformalAssembly` in
   `evaluation/domain/services/` runs only when the `SeriesAssembly` has no
   finding. Per candidate run (fold from `CohortRun`, a `str` converted with
   `int`) and horizon it builds the calib points from `split = "calib"`
   records and the test points from `split = "test"` records. The calib goes
   through the same rules the `SeriesAssembly` applies to the test; those rules
   are private to `series_assembly.py` today and emit `AlignmentFinding`, so
   the module is refactored: each rule becomes a public function that returns
   the violation, which the `SeriesAssembly` turns into a finding (unchanged
   behavior) and the `ConformalAssembly` into an `undefined` unit. The rules: horizon = target index − decision index, no duplicate
   (run, horizon, decision, level), the plan's levels complete; realized from
   `RealizedReturns` at each calib target. The test ↔ native join is by
   `target_timestamp`: per fold, the unit's set of test targets must equal the
   native full series' targets of that fold. Any violation, a missing or
   partial calib, or a non-integer fold becomes an `undefined` unit with its
   reason — never an alignment finding, because conformal is not in the
   verdict path.
5. **`RefreshGold`.** After the horizon reports, when the plan carries a
   `[conformal]` block: one port call with every `ok` unit of the assembly;
   every unit not `ok` (from the assembly or returned by the port) is a row
   with its status and reason, and each `error` adds 1 to
   `RefreshGoldResult.conformal_error_units`. The port result is mapped to
   evaluation-owned records (`ConformalUnitRecord` inside `ConformalReports`)
   in `refresh_gold.py`, the only module with the runtime edge; `GoldInputs`
   and the builders see evaluation types only. A (seed, horizon, variant) with
   any unit not `ok` gets an `undefined` coverage row with the reason — never
   coverage over a subset of folds. For the complete ones: one
   `ConformalCoverageSeries` from the native full series and the returned
   limits, `ConformalCoverage.evaluate` with the plan's
   `degeneracy_tolerance` and band levels, then `seed_mean` over complete
   seeds only (seeds used and excluded reported; zero complete seeds ⇒
   `undefined`), persisting both c̄/n̄ and the mean of per-seed coverages. The
   refresh never aborts on a conformal unit (ADR 6.6.0002 item 3 pattern); an
   exception raised by the port call itself is a command error and
   propagates. A BLOCKED generation does not build the conformal tables (not
   `runs_when_blocked`).
6. **`RefreshParameters`** gains the required key `conformal_parameters:
   ConformalParameters | None` (`None` for r0/r1), filled by
   `refresh_command_from` and compared by `check_manifest`. Manifests written
   before this Stage no longer read (no real gold exists — the 6.6 D6 rule).
7. **Gold tables** (schema in `gold_schema`, one pure-mapping builder each):
   - `gold_conformal_corrections` — one row per (fold, seed, horizon, pair,
     tail, variant): n, rank, correction, infinite, ρ, Beta per tail (a, b,
     mean, sd; null for NEXCP and for l = 0), status (`ok` | `undefined` |
     `error`) and reason;
   - `gold_conformal_coverage` — one row per (horizon, variant, pair, kind ∈
     {lower_tail, upper_tail, pair, nesting}, seed or seed mean): n_points,
     n_evaluated, count, coverage or PICP, MPIW and its infinite flag, crossed
     and nesting-violation rates, Wilson bounds per band level, nominal,
     `serial_dependence_warning`, the label, status and reason.

   Both enter `GOLD_SCHEMAS` and `CONFIRMATORY_TABLES` (they carry the
   `preregistration_ref` column, ADR 6.4.0006 item 4), and `GoldInputs` gains
   `conformal_reports`. Without a `[conformal]` block both tables are written
   with zero rows; a
   COMPLETED generation missing either is corrupt (ADR 6.6.0002). Neither the
   evidence mapper, the verdict nor the `ScorecardProfile` reads them.

## Alternatives considered

### Alternative A — Silver table of conformal limits
- **Why rejected:** a persisted format and a writer for a deterministic, cheap
  derivative (ADR 4.1.0001); rung 5.

### Alternative B — A gold builder that computes CQR itself
- **Why rejected:** builders are pure mappings (ADR 6.4.0001/6.6.0002).

### Alternative C — CQR in the evaluation domain
- **Why rejected:** contradicts the roadmap (`ConformalCalibrator` in
  `inference/domain`), a higher source.

### Alternative D — A separate conformal job or CLI command
- **Why rejected:** a second reader of silver and grid and a second
  publication path; the gold generation and its manifest are the single place
  where cohort results appear (ADR 6.4.0005).

### Alternative E — Defer the gold integration to 8.1
- **Why rejected:** no real scope boundary — 8.1 runs the confirmatory
  pipeline and consumes the calibrator ready; building the integration is a
  7.2 capability. Task count is a reference, not a gate (orchestrator,
  2026-10-17).

## Consequences

### Positive
- No new silver format; the conformal output is always rebuilt from silver +
  grid + the anchored plan, in the same generation and manifest as the rest.

### Negative
- One more declared cross-slice data edge and two gold tables to maintain.
- Old gold manifests stop reading (none exists for the real cohort).

### Neutral / trade-offs accepted
- The Stage tests the integration on synthetic silver only; the first real
  refresh is 8.1's (blinding).

## References

- Related ADRs: [0.0.0053](./0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md),
  [4.1.0001](./4_1_0001-analytics-store-silver-schema-per-table.md),
  [6.4.0001](./6_4_0001-gold-builder-dag-graphlib-declared-dependencies.md),
  [6.4.0005](./6_4_0005-gold-full-refresh-per-cohort-partition.md),
  [6.4.0009](./6_4_0009-realized-from-modeling-training-grid-via-consumer-port.md),
  [6.6.0002](./6_6_0002-profile-tables-isolated-from-the-verdict.md),
  [7.1.0002](./7_1_0002-calib-predictions-in-fact-oos-predictions-idempotent-completion.md),
  [7.2.0001](./7_2_0001-cqr-preregistration-details.md),
  [7.2.0004](./7_2_0004-conformal-coverage-series-embeds-native-series.md).
- Issue: [#158](https://github.com/MarceloSanC/financial-forecasting/issues/158).
