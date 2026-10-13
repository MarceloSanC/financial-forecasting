---
title: ADR 7.1.0001 — Checkpoint prediction is supplied by the modeling slice through a port owned by inference; torch stays in modeling and the trainer's dataset recipe and emission rule are reused, not copied
description: Architecture Decision Record
when-use: Reference before adding any torch/pytorch-forecasting code to the inference slice, before writing a second prediction-dataset builder or a second emission rule for the TFT, when asking why the roadmap's `InferenceModelLoader` and `pf_inference_engine.py` do not exist, or where the inference runtime surface (CLI) lives
keywords: [adr, inference, checkpoint, consumer-owned-port, modeling, pytorch-forecasting, train-serve-skew, two-pipelines, emission-rule, dataset-parameters, cli, runtime-surface]
status: accepted
created_at: 2026-10-06
updated_at: 2026-10-06
adr_id: 7.1.0001
decision: The inference slice declares consumer-owned ports `CheckpointResolver` (run_id, model_version, checkpoint path and streamed sha256 per fold, no load) and `CheckpointGridPredictor` (raw grid per fold, partition, decision and horizon for an allowlist of run_id → sha256); they are satisfied structurally by new modeling use cases `ResolveTftCheckpoints` and `PredictTftFromCheckpoints`, which reuse the cohort's run identity, grid, splitter and artifact-directory rule and call new modeling ports-out `CheckpointLocator` (stdlib adapter) and `TftCheckpointPredictor` (`predict_from_checkpoint`), the latter implemented by the existing `PfTftTrainer` with the same prediction-dataset recipe and the same `_emit` rule the trainer uses for the test block; the inference application/domain import no torch, and its runtime surface is an `infer` subcommand of the existing CLI.
context_stage: 7.1-inference-engine
bounded_context: inference
---

# ADR 7.1.0001 — Checkpoint prediction supplied by modeling through a consumer-owned port

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 7.1 must predict the candidate's dense quantile grid from each trained
artifact (one checkpoint per fold × seed, `<artifacts_root>/tft/<run_id>/`,
concept 5.4 D9), for the `test` block (reproduction) and for the `calib` block
(input of the CQR in 7.2; domain doc inference §3.4). The roadmap text of 7.1
listed a port `InferenceModelLoader` and an adapter
`inference/adapters/out/pytorch_forecasting/pf_inference_engine.py`.

Forces:

- **The prediction recipe already exists and is the reference.** `PfTftTrainer`
  builds the prediction dataset from the training dataset (`from_dataset`, which
  is `from_parameters(dataset.get_parameters(), …)` in pytorch-forecasting
  1.8.0, `_timeseries.py` L1643–1681), cuts the frame at
  `max(decisions) + max_horizon + 1`, sets `min_prediction_length=1`, predicts
  with the restored best checkpoint, `batch_size = params.batch_size`,
  `num_workers=0`, CPU, and applies `_emit` (decision key from the returned
  index, `decoder_lengths` cut, longest window per decision, explicit filter of
  requested decisions). Every one of those details is load-bearing (ADR
  4.3.0001 off-by-one class; I15/I16 of concept 5.4). A second implementation is
  the "two pipelines" anti-pattern of train/serve skew (Huyen 2022, *Designing
  Machine Learning Systems* ch. 6 — skill `dmls-ch06-deployment-and-inference-decisions`,
  Task 1) and the second-definition failure that ADR 5.5.0004 removed for the
  training grid.
