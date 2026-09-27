---
title: ADR 0.0.0054 — Single evaluation domain doc covering Step 6, with boundaries to modeling (Step 5) and conformal (Step 7)
description: Architecture Decision Record
when-use: Reference when questioning why the Step 6 domain gate is satisfied by one doc (probabilistic-forecast-evaluation.md), why it does not re-derive Step 5 theory or cover conformal/CQR, or why the roadmap's orphan vocabulary (C.0, Gates A–F) is not used
keywords: [adr, domain-doc, evaluation, probabilistic-forecast-evaluation, scope, boundary, step-6, step-7, conformal, doc-category]
status: accepted
created_at: 2026-09-26
updated_at: 2026-09-26
adr_id: 0.0.0054
decision: The Step 6 domain gate is satisfied by a single doc, docs/domain/evaluation/probabilistic-forecast-evaluation.md, covering the five theory blocks of Step 6 (scoring, calibration + degeneracy gate, paired inference, coverage/risk backtests, preregistration/scorecard), consuming the modeling §7 contract by pointer only, excluding conformal/CQR (Step 7), and abandoning the roadmap's orphan vocabulary.
context_stage: 0.0-global
bounded_context: evaluation
---

# ADR 0.0.0054 — Single evaluation domain doc covering Step 6

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — ratified by the human (Marcelo) on 2026-09-26, together with the evaluation domain doc (issue #78).

## Context

No Stage of Step 6 may start without an `accepted` domain doc for the
`evaluation` bounded context (ADR 0.0.0003; `PROMPT-step-single-session.md`
§1). ADR 0.0.0051 already deferred the evaluation theory (DM/HLN, Holm, MCS,
Christoffersen, Kupiec, degeneracy gate) to this doc. The five Stages of Step 6
(6.1–6.5) share one object — the common quantile grid aligned to the realized
return — and one discipline — per-horizon, preregistered, mechanical verdict.

Forces:

- The shared core (proper scores, per-horizon rule, pairing, degeneracy) is
  consumed by all five Stages; splitting it would duplicate it.
- The modeling doc (§7) already states the contract on its side; re-deriving
  it here would create two sources that drift.
- Conformal/CQR has its own gate (Step 7) and its own guarantees language
  (R-CONFORMAL-1); mixing it in would blur "native calibration" (H1) with
  "benchmark coverage".
- The roadmap text of 6.2/6.3/6.5 carries vocabulary inherited from the old
  project (C.0, Gates A–F, top-50, win-rate) defined nowhere in this repo.

## Decision

Write **one** domain document,
[`docs/domain/evaluation/probabilistic-forecast-evaluation.md`](../domain/evaluation/probabilistic-forecast-evaluation.md),
to satisfy the Step 6 gate. Its scope:

- the **five theory blocks** of Step 6 plus shared fundamentals and a
  per-Stage consumption map (6.4 has no theory of its own; it consumes
  invariants);
- a **boundary section** that consumes modeling §7 (common grid, one
  observation per `target_timestamp`, pinball as training loss and paired
  metric, degenerate grid of the point baselines) **by pointer only**;
- **excluded:** conformal/CQR and its coverage (Step 7 gate), implementation
  specs (schemas, paths, classes — `technical.md` of each Stage);
- the orphan roadmap vocabulary is **abandoned**; the doc says what replaces
  each term, and the roadmap text is adjusted in the PRs of 6.2/6.3/6.5.

Methodological forks inside the doc were triaged with the
`evidence-resolution` skill (2026-09-26): E/C forks closed by the agent and
recorded in doc §10.1; the only P fork (wording of the H1 claim, "B1") was
decided by the human on issue #78. The load-bearing ones are recorded in
ADR 0.0.0009 (scoring), ADR 0.0.0010 (paired inference) and ADR 0.0.0011
(preregistration, invariants, degeneracy gate, H1 gate).

## Alternatives considered

### Alternative A — One doc per Stage (6.1–6.5)
- **Pros:** local to each `concept.md`.
- **Cons:** the object, the per-horizon rule and the pairing are the same in
  all Stages; five docs would copy them.
- **Why rejected:** same reasoning as ADR 0.0.0051 Alternative B.

### Alternative B — Include conformal/CQR
- **Pros:** one place for "all coverage".
- **Cons:** different gate, different guarantee language, different BC
  (`inference`); CQR is a benchmark, not the H1 yardstick.
- **Why rejected:** would blur H1 and the benchmark; the doc instead promises
  that Step 7 reuses its coverage definitions without re-derivation.

### Alternative C — Keep the roadmap's Gate A–F vocabulary
- **Pros:** no roadmap edits.
- **Cons:** terms are undefined in the repo; keeping them imports the old
  project's semantics silently.
- **Why rejected:** undefined vocabulary cannot be audited.

## Consequences

### Positive
- Step 6 has a single citable theory source with a Stage → section map.
- The modeling/evaluation contract lives on each side as pointers, not copies.

### Negative
- A long doc (~1,900 lines); mitigated by the consumption map.
- Roadmap prose of 6.2/6.3/6.5 must be edited in those Stages' PRs.

### Neutral / trade-offs accepted
- Splitting later is cheap (supersede this ADR per ADR 0.0.0003).

## References

- [ADR 0.0.0003](./0_0_0003-formalize-domain-and-audits-doc-categories.md),
  [ADR 0.0.0051](./0_0_0051-modeling-domain-doc-scope-and-boundary.md),
  [ADR 0.0.0009](./0_0_0009-pinball-primary-crps-complementary.md),
  [ADR 0.0.0010](./0_0_0010-paired-inference-dm-holm-mcs.md),
  [ADR 0.0.0011](./0_0_0011-preregistration-invariants-and-h1-gate.md).
- Originating issue: [#78](https://github.com/MarceloSanC/financial-forecasting/issues/78).
