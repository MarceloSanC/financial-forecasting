---
title: ADR 3.4.0001 — Compute the ~38 derived features in the pure stdlib-only domain (DerivedFeatures service) as the causal oracle the pandas dataset-builder (3.5) is validated against
description: Architecture Decision Record
when-use: Reference before deciding whether a derived feature is computed in the domain or only specified, before adding a derived feature to DerivedFeatures, or when the 3.5 dataset-builder needs the oracle to validate its pandas implementation against
keywords: [adr, derived-features, domain-service, pure-python, stdlib-only, oracle, causality, anti-leakage, rolling, ewm, pct-change, shift, ddof, min-periods, parity, pandas-free, feature-engineering]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "3.4.0001"
decision: The ~38 derived features are computed in the pure stdlib-only domain service DerivedFeatures (math/sequences/tuples), replicating pandas semantics verbatim, so it doubles as the independent causal oracle that the pandas dataset-builder (Stage 3.5) is validated against — rather than being a passive spec-only registry
context_stage: 3.4-feature-registry-and-derived
---

# ADR 3.4.0001 — Compute derived features in the pure domain as a causal oracle

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 3.4 owns the rich feature registry **and** the ~38 derived features
(log-returns, momentum, reversal, drawdown, Amihud, volume z-score/spike,
Parkinson/Garman-Klass/downside volatilities, vol-of-vol, volatility/trend
regimes, stress-tail flag, sentiment lags/EMA/surprise/interactions, fundamental
ratios + YoY). The roadmap (`§Stage 3.4`) lists
`domain/services/derived_features.py` as a **domain service**, not a value-object,
and the loaded findings + ledger §B 3.4 demand the formulas be replicated
**verbatim** from the prior repo (`build_tft_dataset_use_case.py:146-285`).

Forces at play:

- **The target layer is mono-layer domain, stdlib-only.** No pandas/numpy may
  enter the domain (`.importlinter` `domain-purity`; proven by an intentional
  break reverted in Stage 3.1 Task 08). Any computation done here must be pure
  Python over sequences/tuples — `math` and stdlib only.
- **The prior repo already proved the formulas in pandas.** The derivations are
  stable and in production-grade use; the work is *translating* pandas semantics
  (`rolling(min_periods=n)`, `std(ddof=0)`, `ewm(adjust=False)`,
  `pct_change(fill_method=None)`, `shift(n)`) to pure Python — not inventing them.
- **ADR 0.0.0021 mandates a per-unit oracle.** Correctness is asserted per unit
  against an *independent* answer, never a global snapshot. Stage 3.5 will compute
  these same features in pandas over the dense daily grid; without a second,
  independent implementation, the 3.5 pandas code has no oracle to be checked
  against, and a silent divergence (an off-by-one shift, a wrong `ddof`) would
  pass unnoticed.
- **Anti-leakage (ADR 0.0.0018 rule 1) is testable only on a real computation.**
  The invariant "appending future bars does not change past values" and "shift is
  always `n>0`" can only be *exercised* by an implementation that produces values
  — a spec-only registry cannot host the causality test the DoD requires.

The alternative under real consideration is the cheaper one: have 3.4 ship only
the *specs* (formula descriptions + warmups + tags) and let 3.5 be the single
implementation in pandas.

## Decision

**Compute the ~38 derived features in the pure stdlib-only domain service
`DerivedFeatures`** (`domain/services/derived_features.py`). Each function takes
aligned input sequences (`close`, `high`, `low`, `open`, `volume`, `sentiment`,
as-of fundamentals) and returns a `tuple` aligned 1:1 with the input, with `None`
in the warmup positions. The functions replicate pandas semantics in pure Python:

- `rolling(min_periods=n)` → `None` for the first `n-1` positions;
- `std(ddof=0)` → population variance (divide by `n`, not `n-1`);
- `ewm(span=s, adjust=False)` → recursive `alpha = 2/(s+1)`;
- `pct_change(n, fill_method=None)` → `(x_t - x_{t-n})/x_{t-n}`, `None` if either is missing;
- `shift(n)` with `n>0` always (no negative shift);
- `clip(lower=0)` before `sqrt`;
- protected division `_safe_ratio` (denominator `None`/`0`/`NaN` → `None`).

This `DerivedFeatures` service is the **independent causal oracle** against which
the Stage 3.5 pandas implementation is validated (ADR 0.0.0021 posture): two
independent implementations of the same formula, asserted equal within a declared
tolerance over a shared fixture.

## Alternatives considered

### Alternative A — Spec-only registry; single pandas implementation in 3.5

- **Description:** Stage 3.4 ships only the `FeatureSpec`s (formula text, warmup,
  tag) for the derived features; the actual computation lives once, in pandas, in
  the 3.5 dataset-builder.
- **Pros:** Less code in 3.4; one implementation to maintain; no pandas→pure
  translation effort.
