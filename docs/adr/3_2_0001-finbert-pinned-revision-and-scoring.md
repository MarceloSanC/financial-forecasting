---
title: ADR 3.2.0001 — FinBERT scoring (P(pos)-P(neg)) as a torch-free pure function + daily mean aggregation over trading days, behind a Protocol port returning DTOs
description: Architecture Decision Record
when-use: Reference before changing the sentiment scoring formula, the daily aggregation, the SentimentModel port shape, or the use case DTO contract
keywords: [adr, finbert, sentiment, score, p-pos-minus-p-neg, scores-from-probs, pure-function, daily-aggregation, mean, pstdev, sentiment-model, protocol, dto, trading-day, oracle]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "3.2.0001"
decision: Per-article sentiment is P(pos)-P(neg) over FinBERT [neg,neu,pos] labels, computed by a stdlib-only pure function scores_from_probs (torch-free, oracle-validated); daily sentiment is mean/pstdev/n over trading days behind the SentimentModel Protocol port; the use case returns frozen DTOs, never entities; ProsusAI/finbert is loaded with a pinned HF revision (0.0.0017)
context_stage: 3.2-sentiment-finbert
---

# ADR 3.2.0001 — FinBERT scoring + daily aggregation + port/DTO shape

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 3.2 adds the sentiment feature to the `feature_engineering` BC (created in
3.1). Several coupled shaping decisions share one context and are recorded together
to avoid near-identical ADRs:

- **The closed human decision (ledger §B, Stage 3.2)** fixes the model and formula:
  "`ProsusAI/finbert` + pinar revisão (SHA); score `P(pos)-P(neg)`; média diária
  por dia de pregão". The foundational pin rationale is `0.0.0017`.
- **The prior repo couples the formula to tensors.** `_score_texts`
  (`src/adapters/finbert_sentiment_model.py:113-118`) computes `(probs[:, 2] -
  probs[:, 0])` inside a `torch.softmax` block, so the formula cannot be exercised
  without torch. The overnight finding requires the pure scoring logic to be
  **separated** so coverage ≥90% is reachable without installing torch and so the
  formula can be validated against the oracle.
- **An oracle exists.** The prior repo's
  `data/processed/scored_news/AAPL/scored_news_AAPL.parquet` (~6892 rows) and
  `sentiment_daily/AAPL/daily_sentiment_AAPL.parquet` (~5844 rows) are regression
  fixtures (ledger; `overview.md` §3 — `processed/` is oracle, not input). They must
  **not** be re-scored via FinBERT overnight.
- **The daily aggregation is settled in the old.** `SentimentAggregator`
  (`src/domain/services/sentiment_aggregator.py:55-85`) groups by trading day and
  emits `mean`, `pstdev if n>1 else 0.0`, `n_articles`.
- **The port-as-Protocol + DTO-on-boundary posture is consolidated** across
  `MedallionStore` (2.1.0002), `ExperimentTracker` (1.5.0002), `IndicatorCalculator`
  (3.1.0001), `ExchangeCalendarProvider` (2.4.0001). The old `SentimentModel` was an
  **ABC** and the old use cases returned **entities** (`ScoredNewsArticle`) directly.

## Decision

Four coupled decisions, one Stage:

1. **Scoring formula as a torch-free pure function.** Per-article sentiment is
   `score = P(pos) − P(neg)` over FinBERT's `[negative, neutral, positive]` labels.
   It is implemented as a **stdlib-only** pure function
   `scores_from_probs(probs: Sequence[Sequence[float]]) -> list[float]`
   (`[p[2] - p[0] for p in probs]`, each row validated to have exactly 3
   components), living in the adapter module but **callable without torch**. The
   tensor path (`_score_texts`) only produces `probs` and delegates the formula to
   `scores_from_probs`. The function is validated against the oracle
   `scored_news_AAPL.parquet` (sample probabilities → scores match). Result ∈
   `[-1, +1]` by construction.

2. **Daily aggregation = mean over trading days.** Grouping scored articles by
   trading day (via the causality guard, `0.0.0018`): `sentiment_score = mean`,
   `sentiment_std = pstdev if n > 1 else 0.0`, `n_articles = len (>= 1)`; rows
   ordered by day. Replicates `SentimentAggregator` (old). Empty trading days are
   **not** synthesized here (filled by the dataset builder, 3.5 — `concept.md` 3.2
   §7 D7).

3. **`SentimentModel` is a Protocol port; the use case returns DTOs.**
   `SentimentModel` is a structural `typing.Protocol` (`score_articles(articles:
   Sequence[NewsArticle]) -> Sequence[float]`, order-preserving, exposing
   `model_name`/`revision`), not an ABC. `ScoreAndAggregateSentiment` receives a
   frozen `Request` and returns a frozen `Result` of `ScoredNewsDTO` +
   `DailySentimentDTO` — the `NewsArticle` entity **never** crosses out of the
   `application`.

4. **`ProsusAI/finbert` loaded with a pinned HF revision** (SHA), exposed as
   config, per the foundational `0.0.0017`; `(model_name, revision)` is carried in
   the use case `Result` for provenance.

## Alternatives considered

### Alternative A — Keep the formula coupled to tensors (the prior repo)

- **Description:** Compute `probs[:, 2] - probs[:, 0]` inside the torch forward, as
  the old `_score_texts` does.
- **Pros:** One fewer function; matches the old verbatim.
- **Cons:** The formula cannot be tested or oracle-validated without torch; coverage
  ≥90% of the live BC code would require installing torch in CI (which the overnight
  finding forbids).
