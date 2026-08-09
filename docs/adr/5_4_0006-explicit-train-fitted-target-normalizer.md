---
title: ADR 5.4.0006 — The TFT target normalizer is fixed explicitly as a train-fitted global standardizer, never left to the library's automatic selection
description: Architecture Decision Record
when-use: Reference before changing the target normalizer, before setting target_normalizer to "auto", or when deciding whether per-window normalization is acceptable for the candidate
keywords: [adr, target-normalizer, group-normalizer, encoder-normalizer, auto-selection, anti-leakage, train-only-fit, pytorch-forecasting, testability]
status: accepted
created_at: 2026-08-09
updated_at: 2026-08-09
adr_id: "5.4.0006"
decision: Fix the TFT target normalizer explicitly as a single-group standardizer fitted on the training frame and expose its fitted center and scale through the port, instead of letting pytorch-forecasting's automatic selection pick a per-encoder-window normalizer
context_stage: 5.4-tft-trainer
bounded_context: modeling
---

# ADR 5.4.0006 — Explicit, train-fitted target normalizer

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

ADR 5.4.0001 clause 2 states that every **fitted** transformation is estimated
from the training block only and inherited by the other partitions. In this
Stage the target normalizer is that transformation — there is no fitted
categorical encoder, because all covariates are continuous and the group id is
constant (ADR 5.4.0004).

`pytorch-forecasting`'s `TimeSeriesDataSet` defaults `target_normalizer` to
`"auto"`. The automatic selection is **conditional on the encoder length**: when
`max_encoder_length > 20` (with `min_encoder_length > 1`) it selects an
`EncoderNormalizer`, which re-fits center and scale **per sample, on that
sample's encoder window**; otherwise it selects a `GroupNormalizer`, fitted once
over the frame it is given. The library's own parameter documentation flags the
encoder variant as the one on which overfitting tests fail.

That conditional is a trap for this Stage specifically:

- The pre-registered default is `max_encoder_length = 60`, so **production would
  get the per-window normalizer**.
- The small geometries the tests need (encoder around 10 sessions, to keep the
  synthetic panel short and the suite fast) fall on the other side of the
  threshold and would get the frame-fitted normalizer. The suite would therefore
  validate a path production never takes — a green gate covering the wrong code.
- With a per-window normalizer there is no train-fitted statistic to inspect at
  all, so clause 2 of ADR 5.4.0001 loses its object and the acceptance criterion
  meant to prove it (concept A4c) becomes unverifiable.

Note that the per-window normalizer is **not** a leakage bug: the encoder window
is entirely at or before the decision date, so it is causal. The problem is
different — it is a silent, geometry-dependent change of design, and it removes
the artifact the anti-leakage invariant is verified against.

## Decision

Set `target_normalizer` **explicitly** to a single-group standardizer
(`GroupNormalizer` with an empty group list, equivalent to a global standardizer
over the frame it is fitted on), for every geometry, in tests and in production
alike. The training dataset is built from the training frame, so the normalizer
is fitted there; the monitor and prediction datasets are derived from it and
inherit the fitted parameters rather than re-fitting.

The fitted `center` and `scale` are returned through the port
(`TftTrainingResult.normalizer_center` / `normalizer_scale`) so the invariant can
be asserted directly on numbers instead of inferred from prediction behavior.

