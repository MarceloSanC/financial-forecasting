---
title: ADR 3.3.0002 — Defer YoY fundamental ratios (revenue_yoy_growth, net_income_yoy_growth) to Stage 3.4/3.5; Stage 3.3 ships only the three point-in-time ratios
description: Architecture Decision Record
when-use: Reference before adding YoY (year-over-year) fundamental features, or when deciding whether a derived fundamental belongs to the as-of policy (3.3) or the derived-features registry (3.4)
keywords: [adr, fundamentals, yoy, year-over-year, revenue-yoy-growth, net-income-yoy-growth, pct-change-252, point-in-time, ratios, net-margin, leverage-ratio, cashflow-efficiency, deferred, derived-features, dense-grid]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "3.3.0002"
decision: Stage 3.3 ships only the three point-in-time fundamental ratios (net_margin, leverage_ratio, cashflow_efficiency) as pure functions of a single report; the YoY growth features (revenue_yoy_growth, net_income_yoy_growth), which the old computed via pct_change(252) over the dense forward-filled daily grid, are deferred to Stage 3.4/3.5 where that grid exists
context_stage: 3.3-fundamentals-asof-join
---

# ADR 3.3.0002 — Defer YoY fundamental ratios to 3.4/3.5

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The prior repo's `_add_fundamental_derived_features`
(`build_tft_dataset_use_case.py:266-285`) computed **five** derived fundamentals:
three point-in-time ratios — `net_margin = net_income/revenue`, `leverage_ratio =
total_liabilities/total_shareholder_equity`, `cashflow_efficiency =
operating_cash_flow/revenue` — and **two YoY growth** features —
`revenue_yoy_growth` and `net_income_yoy_growth`, each via `pct_change(252,
fill_method=None)`.

Forces at play:

- **The three ratios are pure functions of one report.** Given a single
  `FundamentalReport`'s numerators/denominators, each ratio is a safe division — no
  time window, no neighbour rows. They belong in the pure-domain
  `FundamentalsAsofPolicy` and satisfy the Stage 3.3 DoD ("ratios derivados corretos
  em fixture").
- **The two YoY features are window functions over the dense daily grid.**
  `pct_change(252)` looks back 252 **trading days** (≈1 year) on the *already
  forward-filled daily frame* — i.e. it depends on the dense grid that the
  dataset-builder (3.5) assembles, not on any single report. Computing it inside the
  as-of policy would couple the pure domain to a dense grid it does not own.
- **The roadmap and ledger already allocate the full derived family to 3.4.** Ledger
  §B line 3.4 ("Replicar as ~38 derivadas … ratios fundamentais, fórmulas verbatim;
  tagging known/unknown") and roadmap §Stage 3.4 (`domain/services/derived_features.py`)
  own the complete derived-features set; 3.3's scope is the as-of join + the
  invariant.
- **Cohesion and swappability.** Stage 3.3's reason-to-exist is the as-of-backward
  join and the `effective_date <= date` invariant. Adding grid-dependent window
  features dilutes that and makes the policy harder to test in isolation.

## Decision

**Stage 3.3 ships only the three point-in-time ratios** (`net_margin`,
`leverage_ratio`, `cashflow_efficiency`) as pure, stdlib-only functions of a single
report's primitives, using safe division (numerator `None` or denominator
`None`/`0`/`NaN` → `None`), ported verbatim from the old `_safe_ratio`
(`build_tft_dataset_use_case.py:256-263`).

**The two YoY growth features** (`revenue_yoy_growth`, `net_income_yoy_growth`) are
**deferred to Stage 3.4/3.5**, where the dense forward-filled daily grid required by
`pct_change(252)` exists. They are explicitly out of scope for 3.3.

## Alternatives considered

### Alternative A — Port all five derived features into the 3.3 policy now

- **Description:** Compute YoY inside `FundamentalsAsofPolicy` too.
- **Pros:** All fundamental derivations in one place; closer to the old single
  method.
- **Cons:** YoY needs the dense daily grid (252 trading-day lookback over the
  forward-filled frame) — the policy would have to take the whole joined grid, not a
  single report, coupling the pure domain to a structure 3.5 owns and duplicating
  grid logic; breaks the point-in-time purity of the policy.
- **Why rejected:** YoY is not a function of one report; it is a window over the
  dense grid. Forcing it into the as-of policy violates the layer's responsibility and
  the Stage's cohesion.

### Alternative B — Build a partial dense grid inside 3.3 just to compute YoY

- **Description:** Have 3.3 assemble enough of a daily grid to run the 252-day
  window.
- **Pros:** YoY available one Stage earlier.
- **Cons:** Re-creates the dataset-builder's responsibility inside the as-of Stage;
  two places would build a daily grid with potentially divergent fill/missing
  policies (exactly the divergence risk we avoid by keeping the grid in 3.5).
- **Why rejected:** Duplicates 3.5's job; the empty-day/fill/known-unknown policy must
  be decided once, in the dataset-builder.

### Alternative C — Do nothing / leave YoY undefined

- **Why not acceptable:** YoY growth is part of the planned ~38 derived features
  (ledger §B 3.4); dropping it silently would lose a feature the methodology expects.
  Deferring (not dropping) records exactly where it lands and why.

## Consequences

### Positive

- Stage 3.3 stays cohesive: as-of-backward join + invariant + point-in-time ratios,
  all unit-testable from a single report without a dense grid.
- The dense-grid window features land where the grid is owned (3.4/3.5), with one
  consistent fill/known-unknown policy.
- Satisfies the 3.3 DoD ("ratios derivados corretos em fixture") with the three
  point-in-time ratios.

### Negative

- The full fundamental derived family is split across two Stages (point-in-time here,
  YoY in 3.4/3.5) — accepted; the split follows the data dependency (single report vs
  dense grid), not convenience.

### Neutral / trade-offs accepted

- 3.4 must remember to add the two YoY features (tracked by ledger §B 3.4 and the
  roadmap §3.4 `derived_features.py`); this ADR is the breadcrumb.

## Implementation notes

- 3.3: `net_margin`/`leverage_ratio`/`cashflow_efficiency` as static safe-division
  helpers on `FundamentalsAsofPolicy`; no YoY.
- 3.4: `domain/services/derived_features.py` adds `revenue_yoy_growth` /
  `net_income_yoy_growth` (and the rest of the ~38) over the joined grid, with
  known/unknown tagging.

## References

- Related ADRs: [3.3.0001](./3_3_0001-duckdb-asof-backward-join.md) (the as-of join
  this Stage ships), [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md)
  (oracle-backed tests for the ported ratios).
- `docs/autonomous-run-decision-ledger.md` §B line 3.4 (full derived family incl. YoY
  → 3.4).
- `docs/roadmap.md` §Stage 3.3 (DoD: ratios in fixture), §Stage 3.4
  (`derived_features.py`).
- Old: `src/use_cases/build_tft_dataset_use_case.py:256-263` (`_safe_ratio`),
  `:266-285` (`_add_fundamental_derived_features`: three point-in-time ratios +
  `revenue_yoy_growth`/`net_income_yoy_growth` via `pct_change(252)`).
