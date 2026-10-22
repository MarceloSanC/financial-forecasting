---
title: ADR 0.0.0062 — Equivalence with the prior evidence uses a numeric declared tolerance where equality is expected (realized target, metric code) and direction as the tolerance for the model numbers
description: Architecture Decision Record
when-use: Reference when questioning what "tolerância declarada" (overview ASSUM-4, R-REPRO-1) means in Stage 8.2, why no |Δ| ≤ X % threshold applies to the retrained model's numbers, or when a direction divergence becomes a [finding]
keywords: [adr, step-8, stage-8.2, equivalence-audit, prior-evidence, declared-tolerance, assum-4, r-repro-1, direction, material-divergence, finding, ich-e9, equivalence-margin, human-decision]
status: accepted
created_at: 2026-10-22
updated_at: 2026-10-22
adr_id: 0.0.0062
decision: In the internal equivalence audit of Stage 8.2, the numeric declared tolerance applies only where equality is expected — the realized target on the common intersection (prior storage precision) and the metric code (new code on the prior predictions against the prior stored number); for the numbers of the retrained model the tolerance is the direction — same sign of the candidate − common-baseline advantage, same side of the nominal for the 80 % PICP, same direction of the DM — with the quantitative deltas documented; a direction divergence without a theory-backed explanation is a [finding] in the report; no |Δ| ≤ X % threshold is applied to model numbers; overview ASSUM-4, R-REPRO-1 and §2 are reworded accordingly.
context_stage: 0.0-global
bounded_context: evaluation
---

# ADR 0.0.0062 — Declared tolerance: numeric where equality is expected, direction for the model numbers

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — decided by the human (Marcelo) on 2026-10-22 (issue #208, fork
P "B2" of the Step 8 domain gate).

## Context

The overview promises that equivalence with the prior evidence is measured
"com tolerância declarada" (ASSUM-4, R-REPRO-1, §2). The domain doc of Step 8
showed that the prior model differs in features, re-derived dataset and
hyperparameters, so a statistical tolerance on the **model's** numbers
measures the equivalence of nothing; the first draft's seed-dispersion scale
was rejected in review (seed variance is "much smaller than the variance due
to perturbing the split", Bouthillier et al. 2021 §7). Reading ASSUM-4 as a
numeric threshold on model numbers would need a margin, and ICH E9 §3.3.2 (p.
18 of the EMA version) requires that "The choice of equivalence margins should
be justified clinically" — there is no substantive ground for one here. Since
this changes how a ratified overview premise is read, it was triaged as P
(`evidence-resolution` §1) and taken to the human.

## Decision

**Option 1.**

1. **Numeric declared tolerance where equality is expected:** the realized
   target on the common intersection, within the prior's storage precision
   (A1); and the metric code — the new code on the prior per-point predictions
   against the number the prior stored, within max(R2, storage precision) (A2).
2. **Direction as the tolerance for model numbers:** same sign of
   (candidate − common baseline) in the per-level pinball, same side of the
   nominal for the 80 % PICP, same direction of the DM as each side reported
   it; quantitative deltas documented.
3. A direction divergence without a theory-backed explanation (domain doc
   §5.6) is a `[finding]` in the equivalence report.
4. Overview §2, ASSUM-4 and R-REPRO-1 are reworded to say this explicitly.

## Alternatives considered

### Alternative 2 — A threshold |Δ| ≤ X % on the model numbers
- **Pros:** a single number, literal reading of "tolerância declarada".
- **Cons:** no source for X; ICH E9 §3.3.2 requires a margin justified on
  substantive grounds; models that differ in features, data and
  hyperparameters would make any X arbitrary.
- **Why rejected:** by the human, on that evidence.

### Alternative 3 — Purely descriptive model comparison, no tolerance at all (the doc's previous text)
- **Pros:** no convention to defend.
- **Cons:** leaves ASSUM-4's "tolerância declarada" without a reading for the
  model numbers; a direction flip would be only "registered".
- **Why rejected:** direction gives a declared, falsifiable criterion with
  primary-source support for not using a numeric margin.

## Consequences

### Positive
- ASSUM-4 / R-REPRO-1 get an operational reading that is fixed before 8.1.

### Negative
- Direction is coarse: a large change in magnitude with the same sign passes
  (it is documented as a delta).

### Neutral / trade-offs accepted
- The DM direction is compared on samples, losses and families that differ by
  construction; its divergence is still a `[finding]` when unexplained.

## References

- Domain doc [reproduction-equivalence-and-reporting](../domain/evaluation/reproduction-equivalence-and-reporting.md)
  §5.4–§5.6, §9.1 (B2).
- [ADR 0.0.0061](./0_0_0061-step-8-compares-own-run-reproduction-and-internal-prior-equivalence.md)
  (B1, what 8.2 compares).
- ICH (1998). *E9 — Statistical Principles for Clinical Trials*.
  CPMP/ICH/363/96 (EMA), §3.3.2, p. 18.
- Bouthillier, X. et al. (2021). "Accounting for Variance in Machine Learning
  Benchmarks". *Proceedings of MLSys*, 3, 747–769. arXiv:2103.03098. (§7.)
- Decision: issue [#208](https://github.com/MarceloSanC/financial-forecasting/issues/208), 2026-10-22.
