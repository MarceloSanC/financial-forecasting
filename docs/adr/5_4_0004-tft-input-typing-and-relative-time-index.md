---
title: ADR 5.4.0004 — TFT input typing derives from FeatureSpec.tft_typing for registry features, declares the calendar columns locally as a stated floor, and excludes the absolute time index in favour of the relative one
description: Architecture Decision Record
when-use: Reference before changing which columns are known vs unknown for the TFT, before adding the absolute time index as a covariate, or when closing issue #58 (registering calendar columns in the FeatureRegistry)
keywords: [adr, tft, known-unknown, tft-typing, feature-registry, calendar, time-idx, relative-time-index, extrapolation, declared-floor]
status: accepted
created_at: 2026-08-09
updated_at: 2026-08-09
adr_id: "5.4.0004"
decision: Registry features are typed from FeatureSpec.tft_typing, the calendar columns are declared as known in a modeling-layer constant (declared floor, general fix tracked in issue #58), and the absolute time index is not a covariate — relative position inside the window is supplied by the library's relative time index instead
context_stage: 5.4-tft-trainer
bounded_context: modeling
---

# ADR 5.4.0004 — Input typing and the absent absolute time index

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

The TFT separates its inputs into static, **observed** (unknown ahead of time)
and **known** covariates; observed inputs and the target enter the encoder only
up to `t`, while known inputs extend into the decoder up to `t+τ` (Lim et al.
2021, §3 and Eq. (1)). That asymmetry is the formal basis of the anti-leakage
rule, and ADR 0.0.0018 rule 3 makes known/unknown typing a first-class
anti-leakage decision.

ADR 3.4.0002 already acted on this: it promoted `tft_typing ∈ {known, unknown}`
into `FeatureSpec` as a required, validated field, explicitly rejecting
Alternative B — leaving the typing hardcoded in the training use case, as the
previous project did (`train_tft_model_use_case.py:1216`:
`known_real_cols = [time_idx, day_of_week, month]`, everything else unknown).

Two facts complicate the straightforward application of that ADR here:

- **The calendar columns are not registry features.** `FEATURE_SPECS` currently
  holds 55 specs, all `unknown`; `day_of_week`, `month` and `time_idx` are added
  by the dataset assembler in Stage 3.5, not by the registry. The registry's own
  docstring records this. So there is no spec to read the typing from for
  exactly the columns that are known.
- **Registering them upstream is not a local change.** `FEATURE_SPECS` feeds
  `feature_set_hash`, and `list_feature_specs(enabled_only=True)` drives both the
  dataset assembly (3.5) and the GBM feature set (5.3, where calendar is
  concatenated explicitly per ADR 5.3.0003). Adding calendar specs changes the
  hash and the column set across three closed Stages.

Separately, the absolute time index needs a decision. The library's own examples
list it among the known reals, and the previous project did the same. ADR
5.3.0003 excluded it from the GBM feature set because, under an expanding
walk-forward, every test index lies outside the range seen in training: trees do
not extrapolate, so it has zero out-of-sample discrimination while enabling
in-sample memorization.

## Decision

Three coupled rules:

1. **Registry features are typed from the spec.** The unknown covariate list is
   built from `list_feature_specs(enabled_only=True)` filtered by
   `spec.tft_typing == 'unknown'` — never from a parallel list. If a future spec
   is registered as `known`, it moves lists automatically.

2. **Calendar columns are declared as known in a modeling-layer constant — a
   declared floor.** `day_of_week` and `month` are listed once in the use case,
   in the same shape Stage 5.3 used for its calendar concatenation. The general
   treatment, registering them in the `FeatureRegistry` with
   `tft_typing='known'`, is tracked in **issue #58** with its blast radius
   documented. This is a stated floor, not a silent capture of the concern.

3. **The absolute time index is not a covariate.** `time_idx` is the panel's
   index only. Relative position inside the encoder/decoder window is supplied by
   the library's relative time index feature, which is bounded by construction.

## Alternatives considered

### Alternative A — Register the calendar columns in the FeatureRegistry now

- **Description:** Add `day_of_week` and `month` as `FeatureSpec`s with
  `tft_typing='known'`, making the registry the single source of typing.
- **Pros:** The general, correct treatment; fully honours ADR 3.4.0002; removes
  the local declaration from both 5.3 and 5.4.
- **Cons:** Changes `feature_set_hash` and the set returned by
  `list_feature_specs(enabled_only=True)`, which drives the dataset assembly
  (3.5) and the GBM feature set (5.3); requires migrating hashes and fixtures
  across three closed Stages, and would churn the dataset the candidate is about
  to be trained on.
- **Why rejected now:** Correct, but its blast radius is outside this Stage's
  critical path. Recorded as issue #58, referenced from the concept, so the floor
  is declared rather than hidden.

### Alternative B — Hardcode the full typing in the use case (the old project's shape)

- **Description:** A single local list naming known columns and treating
  everything else as unknown, as `train_tft_model_use_case.py` did.
- **Pros:** One place; nothing to read from the registry.
- **Cons:** Exactly the alternative ADR 3.4.0002 rejected — a per-feature
  anti-leakage decision drifts away from the feature definition, and a newly
  registered feature gets a typing nobody chose.
- **Why rejected:** It would discard the part of the general solution that
  already works.

### Alternative C — Include the absolute time index among the known reals

- **Description:** Follow the library example and the previous project.
- **Pros:** Gives the model an explicit trend coordinate.
- **Cons:** Under expanding walk-forward, every test index is outside the
  training range by construction. Unlike trees, which simply cannot extrapolate,
  a normalized continuous input here *does* extrapolate — silently, into a region
  where the mapping was never estimated. The failure mode is worse than the one
  ADR 5.3.0003 avoided, not milder.
- **Why rejected:** Same rationale as 5.3.0003, with a sharper edge for a
  continuous model.

### Alternative D — Do nothing / leave typing to the adapter

- **Why not acceptable:** Typing is the anti-leakage rule of the architecture
  (ADR 0.0.0018 rule 3). Deciding it inside the adapter would place it below the
  layer gate and outside the reach of a unit test.

## Consequences

### Positive

- The typing of every registry feature has exactly one source, and it is the
  validated field a previous ADR created for this purpose.
- The known/unknown split is testable at the use case level, without the
  library: a unit test pins both lists against the registry and against the
  calendar constant, and detects any reclassification by mutation.
- The candidate is not fed an input that is guaranteed to be out of range at
  prediction time.

### Negative

- Two places still describe the calendar columns (5.3's concatenation and 5.4's
  known list) until issue #58 closes; they can drift, and only a test pinning
  both against the dataset schema would catch it.

### Neutral / trade-offs accepted

- Excluding the absolute index means the model has no explicit long-run trend
  coordinate. For daily returns, whose predictable mean component is minuscule
  (overview §1), this is not expected to cost signal.

## Implementation notes

- Unknown list: registry order, filtered by `tft_typing == 'unknown'`. Known
  list: the calendar constant. Neither contains `time_idx`, `timestamp`,
  `asset_id`, `fundamentals_effective_date` or `target_return`.
- The panel crossing the port belongs to a **single asset** (the one in the
  `ScopeSpec`), so no group identity travels through the contract: the adapter
  supplies a constant group id because the library requires one, and that is an
  adapter-internal detail carrying no information. Multi-asset readiness lives
  in the architecture (one run per scope), not in a static categorical this
  Stage introduces speculatively.
- The port receives `feature_names` (full ordered list) and
  `known_feature_names` (subset); the adapter derives the unknown list by
  difference, so the two can never disagree.

## References

- Related ADRs:
  [3.4.0002](./3_4_0002-featurespec-superset-and-tft-typing-promotion.md) (the
  typing promotion this ADR consumes, and whose Alternative B it declines to
  reintroduce);
  [5.3.0003](./5_3_0003-feature-set-no-time-idx.md) (absolute time index excluded
  from the GBM feature set);
  [0.0.0018](./0_0_0018-anti-leakage-non-negotiable.md) rule 3;
  [0.0.0016](./0_0_0016-four-feature-families.md).
- External: Lim, B.; Arık, S. Ö.; Loeff, N.; Pfister, T. (2021).
  "Temporal Fusion Transformers…". *IJF* 37(4), 1748–1764, §3 and Eq. (1).
- Conversation/issue: GitHub issue #57 (this Stage); GitHub issue #58 (the
  general treatment — calendar columns in the registry).
