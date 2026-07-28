---
title: ADR 5.3.0003 — GBM feature set — registry features + ordinal calendar, excluding time_idx
description: Architecture Decision Record
when-use: Reference whenever revisiting which dataset columns tree-based models consume, or before adding a monotone time/trend feature to any tabular model
keywords: [adr, lightgbm, feature-set, time-idx, calendar, day-of-week, extrapolation, trees]
status: accepted
created_at: 2026-07-19
updated_at: 2026-07-19
adr_id: 5.3.0003
decision: The GBM consumes the enabled FeatureRegistry features plus day_of_week and month as plain ordinal integers, and excludes time_idx (and non-feature columns timestamp, asset_id, fundamentals_effective_date, target_return) from the design matrix.
context_stage: 5.3-gbm-quantile-baseline
---

# ADR 5.3.0003 — GBM feature set: registry features + ordinal calendar, excluding `time_idx`

## Status

`accepted`

## Context

The 3.5 dataset materializes: registry features (canonical insertion order),
calendar columns `day_of_week`/`month`, `time_idx` (monotone session
counter required by the TFT's temporal encoding), plus non-feature columns
(`timestamp`, `asset_id`, `fundamentals_effective_date`, `target_return`).
The GBM must declare which columns enter its design matrix; the choice
affects comparability with the TFT (5.4) and the validity of the
walk-forward evaluation.

Two verified mechanisms drive the decision:

1. **Trees cannot extrapolate.** Tree predictions are piecewise-constant
   ("they are not good at extrapolation" — scikit-learn User Guide §1.10).
   Under the expanding walk-forward, every test session has a `time_idx`
   strictly greater than every training value, so every test row falls in
   the same terminal region of every `time_idx` split: the feature carries
   **zero out-of-sample discriminative information by construction**, while
   in-sample it acts as a near-unique row identifier — a pure overfitting
   channel that consumes split budget and corrupts feature importances.
   Neither `mlforecast` nor `skforecast` even offers a raw time-index
   feature (both handle trend via target transforms); our target is already
   a return (differenced), so no trend handling is needed.
2. **Calendar effects in daily equity returns are attenuated to
   insignificance in modern large-cap data.** Schwert (2003, Table 3):
   weekend coefficient t = −8.86 (1953–1977) vs t = −1.37 (1978–2002);
   Robins & Smith (2016): structural break ~1975, insignificant after;
   Plastun et al. (2019, DJIA 1900–2018): "since the 1980s all calendar
   anomalies disappeared"; Sullivan, Timmermann & White: the best calendar
   rule does not survive data-snooping correction (Reality Check
   p ≈ 0.20–0.24). Honest counterweight: Zilca (2017) finds the effect
   declined most in the **largest**-cap deciles but did not vanish
   everywhere — AAPL is the extreme large-cap case.

Meanwhile the TFT (5.4) will consume calendar columns as known covariates —
that is the basis of the known/unknown anti-leakage typing (ADR 3.4.0002,
domain doc §5.2).

## Decision

Design matrix = FeatureRegistry features (`list_feature_specs
(enabled_only=True)`, canonical insertion order) **plus** `day_of_week` and
`month` encoded as plain ordinal integers. Excluded: `time_idx` (mechanism 1),
and the non-feature columns `timestamp`, `asset_id`,
`fundamentals_effective_date`, `target_return`.

Calendar columns are included for **feature-set parity with the TFT
candidate**, not from expectation of predictive effect: a feature-set
mismatch between candidate and comparator would confound exactly the H2
comparison the thesis makes, while two low-cardinality ordinal columns cost
a tree model almost nothing and the null result is itself pre-registered and
literature-grounded. Ordinal (not one-hot/cyclic) encoding follows
scikit-learn's official guidance: cyclical machinery exists for linear
models; trees "can learn a non-monotonic relationship between ordinal input
features and the target".

## Alternatives considered

### Alternative A — Registry features only (no calendar)
- **Pros:** narrowest cut, 100% governed by FeatureSpec; drops columns the
  anomaly literature says are dead.
- **Why rejected:** creates a feature-set asymmetry with the TFT (which
  sees calendar as known covariates), confounding the model comparison —
  a difference in information sets would be entangled with the difference
  in model class.

### Alternative B — All dataset columns (including time_idx)
- **Pros:** maximal parity with what the TFT's dataset carries.
- **Why rejected:** mechanism 1 — `time_idx` is provably useless
  out-of-sample under expanding walk-forward and harmful in-sample
  (memorization channel, importance corruption). The TFT consumes
  `time_idx` as positional encoding infrastructure, not as a free
  covariate; feeding it to a tree is not parity, it is a category error.

### Alternative C — Do nothing / decide per-experiment
- **Why rejected:** the confirmatory design pre-registers feature sets;
  a floating design matrix would undermine auditability (the run_id payload
  includes the ordered feature_names precisely to freeze this).

## Consequences

### Positive
- Comparable information sets between GBM and TFT (calendar included in
  both; `time_idx` only where it is architectural infrastructure).
- No monotone-feature overfitting channel; feature importances (if ever
  inspected) stay meaningful.
- Exclusion is pre-registered and literature-grounded — a defensible
  design decision instead of a post-hoc discovery.

### Negative
- Two likely-null columns consume (marginal) split budget.
- If a genuine regime/trend signal existed in calendar time, the GBM cannot
  represent it (accepted: returns are ~stationary and regime features are
  the registry's job — e.g. volatility features).

### Neutral / trade-offs accepted
- The registry's warmup NaNs pass through as native LightGBM missing values
  (concept I11) — no imputation is introduced by this Stage.

## Implementation notes

- Column selection is nominal and validated: missing expected columns raise
  before any training (concept C6), naming the gap — protects against
  registry × dataset drift.
- `day_of_week`/`month` arrive as int64 from the dataset schema; cast to
  float like every other column (LightGBM treats them as numeric ordinals).

## References

- Related ADRs: 3.4.0002 (known/unknown typing promotion), 3.5.0002 (regime
  features/warmup), 5.3.0001 (per-horizon boosters)
- External:
  - scikit-learn User Guide §1.10 (Decision Trees): "piecewise constant
    approximations… not good at extrapolation"; example "Time-related
    feature engineering": ordinal time features are "not much of a problem
    for tree-based models". Accessed 2026-07-19.
  - skforecast docs/tutorial "Modelling time series trend with tree based
    models" (Amat Rodrigo & Escobar Ortiz): predictions saturate "close to
    the maximum values observed in the training data". Accessed 2026-07-19.
  - Schwert, G. W. (2003). "Anomalies and Market Efficiency." *Handbook of
    the Economics of Finance*, ch. 15 (Table 3: weekend effect
    1978–2002 t = −1.37).
  - Robins, R. P.; Smith, G. P. (2016). "No More Weekend Effect." *Critical
    Finance Review*, 5(2), 417–424.
  - Plastun, A.; Sibande, X.; Gupta, R.; Wohar, M. E. (2019). "Rise and
    fall of calendar anomalies over a century." *NAJEF*, 49, 181–205.
  - Sullivan, R.; Timmermann, A.; White, H. (2001). "Dangers of data
    mining: the case of calendar effects in stock returns." *Journal of
    Econometrics*, 105(1), 249–286. (Quotes verified against the 1998 UCSD
    working-paper version.)
  - Zilca, S. (2017). "The evolution and cross-section of the
    day-of-the-week effect." *Financial Innovation*, 3(33). (Decline
    largest in large caps; honest counterweight.)
- Conversation: bifurcação B4, sessão de kickoff da Stage 5.3 (2026-07-19)
