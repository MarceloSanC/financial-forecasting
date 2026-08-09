---
title: ADR 5.4.0003 — torch and pytorch-forecasting are core dependencies resolved from the CPU wheel index, with the real TFT smoke test running in CI (diverging from the optional-ML-extra posture of 3.2.0002)
description: Architecture Decision Record
when-use: Reference before moving torch into an optional extra, before changing the wheel index, before adding a skipif to the TFT smoke test, or when enabling ROCm for the confirmatory training environment
keywords: [adr, torch, pytorch-forecasting, dependencies, cpu-index, uv, ci, smoke-test, skipif, rocm, optional-extra]
status: accepted
created_at: 2026-08-09
updated_at: 2026-08-09
adr_id: "5.4.0003"
decision: torch, lightning, pytorch-forecasting and optuna enter the main dependencies with torch resolved from the explicit CPU wheel index, and the real TFT smoke test runs in CI without skipif — diverging from ADR 3.2.0002 because the TFT is the object of study, not an auxiliary scorer
context_stage: 5.4-tft-trainer
bounded_context: modeling
---

# ADR 5.4.0003 — torch as a core CPU dependency with a real smoke test in CI

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

The project already has a posture for heavy ML dependencies: ADR 3.2.0002 put
`torch` and `transformers` in an optional `sentiment` extra, made the FinBERT
adapter import them lazily, and marked the real adapter's tests with `skipif` so
CI (`uv sync --extra dev`) never installs them. Stage 3.2 later recorded the
consequence honestly in its post-execution section: the adapter body sits at 0%
coverage in CI, accepted because the formula that mattered was extracted into a
pure, torch-free function and covered there.

Stage 5.4 is not in the same situation:

- **The TFT is the object of study.** The project's question is whether this
  model produces calibrated predictive distributions. "The TFT trains in
  quantile mode with the dense grid" is the Stage's central acceptance criterion,
  not a supporting detail.
- **The pure-logic escape does not apply.** In 3.2 the decisive logic
  (`P(pos) − P(neg)`) was arithmetic that could live outside the adapter. Here
  the decisive behavior *is* the training loop: dataset typing, early stopping,
  best-checkpoint restoration, quantile emission. None of it can be verified
  without the library.
- **Cost is different too.** ADR 3.2.0002 names two costs, and the operative one
  was the library itself: "keep torch out of the CI's default install. The CI
  runs `uv sync --extra dev`. If torch were in `dev`, the CI would download torch
  on every run" — with the ~400 MB of FinBERT weights as the second. Here there
  are no pretrained weights, so only the first cost applies — and it is the one
  the CPU index addresses. And the default PyPI resolution of `torch` on Linux is the CUDA
  variant, several GB — which would make CI installation the dominant cost and
  is the real reason a naive "just add torch" fails.
- **`uv` supports an explicit index per package.** `[[tool.uv.index]]` with
  `explicit = true` plus `[tool.uv.sources]` pins `torch` to
  `https://download.pytorch.org/whl/cpu`, resolving the CPU wheel (~200 MB)
  everywhere by default.
- **The confirmatory training environment is AMD ROCm** (overview ASSUM-2), but
  that environment belongs to Stage 5.5 and is not exercised here.

## Decision

`torch`, `lightning`, `pytorch-forecasting` and `optuna` enter the main
`dependencies`. `torch` is resolved from an explicit CPU wheel index declared in
`pyproject.toml`, so the default resolution — devcontainer, CI and any fresh
checkout — is the CPU build.

The TFT smoke test runs the **real** adapter in CI, without `skipif`: a minimal
model over a short synthetic panel for a couple of epochs, CPU-only. The
end-to-end test (concept A16) likewise wires the real adapter, together with the
real MLflow tracker.

Enabling ROCm for the confirmatory training run is declared out of scope for
this Stage and belongs to 5.5, which will either override the index in that
environment or introduce the conflicting-extras arrangement of Alternative B.

## Alternatives considered

### Alternative A — Follow 3.2.0002: optional `tft` extra, lazy import, skipif in CI

- **Description:** Keep the FinBERT posture verbatim for the TFT.
- **Pros:** Consistent with an existing ADR; CI installation stays small; no
  index configuration.
- **Cons:** The Stage's central acceptance criterion would never be verified
  automatically — the one adapter in the project whose correctness the whole
  research question depends on would be the one without an automated net. Every
  later Stage that touches the trainer (5.5, 7.1) would inherit a red-free CI
  that proves nothing about it. Stage 3.2's own post-execution note shows what
  this costs: a real gap (the label-order remap) survived precisely because the
  only test exercising it was skipped.
- **Why rejected:** The reason 3.2.0002 works is that the decisive logic could
  be extracted torch-free. Here it cannot, so the same structure buys the same
  installation savings while giving up the guarantee that mattered.

### Alternative B — Conflicting extras (`cpu` / `rocm`) as documented by uv

- **Description:** Declare `cpu` and `rocm` optional extras, each pinning
  `torch` to its own index, with `[tool.uv]` conflict declarations.
- **Pros:** Both environments first-class; no override needed for the ROCm run.
- **Cons:** Every entry point that installs dependencies (`make setup`, the
  Dockerfile, the devcontainer, CI) must choose an extra explicitly, and a
  forgotten flag yields an environment with no `torch` at all — a failure mode
  that appears at runtime rather than at install time. The ROCm path is not
  exercised until 5.5, so the complexity would be carried unvalidated.
