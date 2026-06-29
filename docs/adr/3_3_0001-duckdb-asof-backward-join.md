---
title: ADR 3.3.0001 — Fundamentals as-of join is a DuckDB ASOF JOIN backward behind a Protocol port, with the anti-leakage invariant re-checked in the pure domain (defense-in-depth)
description: Architecture Decision Record
when-use: Reference before changing the as-of join engine, the AsofJoinAdapter port shape, the effective_date <= date invariant, or the fundamentals_effective_date audit column
keywords: [adr, fundamentals, as-of, asof-backward, duckdb, match-condition, merge-asof, anti-leakage, effective-date, asof-join-adapter, protocol, defense-in-depth, fundamentals-effective-date]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "3.3.0001"
decision: The point-in-time fundamentals join is implemented as a DuckDB ASOF JOIN backward (d.date >= f.effective_date) confined to an adapter behind the AsofJoinAdapter Protocol port; it mirrors the old pandas merge_asof(direction=backward), exposes a fundamentals_effective_date audit column, and the effective_date <= date anti-leakage invariant is enforced both by the join condition and by an explicit re-check in the pure domain (defense-in-depth)
context_stage: 3.3-fundamentals-asof-join
---

# ADR 3.3.0001 — Fundamentals as-of join = DuckDB ASOF JOIN backward

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 3.3 adds the point-in-time fundamentals feature to the `feature_engineering`
BC. Each trading day must receive the **last fundamental report visible at that day**,
where "visible" means `effective_date <= day` and `effective_date = reported_date or
(fiscal_date_end + 45 calendar days)` (ledger H-3). The temporal-validity rule is the
*reason this Stage exists*: `effective_date <= date` is the as-of-backward invariant
of foundational ADR `0.0.0018` (rule 2), and a future effective date must **raise**,
never be silently used.

Forces at play:

- **The prior repo already encoded the semantics**, ad hoc, inside a monolithic use
  case: `build_tft_dataset_use_case.py:513-535` used
  `pandas.merge_asof(left_on="date", right_on="effective_date", direction="backward")`
  and then raised `ValueError` if any `fundamentals_effective_date > date`. The
  semantics (last `effective_date <= date`) are correct and worth porting; the shape
  (pandas inside a god-use-case) is not.
- **The data engine is already DuckDB.** Overview §11 (`0.0.0022`) fixes "engine de
  dados = pandas + duckdb … SQL rápido e **as-of joins** sobre Parquet", and the
  `MedallionStore` read adapter (Stage 2.1) already runs DuckDB. The ledger §B line
  3.3 pre-declares "DuckDB ASOF backward (novo) portando a lógica do `merge_asof`".
- **Domain must stay pure.** The `feature_engineering.{application,domain}` layers are
  already forbidden from importing `duckdb`/`pandas`/`pyarrow`/`pandera` by the
  `import-linter` `store-no-storage-leak` contract (Stages 2.1/3.1). The join engine
  must live in an adapter; the policy (effective_date + invariant) must live in the
  pure domain.
- **The invariant is too important for one guard.** A single enforcement point that
  could be bypassed (e.g. a future change to the SQL) is a single point of failure for
  the central claim. Defense-in-depth is warranted.

## Decision

Implement the fundamentals point-in-time join as a **DuckDB ASOF JOIN backward**,
confined to the adapter `feature_engineering/adapters/out/duckdb/asof_join_adapter.py`,
behind a **`Protocol`** port `AsofJoinAdapter`
(`application/ports/out/asof_join.py`). The join matches, for each trading day `d`,
the row `f` with the **greatest `f.effective_date` such that `d.date >=
f.effective_date`** — the exact semantics of `merge_asof(direction="backward")`. The
output is **wide** (one `Mapping` row per trading day) and carries a
`fundamentals_effective_date` audit column (the internal name `effective_date` is not
exposed), mirroring the old rename-at-the-merge-boundary
(`build_tft_dataset_use_case.py:516-518`).

The `effective_date <= date` anti-leakage invariant is enforced **twice**
(defense-in-depth): (1) structurally by the `ASOF JOIN … ON d.date >=
f.effective_date` match condition, and (2) explicitly by the pure domain
`FundamentalsAsofPolicy.validate_not_future(effective_date, sample_date)`, which
raises `AntiLeakageError` (a `DomainError` subclass) — re-checked in the adapter even
though the join already guarantees the condition. `effective_date` itself is computed
by the pure-domain policy (`reported_date or fiscal_date_end + 45 calendar days`, H-3)
and mapped to a trading day via `TradingCalendar.trading_day_from_timestamp` (Stage
2.4, raise-no-clamp out of window) **before** the join — so the engine receives
already-validated effective dates and never re-implements the policy.

The port exchanges only `collections.abc`/`datetime` primitives; `duckdb` never
crosses the port boundary. A behavioral fake (`InMemoryAsofJoinAdapter`, stdlib-only)
satisfies the same `Protocol` and is held to the same assertions as the real adapter
via a parametrized contract test (ADR `0.0.0021`).

## Alternatives considered

### Alternative A — Port the pandas `merge_asof` into a pandas adapter

- **Description:** Keep `pandas.merge_asof(direction="backward")` from the old, moved
  into a `adapters/out/pandas/` adapter behind the same port.
- **Pros:** 1:1 with the old code; no new SQL to write; pandas is already a project
  dependency.
- **Cons:** Introduces a second data engine on the join path while the rest of the
  read layer (`MedallionStore`) is DuckDB; diverges from the pre-declared direction
  (ledger §B 3.3) and the foundational engine ADR (`0.0.0022`); pandas joins on a
  Python process are slower and less SQL-pushdown-friendly than DuckDB over Parquet.
