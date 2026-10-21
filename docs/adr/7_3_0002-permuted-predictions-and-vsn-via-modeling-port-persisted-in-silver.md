---
title: ADR 7.3.0002 — Permuted predictions and VSN weights produced once by an inference use case over a modeling-supplied port, permutation at tensor level in the trainer adapter, persisted in two new silver tables
description: Architecture Decision Record
when-use: Reference when asking how the family permutation is applied to the TFT input, why the permuted predictions and the VSN weights are persisted instead of computed in the refresh, where torch runs for 7.3, why the identity pass is persisted, or how the C6/P-H3-VSN premise is guarded in code
keywords: [adr, h3, permutation-importance, tensor-permutation, collate, dataloader, vsn, interpret-output, consumer-owned-port, silver, fact_permuted_predictions, fact_vsn_weights, identity-pass, reproduction, torch, modeling, inference]
status: accepted
created_at: 2026-10-18
updated_at: 2026-10-18
adr_id: 7.3.0002
decision: An inference use case RunPermutationInference resolves the confirmatory checkpoints, generates the family permutation plan in the inference domain and calls a consumer port satisfied by the modeling use case PredictTftAttributionFromCheckpoints, whose PfTftTrainer method loads the checkpoint bytes once and, through the same prediction dataset and a collate wrapper of the same dataloader, emits the identity grid, the grid with each family's whole encoder window swapped between the fold's test decisions for each of the K_p permutations, and the per-decision encoder VSN weights; identity and permuted grids go to a new silver table fact_permuted_predictions and the VSN weights to fact_vsn_weights, both written by analytics_store use cases; the refresh never runs torch; the VSN extractor is not an inference adapter.
context_stage: 7.3-explainability
bounded_context: inference
---

# ADR 7.3.0002 — Permuted predictions and VSN through the modeling port, persisted in silver

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 7.3 concept (issue #186), 2026-10-18. Closes items 1, 6
and 9 of the research findings of the issue. ADR 7.1.0001 (Neutral) left this
shape to the 7.3 concept: "the same rule applies (torch stays in modeling,
behavior through a consumer port)".

## Context

- **What is permuted** (inference domain doc §5.4, C1): for family f, the whole
  encoder window of all of f's features is swapped *between test samples*, the
  model and the rest of the input fixed. Encoder windows of consecutive
  decisions overlap, so the swap cannot be done on the panel rows; it has to be
  done on the sample tensors: `encoder_cont[i, :L, cols_f] ←
  encoder_cont[π(i), :L, cols_f]`.
- **Library facts** (pytorch-forecasting 1.8.0, read raw and checked by a
  zero-context verifier on 2026-10-18): the TFT indexes continuous inputs by
  the position of the name in `hparams.x_reals` (`x_cont[..., idx]`) and feeds
  the encoder VSN only `[:, :max_encoder_length]` and the decoder VSN only the
  decoder (known) variables (`_tft.py` L547–549, L576–590), so swapping the
  encoder block of f's columns is the whole perturbation; with no user scalers
  and no lags (our case — ADR 5.4.0006 fixes only the target normalizer), each
  non-target real gets a `StandardScaler` fitted on the training frame and
  reused, an affine map fixed per column (`_timeseries.py` L1257–1283; the
  verifier marked "parcial" only for the user-scaler/lag/`GroupNormalizer`
  branches that do not apply), so swapping normalized blocks equals swapping
  raw ones within a fold; `BaseModel.predict` uses a `DataLoader` as given
  (`_base_model.py` L1705–1714) and `to_dataloader` lets extra kwargs such as
  `collate_fn` override its defaults (`_timeseries.py` L2633–2664);
  `interpret_output(reduction="none")` returns per-sample encoder VSN weights
  averaged over the valid encoder steps (`_tft.py` L706–720, L811–848).
  Today `_emit` passes the `TimeSeriesDataSet` to `predict` with
  `mode="quantiles"` (`pf_tft_trainer.py` L500–519), and `predict` builds
  `to_dataloader(batch_size, train=False, num_workers)` itself.
