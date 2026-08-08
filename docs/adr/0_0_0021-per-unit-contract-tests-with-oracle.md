---
title: ADR 0.0.0021 — Per-unit regression tests against an oracle, not global byte-identical snapshots
description: Architecture Decision Record
when-use: Reference when deciding how to test a metric/test for correctness, or before adding an end-to-end snapshot assertion
keywords: [adr, testing, oracle, regression, fixture, golden-test, snapshot, calibration, dm-test, R]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "0.0.0021"
decision: Correctness is asserted per unit against an oracle (analytic fixture + library/R), never via a global byte-identical pipeline snapshot
context_stage: 1.1-bootstrap
bounded_context: transversal
---

# ADR 0.0.0021 — Per-unit regression tests against an oracle, not global byte-identical snapshots

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The confirmatory statistics (ADR 0.0.0020) must be *correct*, and correctness must be
*demonstrable* for the thesis defense. The question is **what kind of test establishes
correctness**.

Forces at play:

- The rebuild is greenfield, but a **prior implementation's results exist**. The temptation is to
  freeze the whole pipeline's output and assert the new code reproduces it byte-for-byte.
- However, the rebuild is a **re-train on a new numeric stack** (torch/ROCm, new library
  versions). Byte-identical reproduction is impossible by construction (ASSUM-4: equivalence is
  asserted with *declared tolerance*, not bit-identity).
- The prior codebase carried a **known statistical bug**. A snapshot of its output would
  *entrench the bug* as the "expected" value — the regression test would defend the error.
- A global snapshot couples the test to the entire pipeline: any legitimate refactor (a renamed
  column, a reordered join, a new feature) breaks the snapshot for reasons unrelated to
  correctness, making refactoring expensive and pushing the team back toward the monolith they are
  escaping (Overview §7).
- Each statistical unit (pinball, DM, Christoffersen, MCS, CRPS, Winkler) has a *known correct
  answer* available independently: an analytic value on a hand-built fixture, and/or the output of
  a canonical library or R routine (`dm.test`, `rugarch`, `scoringrules`).

## Decision

Correctness is established by **per-unit regression tests against an oracle**, never by a global
byte-identical pipeline snapshot. For each statistical unit:

- A **small analytic fixture** with a hand-computable expected result (e.g. degenerate/known
  inputs where the metric has a closed form), asserted within tolerance; and/or
- A **library/R oracle** (`scoringrules`, `arch`, `statsmodels`, R `dm.test`/`rugarch`) computing
  the same quantity on the same fixture, asserted within a **declared numeric tolerance**.

Equivalence to prior evidence (when used at all) is a **tolerance-bounded comparison**
(ASSUM-4), treated as a sanity signal — never as the authority that defines "correct." Real adapters
get **contract tests**; the application/domain is tested with fakes of the ports (project testing
convention).

## Alternatives considered

### Alternative A — Global byte-identical snapshot of pipeline output
- **Description:** Run the full pipeline, freeze the final artifact, and assert future runs
  reproduce it byte-for-byte.
- **Pros:** One test "covers everything"; trivial to write initially; catches any change.
- **Cons:** Impossible across a re-train on a new numeric stack (non-deterministic to the bit);
  entrenches the prior implementation's *known bug* as expected truth; breaks on every benign
  refactor, making the cost of cleaning up the monolith prohibitive; gives no localized signal
  (a red snapshot says "something changed," not "this metric is wrong").
- **Why rejected:** Expensive to refactor against, entrenches the monolith and its bug, and is
  numerically infeasible here. It defends the past instead of verifying correctness.

### Alternative B — Trust the libraries, test nothing
- **Description:** Assume `arch`/`statsmodels`/`scoringrules` are correct and skip oracle tests.
- **Pros:** Least effort.
- **Cons:** The project re-implements units with no canonical Python library (DM, Christoffersen,
  Kupiec) where the library *cannot* be trusted because it doesn't exist; library wiring (wrong
  axis, wrong sign, wrong HAC lag) is exactly where bugs hide; gives no defensible evidence for
  the thesis.
- **Why rejected:** Leaves the own-implemented units unverified and provides no audit trail.

### Alternative C — Do nothing / ad-hoc manual checks
- **Description:** Eyeball results in a notebook when something looks off.
- **Why rejected:** Non-reproducible, non-auditable, and exactly the discipline gap that let the
  prior bug survive.

## Consequences

### Positive
- Each metric is verified against a known-correct answer, localized and auditable per unit.
- Refactoring the pipeline is cheap: a benign change touches no unit test unless it changes a
  unit's contract.
- The own-implemented units (DM/Christoffersen/Kupiec) get an explicit R-oracle provenance
  defensible at the thesis defense.

### Negative
- Authoring fixtures and oracle harnesses (including an R dependency for some oracles) is upfront
  work, per unit.
- Declared tolerances must be chosen and justified; a too-loose tolerance hides error, too-tight
  flakes on float noise.

### Neutral / trade-offs accepted
- We accept that there is **no single "the whole thing reproduces" test**; confidence is the
  conjunction of per-unit oracle tests plus tolerance-bounded equivalence checks.
- We accept tolerance-based (not bit-identical) equivalence to prior evidence (ASSUM-4).

## Implementation notes

- Test layout follows the project convention: `tests/unit/...` (analytic fixtures), `tests/contract/...`
  (real adapter vs port), fakes for application/domain. R-oracle harnesses are version-pinned and
  documented per unit when introduced (later stages). No statistical test is introduced in Stage 1.1.

## References

- Related ADRs: [0.0.0020](./0_0_0020-statistics-in-domain-over-value-objects.md) (what is tested),
  [0.0.0019](./0_0_0019-hexagonal-enforced.md) (architecture gates that complement these tests).
- Overview: `docs/overview.md` §2, §4 (Critérios de sucesso — "validado contra oráculo"),
  §7 (Abordagem — contratos por unidade + oráculo), §8 (Riscos), ASSUM-4.
