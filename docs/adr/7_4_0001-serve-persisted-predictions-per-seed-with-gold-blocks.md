---
title: ADR 7.4.0001 — The inference API serves the candidate's persisted test predictions per seed, with conformal and H3 blocks read from the gold and marked available or unavailable
description: Architecture Decision Record
when-use: Reference when asking why the API does not run the model, why it lists seeds instead of averaging them, how a request binds to a run, why a missing point is a 404 while a missing gold is not, which conformal variant it serves, how it reads the gold (and why that edge goes evaluation → inference), or how the served data would be kept fresh
keywords: [adr, inference-api, serving, batch-prediction, online-prediction, persisted-predictions, seeds, quantile-averaging, conformal, gold, availability, not-found, consumer-owned-port, acyclicity, freshness]
status: accepted
created_at: 2026-10-21
updated_at: 2026-10-21
adr_id: 7.4.0001
decision: POST /inference/run reads, on demand, the candidate's split = "test" rows already in silver (written by the cohort trainer, whose reproduction from the checkpoint Stage 7.1 proved) without loading any checkpoint, binds each requested (seed, horizon) to the single test run of the cohort with a row at the decision date, serves one member per seed without cross-seed aggregation, applies the record-variant correction of the same (fold_raw, seed, horizon, pair) unit through PairCorrection.limits, attaches the H3 reading from the gold, answers 404 "não há dados para o pedido solicitado" when any requested (seed, horizon) has no row, marks each gold-derived block (or interval) unavailable with a reason — never an error — when the generation is missing, BLOCKED, lacks the preregistration block, belongs to another candidate or lacks the unit, raises an ApplicationError on inconsistent data, and reads the gold through an inference-owned port satisfied by an evaluation use case, an edge from evaluation to inference declared as an exception to ADR 0.0.0053 items 2–3 for acyclicity.
context_stage: 7.4-inference-api
bounded_context: inference
---

