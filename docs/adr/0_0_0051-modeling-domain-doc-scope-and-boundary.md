---
title: ADR 0.0.0051 — Single modeling domain doc covering Step 5 plus an evaluation-boundary section, without Step 6 theory
description: Architecture Decision Record
when-use: Reference when questioning why the Step 5 domain gate is satisfied by one doc (quantile-model-training.md) instead of several, why it carries a boundary section pointing at the evaluation BC, or before writing the evaluation domain doc for the Step 6 gate
keywords: [adr, domain-doc, modeling, quantile-model-training, scope, boundary, step-5, step-6, evaluation, doc-category]
status: accepted
created_at: 2026-07-14
updated_at: 2026-07-14
adr_id: 0.0.0051
decision: The Step 5 domain gate is satisfied by a single doc, docs/domain/modeling/quantile-model-training.md, covering the four theory blocks of Step 5 (baselines, quantile GBM, quantile TFT, confirmatory cohort) plus a short evaluation-boundary section with pointers only — no Step 6 theory (DM/MCS/Holm/backtests), which belongs to the future evaluation BC domain doc.
context_stage: 0.0-global
---

# ADR 0.0.0051 — Single modeling domain doc covering Step 5 plus an evaluation-boundary section

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Step 5 cannot start any Stage until the theory its `concept.md`s consume
exists as an `accepted` domain doc (blocking gate of ADR 0.0.0003 /
`PROMPT-step-single-session.md` §1). The theory in question spans four Stages
(5.2–5.5) and one bounded context (`modeling`), and it shares a dense common
core: every model — naive baseline, GBM, TFT — emits the **same quantile
grid**, is scored by the **same pinball loss**, runs under the **same
walk-forward protocol** (5.1), and hands predictions across the same boundary
to the evaluation BC.

Forces:

- ADR 0.0.0003 nests domain docs by BC and subdomain; the granularity of the
  "subdomain" (one doc vs several) was left to the first instance — this one.
- The common core (target semantics, pinball, grid, crossing) is consumed by
  **all four** Stages; splitting it across docs would either duplicate it or
  force one doc to be the "real" home with the others pointing at it.
- Step 6 theory is a different gate for a different BC (`evaluation`), but the
  two sides share contracts (grid, degenerate triplet, alignment); leaving the
  boundary unstated invites each side to re-derive (and drift on) it.
- Healthy-size guidance (CONVENTIONS §6) tolerates a longer canonical
  reference doc; domain docs are read per-section by Stage, not linearly.

## Decision

Write **one** domain document,
[`docs/domain/modeling/quantile-model-training.md`](../domain/modeling/quantile-model-training.md),
to satisfy the blocking domain gate of Step 5
([ADR 0.0.0003](./0_0_0003-formalize-domain-and-audits-doc-categories.md);
`PROMPT-step-single-session.md` §1). Its scope is:

- the **four theory blocks** of Step 5: baseline hierarchy and quantile
  emission (Stage 5.2), quantile gradient boosting (Stage 5.3), quantile TFT
  training (Stage 5.4), and the confirmatory cohort discipline (Stage 5.5);
- the **shared fundamentals** those blocks rest on (target semantics, pinball
  loss, dense quantile grid, quantile crossing and rearrangement, the 5.1
  temporal protocol as a presupposition);
- a short **"contract with evaluation" boundary section**: the common quantile
  grid, the degenerate grid, pinball as both training loss and future paired
  metric, one observation per `target_timestamp` — stated as **pointers only**,
  **without deriving** any Step 6 theory (DM/HLN, Holm, MCS, calibration and
  risk backtests), which belongs to the future domain doc of the `evaluation`
  bounded context (the Step 6 gate).

