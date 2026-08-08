---
title: ADR 3.4.0002 — FeatureSpec is the rich superset (formula_desc, null_policy, enabled_by_default, family of 4, tft_typing) coexisting with the minimal IndicatorSpec (3.1); the known/unknown TFT typing is promoted from the old training use case into the spec as a validated field
description: Architecture Decision Record
when-use: Reference before changing FeatureSpec fields, before deciding how much of IndicatorSpec FeatureSpec absorbs, before relocating the known/unknown typing decision, or before unifying the two registries
keywords: [adr, feature-spec, superset, indicator-spec, absorption, tft-typing, known-unknown, family, anti-leakage-tag, feature-registry, single-source-of-truth, value-object, domain, coexistence]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "3.4.0002"
decision: FeatureSpec is the rich superset value-object (adds formula_desc, null_policy, enabled_by_default, a 4-value family, and a new validated tft_typing known/unknown field) that coexists with the minimal IndicatorSpec from 3.1 rather than physically replacing it now; the known/unknown TFT typing — hardcoded in the old training use case — is promoted into the spec as a required, validated field so the registry is the single source of truth
context_stage: 3.4-feature-registry-and-derived
bounded_context: feature_engineering
---

# ADR 3.4.0002 — FeatureSpec superset + tft_typing promotion

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 3.1 deliberately shipped a **minimal** `IndicatorSpec`
(`name`, `family`, `source_cols`, `warmup`, `anti_leakage_tag`, `dtype`) and
deferred the rich registry to 3.4 (ADR 3.1.0001 §Decision 2, Alternative A). ADR
3.1.0001 §Consequences explicitly names the future absorption of `IndicatorSpec`
into the 3.4 `FeatureSpec` as accepted extra work. Stage 3.4 now builds that rich
spec.

Forces at play:

- **The old `FeatureSpec`** (`feature_registry.py:7-17`) carried the richer
  fields the 3.1 spec dropped: `formula_desc`, `null_policy`,
  `enabled_by_default`, and a `group` taxonomy of **5 values**
  (`baseline`/`technical`/`sentiment`/`derived`/`fundamental`).
- **The known/unknown TFT typing was hardcoded in the old training use case**
  (`train_tft_model_use_case.py:1216`: `known_real_cols = [time_idx,
  day_of_week, month]`, everything else unknown), scattering a per-feature
  decision away from the feature definition. ADR 0.0.0018 rule 3 makes
  known/unknown a first-class anti-leakage rule that Stage 3.4 owns.
- **The 4-family taxonomy is foundational** (`overview.md` §11 `0.0.0016`:
  price, technical, sentiment, fundamental). The old's 5-value `group` mixed a
  computation-origin label (`baseline`/`derived`) with the family; the new
  taxonomy collapses `baseline` + price-derived into `price`.
- **3.1's `IndicatorSpec` is green and hashed.** `indicator_registry_hash()` and
  the 10 indicator specs already pass the gates; rewriting `IndicatorSpec` now
  would churn passing tests and the indicator hash, widening the blast radius into
  a Stage (3.1) that is closed — for no benefit this Stage needs.

## Decision

Two coupled decisions:

1. **`FeatureSpec` is the rich superset, coexisting with `IndicatorSpec`.**
   `FeatureSpec` adds `formula_desc`, `null_policy` (default `"allow"`),
   `enabled_by_default` (default `True`), a `family` constrained to the **4**
   foundational values (`price`/`technical`/`sentiment`/`fundamental`), and the new
   `tft_typing` field. It is the source of truth for *features*; `feature_set_hash`
   covers the feature registry. **`IndicatorSpec` (3.1) is not rewritten or
   removed** in this Stage, and `indicator_registry_hash` keeps covering the
   technical indicators. The *physical* unification of the two registries is
   deferred to the integration Stage (3.5) as accepted work — a mechanical refactor
   once both are exercised by the dataset-builder.

2. **Promote `tft_typing ∈ {known, unknown}` into `FeatureSpec` as a required,
   validated field.** Calendar features (`day_of_week`, `month`, `time_idx`) are
   `known`; price/indicator/sentiment/fundamental/derived features are `unknown`.
   The rule lives once, in the spec, validated by `__post_init__` — not duplicated
   in a downstream training use case.

## Alternatives considered

### Alternative A — Physically unify: rewrite IndicatorSpec into FeatureSpec now

- **Description:** Replace `IndicatorSpec`/`INDICATOR_SPECS`/`indicator_registry_hash`
  with the rich `FeatureSpec`/`FeatureRegistry` in this Stage; one registry only.
- **Pros:** No later absorption step; a single registry and a single hash.
- **Cons:** Churns the green, hashed 3.1 module and every test/consumer that
  depends on `IndicatorSpec`'s shape and on `indicator_registry_hash`'s value;
  widens the blast radius into a closed Stage; couples 3.4 to a contract-change of
  something 3.1 already shipped — with no benefit 3.4 requires (the dataset-builder
  that consumes both is 3.5).
