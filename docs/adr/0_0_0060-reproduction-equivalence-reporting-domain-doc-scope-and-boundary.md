---
title: ADR 0.0.0060 — Single evaluation domain doc covering Step 8 (reproduction, equivalence and reporting), consuming the evaluation and inference docs by pointer
description: Architecture Decision Record
when-use: Reference when questioning why the Step 8 domain gate is satisfied by one doc (reproduction-equivalence-and-reporting.md), why it re-derives none of the Step 6 or Step 7 theory, why 8.1 gets only pointers, or why the equivalence audit against the prior evidence stays out of the TCC text
keywords: [adr, domain-doc, evaluation, reproduction-equivalence-and-reporting, scope, boundary, step-8, reproduction, equivalence-audit, plots, traceability-dossier, editorial-policy, doc-category]
status: accepted
created_at: 2026-10-22
updated_at: 2026-10-22
adr_id: 0.0.0060
decision: The Step 8 domain gate is satisfied by a single doc, docs/domain/evaluation/reproduction-equivalence-and-reporting.md, with pointers only for 8.1, new theory for 8.2 (reproduction of the own run from persisted artifacts — the citable claim — and an internal equivalence audit against the prior confirmatory evidence on the common intersection, with the declared tolerance on the realized target and the metric code, direction as the declared tolerance for the model numbers (ADR 0.0.0062) and a closed catalog of theory-backed explanations) and for 8.3 (status label of each canonical plot and the minimum content of the traceability dossier per Sandve et al. 2013); it consumes the evaluation and inference docs by pointer only, defers implementation to the Stages' technical.md, and keeps the prior-evidence audit out of the TCC text.
context_stage: 0.0-global
bounded_context: evaluation
---

# ADR 0.0.0060 — Single domain doc covering Step 8

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — written for the Step 8 domain gate (issue #208, 2026-10-22),
together with the domain doc.

## Context

No Stage of Step 8 may start without an `accepted` domain doc covering it
(ADR 0.0.0003; `PROMPT-step-single-session.md` §1). The inventory of issue
#208 found:

- **8.1** — the theory is already in place (evaluation §8.1–§8.8; inference
  §4.11–§4.12, §5.7–§5.8, §7): it needs only pointers.
- **8.2** — a gap: the equivalence tolerance was never fixed (roadmap
  §Lacunas conhecidas; overview ASSUM-4 and R-REPRO-1); inference §3.1 has
  only the cross-environment tolerance as a convention without primary source
  (A1-TOL); the roadmap DoD asks for "divergências explicadas pela teoria (não
  'bate com o antigo')" without saying what an explanation is.
- **8.3** — partial: the quantile score plot, reliability diagram, sharpness
  diagram and PICP/MPIW are defined in evaluation §3–§4; the OOS series, the
  PICP × MPIW plot, the status of the DM p-value matrix and the minimum content
  of the traceability dossier are not.
