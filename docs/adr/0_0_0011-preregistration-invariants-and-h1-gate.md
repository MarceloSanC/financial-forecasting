---
title: ADR 0.0.0011 — Preregistration order, degeneracy gate semantics and the per-tail H1 gate ("calibration not rejected" with declared power)
description: Architecture Decision Record
when-use: Reference when questioning when the preregistration is hashed, what the degeneracy gate invalidates, how the H1 gate is defined, how the H1 claim is worded, or why comparators failing H1 stay in the H2 family
keywords: [adr, preregistration, degeneracy-gate, h1-gate, calibration, wilson, bonferroni, christoffersen, power, scorecard, evaluation, step-6]
status: accepted
created_at: 2026-09-26
updated_at: 2026-10-03
adr_id: 0.0.0011
decision: The preregistration is hashed after the cohort is frozen and trained and before any confirmatory metric; degenerate rows keep proper scores and leave only calibration metrics, with no row exclusion in inference; H1 is gated per horizon, on the candidate only, by both tails of the primary central pair inside Wilson 97.5 % bands plus a degeneracy-rate threshold, and is worded "calibration not rejected" with declared power.
context_stage: 0.0-global
bounded_context: evaluation
---

# ADR 0.0.0011 — Preregistration, degeneracy gate and the H1 gate

> **Nota (2026-10-03, issue #131):** o "≤ 5 % false failure" do item 4 é o alvo nominal do Bonferroni sobre bandas de Wilson; a taxa exata de reprovar um candidato calibrado é ≈ 5 %, não ≤ 5 % — 0,0506 em n = 1 512 e, em todo n inteiro de 1 400 a 1 600, de 0,0442 (n = 1 555) a 0,0545 (n = 1 435) — ver technical 6.5 §7 `[finding]` T-F11. A regra do gate não muda.

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — ratified by the human (Marcelo) on 2026-09-26, together with the evaluation domain doc (issue #78).

## Context

Overview §11 planned "immutable preregistration + invariants (no cross-horizon
aggregation, OOS alignment, dedup, degeneracy gate)". Three forks of the
domain doc concern it: B-ORDEM (§8.2), B-GATE (§5.3), B-GATE-H1 (§8.5). A
fourth question — how to word the H1 claim — was class P and decided by the
human: **B1**.

Two facts shaped the H1 gate:

- The draft gated on the PICP of the primary central pair. The PICP is
  invariant to a common shift of both tails (doc §4.2): a **location** error
  passes it. Exact computation (T = 500, 80 % pair): a 0.3σ bias passes the
  PICP gate with probability 0.790, the per-tail gate with 0.004.
- A non-rejection gate cannot prove calibration (ICH E9 §3.3.2, pp. 17–18).

## Decision

1. **Order (B-ORDEM, rung 1).** Cohort (5.5) frozen and trained → preregistration
   (6.5) hashed → confirmatory metrics (8.1). Seeing raw OOS predictions before
   the hash is not a violation; computing confirmatory metrics is.
2. **Degeneracy gate (B-GATE, rung 1).** Degenerate = total collapse of the grid
   (Dirac). Proper scores are computed on **all** rows (the Dirac is well posed;
   without this the naive baselines have no pinball and H2 is empty);
   calibration/sharpness metrics only on non-degenerate rows ("not applicable"
   at 100 %, the declared case of the point baselines); the rate is always
   reported; above a preregistered threshold it fails H1 for distributional
   models; **no row exclusion** in paired inference (researcher degree of
   freedom; breaks HAC/bootstrap contiguity). The 6.1 DoD "invalidates the
   row's metrics" reads "invalidates the row's **calibration** metrics".
3. **H1 claim (B1, human).** "Calibration **not rejected** within the Wilson
   band", always with the gate's **power** against a preregistered minimum
   relevant deviation (width and location forms) at the effective T.
   "Calibrated" is not used unqualified.
4. **H1 gate (B-GATE-H1, rungs 1 and 4).** Per horizon, **candidate only**:
   each tail of the primary central pair inside its Wilson band at 97.5 %
   (Bonferroni over two tails, ≤ 5 % false failure) **and** degeneracy rate
   ≤ threshold. PICP, per-τ coverage, LR tests, sharpness and VaR are the H1
   profile. Preregistered sensitivities: Christoffersen's 3-state LR_uc (χ²(2))
   on the same pair; the Diebold–Gunther–Tay sub-series partition at h+7.
   Comparators that fail their own H1 stay in the Holm family and the MCS set
   (ADR 0.0.0010).

## Alternatives considered

- **B2 — equivalence test (CI inside nominal ± δ).** Rejected by the human: δ
  has no convention; with δ = 5 p.p. and T = 500 a perfectly calibrated model
  passes only ~60 % of the time, blocking H2 by chance in ~40 %.
- **PICP-only gate.** Rejected: blind to location (0.790 pass at 0.3σ).
- **3-state LR_uc as the gate.** Dominates the per-tail gate in every computed
  scenario; kept as sensitivity because B1 words the claim on the Wilson band.
- **PICP and tails together.** Three tests raise the false-failure bound to
  ~10 % without correction.
- **Invalidate all metrics of degenerate rows; pairwise exclusion.** Rejected:
  empties H2 for the point baselines / selection conditioned on a model's
  behaviour, breaks contiguity.
- **Preregister before training the cohort.** Rejected: would fix inference
  parameters before knowing the effective T; the roadmap orders 5.5 → 6.5.

## Consequences

- Positive: the gate catches location errors; the claim says only what a
  non-rejection test can say; the family is fixed before data.
- Negative: against pure width errors the per-tail gate detects less than the
  PICP (pass 0.42 vs 0.22 at 75 % true coverage) — the PICP stays in the
  profile, and the cost is declared.
- Overview §4 (H1 text) is reworded in the same PR; the preregistration (6.5)
  and the TCC text use the same language.

## References

- ICH E9 (1998) §2.2.2, §3.3.2 pp. 17–18, §5.1–§5.3; Nosek et al. (2018)
  "Challenge 3"; Simmons, Nelson & Simonsohn (2011) req. 5; Gneiting & Raftery
  (2007) §4.2; Brown, Cai & DasGupta (2001); Christoffersen (1998) §4.2;
  Diebold, Gunther & Tay (1998) §6; White (2000) §2.
- Doc: [`probabilistic-forecast-evaluation.md`](../domain/evaluation/probabilistic-forecast-evaluation.md) §5, §8, §10.1.
- Issue [#78](https://github.com/MarceloSanC/financial-forecasting/issues/78)
  (B1 decision comment, 2026-09-26).
