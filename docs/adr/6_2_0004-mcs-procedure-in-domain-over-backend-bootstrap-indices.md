---
title: ADR 6.2.0004 — The MCS 'R' procedure is computed in the domain over bootstrap indices supplied by a second port, McsBackend (arch as generator of record), which also exposes Politis–White block lengths; arch.MCS is the oracle in an integration test
description: Architecture Decision Record
when-use: Reference when asking where the Model Confidence Set is computed, why there are two ports (InferenceBackend and McsBackend), what McsBackend exposes and who consumes it, how "MCS matches arch with the same seed and block" is proven, how reproducibility of the bootstrap is recorded, or how MCS membership, ties and degenerate inputs are handled
keywords: [adr, evaluation, mcs, model-confidence-set, hansen-lunde-nason, arch, stationary-bootstrap, moving-block, politis-white, bootstrap-indices, port, oracle, membership, provenance]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.2.0004
decision: ModelConfidenceSet (statistic 'R', variance computed once, elimination by e_R, one model per step, MCS p-value = cumulative max, membership p ≥ α) is a stdlib domain service over a `PairedLossSeries` and a `BootstrapIndices` VO that carries the index generator's provenance; resampling is delegated through a second port `McsBackend` with exactly two methods (`optimal_block_length`, `bootstrap_indices`) whose inputs pass one domain validator, satisfied by `ArchMcs` — the generator of record for confirmatory indices, reproducing arch.MCS's own index stream for an int seed — and consumed in production by the 6.4 use case; `arch.MCS` itself is the oracle only in an integration test that imports arch directly.
context_stage: 6.2-paired-inference-dm-mcs-holm
bounded_context: evaluation
---

