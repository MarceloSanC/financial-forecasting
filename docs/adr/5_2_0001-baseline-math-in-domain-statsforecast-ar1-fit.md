---
title: ADR 5.2.0001 — Preregistered baseline math as pure domain services; statsforecast confined to AR(1) parameter estimation
description: Architecture Decision Record
when-use: Reference whenever revisiting why the baseline emission formulas live in modeling.domain (stdlib-only) instead of inside the statsforecast adapter, why statsforecast is used only to fit the AR(1), or before swapping/expanding the baseline library
keywords: [adr, baselines, statsforecast, domain-purity, quantile-emission, ewma, type-7, ar1, oracle-tests, normaldist, modeling]
status: accepted
created_at: 2026-07-15
updated_at: 2026-07-15
adr_id: 5.2.0001
decision: The preregistered emission formulas (degenerate grid, Gaussian location-scale via statistics.NormalDist, Hyndman-Fan type-7 sample quantile, RiskMetrics EWMA recursion, AR(1) closed-form h-step mean/variance) are implemented as stdlib-only domain services validated per unit against oracles; statsforecast is kept behind the BaselineForecaster port but used ONLY to estimate the AR(1) parameters (ARIMA(1,0,0), the R arima port), because no statsforecast model implements the other preregistered conventions and its naive-model intervals follow the √h level semantics that does not match the project's 1-day-return target
context_stage: 5.2-baselines-naive-statistical
---

# ADR 5.2.0001 — Preregistered baseline math in the domain; statsforecast for the AR(1) fit only

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The roadmap describes Stage 5.2 as "baselines naive e estatísticos **via
statsforecast**" and names the adapter file
`statsforecast_baseline_forecaster.py`; the overview ratifies
`statsforecast` as the baselines library in §6 (constraints/stack) and §7
(approach). Meanwhile, the domain doc
[`quantile-model-training.md`](../domain/modeling/quantile-model-training.md)
§3 and [ADR 0.0.0052](./0_0_0052-baseline-quantile-emission-conventions.md)
preregister **exact emission conventions** per baseline: degenerate grid for
the point baselines; RiskMetrics EWMA with fixed λ = 0.94 and μ = 0; Gaussian
location-scale conversion (QRM Eq. (2.19)); Hyndman-Fan type-7 sample
quantiles on a rolling window; AR(1) closed-form h-step mean and variance
(Hamilton §4.2; Box-Jenkins Eq. (5.1.16)).

Verifying what statsforecast actually offers (official Nixtla docs,
2026-07-15) surfaces a real conflict:

- Its model zoo (AutoARIMA/ARIMA/AutoRegressive, HistoricAverage, Naive,
  RandomWalkWithDrift, SES/Holt/HoltWinters, GARCH/ARCH, Theta, Croston, …)
  contains **no** RiskMetrics EWMA-volatility model with fixed λ, **no**
  rolling empirical-quantile model, and **no** "forecast zero" model.
- The prediction intervals of its naive-family models follow the textbook
  **level/accumulated** semantics (FPP3 Table 5.2, σ scaling with √h) — a
  different model from this project's target, where the value predicted at
  horizon h is the **one-day** return realized at session t+h, so no √h rule
  applies (domain doc §2.1; ADRs 3.5.0001 + 4.3.0001). Using those intervals
  would silently violate the preregistered per-horizon behavior (EWMA flat in
  h; AR(1) variance growing to the unconditional).
- The only exact correspondence is the AR(1): `ARIMA(order=(1, 0, 0),
  include_mean=True)` is the R `arima` port, exposing fitted coefficients and
  σ²_ε, with ψ-weight h-step variance identical to the preregistered closed
  form.

Forces: preregistered formulas are load-bearing methodology (they change
reported numbers — ADR 0.0.0052); the overview mandates the statistical
methodology as **pure, testable domain services backed by recognized
libraries validated against oracles** (overview §1/§7); ADR 0.0.0021 rejects
"trust the libraries, test nothing" and prescribes thin own implementations +
oracle where no canonical library implements the unit; the domain layer must
stay stdlib-only (`domain-purity` gate) — and `statistics.NormalDist.inv_cdf`
(stdlib, AS241) provides z_τ without numpy/scipy.

