---
title: ADR 0.0.0017 — FinBERT sentiment is version-pinned (model + HF revision SHA) for reproducibility
description: Architecture Decision Record
when-use: Reference before choosing or changing the sentiment model, before loading any Hugging Face model in an adapter, or when deciding whether a model artifact needs a pinned revision
keywords: [adr, finbert, sentiment, prosusai, huggingface, revision, version-pin, reproducibility, model-artifact, supply-chain, foundational]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "0.0.0017"
decision: Sentiment is computed by FinBERT (ProsusAI/finbert) loaded with an explicitly pinned Hugging Face revision (commit SHA), exposed as config, so the model artifact is reproducible across runs and machines — the prior repo loaded the model by name only and was not reproducible
context_stage: 3.2-sentiment-finbert
bounded_context: transversal
---

# ADR 0.0.0017 — FinBERT sentiment is version-pinned

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

> Foundational ADR listed in `overview.md` §11 (`adr_id 0.0.0017`, "FinBERT
> version-pinned"). The file did not exist until Stage 3.2 — the first Stage whose
> scope actually loads FinBERT — officialized it here, mirroring how Stage 3.1
> officialized `0.0.0024` (`concept.md` 3.1 §7 D4).

## Context

The project needs a sentiment feature over financial news (one of the four feature
families — `overview.md` §11, `0.0.0016`). FinBERT (`ProsusAI/finbert`) is the de
facto standard for financial-news sentiment and is what the prior repo used.

Forces at play:

- **Reproducibility is a project-wide non-negotiable.** The study is confirmatory
  and pre-registered (`overview.md` §7: "pré-registro imutável hasheado"); a
  feature whose values depend on *which snapshot of a model happened to be on the
  Hub that day* poisons every downstream artifact (dataset hash, training, the
  pre-registered scorecard). The same posture already governs library pins
  (`0.0.0024` pandas-ta-classic, `uv.lock` versioned — `CONVENTIONS.md` §5) and
  deterministic hashing (`1.4.0001`).
- **The prior repo was not reproducible here.** It loaded the model by name only
  (`AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")`,
  `src/adapters/finbert_sentiment_model.py`) with **no `revision`**. Hugging Face
  resolves an unpinned name to the *current* `main` of the repo, which can change
  (re-uploaded weights, tokenizer config, label order) without notice.
- **A model artifact is a dependency like any other.** Hugging Face supports
  `from_pretrained(..., revision="<sha>")`; the commit SHA pins the exact weights +
  config + tokenizer, the same way `uv.lock` pins a wheel.
- **The closed human decision already mandates it.** The decision ledger §B (Stage
  3.2) reads: "`ProsusAI/finbert` + **pinar revisão (SHA)** — old não pinava (ADR
  0017 manda)".

## Decision

Sentiment is computed by **`ProsusAI/finbert`** loaded with an **explicitly pinned
Hugging Face `revision` (a commit SHA)**, exposed as configuration (constructor
parameter / settings), not hardcoded behind a name-only load. The pair
`(model_name, revision)` is **carried through to the use case output** so any
artifact derived from sentiment can record exactly which model produced it.

The scoring formula is fixed independently of the snapshot: `score = P(pos) −
P(neg)` over FinBERT's `[negative, neutral, positive]` labels, yielding a value in
`[-1, +1]` (the concrete formula and daily aggregation are detailed in
`3.2.0001`). The pinned revision plus an oracle fixture (the prior repo's
`scored_news_AAPL.parquet`) and a contract test form the safety net: if a future
revision changes label order or semantics, the test fails rather than silently
shifting feature values.

## Alternatives considered

### Alternative A — Load `ProsusAI/finbert` by name only (the prior repo)

- **Description:** `from_pretrained("ProsusAI/finbert")` with no `revision`.
- **Pros:** Simplest; always gets the "latest" model.
- **Cons:** Non-reproducible — the resolved artifact can change under the project's
  feet; breaks the pre-registration anchor and the dataset hash; "latest" is the
  opposite of what a confirmatory study wants.
- **Why rejected:** Directly contradicts the reproducibility posture; it is the
  exact defect this ADR exists to fix.

