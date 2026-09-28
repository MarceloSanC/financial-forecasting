---
title: ADR 6.1.0001 — Scoring formulas are stdlib domain services of record; sklearn and scoringrules sit behind the ScoringBackend port as the oracle backend
description: Architecture Decision Record
when-use: Reference when asking why pinball/CRPS_Q/interval score are computed in evaluation.domain instead of by a library, what the ScoringBackend port is for when no use case consumes it, or how the "matches sklearn/scoringrules" acceptance criterion is proven
keywords: [adr, evaluation, scoring, pinball, crps, interval-score, winkler, sklearn, scoringrules, port, oracle, contract-test, domain-purity]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.1.0001
decision: The scoring formulas (pinball per level, CRPS_Q, interval score per symmetric pair) are implemented once, as stdlib-only domain services that are the implementation of record; scikit-learn and scoringrules are confined to two adapters behind a single `ScoringBackend` port (primitive in/out), and the `[fake, sklearn, scoringrules]` contract suite on that port is the per-unit oracle check required by the Stage DoD.
context_stage: 6.1-scoring-and-calibration-metrics
bounded_context: evaluation
---

# ADR 6.1.0001 — Domain formulas of record; libraries as oracle backend behind `ScoringBackend`

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 6.1 must deliver pinball, CRPS and interval (Winkler) scores that
"match sklearn/scoringrules and analytic fixtures" (roadmap, Stage 6.1 DoD).
Four project sources speak to where the math and the libraries live:

