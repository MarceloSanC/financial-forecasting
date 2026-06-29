---
title: ADR 3.2.0002 — torch/transformers as an optional pyproject extra outside dev, lazily imported in the FinBERT adapter, with a sentiment-no-ml-leak import-linter contract and a skipif integration test
description: Architecture Decision Record
when-use: Reference before adding a heavy ML dependency (torch, transformers, …), before changing how the FinBERT adapter imports its libs, or before changing which extras the CI installs
keywords: [adr, torch, transformers, optional-extra, lazy-import, sentiment-no-ml-leak, import-linter, skipif, ci, coverage, dev-group, finbert, overnight-finding]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "3.2.0002"
decision: torch+transformers live in a [project.optional-dependencies].sentiment extra OUTSIDE the dev group the CI installs; the FinBERT adapter imports them lazily (inside __init__/method, clear ImportError if absent); a new import-linter contract sentiment-no-ml-leak forbids torch/transformers in feature_engineering.application+domain; the live integration test is skipif-guarded so the ~400MB model is never downloaded in the unattended CI run
context_stage: 3.2-sentiment-finbert
---

# ADR 3.2.0002 — ML deps as an optional extra + lazy import + anti-leak contract

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 3.2's FinBERT adapter needs `transformers` + `torch` (hundreds of MB; torch
pulls CUDA/ROCm wheels). Forces:

- **Overnight-finding (carried from prior Stages): keep torch out of the CI's
  default install.** The CI runs `uv sync --extra dev`. If torch were in `dev`, the
  CI would download torch on every run — very slow and liable to blow the runner's
  disk/time budget. The model itself (~400 MB) must **never** be downloaded in the
  unattended overnight run.
- **Coverage ≥90% of live BC code must hold without torch.** The pure scoring
  (`scores_from_probs`), `_build_text`, the port, and the use case aggregation are
  torch-free (ADR `3.2.0001`); only the tokenize+forward path needs torch, and that
  path is exercised only in a manually-run integration test.
- **The posture is already consolidated for other heavy/leaky libs.** Three prior
  `forbidden`-type import-linter contracts confine a library to its adapter:
  `tracker-no-mlflow-leak` (`.importlinter` 145-154), `store-no-storage-leak`
  (167-197, pandas/pyarrow/duckdb/pandera), `calendar-no-exchange-calendars-leak`
  (207-216). Live integration tests already `skipif` when an external dependency is
  absent (`yfinance`/Alpha Vantage in 2.2/2.3, `exchange-calendars` in 2.4).
- **The prior repo imported torch/transformers at module top**
  (`src/adapters/finbert_sentiment_model.py`), so merely importing the adapter
  module required torch — which would break test collection on a torch-free CI.

## Decision

Four coupled decisions:

1. **Optional extra outside dev.** Declare
   `[project.optional-dependencies].sentiment = ["torch>=…,<…", "transformers>=…,<…"]`
   (pinned by minor; `uv.lock` regenerated in the same commit — `CONVENTIONS.md`
   §5), **not** in the `dev` group. The CI keeps running `uv sync --extra dev` and
   never installs torch. Running sentiment for real is `uv sync --extra sentiment`.

2. **Lazy import in the adapter.** `transformers`/`torch` are imported **inside**
   `FinbertSentimentModel.__init__`/method, not at module top, so the module (and
   the pure `scores_from_probs`) import cleanly without the libs. A missing lib
   raises a **clear `ImportError`** pointing at `uv sync --extra sentiment`.

3. **`sentiment-no-ml-leak` import-linter contract.** A new `type = forbidden`
   contract forbids `torch` + `transformers` in
   `financial_forecasting.features.feature_engineering.application` and
   `...domain`, mirroring `calendar-no-exchange-calendars-leak`. The libs live only
   in `adapters/out/finbert/`. An intentional `import torch` in the application
   turns `lint-imports` red, then is reverted (proof).

4. **Skipif integration test.** The live adapter test is `skipif`-guarded
   (lib/model absent) and marked out of the overnight run; it never downloads the
   ~400 MB model unattended. It is `SKIPPED` in the `dev` CI and runs only when a
   developer installs the `sentiment` extra.

## Alternatives considered

### Alternative A — Put torch/transformers in the `dev` group

- **Description:** Add the ML deps to the group the CI installs.
- **Pros:** Integration test runs in CI; one dependency group.
- **Cons:** CI downloads torch every run (slow; can blow the runner); the unattended
  overnight run would try to fetch the ~400 MB model — the exact finding being
  guarded against.
- **Why rejected:** Directly violates the overnight finding; a heavy, optional
  inference dependency does not belong in the dev/test default.

### Alternative B — Import torch/transformers at the adapter module top (prior repo)

