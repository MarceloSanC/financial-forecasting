---
title: ADR 0.0.0016 — Four feature families (price, technical, sentiment, fundamental) as the canonical taxonomy, required by the H3 family-contribution hypothesis and reusing the bronze layer
description: Architecture Decision Record
when-use: Reference whenever assigning a feature to a family, before adding a fifth family, or when the H3 family-ablation/contribution analysis needs the canonical family set
keywords: [adr, feature-families, taxonomy, price, technical, sentiment, fundamental, h3, family-contribution, ablation, vsn, permutation, bronze, foundational, feature-engineering]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "0.0.0016"
decision: Features are organized into exactly four families — price, technical, sentiment, fundamental — which is the canonical taxonomy required by the H3 relative-contribution hypothesis and reused from the bronze sources; the FeatureSpec.family field is constrained to this four-value set
context_stage: 3.4-feature-registry-and-derived
bounded_context: transversal
---

# ADR 0.0.0016 — Four feature families

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

> Foundational ADR listed in `overview.md` §11 (`adr_id 0.0.0016`, "4 famílias de
> features (preço, técnico, sentimento, fundamento)"). The file did not exist
> until Stage 3.4 — the first Stage whose scope *encodes* the taxonomy as a
> constrained field on `FeatureSpec.family` — which officializes it here,
> mirroring Stage 3.1's officialization of `0.0.0024` and Stage 3.2's of `0.0.0018`.

## Context

The project's hypothesis **H3** is explicitly about the *relative contribution of
feature families* to forecast quality (`overview.md` §65, §71): "A contribuição
das famílias (**preço, técnico, sentimento, fundamento**) é heterogênea entre
horizontes, detectável … em ≥2 de 3 métodos (VSN, permutação, ablação)." The H3
ablation/permutation analysis can only attribute contribution to families if there
is a single, agreed, mutually-exclusive family taxonomy.

Forces at play:

- **H3 needs a stable family partition.** Variable-selection-network weights,
  permutation importance, and ablation are computed *per family*; a drifting or
  overlapping taxonomy makes the contribution claim un-attributable.
- **The four families reuse the bronze sources** (`overview.md` §11 rationale:
  "Necessárias para H3 e diferencial; reusa bronze"): price/technical derive from
  OHLCV (Step 2 market data), sentiment from news (3.2), fundamental from reports
  (3.3). The taxonomy maps onto the ingestion layer already built.
- **The old repo used a 5-value `group`** (`feature_registry.py`):
  `baseline`/`technical`/`sentiment`/`derived`/`fundamental` — which mixed a
  *computation-origin* label (`baseline` raw OHLCV, `derived` engineered) with the
  *family*. For H3 attribution, raw `close` and `log_return_5d` both belong to the
  **price** family regardless of whether they are raw or derived.
- **A constrained field is enforceable.** Putting the taxonomy in
  `FeatureSpec.family` with a validated 4-value set makes "every feature belongs to
  exactly one of the four families" a tested invariant, not a convention.

## Decision

**Features are organized into exactly four families: `price`, `technical`,
`sentiment`, `fundamental`.** This is the canonical taxonomy for the project and
the unit of the H3 relative-contribution analysis. `FeatureSpec.family`
(Stage 3.4) is constrained to this four-value set and validated at construction.

The computation-origin distinction the old encoded as `baseline`/`derived` is
**not** a family; it is carried separately (`enabled_by_default`, `formula_desc`,
the derived-features service). Raw OHLCV and price-derived features (returns,
momentum, drawdown, volatility) all belong to the **price** family.

## Alternatives considered

### Alternative A — Keep the old 5-value `group` (baseline/technical/sentiment/derived/fundamental)

- **Description:** Carry the old taxonomy verbatim as the family.
- **Pros:** Verbatim with the prior repo; no remapping.
- **Cons:** Conflates computation-origin (`baseline`/`derived`) with family,
  fragmenting the *price* family across two labels and making H3's per-family
  attribution ambiguous (where does `log_return_5d` count?).
- **Why rejected:** H3 attributes contribution to families; a clean four-family
  partition is required, and origin is better carried by separate fields.

### Alternative B — Finer-grained taxonomy (e.g. split technical into momentum/trend/volatility)

- **Description:** Use a richer set of families matching `IndicatorSpec.family`
  (`momentum`/`trend`/`volatility`/`ohlc_derived`).
- **Pros:** More granular attribution within technical indicators.
- **Cons:** H3 is stated over the four families, not sub-families; over-splitting
  inflates the number of ablation groups (less statistical power per group) and
  diverges from the hypothesis as pre-registered.
- **Why rejected:** Granularity below the family level belongs to a different
  field (`IndicatorSpec.family` already carries it for indicators); the H3 unit is
  the four families.

### Alternative C — Do nothing / leave family informal

- **Why not acceptable:** Without a constrained, validated family field, H3's
  contribution claim cannot be mechanically attributed and a feature can be
  mis-grouped silently; `overview.md` §11 already reserves the ADR id and the
  hypothesis depends on it.

## Consequences

### Positive

- H3's per-family contribution (VSN / permutation / ablation) has a stable,
  mutually-exclusive partition to attribute to.
- `FeatureSpec.family` constrained to four values is a tested invariant; a feature
  cannot be added outside the taxonomy.
- The families map cleanly onto the bronze sources already ingested.

### Negative

- The old's `baseline`/`derived` origin signal must be carried by other fields
  (`enabled_by_default`, `formula_desc`) — accepted; origin is not a family.

### Neutral / trade-offs accepted

- Sub-family granularity (momentum/trend/volatility within technical) is kept at
  the `IndicatorSpec.family` level (3.1), distinct from the four feature families
  used for H3.

## Implementation notes

- Stage 3.4: `FeatureSpec.family ∈ {price, technical, sentiment, fundamental}`,
  validated in `__post_init__` (→ `ValueError`); raw OHLCV + price-derived →
  `price`; indicators → `technical`; news-derived → `sentiment`; report-derived →
  `fundamental`.
- Step 5/6 H3 analysis groups features by `FeatureSpec.family` for
  ablation/permutation.

## References

- Related ADRs:
  [3.4.0002](./3_4_0002-featurespec-superset-and-tft-typing-promotion.md)
  (`FeatureSpec.family` of 4 values; maps old 5-value `group` onto this taxonomy),
  [3.1.0001](./3_1_0001-feature-engineering-bc-and-indicator-contracts.md)
  (`IndicatorSpec.family` carries finer technical sub-families).
- `docs/overview.md` §11 (`adr_id 0.0.0016`), §65/§71 (H3 family contribution),
  §3 (bronze reuse).
- Old: `src/infrastructure/schemas/feature_registry.py` (5-value `group`).