- **The trainer's emission is the reference** (ADR 7.1.0001): `_emit` keeps the
  longest-decoder sample per decision; the 7.1 reproduction contract
  (ADR 7.1.0003; policy in the inference domain, ADR 7.2.0005) is strict in the
  same environment with the same batch, tolerance across.
- **Blinding:** computing the pinball of permuted predictions *is* the
  importance; it cannot happen before the r3 anchor (doc §7). Predictions may
  be produced and stored (doc §7: "treinar ... e ver predições não viola").
- **Cost** (technical 7.1 §7, E5): re-predicting the test of the 60 runs took
  ~20 min (≈ 20 s per run including the silver read); one run needs
  2 + 4·K_p passes (identity, VSN, permutations).
- The refresh path (`RefreshGold`) is stdlib + `arch`; torch is confined to
  modeling adapters (`modeling-no-torch-leak`, `inference-no-torch-leak`).

## Decision

`[decision:C] 7.3-PERM-WHERE — where the permuted predictions and the VSN come from`
`Escolha: computed once by an inference use case over a modeling-supplied port, persisted in two silver tables · Alternativas: on demand inside RefreshGold through a port to modeling; a torch adapter in inference; one table for both · Degrau: 1 (ADR 7.1.0001 rule; ADR 4.1.0001 "a table only for a fact with a consumer"; doc §7 blinding) e 5`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim até a primeira gravação real; depois, formato persistido`

1. **Modeling supplies behavior.** `TftCheckpointPredictor` gains
   `predict_attribution_from_checkpoint(..., permuted_columns, donors)` and its
   real `PfTftTrainer` implements it: bytes read once and hashed (C10 of 7.1),
   the prediction dataset by the same `_prediction_dataset`, then **one
   dataloader** built as `to_dataloader(train=False, batch_size, num_workers=0)`
   — the construction `predict` uses — passed to `model.predict(...)`; the
   identity pass uses it unchanged, each permuted pass uses the same dataloader
   with a `collate_fn` wrapper that, for every sample of decision d, replaces
   the encoder block of f's columns by the block of decision `donor_k(d)`.
   The `collate_fn` only sees its batch, so the donor blocks are **extracted
   beforehand** from the prediction dataset — one block per decision, from its
   longest-decoder sample — and the wrapper substitutes from that table; a
   donor in another batch is therefore exact (tested with `batch_size` < n
   decisions, and with the non-permuted columns compared bit for bit).
   The donor block of a decision is well defined (the encoder window ends at
   the decision, whatever the decoder length). `_emit` is generalized to
   receive the dataloader (built exactly as `predict` builds it) instead of the
   dataset — the 7.1 path passes the default one, so its output is unchanged —
   and the selection of the longest-decoder sample per decision stays
   `_emit`'s, shared. The VSN weights come from **one extra pass** of the
   identity dataloader with `mode="raw"` + `interpret_output(reduction="none")`
   (quantile and raw outputs are different `predict` modes), one vector per
   decision (longest sample), keyed by encoder variable name; same loaded
   model, same bytes.
   The modeling use case `PredictTftAttributionFromCheckpoints` mirrors
   `PredictTftFromCheckpoints` (same declaration checks, same `run_id`
   derivation, same allowlist and emission guard) and adds three guards:
   `donors` must be K_p permutations of the fold's test positions, the
   command's family partition must equal the registry's, and **every family
   column must be an `unknown` real of the encoder in the checkpoint** (in
   `time_varying_unknown_reals` of `dataset_parameters`, not in
   `time_varying_known_reals`) (C6 / P-H3-VSN
   premise; `FamilyFeatureKnownError`, nothing emitted).
2. **Inference owns the method.** `RunPermutationInference`
   (`inference/application/use_cases/`) per seed: resolves checkpoints
   (`CheckpointResolver`, 7.1), reads the run's silver test rows, generates the
   plan with the inference-domain `FamilyPermutationPlan` (ADR 7.3.0005),
   calls the consumer port `CheckpointAttributionPredictor`, checks the
   identity grid against the silver test rows with the 7.2 reproduction policy
   (mode by environment: strict in the 7.1 environment, tolerance across) —
   failure blocks the run before any write —, applies the guardrail
   (`QuantileForecast.from_raw`) and persists through two consumer ports. A
   write-ahead attribution manifest (pattern of ADR 7.1.0004) records, per run,
   the checkpoint sha256, the environment of the first write, the settings,
   the plan's identity as values — permutation seed, K_p, algorithm id, fold
   and n decisions — and the family partition with its `partition_hash`
   (no ad-hoc hash outside the shared identity VOs). Unit of resumption = run:
   complete rows → re-verified and skipped; partial rows →
   `PartialAttributionError` (pattern I7-d of 5.5). CLI: `attribute`.
3. **The identity pass is persisted** (`permuted_family = "none"`,
   `permutation_index = 0`), and d_{f,t} is computed against it, not against
   the trainer's silver rows: the two grids of a difference are always born in
   the same process, environment and dataloader (the principle of doc §5.5 for
   LOCO — "não pode misturar ambientes" — applied to permutation), whatever
   machine runs the attribution.
4. **Two silver tables** (analytics_store owns the schemas and writers, ADR
   4.1.0001 "reintroducing ... requires a new Stage and ... its own ADR"):
   - `fact_permuted_predictions`, long format as `fact_oos_predictions` (ADR
     4.1.0002): logical PK `(run_id, permuted_family, permutation_index,
     horizon, timestamp_utc, target_timestamp_utc, quantile_level)`, plus
     `model_version`, `asset`, `feature_set_name`, `decision_idx`,
     `permutation_seed`, `permutation_algorithm`, `partition_hash` (shared VO
     `FamilyPartitionHash` over `feature_set_hash` + the per-family lists; the
     r3 carries the same value as the literal `[h3.partition].partition_hash`,
     checked by a consistency test, and the refresh — which has no `Hasher`
     since #128 — only compares the column with the plan's literal and marks
     the permutation undefined on mismatch; alternative "inject a Hasher into
     RefreshGold" rejected, ADR 7.3.0005 H3-PARTITION), `value_raw`,
     `value_guardrail`, `guardrail_applied`, `schema_version`, `year`;
     partition `(asset, feature_set_name, run_id, year)` — `run_id` is a
     partition column so the per-run read is pushed down (the repository's
     `_build_predicates` only pushes partition columns); alternatives rejected:
     teach the repository to push down a non-partition column (a change of the
     4.2 adapter contract for every table, for one consumer) and read the whole
     table then filter by run (the ~8.7 M rows in memory that the per-run
     reduction exists to avoid); the docstrings of `AnalyticsRepository` and
     `ParquetAnalyticsRepository` move from 1..3 to 1..4 partition levels;
     append-only;
     `permuted_family ∈ {price, technical, sentiment, fundamental, none}`,
     `none ⇔ permutation_index = 0`;
   - `fact_vsn_weights`: PK `(run_id, timestamp_utc, variable)`, plus
     `model_version`, `asset`, `feature_set_name`, `decision_idx`, `family`
     (the registry family, or `none` for calendar, past target and relative
     time index), `weight`, `schema_version`, `year`; same partitioning.
   Writers: `PersistPermutedPredictions` and `PersistVsnWeights`
   (`analytics_store/application/use_cases/`), satisfying the inference
   consumer ports by duck typing (pattern of `PersistPredictions`, ADR 0.0.0053).
   `fact_oos_predictions` is untouched.
5. **No VSN adapter in inference.** The roadmap file
   `inference/adapters/out/pytorch_forecasting/vsn_weight_extractor.py` and the
   port `VsnWeightExtractor` leave the 7.3 list: the weights come from the
   same loaded model and the same identity pass as the predictions.

## Alternatives considered

### Alternative A — On demand inside `RefreshGold`
- **Description:** an evaluation port, satisfied by the modeling, called by the
  refresh to predict under permutation.
- **Cons:** torch, 60 checkpoints and ~2 500 passes on the refresh path (hours,
  not seconds); the refresh would depend on the machine (strict vs tolerance)
  and could not be rebuilt identically from silver; blinding becomes a matter
  of discipline instead of structure, because the same call that predicts
  would score.
- **Why rejected:** ADR 6.4.0005 (the generation is a pure function of silver,
  grid and plan) and rung 5.

### Alternative B — A torch adapter in the inference slice (roadmap text)
- **Why rejected:** ADR 7.1.0001 Alt. A — a second prediction recipe and a
  second `_emit`; the bytes would be read and hashed twice for predictions and
  VSN.

### Alternative C — Permute the panel rows (the frame) instead of the tensors
- **Why rejected:** encoder windows overlap; a row permutation would shuffle
  inside time and across decisions at once — the within-time shuffle that C1
  rejects (Hooker, Mentch & Zhou 2021).

### Alternative D — A custom forward loop over a stacked tensor of the fold
- **Pros:** the permutation is a single tensor index.
- **Cons:** batch composition differs from the trainer's, so even the identity
  pass would only reproduce silver by tolerance in the same environment;
  re-implements the output transformation of `predict`.
- **Why rejected:** the collate wrapper over the same dataloader keeps the
  identity pass on the trainer's exact path (strict in the same environment).

### Alternative E — Compare against the silver test rows (no identity rows)
- **Pros:** ~211 k fewer rows.
- **Cons:** d_{f,t} would mix environments whenever the attribution runs
  outside the 7.1 environment (e.g. on Linux).
- **Why rejected:** the extra pass is 1/(4·K_p + 1) of the cost and removes the
  environment from the estimand.

### Alternative F — Do nothing (no persisted permuted predictions)
- **Why rejected:** 8.1 would have to predict and score in one step, which is
  Alternative A.

## Consequences

### Positive
- The refresh stays stdlib + `arch`; H3 is rebuilt from silver.
- One recipe, one emission rule, one hash check of the bytes for predictions,
  permuted predictions and VSN.
- The C6 premise is checked against the real checkpoints, not only the registry.

### Negative
- ~8.7 M rows in `fact_permuted_predictions` for the real cohort (K_p = 10:
  4 × 10 × 211 540 + 211 540) and ~0.9 M in `fact_vsn_weights`.
- `PfTftTrainer` gains a third public method; modeling gains a use case that
  exists for a consumer; three new declared data edges (inference → modeling
  command DTO, inference → analytics_store command DTOs).

### Neutral / trade-offs accepted
- The attribution can run on the Windows CPU environment of 7.1 (strict
  identity) or on Linux (tolerance identity); the estimand does not change.

## References

- Related ADRs: [4.1.0001](./4_1_0001-analytics-store-silver-schema-per-table.md),
  [4.1.0002](./4_1_0002-fact-oos-predictions-long-quantile-format.md),
  [5.4.0006](./5_4_0006-explicit-train-fitted-target-normalizer.md),
  [7.1.0001](./7_1_0001-checkpoint-prediction-supplied-by-modeling-through-consumer-port.md),
  [7.1.0003](./7_1_0003-reproduction-contract-strict-same-environment-tolerance-across.md),
  [7.1.0004](./7_1_0004-checkpoint-resolution-before-load-and-write-ahead-inference-manifest.md),
  7.2.0005 (Stage 7.2),
  [7.3.0001](./7_3_0001-attribution-statistics-in-evaluation-gold-via-refresh-gold.md),
  [7.3.0005](./7_3_0005-h3-preregistration-r3-details.md).
- pytorch-forecasting 1.8.0 (tag `v1.8.0`): `models/temporal_fusion_transformer/_tft.py`,
  `models/base/_base_model.py`, `data/timeseries/_timeseries.py` (locators above).
- Hooker, G.; Mentch, L.; Zhou, S. (2021). *Statistics and Computing*, 31, 82. DOI: 10.1007/s11222-021-10057-z.
- Inference domain doc §5.2 (C6), §5.3, §5.4, §7.
- Issue: [#186](https://github.com/MarceloSanC/financial-forecasting/issues/186).