### Alternative B — Vendor the weights into the repo / a private artifact store

- **Description:** Download the model once and commit/store the weights as a fixed
  artifact the pipeline reads locally.
- **Pros:** Fully offline and immutable; no Hub dependency at run time.
- **Cons:** ~400 MB of binary in the repo (or extra infra for an artifact store);
  heavy for an academic solo pilot; the Hub already offers immutable revisions for
  free.
- **Why rejected:** A pinned `revision` gives the same immutability guarantee at
  near-zero cost; vendoring is over-engineering for the pilot. Can be revisited if
  the Hub ever becomes unavailable (cheap to switch — the loader is confined to one
  adapter).

### Alternative C — Train/fine-tune a bespoke sentiment model

- **Description:** Build a project-specific financial-sentiment model.
- **Pros:** Full control over labels and domain fit.
- **Cons:** Out of scope for the pilot (no labeled corpus, no budget); FinBERT is
  the accepted baseline and the prior repo's choice; sentiment is one feature among
  many, not the object of study.
- **Why rejected:** Scope creep against a named risk (`overview.md` §10); FinBERT
  pinned is the simple-and-replaceable choice.

### Alternative D — Do nothing / keep sentiment unpinned

- **Why not acceptable:** Leaves the pipeline non-reproducible at exactly the point
  the methodology demands reproducibility; a silently changed model would
  invalidate the pre-registered evidence without any signal.

## Consequences

### Positive

- Sentiment feature values are reproducible across runs and machines; the dataset
  hash and pre-registered scorecard stay anchored.
- `(model_name, revision)` is recorded in the use case output — full provenance for
  any downstream artifact.
- A revision change that alters label order/semantics is caught by the oracle
  fixture + contract test, not absorbed silently.

### Negative

- The pinned revision must be looked up once and recorded (a small manual step;
  Q1 in `concept.md` 3.2 §13). Accepted as the cost of reproducibility.
- Pinning means we do **not** automatically get model improvements; upgrading is a
  deliberate, ADR-superseding act — which is the intended trade-off for a
  confirmatory study.

### Neutral / trade-offs accepted

- The exact SHA is resolved during execution (Stage 3.2) and recorded in the
  adapter config + `technical.md` §7; this ADR fixes the *policy* (must be pinned),
  not the literal SHA.

## Implementation notes

- The loader (`AutoTokenizer`/`AutoModelForSequenceClassification.from_pretrained(
  model_name, revision=...)`) lives **only** in the Stage 3.2 adapter
  `features/feature_engineering/adapters/out/finbert/finbert_sentiment_model.py`,
  with `transformers`/`torch` imported **lazily** (ADR `3.2.0002`).
- Scoring formula + daily aggregation: ADR `3.2.0001`.
- Provenance crosses the boundary via the use case `Result` (`model_name`,
  `revision`).

## References

- Related ADRs: [3.2.0001](./3_2_0001-finbert-pinned-revision-and-scoring.md)
  (concrete scoring formula + aggregation that this foundational pin governs),
  [3.2.0002](./3_2_0002-ml-deps-optional-extra-and-lazy-import.md) (lazy load of the
  pinned model), [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md)
  (oracle fixtures as the net against silent model drift),
  [0.0.0024](./0_0_0024-pandas-ta-classic-over-pandas-ta.md) (same version-pin
  posture for the indicator library; same "officialize a foundational ADR in the
  Stage that first uses it" pattern), [1.4.0001](./1_4_0001-canonicalizacao-de-hash-deterministico.md)
  (deterministic reproducibility posture).
- `docs/overview.md` §11 (FinBERT version-pinned, `adr_id 0.0.0017`), §7
  (pre-registration / reproducibility).
- `docs/autonomous-run-decision-ledger.md` §B (Stage 3.2: pin the HF revision SHA).
- Old: `financial-time-series-forecasting/src/adapters/finbert_sentiment_model.py`
  (name-only load, no `revision`).
- External: ProsusAI/finbert on the Hugging Face Hub; `from_pretrained(...,
  revision=...)` API (Hugging Face `transformers`).