- **The checkpoint carries the fitted dataset state.** `BaseModel.from_dataset`
  stores `dataset.get_parameters()` (constructor kwargs with the fitted target
  normalizer, plus the fitted per-column `scalers`) and `on_save_checkpoint`
  writes it as `checkpoint["dataset_parameters"]` ("add dataset parameters for
  making fast predictions"; `_base_model.py` L1542–1543, L1556–1558, L1584–1585).
  A dataset built with already-fitted normalizer/scalers does not re-fit them
  (`check_is_fitted` guard, `_timeseries.py` L1168, L1256–1268). Verified on the
  pinned image by a zero-context verifier on 2026-10-06 (items 1–4: sustain;
  item 3 "partial" only because of branches that do not apply here — the
  normalizer is a `GroupNormalizer` (ADR 5.4.0006) and every real column has a
  fitted scaler from the training frame).
- **torch is confined to the modeling adapters** by the `modeling-no-torch-leak`
  contract, and slices exchange behavior only through consumer-owned ports
  (ADR 0.0.0053 item 2; its Consequences name the case: "When
  evaluation/inference arrive: define their ports in their own
  application/ports/out/, let [the supplier] satisfy them"). The precedent of a
  modeling **use case** satisfying another slice's port is `ReadTrainingGrid` →
  `evaluation.TrainingGridReader` (ADR 6.4.0009).
- **Knowledge needed to predict a fold is modeling knowledge:** fold geometry
  (`WalkForwardSplitter` + `CohortGeometry`), the run identity (`RunId` from the
  nine slots computed in `TrainTft._identity`), the training grid and its
  fingerprint (ADR 5.5.0004), the known/unknown typing (ADR 5.4.0004), the
  artifact-directory rule (D9 of concept 5.4).
- A "loader" port that returns a model object cannot cross the boundary without
  leaking a torch type into `inference.application`.

## Decision

1. **Consumer-owned ports in inference, resolution separate from prediction.**
   `inference/application/ports/out/checkpoint_resolver.py` declares
   `CheckpointResolver` ("for a frozen cohort and a seed, give me, per fold, the
   `run_id`, `model_version`, checkpoint path and streamed sha256 — without
   loading anything") and `checkpoint_grid_predictor.py` declares
   `CheckpointGridPredictor` ("for the same cohort and seed, an allowlist
   `run_id → expected sha256` and the partitions to predict (`test`, `calib`),
   give me per fold the **raw** grid `decision_idx → horizon → tuple aligned to
   quantile_levels`, the checkpoint's normalizer center/scale, the dataset
   timestamps and the inference settings"). The split exists so that every
   guard of the consumer (environment, `dim_run`, manifest sha256) runs before
   any unpickle (ADR 7.1.0004). The DTOs are the supplier's (data edge, ADR
   0.0.0053 item 3).
2. **Suppliers = two modeling use cases** (one use case per file, LAYOUT §7):
   `resolve_tft_checkpoints.py` (`ResolveTftCheckpoints`) and
   `predict_tft_from_checkpoints.py` (`PredictTftFromCheckpoints`), satisfying
   the ports by duck typing. Both run the cohort declaration checks through the
   function extracted from `RunConfirmatoryCohort._check_declarations`; the
   resolver also checks cohort completeness with `recorded_run_problems` over
   the TFT units; both derive each fold's `run_id` with the **same function**
   `TrainTft` uses (extracted from `_identity`), built from the **same**
   `CohortSpec → TrainTftCommand` construction the cohort runner uses (extracted
   from `RunConfirmatoryCohort._units`), and the artifact directory with the
   **same rule**. The predictor refuses a `run_id` outside the allowlist and
   asserts that the emission stays inside the requested decisions/horizons (the
   `_assert_emission_within_request` guard, generalized to any partition).
3. **Two new modeling ports-out.** `modeling/application/ports/out/checkpoint_locator.py`
   (`CheckpointLocator.locate`: directory listing + streamed sha256), whose real
   is the stdlib adapter `modeling/adapters/out/filesystem/checkpoint_locator.py`
   (`FilesystemCheckpointLocator`, no torch/lightning/pytorch_forecasting import,
   wired directly in the composition root, outside the lazy proxy); and
   `modeling/application/ports/out/tft_checkpoint_predictor.py`
   (`TftCheckpointPredictor.predict_from_checkpoint`), whose real is
   `PfTftTrainer`: read the file's bytes once, hash them with the stdlib streaming hash
   function that lives in the port module `checkpoint_locator.py` (both the
   locator and the trainer import it from there — no adapter-to-adapter import,
   rule 3b of `scripts/check_layout.py`), compare with the expected sha256 **before** the unpickle, load
   **from those bytes** (`io.BytesIO`), rebuild
   the prediction dataset with `TimeSeriesDataSet.from_parameters(model.dataset_parameters, …)`
   through **one** helper shared with `train_and_predict`, emit through the same
   `_emit`, threads and deterministic flag pinned to the trainer's — ADR
   7.1.0003). The checkpoint's declared
   inputs (known/unknown reals, decoder length, quantile levels) must equal what
   the caller passes; mismatch raises.
4. **No torch in inference's core.** An `inference-no-torch-leak` import-linter
   contract forbids `torch`/`lightning`/`pytorch_forecasting` in
   `inference.application` and `inference.domain` — the same perimeter as
   `modeling-no-torch-leak` (adapters may host a library, as the 7.3 roadmap
   foresees for VSN weights; in this Stage none does). The slice joins
   `hexagonal-layers`, `domain-purity`, `inward-only`, `store-no-storage-leak`
   and `bc-independence`.
5. **Runtime surface = CLI subcommand.** `python -m financial_forecasting.cli
   infer --data-root … --cohort … [--break-stale-lock] [--cross-environment "<justification>"]`,
   implemented in `inference/adapters/in/cli/inference_commands.py` and loaded by
   `importlib` (LAYOUT §8), with the cohort file read by the root `cli.py` (as
   for the 5.5 commands). Serving over HTTP is Stage 7.4.

## Alternatives considered

### Alternative A — Torch adapter inside the inference slice (roadmap text)
- **Description:** `inference/adapters/out/pytorch_forecasting/pf_inference_engine.py`
  loads the checkpoint, rebuilds the dataset and emits.
- **Pros:** The inference slice owns its whole path; matches the original
  roadmap file list.
- **Cons:** Duplicates the frame builder, the prediction-dataset recipe and
  `_emit` (or forces an adapter-to-adapter import across slices, which LAYOUT
  §3/ADR 0.0.0053 forbid); duplicates the run identity and fold geometry or
  imports modeling behavior into inference; any later fix to `_emit` would have
  to be made twice — the off-by-one of ADR 4.3.0001 is exactly the class of bug
  that a second copy re-opens.
- **Why rejected:** two pipelines for the same model output; the reproduction
  test would compare two codebases instead of proving one.

### Alternative B — `InferenceModelLoader` returning a model handle
- **Description:** a port that loads and returns the model; the use case calls
  `predict` on it.
- **Cons:** the handle is a torch object (or an opaque `Any`), so either torch
  leaks into `inference.application` or the port is untyped; prediction
  behavior would still need to live somewhere outside the port.
- **Why rejected:** violates `modeling-no-torch-leak`'s intent and LAYOUT §3.

### Alternative C — Put all of 7.1 in modeling (no inference slice yet)
- **Description:** a modeling use case predicts and persists the calib directly.
- **Pros:** fewest files.
- **Cons:** the roadmap places `RunInference` in BC `inference` and 7.2–7.4
  build on it; reproduction policy, calib emission and the inference record are
  inference concerns. Modeling would grow a responsibility the roadmap assigns
  elsewhere.
- **Why rejected:** contradicts the roadmap's BC assignment without a reason
  that the consumer-port pattern does not already solve.

### Alternative D — Rebuild the training dataset from the grid instead of reading `dataset_parameters`
- **Description:** rerun `build_datasets` with the fold's train indices and
  derive the prediction dataset from the re-fitted training dataset.
- **Pros:** no reliance on the checkpoint's pickled parameters.
- **Cons:** re-fits the normalizer and scalers — deterministic on the same grid,
  but it makes "the artifact" depend on re-executing training-side code, which is
  what the artifact exists to avoid, and it hides a mismatch between the
  checkpoint and today's code.
- **Why rejected:** the checkpoint is the artifact (domain doc §3.1); using its
  fitted state is the reproduction contract. The trainer path itself is
  unchanged semantically (`from_dataset` ≡ `from_parameters(get_parameters())`).

### Alternative E — No runtime surface (use case only, called by 8.1)
- **Why rejected:** concept 5.4 §1 assigned the "superfície de runtime" to 7.1;
  the functional verification on the real cohort and the human "Valide você"
  need a command; the 5.5 CLI is the precedent and costs one module.

## Consequences

### Positive
- One prediction recipe and one emission rule for the TFT: the reproduction test
  (ADR 7.1.0003) proves the artifact, not a re-implementation.
- `inference.application`/`domain` stay torch-free; the gate proves it.
- The run identity of the calib rows is the training run's by construction.

### Negative
- `modeling` grows two ports, two use cases, a stdlib adapter and one adapter
  method that exist for a consumer; `PfTftTrainer` now satisfies two ports.
- New declared data edges `inference.application → modeling.application`
  (DTOs, `CohortSpec`, and the probe constants `CODE_KEYS`/`DIRTY_KEY`/`THREADS_KEY`) and `→ analytics_store` (`PersistPredictionsCommand`,
  `QuantileForecast`).

### Neutral / trade-offs accepted
- Stage 7.3 will need predictions under permuted inputs and VSN weights; the
  same rule applies (torch stays in modeling, behavior through a consumer port);
  the 7.3 concept decides the shape. The roadmap's 7.3 file
  `inference/adapters/out/pytorch_forecasting/vsn_weight_extractor.py` is to be
  reviewed in that concept under this ADR.
- The finding of technical 5.4 §7 (runtime image carries the deep-learning
  stack) is answered: the inference runs from the same CLI/image, so the stack is
  legitimate at runtime; `optuna` stays (the `sweep` subcommand lives in the
  same CLI).

## Implementation notes

- Shared helpers to extract, not copy: run identity (`TrainTft._identity`),
  artifact directory (`artifacts_root / "tft" / run_id`), emission guard
  (`_assert_emission_within_request`), cohort declaration checks
  (`RunConfirmatoryCohort._check_declarations`), `CohortSpec → TrainTftCommand`
  (the `tft(seed)` closure of `RunConfirmatoryCohort._units`),
  prediction-dataset construction and `_emit` in `pf_tft_trainer.py`.
- The lazy proxy in `composition_root.py` (`_LazyPfTftTrainer`) forwards the new
  `predict_from_checkpoint` method so `import torch` still happens only on first
  prediction; the locator is not behind the proxy at all.

## References

- Related ADRs: [0.0.0053](./0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md),
  [5.5.0004](./5_5_0004-single-training-grid-warmup-trim.md),
  [6.4.0009](./6_4_0009-realized-from-modeling-training-grid-via-consumer-port.md),
  [5.4.0006](./5_4_0006-explicit-train-fitted-target-normalizer.md),
  [4.3.0001](./4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md),
  [7.1.0002](./7_1_0002-calib-predictions-in-fact-oos-predictions-idempotent-completion.md),
  [7.1.0003](./7_1_0003-reproduction-contract-strict-same-environment-tolerance-across.md),
  [7.1.0004](./7_1_0004-checkpoint-resolution-before-load-and-write-ahead-inference-manifest.md)
- External: pytorch-forecasting 1.8.0 `data/timeseries/_timeseries.py`
  L1623–1745, `models/base/_base_model.py` L1535–1590 (read on the pinned image,
  2026-10-06); Huyen, C. (2022) *Designing Machine Learning Systems*, ch. 6.
- Conversation/issue: [#153](https://github.com/MarceloSanC/financial-forecasting/issues/153)
  (Passo 1b, point 5 "solução mais direta").
