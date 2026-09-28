---
title: ADR 6.2.0003 — DM/HLN and Holm are stdlib domain services of record; statsmodels sits behind the InferenceBackend port as their oracle; the R dm.test oracle is read from fixtures by golden tests; no dm_wrapper.py
description: Architecture Decision Record
when-use: Reference when asking why DM and Holm are computed in evaluation.domain, what the InferenceBackend port and the statsmodels adapter are for, how "DM matches R dm.test" and "Holm matches statsmodels" are proven, where each oracle test lives, or why the roadmap's dm_wrapper.py does not exist
keywords: [adr, evaluation, diebold-mariano, hln, holm, statsmodels, hac, multipletests, inference-backend, port, oracle, contract-test, dm-wrapper, r-oracle, golden-test]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.2.0003
decision: Applying ADR 0.0.0056 (human decision), DieboldMariano (rectangular lag h−1 or Bartlett, HLN factor, t_{T−1}, one-sided less, oracle fallback to h = 1, T > h, non-negative losses) and HolmCorrection (step-down with ≤, cumulative-max adjusted p-values capped at 1) are implemented once, stdlib-only, in the domain; the `InferenceBackend` port (DM on two loss sequences, Holm adjust/reject) is satisfied by `StatsmodelsHac` (HAC regression on a constant, kernel uniform/bartlett, maxlags = h−1, use_correction=False, sign of the variance checked by the adapter, HLN and scipy t applied outside; `multipletests(method='holm')`), verified by a `[fake, statsmodels]` contract suite; the R `dm.test` oracle is read from versioned fixtures by an integration golden test; `dm_wrapper.py` is not created; unit tests hold analytic fixtures only.
context_stage: 6.2-paired-inference-dm-mcs-holm
bounded_context: evaluation
---