- **Overview §7** (line "Bibliotecas confiáveis entram como adapters por trás
  de portas: … `sklearn`/`scoringrules` (pinball, Winkler/CRPS)") and the
  roadmap's inherited constraint ("bibliotecas … vivem em adapters").
- **Roadmap Stage 6.1** names the contract `ScoringBackend (port-out)` and the
  files `adapters/out/scoring/{sklearn_scoring.py, scoringrules_backend.py}`.
- **ADR 0.0.0020** — "The statistical operations expressed as pure
  functions/services over these VOs — pinball, CRPS, … — depend only on the
  standard library"; libraries "that compute or accelerate these quantities"
  live behind ports.
- **ADR 0.0.0021** — correctness is proven per unit against an analytic
  fixture and a library oracle, within a declared tolerance.

The precedent inside the project is **ADR 5.2.0001**: the preregistered
formulas live in the domain (stdlib), the library stays behind the port for
what it genuinely contributes, and "the library is a means, validated against
the oracle — never the authority".

What is *not* written anywhere is the runtime role of the port when the domain
already computes the number: pinball, CRPS_Q = 2·P̄_G and IS_α are closed-form
sums over the grid (domain doc §3.1–§3.3) — a library adds no estimation step
(unlike the AR(1) fit of 5.2) and no measurable speed-up at pilot scale
(T ≈ 10³ points × K ≈ 7 levels per series).

A second mechanical force: scikit-learn exposes only `mean_pinball_loss`
(`alpha` = level, one level per call); scoringrules exposes
`quantile_score`, `crps_quantile` and `interval_score` (`alpha` =
**miscoverage** for the interval score — domain doc §11.3). A port whose
methods only one library can satisfy would split into two ports.

## Decision

1. **Implementation of record = domain.** `PinballScore`, `CrpsScore` and
   `IntervalScore` in `evaluation/domain/services/` are stdlib-only and are the
   only code path that produces the project's numbers. Each exposes a
   per-point kernel (`ρ_τ(y − q)`, `(2/K)·Σ_k ρ_{τ_k}`, `IS_α(l, u; y)`) **and
   a series-level primitive function** (`mean_pinball`, `mean_crps_quantile`,
   `mean_interval_score` over `Sequence[float]`) that the services themselves
   call when aggregating a `CoverageSeries` (ADR 6.1.0002). The same domain
   module holds the input validator (equal lengths, level/miscoverage in
   (0, 1), lower ≤ upper, grid shape) called by the domain functions, the fake
   and both adapters — one copy, so `check_fake_parity` has nothing to flag.
   The miscoverage of a pair is always computed as α = 2·τ_l and the nominal
   as 1 − 2·τ_l (domain doc §2.4); `1 − (τ_u − τ_l)` is avoided because it
   carries float noise (0.10000000000000009 for (0.05, 0.95)).
2. **One port, three methods, primitive in/out.**
   `evaluation/application/ports/out/scoring_backend.py` declares
   `ScoringBackend(Protocol)` with `mean_pinball(realized, quantiles, level)`,
   `mean_crps_quantile(realized, quantile_grid, levels)` and
   `mean_interval_score(realized, lower, upper, miscoverage)`, all keyword-only,
   `Sequence[float]` in, `float` out. The parameter is named `miscoverage`, not
   `alpha`, so the two library conventions (sklearn `alpha` = level;
   scoringrules `interval_score` `alpha` = miscoverage) are neutralised at the
   port, not left to each caller.
3. **Two real adapters satisfy the whole port.**
   - `ScoringrulesBackend` calls the native functions (`quantile_score`,
     `crps_quantile`, `interval_score`) with the backend fixed explicitly.
   - `SklearnScoring` computes `mean_pinball` natively
     (`mean_pinball_loss`) and the other two **through the documented
     identities** CRPS_Q = 2·mean_k P̄_{τ_k} (domain doc §3.2) and
     IS_α = (2/α)·[ρ_{α/2}(y − l) + ρ_{1−α/2}(y − u)] (domain doc §3.3,
     Bracher et al. 2021 App. A Eq. (5)). The sklearn leg thus checks the
     identity against scoringrules' direct Eq. (43) formula — an independent
     path, which matters because `crps_quantile` alone is **not** independent
     of the pinball (domain doc §11.3).
4. **The oracle check is the port's contract suite.** The fake
   (`FakeScoringBackend`, `tests/fakes/features/evaluation/`) delegates to the
   **same series-level domain functions the services use** (no averaging of
   its own), so the oracle covers the code of record; the suite `tests/contract/features/evaluation/` is
   parametrised over `[fake, sklearn, scoringrules]` on shared fixtures
   (analytic cases, tie-free random grids, Dirac grids) with a declared
   numeric tolerance (ADR 0.0.0021). "Domain matches the libraries" is
   therefore enforced by the same `port-coverage` machinery as every other
   port (LAYOUT §7, issue #62). The suite is **in addition to** the unit files
   the roadmap lists (`tests/unit/features/evaluation/test_pinball_vs_oracle.py`,
   `test_crps_interval_score.py`, `test_degeneracy_gate.py`), which keep the
   analytic fixtures and oracle checks. The library oracle reaches **only**
   pinball, CRPS_Q and IS; marginal coverage, PICP, MPIW and the degeneracy
   gate are verified by analytic fixtures only.
5. **No use case consumes the port in 6.1.** The gold builders (6.4) consume
   the domain services. Using the backend at runtime (e.g. a gold quality check
   "domain vs library agreement") is left to 6.4 as an option, not a
   commitment.
6. **Dependencies.** `scikit-learn` (already in `uv.lock` transitively, 1.9.0)
   is declared explicitly, `>=1.9,<2.0`; `scoringrules` is added
   `>=0.11,<0.12` (0.11.0 is the version whose code the domain doc verified),
   both in `dependencies` for the same reason as statsforecast/lightgbm: the
   real legs of the contract suite run in CI. A new import-linter contract
   forbids `sklearn`, `scoringrules`, `numpy` and `scipy` in
   `evaluation.{application,domain}`.

## Alternatives considered

### Alternative A — Libraries as test-only oracles (dev dependencies), no port

- **Description:** domain services only; sklearn/scoringrules imported only
  by unit tests; no `ScoringBackend`, no adapters.
- **Pros:** the most direct path; no port without a production consumer; no
  runtime dependency on scoringrules.
- **Cons:** removes a contract the roadmap declares
  (`contratos_introduzidos: ScoringBackend (port-out)`) and the placement the
  overview §7 ratifies ("sklearn/scoringrules … como adapters por trás de
  portas"); the oracle check becomes an import in a unit test, outside the
  `port-coverage` gate.
- **Why rejected:** it changes the Stage frontier fixed by higher sources
  (overview > roadmap > concept); a Stage cannot supersede them. Recorded as
  the documented simplification if the overview/roadmap are ever revised.

### Alternative B — Library as the runtime kernel, domain as bookkeeping

- **Description:** the domain validates inputs and selects rows/pairs; the
  numbers come from the library through the port.
- **Pros:** "maximal library use" reading of overview §1.
- **Cons:** the domain cannot call an application port (LAYOUT §3); the math
  would have to move to a use case, which ADR 0.0.0020 Alternative B rejects
  ("misplaces the scientific core"); the conventions (ρ_τ scale, equal
  weights, rearranged vector, miscoverage) would depend on library defaults.
- **Why rejected:** contradicts ADR 0.0.0020 and the 5.2.0001 precedent.

### Alternative C — Two ports (`PinballBackend` for sklearn, `ScoringBackend` for scoringrules)

- **Description:** segregate the interface by what each library offers
  natively.
- **Pros:** each adapter implements only native calls.
- **Cons:** two Protocols, two fakes, two contract suites for the same
  concern; the sklearn leg would never test CRPS_Q or IS, losing the
  independent check of the IS identity.
- **Why rejected:** more ceremony and less verification than decision item 3.

### Alternative D — Do nothing (let each metric pick its oracle ad hoc)

- **Why rejected:** ADR 0.0.0020 Alternative C — guarantees drift in where
  libraries live and how their conventions are neutralised.

## Consequences

### Positive

- One implementation of each formula; the libraries can never become the
  authority silently.
- The DoD "matches sklearn/scoringrules" is a gated contract, not a
  convention.
- The IS and CRPS_Q identities are verified by two independent routes.

### Negative

- A port with no production consumer in 6.1; its only caller is the contract
  suite until 6.4 decides otherwise.
- `scoringrules` becomes a runtime dependency (plus whatever it pulls
  transitively — to be measured by `uv lock` in the technical phase).

### Neutral / trade-offs accepted

- The sklearn adapter composes identities instead of calling a native
  CRPS/IS; accepted because that composition is exactly what is being
  cross-checked.

## Implementation notes

- Files: `evaluation/application/ports/out/scoring_backend.py`,
  `evaluation/adapters/out/scoring/{sklearn_scoring.py,scoringrules_backend.py}`,
  `tests/fakes/features/evaluation/fake_scoring_backend.py`,
  `tests/contract/features/evaluation/test_scoring_backend_contract.py`.
- Fixtures must avoid exact ties `y == q` in coverage-style indicators only;
  for the scores ties are harmless (the loss is zero either way, domain doc
  §3.1/§4.5), and one tie case is kept to prove it.
- Tolerance is declared per test (float64 summation-order noise, order
  1e-12), never implicit.

## References

- Related ADRs: [0.0.0020](./0_0_0020-statistics-in-domain-over-value-objects.md),
  [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md),
  [0.0.0009](./0_0_0009-pinball-primary-crps-complementary.md),
  [0.0.0053](./0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md),
  [5.2.0001](./5_2_0001-baseline-math-in-domain-statsforecast-ar1-fit.md),
  [6.1.0002](./6_1_0002-coverage-series-aligned-input-vo.md).
- Domain doc: [`probabilistic-forecast-evaluation.md`](../domain/evaluation/probabilistic-forecast-evaluation.md)
  §2.3, §3.1–§3.3, §11.3.
- Overview §7; roadmap Stage 6.1; issue [#77](https://github.com/MarceloSanC/financial-forecasting/issues/77).
