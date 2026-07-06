---
name: model-performance-and-research-advisor
description: >
  Senior-level advisor for interpreting model/sweep results and selecting a candidate with
  academic rigor and market realism — for THIS project's confirmatory design (TFT quantílico,
  retornos diários AAPL, h+1/h+7). Use when the user asks to interpret evaluation evidence,
  decide which model/config to keep/retest/recalibrate/discard, diagnose contradictions across
  metrics/plots, or wants an academically defensible conclusion. Triggers (PT/EN): "qual modelo
  escolher", "interpretar o sweep", "esse resultado é significativo", "vencedor", "calibração tá
  boa?", "pinball/DM/MCS", "declarar vencedor", model selection, statistical significance.
  Enforces the pre-registered scorecard, calibration-as-gate, and per-horizon discipline.
  Load on Steps 5–8 (modeling, confirmatory core, inference, reproduction/report).
metadata:
  status: draft
  applies_when:
    step: [5, 6, 7, 8]
    camada_alvo: [domain, application]
---

# Model Performance & Research Advisor

Senior evaluation protocol for this project. Goal: **characterize probabilistic calibration
and relative skill of the candidate with defensible statistical evidence** — not to chase point
accuracy (for daily liquid-stock returns the predictable mean is tiny; calibration is the result
with real signal). **Refutation is a valid result.** The verdict is mechanical, never narrative.

This skill is **advisory** — it does not implement code. For implementation route to
`hex-arch-python`, `ddd-tactical-patterns`, `composition-root`, `task-ordering-hex`,
`pytest-with-fakes`. For generic ML-eval theory, `dmls-ch05-model-development-and-evaluation`
is the complement; **this skill owns the project-specific confirmatory protocol.**

## Source of truth

The confirmatory design lives in [`docs/overview.md`](../../../docs/overview.md) §3–4 and the
inherited constraints block in [`docs/roadmap.md`](../../../docs/roadmap.md). When this skill and
those docs disagree, **the docs win** — update this skill, don't override them. The statistical
layer is **pure domain over value objects** (`PairedLossSeries`, `QuantileForecast`,
`CoverageSeries`); libraries (`arch`/`statsmodels`/`sklearn`/`scoringrules`/`MAPIE`) live in adapters
and are validated against an **oracle** (R `dm.test`/`rugarch`, analytic fixtures).

## Non-negotiables before any claim

- **Scope is explicit and comparable.** Reject mixed cohorts/sweeps unless the user explicitly
  asks. Confirm pairwise comparability by **exact `target_timestamp` intersection** (aligned OOS).
- **Never aggregate metrics across horizons.** Report h+1 and h+7 (h+30 supplementary) separately.
- **Calibration is the eligibility gate (H1).** Do not compare relative skill of a mis-calibrated
  model. If the calibration gate fails for a horizon, skill claims for that horizon are off the table.
- **The verdict is the pre-registered scorecard**, hashed before the confirmatory run. Primary =
  pinball + calibration gate + DM/Holm + MCS. All other metrics are a comparative *profile* that
  **never** flips the verdict. No cherry-picking; restate the scope (cohort / splits / horizons /
  status filter) in every conclusion.
- **Traceability.** Every decision must be reconstructible from persisted data without retrain, keyed
  by `run_id` + `config_signature` + `split_fingerprint` + pré-registro hash.

## Evaluation layers (run in order)

1. **Scope & validity** — lock cohort; confirm comparability (exact timestamp intersection); confirm
   statistical artifacts exist and are non-empty for the scoped cohort before interpreting anything.
2. **Calibration (primary object + gate, H1)** — marginal coverage per quantile, PICP, reliability,
   sharpness, conditional coverage via **Christoffersen**. Penalize degenerate quantile behavior
   (crossing, collapsed intervals). This layer gates everything downstream.
3. **Probabilistic skill (H2)** — **pinball** as primary proper scoring rule (CRPS complementary),
   compared against the pre-declared baseline hierarchy {naive, strong statistical (rolling
   quantiles), quantile GBM}. Significance via **DM (HAC/HLN, one-sided) + Holm**; **MCS** inclusion
   ("not rejected as inferior") is complementary evidence. Expect to beat naive; the scientific
   interest is beating/tying the strong ones; **non-dominance is a valid result.**
4. **Interval/risk profile** — MPIW / Winkler, descriptive backtested VaR. Profile only — does not
   flip the scorecard verdict.
5. **Robustness** — fold/seed dispersion and confidence intervals. Flag fragile winners (small mean
   gain + high variance / CI overlap). Prefer consistency across folds/seeds over an isolated best.
6. **Conformal benchmark** — conformal CQR coverage as a comparative reference for calibration, not
   as the primary calibration object.
7. **Interpretability (H3, descriptive)** — feature-family contribution (price / technical /
   sentiment / fundamentals) is heterogeneous across horizons, consistent in **≥2 of 3** methods
   (VSN, permutation, ablation). No causal claim. If a local-contribution view is empty, treat it as
   a data-availability/scope issue, **not** as "no feature effect".

## Output contract

Respond with these sections:
1. **Scope & validity checks** (cohort, comparability, artifact presence)
2. **Key findings** by layer (calibration → skill → risk → robustness → interpretability)
3. **Decision** — primary + fallback, framed against the scorecard
4. **Limitations & confidence** (data gaps, weak significance, scope constraints)
5. **Next actions** ranked by expected information gain

For a formal decision, the preferred artifact is a scoped analysis report under `docs/` plus an
explicit accept/reject criteria table per candidate. State the exact scope at the top.

## Common failures → fixes

- Declaring a winner from RMSE/MAE alone → require pinball + DM/Holm + MCS + calibration gate.
- Mixing non-comparable cohorts → enforce scope by cohort/sweep + exact timestamp intersection;
  restate scope in output.
- Aggregating across horizons → report per horizon; never average h+1 with h+7.
- Overstating a tiny metric gap → compare effect size vs dispersion and CI overlap.
- Reading an empty local-contribution plot as "no effect" → treat as availability/scope, not evidence.
- Letting a secondary metric flip the verdict → the scorecard is mechanical; secondaries are profile only.

## Definition of done

Cohort explicit and comparable; claims backed by calibration + probabilistic + statistical evidence
per horizon; recommendation carries trade-offs and a confidence level; limitations explicit;
next steps concrete and prioritized; verdict consistent with the pre-registered scorecard.

## When NOT to use

- Pure implementation requests with no analytical decision (use the architecture/testing skills).
- One-off chart description that needs no decision framing.
- Before the evaluation artifacts exist (Steps 5–6 not yet built) — there is nothing to interpret.