## Decision

**Split the responsibility at the estimation/emission boundary:**

1. **Emission math = pure domain services** (`modeling/domain/services/`,
   stdlib-only), implementing exactly the preregistered formulas of the
   domain doc §3: `degenerate_grid`, `gaussian_grid` (location-scale with
   `statistics.NormalDist().inv_cdf`), `sample_quantiles_type7`
   (h = (n−1)p + 1), `ewma_variance_path` (RMTD Eq. [5.3], λ fixed), and
   `ar1_step_forecast` (closed-form h-step mean/variance). Each unit is
   validated per ADR 0.0.0021 against an analytic fixture and/or an
   independent library oracle in tests (`numpy.quantile` for type 7,
   `pandas.ewm` for the EWMA recursion, tabulated z_τ for `NormalDist`,
   synthetic-series parameter recovery + closed-form fixture for the AR(1)).
2. **statsforecast stays behind the `BaselineForecaster` port, confined to
   the AR(1) parameter estimation** (`ARIMA(order=(1,0,0), include_mean=True)`
   fit → μ̂, φ̂, σ̂²_ε), inside
   `modeling/adapters/out/statsforecast/statsforecast_baseline_forecaster.py`.
   The adapter dispatches the 5 canonical families and delegates all emission
   to the domain services. The dependency is declared in `pyproject.toml`
   with minor pinning (posture of `exchange-calendars`/`pandas-ta-classic`).

The preregistered formula is the contract; the library is a means, validated
against the oracle — never the authority.

## Alternatives considered

### Alternative A — Force all five specs through statsforecast models
- **Description:** map `historical_mean` → `HistoricAverage`, `zero_return` →
  a constant/Naive hack, `ewma_vol` → `SES(alpha=0.06)` applied to squared
  returns, `historical_quantiles` → none available; take the library's
  prediction intervals as the quantile grid.
- **Pros:** maximal reuse of a ratified library; least own math.
- **Cons:** the library's intervals encode the √h level semantics —
  **mis-specified** for the 1-day-return target (domain doc §2.1); no model
  implements the RiskMetrics fixed-λ EWMA or the rolling type-7 quantile, so
  two of five specs are impossible anyway; the SES-on-squared-returns hack
  obscures the preregistered recursion and still requires custom emission;
  convention fidelity would depend on undocumented library internals.
- **Why rejected:** violates the preregistered conventions it is supposed to
  implement; the "via statsforecast" wording cannot override the emission
  ADR (0.0.0052) that the same domain gate produced.

### Alternative B — All math in the adapter (numpy), nothing in the domain
- **Description:** implement estimation and emission with numpy/pandas inside
  the adapter; the domain keeps only `BaselineSpec`.
- **Pros:** vectorized; one home for all numerics.
- **Cons:** the emission conventions — the exact thing preregistered — become
  untestable as pure units and invisible to the `domain-purity` discipline;
  contradicts the overview's stated design ("metodologia estatística
  implementada como domínio puro testável", overview §1/§7) and the precedent
  of 4.3 (`MultiHorizonPredictionPersister` pure) and 5.1 (harness pure).
- **Why rejected:** the formulas are methodology, not plumbing; pure domain +
  oracle is the project's spine. Performance is a non-issue at this scale
  (O(n) recursions over ~4k floats; W log W rolling quantiles), and the
  fallback (move a hot loop to the adapter, keep the domain as oracle) is a
  local, contract-preserving change.

### Alternative C — Drop statsforecast; use statsmodels (or own OLS) for the AR(1) fit
- **Description:** estimate the AR(1) with `statsmodels` (already destined
  for Step 6) or a hand-rolled regression, removing the statsforecast (and
  numba) dependency entirely.
- **Pros:** lighter dependency tree; one fewer library.
- **Cons:** overview §6/§7 ratify `statsforecast (baselines)` — dropping it
  is a project-level supersession, not a Stage decision; statsforecast's
  ARIMA is the validated R `arima` port (exactly the kind of recognized,
  oracle-checkable backend the methodology wants).