Decided by the human (Marcelo) on 2026-07-14, at the Step 5 domain-gate
session (issue [#47](https://github.com/MarceloSanC/financial-forecasting/issues/47)).

## Alternatives considered

### Alternative A — Two docs (baselines × training)
- **Description:** split into `baseline-quantile-emission.md` (5.2) and
  `quantile-model-training.md` (5.3–5.5).
- **Pros:** each doc shorter; the baselines doc closes earlier.
- **Cons:** the shared fundamentals (pinball, grid, crossing/rearrangement,
  degenerate-grid theory) are load-bearing for **both** halves — either
  duplicated (drift risk, the exact failure mode `domain/` exists to prevent)
  or hoisted into one doc that the other must import wholesale. The boundary
  with evaluation would also be stated twice.
- **Why rejected:** human decision (2026-07-14) — the common core dominates;
  one doc with a per-Stage consumption map serves the same navigability
  without the duplication.

### Alternative B — One doc per Stage (5.2, 5.3, 5.4, 5.5)
- **Description:** four subdomain docs, one per Stage.
- **Pros:** maximally local to each Stage's `concept.md`.
- **Cons:** re-creates in `domain/` the per-Stage fragmentation that ADR
  0.0.0003 Alternative B already rejected for `concept.md`s: the theory is
  transversal (the grid, the loss, and the protocol are the same objects in
  all four Stages). Four docs × shared core = four copies to keep in sync.
- **Why rejected:** contradicts the raison d'être of the `domain/` category
  (state once, consume across Stages).

### Alternative C — Step-5-strict (no boundary section)
- **Description:** cover only Step 5 theory; say nothing about the evaluation
  contract.
- **Pros:** cleanest category boundary (modeling theory only); slightly
  shorter.
- **Cons:** the emission conventions only make sense **because of** how the
  predictions will be evaluated (common grid for paired pinball, degenerate
  grid vs degeneration gate, 1 obs per `target_timestamp`). Omitting the
  contract leaves each Stage 5.x `concept.md` to reconstruct why the
  conventions exist — precisely the drift the doc is meant to stop.
- **Why rejected:** human decision (2026-07-14) — the boundary is part of the
  modeling side's obligations; stating it as pointers costs one short section.

### Alternative D — Include Step 6 theory now
- **Description:** one grand doc covering Step 5 **and** the confirmatory
  statistics (DM/HLN, Holm, MCS, Christoffersen, degeneration gate).
- **Pros:** one research effort; the boundary becomes internal.
- **Cons:** Step 6 theory belongs to another BC (`evaluation`) with its own
  gate, its own research pass, and its own review; bundling it would front-load
  work not needed to unblock Step 5, violate the BC nesting of ADR 0.0.0003,
  and produce a doc far past healthy size. The evaluation side also depends on
  choices (oracle libraries, test variants) not yet researched to the
  project's sourcing bar.
- **Why rejected:** human decision (2026-07-14) — defer to the Step 6 gate;
  the boundary section records the hand-off instead.

### Alternative E — Do nothing / status quo
- **Description:** keep the theory scattered (roadmap prose, `5_1_*` ADRs,
  skills) and let each Stage re-derive it.
- **Pros:** zero writing cost now.
- **Cons:** the Step 5 gate is **blocking**: no Stage of Step 5 may start
  without an `accepted` domain doc (ADR 0.0.0003). Scattered theory is exactly
  the drift problem that ADR already diagnosed.
- **Why rejected:** not available — the gate makes the doc a precondition.

## Consequences

### Positive
- Step 5's domain gate has a single, citable target; Stages 5.2–5.5 consume
  sections of one doc instead of re-deriving theory.
- The shared fundamentals exist exactly once; the evaluation boundary is
  written down on the modeling side as pointers, so both BCs agree on the
  contract without duplicating theory.
- The doc's consumption map (Stage → sections) keeps per-Stage reading short
  despite the single-file scope.

### Negative
- One larger doc (several hundred lines) instead of small per-Stage notes; a
  reader wanting only 5.3 theory must navigate sections (mitigated by the
  consumption map).
- The boundary section must be kept consistent with the future evaluation
  domain doc when the Step 6 gate produces it (one more cross-reference to
  maintain).

### Neutral / trade-offs accepted
- If the subdomain outgrows one file (e.g. multi-asset training theory), the
  doc can be split and superseded per the ADR 0.0.0003 lifecycle — cheap
  reversal.
- Consolidating scope + boundary decisions in a single ADR follows the
  precedent of ADR 0.0.0003 itself (decisions taken in the same act, same
  rationale).

## Implementation notes

- The doc ships as `status: draft` and only satisfies the gate after human
  ratification flips it to `accepted` (ADR 0.0.0003 lifecycle).
- Emission conventions for the baselines (the other decision of the same
  session) live in [ADR 0.0.0052](./0_0_0052-baseline-quantile-emission-conventions.md).
- New primary sources cited by the doc are registered in `overview.md` §10 in
  the same PR (sourcing rule of ADR 0.0.0003).

## References

- Related ADRs: [ADR 0.0.0003](./0_0_0003-formalize-domain-and-audits-doc-categories.md)
  (domain/ category, gate and sourcing bar);
  [ADR 0.0.0052](./0_0_0052-baseline-quantile-emission-conventions.md)
  (baseline quantile-emission conventions, same session).
- The doc governed by this ADR:
  [`docs/domain/modeling/quantile-model-training.md`](../domain/modeling/quantile-model-training.md).
- Originating issue:
  [#47](https://github.com/MarceloSanC/financial-forecasting/issues/47).
