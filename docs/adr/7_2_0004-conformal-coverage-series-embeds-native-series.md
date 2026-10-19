---
title: ADR 7.2.0004 — Conformal coverage is measured on a ConformalCoverageSeries that embeds the native CoverageSeries (same mask, same n, same predicates) instead of putting conformal limits in a CoverageSeries
description: Architecture Decision Record
when-use: Reference when computing or reading conformal coverage, when asking why the conformal n equals the native n, why the conformal output is not a CoverageSeries, or how ADR 6.1.0004 applies to conformal limits
keywords: [adr, conformal, coverage, coverage-series, degeneracy, mask, wilson, picp, mpiw, nesting, evaluation, domain]
status: accepted
created_at: 2026-10-17
updated_at: 2026-10-17
adr_id: 7.2.0004
decision: A new frozen VO ConformalCoverageSeries in evaluation/domain/value_objects holds the candidate's native CoverageSeries (one seed, one horizon) plus, per symmetric pair, the conformal lower/upper limit of every point (one per native point, after an upstream join by target_timestamp; ±∞ allowed, no monotonicity, never rearranged); the service ConformalCoverage runs DegeneracyGate on the embedded native series with the plan's tolerance and computes, on its non-degenerate rows only, ĉ at each conformal limit (is_at_or_below), PICP (is_inside_closed) and MPIW per pair, Wilson bands at the given levels, the nesting-violation rate, and, over complete seeds only, both seed means (c̄/n̄ and the mean of per-seed coverages), every report carrying the label "cobertura empírica (não garantida)".
context_stage: 7.2-conformal-cqr
bounded_context: inference
---

