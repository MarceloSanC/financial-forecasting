---
title: ADR 7.2.0002 — CQR and NexCP implemented once in the inference domain (exact rational rank and weights); MAPIE 1.5 as contract oracle behind ConformalBackend; NexCP oracle frozen from the authors' code
description: Architecture Decision Record
when-use: Reference when touching ConformalCalibrator, the ConformalBackend port or the MAPIE adapter, when a conformal number disagrees with MAPIE, or when asking how ranks, ties, weights and infinite limits are computed
keywords: [adr, conformal, cqr, nexcp, mapie, oracle, contract-suite, fixture, rank, weighted-quantile, fractions, infinity, inference, domain]
status: accepted
created_at: 2026-10-17
updated_at: 2026-10-18
adr_id: 7.2.0002
decision: The asymmetric split-CQR and the NexCP weighted variant are implemented once, stdlib-only, in inference/domain (ConformalCalibrator) as the implementation of record, with the rank ⌈(n+1)(1−α_tail)⌉ and the NexCP cumulative weights in exact rational arithmetic over the decimal of each level and +∞ (no clipping) when the rank exceeds n or the finite weighted mass never reaches 1−α_tail; MAPIE (>=1.5,<1.6, in dependencies) is the oracle of the unweighted variant behind a ConformalBackend port, compared in a [fake, mapie] contract suite only at calibration sizes where MAPIE's "higher" rank coincides with the domain's; the NexCP oracle is a frozen fixture generated from the threshold block of the authors' splitCP_LS; no library is called at runtime.
context_stage: 7.2-conformal-cqr
bounded_context: inference
---