- **Cons:** No independent oracle for 3.5 — its pandas code would be checked only
  against itself (or hand-typed expected values), exactly the global-snapshot
  anti-pattern ADR 0.0.0021 rejects; the causality invariant of the derived
  features (append-future-bars, shift>0) has nothing to run against in 3.4, so the
  DoD test ("derivadas causais testadas") cannot be met here; a silent divergence
  in 3.5 (wrong `ddof`, off-by-one shift) would pass undetected.
- **Why rejected:** The roadmap lists `derived_features.py` as a *service*, not a
  spec; the loaded finding and ledger §B 3.4 require a pure causal oracle; the cost
  of the translation is low (the formulas already exist and are stable) and the
  gain is high (a genuinely independent second implementation that catches 3.5
  divergence).

### Alternative B — Compute in the domain but as a thin numeric helper that imports numpy

- **Description:** Keep the computation in the domain layer but lean on numpy for
  vectorized rolling/std.
- **Pros:** Less manual loop code; familiar numeric API.
- **Cons:** numpy is banned from the domain (`domain-purity`); importing it turns
  `lint-imports` red and breaks the mono-layer purity invariant this Stage rests
  on.
- **Why rejected:** Directly violates the enforced domain-purity contract; stdlib
  `math` + explicit loops are sufficient for sequence-level computation and keep
  the oracle honestly pandas-free (so it cannot share a bug with 3.5's pandas).

### Alternative C — Do nothing / leave derived features to a later Stage

- **Why not acceptable:** The roadmap and ledger §B 3.4 explicitly allocate the
  full derived family (incl. YoY deferred from 3.3, ADR 3.3.0002) to this Stage;
  3.5 depends on 3.4. Deferring blocks Step 3 and leaves 3.5 without an oracle.

## Consequences

### Positive

- Stage 3.5's pandas implementation gains a genuinely independent, pandas-free
  oracle; a divergence (shift, `ddof`, `min_periods`, regime cutoff) is caught by
  a parity test rather than shipped silently.
- The causality invariants (append-future-bars stability, `shift>0`,
  shifted-trailing windows for z-score/regimes/stress) are *exercised* by a real
  computation, satisfying the DoD's "derivadas causais testadas".
- The pure functions are trivially unit-testable from tuples, with no pandas,
  numpy, or fixtures-on-disk.

### Negative

- The same formulas are implemented twice (pure Python here, pandas in 3.5) —
  accepted: the duplication *is* the oracle; without it there is no independent
  check.
- Translating pandas window semantics to pure Python has off-by-one traps
  (`min_periods`, effective warmup of `vol_of_vol`=40, `shift(1).rolling(63)` for
  regimes) — mitigated by documenting the effective warmup per feature and by the
  parity test against the old's known values.

### Neutral / trade-offs accepted

- The domain oracle and the pandas implementation must stay in sync as formulas
  evolve; the parity test in 3.5 is what keeps them honest (any drift turns it
  red).

## Implementation notes

- `DerivedFeatures` imports only `math`/`dataclasses`/`typing`/`collections.abc`;
  no numpy/pandas. Helpers: `_rolling_mean`, `_rolling_std` (ddof=0),
  `_rolling_max`, `_rolling_quantile`, `_ewm`, `_pct_change`, `_shift`,
  `_safe_ratio`.
- Verbatim sources: `build_tft_dataset_use_case.py:146-237`
  (`_add_phase_a_derived_features`), `:240-253`
  (`_add_sentiment_dynamic_features`), `:256-285`
  (`_add_fundamental_derived_features` + `_safe_ratio`).
- Regimes/stress use `.shift(1).rolling(63)` trailing windows; `volume_zscore`
  uses `volume.shift(1)` window of 20 with `ddof=0`; YoY is `pct_change(252,
  fill_method=None)` over the daily series (ADR 3.3.0002).
- Correctness guarded by `test_derived_features_causal.py` (append-future-bars
  invariance, `shift>0`, flag/regime ranges, parity helpers).

## References

- Related ADRs:
  [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md) (per-unit oracle,
  not global snapshot — the reason for a second independent implementation),
  [0.0.0018](./0_0_0018-anti-leakage-non-negotiable.md) (causal feature timing,
  rule 1; the invariant the derived oracle exercises),
  [3.3.0002](./3_3_0002-defer-yoy-fundamentals.md) (YoY deferred to 3.4 — lands
  here),
  [3.1.0001](./3_1_0001-feature-engineering-bc-and-indicator-contracts.md)
  (the minimal `IndicatorSpec` mold and the BC's enforced domain purity).
- `docs/roadmap.md` §Stage 3.4 (`derived_features.py` as domain service; DoD:
  derivadas causais testadas), §Stage 3.5 (pandas dataset-builder consumes/validates).
- `docs/autonomous-run-decision-ledger.md` §B line 3.4 (replicate the ~38 derived,
  formulas verbatim, warmups included).
- Old: `src/use_cases/build_tft_dataset_use_case.py:146-285`.
