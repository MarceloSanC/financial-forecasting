---
title: ADR 0.0.0056 — Own-implemented statistics (DM, Christoffersen, Kupiec) are domain formulas of record; ports only where a Python library exists; the R oracle enters as versioned fixtures read by golden tests
description: Architecture Decision Record
when-use: Reference when implementing a statistic with no canonical Python library (Diebold–Mariano, Christoffersen, Kupiec, …), when deciding whether it needs a port/adapter, or how an R oracle reaches the test suite without R in CI
keywords: [adr, statistics, domain, own-implementation, r-oracle, fixtures, golden-test, port, adapter, diebold-mariano, christoffersen, kupiec, r-libs-1]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 0.0.0056
decision: A statistic with no canonical Python library is implemented once as a stdlib domain formula of record (never in an adapter); a port-out exists only where a Python library can be wrapped (e.g. statsmodels, arch, sklearn, scoringrules) and then serves as oracle/backend behind that port; the R oracle is consumed as versioned fixtures (generator, pinned image, sessionInfo, provenance) read by golden tests, with no adapter that replays R answers.
context_stage: 6.2-paired-inference-dm-mcs-holm
bounded_context: transversal
---

# ADR 0.0.0056 — Own statistics in the domain; R oracle as fixtures

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — **Decided by: human, 2026-09-28, via master session** (Step 6
orchestration, Checkpoint A of Stage 6.2, item H1). Amends
[ADR 0.0.0020](./0_0_0020-statistics-in-domain-over-value-objects.md) (second bullet of its
Decision) and the wording of overview §7 and §8 R-LIBS-1.

## Context

Three ratified texts disagreed on where an own-implemented statistic lives:

- ADR 0.0.0020, first bullet: "the DM statistic, MCS bookkeeping, Christoffersen —
  depend only on the standard library" (domain); second bullet: "Where no canonical
  Python library exists (Diebold–Mariano, Christoffersen, Kupiec), a thin
  own-implementation sits behind a port and is validated against an R oracle".
- Overview §7: "implementação própria fina atrás de porta + golden-tests contra
  oráculo R + fixtures"; §8 R-LIBS-1: "Wrapper próprio atrás de porta + oráculo R".
- ADR 6.1.0001 (Stage 6.1) fixed, for the `evaluation` BC, "formula of record in the
  domain; libraries behind a port as oracle", and a Stage cannot supersede the
  overview (6.1.0001 Alternative A).

Facts: the domain cannot call an application port (LAYOUT §3), so a formula behind
a port cannot be used by a domain service; R does not run in CI (Docker-only dev
image without R); Stages 6.2 (DM) and 6.3 (Christoffersen, Kupiec) both need a rule.

## Decision

**Option A.** For a statistic with no canonical Python library:

1. the formula is implemented **once**, stdlib-only, as a **domain** service — the
   implementation of record (ADR 0.0.0020 first bullet);
2. a **port-out exists only where a Python library can be wrapped** (statsmodels,
   arch, sklearn, scoringrules, …): the adapter calls the library and the port's
   contract suite compares it with a fake that delegates to the domain formula
   (ADR 6.1.0001 pattern); no port is created just to host an own implementation;
3. the **R oracle** is consumed as **versioned fixtures** (generator script, pinned
   image, `sessionInfo`, provenance block) read by **golden tests**; no adapter
   replays recorded R answers. The fixture format is fixed by ADR 6.2.0006.

## Alternatives considered

### Alternative A — Formula in the domain, port only for real libraries, R as fixtures (chosen)
- **Pros:** one implementation; the domain returns complete results; R stays out of CI;
  consistent with ADR 6.1.0001.
- **Cons:** overview §7/§8 and ADR 0.0.0020's second bullet need rewording (done with
  this ADR).

### Alternative B — Literal "own implementation in an adapter behind a port"
- **Description:** the DM/Christoffersen/Kupiec kernel lives in an adapter; the domain
  keeps bookkeeping.
- **Why rejected:** duplicates the formula the domain already needs (the domain cannot
  call the port, so it would re-implement it or push the verdict into a use case) and
  contradicts ADR 0.0.0020's own first bullet (line 54: "the DM statistic … depend only
  on the standard library").

### Alternative C — A "replay" port whose adapter serves the recorded R answers
- **Why rejected:** no production consumer; it answers only recorded inputs, so it
  satisfies the Protocol only nominally; production code would carry test data.

### Alternative D — Do nothing (leave the three texts inconsistent)
- **Why rejected:** every own-implemented statistic would reopen the question
  (6.2 and 6.3 in parallel).

## Consequences

### Positive
- Stages 6.2 and 6.3 follow one rule; the overview matches the code.

### Negative
- R oracle regeneration is a manual Docker step (ADR 6.2.0006).

### Neutral / trade-offs accepted
- "Wrapper próprio" in R-LIBS-1 now means the own domain formula plus pinned R
  fixtures, not an adapter.

## References

- Related ADRs: [0.0.0020](./0_0_0020-statistics-in-domain-over-value-objects.md) (amended),
  [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md),
  [6.1.0001](./6_1_0001-scoring-libraries-as-oracle-backend-behind-port.md),
  [6.2.0003](./6_2_0003-dm-holm-of-record-statsmodels-oracle-no-dm-wrapper.md),
  [6.2.0006](./6_2_0006-r-oracle-fixtures-provenance-and-scope.md).
- Overview §7, §8 (R-LIBS-1); LAYOUT §3.
- Issue [#114](https://github.com/MarceloSanC/financial-forecasting/issues/114).