# ADR 6.2.0004 — MCS in the domain over backend-supplied bootstrap indices; `McsBackend`

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` (revised after Checkpoint A rounds 1–2: reference MCS removed from the port,
single validators (bootstrap request; block-length request), generator provenance, degenerate-input errors, production consumer
named).

## Context

- Issue #114 scope 4: `ModelConfidenceSet` is a domain service ("the control logic of
  the procedure"); membership and MCS p-value follow HLN 2011 Definitions 2/4 and
  Theorem 3; "the stationary bootstrap sits behind the port". ADR 0.0.0020 lists
  "MCS bookkeeping" in the domain and `arch` "for MCS/bootstrap" in adapters.
- DoD: "MCS matches `arch` with the same seed and the same block, and membership
  follows HLN Definition 4" — informative only if the domain computes the procedure
  independently of `arch.MCS`.
- `arch.bootstrap.MCS` (8.0.0) builds `StationaryBootstrap(block_size, np.arange(T),
  seed=seed)` (or `MovingBlockBootstrap`), and in `_compute_r` takes the resampled rows
  of each replication as `data[0][0]`; the pairwise variance is computed once; the step
  statistic is the max standardized d̄_ij among the included models; the step p-value
  is `(test_stat < simulated).mean()`; p-values are the cumulative max, the survivor
  gets 1.0; `included` uses `> size`. With an int seed the stream is
  `numpy.random.default_rng(seed)` and reproducible; a Generator seed or `None` is not.
- Two `arch` quirks the domain must not inherit: on an exact tie at the max,
  `loc.squeeze()[0]` is the first tied **pair**, so arch removes both its row-model and
  its column-model — possibly the better of the two — in one step; and `>` instead of
  HLN's `≥` at the membership boundary (doc §11.3).
- Degenerate inputs: a constant differential gives a zero bootstrap variance (arch
  divides by it; only the diagonal is protected). `MovingBlockBootstrap` raises for
  l > n, and l = n yields every replication equal to the sample (zero variance) — so
  the moving-block scheme needs l < n.
- `optimal_block_length` (Politis & White 2004 with Patton et al. 2009) returns columns
  `"stationary"`/`"circular"` (the docstring's `b_sb`/`b_cb` are wrong), float values.
- One Protocol cannot be satisfied by both libraries: statsmodels has no block
  bootstrap and arch has no Holm/uniform-kernel HAC.
- The domain has no RNG of record, so the 6.4 use case must call `McsBackend` in
  production (block estimates → block rule → indices → domain MCS).

## Decision

1. **Domain computes the MCS.** `model_confidence_set.py`:
   `ModelConfidenceSet.evaluate(series, *, bootstrap, alpha) -> McsReport` —
   d̄_ij; bootstrap means of every column per replication; recentred squared
   differences averaged once into var̂(d̄_ij); t_ij = d̄_ij/√var̂; per step over the
   included models, T_R = max t_ij and its bootstrap distribution max t*_ij; step
   p-value = share of replications with T_R **<** T*_R (arch's convention, so numbers
   match); eliminate the row model of the max (e_R,M); on an exact tie, **one** model —
   the first row-model in the VO's model order; MCS p-value = cumulative max
   (Definition 4), last survivor 1; **membership p̂ ≥ α** (Theorem 3). Only statistic
   'R'. Preconditions (`ValueError`): `alpha ∈ (0, 1)`; `bootstrap.reps ≥ MIN_MCS_REPS`
   (1000, convention #16); `bootstrap.n_obs == T`; **no pair with a constant
   differential** (var(L_i − L_j) > 0, doc §6.5 — the MCS owns this check, ADR
   6.2.0001); **any estimated var̂(d̄_ij) ≤ 0** (e.g. a moving block that reproduces the
   sample).
2. **`BootstrapIndices` VO** — scheme (`stationary` | `moving_block`), `block_size ≥ 1`
   int, `seed` int, `n_obs ≥ 2`, reps × n_obs indices in [0, n_obs), and a
   **`generator`** string naming the index generator of record (e.g.
   `"arch 8.0.0 StationaryBootstrap / numpy default_rng"`); `McsReport` copies
   scheme, block, seed, reps and generator. Reproducing a confirmatory MCS therefore
   depends on the pinned `arch` and `numpy` versions; the report says which.
3. **Single validator** for bootstrap requests in the domain
   (`n_obs ≥ 2`, `block_size ≥ 1`, `reps ≥ 1`, `seed` an `int` (not `bool`), known
   scheme, and `block_size < n_obs` for `moving_block`), called by the VO, the fake and
   the adapter — the same errors in every leg (6.1 `scoring_input_validation` pattern).
   A second named validator, `validate_block_length_request(series)` (minimum length
   measured in the technical, finite values, **non-constant** series), guards
   `optimal_block_length` in fake and adapter alike: on a constant series `arch` 8.0.0
   returns `nan` (all zeros) or a finite spurious value (10.51 for a constant 0.3),
   while the fake would return its constant — no parity without the validator
   (Checkpoint A round 2).
4. **Block rule in the domain:** `ModelConfidenceSet.block_length(series, *,
   block_estimates)` — one b̂_sb per unordered model pair, all pairs required; returns
   max(h, ⌈max b̂_sb⌉) (ADR 6.2.0005).
5. **Second port, two methods** — `evaluation/application/ports/out/mcs_backend.py`:
   `McsBackend(Protocol)` with `optimal_block_length(series) -> float` (b̂_sb ≥ 0,
   finite) and `bootstrap_indices(n_obs, block_size, reps, seed, scheme) ->
   BootstrapIndices`. Real adapter `ArchMcs` (`adapters/out/inference/arch_mcs.py`)
   builds the bootstrap exactly as `arch.MCS` does (`np.arange(n_obs)`, int seed) and
   reads `optimal_block_length(...)["stationary"]`; it is the **generator of record**
   for confirmatory indices. The fake (`tests/fakes/features/evaluation/`) generates
   indices with `random.Random(seed)` (generator `"stdlib random.Random"`) and returns,
   from `optimal_block_length`, a constant set at construction (default 1.0) after the
   same input validation — it serves application tests, not estimation.
6. **Verification.** `[fake, arch]` contract suite (index shape/range/determinism,
   different seeds differ, moving-block contiguity and l < n, stationary wrap-around;
   b̂_sb finite and ≥ 0; error parity). Integration test
   `tests/integration/features/evaluation/test_mcs_vs_arch.py` (imports `arch`
   directly): domain over `ArchMcs.bootstrap_indices` vs `arch.MCS(..., method='R')`
   with the same T, k, seed, reps, block and scheme, on tie-free data — identical
   elimination order and **identical** p-values (they are multiples of 1/reps). It
   cannot compare `included` (≥ vs arch's >); membership, the boundary p̂ = α and ties
   (built from integer/dyadic losses) are unit-analytic.
7. **Production consumer:** the 6.4 use case (roadmap §6.4 `contratos_consumidos`
   gains `McsBackend`, edited in this Stage's PR).

## Decision record

```
[decision:C] 6.2-R5 — where the MCS procedure is computed and how the libraries split
Escolha: domain computes MCS 'R' over BootstrapIndices; McsBackend (arch, generator of record) supplies indices and b̂_sb; arch.MCS is an integration-test oracle; InferenceBackend (statsmodels) stays for DM/Holm · Alternativas: (a) arch.MCS as runtime kernel, domain only validates and re-applies membership; (b) full stdlib MCS with its own RNG; (c) one InferenceBackend port with a combined statsmodels+arch adapter; (d) read arch.MCS._bootstrap_indices (private attribute) instead of rebuilding the stream; (e) keep a reference model_confidence_set method in the port · Degrau (C): 1 (issue #114 scope 4; ADR 0.0.0020 "MCS bookkeeping" in the domain; ADR 0.0.0056) e 2 (the index stream is arch's own, so the oracle comparison is exact)
Base: arch 8.0.0 multiple_comparison.py "bootstrap_inst = StationaryBootstrap(self.block_size, indices, seed=seed)"; "for j, data in enumerate(bs.bootstrap(self.reps)): bs_index = data[0][0]"; "pval = (test_stat < simulated_test_stat).mean()"; "incl_loc = self._pvalues.Pvalue > self.size"; tie: "i = loc.squeeze()[0]" [verificado]
Sensibilidade pré-registrada: moving-block scheme; l = h; l = √T (B-MCS; values fixed in 6.5) · Reversível: sim
```

## Alternatives considered

### Alternative A — `arch.MCS` as the runtime kernel
- **Why rejected:** "matches arch" becomes a tautology; the elimination rule — the
  object of the old project's bug — would not be ours; the tie quirk and `>` would be
  inherited.

### Alternative B — Full stdlib MCS with Python's RNG
- **Why rejected:** `random.Random` and `numpy` streams differ, so "same seed and
  block" could only match in distribution.

### Alternative C — One `InferenceBackend` port with a combined adapter
- **Why rejected:** no documented identity lets either library satisfy the other's
  half (unlike ADR 6.1.0001 item 3).

### Alternative D — Read `arch.MCS._bootstrap_indices`
- **Why rejected:** private attribute ("For testing" in the source), not a contract;
  rebuilding the stream with the public `StationaryBootstrap` is equivalent and
  verified.

### Alternative E — Keep a reference `model_confidence_set` in the port
- **Why rejected:** exists only for the oracle, has no production consumer and no
  fake × arch error parity; tests may import `arch` directly (integration).

### Alternative F — Do nothing (defer MCS to 6.4)
- **Why rejected:** MCS is in the 6.2 DoD.

## Consequences

### Positive
- The procedure of record is auditable line by line against HLN 2011; arch is an
  exact oracle, not the authority; the report states which generator produced the
  indices.
- Membership uses HLN's ≥; exact ties remove one model per step.

### Negative
- Two ports, two fakes, two contract suites, two transient `port-coverage` entries
  (ADR 6.1.0005 pattern).
- reps × T indices materialised and a stdlib loop of order reps × T × k per MCS run —
  **not yet measured**, and multiplied by the sensitivities (moving-block, l = h,
  l = √T); the technical measures it at T ≈ 10³, k = 7, reps = 1000.
- Confirmatory reproducibility is tied to the `arch`/`numpy` pins.

### Neutral / trade-offs accepted
- The domain replicates arch's strict `<` in the step p-value (immaterial with
  continuous statistics).
- The roadmap's contract lists gain `McsBackend` and `BootstrapIndices` (6.2) and
  `McsBackend` as consumed (6.4); corrected in this Stage's PR.

## References

- Hansen, Lunde & Nason (2011), Econometrica 79(2), Definitions 2 and 4, Theorem 3,
  §3.1.2 (pp. 459, 462, 465–466).
- Politis & White (2004), Econometric Reviews 23(1), §3.1 p. 55 (stationary
  bootstrap), §3.2 Eq. (6) (b_opt); Patton, Politis & White (2009).
- arch 8.0.0 `arch/bootstrap/multiple_comparison.py`, `arch/bootstrap/base.py`.
- Related ADRs: [0.0.0010](./0_0_0010-paired-inference-dm-holm-mcs.md),
  [0.0.0020](./0_0_0020-statistics-in-domain-over-value-objects.md),
  [0.0.0056](./0_0_0056-own-statistics-in-domain-r-oracle-as-fixtures.md),
  [6.1.0001](./6_1_0001-scoring-libraries-as-oracle-backend-behind-port.md),
  [6.1.0005](./6_1_0005-transient-port-coverage-baseline-between-port-and-first-adapter.md),
  [6.2.0001](./6_2_0001-paired-loss-series-single-aligned-matrix-vo.md),
  [6.2.0003](./6_2_0003-dm-holm-of-record-statsmodels-oracle-no-dm-wrapper.md),
  [6.2.0005](./6_2_0005-mcs-block-length-ceiling-integer.md).
- Domain doc §6.5, §10 #16/#16b, §11.3; issue [#114](https://github.com/MarceloSanC/financial-forecasting/issues/114).
