---
title: ADR 6.2.0005 — MCS block length is the integer max(h, ⌈max b̂_sb⌉), the same l for the stationary and the moving-block bootstrap
description: Architecture Decision Record
when-use: Reference when computing the MCS block length from Politis–White estimates, or when asking why the block is an integer and why it is rounded up
keywords: [adr, evaluation, mcs, block-length, politis-white, stationary-bootstrap, moving-block, rounding, ceil, arch]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.2.0005
decision: The primary MCS block length is l = max(h, ⌈max over all model pairs of b̂_sb⌉), an int ≥ 1 (b̂_sb = 0 is legitimate and yields l = h), used unchanged by the stationary bootstrap and by the moving-block scheme; the values of the other block sensitivities are left to the preregistration (6.5).
context_stage: 6.2-paired-inference-dm-mcs-holm
bounded_context: evaluation
---

# ADR 6.2.0005 — MCS block length: integer, rounded up

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` (revised after Checkpoint A round 1: the √T sensitivity is 6.5's, not
fixed here; b̂_sb = 0 allowed; moving-block ceiling l < n cited).

## Context

ADR 0.0.0010 item 3 / doc §6.5 (B-MCS) fix the block as max(h, the largest
Politis–White b̂_sb among the pairwise differentials of the horizon) — "the most
persistent, hence most conservative, floored at h". They do not say what happens to
the real-valued b̂_sb before the max (issue #114, fork R3; no primary source found).

Facts:

- In the stationary bootstrap the block length is geometric "with mean equal to the
  real number b" (Politis & White 2004, §3.1 p. 55): a non-integer mean is
  theoretically fine; b_opt itself is Eq. (6) of §3.2.
- `arch` 8.0.0 annotates `block_size: int` everywhere; `StationaryBootstrap` only uses
  `1.0 / block_size`, but `MovingBlockBootstrap`/`CircularBlockBootstrap` use
  `n // block_size` and `np.arange(block_size)`, so the moving-block scheme needs an
  integer; `MovingBlockBootstrap` raises for l > n and l = n reproduces the sample
  (zero bootstrap variance), hence l < n there (ADR 6.2.0004 item 3).
- `optimal_block_length` returns float values ≥ 0, capped at ⌈min(3√n, n/3)⌉; a zero
  estimate (no detectable dependence) is legitimate.

## Decision

l = max(h, ⌈max_{i<j} b̂_sb(d_ij)⌉), an `int` ≥ 1, computed by
`ModelConfidenceSet.block_length` (ADR 6.2.0004). b̂_sb must be finite and ≥ 0
(negative or non-finite → `ValueError`; 0 → l = h). The same l feeds the stationary
(primary) and the moving-block schemes, so that sensitivity changes only the scheme.
`McsBackend.bootstrap_indices` accepts only `int` blocks. The values of the other
sensitivities (l = h, l = √T and how √T is rounded) are preregistration content (6.5).

## Decision record

```
[decision:C] 6.2-R3 — rounding of b̂_sb before max(h, ·)
Escolha: ceil to int · Alternativas: keep the float (stationary only); round to nearest; floor · Degrau (C): 2 (the backend's interface is int and its moving-block needs an int) e 4 (rounding up keeps l ≥ b̂, the conservative direction ADR 0.0.0010 already chose)
Base: arch 8.0.0 base.py StationaryBootstrap "self._p = 1.0 / block_size"; MovingBlockBootstrap "num_blocks = self._num_items // self.block_size", "np.arange(self.block_size)" [verificado]; Politis & White 2004 §3.1 p. 55 "(B) The distribution F_b is a Geometric distribution with mean equal to the real number b" [verificado]
Sensibilidade pré-registrada: nenhuma nova (difference < 1 block) · Reversível: sim
```

## Alternatives considered

### Alternative A — Keep the float for the stationary bootstrap
- **Why rejected:** violates the backend's `int` interface; the moving-block scheme
  would need a different l, so the two schemes would differ in two things at once.

### Alternative B — Round to nearest / floor
- **Why rejected:** can yield l < b̂_sb — less conservative than the ratified rule
  intends.

### Alternative C — Do nothing (leave rounding to the adapter)
- **Why rejected:** the block enters the preregistration (6.5) and the report; a
  rounding hidden in an adapter would be an undeclared convention.

## Consequences

### Positive
- One integer l per horizon, recorded in `McsReport`, valid for both schemes.

### Negative
- Up to one extra observation of mean block length versus the raw estimate.

### Neutral / trade-offs accepted
- Doc §6.5 / §10 #16b gain the precision "⌈·⌉" in this Stage's PR.

## References

- Politis & White (2004), Econometric Reviews 23(1), §3.1 p. 55, §3.2 Eq. (6).
- arch 8.0.0 `arch/bootstrap/base.py`.
- Related ADRs: [0.0.0010](./0_0_0010-paired-inference-dm-holm-mcs.md),
  [6.2.0004](./6_2_0004-mcs-procedure-in-domain-over-backend-bootstrap-indices.md).
- Domain doc §6.5, §10 #16b; issue [#114](https://github.com/MarceloSanC/financial-forecasting/issues/114) (fork R3).
