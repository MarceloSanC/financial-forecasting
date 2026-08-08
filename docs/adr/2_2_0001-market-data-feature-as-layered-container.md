---
title: ADR 2.2.0001 — Model the market_data feature as a layered import-linter container, proving inward-only in the first feature BC
description: Architecture Decision Record
when-use: Reference before adding a new feature bounded context to the import-linter containers, before changing how feature layers are modeled, or when deciding whether a feature needs its own layers contract
keywords: [adr, import-linter, layers, container, feature, market-data, hexagonal, inward-only, bounded-context, fitness-function]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "2.2.0001"
decision: The market_data feature is added to the existing hexagonal-layers import-linter contract as a layered container (adapters > application > domain), proving inward-only direction for the first feature bounded context, rather than getting a separate per-feature contract or staying unmodeled
context_stage: 2.2-market-data-ingestion
bounded_context: market_data
---

# ADR 2.2.0001 — Model the `market_data` feature as a layered import-linter container

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 2.2 introduces `market_data`, the **first bounded context under
`features/`**. Until now `features/` held only `__init__.py`; the only layered
container in `.importlinter` was `financial_forecasting.shared`. The
`hexagonal-layers` contract (ADR [1.3.0001](./1_3_0001-import-linter-as-architecture-fitness-function.md))
encodes the inward dependency rule (`adapters > application > domain`) **per
container** and explicitly anticipated this moment:

- `.importlinter` **line 42** (verbatim comment): *"Cada feature vira container
  ao ganhar layers."* ("Each feature becomes a container once it gains layers.")
- ADR 1.3.0001 lists as a known negative consequence: *"`layers`/`containers`
  modeling must track the real package tree as features are added; a new feature
  with populated layers may require touching `.importlinter` (a known, cheap
  maintenance cost)."*

`market_data` now ships three populated layers
(`domain` ← `application` ← `adapters/out`). Forces at play:

- **The thesis of the rebuild is mechanically-enforced hexagonal boundaries.**
  The prior repo rotted because the domain boundary was unenforced (23/36 domain
  files imported pandas/numpy/torch — ADR 1.3.0001 Context). The first feature
  must carry the same proof of dependency direction the `shared` container
  already carries, or the gate has a blind spot exactly where new code lands.
- **`gate_mode: strict`** for Stage 2.2 (roadmap): the architecture gate is
  blocking; "the feature compiles" is not evidence of inward-only.
- **import-linter `layers` contracts accept multiple containers** in a single
  contract block; modeling does not require one contract per container.
- **`exhaustive = False`** is already set, so a container that omits optional
  layers (this Stage has no `adapters/in` or `ports/in`) does not fail the build.

## Decision

Add `financial_forecasting.features.market_data` to the **`containers`** list of
the existing `hexagonal-layers` contract in `.importlinter`, alongside
`financial_forecasting.shared`. The contract's `layers` stack
(`(adapters)` / `application` / `domain`) and `exhaustive = False` are reused
as-is — `market_data` inherits the same inward-only rule (`adapters` may import
`application` may import `domain`; the reverse breaks the build).

The direction is proven the same way ADR 1.3.0001 mandates: an **intentional
break** (`import pandas` inside `features/market_data/domain`) must turn
`lint-imports` red, then is reverted with no production code left changed
(evidence recorded in `technical.md` §7). The architecture regression test
(`tests/architecture/test_import_contracts.py`) pins the contract so that
removing `market_data` from the containers fails the suite.

No new per-feature contract file or block is created: one `layers` contract with
two containers expresses the rule for both `shared` and `market_data`.

## Alternatives considered

### Alternative A — Leave `market_data` unmodeled (only `shared` is a container)

- **Description:** Keep `.importlinter` as-is; rely on `check_layout.py` and code
  review for the new feature's layering.
