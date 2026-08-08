---
title: ADR 2.3.0002 — Reuse the existing news and fundamentals parquet as the default ingestion source via ParquetRawNewsFetcher and ParquetFundamentalFetcher adapters, keeping the Alpha Vantage adapters non-default and offline in tests
description: Architecture Decision Record
when-use: Reference before changing the default news/fundamentals ingestion source, before making the Alpha Vantage adapters the default fetcher, before letting an integration test hit the live Alpha Vantage API, or when adding a new NewsFetcher/FundamentalFetcher adapter
keywords: [adr, market-data, news-fetcher, fundamental-fetcher, parquet, alpha-vantage, raw-reuse, ingestion-source, overnight-robustness, port, adapter, offline-test, free-tier]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "2.3.0002"
decision: ParquetRawNewsFetcher and ParquetFundamentalFetcher adapters that read the existing news/fundamentals parquet are the default ingestion sources behind the NewsFetcher/FundamentalFetcher ports; the Alpha Vantage adapters are built but non-default, and no integration test hits the live Alpha Vantage API (live only behind skipif-no-network/no-key)
context_stage: 2.3-news-fundamentals-ingestion
bounded_context: market_data
---

# ADR 2.3.0002 — Reuse the existing news and fundamentals parquet as the default ingestion source

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 2.3 must satisfy the roadmap `definition_of_done`: *"News e fundamentals de
AAPL gravados em bronze com dedup (`article_id`) e throttle de free-tier; fakes
passam contract tests."* Three facts shape the decision:

- **The data already exists and is the source of truth for reuse.** The decision
  ledger §A states the run *"reusa só dados brutos (`raw/`)"* — features are
  re-derived; the inputs are reused. Two files are present and verified:
  `data/raw/news/AAPL/news_AAPL.parquet` (**6921 rows × 8 columns**, matching the
  bronze `NEWS` schema 1:1) and
  `data/processed/fundamentals/AAPL/fundamentals_AAPL.parquet` (**81 rows × 10
  columns**, 17 `NaT` in `reported_date`, matching the bronze `FUNDAMENTAL`
  schema 1:1). These are the datasets the Stage 2.1 bronze schemas were
  calibrated against.
- **Overnight robustness forbids network dependence in the gate.** This Stage runs
  in autonomous overnight mode (ADR
  [0.0.0050](./0_0_0050-autonomous-overnight-mode.md)). Alpha Vantage's free tier
  is ~25 requests/day with aggressive rate-limiting; a test or default path that
  calls the live API can fail for reasons unrelated to the code (rate limit,
  network, upstream drift), halting the run. The prior repo's integration test hit
  the live API — an anti-pattern not to replicate.
- **This mirrors a decision already accepted in Stage 2.2.** ADR
  [2.2.0002](./2_2_0002-reuse-raw-candles-default-vs-live-yfinance.md) introduced
  `ParquetRawCandleFetcher` as the default source for candles for exactly these
  reasons. Stage 2.3 is the same situation for news and fundamentals.

The roadmap's `arquivos_a_criar` for 2.3 lists **only** the Alpha Vantage adapters
— there is no production code path that reads the existing parquet. Without one,
the DoD "reuse existing data" would be satisfiable only inside a test fixture, not
in production: the default source would be the live API, contradicting the ledger
and overnight robustness, and the fake↔real contract-test parity (ADR
[0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md)) would have only the
network adapter to validate against.

A second fact: the fundamentals file lives under `data/processed/`, not
`data/raw/`. It is the reused input nonetheless (it predates this pipeline's
medallion layout); the adapter reads it as the origin of truth and the use case
writes the bronze copy.

## Decision

Introduce two reuse adapters under
`features/market_data/adapters/out/parquet/`, both implementing the same ports the
use cases depend on, and both the **default** ingestion sources:

- **`ParquetRawNewsFetcher`** — reads `data/raw/news/AAPL/news_AAPL.parquet` and
  maps rows to `list[NewsArticle]` (preserving tz-aware UTC `published_at`).
- **`ParquetFundamentalFetcher`** — reads
  `data/processed/fundamentals/AAPL/fundamentals_AAPL.parquet` and maps rows to
  `list[FundamentalReport]`, converting the UTC-datetime `fiscal_date_end`/
  `reported_date` columns back to `date`/`None` (the 17 `NaT` → `None`), and
  normalizing `asset_id` (e.g. `"AAPL.US" → "AAPL"`, `split(".")[0].upper()`,
  ported from the old parquet repository).

`pandas`/`pyarrow` are confined to these adapters (import-linter
`store-no-storage-leak` + `domain-purity`).

**`AlphaVantageNewsFetcher`** and **`AlphaVantageFundamentalFetcher`** are still
built (throttle, defensive parse, rate-limit guard, four-endpoint merge — ported
from the old repo with judgment) and implement the same ports, but are **not** the
default path. Their integration test **never** hits the live API: it uses
`monkeypatch` of `requests`/the session with JSON fixtures; a live smoke test
exists **only** behind `pytest.mark.skipif(no network / no ALPHAVANTAGE_API_KEY)`.

Both parquet reuse adapters and the in-memory fakes pass the **same** parametrized
contract tests for their ports (fake↔real parity, ADR 0.0.0021).

**Provenance note:** `parquet_raw_news_fetcher.py` and
`parquet_fundamental_fetcher.py` are **not** in the roadmap's `arquivos_a_criar`
(which lists only the Alpha Vantage adapters). They are a justified addition driven
by the DoD + ledger + overnight finding, flagged as a `[deviation]` in
`technical.md` §7 — exactly as in Stage 2.2.

