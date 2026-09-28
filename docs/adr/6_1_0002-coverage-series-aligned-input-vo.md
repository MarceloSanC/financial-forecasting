---
title: ADR 6.1.0002 — CoverageSeries is the single aligned per-horizon input of every Step 6 metric, holding the supplier's QuantileForecast and rejecting non-finite values
description: Architecture Decision Record
when-use: Reference when building the input of any evaluation metric (6.1 scores, 6.2 paired losses, 6.3 hit sequences, 6.4 builders), when asking why the evaluation domain imports QuantileForecast from analytics_store, or why a non-finite forecast raises instead of being dropped
keywords: [adr, evaluation, value-object, coverage-series, quantile-forecast, alignment, per-horizon, symmetric-grid, non-finite, bc-independence, data-edge]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.1.0002
decision: Every 6.1 service takes one frozen `CoverageSeries` — one horizon, one common symmetric grid, strictly increasing unique `target_timestamp`s, one supplier `QuantileForecast` and one finite realized value per point — whose invariants are enforced once at construction; the series scores the post-guardrail vector, carries the supplier VO as a declared data edge (no translation), and raises on any non-finite forecast or realized value instead of dropping the row.
context_stage: 6.1-scoring-and-calibration-metrics
bounded_context: evaluation
---

# ADR 6.1.0002 — `CoverageSeries`: the aligned per-horizon input VO

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The roadmap introduces one value object in 6.1, `CoverageSeries`, and says
the Stage consumes `QuantileForecast` (4.3); 6.3 consumes `CoverageSeries`
for its hit sequences. The overview §7 lists `PairedLossSeries`,
`QuantileForecast` and `CoverageSeries` as the VOs whose invariants
("alinhada, 1 obs/unidade, monotonicidade") are enforced once (ADR 0.0.0020).

A `QuantileForecast` (analytics_store) is one grid for one `(decision,
horizon)`; it does not carry the realized value nor the timestamp. Every 6.1
metric needs the same triple per point — forecast grid, realized return,
`target_timestamp` — plus facts about the whole series that the domain doc
makes preconditions:

- one horizon per computation, never aggregated across horizons (doc §2.7);
- a common grid for the whole series (doc §2.1, modeling §7 item 1);
- a symmetric grid, so that symmetric pairs, the dynamic nominal and the
  Dirac identity CRPS_Q = |y − x| exist (doc §2.1, §3.2, §3.3);
- one observation per aligned point, already deduplicated (doc §2.1, modeling
  §7 item 2), in time order (6.3 needs transitions, doc §7.2);
