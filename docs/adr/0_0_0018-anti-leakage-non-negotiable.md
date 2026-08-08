---
title: ADR 0.0.0018 — Anti-leakage is non-negotiable — causal feature timing, as-of-backward joins, known/unknown typing, embargo; target = log-return
description: Architecture Decision Record
when-use: Reference whenever building a feature whose timing could leak future information — sentiment cutoff, as-of fundamentals, indicator windows, train/val/test splits — or before relaxing any temporal guard
keywords: [adr, anti-leakage, causality, leakage, as-of-backward, known-unknown, embargo, purge, cutoff, trading-day, target, log-return, temporal-validity, foundational]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "0.0.0018"
decision: Temporal validity is a non-negotiable pre-condition of every feature and claim — feature timing is causal (no future information at time t), joins are as-of backward, features are typed known vs unknown, splits use purge+embargo, and the target is the log-return; the first concrete enforcement is the publication-cutoff guard on sentiment aggregation in Stage 3.2
context_stage: 3.2-sentiment-finbert
bounded_context: transversal
---

# ADR 0.0.0018 — Anti-leakage is non-negotiable

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

> Foundational ADR listed in `overview.md` §11 (`adr_id 0.0.0018`, "Anti-leakage
> não-negociável"). The file did not exist until Stage 3.2 — the first Stage whose
> scope *exercises* a causal cutoff (news publication time → trading day) — which
> officializes it here, mirroring Stage 3.1's officialization of `0.0.0024`.

## Context

The project's central claim is about **calibration of next-day(s) return forecasts**
(`overview.md` §1/§4). Any leakage of future information into a feature inflates
apparent skill and invalidates the claim — and leakage in time series is subtle and
easy to introduce (a join that reaches forward, a scaler fit on the whole series, a
news item dated after the close folded into the same day).

Forces at play:

- **Temporal validity is a pre-condition, not a nice-to-have.** Without it, none of
  the downstream statistics (pinball, DM/MCS, coverage) mean anything. The overview
  states it as a hard rule (§7: "alinhamento OOS estrito por `target_timestamp`",
  "anti-p-hacking é estrutural").
- **The pilot reconstructs features from raw, deliberately.** Features are
  re-derived from `raw/` (`overview.md` §3), so each derivation is a fresh
  opportunity to leak — and a fresh place to enforce the guard.
- **The prior repo already encoded the discipline** but ad hoc: a publication-cutoff
  in sentiment (`sentiment_feature_engineering_use_case.py:_validate_daily_causality`),
  an as-of-backward merge for fundamentals, per-feature `anti_leakage_tag` in the
  feature registry. This ADR lifts that scattered discipline into one foundational
  rule the import-linter-style gates and per-feature tests enforce.
- **It spans multiple Stages.** Sentiment cutoff (3.2), as-of-backward fundamentals
  with `effective_date <= date` (3.3, ledger H-3), indicator causal windows (3.1),
  known/unknown typing (3.4), purge+embargo splits (5.1). One foundational ADR
  anchors all of them.

## Decision

**Temporal validity (anti-leakage) is a non-negotiable pre-condition of every
feature and every claim.** Concretely, five rules hold across the feature and
modeling layers:

1. **Causal feature timing.** A feature value at time `t` uses **only** information
   available at `t`. For news sentiment specifically: an article published **after
   the market close** of its calendar day rolls forward to the **next trading
   session** (publication-cutoff guard) and is **never** folded into a day that
   already closed. Implemented via
   `TradingCalendar.trading_day_from_timestamp(ts, close_hour)` (Stage 2.4).
2. **As-of-backward joins.** Point-in-time joins look **backward** only;
   `effective_date <= date` is an invariant that *fails* (raises) if a future
   effective date would be used (fundamentals, Stage 3.3, ledger H-3).
3. **Known vs unknown typing.** Features are typed by whether their future values
   are known at decision time (e.g. calendar features known; realized returns
   unknown) so the model never consumes an unknown as if known (Stage 3.4).
4. **Purge + embargo splits.** Walk-forward validation purges and embargoes around
   split boundaries to prevent train/test contamination (Stage 5.1).
5. **Target = log-return.** The prediction target is the log-return at the
   forecast horizon, aligned strictly by `target_timestamp`.

Each rule is enforced by a **test that fails on violation**, not by convention:
the sentiment cutoff test (3.2), the `effective_date <= date` invariant test (3.3),
the indicator leakage test (3.1), and the split tests (5.1). Out-of-window lookups
raise rather than clamp (Stage 2.4 `TradingCalendar`).

## Alternatives considered

### Alternative A — Enforce anti-leakage per Stage, with no foundational ADR

- **Description:** Each Stage handles its own leakage guard with no shared anchor.
- **Pros:** Less upfront documentation.
- **Cons:** The discipline drifts — exactly what happened in the prior repo, where
  the guard lived in three unrelated places with no single statement of intent; a
  new feature can quietly skip the guard.
- **Why rejected:** Anti-leakage is the *spine* of the methodology; it deserves one
  citable rule that every feature Stage references (and `overview.md` §11 already
  reserves the ADR id).

### Alternative B — Clamp out-of-window timestamps instead of raising

- **Description:** When an article's cutoff day falls outside the materialized
  session window, snap it to the nearest in-window session.
- **Pros:** Never errors; "just works".
- **Cons:** Silently fabricates a placement; hides a too-narrow window or a bad
  timestamp — the kind of silent wrong-answer this project explicitly rejects.
- **Why rejected:** Raising surfaces the defect; the caller must materialize a wide
  enough window (Stage 2.4 `TradingCalendar` already raises, no clamp).

### Alternative C — Allow same-day folding regardless of publication time

- **Description:** Aggregate every article into its calendar day, ignoring the
  close.
- **Pros:** Simpler aggregation.
- **Cons:** Leaks after-close news into a day whose return is already determined —
  textbook look-ahead bias.
- **Why rejected:** It is the precise leakage the cutoff guard exists to prevent.

### Alternative D — Do nothing / trust convention

- **Why not acceptable:** Leakage is silent and fatal to the claim; convention
  without a failing test is how the prior repo's discipline rotted.

## Consequences

### Positive

- One citable, foundational rule anchors every feature/modeling Stage; new features
  inherit the requirement to ship a failing-on-leakage test.
- The sentiment cutoff, as-of-backward, known/unknown, and embargo rules are
  coherent rather than ad hoc; downstream statistics rest on a sound temporal base.
- Out-of-window raises (no clamp) surface narrow windows / bad data early.

### Negative

- Every feature Stage must add a leakage test (extra work — accepted as the cost of
  a defensible claim).
- Callers must materialize wide-enough session windows (e.g. the sentiment use case
  must cover the cutoff of the last article). Accepted; it is explicit, not magic.

### Neutral / trade-offs accepted

- This ADR states the *policy*; the concrete mechanism per Stage (cutoff in 3.2,
  as-of in 3.3, known/unknown in 3.4, embargo in 5.1) is detailed in those Stages'
  artifacts and tests.

## Implementation notes

- Stage 3.2 enforcement (the first concrete one): the sentiment use case maps
  `published_at` → trading day via
  `TradingCalendar.trading_day_from_timestamp(ts, close_hour)` (after-close →
  `next_session`); naive `published_at` → `ValueError`; day outside the
  materialized `[start, end]` → `ValueError` (no clamp). Tested in
  `test_sentiment_aggregation.py` (causality cases A6, `concept.md` 3.2).
- Stage 3.3: `FundamentalsAsofPolicy` with `effective_date = reported_date or
  (fiscal_date_end + 45d fallback)` (ledger H-3) and the `effective_date <= date`
  invariant that raises.
- Stage 3.1: indicator leakage test (append future bars; past values unchanged).

## References

- Related ADRs: [2.4.0001](./2_4_0001-trading-calendar-domain-over-materialized-sessions-vo.md)
  (the `TradingCalendar` that implements the publication cutoff and raises on
  out-of-window — no clamp), [3.1.0001](./3_1_0001-feature-engineering-bc-and-indicator-contracts.md)
  (indicator causal windows + leakage test), [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md)
  (per-unit tests + oracle as the enforcement mechanism),
  [3.2.0001](./3_2_0001-finbert-pinned-revision-and-scoring.md) (the sentiment
  scoring/aggregation that this guard wraps).
- `docs/overview.md` §11 (anti-leakage non-negotiable, `adr_id 0.0.0018`), §7
  (anti-p-hacking structural; strict OOS alignment by `target_timestamp`).
- `docs/autonomous-run-decision-ledger.md` H-3 (as-of fallback, validated
  anti-leakage in the old: 17/81 used the fallback, no leakage).
- Old: `src/use_cases/sentiment_feature_engineering_use_case.py:116-186`
  (`_validate_daily_causality`), the fundamentals as-of merge, and
  `feature_registry.py` per-feature `anti_leakage_tag`.
- External: López de Prado 2018 (purged/embargoed CV) — `overview.md` §10.