- **Why rejected:** Scope creep across a Stage boundary; the superset coexisting is
  simple-and-replaceable, and the unification is a cheap mechanical refactor once
  3.5 exercises both registries.

### Alternative B — Keep tft_typing in the training use case (as the old did)

- **Description:** Leave the known/unknown classification hardcoded downstream, in
  the model-training layer.
- **Pros:** Matches the old; nothing to add to the spec.
- **Cons:** Scatters a per-feature anti-leakage decision away from the feature
  definition; a new feature can be added without anyone deciding its typing;
  contradicts ADR 0.0.0018 rule 3 and the DoD that requires per-feature TFT typing
  as a contract; makes the known/unknown invariant untestable at the registry.
- **Why rejected:** Centralizing in the spec is a strict improvement over the old —
  single source of truth, validated, testable; the DoD demands it.

### Alternative C — Keep the old's 5-value `group` taxonomy

- **Description:** Carry `baseline`/`technical`/`sentiment`/`derived`/`fundamental`
  as the family.
- **Pros:** Verbatim with the old.
- **Cons:** Mixes computation-origin (`baseline`/`derived`) with feature family;
  diverges from the foundational 4-family taxonomy (`0.0.0016`) the H3 ablation
  relies on.
- **Why rejected:** The 4-family taxonomy is the foundational one; `baseline` and
  price-derived map to `price`. A separate `enabled_by_default`/`formula_desc`
  already carries the origin/description signal without overloading `family`.

### Alternative D — Do nothing / keep only the minimal IndicatorSpec

- **Why not acceptable:** Stage 3.4 *is* the rich registry; the minimal spec
  cannot host derived features, null policy, formula text, or TFT typing. Deferring
  blocks 3.5.

## Consequences

### Positive

- The feature registry becomes the single source of truth for features, including
  the anti-leakage tag and the TFT known/unknown typing — both validated at
  construction, both testable as invariants.
- 3.1 stays untouched and green; no churn to `indicator_registry_hash` or the
  indicator tests.
- The 4-family taxonomy aligns the registry with the foundational `0.0.0016` and
  the H3 family-ablation design.

### Negative

- Two registries (`INDICATOR_SPECS` and `FEATURE_SPECS`) and two hashes coexist
  until 3.5 unifies them — accepted; the unification is a mechanical refactor, and
  doing it now would churn a closed Stage.

### Neutral / trade-offs accepted

- The physical absorption of `IndicatorSpec` is tracked here and in ADR 3.1.0001
  §Consequences as deferred work for 3.5; this ADR is the breadcrumb.

## Implementation notes

- `FeatureSpec` (`domain/value_objects/feature_spec.py`): frozen dataclass; fields
  `name`, `family`, `source_cols`, `formula_desc`, `anti_leakage_tag`,
  `warmup_count`, `null_policy="allow"`, `dtype`, `enabled_by_default=True`,
  `tft_typing`. `__post_init__` rejects empty `name`, `warmup_count<0`, `family`
  ∉ 4-set, `anti_leakage_tag` ∉ fixed vocabulary, `tft_typing` ∉ {known,unknown} →
  `ValueError`.
- The fixed anti-leakage vocabulary (superset of 3.1's two tags): {
  `point_in_time_ohlcv`, `same_timestamp_ohlc_derived`, `trailing_window_causal`,
  `lagged_causal`, `publication_cutoff_asof`, `reported_date_asof` }.
- `FEATURE_SPECS` is a `MappingProxyType`; `feature_set_hash` mirrors
  `indicator_registry_hash` (3.1) over specs sorted by name (ADR 3.4 D3).

## References

- Related ADRs:
  [3.1.0001](./3_1_0001-feature-engineering-bc-and-indicator-contracts.md)
  (minimal `IndicatorSpec`; §Consequences declares the future absorption into
  `FeatureSpec`),
  [0.0.0018](./0_0_0018-anti-leakage-non-negotiable.md) (rule 3: known/unknown
  typing is an anti-leakage rule owned by 3.4),
  [0.0.0016](./0_0_0016-four-feature-families.md) (the 4-family taxonomy),
  [1.4.0001](./1_4_0001-canonicalizacao-de-hash-deterministico.md) (deterministic
  hashing posture the `feature_set_hash` follows).
- `docs/roadmap.md` §Stage 3.4 (`FeatureSpec`/`FeatureRegistry`; DoD: tag de
  causalidade + tipagem known/unknown).
- Old: `src/infrastructure/schemas/feature_registry.py:7-17` (rich `FeatureSpec`),
  `src/use_cases/train_tft_model_use_case.py:1216` (hardcoded known/unknown).
