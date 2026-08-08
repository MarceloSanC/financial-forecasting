---
title: ADR 1.2.0011 — Treat the CI quality gate (lint+types+layout+tests+coverage≥90%) as a single foundational fitness function
description: Architecture Decision Record
when-use: Reference when deciding whether a new quality check belongs in the blocking CI gate, or when wondering why CI green is defined as "all five checks pass" rather than "tests pass"
keywords: [adr, fitness-function, ci, gate, coverage, enforcement-as-test, fronteiras-enforcadas, blocking, merge]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "1.2.0011"
decision: Define "CI green" as a single blocking fitness function — ruff + mypy --strict + check_layout.py + pytest + coverage ≥ 90% must all pass for a PR to merge — implemented as one lint-and-test job running `make check`
context_stage: 1.2-ci-coverage
bounded_context: shared
---

# ADR 1.2.0011 — Treat the CI quality gate as a single foundational fitness function

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

This is a foundational ADR derived from overview §4 ("Fronteiras enforçadas") and §7
("enforcement-as-test"). The project's stated root cause of the previous implementation's decay was
that architectural and quality rules existed only as **prose and intention**, not as automated
checks — "mexer num ponto quebrava vários" (overview §7; ADR 0.0.0019). The chosen cure is to turn
the rules into **fitness functions**: executable checks that fail the build when a boundary is
crossed.

Stage 1.1 assembled the individual checks (`ruff`, `mypy --strict`, `scripts/check_layout.py`,
`pytest`, and a `fail_under=90` coverage config) and wired a CI workflow that runs `make check`. But
Stage 1.1 left the coverage portion inert (F3 — see ADR 1.2.0010): the gate's *parts* existed without
being composed into one enforced contract.

The forces: GitHub Free gives no branch protection on private repos, so "what blocks a merge" must be
expressed as a **required status check** rather than relying on repo settings; the project is solo,
so the gate is the main safety net; and the value of a gate is binary — a check that does not block
is decoration.

## Decision

Define **"CI green"** as a **single foundational fitness function**: a PR may merge **only if**
*all* of the following pass, and the failure of *any one* fails the job and blocks the merge:

1. `ruff check` (style/lint),
2. `mypy --strict` (types),
3. `scripts/check_layout.py` (hexagonal dependency direction — the import contract for Stage 1.2; see
   ADR 1.2.0010 D3),
4. `pytest` (the test suite),
5. coverage `≥ 90%` of live, in-scope code (`fail_under=90`).

This contract is implemented as **one** CI job (`lint-and-test`) running `make check`, which chains
the five checks. Coverage is part of `make check` via `pytest --cov` (ADR 1.2.0010 D1), so there is
**no separate coverage step that could be skipped**. The `guard-main-source` job (PR-base guard) is
orthogonal and preserved. New quality checks join *this* gate rather than spawning parallel,
non-blocking reports.

The gate's effectiveness is proven, not assumed: each of the five failure modes is validated by an
**intentional break, reverted** (the Stage's DoD), so we have evidence the gate reproves rather than
trusting configuration.

## Alternatives considered

### Alternative A — Keep checks as separate, individually-optional CI steps
- **Description:** Run lint, types, tests, coverage as independent steps/jobs; coverage as an
  upload/report rather than a `fail_under` gate (as the old repo and the Stage 1.1 README described:
  "Upload do relatório de cobertura").
- **Pros:** Granular; a flaky check can be made non-blocking individually.
- **Cons:** This is exactly the failure mode F3 — a report that never blocks. "CI green" stops
  meaning "all boundaries held". Optionality erodes the gate over time.
- **Why rejected:** Defeats enforcement-as-test (overview §7). A boundary that does not block is not
  enforced.

### Alternative B — Fragment into multiple chained jobs (`needs:`), one check per job
- **Description:** Separate jobs for lint, typecheck, test, coverage with dependency edges.
- **Pros:** Clearer per-check status badges; parallelism.
- **Cons:** More YAML, more runner minutes on Free, more moving parts, for a single small gate. The
  old repo's two-job split bought nothing for this project's scale.
- **Why rejected:** Simple-and-replaceable wins: one `lint-and-test` job running `make check` is the
  minimal honest gate. Fragmentation is a later optimization if it ever pays off.

### Alternative C — Do nothing / status quo
- **Description:** Ship Stage 1.1's workflow unchanged.
- **Why rejected:** Coverage stays inert (F3); the fitness-function premise of the project is unmet
  at its foundation.

## Consequences

### Positive
- "CI green" has a single, precise, auditable meaning enforced identically locally (`make check`) and
  in CI.
- The foundation matches the project's premise: every boundary that matters is an executable,
  blocking check.
- Adding a future check (e.g., import-linter in Stage 1.3) is a well-defined act: extend `make check`
  / the one job, keep it blocking.

### Negative
- A single chained job means one failing check stops the rest from reporting in the same run (no
  parallel per-check feedback). Accepted for a small gate; local `make lint`/`typecheck`/etc. give
  granular feedback during development.

### Neutral / trade-offs accepted
- We accept that the `guard-main-source` job stays separate (it gates PR *origin*, not code quality).
- The exact composition of `make check` is the contract; it is allowed to grow (1.3 import-linter) as
  long as it stays blocking.

## Implementation notes

- Implemented across `Makefile` (`check` chains lint→typecheck→layout-check→docs-check→test-with-cov),
  `pyproject.toml` (`fail_under=90`), and `.github/workflows/ci.yml` (single `lint-and-test` job,
  `timeout-minutes` per job, `guard-main-source` preserved).
- README documents the contract and the workflow status badge.

## References

- Related ADRs: [0.0.0019](./0_0_0019-hexagonal-enforced.md) (hexagonal enforced by tooling — the
  origin of the fitness-function posture), [1.2.0010](./1_2_0010-cobertura-no-ci-e-tratamento-do-excedente-herdado.md)
  (how coverage is made effective and how the surplus is treated), [1.1.0001](./1_1_0001-template-surplus-handling.md)
  (the inherited surplus).
- Overview: §4 (Critérios de sucesso — fronteiras enforçadas, cobertura ≥ 90%), §7 (abordagem —
  enforcement-as-test).
- Roadmap: Step 1 ("qualquer mudança que viole arquitetura/cobertura é barrada automaticamente antes
  do merge"), Stage 1.2.
</content>
</invoke>
