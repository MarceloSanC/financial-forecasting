---
title: ADR 6.2.0001 — PairedLossSeries is one aligned T × k matrix VO that validates (never assembles) the pairing; L_t comes from a domain factory that averages the per-point pinball across seeds
description: Architecture Decision Record
when-use: Reference when building the input of DM, Holm or MCS, when asking why there is no separate "pair" type, why the VO requires T > h and non-negative losses but does not reject a constant differential, or where the loss L_t (and its seed average) of the paired tests comes from
keywords: [adr, evaluation, value-object, paired-loss-series, alignment, diebold-mariano, mcs, holm, pinball, coverage-series, seeds, zero-variance]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.2.0001
decision: Every paired test of Stage 6.2 takes one frozen `PairedLossSeries` — one horizon, k ≥ 2 named models, T ≥ 2 and T > h strictly increasing common `target_timestamp`s, k finite non-negative loss columns — which validates the alignment but never builds it; the zero-variance precondition var(L_i − L_j) > 0 belongs to the MCS (validated there), not to the VO; L_t comes from the domain factory `paired_pinball_losses(Mapping[str, Sequence[CoverageSeries]])`, which takes `PinballScore.per_point_losses` of each seed's series and averages them point by point (B-SEEDS), requiring a common horizon, timestamps and grid.
context_stage: 6.2-paired-inference-dm-mcs-holm
bounded_context: evaluation
---

