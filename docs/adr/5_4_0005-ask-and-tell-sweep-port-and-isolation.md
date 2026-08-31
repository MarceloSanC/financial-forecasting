---
title: ADR 5.4.0005 — The hyperparameter search port is an ask-and-tell interface with the trial loop in the use case, and the exploratory sweep writes nothing to the silver layer
description: Architecture Decision Record
when-use: Reference before passing an objective callable through the search port, before moving the trial loop into the adapter, or before persisting sweep predictions alongside confirmatory ones
keywords: [adr, optuna, hyperparameter-search, ask-and-tell, port, exploratory, confirmatory, raschka, data-snooping, isolation, silver]
status: accepted
created_at: 2026-08-09
updated_at: 2026-08-09
adr_id: "5.4.0005"
decision: Expose hyperparameter search as an ask-and-tell Protocol (create_study/ask/tell/best_trial) with the trial loop owned by the RunTftSweep use case, and keep the sweep structurally isolated — objective measured only on the early-stopping partition, nothing written to fact_oos_predictions or dim_run, every run tagged exploratory
context_stage: 5.4-tft-trainer
bounded_context: modeling
---

# ADR 5.4.0005 — Ask-and-tell search port and structural isolation of the sweep

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

The Stage delivers an exploratory hyperparameter sweep (roadmap §5.4:
"sweeps Optuna rotulados como exploratórios"). Two independent questions have to
be settled: what shape the search takes as a hexagonal port, and how the sweep is
kept from contaminating the confirmatory evidence.

On the **shape**: Optuna's headline API is `study.optimize(objective, n_trials)`
— the caller hands a callable to the library, which owns the loop. Optuna also
supports an *ask-and-tell* interface (`study.ask()` / `study.tell()`) where the
caller owns the loop.

On the **isolation**: the project's confirmatory design (overview §3/§4, domain
doc §5.4/§6.1) follows Raschka (2018, §3–4): hyperparameter selection uses only
training and validation from the exploratory phase, and the final evaluation
happens **once**, with hyperparameters frozen, on data never touched by the
search. White (2000) and Romano & Wolf (2005) formalize what happens otherwise;
the project's answer is to *eliminate* the search from the confirmatory path
rather than correct for it. The out-of-sample store
(`fact_oos_predictions`) is the sole source of truth the Step 6 tests read.

Forces at play:

- The project's port posture (ADR 1.5.0002) is minimal structural `Protocol`s
  exchanging primitives, with a fake and a contract test for every port.
- A callable crossing a port boundary is not a data contract: it cannot be
  serialized, its behavior cannot be pinned by a contract test, and whatever it
  closes over becomes an invisible part of the adapter's input.
- If the sweep wrote predictions into the same tables as the confirmatory runs,
  separating them at read time would depend on filtering by a label — and a
  filter mistake would silently contaminate the inference the project exists to
  produce.

## Decision

Two coupled decisions:

1. **Ask-and-tell port.** `HyperparameterSearch` exposes
   `create_study(seed, direction)`, `ask(space) -> SearchTrial`,
   `tell(trial_number, objective_value)` and `best_trial()`, exchanging only
   primitives and small frozen dataclasses. The trial loop — which fold, which
   trainer mode, what gets logged, when to stop — lives in the `RunTftSweep`
   use case.

2. **Structural isolation of the sweep.** `RunTftSweep` is **not injected with
   any port that writes results** — neither `PersistPredictions` nor
   `AnalyticsRepository` appears in its constructor, so the paths that produce
   `fact_oos_predictions` and `dim_run` rows are absent from its dependency
   graph. The one storage port it does receive, `MedallionStore`, is there to
   **read** the dataset pair `(processed, dataset_tft)`; that port does expose a
   generic `write`, so the absence of writes through it is not structural and is
   asserted instead (concept A10: the fake store records zero write calls). It
   runs the
   trainer in **fit-only** mode (empty test decision set), so no out-of-sample
   prediction is even produced; its objective is the early-stopping partition
   loss; and every tracked run carries `phase='exploratory'`.

   The ordering of the guarantees matters. Not having the dependency is the
   first layer and the only one a test can assert without depending on the
   implementation's discipline (a test asserting "the fake repository received
   no writes" is vacuous if the repository was never wired in). Fit-only mode is
   the second; the tag is the third.

## Alternatives considered

### Alternative A — Pass the objective callable to the adapter (`study.optimize`)

- **Description:** The port takes a callable and a trial count; the adapter runs
  Optuna's optimization loop.
- **Pros:** Least code; matches the library's most common usage; pruning
  integrations come for free.
