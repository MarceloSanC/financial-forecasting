---
title: ADR 5.3.0001 — Direct multi-horizon — one independent booster per (quantile level × horizon)
description: Architecture Decision Record
when-use: Reference whenever revisiting how the GBM baseline covers horizons h ∈ {1, 7}, or before changing the multi-step strategy of any tabular model in the project
keywords: [adr, lightgbm, multi-horizon, direct, recursive, quantile, gbm]
status: accepted
created_at: 2026-07-19
updated_at: 2026-07-19
adr_id: 5.3.0001
decision: The GBM baseline trains one independent LightGBM booster per (quantile level × horizon), with the label shifted to target_return[t+h]; recursion and horizon-as-feature are rejected.
context_stage: 5.3-gbm-quantile-baseline
---

# ADR 5.3.0001 — Direct multi-horizon: one independent booster per (quantile level × horizon)

## Status

`accepted`

## Context

The project target at horizon `h` is the **one-day** log return realized at
session `t+h` (ADR 3.5.0001 + 4.3.0001), for h ∈ {1, 7} — two
non-adjacent horizons, not a contiguous path 1..7. LightGBM has no native
multi-quantile or multi-output mode (`objective` is a scalar enum, `alpha` a
single double — domain doc §4.2), so a dense grid already requires one
booster per level; the open question is how those boosters cover the two
horizons.

The canonical taxonomy of multi-step strategies (recursive, direct, DirRec,
MIMO, DIRMO) is formalized in Ben Taieb, Bontempi, Atiya & Sorjamaa (2012).
Careful reading of the literature matters here, because the folklore
misquotes it:

- In the NN5 empirical comparison (2012), **recursive beat direct** among
  single-output strategies; multiple-output strategies (MIMO/DIRMO) won
  overall. The paper does NOT license "direct is more accurate".
- The bias/variance analysis lives in Ben Taieb & Atiya (2016, IEEE TNNLS):
  direct has the smallest bias but high variance — each horizon forecast in
  isolation "could produce completely unrelated forecasts over the whole
  horizon"; direct also loses `h−1` training rows per horizon (edge effect).
- "Direct multi-horizon" in the deep-learning lineage (MQ-RNN — Wen et al.
  2017; TFT — Lim et al. 2021) means ONE model emitting a K×H output matrix
  — Ben Taieb's **MIMO/joint**, the opposite of his **direct**. The
  project's TFT candidate (5.4) sits on the MIMO side; this ADR's GBM sits
  on the direct side. The thesis must not conflate the two senses.

## Decision

For each horizon h ∈ scope and each quantile level τ in the dense grid,
train an **independent LightGBM booster** with training pairs
(features known at `t`, label `target_return[t+h]`) — K levels × H horizons
boosters per fold. No recursion; no pooling of horizons; no `horizon`
feature. The justification is **structural fit**, not accuracy folklore:
the deliverable horizons are {1, 7}, recursion would manufacture six
throwaway intermediate forecasts (h=2..6) importing six rounds of error
accumulation, and with H=2 the cost objection the literature raises against
direct does not bind.

## Alternatives considered

### Alternative A — Recursive (iterated one-step model)
- **Description:** train one booster set for h=1; feed predictions back to
  iterate up to h=7.
- **Pros:** single model set (K boosters total); lowest variance in the
  Ben Taieb & Atiya decomposition; won among single-output strategies on NN5.
- **Cons / why rejected:** structurally infeasible here — the feature vector
  is composed of price-derived indicators/sentiment/fundamentals, so
  iterating requires simulating the **entire feature vector** at t+1..t+6
  from predicted returns, which the dataset contract (3.5) cannot provide;
  it would also propagate error through five intermediate sessions the
  project never reports. Recursion of quantiles (not means) is additionally
  ill-defined without a distributional simulation step.

### Alternative B — Horizon as a feature (pooled)
- **Description:** stack rows of all horizons with a `horizon` column;
  K boosters total.
- **Pros:** parameter sharing across horizons; half the boosters.
- **Cons / why rejected:** not a member of the canonical taxonomy (no
  primary academic formalization found — practitioner pattern only), mixes
  target populations with different conditional distributions, and blurs the
  per-horizon reading that the confirmatory design (Step 6, per-horizon
  discipline) requires.