The assertion compares them against the mean and the **sample** standard
deviation (with the library's epsilon) of the target over the sessions of the
**training frame** — the `train` block plus the `max_horizon` purge sessions
that follow it. Two corrections are folded into that sentence, and both would
otherwise produce a criterion that fails against a correct implementation:

- Not the training *decisions*: the library fits on every row of the frame it
  receives, and the decisions are a subset of those rows (the first
  `max_encoder_length − 1` have no full window).
- Not the `train` block alone: the frame necessarily extends `max_horizon`
  sessions past `train_end`, because those rows are the **labels** of the last
  training decisions. They are purge sessions, strictly before `early_stop`,
  `calib` and `test`, so including them is not leakage — but excluding them
  from the assertion's population would make the numbers disagree.

The mutation this criterion detects is **building the training dataset from the
full panel**. Mutating the *prediction* frame proves nothing: it is derived from
the training dataset and inherits the fitted parameters without re-fitting.

## Alternatives considered

### Alternative A — Leave `target_normalizer="auto"`

- **Description:** Accept the library default and whatever it selects.
- **Pros:** No configuration; follows tutorials.
- **Cons:** The selection flips on `max_encoder_length > 20`, so the test
  geometry and the production geometry land on different normalizers; clause 2
  of ADR 5.4.0001 becomes unverifiable; a later change of encoder length would
  silently change the model's normalization design.
- **Why rejected:** A design decision that depends on a hyperparameter crossing
  an undocumented-in-our-docs threshold is not a decision, it is an accident
  waiting to be discovered by whoever changes the window.

### Alternative B — Choose `EncoderNormalizer` deliberately

- **Description:** Adopt per-window normalization on purpose, arguing it adapts
  to volatility regimes and is still causal.
- **Pros:** Causal; adapts scale to the local regime, which for daily returns
  (volatility clustering) is defensible on its own terms.
- **Cons:** Each sample is normalized by a different statistic, so the emitted
  quantiles' inverse transform varies per decision — comparability with the
  fixed-scale comparators (5.2/5.3) becomes an argument rather than a
  construction; there is no fitted artifact to assert, so the anti-leakage
  invariant loses its direct verification; and it introduces a modeling choice
  the domain doc never pre-registered, in the confirmatory candidate.
- **Why rejected:** It is a real modeling alternative, but adopting it here
  would be an undeclared change to the pre-registered candidate, decided by a
  library default rather than by the design. If it is ever wanted, it belongs in
  an ADR of its own with the comparability argument made explicitly.

### Alternative C — No normalization at all (identity)

- **Description:** Feed raw log returns to the loss.
- **Pros:** Nothing fitted, so clause 2 is trivially satisfied; the emitted
  quantiles need no inverse transform.
- **Cons:** Daily log returns have a scale around 1e-2; with the pre-registered
  learning rate, optimization is poorly conditioned and the model spends its
  capacity on scale rather than shape. It also diverges from how the
  architecture is normally trained, weakening the "this is a TFT" claim.
- **Why rejected:** Trades a real optimization property for a verification
  convenience that Alternative-as-decided already provides.

### Alternative D — Do nothing / decide during implementation

- **Why not acceptable:** The default silently decides it, and decides it
  *differently* in the test suite than in production. That is precisely the case
  where leaving it implicit is worse than any explicit choice.

## Consequences

### Positive

- Test geometry and production geometry exercise the same normalization path, so
  the suite covers what actually runs.
- Clause 2 of ADR 5.4.0001 gains a direct, numeric verification instead of an
  indirect behavioral one that the context channel would confound.
- Changing the encoder length no longer changes the model's normalization
  design as a side effect.

### Negative

- The port surface grows by two floats whose only consumer is a test. The
  alternative — reaching into the adapter's internals from the test — would
  break the port abstraction the whole Stage rests on, so the cost is accepted.
- Global standardization does not adapt to volatility regimes; under regime
  shift the normalized target drifts. This is the same exposure the comparators
  have, and reading it is Step 6's job, not this Stage's.

### Neutral / trade-offs accepted

- The scale is estimated over the `train` block of each fold, so it differs
  across folds. That is correct under the expanding-window design (each fold's
  model is fitted on its own history) and matches how the comparators estimate
  their own frozen statistics (ADR 5.2.0002).

## Implementation notes

- Both the monitor and the prediction datasets are built with the library's
  `from_dataset` derivation from the training dataset, which reuses the fitted
  normalizer instead of re-fitting; constructing them from the full frame
  directly is the mistake this ADR and 5.4.0001 exist to prevent.
- The returned `center`/`scale` come from the fitted normalizer's parameters, not
  recomputed by the adapter — recomputing would make the assertion tautological.

## References

- Related ADRs:
  [5.4.0001](./5_4_0001-encoder-context-across-partitions.md) (clause 2 — the
  invariant this decision makes verifiable);
  [5.4.0004](./5_4_0004-tft-input-typing-and-relative-time-index.md) (constant
  group, continuous covariates — why the normalizer is the only fitted
  transform);
  [5.2.0002](./5_2_0002-frozen-train-estimation-causal-state.md) (comparators'
  train-estimated statistics);
  [0.0.0018](./0_0_0018-anti-leakage-non-negotiable.md).
- External: `pytorch-forecasting` 1.8 `TimeSeriesDataSet` — automatic
  normalizer selection conditional on `max_encoder_length > 20`, and the
  parameter documentation's note on `EncoderNormalizer`.
- Conversation/issue: GitHub issue #57; Checkpoint A round 2 finding
  (2026-08-09) that the automatic selection differs between test and production
  geometries.
