---
title: ADR 0.0.0019 — Enforce hexagonal boundaries by tooling, not by review
description: Architecture Decision Record
when-use: Reference when questioning why dependency rules are machine-checked, or before relaxing a layer/import gate
keywords: [adr, hexagonal, enforcement, import-linter, check-layout, fitness-function, dependency-rule]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "0.0.0019"
decision: The hexagonal dependency rule is enforced by an automated gate (check_layout.py now, import-linter from Stage 1.3) that fails the build, not by code review
context_stage: 1.1-bootstrap
---

# ADR 0.0.0019 — Enforce hexagonal boundaries by tooling, not by review

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

ADR [0.0.0001](./0_0_0001-hexagonal-from-day-one.md) already commits the project to a hexagonal
(ports-and-adapters) structure with vertical slices from day one. That ADR decides the *shape*.
This ADR decides **how the shape is kept true over time**.

Forces at play:

- The explicit motivation for the rebuild (Overview §2) is that the **prior implementation rotted
  into architectural debt** precisely because the dependency rule was *not* enforced: scientific
  logic ended up coupled to the data layer, there was no single composition point, and "fixing one
  bug required editing many files." The codebase became un-auditable.
- The structure of ADR 0.0.0001 is worthless if nothing prevents regression. A pure `domain/`
  that nobody stops from `import pandas` is pure only until the first deadline.
- The team is effectively solo (Overview §6) and works overnight in autonomous sessions. There is
  no second reviewer to catch a sideways import in real time. Review-based enforcement has no
  reviewer.
- Academic defensibility (Overview §4, "fronteiras enforçadas… build falha se violado") requires
  that the architecture claim be *verifiable*, not asserted.

## Decision

Hexagonal boundaries are a **fitness function**: the dependency rule is encoded as an automated
check that **fails the build** when violated. Enforcement is staged:

- **Stage 1.1 (now):** `scripts/check_layout.py`, invoked by `make check`, is the active gate. It
  verifies import direction (domain imports nothing project-internal nor pandas/pyarrow/torch/
  pydantic/sqlalchemy; application imports domain + shared ports only; adapters never import
  sideways into another feature's adapters; shared never imports from features).
- **Stage 1.3 (`1.3-architecture-contracts`):** `import-linter` contracts mirroring `LAYOUT.md`
  replace/augment the script as the canonical enforcement, wired into CI (Stage 1.2). The
  domain-purity contract (no pandas/pyarrow/torch in `domain`) becomes a build-breaking import
  contract.

The principle is **enforcement-as-test** (Overview §7): architecture rules live as executable
gates in the same pipeline as the tests, so a violating change cannot merge.

## Alternatives considered

### Alternative A — Enforce by code review / convention only
- **Description:** Document the rules in `LAYOUT.md` and `CLAUDE.md` and rely on humans (and AI
  agents reading the docs) to honor them in review.
- **Pros:** Zero tooling to build or maintain; no false positives; flexible.
- **Cons:** Exactly how the prior codebase rotted — conventions decay silently, and there is no
  reviewer in a solo/overnight workflow. Docs alone demonstrably did not hold.
- **Why rejected:** This is the failure mode the rebuild exists to cure ("mexer num ponto quebra
  vários"). A rule that isn't checked isn't a rule.

### Alternative B — mypy / linter rules only (no dedicated layer check)
- **Description:** Lean on mypy strict and Ruff to indirectly discourage bad imports.
- **Pros:** Tools already in the stack; no extra dependency.
- **Cons:** Neither mypy nor Ruff understands *layer direction* (that `domain` may not import
  `adapters`). They catch type and style errors, not architectural ones.
- **Why rejected:** Wrong tool — type/lint gates are necessary but cannot express the dependency
  rule. (They remain in the stack alongside the layer gate.)

### Alternative C — Do nothing / status quo
- **Description:** Keep the hexagonal folders but add no automated boundary check.
- **Why rejected:** Folders without a gate are decoration. The whole point of the rebuild is a
  *verified* boundary; "do nothing" reproduces the debt.

## Consequences

### Positive
- Architectural regression is caught at `make check` / CI, before merge, automatically.
- The architecture claim becomes auditable evidence for the thesis, not an assertion.
- AI agents and future contributors get immediate, unambiguous feedback on misplaced imports.

### Negative
- Two enforcement mechanisms coexist briefly (`check_layout.py` in 1.1 → import-linter in 1.3);
  the handoff must be deliberate so coverage never drops.
- A strict gate occasionally blocks a legitimate-looking change, forcing the author to route it
  through a port instead of a shortcut import (this friction is the intended behavior).

### Neutral / trade-offs accepted
- We accept the upfront cost of authoring and maintaining `check_layout.py` and, later, the
  import-linter contracts, in exchange for permanent regression protection.

## Implementation notes

- Stage 1.1 gate: `scripts/check_layout.py` (already present, passing under `make check`).
- Stage 1.3 will add `.importlinter` + `tests/architecture/test_import_contracts.py` and wire them
  into the CI workflow from Stage 1.2. No import-linter artifact is introduced in 1.1 (non-goal).

## References

- Related ADRs: [0.0.0001](./0_0_0001-hexagonal-from-day-one.md) (the structure this gate protects);
  [0.0.0020](./0_0_0020-statistics-in-domain-over-value-objects.md) (what lives behind the boundary).
- Overview: `docs/overview.md` §2 (Problema), §4 (Critérios de sucesso), §6 (Restrições), §7 (Abordagem).
- LAYOUT: `docs/LAYOUT.md` §3 (regras de dependência).