- **Description:** `import torch` / `from transformers import …` at the top of the
  adapter module.
- **Pros:** Conventional; matches the old.
- **Cons:** Importing the module (e.g. during test collection or to reach
  `scores_from_probs`) requires torch installed — breaks the torch-free CI and
  couples the pure function's importability to the heavy lib.
- **Why rejected:** Lazy import decouples module import from lib presence, which is
  what makes torch-free coverage possible.

### Alternative C — No import-linter contract; rely on review to keep torch in the adapter

- **Description:** Trust code review to prevent torch leaking into
  application/domain.
- **Pros:** No `.importlinter` change.
- **Cons:** Architecture-as-convention rots (the prior repo's lesson, ADR
  `1.3.0001`); a leak would pass silently.
- **Why rejected:** The project enforces boundaries as fitness functions; three
  sibling contracts already exist — adding the fourth is one cheap block.

### Alternative D — A single generic `ml-deps` extra for all future model libs

- **Description:** One extra bucket for torch/transformers/pytorch-forecasting/etc.
- **Pros:** Fewer extras.
- **Cons:** Premature — only sentiment needs torch today; training libs
  (pytorch-forecasting, LightGBM) arrive in Step 5 with different install profiles.
- **Why rejected:** A focused `sentiment` extra is simpler now and trivially
  splittable; grouping unrelated heavy libs prematurely couples their install.

### Alternative E — Do nothing

- **Why not acceptable:** Without an extra + lazy import + contract, torch would
  either enter the CI default (finding) or leak into the application (boundary
  rot).

## Consequences

### Positive

- CI stays fast and torch-free (`uv sync --extra dev`); the ~400 MB model is never
  fetched unattended; coverage ≥90% of live BC code holds without torch.
- `sentiment-no-ml-leak` mechanically confines torch/transformers to the adapter,
  consistent with the mlflow/storage/calendar contracts.
- Running sentiment for real is one opt-in flag (`--extra sentiment`).

### Negative

- One more optional extra and one more import-linter contract to maintain (the
  cheap, known cost ADR `1.3.0001` accepted).
- The live integration test does not run in CI (it is `SKIPPED`); the torch-free
  oracle/pure-function tests carry correctness in CI, with the live test as a
  manual smoke.

### Neutral / trade-offs accepted

- The exact `torch`/`transformers` pins are resolved during execution and locked in
  `uv.lock`; this ADR fixes the *placement* (extra, outside dev) and *posture*
  (lazy + contract), not the literal versions.

## Implementation notes

- `pyproject.toml`: `[project.optional-dependencies].sentiment` (not `dev`); run
  `uv lock` in the same commit.
- `.importlinter`: append a `[importlinter:contract:sentiment-no-ml-leak]`
  (`type = forbidden`) with `source_modules =
  financial_forecasting.features.feature_engineering.{application,domain}` and
  `forbidden_modules = torch, transformers`, `allow_indirect_imports = False`, with
  a comment citing this ADR and the sibling `calendar-no-exchange-calendars-leak`.
- Adapter: `import torch` / `from transformers import AutoTokenizer,
  AutoModelForSequenceClassification` inside `__init__`, wrapped to raise a clear
  `ImportError("install the 'sentiment' extra: uv sync --extra sentiment")`.
- Integration test: `pytest.importorskip("transformers")` / `importorskip("torch")`
  + a marker excluded from the overnight selection; asserts score ∈ `[-1, +1]`
  against an oracle case when run manually.

## References

- Related ADRs: [3.2.0001](./3_2_0001-finbert-pinned-revision-and-scoring.md) (the
  torch-free pure scoring this lazy split enables),
  [0.0.0017](./0_0_0017-finbert-version-pinned.md) (the pinned model loaded lazily
  here), [1.3.0001](./1_3_0001-import-linter-as-architecture-fitness-function.md)
  (import-linter as fitness function; cheap per-contract cost accepted),
  [3.1.0001](./3_1_0001-feature-engineering-bc-and-indicator-contracts.md) (the BC
  this contract extends).
- `docs/stages/3.2-sentiment-finbert/concept.md` §5 I5/I8/I9/I10, §7 D2.
- `.importlinter` — `tracker-no-mlflow-leak` (145-154), `store-no-storage-leak`
  (167-197), `calendar-no-exchange-calendars-leak` (207-216) — the molds for
  `sentiment-no-ml-leak`.
- Overnight finding (heavy ML deps / robustness): keep torch out of the CI default;
  do not download the model unattended; separate pure scoring for torch-free
  coverage.
- `docs/CONVENTIONS.md` §5 (`uv.lock` versioned; regenerate in the same commit).
- Old: `src/adapters/finbert_sentiment_model.py` (top-level torch/transformers
  import → move to lazy).