# ADR 6.2.0001 — `PairedLossSeries`: one aligned T × k VO

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` (revised after Checkpoint A round 1: zero-variance check moved to the MCS,
T > h, seed-averaging factory).

## Context

The roadmap introduces `PairedLossSeries` (value-object) for Stage 6.2 and the
overview §7 / ADR 0.0.0020 list it among the VOs whose invariants ("aligned, one
obs/unit") are enforced once. Its consumers need different views of the same data:

- **DM** (domain doc §6.1, §6.3) needs two columns: d_t = L_cand,t − L_comp,t.
- **Holm** (doc §6.4) needs the B DMs of one horizon **on the same paired sample**.
- **MCS** (doc §6.5) needs the whole T × k matrix; `arch.bootstrap.MCS` with
  `method='R'` gives NaN/`IndexError` without a diagnostic on identical columns, so
  var(L_i − L_j) > 0 for every pair is a precondition **of the MCS** (doc §6.5 and
  convention #16 list it under the MCS only).
- Strict pairing is by the exact `target_timestamp` intersection among **all** models
  of the horizon, one observation per point, contiguous (doc §6.7, convention #17);
  intersection, contiguity check and dedup are the 6.4 builder's job.
- The candidate's column with S seeds is the **pointwise mean of the losses across
  seeds** (doc §6.9 B-SEEDS; ADR 0.0.0010 item 5) — a domain rule about what the loss
  is, not an assembly step.
- The confirmatory loss is L_t, the grid-average pinball per point (doc §2.4, §6.4
  B-FAMILIA); 6.1 exposes it as `PinballScore.per_point_losses(CoverageSeries)`.
- The R oracle `forecast::dm.test` scores `|e|^power`; with `power = 1` it equals the
  loss only when the loss is non-negative (doc §11.3).
- With h = T the DM is indeterminate: the rectangular long-run variance and the HLN
  factor are both identically 0 (T + 1 − 2h + h(h − 1)/T = 0 at h = T), so the
  fallback is decided by the sign of rounding noise — measured in Checkpoint A: a
  stdlib estimate and statsmodels disagreed on that sign in 844 of 2000 random series
  with T = h = 7. R allows h = T (it stops only when h > n).

## Decision

1. **One VO for all three tests.** `PairedLossSeries` (frozen, stdlib-only) holds
   `horizon`, `models` (k ≥ 2, unique, non-empty names, in a fixed order),
   `target_timestamps` (strictly increasing), and one loss column per model.
2. **Invariants at construction (`ValueError`):** `horizon ≥ 1`; T ≥ 2 (df of
   t_{T−1} ≥ 1) and **T > h** (deliberate divergence from R, which allows h = T: at
   h = T the test is indeterminate, see Context); every column of length T; every loss
   finite and ≥ 0.
3. **No zero-variance check in the VO.** A constant differential between two models
   is rejected by the MCS (which needs every pair) and, for one DM pair, ends in the
   DM error "zero variance with h = 1" after the fallback — so one degenerate pair of
   comparators does not block the DM/Holm of the whole horizon. This **departs from
   the wording of issue #114's DoD** ("`PairedLossSeries` rejects … a differential
   with zero variance"), which placed the check in the VO; the doc (§6.5, #16) places
   it in the MCS.
4. **Validate, never assemble.** No intersection, reindexing or dedup logic; a
   misaligned input is an error.
5. **L_t factory** `evaluation/domain/services/paired_pinball_losses.py`:
   `paired_pinball_losses(series_by_model: Mapping[str, Sequence[CoverageSeries]])`.
   For each model it takes `PinballScore.per_point_losses` of each of its S ≥ 1 seed
   series and averages them point by point (S = 1 is the identity); all series
   (across seeds and models) must share `horizon`, `target_timestamps` and `levels`
   (common grid — doc §6.7 last sentence). The factory is the only path that
   **guarantees** L_t; the plain constructor accepts any non-negative losses (tests,
   descriptive profiles).

## Alternatives considered

### Alternative A — A pair type for DM plus a matrix type for MCS
- **Why rejected:** two definitions of "aligned"; nothing ties the B pairs of a Holm
  family to one sample (same reasoning as ADR 6.1.0002 Alternative B).

### Alternative B — The VO intersects/reindexes its inputs (a local "pairer")
- **Why rejected:** duplicates the 6.4 builder, would reach into `modeling` for the
  dedup, and a silent interior drop breaks contiguity (doc §6.7; ADR 0.0.0011).

### Alternative C — Zero-variance check for every pair in the VO (issue #114 wording)
- **Pros:** fails early for the MCS.
- **Cons:** a constant differential between two comparators (a pair neither DM nor
  Holm uses) would stop the DM/Holm of the whole horizon.
- **Why rejected:** doc §6.5 / convention #16 make it an MCS precondition.

### Alternative D — Seed averaging in the 6.4 builder
- **Why rejected:** averaging losses (not predictions) is the B-SEEDS rule of the
  domain doc; outside the domain the L_t guarantee would not reach the candidate,
  whose column is exactly the averaged one.

### Alternative E — Accept negative losses; accept h = T
- **Why rejected:** no project loss is negative and the R oracle would score |L|;
  h = T makes the DM depend on rounding noise.

### Alternative F — Do nothing (tests take bare tuples)
- **Why rejected:** ADR 0.0.0020 Alternative C — invariants checked N times or never.

## Consequences

### Positive
- Same paired sample for every DM of the family and for the MCS by construction (old
  "gate C"); one observation per `target_timestamp` (old "gate F"); L_t including the
  seed average through one factory (old "gate A").

### Negative
- Near-constant differentials (range at float-noise level) pass the VO; the MCS and DM
  checks are exact. Recorded as a risk in the concept.

### Neutral / trade-offs accepted
- The VO cannot verify that the points are contiguous trading sessions; contiguity is
  a 6.4 invariant (doc §6.7).

## Implementation notes

- Files: `evaluation/domain/value_objects/paired_loss_series.py`,
  `evaluation/domain/services/paired_pinball_losses.py`.
- Reuse `_finite_number.is_finite_number` (6.1 audit F1); sums with `math.fsum`.

## References

- Related ADRs: [0.0.0010](./0_0_0010-paired-inference-dm-holm-mcs.md),
  [0.0.0011](./0_0_0011-preregistration-invariants-and-h1-gate.md),
  [0.0.0020](./0_0_0020-statistics-in-domain-over-value-objects.md),
  [6.1.0002](./6_1_0002-coverage-series-aligned-input-vo.md),
  [6.2.0004](./6_2_0004-mcs-procedure-in-domain-over-backend-bootstrap-indices.md).
- Domain doc: [`probabilistic-forecast-evaluation.md`](../domain/evaluation/probabilistic-forecast-evaluation.md)
  §2.4, §6.1, §6.3, §6.4, §6.5, §6.7, §6.9, §10 #16, §11.3.
- Issue [#114](https://github.com/MarceloSanC/financial-forecasting/issues/114).