- the **post-guardrail** vector is what is scored (doc §2.2, convention #3);
- the realized value is read, never recomputed (doc §2.1, convention #1).

`QuantileForecast.from_raw` preserves non-finite raw values with
`guardrail_applied = False` and explicitly defers "the decision about quality
/ degeneracy" to Step 6 (concept 4.3 C4). The modeling adapters already raise
on non-finite emission (5.2/5.3 C5), so a non-finite value reaching evaluation
is an upstream invariant violation, not a data condition.

## Decision

1. **One VO, one horizon.** `CoverageSeries` (frozen) holds `horizon: int`
   (≥ 1), `levels: tuple[float, ...]`, `target_timestamps: tuple[str, ...]`,
   `forecasts: tuple[QuantileForecast, ...]` and `realized: tuple[float, ...]`,
   aligned 1:1, with T ≥ 1. There is no multi-horizon container in 6.1, so
   no service can aggregate across horizons. `QuantileForecast` carries no
   horizon, so the VO cannot verify that every point really belongs to
   `horizon`: that guarantee belongs to the builder (6.4); the VO only
   carries the label (and the strict timestamp order rejects the most common
   mix, repeated `target_timestamp`s).
2. **Invariants at construction (`__post_init__`, `ValueError`):** lengths
   equal and non-zero; `target_timestamps` strictly increasing (hence unique
   and ordered); `levels` in (0, 1) and strictly increasing; every
   `forecast.levels == levels`; `levels` symmetric,
   |τ_k + τ_{K+1−k} − 1| ≤ 1e-12 (float representation), with at least one
   pair (τ_1 < 0.5 — K = 1 {0.5} is rejected); every `guardrail_values`
   non-decreasing and finite, every `realized` value finite.
   `QuantileForecast` is a public frozen dataclass with no `__post_init__`
   (only `from_raw` sorts), so these per-point checks are re-done here
   rather than trusted (overview §7 "monotonicidade"; ADR 0.0.0020).
3. **Supplier VO, not a copy.** The series stores the analytics_store
   `QuantileForecast` itself and reads `guardrail_values` (scored vector) and
   `guardrail_applied` (diagnostic). The edge
   `evaluation.domain → analytics_store.domain.value_objects.quantile_forecast`
   is declared in the `bc-independence` contract with its reason, as ADR
   0.0.0053 item 3 prescribes; `evaluation` joins that contract (and
   `hexagonal-layers`, `domain-purity`, `inward-only`) in this Stage.
4. **Derived values on the VO, not in a service:** the symmetric pairs
   `(τ_k, 1 − τ_k)` for τ_k < 0.5 and the guardrail application rate
   (fraction of points with `guardrail_applied`), which the domain doc puts in
   the profile as a crossing diagnostic (§2.2, convention #3).
5. **Non-finite ⇒ raise, never drop.** A non-finite forecast or realized value
   fails construction. Rows are never excluded silently: exclusion is a
   researcher degree of freedom and breaks the contiguity that HAC and the
   block bootstrap need (ADR 0.0.0011, doc §5.3 item 5).

## Alternatives considered

### Alternative A — An evaluation-owned grid type (primitive matrix) translated from `QuantileForecast`

- **Pros:** `evaluation.domain` would import nothing from another slice.
- **Cons:** a second definition of the same persisted row
  (`fact_oos_predictions`) plus a translator — the Anticorruption Layer that
  ADR 0.0.0053 rejects between modules of one context.
- **Why rejected:** ADR 0.0.0053 items 1–3.

### Alternative B — Two VOs (a "scored series" for proper scores, `CoverageSeries` for calibration)

- **Pros:** names each input after its use.
- **Cons:** both would carry identical fields and invariants; the degeneracy
  gate needs the same rows for both halves (proper scores on all rows,
  calibration on the non-degenerate ones — ADR 0.0.0011).
- **Why rejected:** duplication without a difference in invariants.

### Alternative C — Services over bare tuples, validation in each service

- **Why rejected:** invariants checked N times or not at all — the failure
  mode ADR 0.0.0020 exists to prevent.

### Alternative D — Drop non-finite rows (with a count) instead of raising

- **Pros:** a partially broken run still produces numbers.
- **Cons:** row exclusion conditioned on a model's output; a hole inside the
  series violates the contiguity 6.2 relies on (doc §6.7); masks an upstream
  bug that 5.2/5.3 already treat as fatal.
- **Why rejected:** ADR 0.0.0011 (no row exclusion) and doc §6.7.

### Alternative E — Do nothing (let 6.4 build whatever shape each metric wants)

- **Why rejected:** the shape is consumed by 6.1, 6.2 (L_t), 6.3 (hits) and
  6.4; fixing it once, with its invariants, is the point of ADR 0.0.0020.

## Consequences

### Positive

- Every metric can assume alignment, order, one horizon, a common symmetric
  grid and finite values.
- 6.2 and 6.3 inherit the same input (per-point losses and hit sequences are
  functions of the same series).

### Negative

- A new declared runtime edge in `bc-independence`.
- Asymmetric grids are unrepresentable; if the project ever adopts one, this
  VO (and the IS/PICP pairing) must be revisited — the domain doc already
  scopes all theory to symmetric grids.

### Neutral / trade-offs accepted

- Seeds and folds are not modelled in the VO: a series is whatever sample the
  builder (6.4) assembles for one horizon; averaging across seeds (doc §6.9)
  is done by the consumer on per-series results.
- **Which sample** feeds the scorecard reports (a model's full series or the
  exact `target_timestamp` intersection that DM/MCS use — doc §6.7) is decided
  by 6.4/6.5, not here: the 6.1 services report on the series they receive.

## Implementation notes

- File: `evaluation/domain/value_objects/coverage_series.py`.
- ISO timestamps compare correctly as strings only in one uniform format; the
  builder (6.4) supplies them as persisted in silver (4.3 format).

## References

- Related ADRs: [0.0.0020](./0_0_0020-statistics-in-domain-over-value-objects.md),
  [0.0.0011](./0_0_0011-preregistration-invariants-and-h1-gate.md),
  [0.0.0053](./0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md),
  [4.3.0001](./4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md),
  [4.3.0002](./4_3_0002-quantile-forecast-dense-grid-guardrail.md),
  [6.1.0001](./6_1_0001-scoring-libraries-as-oracle-backend-behind-port.md).
- Domain doc: [`probabilistic-forecast-evaluation.md`](../domain/evaluation/probabilistic-forecast-evaluation.md)
  §2.1, §2.2, §2.7, §5.3, §6.7, §10 (conventions #1–#3).
- Roadmap Stage 6.1/6.3; issue [#77](https://github.com/MarceloSanC/financial-forecasting/issues/77).