### Alternative C — Do nothing / single grid for all horizons
- **Description:** train only h-agnostic boosters (label t+1) and emit the
  same grid for every h, like the flat baselines of 5.2.
- **Why rejected:** the GBM exists to raise the H2 bar above the 5.2
  baselines; an h-flat GBM cannot differentiate horizons and degenerates
  into an expensive incondicional baseline, forfeiting the stage's purpose.

## Consequences

### Positive
- Each horizon gets its own conditional quantile function — the comparator
  can actually contrast h=1 vs h=7 against the TFT.
- No error accumulation; no simulated features; anti-leakage stays exactly
  the harness's purge geometry (label window ≤ partition_end + max_horizon,
  covered by the 5.1 gap).
- Clean identity per booster (`objective='quantile'`, `alpha=τ`, horizon h)
  — auditable and reproducible.

### Negative
- K×H boosters per fold (14 with the 7-level grid) — CPU time scales
  linearly with levels × horizons.
- Horizon isolation: nothing couples the h=1 and h=7 predicted
  distributions (Ben Taieb & Atiya's variance/discontinuity cost). Declared
  honestly in the thesis; no standard fix exists (the CFG rearrangement
  handles level-direction crossing only).
- Edge effect: the literature's loss of h−1 training rows does NOT apply
  under this harness — labels are drawn from the full session grid and the
  last train/early_stop labels land inside the purge gap (concept I12), so
  no pair is lost. The residual cost is only that the h=7 label window ends
  deeper into the gap (still strictly before the next partition — 5.1
  arithmetic, margin `embargo+1`).

### Neutral / trade-offs accepted
- The GBM (direct/per-horizon) and the TFT (MIMO/joint) differ in strategy
  class by construction; this is the comparison the thesis wants, and the
  terminology distinction is recorded here to keep it honest.

## Implementation notes

- Port `QuantileModelTrainer.train_and_predict` receives
  `train_labels_by_horizon` / `early_stop_labels_by_horizon`; the adapter
  loops horizons × levels internally. Feature matrices are shared across
  horizons; only labels shift.
- Non-finite labels exclude the pair from that horizon's fit (concept I11).

## References

- Related ADRs: 3.5.0001 (target definition), 4.3.0001 (session indexing),
  5.1.0001 (walk-forward geometry)
- Domain doc: `docs/domain/modeling/quantile-model-training.md` §2.1, §4
- External:
  - Ben Taieb, S.; Bontempi, G.; Atiya, A. F.; Sorjamaa, A. (2012). "A
    review and comparison of strategies for multi-step ahead time series
    forecasting based on the NN5 forecasting competition." *Expert Systems
    with Applications*, 39(8), 7067–7083. DOI: 10.1016/j.eswa.2012.01.039.
    (Taxonomy §2; NN5 result §5.3: MIMO/DIRMO > REC > DIR.)
  - Ben Taieb, S.; Atiya, A. F. (2016). "A Bias and Variance Analysis for
    Multistep-Ahead Time Series Forecasting." *IEEE TNNLS*, 27(1), 62–76.
    DOI: 10.1109/TNNLS.2015.2411629. (Direct: smallest bias, high variance,
    edge effect of h−1 rows.)
  - Ben Taieb, S.; Huser, R.; Hyndman, R. J.; Genton, M. G. (2016).
    "Forecasting Uncertainty in Electricity Smart Meter Data by Boosting
    Additive Quantile Regression." *IEEE Trans. Smart Grid*, 7(5),
    2448–2455. DOI: 10.1109/TSG.2016.2527820. (§IV: functions "distinct for
    each quantile and horizon" — the per-(τ,h) precedent, 21 quantiles × 48
    horizons.)
  - Wen, R.; Torkkola, K.; Narayanaswamy, B.; Madeka, D. (2017). "A
    Multi-Horizon Quantile Recurrent Forecaster." arXiv:1711.11053. (K×Q
    output matrix — the MIMO sense of "direct multi-horizon".)
  - Nixtla `mlforecast` docs (`MLForecast.fit(max_horizon=...)`: "Train this
    many models, where each model will predict a specific horizon");
    skforecast docs (`ForecasterDirect`: "a separate model is trained to
    predict each step in the forecast horizon"). Library-practice
    corroboration, accessed 2026-07-19.
- Conversation: bifurcação B1, sessão de kickoff da Stage 5.3 (2026-07-19)