- **Cons:** Moves orchestration — fold choice, trainer mode, logging, and the
  guarantee that only the validation partition is scored — inside the adapter,
  where the layer gate cannot see it and a fake cannot reproduce it. The
  contract test degenerates into "the adapter called my function". The most
  important property of this Stage's sweep (isolation) would be enforced by code
  living outside the application layer.
- **Why rejected:** It puts the invariant that matters in the least auditable
  place, to save a loop the use case can express in a few lines.

### Alternative B — Persist sweep predictions with a dedicated sweep cohort id

- **Description:** Let the sweep predict and persist out-of-sample rows under a
  separate `parent_sweep_id`, filtering them out when the confirmatory analysis
  reads.
- **Pros:** Exploratory results become queryable with the same tooling;
  comparisons across trials are easy.
- **Cons:** The separation between exploratory and confirmatory evidence would
  rest on every future reader applying the right filter. A single missed filter
  in Step 6 reintroduces exactly the selective-inference bias the design was
  built to eliminate — and it would be invisible, because the rows look like any
  other rows.
- **Why rejected:** A structural guarantee (the data does not exist) is
  categorically stronger than a procedural one (the data is labelled), and the
  cost is only convenience during exploration, where MLflow already serves.

### Alternative C — Custom sweep logic instead of Optuna

- **Description:** Implement random search directly, no dependency.
- **Pros:** One fewer dependency; random search is the recognized baseline
  (Bergstra & Bengio 2012).
- **Cons:** The domain doc pre-registers Optuna with its TPE sampler for the
  exploratory phase; reimplementing sampling would be new mechanism where a
  documented one exists, and would drift from what the project declared.
- **Why rejected:** The design was pre-registered; changing it here would be an
  undeclared deviation for no gain.

### Alternative D — Do nothing / defer the sweep to a later Stage

- **Why not acceptable:** The sweep is in the Stage's definition of done, and the
  human explicitly kept it in scope during alignment (issue #57, block B4).

## Consequences

### Positive

- The isolation invariant is enforced where it can be read and tested: in the
  use case, by a test asserting that no row reaches the analytics repository and
  that the trainer is called with an empty test set.
- The search port is fakeable with a deterministic sampler, so the contract test
  compares fake and real on behavior rather than on convergence.
- Swapping the search backend later touches one adapter.

### Negative

- The use case carries the trial loop, including failure handling per trial —
  code the library would otherwise own.
- Optuna's pruning callbacks are not available through this interface; a pruned
  search would need the port to grow (`should_prune`), under a new ADR.

### Neutral / trade-offs accepted

- Exploratory results live only in the experiment tracker, not in the medallion
  layers. Comparing trials means reading MLflow, which is what it is for.

## Implementation notes

- The fake sampler walks a deterministic grid over the declared dimensions so
  the contract test is reproducible without Optuna's stochasticity; the real
  adapter seeds its sampler from `create_study(seed=...)`.
- `SearchDimension` covers integer and float ranges with an optional log scale —
  the shapes the pre-registered space needs. Categorical dimensions are not
  introduced speculatively.
- `RunTftSweep` maps sampled values onto a frozen copy of the base
  `TftTrainingParams`; anything not in the space keeps its pre-registered value.

## References

- Related ADRs:
  [1.5.0002](./1_5_0002-experiment-tracker-port-shape.md) (minimal structural
  Protocol posture over primitives);
  [5.1.0002](./5_1_0002-dedicated-calibration-partition.md) (why the monitored
  split is not the calibration split);
  [4.1.0002](./4_1_0002-fact-oos-predictions-long-quantile-format.md) (the store
  the sweep deliberately does not write to);
  [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md).
- External: Akiba, T.; Sano, S.; Yanase, T.; Ohta, T.; Koyama, M. (2019).
  "Optuna: a next-generation hyperparameter optimization framework". *KDD* —
  including the ask-and-tell interface. Bergstra, J.; Bardenet, R.; Bengio, Y.;
  Kégl, B. (2011). "Algorithms for hyper-parameter optimization". *NeurIPS* 24
  (TPE). Bergstra, J.; Bengio, Y. (2012). "Random search for hyper-parameter
  optimization". *JMLR* 13, 281–305. Raschka, S. (2018). "Model evaluation,
  model selection, and algorithm selection in machine learning".
  arXiv:1811.12808, §3–4. White, H. (2000). "A reality check for data snooping".
  *Econometrica* 68(5), 1097–1126. Romano, J. P.; Wolf, M. (2005). "Stepwise
  multiple testing as formalized data snooping". *Econometrica* 73(4), 1237–1282.
- Conversation/issue: GitHub issue #57, alignment block B4 (2026-08-09).