# ADR 7.4.0001 — Serve persisted predictions per seed, gold blocks with availability

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 7.4 concept (issue #201), 2026-10-21. Items 1, 2, 4, 5 and
8 were validated by the human in the Stage kickoff (RUNBOOK Passo 1b, blocks
B1, B2 and B3); the remaining items close by evidence or convention (skill
`evidence-resolution`). Revised after Checkpoint A (three independent
reviewers) before the concept was approved.

## Context

- The candidate's `split = "test"` rows in `silver.fact_oos_predictions` were
  written by the confirmatory-cohort trainer (Stage 5.5). Stage 7.1 re-predicts
  the test block from the checkpoint **in memory** and proves bit-for-bit
  reproduction in the same environment (ADR 7.1.0003, which rejected
  re-persisting the test block); 7.1 writes only the `calib` partition (ADR
  7.1.0002). The real cohort has 60 `tft_quantile` runs (folds "0"–"5" × seeds
  1–10) and, per seed, 1511 test decisions at h+1 and 1505 at h+7; the last 6
  sessions have h+1 only. Filtered by `split = "test"`, each (seed, horizon,
  date) has exactly one run; unfiltered, 82.6 % of test dates also carry a
  `calib` run of the next fold (measured 2026-10-21 on
  `data/cohorts/aapl/silver/`, prediction columns only).
- The 7.1 prediction port (`CheckpointGridPredictor`) predicts whole
  partitions per fold of a seed; it has no single-point mode.
- The conformal corrections (ADR 7.2.0003; two rows — one per tail — per
  (`fold_raw`, seed, horizon, pair, variant) unit) and the H3 tables (ADR
  7.3.0001) live only in the gold, published by `RefreshGold`; the real
  generation is published by Stage 8.1. A generation can be missing
  (`GoldManifestNotFoundError`), `BLOCKED` (its manifest lists no
  confirmatory table, so reading one raises `GoldGenerationCorruptError`),
  `COMPLETED` with zero-row tables when the preregistration has no
  `[conformal]`/`[h3]` block (null parameters in the manifest), or corrupt;
  both errors subclass `ApplicationError`. The generation's candidate is
  `manifest.parameters.candidate`.
- The inference domain doc §6 says the API "serve o que foi produzido pelas
  Stages 7.1–7.3; ela não recalibra, não re-treina e não calcula atribuição";
  §2.3 says seeds are replicas aggregated only as losses and coverages.
- Concept 7.2 D9 and the roadmap block of 7.4 fixed how 7.4 reads the gold: a
  consumer port in inference, the reader in evaluation (the `gold_schema` owns
  name, key and columns), "direção de produção só evaluation → inference".
  ADR 0.0.0053 items 2–3 say the opposite for data edges in general: "The
  supplier does not import the consumer", and what crosses is the supplier's
  inbound-port DTOs. An evaluation → inference edge already exists
  (`refresh_gold → calibrate_conformal`, ADR 7.2.0003 item 3).
- The confirmatory cohort is frozen: new sessions change the dataset content
  fingerprint, whose hash includes the timestamps
  (`DatasetContentFingerprint`), and the cohort runner refuses it
  (`DatasetMismatchError`), as does `RefreshGold`
  (`GridFingerprintMismatchError`).

## Decision

1. **Serve what is persisted.** `[decision]` B1 (human, 2026-10-21). The use
   case `ServeInference` reads `dim_run` and `fact_oos_predictions` through
   the inference `SilverTableReader` port; no checkpoint, `torch`, `lightning`
   or `pytorch_forecasting` is reached from the route (the
   `inference-no-torch-leak` contract is extended to the router package and a
   subprocess test checks `sys.modules` after a request). The roadmap block of
   7.4 drops the checkpoint prediction ports and the `calib` partition.
2. **One member per seed, no aggregation.** `[decision]` B2 (human). Each
   requested seed is served with its own rearranged grid and its own
   intervals. Averaging quantiles across seeds would serve an ensemble that
   no Stage evaluated for H1 (inference domain doc §2.3; ADR 0.0.0010 item 5
   — the project's inference; Fakoor et al. 2023 is context, see Alternative
   C).
3. **Binding.** `[decision:E]` The decision date matches the date part of the
   stored `timestamp_utc`. For each requested (seed, horizon), the served run
   is the seed's run under `parent_sweep_id = cohort_id` and the scope's
   `model_version` whose `split = "test"` rows include that date and horizon
   (test blocks tile the tail into disjoint blocks, ADR 5.1.0001). Zero runs
   for the point → not found (item 4). Zero runs of the cohort, a scope seed
   with no run, more than one run for the point, a grid missing or repeating
   a level of the scope, or target dates that differ across seeds for a
   horizon → `ApplicationError` (inconsistent data or a wrong `data_root`
   never becomes "no data"). A `ValueError` raised while building DTOs or VOs
   from read data is re-raised as `ApplicationError`.
4. **Missing data is a 404 of the whole request.** `[decision]` B1/B3
   (human: "se pedir algo que ainda não tem, devolve que não há dados para o
   pedido solicitado"). Asset other than the cohort's, a horizon or seed
   outside the cohort, or a decision date without a test row for any
   requested (seed, horizon) raises `NoServedDataError(NotFoundError)`,
   whose message starts with "não há dados para o pedido solicitado" and
   names what is missing. A client wanting only h+1 in the last sessions asks
   only for h+1.
5. **A missing gold is not an error.** `[decision]` B3 (human). The reader
   catches **only** `GoldManifestNotFoundError` (no generic
   `ApplicationError` catch) → both blocks `unavailable` ("gold não
   publicado"), and checks `manifest.status` **before** reading any table:
   `BLOCKED` → both blocks `unavailable`; `COMPLETED` with null
   `conformal_parameters` → conformal `unavailable`; with null
   `h3_parameters` → explainability `unavailable`. `ServeInference` (not the
   reader, which does not receive the `model_version`) compares
   `ServingGold.candidate` with the served `model_version`: different → both
   blocks `unavailable`. In every case the answer is 200, the grid is served
   and each case has its own reason. A
   corrupt generation propagates as `ApplicationError` (500), so corruption
   is never silenced.
6. **Conformal block.** `[decision:E]` For each symmetric pair of the grid,
   the correction of the record variant (`ConformalVariant.SPLIT_CQR`) of the
   unit (`fold_raw` of the served run — the `dim_run` string, never converted
   — seed, horizon, pair), applied by `PairCorrection.limits` to the
   rearranged grid, with no rearrangement of the output (inference domain doc
   §4.5, §4.8, §4.13; ADR 0.0.0008): an interval may come out crossed and
   pairs may not nest, and the payload neither fixes nor hides it. Interval
   states: both tails `ok` → `ok`; a tail `undefined` or `error` →
   `unavailable` with the gold's status and reason; no row for the unit →
   `unavailable` ("unidade ausente na geração gold"); exactly one tail
   missing → `ApplicationError` (the builder always writes both). NexCP
   (sensitivity) and the measured conformal coverages stay in the gold and
   the report: coverage is measured over the test, not an attribute of one
   interval (Bracher et al. 2021 identify an interval by its nominal level and
   report empirical coverage apart).
7. **Gold read through a consumer port; evaluation → inference edge as a
   declared exception.** `[decision:C] 7.4-EDGE — direction of the gold-read data edge`
   `Escolha: evaluation imports the inference port's DTOs · Alternativas: inference imports an evaluation result DTO (ADR 0.0.0053 items 2–3); primitive mappings with no edge; a Parquet reader in inference · Degrau: 1`
   The inference port `ServingGoldReader.read(*, asset, cohort_id) ->
   ServingGold` returns inference-owned DTOs; the real is the evaluation use
   case `ReadServingGold`, which reads the live generation through the
   existing `GoldGenerationReader` (manifest first,
   `GoldGeneration.from_stored`), selects columns through `gold_schema` and
   its typed cell readers, rebuilds `±inf` from the stored flags, and fills
   the labels (ADR 7.4.0002 item 4). One declared data edge in
   `bc-independence`: `evaluation.application.use_cases.read_serving_gold →
   inference.application.dtos.serving_gold`. This **inverts** ADR 0.0.0053
   items 2–3 on purpose: the direction they prescribe (inference →
   evaluation) would close a cycle with the existing evaluation → inference
   edge, and the slices must stay acyclic. The exception was already decided
   (concept 7.2 D9; roadmap 7.4) and is recorded here, in LAYOUT §7 and in an
   amendment note of ADR 0.0.0053. Primitive mappings would move the gold
   column names into inference (a second definition), so they lose.
8. **Freshness belongs to another pipeline.** `[decision]` B1 (human: "a
   solução para ficar sempre atualizado é ter um scheduler que roda de
   maneira agendada"). The API neither ingests nor predicts nor publishes;
   it serves whatever cohort it is configured with. Serving new dates needs
   another cohort (or cohort revision) with its own data, training or
   prediction and gold under another `data_root`, kept by a scheduled job —
   a separate issue. A job writing new data into the confirmatory cohort's
   `data_root` would break the frozen cohort and the 8.1 refresh.

## Alternatives considered

### Alternative A — Online prediction from the checkpoint per request
- **Description:** load the fold's checkpoint and predict the requested
  decision on each call, as model servers do (Open Inference Protocol
  `POST v2/models/<name>/infer`; MLflow `/invocations`).
- **Pros:** can, in principle, predict dates outside the persisted
  partitions; "run" in the route would be literal.
- **Cons:** the 7.1 port predicts whole partitions per fold of a seed, so a
  default request would load at least one checkpoint per seed (10) and the
  deep-learning stack into the web process; for every persisted date the
  number would equal the stored one (ADR 7.1.0003), and in another process or
  environment the reproduction contract only promises tolerance — a second
  prediction path next to the evaluated one (the "two pipelines" risk of ADR
  7.1.0001). Dates outside the cohort have no new data to predict from.
- **Why rejected:** the query universe is finite and already persisted; the
  project's serving skill names "online when batch would do" as a failure
  mode (Huyen 2022, ch. 7, §"Batch Prediction Versus Online Prediction"; skill
  `dmls-ch06` Task 1); Sandve et al. 2013, Rule 1 ("For Every Result, Keep
  Track of How It Was Produced") favours serving the row whose provenance is
  recorded. Human decision B1.

### Alternative B — Hybrid: persisted rows, online fallback for the rest
- **Description:** serve the persisted row when it exists, predict online
  otherwise.
- **Pros:** covers both cases.
- **Cons:** all of Alternative A's costs, and the fallback has no input: a
  date outside the frozen cohort has no features in its dataset, and adding
  them changes the dataset fingerprint the cohort is frozen on.
- **Why rejected:** freshness needs a new cohort or revision, not a fallback
  inside the API (item 8).

### Alternative C — Average the seeds into one grid
- **Description:** serve the point-wise mean of the seeds' quantiles.
- **Pros:** one grid per horizon; smaller payload.
- **Cons:** it is quantile averaging, an aggregation that Fakoor et al. 2023
  §2.3 show "often lead[s] to markedly different outcomes" from probability
  averaging, and (Prop. 4, after Lichtendahl et al. 2013) sharper than it,
  where "sharpness is only a desirable property if it does not come at the
  expense of calibration"; no Stage evaluated the calibration of such an
  ensemble, and the conformal corrections are per seed.
- **Why rejected:** human decision B2; doc §2.3.

### Alternative D — Partial answer (serve what exists, skip the rest)
- **Description:** answer 200 with the horizons and seeds that exist.
- **Pros:** the last sessions answer h+1 without a new request.
- **Cons:** a client that asked for h+7 gets silence about it unless it
  checks the list; the request semantics become "best effort".
- **Why rejected:** human decision (missing data → "não há dados para o pedido
  solicitado"); the client can ask for the horizons it wants.

### Alternative E — Missing gold as 404, 409 or 503
- **Description:** refuse the whole request while the gold is not published.
- **Pros:** one less state in the payload.
- **Cons:** the grid exists and is useful before 8.1; RFC 9110 defines 503
  for "temporary overload or scheduled maintenance" (§15.6.4) and 409 for "a
  conflict with the current state of the target resource" (§15.5.10) —
  neither describes "not yet published". Serving the block as unavailable
  inside a 200 is the project's reading of §15.3.1 (the content of a 200 to
  POST represents "the status of, or results obtained from, the action").
- **Why rejected:** human decision B3.

### Alternative F — A Parquet reader of the gold inside inference
- **Description:** inference reads `gold/.../current/*.parquet` directly.
- **Pros:** no cross-slice edge.
- **Cons:** a second definition of table names, keys, columns and of the
  generation assembly (`GoldGeneration.from_stored`), and of the labels.
- **Why rejected:** concept 7.2 D9; ADR 6.5.0005 (single assembly).

### Alternative G — Do nothing (no API)
The overview §3 puts "API de inferência fina (FastAPI) + explicabilidade" in
scope and the roadmap closes Step 7 with it.

## Consequences

### Positive
- The API serves exactly the evaluated object, with its run id, fold and
  seed, and needs no deep-learning stack or checkpoint at runtime.
- Before 8.1 the API already serves the grid; after 8.1 the gold blocks turn
  `available` with no code change.
- Rules keep one owner: the conformal rule (`PairCorrection.limits`), the gold
  schema, assembly and cell readers, the labels.

### Negative
- Dates outside the cohort's test partitions are 404 until another cohort is
  kept fresh by a scheduled job.
- The payload carries 10 members per horizon (larger than one averaged grid).
- One more declared data edge evaluation → inference, against the default
  direction of ADR 0.0.0053.
- The gold generation is read whole on every request (no cache); measured at
  the Stage exit against a generation of real size (concept D15).

### Neutral / trade-offs accepted
- The route keeps `/inference/run` from the roadmap although it runs no model.
- A request racing the gold publication can see the residual window of ADR
  6.4.0005 (no `current/` between the two folder swaps); accepted while
  refreshes are manual, and handed to the scheduled-job issue.

## Implementation notes

- Filter the silver read by its partitions (`asset`, `feature_set_name`,
  `year` of the decision) and then by `run_id`, `split = "test"` and decision
  date; join the gold unit by `fold_raw == dim_run.fold`.
- Contract suite `[fake, real]` for `ServingGoldReader`; real leg =
  `ReadServingGold` over `ParquetGoldStore` in `tmp_path`; the port's and the
  use case's `read` annotations must be textually equal
  (`check_port_coverage.py`).

## References

- Related ADRs: 0.0.0008, 0.0.0010, 0.0.0053, 5.1.0001, 6.4.0005, 6.5.0005,
  7.1.0001, 7.1.0002, 7.1.0003, 7.2.0003, 7.3.0001, 7.4.0002.
- Inference domain doc §2.3, §4.5, §4.8, §4.13, §6; concept 7.2 D9; concept
  7.3 §8; roadmap §7.4.
- Huyen, C. (2022). *Designing Machine Learning Systems*. O'Reilly. Ch. 7
  "Model Deployment and Prediction Service", §"Batch Prediction Versus Online
  Prediction". (ADR 7.1.0001 cites it as "ch. 6": locator erratum.)
- Sandve, G. K., Nekrutenko, A., Taylor, J., Hovig, E. (2013). Ten Simple
  Rules for Reproducible Computational Research. *PLoS Comput Biol* 9(10):
  e1003285. doi:10.1371/journal.pcbi.1003285.
- Fakoor, R., Kim, T., Mueller, J., Smola, A. J., Tibshirani, R. J. (2023).
  Flexible Model Aggregation for Quantile Regression. *JMLR* 24, §2.3, Prop. 4.
- Bracher, J., Ray, E. L., Gneiting, T., Reich, N. G. (2021). Evaluating
  epidemic forecasts in an interval format. *PLoS Comput Biol* 17(2):
  e1008618. doi:10.1371/journal.pcbi.1008618.
- Fielding, R., Nottingham, M., Reschke, J. (2022). RFC 9110 *HTTP
  Semantics*, §15.3.1, §15.5.10, §15.6.4.
- Comparable projects: Amazon Forecast (`CreateForecast` + `QueryForecast`;
  batch then query, with a publication status); Open Inference Protocol
  (KServe V2) and MLflow model serving (online, counterpart).
- Issue #201 (Passo 1b, B1–B3; `## Referências`).
