---
title: ADR 0.0.0020 — Statistics as pure domain services over value objects
description: Architecture Decision Record
when-use: Reference when deciding where a metric/test belongs (domain vs adapter), or before computing statistics directly on a DataFrame
keywords: [adr, domain, value-object, statistics, pinball, crps, dm, mcs, ports, adapters, pure-function]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "0.0.0020"
decision: Confirmatory statistics are pure domain services over typed value objects; numeric/statistical libraries live behind ports in adapters
context_stage: 1.1-bootstrap
bounded_context: transversal
---

# ADR 0.0.0020 — Statistics as pure domain services over value objects

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The confirmatory methodology — pinball/CRPS, Diebold–Mariano + Holm + MCS, PICP +
Christoffersen, MPIW/Winkler, VaR backtesting — is the scientific core of the project and the
evidence the thesis stands on. The question is **where this logic lives** in the hexagonal
structure decided by ADR 0.0.0001.

Forces at play:

- In the prior implementation (Overview §2) the statistics layer was "entirely hand-rolled,
  including a known bug," and was fused with the data layer. Because the math lived inside
  pandas/notebook code paths, it could not be tested in isolation, and a single error
  contaminated results without detection.
- The project's domain-purity rule (Overview §6; ADR 0.0.0019) forbids pandas/pyarrow/torch in
  `domain`. But the statistics *must* be testable in isolation against an oracle (ADR 0.0.0021,
  Overview §4 "Estatística defensável").
- The methodology has stable, well-defined inputs: aligned paired loss series, quantile forecasts,
  coverage series. These are natural **value objects** with invariants (alignment, one observation
  per unit, monotonic quantiles) that should be enforced once, at construction.
- Reliable libraries (`arch`, `statsmodels`, `scikit-learn`, `scoringrules`, `MAPIE`) should do
  the heavy lifting — but they carry framework/numeric dependencies that must not leak into the
  domain.

## Decision

Confirmatory statistics are implemented as **pure domain services operating on typed value
objects**, with libraries confined to adapters behind ports:

- **Domain (stdlib-only, pure):** value objects such as `PairedLossSeries`, `QuantileForecast`,
  `CoverageSeries` carry their invariants (aligned, one obs/unit, monotonicity) and are immutable.
  The statistical operations expressed as pure functions/services over these VOs — pinball, CRPS,
  the DM statistic, MCS bookkeeping, Christoffersen — depend only on the standard library.
- **Adapters (out):** libraries that compute or accelerate these quantities (`arch` for MCS/
  bootstrap/VaR, `statsmodels` for Holm/HAC, `sklearn`/`scoringrules` for pinball/Winkler/CRPS,
  `MAPIE` for CQR, `pandas`+`duckdb` for the transformations feeding the VOs) live behind ports.
  Where no canonical Python library exists (Diebold–Mariano, Christoffersen, Kupiec), a thin
  own-implementation sits behind a port and is validated against an R oracle.

The boundary is exactly the value object: data engineering (pandas/duckdb) produces VOs at the
adapter edge; the domain consumes VOs and returns results; no statistical decision logic touches
a DataFrame.

## Alternatives considered

### Alternative A — Statistics directly in pandas / notebooks (status quo)
- **Description:** Compute metrics and tests inline on DataFrames in the data/analysis layer, as
  the prior implementation did.
- **Pros:** Fast to write; pandas vectorization is convenient; matches typical DS workflow.
- **Cons:** Not testable in isolation; couples science to the data layer; a bug (as already
  happened) propagates undetected; cannot be audited or oracle-checked per unit; entrenches a
  monolith.
- **Why rejected:** This is the documented failure mode of the prior codebase — un-auditable,
  un-isolable, harboring a known bug.

### Alternative B — Statistics in the application layer (use cases) over DTOs
- **Description:** Put the math in use cases operating on DTOs, keeping domain as data-only.
- **Pros:** Keeps domain thin; application can orchestrate libraries directly.
- **Cons:** The methodology *is* the business logic of this project; pushing it to application
  with library access blurs the very boundary we are protecting and tempts direct library use in
  the orchestration layer. Invariants (alignment, monotonicity) end up unenforced or duplicated.
- **Why rejected:** Misplaces the scientific core. In this project the statistics are domain logic,
  not orchestration; they belong with the value objects that enforce their preconditions.

### Alternative C — Do nothing / leave placement to each metric's author
- **Description:** No rule; each metric lands wherever convenient when implemented.
- **Why rejected:** Guarantees drift — some metrics in pandas, some in domain — reproducing the
  inconsistency that made the prior codebase un-auditable.

## Consequences

### Positive
- Each metric/test is a pure function testable in isolation against an analytic fixture and a
  library/R oracle (ADR 0.0.0021).
- The science is decoupled from the data layer; swapping the data engine or a library is an
  adapter change, not a rewrite of the methodology.
- Invariants are enforced once, at VO construction, so downstream math can assume them.

### Negative
- More ceremony: every statistic needs a VO with invariants and (often) a port + adapter, rather
  than one pandas line.
- Re-implementing DM/Christoffersen/Kupiec in stdlib (no canonical lib) is real work, justified by
  oracle tests.

### Neutral / trade-offs accepted
- We accept that some convenient pandas one-liners become a VO + service + adapter triple, in
  exchange for isolated testability and auditability.

## Implementation notes

- Value objects and services land in later Step-3/Step-4 stages; this ADR fixes the placement rule
  consumed by all of them. No statistical code is introduced in Stage 1.1.
- Domain purity (no pandas/pyarrow/torch) is enforced by `check_layout.py` (1.1) and import-linter
  (1.3) per ADR 0.0.0019.

## References

- Related ADRs: [0.0.0001](./0_0_0001-hexagonal-from-day-one.md),
  [0.0.0019](./0_0_0019-hexagonal-enforced.md) (enforcement),
  [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md) (how these services are tested).
- Overview: `docs/overview.md` §2, §6 (Restrições — domínio puro), §7 (Abordagem),
  §11 (Arquitetura e ferramentas).
