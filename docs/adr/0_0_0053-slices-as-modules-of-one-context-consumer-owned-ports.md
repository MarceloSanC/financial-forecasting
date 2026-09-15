---
title: ADR 0.0.0053 — Vertical slices are modules of one bounded context; cross-slice behavior enters through consumer-owned Protocols (no Anticorruption Layer, no Shared Kernel)
description: Architecture Decision Record
when-use: Reference before adding any dependency between two slices under `features/` (modeling → analytics_store today; evaluation/inference → analytics_store tomorrow), before proposing an ACL/translator or a shared-kernel package between slices, or when questioning why `bc-independence` still lists data-only edges
keywords: [adr, bounded-context, vertical-slices, modules, dependency-inversion, protocol, duck-typing, anticorruption-layer, shared-kernel, context-map, bc-independence, import-linter, modeling, analytics_store]
status: accepted
created_at: 2026-09-14
updated_at: 2026-09-14
adr_id: 0.0.0053
decision: The four slices under `features/` (market_data, feature_engineering, modeling, analytics_store) are modules of a single bounded context, not separate contexts — so the rule governing their coupling is layering, dependency direction and acyclicity, not context mapping. When a slice needs behavior from another, it defines the port (a `Protocol`) in its own `application/ports/out/` and the supplier satisfies it structurally without importing the consumer; what may cross the boundary at runtime is data (the supplier's inbound-port DTOs and its value objects), declared edge by edge in the `bc-independence` contract. No Anticorruption Layer and no Shared Kernel are introduced between slices.
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0053 — Slices as modules of one context; consumer-owned ports

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Issue [#68](https://github.com/MarceloSanC/financial-forecasting/issues/68)
found three real defects in the coupling between `modeling` and
`analytics_store`:

- **(a)** the three confirmatory use cases (`RunBaselines`, `TrainGbmQuantile`,
  `TrainTft`) wrote `dim_run` **directly** into the `AnalyticsRepository` of the
  other slice, while predictions went through the use case `PersistPredictions`
  — any invariant the `analytics_store` application layer enforces for
  predictions was not enforced for `dim_run`, and two slices knew that table;
- **(b)** those use cases took the **concrete class** `PersistPredictions` in
  their constructors — the only non-`Protocol` collaborator they had;
- **(c)** the relation between the slices had never been *decided*: the
  `bc-independence` contract (issue #60) froze the existing edges, which stops
  growth but decides nothing.

The first version of #68 framed the problem as Evans' **Shared Kernel** and used
that pattern to argue "do not separate further". The framing was wrong: the
*Therefore* of SHARED KERNEL (DDD Reference, 2015) reads *"Designate with
an explicit boundary some subset of the domain model that **the teams** agree to
share [...] This explicitly shared stuff [...] shouldn't be changed without
consultation with the other team"*. It has the same precondition as
Customer/Supplier, Conformist, Anticorruption Layer and Open-host Service — two
teams — which the issue itself used to discard those four. Read to the end,
Evans' guidance for one developer, one repository and one CI is not a context map
at all: it is **continuous integration inside a single bounded context**, with
the slices as modules. `Candle`, `RunRecord`, `QuantileForecast` mean the same
thing in every slice; there is no shift of ubiquitous language — and Fowler
places the dominant boundary criterion in human culture precisely because *"models
act as Ubiquitous Language, you need a different model when the language changes"*
([BoundedContext](https://martinfowler.com/bliki/BoundedContext.html)); one
culture, one language, one model.

Forces:

- **Reproducibility wants one canonical definition of a table row.** A translator
  layer would give `modeling` its own copy of `RunRecord`/`QuantileForecast` —
  two definitions of the same `dim_run`/`fact_oos_predictions` line, the exact
  failure mode the identity work of ADR 5.2.0004 exists to prevent.
- **Dependency Inversion is a module-level principle, not a context-map one.**
  Martin's Dependency Rule — source-code dependencies point inward, toward the
  higher-level policy, which owns the abstraction the lower level implements
  ([The Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html))
  — applies to modules inside one context; Python `Protocol` makes it free —
  structural typing means the supplier satisfies the consumer's port with zero
  imports in either direction at runtime.
- **The pattern will be reapplied.** The `evaluation` (8 stages) and `inference`
  (4 stages) BCs read `analytics_store` by definition; whatever #68 establishes
  becomes the template for them.
- **The gate must keep telling the truth.** LAYOUT §7 already says the
  `bc-independence` rule enforces direction + acyclicity and "does NOT claim each
  slice is a separate Bounded Context"; this ADR is the decision that sentence
  was pointing at.

## Decision

1. **The four slices are modules of one bounded context.** `market_data`,
   `feature_engineering`, `modeling`, `analytics_store` share one ubiquitous
   language, one repository, one CI and one developer. The rule for coupling
   between them is the one that governs modules: **layer direction** (a slice's
   `application` may depend on another slice's `application` DTOs and `domain`
   VOs, never the reverse of the inward direction; adapters of one slice never
   import adapters of another) and **acyclicity**, enforced by
   `hexagonal-layers`, `check_layout.py` and `bc-independence`.
2. **Behavior crosses the boundary only through a port owned by the consumer.**
   When slice A needs slice B to *do* something, A declares a `Protocol` in
   `A/application/ports/out/` and B's use case satisfies it structurally.
   Concretely (#68): `modeling/application/ports/out/prediction_persister.py`
   (`PredictionPersister`) and `run_record_persister.py` (`RunRecordPersister`),
   satisfied by `analytics_store.PersistPredictions` and the new
   `analytics_store.PersistRunRecord`; the three confirmatory use cases receive
   the ports, not the concrete classes, and no longer receive the other slice's
   repository. The supplier does not import the consumer. Wiring happens only in
   the composition root.
3. **Data may cross the boundary; it is declared, not translated.** The consumer
   speaks the supplier's inbound-port DTOs (`PersistPredictionsCommand`,
   `PersistPredictionsResult`, `PersistRunRecordResult`) and the supplier's value
   objects (`QuantileForecast`, `RunRecord`). Each such runtime edge is listed one
   by one in `bc-independence.ignore_imports` with its reason; a new edge fails
   the build; a dead entry fails the build (`unmatched_ignore_imports_alerting =
   error`). The list is measured debt of *data* coupling, never of behavior.
4. **Every port a slice defines follows the fake + `[fake, real]` contract rule**
   of LAYOUT §7 and the `port-coverage` gate (#62), even when the "real" is
   another slice's use case rather than an infrastructure adapter
   (`tests/contract/features/modeling/test_persistence_ports_contract.py`).

## Alternatives considered

- **Anticorruption Layer between `modeling` and `analytics_store`** (Evans, DDD
  Reference — an isolating, translating layer for when *"control or
  communication is not adequate"*). Rejected:
  the trigger — an upstream model you do not control — does not exist; the
  layer would duplicate `QuantileForecast` and `RunRecord` inside `modeling`
  and require bidirectional translators, producing two definitions of the same
  table row. The project's ACL sits where the trigger is real: between adapters
  and `httpx`/LightGBM/`yfinance`/pytorch-forecasting (issue #69, #84).
- **Shared Kernel** (a package both slices agree to share). Rejected: its
  precondition is two teams that must consult each other before changing the
  shared subset; with one team it degenerates to "a module", which is what this
  ADR declares directly without borrowing a context-map name that implies a
  boundary that is not there.
- **Ports defined in the supplier (`analytics_store/application/ports/in/`) and
  imported by `modeling`.** Rejected: `modeling` would still import
  `analytics_store` for behavior (the abstraction would be owned by the
  low-level side), which is the dependency direction DIP exists to invert; the
  consumer-owned `Protocol` costs nothing more in Python.
- **A `modeling`-owned command DTO for `dim_run` instead of passing `RunRecord`.**
  Rejected: a DTO with the same ten fields is the "second definition of the
  same row" from the first alternative, one file smaller.
- **Separating more contexts / moving code between slices / including
  `market_data` in `bc-independence` now.** Out of scope: the nine
  `feature_engineering → market_data.domain.entities` edges (`Candle`,
  `NewsArticle`, `FundamentalReport` in port signatures) are data edges of the
  same kind as item 3; declaring them and adding `market_data` to the contract is
  issue [#95](https://github.com/MarceloSanC/financial-forecasting/issues/95)
  (speculative), which applies this ADR's rule rather than reopening it.

## Consequences

- No slice of `modeling` holds a concrete class or a repository of another slice;
  the structural isolation test of `RunTftSweep` (A10) now also forbids
  `persist_run_record`.
- `bc-independence.ignore_imports` keeps **12** entries — the same count as
  before #68 — but their nature changed: every remaining edge is a DTO, a VO or
  the feature registry. The comments in `.importlinter` say so per edge; the
  count is not the metric, the kind of edge is.
- Type-only references (`if TYPE_CHECKING:`) across the trio are now exactly the
  port signatures of `modeling` annotating supplier DTOs/VOs.
- The `port-coverage` gate cannot yet see a "real" implementation that is another
  slice's use case (by design it does not cite the consumer's port); the two #68
  ports are in `scripts/arch_baseline.toml` pointing at issue #93, which teaches
  the gate the pattern this ADR makes standard.
- When `evaluation`/`inference` arrive: define their ports in their own
  `application/ports/out/`, let `analytics_store` satisfy them, declare the data
  edges — and do not open a context-map discussion.

## Implementation notes

- Owner use case for `dim_run`:
  `analytics_store/application/use_cases/persist_run_record.py` (takes the VO
  `RunRecord`, writes `silver.dim_run`, relies on the registry's `upsert` policy
  and on the adapter for `created_at_utc`).
- Golden captured before and after the move (full `dim_run` and
  `fact_oos_predictions` rows of the three use cases on the identity-golden
  scenario): byte-identical — the refactor changes no persisted value.
- Gates touched: `.importlinter` (comments only; list unchanged), LAYOUT §7 note
  of scope, `scripts/arch_baseline.toml` (two `port_coverage` entries → #93).

## References

- Issue [#68](https://github.com/MarceloSanC/financial-forecasting/issues/68)
  (rewritten framing), [#60](https://github.com/MarceloSanC/financial-forecasting/issues/60)
  / PR #63 (`bc-independence`), [#62](https://github.com/MarceloSanC/financial-forecasting/issues/62)
  (port-coverage gate), [#93](https://github.com/MarceloSanC/financial-forecasting/issues/93)
- Evans, E. *Domain-Driven Design Reference* (2015): SHARED KERNEL,
  ANTICORRUPTION LAYER, CONTINUOUS INTEGRATION (quotes as carried in issue #68) —
  https://www.domainlanguage.com/wp-content/uploads/2016/05/DDD_Reference_2015-03.pdf
- Martin, R. C. *The Clean Architecture* (2012) — Dependency Rule / DIP —
  https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html
- Fowler, M. *BoundedContext* — https://martinfowler.com/bliki/BoundedContext.html
- Cockburn, A. *Hexagonal architecture* — *"What exactly a port is and isn't is
  largely a matter of taste"* (the pattern does not mandate port ownership; DIP does)
- [`docs/LAYOUT.md`](../LAYOUT.md) §7; ADR 4.3.0001 (single owner of
  `target_timestamp`); ADR 5.2.0004 (canonical run identity)