- **Why rejected:** The pre-declared decision and the foundational ADR both name
  DuckDB as the as-of engine; aligning the join with the read engine keeps one engine
  on the data path. The semantics are identical, so the contract test proves parity.

### Alternative B — Enforce the invariant only in the SQL `MATCH_CONDITION`

- **Description:** Trust `d.date >= f.effective_date` alone; drop the explicit
  `validate_not_future` re-check.
- **Pros:** Less code; no duplicated guard.
- **Cons:** A single enforcement point for the central anti-leakage claim; a future
  edit to the SQL (or a fallback path that bypasses the join) could silently leak with
  no failing test in the pure domain. The invariant would not be expressible/testable
  without a DuckDB session.
- **Why rejected:** Anti-leakage is non-negotiable (`0.0.0018`); the pure-domain
  `validate_not_future` is cheap, testable without DuckDB, and gives a second,
  engine-independent guard. Defense-in-depth is the right posture for the Stage's
  reason-to-exist.

### Alternative C — Long output (day, field, value) triples

- **Description:** Return a long/tidy shape instead of one wide row per trading day.
- **Pros:** Schema-agnostic to the set of fundamental fields.
- **Cons:** Diverges from the old wide dataset shape and from what the 3.5
  dataset-builder consumes; loses the natural `fundamentals_effective_date` per-day
  audit column placement; more reshaping downstream.
- **Why rejected:** The downstream consumer (3.5 dense grid) is row-per-day; wide is
  the natural and old-aligned shape.

### Alternative D — Do nothing / leave it in a future monolithic dataset builder

- **Why not acceptable:** The as-of policy + invariant is the scientific spine of the
  fundamentals family; folding it into 3.5 would re-create the old god-use-case and
  make the invariant untestable in isolation. Decomposing it here keeps 3.3 cohesive
  and the invariant a first-class, unit-tested domain rule.

## Consequences

### Positive

- One data engine (DuckDB) on the read+join path, aligned with `MedallionStore` and
  `0.0.0022`.
- The anti-leakage invariant is enforced twice (SQL + pure domain) and unit-tested
  without a DuckDB session — a robust guard for the central claim.
- The port stays `duckdb`-free; the fake + contract test keep the adapter swappable
  and prove parity (`0.0.0021`).
- `fundamentals_effective_date` audit column preserves source-level traceability of
  every fundamental, as the old did.

### Negative

- A small amount of DuckDB SQL must be written and pinned to the project's DuckDB
  version (ASOF JOIN syntax) — mitigated by the contract test (parity fake↔real).
- The invariant is checked in two places (mild duplication) — accepted as the cost of
  defense-in-depth on a non-negotiable rule.

### Neutral / trade-offs accepted

- The dense daily grid (forward-fill, empty-day policy, YoY) is **not** built here;
  it belongs to 3.5 (and the YoY ratios to 3.4 — ADR `3.3.0002`). 3.3 emits one row
  per trading day with the last visible fundamental (or `None`).

## Implementation notes

- Port: `feature_engineering/application/ports/out/asof_join.py` —
  `AsofJoinAdapter.asof_join_backward(*, grid_days, reports) -> Sequence[Mapping]`.
- Adapter: `feature_engineering/adapters/out/duckdb/asof_join_adapter.py` —
  `ASOF JOIN f ON d.date >= f.effective_date` (confirm exact syntax against the pinned
  DuckDB version, concept §13 Q1); re-check `effective_date <= day` and raise
  `AntiLeakageError` on violation.
- Policy (pure domain): `effective_date` + `validate_not_future` +
  `net_margin`/`leverage_ratio`/`cashflow_efficiency` live in
  `domain/services/fundamentals_asof_policy.py`.
- `import-linter` `store-no-storage-leak` already forbids `duckdb` in
  `feature_engineering.{application,domain}`; no new contract needed (concept §7 D5).

## References

- Related ADRs: [0.0.0018](./0_0_0018-anti-leakage-non-negotiable.md) (anti-leakage
  non-negotiable — rule 2 as-of-backward `effective_date <= date`, raise no clamp),
  [0.0.0022](./0_0_0022-data-engine-pandas-duckdb.md) (data engine = pandas + DuckDB;
  as-of joins over Parquet — the foundation this Stage exercises),
  [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md) (contract tests +
  oracle), [2.1.0002](./2_1_0002-medallion-store-port-shape.md) (port-as-Protocol +
  Mapping at the boundary; named domain error over raw `ValueError`),
  [2.4.0001](./2_4_0001-trading-calendar-domain-over-materialized-sessions-vo.md)
  (`TradingCalendar`, raise no clamp), [3.3.0002](./3_3_0002-defer-yoy-fundamentals.md)
  (YoY deferred to 3.4).
- `docs/autonomous-run-decision-ledger.md` H-3 (fallback 45d, anti-leakage validated
  in the old) and §B line 3.3 (DuckDB ASOF backward, `effective_date <= date`).
- `docs/overview.md` §11 (`0.0.0018`, `0.0.0022`), §7 (anti-leakage structural).
- Old: `src/use_cases/build_tft_dataset_use_case.py:513-535` (merge_asof backward +
  rename `effective_date` → `fundamentals_effective_date` + `ValueError` invariant),
  `:116-143` (`_fundamentals_to_df` effective_date + fallback),
  `tests/unit/use_cases/test_build_tft_dataset_use_case.py:570-686` (reference tests).
