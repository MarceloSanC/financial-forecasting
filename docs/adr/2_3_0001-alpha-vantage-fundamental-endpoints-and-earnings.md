---
title: ADR 2.3.0001 — The AlphaVantageFundamentalFetcher fetches four endpoints (INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, EARNINGS); EARNINGS is the sole source of reported_date and is not omitted
description: Architecture Decision Record
when-use: Reference before dropping the EARNINGS call from the fundamental fetcher, before changing which Alpha Vantage endpoints feed the FundamentalReport, or before assuming reported_date can come from another source
keywords: [adr, market-data, fundamentals, alpha-vantage, earnings, reported-date, income-statement, balance-sheet, cash-flow, fundamental-fetcher, as-of, throttle]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "2.3.0001"
decision: AlphaVantageFundamentalFetcher fetches four endpoints (INCOME_STATEMENT + BALANCE_SHEET + CASH_FLOW + EARNINGS), merging by (report_type, fiscal_date_end); EARNINGS is kept because it is the only source of reported_date, which is nullable in the bronze schema and feeds the as-of fallback of Stage 3.3 (ledger H-3)
context_stage: 2.3-news-fundamentals-ingestion
---

# ADR 2.3.0001 — Alpha Vantage fundamental fetcher uses four endpoints, including EARNINGS

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 2.3 builds `AlphaVantageFundamentalFetcher`, the (non-default) live adapter
behind the `FundamentalFetcher` port. The `FundamentalReport` entity carries six
numeric/temporal facts that no single Alpha Vantage endpoint exposes together:

- `revenue`, `net_income` — from `INCOME_STATEMENT`.
- `total_shareholder_equity`, `total_liabilities` — from `BALANCE_SHEET`.
- `operating_cash_flow` — from `CASH_FLOW`.
- `reported_date` — **only** from `EARNINGS` (`reportedDate` per fiscal period).
  No statement endpoint carries the filing/announcement date; it lives solely in
  the EARNINGS feed.

Three forces shape the decision:

- **The bronze `FUNDAMENTAL` schema (2.1) makes `reported_date` nullable on
  purpose.** The real reused dataset has **17 of 81** rows with `NaT` in
  `reported_date` (verified on `data/processed/fundamentals/AAPL/fundamentals_AAPL.parquet`).
  `reported_date` is therefore a real, partially-populated column — not decorative.
