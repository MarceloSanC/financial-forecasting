---
title: ADR 2.2.0002 — Reuse the existing raw candle parquet as the default ingestion source via a ParquetRawCandleFetcher adapter, keeping yfinance non-default and offline in tests
description: Architecture Decision Record
when-use: Reference before changing the default candle ingestion source, before making yfinance the default fetcher, before letting an integration test hit the live yfinance API, or when adding a new CandleFetcher adapter
keywords: [adr, market-data, candle-fetcher, parquet, yfinance, raw-reuse, ingestion-source, overnight-robustness, port, adapter, offline-test]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "2.2.0002"
decision: A ParquetRawCandleFetcher adapter that reads the existing raw candle parquet is the default ingestion source behind the CandleFetcher port; YfinanceCandleFetcher is built but non-default, and no integration test hits the live yfinance API (live only behind skipif-no-network)
context_stage: 2.2-market-data-ingestion
---

# ADR 2.2.0002 — Reuse the existing raw candle parquet as the default ingestion source

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 2.2 must satisfy the roadmap `definition_of_done`: *"`IngestCandles`
grava candles de AAPL em bronze ... reusa raw existente sem re-baixar por
padrão"* ("reuses the existing raw without re-downloading by default"). Two
facts shape the decision:

- **The raw already exists and is the source of truth for reuse.** The decision
  ledger §A states the run *"reusa só dados brutos (`raw/`)"* — features are
  re-derived; the raw is the input. The file
  `data/raw/market/candles/AAPL/candles_AAPL_1d.parquet` (4024 rows) is present
  and was the dataset the Stage 2.1 bronze `CANDLE` schema was calibrated against
  (`open/high/low/close` `float32`, `volume` `int64`, `timestamp`
  `datetime64[ns, UTC]` at `00:00`; **no `asset` column**).
- **Overnight robustness forbids network dependence in the gate.** This Stage
  runs in the autonomous overnight mode (ADR
  [0.0.0050](./0_0_0050-autonomous-overnight-mode.md)). A test or default path
  that calls the live yfinance API can fail for reasons unrelated to the code
  (network, rate limits, upstream schema drift), which would halt the run. The
  prior repo's integration test
  (`financial-time-series-forecasting/tests/integration/test_yfinance_fetcher.py`)
  hit the live API with no skip — an anti-pattern not to replicate.

The `CandleFetcher` port abstracts the **origin** of candles
(`fetch_candles(symbol, start, end) -> list[Candle]`). The roadmap's
`arquivos_a_criar` for 2.2 lists **only** the yfinance adapter — there is no
production code path that reads the raw. Without one, the DoD "reuses raw by
default" would be satisfiable only inside a test fixture, not in production: the
default source would be the live API, contradicting the ledger and overnight
robustness.

## Decision

Introduce a **`ParquetRawCandleFetcher`** adapter
(`features/market_data/adapters/out/parquet/parquet_raw_candle_fetcher.py`) that
reads the existing raw candle parquet and maps it to `list[Candle]` (preserving
`float32`/`int64` and tz-aware UTC), implementing the **same** `CandleFetcher`
port. This adapter is the **default** ingestion source.

**`YfinanceCandleFetcher`** is still built (retry+backoff, `MultiIndex`/tz
normalization, column validation, ported from the old repo with judgment) and
implements the same port, but it is **not** the default path. Its integration
test **never** hits the live API: it uses `monkeypatch` of `yf.download` / a
fixture under `@pytest.mark.integration`; a live smoke test exists **only** behind
`pytest.mark.skipif(no-network)`.

Both `ParquetRawCandleFetcher` and the in-memory `FakeCandleFetcher` pass the
**same** parametrized contract test for the `CandleFetcher` port (fake↔real
parity, ADR [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md)).

**Provenance note:** `parquet_raw_candle_fetcher.py` is **not** in the roadmap's
`arquivos_a_criar` (which lists only the yfinance adapter). It is a justified
addition driven by the DoD + ledger + overnight finding, flagged as a
`[deviation]` in `technical.md` §7.

## Alternatives considered

### Alternative A — yfinance is the default ingestion source

- **Description:** `IngestCandles` defaults to `YfinanceCandleFetcher`, fetching
  AAPL daily candles live.
- **Pros:** Matches the literal `arquivos_a_criar` list; no extra adapter.
- **Cons:** Re-downloads by default (violates the DoD "sem re-baixar por
  padrão"); depends on the network in the default path (violates overnight
  robustness); ignores the ledger's "reuse only `raw/`" decision; risks upstream
  schema/tz drift diverging from the bronze schema 2.1 was calibrated against.