- **Why rejected:** keep the ratified library where it is faithful to the
  convention. If the numba/CI cost ever bites, this alternative is the
  documented fallback (cheap: only the fit call changes, behind the port).

### Alternative D — Do nothing / decide inside the implementation PR
- **Description:** let the Stage 5.2 implementation pick whatever mix seems
  convenient.
- **Pros:** zero ceremony.
- **Cons:** the spec→implementation mapping decides which numbers the
  confirmatory comparison reports; silent choice = the p-hacking surface the
  methodology forbids (overview §7).
- **Why rejected:** same rationale as ADR 0.0.0052 Alternative F.

## Consequences

### Positive
- Every preregistered convention is a pure, unit-tested function with a named
  oracle — auditable line by line for the thesis defense.
- The port/adapter shape matches the roadmap contract (`BaselineForecaster`
  port; statsforecast adapter) while keeping convention fidelity.
- Swapping or dropping statsforecast later touches one fit call behind the
  port (Alternative C is a documented, cheap fallback).

### Negative
- The project carries `statsforecast` (and transitively `numba`) for a single
  fit — accepted for fidelity to the ratified library list; mitigated by
  minor pinning + `uv.lock` and the documented fallback.
- Two implementations of "quantile math" exist in the ecosystem (domain
  stdlib vs numpy in tests as oracle) — deliberate: the duplication IS the
  verification (ADR 0.0.0021).

### Neutral / trade-offs accepted
- The AR(1) estimation method is delegated to the library default (CSS-ML,
  R-port behavior). The domain doc §3.5 preregisters the **emission** formula,
  not the estimator; the oracle test asserts parameter recovery within a
  declared tolerance on a synthetic series.
- Pure-Python loops in the domain trade vectorized speed for auditability —
  measured in the integration test; acceptable at pilot scale.

## Implementation notes

- Domain services: `modeling/domain/services/quantile_grid_emission.py`
  (degenerate / gaussian / type-7) and
  `modeling/domain/services/baseline_statistics.py` (EWMA path, AR(1) h-step
  forecast). Signatures in the Stage concept §4.
- Adapter: exhaustive dispatch over `BASELINE_FAMILIES`; unknown family
  raises; non-finite emissions raise; the statsforecast fit call sits behind
  a thin injectable seam (`_fit_ar1(returns) -> (mu, phi, sigma2_eps)`) so
  the degenerate-fit path is testable (concept §6 C4/C5).
- `statistics.NormalDist().inv_cdf` is stdlib (AS241) — no scipy in the
  domain; the test fixture pins z_τ values (e.g. Φ⁻¹(0.95) = 1.6448536269…).
- Oracle tolerances are declared per test (ADR 0.0.0021), never implicit.

## References

- Related ADRs: [0.0.0052](./0_0_0052-baseline-quantile-emission-conventions.md)
  (emission conventions), [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md)
  (oracle testing posture), [0.0.0022](./0_0_0022-data-engine-pandas-duckdb.md)
  (library-in-adapter discipline), [3.5.0001](./3_5_0001-target-definition-backward-log-return.md)
  + [4.3.0001](./4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md)
  (1-day-return target semantics), [5.2.0002](./5_2_0002-frozen-train-estimation-causal-state.md)
  (estimation protocol, same Stage), [5.2.0003](./5_2_0003-historical-quantiles-window-252.md)
  (rolling-window width for historical_quantiles, same Stage).
- Internal: domain doc [`quantile-model-training.md`](../domain/modeling/quantile-model-training.md)
  §2.1/§3; `docs/overview.md` §1/§6/§7; `docs/roadmap.md` §Stage 5.2.
- External: statsforecast official docs (Nixtla) — model inventory verified
  2026-07-15; R `stats::arima` (reference implementation ported by
  statsforecast's ARIMA); Hyndman & Athanasopoulos FPP3 Table 5.2 (the √h
  level semantics NOT applicable here); primary sources per domain doc §9.
- Originating issue: [#51](https://github.com/MarceloSanC/financial-forecasting/issues/51).