# ADR 7.2.0004 — Conformal coverage series embeds the native series

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 7.2 concept (issue #158), 2026-10-17. Closes fork (f) of
the issue and the tension left open by inference domain doc §8.2 ("como os
intervalos conformais entram nas estruturas de cobertura existentes").
`bounded_context` is the Stage's (`inference`); the code lives in `evaluation`.

## Context

Doc §4.11 / ADR 0.0.0008 item 11: the comparison reuses evaluation §4 without
re-derivation — ĉ, PICP/MPIW, Wilson with the same n, hits — and no new test.
`CoverageSeries` (ADR 6.1.0002) demands one common symmetric grid scored on
the post-guardrail monotone vector; conformal limits are not nested by
construction (Gupta et al. 2022 Tab. 1) and must not be rearranged (ADR
0.0.0008 item 8), so they cannot be a `CoverageSeries` without the
rearrangement that voids the per-tail guarantee. ADR 6.1.0004 forbids any
service from accepting a degeneracy mask from outside. The issue's triage
proposed "a VO of its own, not the CoverageSeries, with the native series'
mask".

## Decision

`[decision:C] 7.2-COV — how conformal intervals enter the coverage structures`
`Escolha: VO embedding the native CoverageSeries + per-point conformal limits; service reusing the evaluation predicates, gate and Wilson · Alternativas: conformal limits in a CoverageSeries (rearranged); mask passed from outside; coverage computed in inference · Degrau: 1 (ADR 6.1.0004, 0.0.0008 item 8, doc §4.11)`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim (no persisted format)`

1. `ConformalCoverageSeries(seed, native, variant, pairs)` — `seed` is the
   native series' seed (carried to `ConformalCoverageReport.seed`); `native` is the
   `CoverageSeries` of one seed and horizon (the candidate's full series,
   `model_full`); each `ConformalPairLimits(lower_level, upper_level, lower,
   upper)` is a symmetric pair of the native grid with one limit per native
   point; NaN is rejected, ±∞ accepted. A crossed interval (L > U, possible
   when both one-sided corrections shrink) is **valid output**, never swapped:
   `is_inside_closed` counts it as not covered, its width U − L enters MPIW as
   is, and it counts as a nesting violation (item 2).
2. `ConformalCoverage.evaluate(series, *, tolerance, band_levels)` runs
   `DegeneracyGate.evaluate(series.native, tolerance=tolerance)` — the mask is
   that of the series the VO embeds, so ADR 6.1.0004's rule holds and n equals
   the native `CoverageMetrics` n by construction; on the kept rows: count and
   ĉ of `is_at_or_below(y, L)` and `is_at_or_below(y, U)` per pair, PICP by
   `is_inside_closed`, MPIW (∞ when any kept limit is infinite, flagged),
   `WilsonBand.evaluate` per tail at each band level with nominal τ_lo and τ_hi;
   the nesting-violation rate = fraction of kept rows whose conformal limits
   are not ordered L(τ_1) ≤ … ≤ L(τ_m) ≤ U(τ_m) ≤ … ≤ U(τ_1), plus the
   crossed-interval rate per pair. 100 % degenerate
   ⇒ "not applicable", not an error (as `CoverageMetrics` C5).
3. `ConformalCoverage.seed_mean(reports, *, horizon, variant, expected_seeds,
   band_levels)` — `reports` hold one report per complete seed (same horizon
   and variant, seeds in `expected_seeds`, no repetition, else `ValueError`);
   `seeds_excluded = expected_seeds − seeds_used`; over the **complete** seeds of
   one (horizon, variant) only (a seed with any unit not `ok` is excluded and
   reported; zero complete seeds ⇒ `undefined`): c̄, n̄, the estimate and band
   on c̄/n̄ (ADR 6.5.0006 item 2, ADR 6.3.0005) — the `coverage` of the mean
   row — and the mean of per-seed coverages with its sd (the literal of doc
   §4.9 and ADR 0.0.0008 item 9) beside it. Both are persisted.
4. Every report carries `EMPIRICAL_COVERAGE_LABEL = "cobertura empírica (não
   garantida)"`, validated at construction (the `MPIW_LABEL` pattern).
5. No `evaluation → inference` import: the limits arrive as floats.

## Alternatives considered

### Alternative A — Conformal limits in a `CoverageSeries`
- **Why rejected:** it needs a monotone grid; rearranging the conformal output
  changes each limit and voids the per-tail guarantee (ADR 0.0.0008 item 8).

### Alternative B — Pass the native mask to a new service
- **Why rejected:** ADR 6.1.0004 forbids it (a mask of one series could select
  rows of another).

### Alternative C — Measure coverage in inference
- **Why rejected:** copies the FA7 predicates and Wilson (doc §4.11 "sem
  re-derivar") or needs an inference → evaluation edge (`bc-independence`).

## Consequences

### Positive
- Same rows, same n, same tie rule as the native coverage: the comparison
  differs only by the limits.

### Negative
- A second coverage report type next to `CoverageReport`.

### Neutral / trade-offs accepted
- Hits as sequences (Christoffersen on conformal limits) are not built: no new
  test (ADR 0.0.0008 item 11); the per-tail counts carry the hit rate.

## References

- Related ADRs: [0.0.0008](./0_0_0008-native-quantiles-with-conformal-benchmark.md),
  [6.1.0002](./6_1_0002-coverage-series-aligned-input-vo.md),
  [6.1.0004](./6_1_0004-coverage-metrics-recomputes-degeneracy-mask.md),
  [6.3.0005](./6_3_0005-count-kernels-accept-mean-counts.md),
  [6.5.0006](./6_5_0006-scorecard-inputs-gate-from-seed-mean-counts.md),
  [7.2.0003](./7_2_0003-conformal-intervals-on-demand-gold-via-refresh-gold.md).
- Gupta, C.; Kuchibhotla, A. K.; Ramdas, A. (2022). *Pattern Recognition*, 127, 108496. DOI: 10.1016/j.patcog.2021.108496.
- Inference domain doc §4.8, §4.11, §8.2; issue [#158](https://github.com/MarceloSanC/financial-forecasting/issues/158).