# ADR 7.2.0002 — Own CQR/NexCP in the domain, MAPIE as oracle, NexCP fixture

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 7.2 concept (issue #158), 2026-10-17. Closes fork (a) of
the issue and decision B9 of the inference domain doc ("papel do MAPIE
decidido na 7.2").

## Context

The mechanics are fixed (ADR 0.0.0008 items 2, 4, 5; doc §4.2, §4.5): one-sided
scores E^lo = q̂_lo − Y, E^hi = Y − q̂_hi, correction = ⌈(n+1)(1−α_tail)⌉-th
smallest score (Romano et al. 2019), and the NexCP sensitivity
Q_{1−α}(Σ w̃_i δ_{R_i} + w̃_{n+1} δ_{+∞}) with w̃_i = w_i/(w_1+…+w_n+1)
(Barber et al. 2023, Eqs. (10)–(11)), Q_τ being "the smallest possible
τ-quantile" (footnote 1). What was open is who computes it and against what.

Facts that drive the decision:

- **MAPIE 1.5.0** (`regression/quantile_regression.py`; read 2026-08-05 and in
  the issue's research): q = (1 − α)(1 + 1/n) with `np.quantile(...,
  method="higher")`, α/2 per tail by default (`symmetric_correction=False`),
  `sample_weight` accepted and unused — no NexCP. `method="higher"` takes the
  0-based index ⌈q(n−1)⌉, so its rank minus one is
  ⌈(1−α)n − (1−α)/n⌉ while the domain's is ⌈(1−α)n − α⌉ (**derivation**): the
  two differ by +1 exactly when an integer lies in
  [(1−α)n − α, (1−α)n − (1−α)/n) — e.g. α = 0.10 and n ≡ 9 (mod 10). At
  n = 252 the three tail levels of the grid (0.02, 0.10, 0.25) coincide (ranks
  248, 228, 190), which is doc §4.12's statement. MAPIE also refuses
  n < max(1/α, 1/(1−α)) (`utils.py::_check_alpha_and_n_samples`) and accepts
  only fitted estimators, so predictions enter through a thin wrapper.
- **`yromano/cqr`** (`nonconformist/nc.py`) clips the index at n − 1, which
  contradicts Angelopoulos & Bates (2023) App. D ("q̂ = ∞" when α < 1/(n+1)).
- **puncc 0.9.3** implements both but requires numpy < 2 (incompatible with
  the lock).
- **Authors' NexCP code** (`nonexchangeable_conformal.zip`,
  `simulation_script_for_supplement.ipynb`, cell 3, `splitCP_LS`; verified
  2026-10-17 by a zero-context verifier): `weights_calib = weights[inds_even] /
  (np.sum(weights[inds_even])+weights[-1])` with `weights[-1] = 1` (test
  point); `ind_thresh = np.min(np.where(np.cumsum(weights_calib[ord_R])>=1-alpha))`;
  `calib_thresh = np.inf` when `np.sum(weights_calib) < 1-alpha`. The +∞ atom
  is implicit in the denominator; the criterion is "≥". The geometric weights
  `rho**(np.arange(n,0,-1))` are built by the caller (cell 6).
- Float pitfalls: 1 − 0.9 = 0.09999999999999998 in float64, so α_hi computed in
  floats can move a rank at a boundary; cumulative float sums of weights can
  land on either side of 1 − α at a boundary.

## Decision

`[decision:C] 7.2-IMPL — implementation of record and oracles`
`Escolha: own stdlib formula in inference/domain; MAPIE oracle behind a port, contract at coincidence n; NexCP fixture from the authors' code · Alternativas: MAPIE as backend of record; MAPIE only as a dev/test dependency without port; puncc · Degrau: 1 (ADR 0.0.0056 and 6.1.0001: own formula of record, library as oracle behind a port) e 2 (MAPIE is the reference oracle of the unweighted variant)`
`Base: Romano et al. 2019 (arXiv:1905.03222) Eq. (11), Thm 2; Barber et al. 2023 (arXiv:2202.13415v5) Eqs. (10)–(11), footnote 1 "Qτ(·) denotes the smallest possible τ-quantile"; authors' splitCP_LS (verified: parcial→corrigido — atom implicit, normalization over calibration weights + 1); MAPIE 1.5.0 quantile_regression.py (B9 verified)`
`Verificado: sustenta (Barber footnote 1, Eqs. (10)–(11)); parcial→corrigido (splitCP_LS location and normalization)`
`Sensibilidade pré-registrada: NexCP ρ = 0.99 (ADR 0.0.0008) · Reversível: sim, até a âncora da r2`

1. **`ConformalCalibrator`** in `features/inference/domain/services/`,
   stdlib-only (`domain-purity`, `inference-no-torch-leak` and a new
   `inference-no-mapie-leak` contract forbidding `mapie`, `numpy`, `sklearn`,
   `scipy` in inference application/domain).
2. **Exact arithmetic.** Each level enters as `Fraction(repr(level))` (its
   shortest decimal, the same exact-float convention as `PreregistrationHash`,
   ADR 6.5.0001); α_lo = τ_lo, α_hi = 1 − τ_hi exactly; the rank
   k = ⌈(n+1)(1 − α)⌉ is an exact integer; NexCP weights are `exact_level(ρ)^(n+1−i)`, with
   `exact_level(ρ) = Fraction(repr(ρ))` (0.99 is 99/100, not the binary value of
   the float)
   and the cumulative comparison with 1 − α is exact. Scores themselves are
   floats (differences of persisted values) and the correction returned is
   one of them.
3. **Ties and infinity.** Unweighted: the k-th smallest score (ties counted
   with multiplicity); k > n ⇒ correction = +∞, flagged, never clipped.
   Weighted: scores sorted ascending; the threshold is the smallest score R
   such that the summed normalized weight of all scores ≤ R is ≥ 1 − α
   (equal scores enter together; the value is the same as the authors'
   per-element `cumsum` on the sorted order); if the finite mass is < 1 − α ⇒
   +∞. With ρ = 1 the weighted rule reproduces the unweighted rank exactly
   (property test).
4. **`ConformalBackend` port** (`inference/application/ports/out/`), primitive
   in/out: given calib lower, upper, realized and one tail α, return the two
   corrections of the unweighted variant. Fake in `tests/fakes/`; the real
   adapter `MapieCqrBackend` (`inference/adapters/out/mapie/`) wraps the
   predictions in prefit estimators and reads each correction from the MAPIE
   attribute that stores the conformal quantile when the API exposes it, or
   else recovers it by subtraction q̂ − L from `predict_interval`. The contract
   suite `[fake, mapie]` compares each leg with the domain at calibration sizes
   chosen by a test helper that computes both ranks (all ≥ 49, n = 252
   included), with scores away from ties and `abs_tol = 1e-12` when the value
   comes from a subtraction. A case run on the `mapie` leg only pins that
   MAPIE differs by +1 at a divergent n (the reason the domain, not MAPIE, is
   of record). MAPIE raises for small n in two ways, both propagated by the
   adapter: its own check refuses n < max(1/α_pair, 1/(1−α_pair)) (n < 25 for
   α_tail = 0.02), and `np.quantile` raises when (1 − α_tail)(1 + 1/n) > 1
   (n from 25 to 48 for α_tail = 0.02).

   > ⚠️ **Errata (2026-10-17):** measured against MAPIE 1.5.0, the small-n refusal
   > works differently. With α_tail = 0.02, `conformalize` (α_pair = 0.04) refuses
   > n < 25, and `predict_interval` calls the same `_check_alpha_and_n_samples` with
   > α_pair/2 = 0.02 and refuses every n < 50, with "Number of samples of the score
   > is too low". The `np.quantile` branch is never reached. The contract suite runs
   > with n ≥ 50 (Stage 7.2 technical §7, `[deviation]` C5). Nothing else in this
   > ADR changes.
5. **NexCP oracle = frozen fixture** under `tests/fixtures/nexcp_oracle/`: a
   generator that transcribes the threshold block of `splitCP_LS` (the zip's
   URL and sha256, notebook cell id and numpy version in a provenance block;
   inputs as `{"dec", "hex"}`, ADR 6.2.0006 format) and a golden test against
   the domain; cases keep the cumulative weight at the chosen index at least
   1e-9 away from 1 − α so float and exact arithmetic select the same score.
   CI never downloads the zip.
6. **No runtime cross-check** (ADR 6.4.0008): no use case calls the backend.
7. **Dependency:** `mapie>=1.5,<1.6` in `[project].dependencies` (the real leg
   runs in CI without `skipif`, the 6.1/6.2 posture).

## Alternatives considered

### Alternative A — MAPIE as backend of record
- **Pros:** less own code.
- **Cons:** no weights (NexCP impossible); its rank differs from the
  preregistered ⌈(n+1)(1−α)⌉ for some n; refuses small n instead of returning
  +∞; needs estimator wrappers in the confirmatory path.
- **Why rejected:** the preregistered formula must be the one computed;
  ADR 0.0.0056 posture.

### Alternative B — MAPIE only in a test, no port
- **Pros:** no port/fake.
- **Cons:** breaks the "port where a Python library can be wrapped" rule
  (ADR 0.0.0056) and the roadmap's `ConformalBackend`; the port-coverage gate
  would not see the oracle.
- **Why rejected:** rung 1.

### Alternative C — Floats for ranks and cumulative weights
- **Pros:** simpler code, matches numpy.
- **Cons:** `1 − 0.9` and float cumsums can move the selected score at a
  boundary, so "the preregistered rule" would depend on rounding.
- **Why rejected:** exact arithmetic is cheap (≤ 253 terms) and removes the
  ambiguity; the fixture margin keeps the float oracle comparable.

### Alternative D — Clip the rank at n (as `yromano/cqr`)
- **Why rejected:** contradicts Angelopoulos & Bates App. D; with n = 252 it
  never triggers on the grid, so the choice only matters for correctness.

## Consequences

### Positive
- The number reported is exactly the preregistered rule; MAPIE and the
  authors' code each certify the part they implement.

### Negative
- A wrapper around MAPIE's estimator API and a fixture generator to maintain.

### Neutral / trade-offs accepted
- MAPIE certifies only the coinciding sizes; the divergence is documented, not
  hidden.

## References

- Romano, Y.; Patterson, E.; Candès, E. (2019). arXiv:1905.03222.
- Barber, R. F.; Candès, E. J.; Ramdas, A.; Tibshirani, R. J. (2023). *Annals of Statistics*, 51(2). DOI: 10.1214/23-AOS2276; arXiv:2202.13415v5 (Eqs. (10)–(11), footnote 1).
- Angelopoulos, A. N.; Bates, S. (2023). DOI: 10.1561/2200000101 (App. D).
- Authors' code: https://rinafb.github.io/code/nonexchangeable_conformal.zip (`splitCP_LS`).
- MAPIE 1.5.0 `mapie/regression/quantile_regression.py`, `mapie/utils.py`.
- Related ADRs: [0.0.0008](./0_0_0008-native-quantiles-with-conformal-benchmark.md),
  [0.0.0056](./0_0_0056-own-statistics-in-domain-r-oracle-as-fixtures.md),
  [6.1.0001](./6_1_0001-scoring-libraries-as-oracle-backend-behind-port.md),
  [6.2.0006](./6_2_0006-r-oracle-fixtures-provenance-and-scope.md),
  [6.3.0002](./6_3_0002-rugarch-oracle-frozen-as-test-fixtures.md),
  [6.4.0008](./6_4_0008-no-runtime-library-cross-check-in-gold.md),
  [6.5.0001](./6_5_0001-preregistration-canonical-toml-hashed-value-object.md).
- Inference domain doc §4.2, §4.5, §4.10, §4.12; issue [#158](https://github.com/MarceloSanC/financial-forecasting/issues/158).