# ADR 6.2.0003 — DM and Holm of record in the domain; statsmodels as oracle; R as fixtures

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` (revised after Checkpoint A round 1: the placement rule is now the human
decision recorded in ADR 0.0.0056; test locations, tolerances, Holm boundary and
statsmodels sign check fixed).

## Context

- The roadmap (Stage 6.2) declares `InferenceBackend (port-out)` and three adapter
  files under `adapters/out/inference/`: `statsmodels_hac.py`, `arch_mcs.py`,
  `dm_wrapper.py`. Issue #114 (fork R2) left the role of `dm_wrapper.py` open, and the
  overview §7/§8 R-LIBS-1 and ADR 0.0.0020's second bullet read "own implementation
  behind a port". The human decided (ADR 0.0.0056, option A): formula of record in the
  domain; port only where a Python library exists; R oracle as versioned fixtures read
  by golden tests.
- statsmodels reproduces the DM variance through a different route — the Diebold 2015
  §2.1 regression of d_t on an intercept with HAC standard errors — provided
  `kernel='uniform'`, `maxlags=h−1`, `use_correction=False`, with the HLN factor and
  the t_{T−1} applied outside (doc §11.3). It does **not** raise on a negative
  long-run variance (Checkpoint A measured `cov_params()` = −7.03e−3 for a uniform
  kernel), so the adapter must check the sign itself.
- `multipletests` implements Holm with ≤ and the cumulative max but defaults to
  `'hs'` (Holm–Šidák), so `method='holm'` must be explicit; its `reject` compares
  p_(j) with α/(m − j + 1) by division, so exact-boundary agreement with the domain's
  p̃ ≤ α is not guaranteed for arbitrary α (float rounding).
- The R `dm.test` (forecast 8.23.0 `R/DM2.R`) falls back to h = 1 when the long-run
  variance is ≤ 0 with h > 1 (dv = 0 included), stops when it is ≤ 0 with h = 1 or
  when h > n, and scores |e|^power.
- Unit tests are "sem I/O" (pyproject marker) and do not import adapters or libraries
  (6.1 `test_pinball_vs_oracle.py`); integration tests may read files and import
  libraries.

## Decision

1. **Of record = domain.** `diebold_mariano.py` holds a series-level primitive
   (`candidate_losses`, `comparator_losses`, `horizon`, `variance_estimator`) and the
   service over `PairedLossSeries` (ADR 6.2.0001); `holm_correction.py` holds
   `adjust`/`reject` primitives and the per-horizon family. Semantics = the oracle's:
   d = L_cand − L_comp; γ̂_k with divisor T; rectangular (γ̂_0 + 2Σ_{k<h} γ̂_k)/T or
   Bartlett weights 1 − k/h; HLN factor ((T + 1 − 2h + h(h − 1)/T)/T)^{1/2};
   p = P(t_{T−1} ≤ S1*) (ADR 6.2.0002); variance ≤ 0 with h > 1 → recompute everything
   with h = 1 and record `fallback_applied`; variance ≤ 0 with h = 1 → `ValueError`.
   Two deliberate divergences from R: **T > h** is required (h = T is indeterminate —
   ADR 6.2.0001) and **negative losses are rejected** (R would score |L|). Sums with
   `math.fsum`.
2. **Holm record.** The domain's rejection is p̃ ≤ α with p̃ the cumulative-max
   adjusted p-value — the record. The adapter's `holm_rejected` is statsmodels'
   `reject`; exact-boundary parity is asserted only on α ∈ {0.01, 0.025, 0.05, 0.10,
   0.20} with m ≤ 7, and the boundary p̃ = α case is a domain-only analytic test.
3. **Port of primitives.** `evaluation/application/ports/out/inference_backend.py`:
   `InferenceBackend(Protocol)` with `diebold_mariano(...)` (returns the domain's
   `DieboldMarianoResult`), `holm_adjusted(p_values)` and `holm_rejected(p_values,
   alpha)`. Real adapter `StatsmodelsHac` (`adapters/out/inference/statsmodels_hac.py`),
   which reads `cov_params()` and applies the fallback on a variance ≤ 0 itself, and
   takes its p-value from `scipy.stats.t`. Input validation (lengths, finiteness,
   non-negativity, T > h, p-values in [0, 1], α in (0, 1)) is one domain validator
   called by the domain primitives, the fake and the adapter (6.1
   `scoring_input_validation` pattern).
4. **Where each check lives.**
   - Unit (`tests/unit/features/evaluation/`), analytic only, roadmap names kept:
     `test_dm_vs_r_oracle.py` (hand-computable DM cases: sign, h = 1 variance,
     rectangular vs Bartlett, HLN factor, fallback, errors) and
     `test_holm_vs_statsmodels.py` (Holm 1979 worked cases, cap at 1, input order,
     ties, boundary p̃ = α).
   - Contract (`tests/contract/features/evaluation/test_inference_backend_contract.py`),
     `[fake, statsmodels]`: DM (random loss pairs with fixed seed, the fallback, error
     parity) and Holm (random p-value lists) — "Holm matches statsmodels" and the scipy
     cross-check of `student_t.py` live here.
   - Integration (`tests/integration/features/evaluation/`): the golden test that reads
     `tests/fixtures/r_oracle/dm_test_cases.json` and compares the domain primitive, and
     the provenance test (ADR 6.2.0006).
   - Tolerances are absolute + relative, declared per quantity in the technical.
5. **No `dm_wrapper.py`**; the roadmap's `arquivos_a_criar` is corrected in this
   Stage's PR (authority: this ADR and ADR 0.0.0056).
6. No use case consumes `InferenceBackend` in 6.2 (as `ScoringBackend`, ADR 6.1.0001
   item 5); runtime use is an option of 6.4.

## Decision record

```
[decision:C] 6.2-R2 — role of dm_wrapper.py (placement rule decided by the human in ADR 0.0.0056)
Escolha: not created; R dm.test as versioned fixtures read by an integration golden test; statsmodels is the Python oracle behind InferenceBackend · Alternativas: (a) replay adapter for recorded R answers; (b) DM kernel in an adapter; (c) R at runtime · Degrau (C): 1 (ADR 0.0.0056, human; ADR 6.1.0001 pattern)
Base: forecast 8.23.0 R/DM2.R "if (dv > 0) … else if (h == 1) stop(\"Variance of DM statistic is zero\") else { warning(…); return(dm.test(e1, e2, alternative, h = 1, power, varestimator)) }" [verificado]
Sensibilidade pré-registrada: Bartlett (convention #14, already) · Reversível: sim
```

## Alternatives considered

### Alternative A — `dm_wrapper.py` replays the recorded R answers as a port adapter
- **Why rejected:** ADR 0.0.0056 Alternative C (no production consumer; answers only
  recorded inputs; test data in production code).

### Alternative B — DM kernel in an adapter, domain as bookkeeping
- **Why rejected:** ADR 0.0.0056 Alternative B.

### Alternative C — Call R at runtime
- **Why rejected:** CI and the dev image have no R.

### Alternative D — Do nothing (only R fixtures, no statsmodels)
- **Why rejected:** the roadmap declares the port and the DoD asks "Holm matches
  statsmodels"; the HAC regression checks the variance by an independent route.

## Consequences

### Positive
- One implementation of DM/Holm; three independent references (R fixtures,
  statsmodels HAC regression, scipy t).
- The `'hs'` default, the `use_correction` divergence for h > 1 and the silent
  negative variance of statsmodels are neutralised once, in the adapter.

### Negative
- A port with no production consumer in 6.2 (as in 6.1).
- The adapter re-states the fallback rule (it must, to satisfy the port contract).
- The unit files `test_*_vs_*` keep the roadmap names but hold analytic fixtures; the
  library/R comparisons live in contract/integration files (recorded as a path
  deviation in the concept).

## Implementation notes

- Port + fake + fake leg before the adapter, with the one-Task `port-coverage`
  baseline entry of ADR 6.1.0005.
- statsmodels pinned `>=0.15,<0.16` (0.14.6 is in `uv.lock` transitively via
  statsforecast, which requires `>=0.14.5`).

## References

- Diebold & Mariano (1995); Harvey, Leybourne & Newbold (1997); Diebold (2015) §2.1;
  Holm (1979) — citations in the domain doc §11.1–§11.2.
- forecast 8.23.0 `R/DM2.R`; statsmodels `stats.multitest.multipletests`,
  `OLSResults.get_robustcov_results`.
- Related ADRs: [0.0.0010](./0_0_0010-paired-inference-dm-holm-mcs.md),
  [0.0.0020](./0_0_0020-statistics-in-domain-over-value-objects.md),
  [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md),
  [0.0.0056](./0_0_0056-own-statistics-in-domain-r-oracle-as-fixtures.md),
  [6.1.0001](./6_1_0001-scoring-libraries-as-oracle-backend-behind-port.md),
  [6.1.0005](./6_1_0005-transient-port-coverage-baseline-between-port-and-first-adapter.md),
  [6.2.0001](./6_2_0001-paired-loss-series-single-aligned-matrix-vo.md),
  [6.2.0002](./6_2_0002-student-t-p-value-stdlib-in-domain.md),
  [6.2.0006](./6_2_0006-r-oracle-fixtures-provenance-and-scope.md).
- Domain doc §6.1, §6.3, §6.4, §11.3; issue [#114](https://github.com/MarceloSanC/financial-forecasting/issues/114) (fork R2).