- **Why rejected:** Directly contradicts the DoD, the ledger §A, and overnight
  robustness — the three governing constraints of this Stage.

### Alternative B — Reuse the raw only inside the test, no production adapter

- **Description:** Load the raw parquet in a test fixture to exercise
  `IngestCandles`; keep yfinance as the only real adapter.
- **Pros:** No file outside `arquivos_a_criar`.
- **Cons:** The DoD "reuses raw by default" has **no production implementation** —
  only the test would reuse the raw; production would still re-download. The
  `CandleFetcher` port would have no offline real adapter, so fake↔real parity
  (ADR 0.0.0021) could only be proven against the network adapter.
- **Why rejected:** Leaves the headline DoD unmet in production and weakens the
  contract-test parity story.

### Alternative C — Read the raw directly in the use case (no adapter)

- **Description:** Have `IngestCandles` open the parquet itself.
- **Pros:** One fewer file.
- **Cons:** Pulls `pandas`/`pyarrow` into the `application` layer — violates the
  `store-no-storage-leak` posture and the inward-only rule; makes the use case
  untestable without disk; couples orchestration to a storage format.
- **Why rejected:** Breaks hexagonal purity; the port exists precisely to keep
  the origin swappable and the application storage-agnostic.

## Consequences

### Positive

- The DoD "reuses the existing raw without re-downloading by default" has a real
  production code path, not just a test.
- The full gate (and overnight run) is network-independent: nothing in
  `make check`/`make test` calls the live yfinance API.
- The `CandleFetcher` port gets an **offline real adapter** to prove fake↔real
  parity against (ADR 0.0.0021), stronger than parity against a network adapter.
- yfinance remains available as a swappable source for later re-ingestion when a
  network fetch is genuinely wanted.

### Negative

- One adapter beyond the roadmap's `arquivos_a_criar` (the documented
  `[deviation]`), and a second `CandleFetcher` implementation to maintain.

### Neutral / trade-offs accepted

- The default path reads the raw file on each call (O(file)); accepted for a
  single-asset, low-volume pilot — swappable later without touching the port.
- The raw lacks an `asset` column; injecting `asset` is the use case's
  responsibility (concept §7 D4), independent of which fetcher is the source.

## Implementation notes

- `ParquetRawCandleFetcher` lives under
  `features/market_data/adapters/out/parquet/`; `pandas`/`pyarrow` stay confined
  to the adapter (import-linter `store-no-storage-leak` + `domain-purity`).
- Map each raw row to `Candle` preserving `float32`/`int64` and tz UTC; the
  strong OHLC invariants (concept §5 I1–I4) must pass for all 4024 real rows
  (integration test asserts this).
- yfinance integration test: `monkeypatch.setattr(yf, "download", ...)` returning
  a small fixture DataFrame (including a `MultiIndex`/tz-naive variant to exercise
  normalization); `@pytest.mark.integration`. Live smoke test guarded by
  `pytest.mark.skipif` on network availability.
- Record the `[deviation]` (adapter outside `arquivos_a_criar`) in
  `technical.md` §7 with a back-reference to this ADR.

## References

- Related ADRs:
  [0.0.0050](./0_0_0050-autonomous-overnight-mode.md) (overnight robustness — no
  network dependence in the gate),
  [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md) (per-unit contract
  tests; fake↔real parity),
  [2.1.0002](./2_1_0002-medallion-store-port-shape.md) (port-as-Protocol; storage
  libs confined to adapters).
- `docs/autonomous-run-decision-ledger.md` §A ("reusa só dados brutos `raw/`").
- `docs/roadmap.md` §Stage 2.2 (`definition_of_done`: "reusa raw existente sem
  re-baixar por padrão"; `arquivos_a_criar` lists only the yfinance adapter).
- `docs/stages/2.2-market-data-ingestion/concept.md` §7 D3, §5 I12/I13.
- Raw verified: `data/raw/market/candles/AAPL/candles_AAPL_1d.parquet`
  (4024 rows, 6 columns, no `asset`).
- Old (anti-pattern, not to replicate):
  `financial-time-series-forecasting/tests/integration/test_yfinance_fetcher.py`
  (hits live API with no skip); `src/adapters/yfinance_candle_fetcher.py`
  (retry/backoff/tz logic — ported with judgment).