## Alternatives considered

### Alternative A — Alpha Vantage is the default ingestion source

- **Description:** `IngestNews`/`IngestFundamentals` default to the Alpha Vantage
  adapters, fetching AAPL news/fundamentals live.
- **Pros:** Matches the literal `arquivos_a_criar` list; no extra adapter.
- **Cons:** Re-downloads by default (contradicts "reuse existing data"); depends on
  the network and a ~25 req/day free tier in the default path (violates overnight
  robustness); ignores the ledger's "reuse only raw" decision; risks upstream drift
  diverging from the bronze schema 2.1 was calibrated against.
- **Why rejected:** Directly contradicts the DoD, the ledger §A, and overnight
  robustness — the three governing constraints of this Stage.

### Alternative B — Reuse the parquet only inside the test, no production adapter

- **Description:** Load the existing parquet in a test fixture to exercise the use
  cases; keep Alpha Vantage as the only real adapter.
- **Pros:** No file outside `arquivos_a_criar`.
- **Cons:** The DoD "reuse existing data" has **no production implementation** —
  only the test would reuse the parquet; production would still re-download. The
  ports would have no offline real adapter, so fake↔real parity (ADR 0.0.0021)
  could only be proven against the network adapter.
- **Why rejected:** Leaves the headline DoD unmet in production and weakens the
  contract-test parity story.

### Alternative C — Read the parquet directly in the use case (no adapter)

- **Description:** Have `IngestNews`/`IngestFundamentals` open the parquet
  themselves.
- **Pros:** Two fewer files.
- **Cons:** Pulls `pandas`/`pyarrow` into the `application` layer — violates
  `store-no-storage-leak` and the inward-only rule; makes the use cases untestable
  without disk; couples orchestration to a storage format.
- **Why rejected:** Breaks hexagonal purity; the ports exist precisely to keep the
  origin swappable and the application storage-agnostic.

## Consequences

### Positive

- The DoD "reuse existing news/fundamentals" has a real production code path, not
  just a test.
- The full gate (and overnight run) is network-independent: nothing in
  `make check`/`make test` calls the live Alpha Vantage API.
- Each port gets an **offline real adapter** to prove fake↔real parity against (ADR
  0.0.0021), stronger than parity against a network adapter.
- The Alpha Vantage adapters remain available as swappable sources for later live
  re-ingestion.

### Negative

- Two adapters beyond the roadmap's `arquivos_a_criar` (the documented
  `[deviation]`), and a second implementation per port to maintain.

### Neutral / trade-offs accepted

- The default path reads the parquet file on each call (O(file)); accepted for a
  single-asset, low-volume pilot — swappable later without touching the ports.
- The fundamentals file lives under `data/processed/`, not `data/raw/`. Accepted as
  the reused input of record (it predates the medallion layout); the use case
  writes the bronze copy. Flagged as a finding in `technical.md` §7.

## Implementation notes

- Both reuse adapters live under
  `features/market_data/adapters/out/parquet/`; `pandas`/`pyarrow` stay confined to
  the adapters (import-linter `store-no-storage-leak` + `domain-purity`).
- `ParquetFundamentalFetcher` converts `datetime64[ns, UTC]` columns to `date`
  (`.date()`), mapping `NaT → None` for the 17 rows; the entity invariant
  "`fiscal_date_end` is a `date`, not `datetime`" must pass for all 81 rows.
- `ParquetRawNewsFetcher` yields `NewsArticle` with `published_at` tz-aware UTC and
  non-empty `article_id` (the file already has stable ids); the use-case row-mapper
  still applies the non-null fallback before writing the bronze row.
- Alpha Vantage integration test: `monkeypatch` the session/`requests.get`
  returning JSON fixtures; `@pytest.mark.integration`. Live smoke test guarded by
  `pytest.mark.skipif` on network/key availability.
- Record the `[deviation]` (adapters outside `arquivos_a_criar`) in `technical.md`
  §7 with a back-reference to this ADR.

## References

- Related ADRs:
  [2.2.0002](./2_2_0002-reuse-raw-candles-default-vs-live-yfinance.md) (same
  decision for candles — the precedent this mirrors),
  [2.3.0001](./2_3_0001-alpha-vantage-fundamental-endpoints-and-earnings.md) (the
  four-endpoint live fundamental fetcher kept as non-default),
  [0.0.0050](./0_0_0050-autonomous-overnight-mode.md) (overnight robustness — no
  network dependence in the gate),
  [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md) (per-unit contract
  tests; fake↔real parity),
  [2.1.0002](./2_1_0002-medallion-store-port-shape.md) (port-as-Protocol; storage
  libs confined to adapters).
- `docs/autonomous-run-decision-ledger.md` §A ("reusa só dados brutos `raw/`").
- `docs/roadmap.md` §Stage 2.3 (`definition_of_done`; `arquivos_a_criar` lists only
  the Alpha Vantage adapters).
- Data verified: `data/raw/news/AAPL/news_AAPL.parquet` (6921×8);
  `data/processed/fundamentals/AAPL/fundamentals_AAPL.parquet` (81×10, 17 `NaT`).
- Old (ported with judgment for the asset_id/date normalization):
  `financial-time-series-forecasting/src/adapters/parquet_fundamental_repository.py`
  (`:54` `asset_id` normalization; `:93-94` `date → pd.Timestamp(tz="UTC")`).