- **`reported_date` is the input to the as-of fallback of Stage 3.3 (ledger
  H-3).** The pre-registered rule is "use `reported_date` OR `fiscal_date_end +
  45 days`". Without `reported_date`, every row would fall back to the conservative
  +45d proxy, discarding the genuine announcement date that exists for 64/81 rows.
- **The old repo already fetched four endpoints with this exact merge.** The
  reference adapter (`alpha_vantage_fundamental_fetcher.py:133-201`) calls all
  four and merges by `(report_type, fiscal_date_end)`; EARNINGS fills
  `reported_date` (`:137`, `:158-173`). Replicating-with-judgment means keeping the
  four-endpoint shape that produced the dataset being reused.

The cost of EARNINGS is one extra throttled HTTP call (`_MIN_INTERVAL = 12.5s`),
paid **only** on a live re-ingestion — which is not the default path (ADR
2.3.0002: the default source is the existing parquet, never the live API).

## Decision

`AlphaVantageFundamentalFetcher.fetch_fundamentals(asset_id)` issues **four**
calls — `INCOME_STATEMENT`, `BALANCE_SHEET`, `CASH_FLOW`, `EARNINGS` — and merges
their `annualReports`/`quarterlyReports` (and `annualEarnings`/`quarterlyEarnings`)
into a single dict keyed by `(report_type, fiscal_date_end)`, ported verbatim from
the old `_merge_reports`. Field maps are kept verbatim: `totalRevenue→revenue`,
`netIncome→net_income`, `totalShareholderEquity→total_shareholder_equity`,
`totalLiabilities→total_liabilities`, `operatingCashflow→operating_cash_flow`,
`EARNINGS.reportedDate→reported_date`. `_to_float` / `_to_date` are defensive
(treat `""`/`"None"`/`"null"`/`"NaN"`/unparseable as `None`). A `"Note"`/
`"Information"` key in any response raises `RuntimeError` (rate-limit guard).
Throttle is `12.5s` (free-tier ~5 req/min), confined to the adapter.

EARNINGS is **not** omitted: it is the single source of `reported_date`.

## Alternatives considered

### Alternative A — Three endpoints only (drop EARNINGS)

- **Description:** Fetch only `INCOME_STATEMENT` + `BALANCE_SHEET` + `CASH_FLOW`;
  leave `reported_date` always `None`.
- **Pros:** One fewer throttled call per live re-ingestion (saves ~12.5s).
- **Cons:** `reported_date` would always be `None`; the Stage 3.3 as-of fallback
  (H-3) would lose the real announcement date for the 64/81 rows that have it, and
  every row would use the conservative `fiscal_date_end + 45d` proxy — a silent
  degradation of the anti-leakage join the ledger pre-registered. Diverges from the
  old adapter that produced the reused dataset.
- **Why rejected:** Saving ~12.5s on a non-default path is not worth degrading the
  as-of join that H-3 depends on. The benefit is negligible; the cost is a worse
  feature in a downstream Stage.

### Alternative B — Derive reported_date from fiscal_date_end (always +45d)

- **Description:** Skip EARNINGS and synthesize `reported_date` as
  `fiscal_date_end + 45d` at ingestion time.
- **Pros:** No EARNINGS call; `reported_date` non-null.
- **Cons:** Bakes the H-3 fallback into bronze ingestion, conflating *raw fact*
  (the actual filing date) with *derived proxy* — a medallion-layer violation
  (bronze stores facts; derivation belongs to 3.3). Loses auditability of which
  rows had a real date vs. a proxy (the 17 genuine `NaT` carry meaning).
- **Why rejected:** Pollutes bronze with a 3.3 derivation and destroys the
  real/NaT distinction; the fallback must stay in 3.3 where it is pre-registered.

### Alternative C — Do nothing / status quo

The fetcher cannot populate the bronze `FUNDAMENTAL` row without choosing which
endpoints to call; "do nothing" is not an option. The relevant question is only
*how many* endpoints, answered above.

## Consequences

### Positive

- `reported_date` is populated wherever Alpha Vantage exposes it, preserving the
  real announcement date for the Stage 3.3 as-of join (H-3).
- The live adapter reproduces the exact four-endpoint shape that produced the
  reused parquet — no schema/field drift between old and new ingestion.
- The 17 genuine `NaT` rows are preserved as `None` (the schema is nullable),
  keeping the real/fallback distinction auditable downstream.

### Negative

- One extra throttled HTTP call (`+12.5s`) per live re-ingestion — paid only off
  the default path (ADR 2.3.0002).

### Neutral / trade-offs accepted

- The merge is keyed on `(report_type, fiscal_date_end)`; a fiscal period present
  in one endpoint but absent in others yields a `FundamentalReport` with `None` in
  the missing facts (the schema is nullable for the five floats). Accepted — bronze
  records partial facts faithfully rather than dropping the period.

## Implementation notes

- `requests` is confined to `adapters/out/alpha_vantage/`; no network call on
  import or construction. Tests `monkeypatch` the session/`requests.get` with JSON
  fixtures (the four endpoints, including `"None"`/`"NaN"` strings and a record
  with `reportedDate` absent to exercise the `NaT` path).
- `_merge_reports`, field maps, `_to_float`, `_to_date`, and the rate-limit guard
  are ported verbatim from the old adapter (judgment applied only to typing/imports
  and to satisfying the `FundamentalFetcher` `Protocol` by duck-typing, not by
  inheritance).

## References

- Related ADRs:
  [2.3.0002](./2_3_0002-reuse-existing-news-fundamentals-as-default-source.md)
  (parquet reuse is the default source — the live four-endpoint path is non-default),
  [2.1.0001](./2_1_0001-medallion-partition-and-bronze-schemas.md) (bronze
  `FUNDAMENTAL` schema; `reported_date` nullable),
  [0.0.0050](./0_0_0050-autonomous-overnight-mode.md) (overnight robustness — no
  live API in the gate).
- `docs/autonomous-run-decision-ledger.md` H-3 (as-of fallback `reported_date` OR
  `fiscal_date_end + 45d`).
- Old (ported with judgment):
  `financial-time-series-forecasting/src/adapters/alpha_vantage_fundamental_fetcher.py`
  (`:133-201` four endpoints + merge; `:137`,`:158-173` EARNINGS→`reported_date`;
  `:30` `_MIN_INTERVAL=12.5`; `:89-105` `_to_date`/`_to_float`).
- Real data verified: `data/processed/fundamentals/AAPL/fundamentals_AAPL.parquet`
  (81 rows, 17 `NaT` in `reported_date`).