- **Pros:** Zero `.importlinter` change this Stage.
- **Cons:** The first feature — where most new code will land — would have **no**
  mechanical proof of inward-only direction. `check_layout.py` does not model the
  directed layer stack the way the `layers` contract does, and the indirect
  composition_root path is its documented blind spot. Contradicts line 42 and the
  `strict` gate.
- **Why rejected:** Reproduces the exact unenforced-boundary failure mode the
  rebuild exists to cure, precisely at the boundary that matters most.

### Alternative B — A separate `layers` contract per feature

- **Description:** Author a new `[importlinter:contract:market-data-layers]`
  block dedicated to `market_data`.
- **Pros:** Slightly more explicit per-feature naming.
- **Cons:** Duplicates the identical layer stack and `exhaustive`/options of the
  `shared` contract; every future feature would add another near-identical block,
  growing the file without expressing anything the multi-container form does not.
- **Why rejected:** `type = layers` already supports multiple containers in one
  contract; the multi-container form is the idiom ADR 1.3.0001 set up (line 42:
  "vira container", not "ganha contrato próprio"). DRY and cheaper to maintain.

### Alternative C — Feature-vs-feature `independence` contract

- **Description:** Add an `independence` contract isolating `market_data` from
  other features.
- **Pros:** Would prevent cross-feature coupling.
- **Cons:** There is only **one** feature today; `independence` needs ≥2 to mean
  anything, and it expresses isolation, **not** the inward direction this Stage
  must prove.
- **Why rejected:** Wrong shape and premature — ADR 1.3.0001 already deferred
  feature-vs-feature `independence` "until a second feature exists (no value
  today)." This Stage still has one feature.

## Consequences

### Positive

- The first feature BC carries the same mechanical inward-only proof as `shared`:
  `import pandas` (or any outward import) in `features/market_data/domain` turns
  the build red.
- The pattern for every future feature is now concrete: add the feature package
  to the `containers` list — one line, no new block.
- The architecture regression test extends naturally to cover the new container.

### Negative

- `.importlinter` now lists two containers; each new feature adds one more line
  (the cheap, known maintenance cost ADR 1.3.0001 already accepted).

### Neutral / trade-offs accepted

- We keep `exhaustive = False`: a feature that (today) lacks `adapters/in` or
  `ports/in` does not fail the build. We accept that the contract does not force
  a feature to populate every optional layer — it only forbids the wrong
  direction.
- Feature-vs-feature `independence` remains deferred until a second feature
  exists.

## Implementation notes

- Edit the `[importlinter:contract:hexagonal-layers]` block: append
  `financial_forecasting.features.market_data` under `containers`. Do not change
  the `layers` stack or `exhaustive`.
- Intentional-break verification: temporarily add `import pandas` to a
  `features/market_data/domain` module, confirm `uv run lint-imports` fails on
  the `hexagonal-layers`/`domain-purity` contract, revert. Record in
  `technical.md` §7.
- `check_layout.py` must stay green for the new feature's structure (correct
  `domain`/`application`/`adapters/out` placement).
- If LAYOUT and `.importlinter` ever disagree, LAYOUT is the source of truth and
  the contract is corrected (ADR 1.3.0001).

## References

- Related ADRs:
  [1.3.0001](./1_3_0001-import-linter-as-architecture-fitness-function.md)
  (import-linter as fitness function; per-container layers; "new feature may
  require touching .importlinter"),
  [0.0.0019](./0_0_0019-hexagonal-enforced.md) (enforce hexagonal by tooling),
  [2.1.0002](./2_1_0002-medallion-store-port-shape.md) (port-as-Protocol posture
  the feature follows).
- `.importlinter` line 42 (verbatim: "Cada feature vira container ao ganhar
  layers"); `[importlinter:contract:hexagonal-layers]`.
- `docs/LAYOUT.md` §1 (`features/<feature>/` per bounded context), §3 (inward
  direction).
- `docs/stages/2.2-market-data-ingestion/concept.md` §7 D1.
- External: import-linter docs — `layers` contract with multiple `containers`,
  `exhaustive`.