- **Why rejected now:** Right-sized for the Stage that actually needs both
  builds. Recorded here as the intended path when 5.5 enables ROCm.

### Alternative C — Add `torch` from the default index (CUDA build)

- **Description:** Plain `torch` in dependencies, no index configuration.
- **Pros:** Simplest declaration.
- **Cons:** Pulls the CUDA wheel and its NVIDIA runtime dependencies (several
  GB) on Linux, on machines and CI runners that have no GPU; installation time
  would dominate every job.
- **Why rejected:** Cost with no benefit — nothing in this Stage runs on CUDA.

### Alternative D — Do nothing / defer the dependency decision to the technical

- **Why not acceptable:** The choice determines whether the Stage's central
  acceptance criterion is machine-verified. That is a concept-level decision.

## Consequences

### Positive

- The candidate model's training path is covered by an automated test that runs
  on every pull request, including quantile emission, early stopping and
  checkpoint restoration.
- Coverage of the adapter is real rather than structurally impossible. (Note
  that the project's automated coverage gate is aggregate — `fail_under = 90` in
  `[tool.coverage.report]`; per-file coverage is measured and reported in the
  Stage report, not enforced by a script. What this decision buys is that the
  adapter's lines are actually executed, so the per-file number is meaningful
  instead of structurally zero.)
- The contract suite can run both legs (fake and real) in CI, as Stages 5.2 and
  5.3 do for their adapters.

### Negative

- CI installation grows by `torch` (CPU) plus `lightning`, `scipy` and
  `scikit-learn` — pulled in by `pytorch-forecasting`. Job time increases; the
  measured delta is recorded in the Stage report and the `uv` cache is enabled
  in the workflow to contain it.
- Every developer environment now installs `torch` by default, including those
  that only touch unrelated bounded contexts.
- The declared CPU index means the ROCm environment needs an explicit override,
  which is a footgun until 5.5 formalizes it.

### Neutral / trade-offs accepted

- This ADR **narrows** 3.2.0002 rather than superseding it, and the narrowed
  clause is named: "The CI keeps running `uv sync --extra dev` and never
  installs torch". After this Stage the CI *does* install `torch`, so that
  clause no longer holds and the consequence "CI stays fast and torch-free" is
  partially void. What survives intact is 3.2.0002's actual decision: FinBERT's
  `transformers` and the ~400 MB of weights stay behind the optional
  `sentiment` extra, the adapter keeps its lazy import, and its live test stays
  skipped. The extra now gates `transformers` and the weights rather than
  `torch`.
- Consequence to clean up in the same Stage: the comments in `pyproject.toml`
  and `.importlinter` that assert "o CI roda `uv sync --extra dev` (sem torch)"
  become factually wrong and are corrected here. A stale comment asserting an
  invariant the build no longer has is worse than no comment.
- The two ADRs encode the same principle applied to different stakes — the
  object of study gets an automated net; an auxiliary scorer whose decisive
  logic is extractable does not need one.

## Implementation notes

- `pyproject.toml`: `[[tool.uv.index]] name = "pytorch-cpu", url =
  "https://download.pytorch.org/whl/cpu", explicit = true` and
  `[tool.uv.sources] torch = [{ index = "pytorch-cpu", marker =
  "platform_system != 'Darwin'" }]`. Requires uv ≥ 0.5.3. The platform marker is
  not optional: the CPU index publishes no macOS wheels, so a universal lock
  without it fails to resolve on the darwin split.
- **The install path must use the project interface.** `tool.uv.sources` is
  honoured by `uv lock`/`uv sync`/`uv run` and **ignored** by `uv pip`. Today
  `Makefile` (`setup`, `install`) and both `Dockerfile` stages install with
  `uv pip install -e ".[dev]"`, and the `Dockerfile` does not even copy
  `uv.lock` — so the declaration above would have no effect where the project
  actually runs, and the image would install the CUDA build. Migrating those
  call sites to `uv sync --locked` (with `uv.lock` copied into the image) is
  part of this decision, not a follow-up: without it the ADR is inert.
- Verification must probe **inside the image**, not only through `uv run` on the
  host — a host-only check passes while the container stays CUDA.
- Pin by minor with `uv.lock` fixing the patch, following the posture of
  `exchange-calendars`/`lightgbm`.
- The composition root still wires the adapter through a lazy proxy
  (`_LazyPfTftTrainer`): importing `torch` at module import time would slow every
  process that only needs an unrelated use case. Lazy import here is about
  startup cost, not about the dependency being optional.
- The smoke test must stay fast (target: seconds). If it exceeds ~60 s it is
  marked `slow` and the deviation is recorded.

## References

- Related ADRs:
  [3.2.0002](./3_2_0002-ml-deps-optional-extra-and-lazy-import.md) (the optional
  ML extra posture this ADR deliberately diverges from, without superseding it);
  [1.2.0011](./1_2_0011-coverage-gate-as-foundational-fitness-function.md);
  [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md).
- External: `uv` documentation, "Using uv with PyTorch" (explicit indexes and
  `tool.uv.sources`); `pytorch-forecasting` 1.8 release metadata (`torch>=2.0`,
  `lightning>=2.0,<2.7`, `scikit-learn`, `scipy`).
- Conversation/issue: GitHub issue #57, alignment block B1 (2026-08-09);
  Stage 3.2 `technical.md` §7 (accepted 0% coverage of the skipped adapter).