- The human decided (fork P, issue #208) that 8.2 makes two comparisons
  (ADR 0.0.0061), and the TCC editorial policy forbids mentioning the prior
  project in the text.

Forces:

- 8.2 and 8.3 share one object (the judged gold generation and scorecard of
  8.1), one discipline (per horizon, seeds as replicas, preregistered status of
  every number) and one source for the record (Sandve et al. 2013); three docs
  would copy them.
- The Step 6 and Step 7 theory must keep one home each (ADRs 0.0.0054,
  0.0.0057); re-deriving any of it would create a second source that drifts.

## Decision

Write **one** domain document,
[`docs/domain/evaluation/reproduction-equivalence-and-reporting.md`](../domain/evaluation/reproduction-equivalence-and-reporting.md),
in the `evaluation` bounded context (the BC of all three Stages in the
roadmap). Its scope:

- **8.1 — pointers only** (doc §3): the theoretical order of the run (cohort →
  anchored preregistration chain → complete inputs → one gold generation after
  the anchor → per-horizon verdict H1 → H2 → winner; H3 descriptive and
  separate; conformal descriptive; "≥ 1 horizon"), each step pointing to its
  source; plus what 8.1 must record and preserve so that 8.2 can reproduce it
  (a preserved copy + hash of the judged generation, a content hash of the
  silver it read).
- **8.2 (i) — reproduction of the own run** (doc §4): bit for bit in the same
  pinned environment and computation path, random steps included (evidence);
  a later commit keeps the bitwise criterion if its diff does not touch the
  computation path, otherwise it is a recorded deviation; across environments,
  per class of quantity (discrete exact; continuous deterministic within a
  declared float64 tolerance scaled by the quantity's natural unit;
  random-dependent bitwise only with the same generator, otherwise reported);
  a same-environment failure is a stop, never a switch to tolerance; the
  reproduction runs in a separate destination and never replaces the judged
  generation.
- **8.2 (ii) — internal equivalence audit** (doc §5): the prior evidence is a
  regression oracle, never an authority; it is frozen by content hash before
  any value is read; the comparison is restricted to the common intersection
  (common models by definition, alignment by `target_timestamp`, common grid
  levels without interpolation); the declared tolerance applies where both
  sides compute the same thing — the realized target (prior storage
  precision) and the metric code (new code on prior predictions vs the prior
  stored number); the model numbers, which differ in features, data and
  hyperparameters, have direction as the declared tolerance (ADR 0.0.0062;
  direction divergence = a change of sign, side of nominal or DM direction,
  with the deltas documented), with no TOST and no seed-scale
  tolerance; the DM is compared only as each side reported it; a closed
  catalog of theory-backed explanations with identifiable direction;
  unexplained divergences are reported, not blocking; a rule for retiring
  interim scaffolding and keeping the equivalence test out of CI.
- **8.3** (doc §6–§7): a three-way status label (confirmatory / descriptive /
  exploratory) applied per element; a catalog of the canonical plots with what
  each represents, its source and its mandatory label; the minimum content of
  the dossier mapped to Sandve et al. (2013) Rules 1 and 3–9.
- **Excluded:** implementation (where the reproduction compares, the report
  and dossier formats, prior-evidence readers, plotting library) —
  `technical.md` of each Stage; every Step 6/Step 7 formula — by pointer.
- **Editorial boundary:** the equivalence audit stays in the repository; the
  TCC text uses the reproduction claim, the plots and the dossier only.

Methodological forks were triaged with the `evidence-resolution` skill
(2026-10-22) and recorded in doc §9.1: the E/C forks were closed by the agent;
the P forks were decided by the human — B1, what 8.2 compares (ADR 0.0.0061),
and B2, the declared tolerance for the model numbers (ADR 0.0.0062).

## Alternatives considered

### Alternative A — One doc per Stage (8.1, 8.2, 8.3)
- **Pros:** local to each `concept.md`.
- **Cons:** 8.1 has no theory of its own; 8.2 and 8.3 share the object, the
  status taxonomy and the Sandve record; three docs would copy them.
- **Why rejected:** same reasoning as ADR 0.0.0054 Alternative A and ADR
  0.0.0057 Alternative A.

### Alternative B — Append Step 8 sections to the evaluation doc
- **Pros:** one file for all evaluation theory.
- **Cons:** the evaluation doc is `accepted` and long (≈ 2,000 lines); the
  Step 8 theory (floating point, RNG guarantees, equivalence against a prior
  pipeline, reporting) is a different subdomain; amending an accepted doc for
  a new gate blurs which ratification covers what.
- **Why rejected:** a separate subdomain doc keeps each gate's ratification
  auditable; the new doc points to the evaluation doc, never the reverse
  dependency of copying its content.

### Alternative C — Leave the 8.2 tolerance and the explanation criterion to the 8.2 concept
- **Pros:** decided next to the implementation.
- **Cons:** the 8.2 concept is written after 8.1 has run; choosing the
  tolerance or what counts as an explanation after seeing the numbers is the
  garden of forking paths the preregistration exists to prevent (Nosek et al.
  2018), and it would turn every such choice into a P question (skill
  `evidence-resolution` §1).
- **Why rejected:** the rules must be fixed before any confirmatory number
  exists; this gate is the last point before 8.1.

## Consequences

### Positive
- Step 8 has a single citable theory source with a Stage → section map.
- The equivalence rules are fixed before either side's numbers are seen.
- The roadmap gap "tolerância de equivalência (8.2)" is closed by a declared
  form.

### Negative
- One more long doc; mitigated by the consumption map and by pointers.
- The float64 reproduction tolerance and the definition of a direction
  divergence are conventions without a primary source for the exact form
  (recorded as such).
- The roadmap block of 8.2 was amended in the same PR (anchored on the human
  decision of ADR 0.0.0061).

### Neutral / trade-offs accepted
- The equivalence audit produces no claim for the TCC text; its value is
  internal (ASSUM-4, R-REPRO-1).

## References

- [ADR 0.0.0003](./0_0_0003-formalize-domain-and-audits-doc-categories.md),
  [ADR 0.0.0054](./0_0_0054-evaluation-domain-doc-scope-and-boundary.md),
  [ADR 0.0.0057](./0_0_0057-inference-domain-doc-scope-and-boundary.md),
  [ADR 0.0.0061](./0_0_0061-step-8-compares-own-run-reproduction-and-internal-prior-equivalence.md),
  [ADR 7.1.0003](./7_1_0003-reproduction-contract-strict-same-environment-tolerance-across.md).
- Sandve, G. K.; Nekrutenko, A.; Taylor, J.; Hovig, E. (2013). "Ten Simple
  Rules for Reproducible Computational Research". *PLOS Computational
  Biology*, 9(10), e1003285. DOI: 10.1371/journal.pcbi.1003285.
- Nosek, B. A.; Ebersole, C. R.; DeHaven, A. C.; Mellor, D. T. (2018). "The
  preregistration revolution". *PNAS*, 115(11), 2600–2606. DOI:
  10.1073/pnas.1708274114.
- Originating issue: [#208](https://github.com/MarceloSanC/financial-forecasting/issues/208).