- **Why rejected:** The pure `scores_from_probs` is a trivial extraction that
  unlocks torch-free testing + oracle validation at zero behavioral cost.

### Alternative B — ABC port returning `ScoredNewsArticle` entities (the prior repo)

- **Description:** `SentimentModel(ABC)`; use cases return entities directly.
- **Pros:** Direct port of the old contract.
- **Cons:** ABCs couple adapters/fakes to `application` via inheritance; returning
  an entity leaks domain identity across the use case boundary — both against the
  consolidated posture (2.1/2.2/3.1).
- **Why rejected:** `Protocol` + DTO keeps the adapter/fake swappable and the entity
  inside `application`, consistent with four prior ports.

### Alternative C — Aggregate by calendar day (not trading day)

- **Description:** Group articles by `published_at.date()` ignoring the close.
- **Pros:** No calendar dependency.
- **Cons:** Leaks after-close news into a closed day (look-ahead) — violates
  `0.0.0018`.
- **Why rejected:** The trading-day cutoff is the anti-leakage guard; calendar-day
  grouping is the leak.

### Alternative D — Use the prior repo's scored parquet directly as the feature

- **Description:** Read `scored_news_AAPL.parquet` as the sentiment feature instead
  of re-deriving.
- **Pros:** Zero compute.
- **Cons:** Features are re-derived from `raw/` by project rule (`overview.md` §3);
  the parquet is an **oracle**, not an input, and is unpinned/irreproducible.
- **Why rejected:** Confuses oracle with input; the contract here is the use case,
  which the oracle *validates* (not feeds).

### Alternative E — Do nothing / defer sentiment

- **Why not acceptable:** Sentiment is one of the four mandated feature families
  (`0.0.0016`); Stage 3.2 *is* its delivery.

## Consequences

### Positive

- `scores_from_probs` + `_build_text` + the aggregation are pure and torch-free →
  coverage ≥90% of live BC code without installing torch (overnight finding
  satisfied); the formula is oracle-validated.
- `Protocol` + DTO keeps the BC testable with a fake and the adapter swappable; the
  entity stays inside `application`.
- Trading-day aggregation enforces the publication cutoff (`0.0.0018`); provenance
  `(model_name, revision)` travels with the result.

### Negative

- One extra function (`scores_from_probs`) and one extra DTO mapping vs returning
  the entity (accepted: small, and it is what enables torch-free testing).
- The pinned revision SHA must be resolved/recorded during execution (Q1,
  `concept.md` 3.2 §13).

### Neutral / trade-offs accepted

- Empty trading days are not filled here (deferred to 3.5, D7); `Result.daily`
  contains only days with `n >= 1`. Recorded as a `[decision]` in `technical.md` §7.

## Implementation notes

- `scores_from_probs` lives in
  `features/feature_engineering/adapters/out/finbert/finbert_sentiment_model.py`
  (stdlib-only; no torch import at module top — ADR `3.2.0002`); the tensor forward
  (`_score_texts`) calls it after `torch.softmax`.
- `_build_text = headline + summary` (space join; fallback `' '` if both empty),
  `batch_size=16`, `max_length=512` — confined to the adapter (old L91-124).
- Aggregation uses `statistics.mean`/`statistics.pstdev` (stdlib) in the use case;
  the trading-day mapping is `TradingCalendar.trading_day_from_timestamp(ts,
  close_hour)` over sessions materialized by `ExchangeCalendarProvider.sessions`.
- Oracle validation: `test_sentiment_aggregation.py` reads a sample of
  `scored_news_AAPL.parquet` probabilities → asserts `scores_from_probs` matches
  within tolerance (read-only; no re-scoring).

## References

- Related ADRs: [0.0.0017](./0_0_0017-finbert-version-pinned.md) (the pinned-revision
  policy this Stage implements), [0.0.0018](./0_0_0018-anti-leakage-non-negotiable.md)
  (the trading-day causality guard wrapping the aggregation),
  [3.2.0002](./3_2_0002-ml-deps-optional-extra-and-lazy-import.md) (lazy torch +
  optional extra + `sentiment-no-ml-leak`),
  [2.1.0002](./2_1_0002-medallion-store-port-shape.md) /
  [1.5.0002](./1_5_0002-experiment-tracker-port-shape.md) /
  [3.1.0001](./3_1_0001-feature-engineering-bc-and-indicator-contracts.md)
  (port-as-Protocol + DTO/Mapping on the boundary),
  [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md) (oracle fixtures).
- `docs/stages/3.2-sentiment-finbert/concept.md` §4/§5 (contracts/invariants), §7
  D1/D3/D4/D7.
- `docs/autonomous-run-decision-ledger.md` §B (Stage 3.2: model, formula,
  aggregation).
- `docs/roadmap.md` §Stage 3.2 (DoD), §Stage 3.5 (dataset builder owns the daily
  grid / empty-day fill).
- Old: `src/adapters/finbert_sentiment_model.py:91-124` (`_build_text`/`_score_texts`
  formula L113-118), `src/domain/services/sentiment_aggregator.py:55-85`
  (mean/pstdev/n), `src/interfaces/sentiment_model.py` (ABC → Protocol),
  `src/use_cases/sentiment_feature_engineering_use_case.py` (entity → DTO),
  `tests/unit/adapters/sentiment/test_finbert_adapter.py:39-45` (DummyFinBERT
  pattern → pure `scores_from_probs`).
- Oracle: `data/processed/scored_news/AAPL/scored_news_AAPL.parquet`,
  `data/processed/sentiment_daily/AAPL/daily_sentiment_AAPL.parquet`.
