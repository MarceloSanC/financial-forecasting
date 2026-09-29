---
title: ADR 6.4.0001 — Gold builders declare their upstream builders; gold_build_order checks duplicates, unknown dependencies and cycles and returns a stdlib graphlib order fixed before any read
description: Architecture Decision Record
when-use: Reference when adding a gold builder, when asking where the build order of the gold tables comes from, or before proposing a pipeline framework (dbt, Dagster) or a shared mutable context between builders
keywords: [adr, evaluation, gold, builders, dag, graphlib, topological-order, dependencies, determinism, reconstructibility]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-29
adr_id: 6.4.0001
decision: Every GoldBuilder declares a name, the frozen set of upstream builder names it depends on and whether it runs when the refresh is blocked; the domain service gold_build_order takes the sequence of (name, depends_on) pairs, raises ValueError on a duplicate name, a self-dependency, a dependency on an unregistered builder or a cycle, inserts the nodes into graphlib.TopologicalSorter in sorted name order and returns static_order(), so the same set of builders always yields the same order; RefreshGold computes it before reading the silver; builders share no mutable context — each maps the same immutable GoldInputs to one table.
context_stage: 6.4-gold-builders-and-quality-gates
bounded_context: evaluation
---

# ADR 6.4.0001 — Gold build order from declared dependencies

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The roadmap (§Stage 6.4, DoD) requires gold builders that "declaram
dependências explícitas (não dict compartilhado); ordem derivada da
topologia". The old project ordered builders by hand and passed a shared
mutable dict between them — the order was implicit and a builder could read
whatever an earlier one happened to leave. Sculley et al. (2015, §5 "Pipeline
Jungles") name this failure; issue #117 (P1) collected the evidence.

Stage 6.4 has five builders (`quality_checks`, `metrics_by_run`,
`calibration_table`, `dm_results`, `mcs_results`). The real edge today is
"every table depends on `quality_checks`": a blocking quality failure must
keep the dependent tables out of the published gold (dbt `build` semantics,
verified: "a test failure will cause those downstream resources to skip
entirely").

Library behaviour, verified on CPython 3.13 in this session and against the
`graphlib` docs (evidence-verifier, 2026-09-29):

- `prepare()` raises `CycleError`; "The detected cycle can be accessed via
  the second element in the args attribute";
- `add()`: "If a node that has not been provided before is included among
  *predecessors* it will be automatically added to the graph with no
  predecessors of its own" — a dependency on a builder that does not exist is
  **not** detected;
- the order returned depends on insertion order (`q,m,c,d,x` vs `q,x,d,c,m`
  for the same graph inserted in two orders); with sorted insertion every
  permutation of registration yields one order (probe of the Checkpoint A
  reviewer, 120 permutations).

## Decision

`[decision:E] 6.4-C1a — engine of the order`
`Escolha: stdlib graphlib · Alternativas: dbt/Dagster; hand-written Kahn · Degrau (C): —`
`Base: CPython docs graphlib "If any cycle is detected, CycleError will be raised" [verified]; roadmap 6.4 DoD`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

`[decision:C] 6.4-C1b — where the order lives and how it is made deterministic`
`Escolha: domain service gold_build_order over (name, depends_on) pairs, sorted insertion, own duplicate/unknown/self checks · Alternativas: order inside the use case; insertion in registration order · Degrau (C): 5`
`Base: graphlib add() "automatically added to the graph with no predecessors" [verified]; overview "gold = decisão reconstruível"`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

1. `GoldBuilder` (port-out, application) exposes `name: str`,
   `depends_on: frozenset[str]` and `runs_when_blocked: bool` (ADR 6.4.0005
   item 4), and `build(inputs) -> GoldTable` (a pure mapping of reports to
   rows; the write belongs to `GoldStore`, ADR 6.4.0005).
2. `gold_build_order(builders: Sequence[tuple[str, frozenset[str]]]) ->
   tuple[str, ...]` is a stdlib-only domain service and the **single owner**
   of the graph rules: `ValueError` on a duplicate name, a self-dependency, a
   dependency naming an unregistered builder (the message names both) and a
   cycle (the message carries `CycleError.args[1]`).
3. Nodes are inserted in **sorted name order**, so the order is a function of
   the declared graph only.
4. `RefreshGold` computes the order **first**, before reading the silver — a
   mis-declared graph never costs a read or a computation.
5. Builders share no mutable state: each receives the same frozen
   `GoldInputs` and returns one table.

## Alternatives considered

### Alternative A — dbt or Dagster

- **Pros:** DAG, severity and skip semantics out of the box.
- **Cons:** a heavy runtime dependency and a second configuration language for
  five nodes; the statistics would have to leave the domain services to fit
  the framework's model abstraction (ADR 0.0.0020).
- **Why rejected:** the only features needed are the order and the skip,
  which are a dozen lines over `graphlib`. The frameworks were consulted for
  semantics (skip on error, `warn` does not skip), which this ADR and
  ADR 6.4.0002 copy.

### Alternative B — Order inside the use case, registration order

- **Why rejected:** the rule "cycle / unknown dependency is an error before
  any read" would be untestable without the use case's fakes, and the order
  would change when the composition root lists builders differently.

### Alternative C — Hard-coded list

- **Why rejected:** the roadmap DoD forbids an order that is not derived from
  declared dependencies.

## Consequences

### Positive

- The order is deterministic and testable in unit tests without I/O.
- A new table built from inputs that `GoldInputs` already carries is one
  adapter and one `depends_on`.

### Negative

- With five builders the graph is shallow; the machinery is justified by the
  DoD, not by today's depth.
- The DAG orders **tables**, not inputs. A profile that needs series
  `GoldInputs` does not carry (DM per fold or per seed, DM per τ — concept
  §Fora do escopo) is **not** "just a builder": 6.5 would build those series by
  reusing `SeriesAssembly` and the 6.2 services (and, for per-fold profiles,
  carrying `fold` through the assembled samples), then add a builder for the
  table.

## References

- Roadmap §Stage 6.4 (DoD); issue #117 P1.
- Python docs, `graphlib` — https://docs.python.org/3/library/graphlib.html
- Sculley, D. et al. (2015). "Hidden Technical Debt in Machine Learning
  Systems". NeurIPS 28, §5.
- dbt docs, `dbt build` (DAG order; downstream skip on test failure).
- Related ADRs: 6.4.0002, 6.4.0005.
