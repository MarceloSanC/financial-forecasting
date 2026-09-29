---
title: Runbook — Confirmatory cohort run (AAPL)
description: Step-by-step procedure to materialize the AAPL data, run the exploratory sweeps, freeze and anchor the confirmatory cohort, run it resumably and verify it by counts
when-use: When producing (or reproducing) the Stage 5.5 confirmatory cohort for AAPL, when resuming a run that stopped, or when remediating a partially persisted unit by opening a new cohort revision
keywords: [runbook, confirmatory-cohort, aapl, materialize, sweep, freeze, anchor, resume, verify, blinding]
status: accepted
created_at: 2026-09-27
updated_at: 2026-09-29
runbook_id: confirmatory-cohort-aapl
triggers:
  - Stage 5.5 real run (Tasks 33–35)
  - A `run` that stopped midway (crash, reboot, killed container)
  - A `PartialCohortUnitError` or `CompletedUnitCorruptedError` from `run`
estimated_duration: ~1.5 days (materialize ~15 min; sweeps ~10 h; run ~19 h, as measured for AAPL)
---

# Runbook — Confirmatory cohort run (AAPL)

> Runbooks are written and consumed in **English**. They describe operational procedures executed by humans or agents.

## Purpose

Produce the confirmatory cohort of Stage 5.5 in five stages:

1. Materialize the AAPL dataset from the raw files of the previous project.
2. Run the two exploratory sweeps (TFT and GBM, same trial budget).
3. Freeze the hyperparameters, provenance and dataset fingerprint into
   `config/cohorts/aapl_confirmatory.toml`, then anchor the freeze publicly
   (git tag + issue comment) **before** the run.
4. Run baselines, GBM and the TFT seeds over the same training grid, resumably,
   under one `parent_sweep_id`.
5. Verify the run by counts.

**No metric is computed on the cohort before the Stage 6.5 pre-registration
(blinding, ADR 5.5.0001).**

Each step below says how it was validated: **executed for real** (Stage 5.5,
Tasks 33–35, with the evidence in `docs/stages/5.5-confirmatory-retrain/technical.md`
§7) or **covered by the end-to-end test** (`tests/e2e/test_cohort_cli.py`,
Task 31 — resume, orphan-lock break, revision remediation).

## Triggers

- Producing the cohort for the first time (Stage 5.5).
- Resuming a `run` that stopped (the ledger and the silver make every unit
  either skip, verify or rerun).
- Remediating a partially persisted unit (`revision += 1`).

## Prerequisites

- [ ] Docker Desktop daemon up (`scripts/docker-start.ps1` on the Windows host).
- [ ] Image `financial_forecasting-app:dev` built.
- [ ] A git worktree of the Stage branch, clean (`git status` empty), run from
      its **root**. The probe refuses any other directory: git pathspecs are
      relative to the working directory, so from a subdirectory `code_dirty`
      would be blind.
- [ ] Raw files of the previous project at hand (AAPL candles, news, fundamentals).
- [ ] A **separate** venv volume with the `sentiment` extra (FinBERT). Do not
      install the extra into the shared dev venv volume.
- [ ] Access to the Hugging Face Hub (first FinBERT download), with a cache volume.
- [ ] `gh` authenticated (anchor comment on the issue).
- [ ] The host stays **on, and not asleep**, for the whole sweep (hours) and the
      whole run.
  - The sweep keeps its Optuna study in memory and records only at the end,
    so a shutdown mid-sweep discards every trial. This happened once in
    Stage 5.5 (§7, "[finding] Task 34").
  - The run resumes per unit, and a shutdown loses only the unit in progress.

All container commands below use this invocation. Mount the main `.git`
**read-only**, and set `GIT_DIR`/`GIT_WORK_TREE`: the worktree's `.git` file
points to a Windows path the container cannot resolve. `GIT_OPTIONAL_LOCKS=0`
keeps `git status` from taking `index.lock` on the read-only mount.
Replace `<raiz-das-worktrees>` with the folder that holds the worktrees and
`<raiz-do-repo>` with the main checkout, both as absolute host paths with
forward slashes.

```bash
WT=feat-102-5-5-confirmatory-retrain
WTP="<raiz-das-worktrees>/$WT"
RUN="docker run --rm -v $WTP:/app \
  -v <raiz-do-repo>/.git:/main.git:ro \
  -v ff55-venv-sentiment:/app/.venv -v ff55-hf-cache:/root/.cache/huggingface \
  -w /app -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app \
  -e GIT_OPTIONAL_LOCKS=0 financial_forecasting-app:dev"
CLI="uv run --no-sync python -m financial_forecasting.cli"
COHORT="--data-root data/cohorts/aapl --cohort config/cohorts/aapl_confirmatory.toml"
# On Git Bash prefix docker with MSYS_NO_PATHCONV=1 and run
# `git config --global --add safe.directory '*'` inside the container first.
```

## Procedure

### Step 1 — Copy the raw files into the cohort data root (executed for real, Task 33)

The three paths are the ones the local-ingestion wiring reads under `data_root`:

```bash
SRC=<previous-project>/data; DST=$WTP/data/cohorts/aapl
for rel in raw/market/candles/AAPL/candles_AAPL_1d.parquet \
           raw/news/AAPL/news_AAPL.parquet \
           processed/fundamentals/AAPL/fundamentals_AAPL.parquet; do
  mkdir -p "$DST/$(dirname $rel)" && cp -p "$SRC/$rel" "$DST/$rel"
done
sha256sum "$SRC"/... "$DST"/...   # must match pairwise
```

**Expected:** identical hashes. `data/` is git-ignored, so the tree stays clean.

### Step 2 — Prepare the venv with the `sentiment` extra (executed for real, Task 33)

```bash
docker volume create ff55-venv-sentiment
docker run --rm -v financial-forecasting_app-venv:/src:ro -v ff55-venv-sentiment:/dst \
  financial_forecasting-app:dev sh -c "cp -a /src/. /dst/"
docker run --rm -v $WTP:/app -v ff55-venv-sentiment:/app/.venv -w /app \
  financial_forecasting-app:dev sh -c "uv sync --locked --extra dev --extra sentiment"
docker volume create ff55-hf-cache
```

**Expected:** `transformers 4.57.6` / `torch 2.13.0+cpu` importable.

### Step 3 — Check git inside the container (executed for real, Task 33)

```bash
$RUN sh -c "git status --short; git log --oneline -1"
```

**Expected:** empty status and the Stage HEAD. The probe snapshot then shows
`code_dirty false`.

### Step 4 — Materialize (executed for real, Task 33)

```bash
$RUN sh -c "$CLI materialize $COHORT --start 2010-04-20"
```

**Expected:**

```
materialized AAPL: 4024 candles, 6921 news, 81 fundamentals
dataset rows 3950 (2010-04-21..2025-12-31), feature_set_hash 7df0e1b4…09e0
```

The run takes about 13–15 min on 12 threads; most of it is FinBERT over the news.

- **Why `--start 2010-04-20`:** without it, the dataset quality gate (check (d))
  rejects the series. The fundamentals only become effective at the
  `reported_date` of the first report, 2010-04-20, and that date is a fact of
  the data. The useful grid starts on the same session either way (2011-04-18).
  See §7, "[decision:E] Task 33 — R9".
- **If it fails with `DuplicateKeyError … (bronze, …)`:** a previous attempt
  left a bronze behind, and ingestion appends. Delete **only the derived
  layers** (`data/cohorts/aapl/bronze/` and `data/cohorts/aapl/processed/dataset_tft/`)
  and rerun. Keep `raw/` and `processed/fundamentals/`: they are inputs.

### Step 5 — Measure before deciding (executed for real, Task 33)

- Data shape, following the skill `data-shape-evidence`:
  - trimmed prefix (251), interior NaN (0), useful grid (3699 sessions);
  - fold-0 train of 1641 sessions → τ·n = 32.8 ≥ 30 (the D6 threshold);
  - target reconciliation.
- Cost: `$RUN sh -c "$CLI sweep $COHORT --n-trials 1"`. It writes under its own
  scope id, because `n_trials` is part of the draft hash. One TFT trial takes
  75–806 s depending on the hyperparameters; one GBM trial takes ≤ 20 s.

Evidence: §7 "[measurement] Task 33" (both entries).

### Step 6 — Human decisions [P] (executed for real, Task 33)

With the measured cost, the human decides `sweep.n_trials` (the same for both
sweeps), the TFT seeds and the device. The decisions for AAPL were
`n_trials = 60`, `seeds = 1..10` and CPU. Write them into the cohort file, and
record them in §7 and on the issue.

### Step 7 — Exploratory sweeps (executed for real, Task 34)

TFT and GBM sweeps with 60 trials each took ~10.3 h (`ELAPSED_S=37182`). A first attempt was lost when the host was shut down; see Prerequisites and §7.

```bash
docker run -d --name cohort-sweep ... sh -c "$CLI sweep $COHORT"   # detached; hours
docker logs cohort-sweep | grep -c "Seed set to"                    # TFT trials started
```

**Expected:** `tft sweep recorded under aapl_confirmatory-r0-sweep-<hash>` and
the same line for `gbm`. A sweep already recorded under the same scope id is
skipped, so rerunning after a crash does not redo the TFT sweep.

### Step 8 — Freeze, anchor, publish (executed for real, Task 34)

For AAPL: `frozen aapl_confirmatory-r0-665f45d9169a` / `hash 665f45d9…65b1`. The tag `cohort/aapl_confirmatory-r0-665f45d9169a` points to `2232605`, and the anchor comment on #102 has `created_at` 2026-09-28T20:27:09Z. The GBM determinism contract passed with the frozen params (§7).

```bash
$RUN sh -c "$CLI freeze $COHORT"        # prints: frozen <cohort_id> / hash <sha256>
git add config/cohorts/aapl_confirmatory.toml && git commit -m "feat(modeling): cohort AAPL congelado [5.5/task-34]"
git push
git tag cohort/<cohort_id> && git push origin cohort/<cohort_id>
gh issue comment 102 --body "cohort/<cohort_id> — hash <sha256>"
```

- Re-run the GBM determinism contract with the frozen `gbm_params`.
- **No rebase from here until the run ends (Step 9):** the code identity
  (content hash of `src/`) would change, and I5 would refuse the resume.
- The freeze refuses to write if:
  - the data changed after the sweeps (`DatasetMismatchError`);
  - the seeds are empty;
  - the file would not read back identically.

### Step 9 — Run (executed for real, Task 35; resume and remediation covered by the end-to-end test)

For AAPL, 12 units ran in ~19 h (`ELAPSED_S=68334`): the baselines took 823 s, the GBM 235 s, and each TFT seed 1.5–2.9 h. `run_started_at` was 2026-09-28T20:27:37Z, after the anchor.

```bash
docker run -d --name cohort-run ... sh -c "$CLI run $COHORT"
docker logs -f cohort-run      # one line per unit: start, outcome, runs, rows, seconds
```

- **Resume:** rerun the same command. Each unit ends up in one of these states:
  - completed in the ledger → `skipped_completed`, after its counts are
    reconfirmed in the silver;
  - complete in the silver but missing from the ledger → `verified_completed`;
  - with only orphan registrations → rerun;
  - partial → `PartialCohortUnitError`.
- **Environment:** the first run records it. A resume from a different
  environment or code is refused (`EnvironmentMismatchError`), so use the same
  image, the same venv and the same container CPU count, since the snapshot
  includes torch threads and CPU.
- **Orphan lock** (a killed process left `data/cohorts/aapl/.writer.lock`): the
  run refuses with `CohortRunLockedError`, which names the owner. After
  confirming that process is dead, rerun with `--break-stale-lock`.
- **Partial unit:** open a new revision. Set `revision += 1` in the cohort file,
  commit, and `run`. The new `cohort_id` is a new `parent_sweep_id`: nothing of
  the previous revision is reused, and the old one stays in the silver as a
  dead branch.

### Step 10 — Verify by counts (executed for real, Task 35)

For AAPL: `VERIFY_EXIT=0`, `rows expected 337792, observed 337792`, `OK`.

```bash
$RUN sh -c "$CLI verify $COHORT"; echo exit=$?
```

**Expected:**

```
cohort <cohort_id>: 16 models x 6 folds; rows expected 337792, observed 337792
OK
```

The 16 models are 5 baselines, the GBM and 10 TFT seeds. The expected rows
come from 21112 per model (5 × 3528 + 3472) × 16 models = 337792. `verify`
reads only counts and target timestamps, never metrics.

## Reproduce the published cohort

The published cohort is anchored at the tag, not at the branch head:

```bash
git checkout cohort/aapl_confirmatory-r0-665f45d9169a    # commit 2232605
```

Later commits (the rebase onto `develop`, other Stages) change `src/` and
`uv.lock`. Run from a later head, `run` would refuse with
`EnvironmentMismatchError`, because the code identity differs from the
recorded one.

To reproduce the cohort:
1. Check out the tag.
2. Rebuild the image and a venv from that `uv.lock`.
3. Materialize with the same `--start 2010-04-20`. The dataset fingerprint
   must be `00e4406d…95bd`, otherwise `run` refuses with
   `DatasetMismatchError`.
4. Run Steps 9–10 against a fresh `artifacts/` and silver.

The recorded environment (library versions, CPU, torch threads) is in
technical §7, entry "Auditoria da Stage", F2.

## Verification

```bash
$RUN sh -c "$CLI verify $COHORT"     # exit 0, "OK"
git ls-remote --tags origin "cohort/*"
gh api repos/{owner}/{repo}/issues/102/comments --jq '.[] | select(.body | contains("cohort/")) | .created_at'
```

Expected:
- `verify` exits 0.
- The tag `cohort/<cohort_id>` exists on the remote.
- The anchor comment's `created_at` is **earlier** than the ledger's
  `run_started_at` (`artifacts/cohorts/<cohort_id>/progress.json`).

## Rollback

There is no in-place rollback: the cohort is append-only by design.

### Step 1 — Discard a bad revision
Increase `revision` in the cohort file and follow Steps 8–10. The old revision
keeps its own `parent_sweep_id`, and Stage 6 reads only the anchored one.

### Step 2 — Rebuild the data
Delete the derived layers (`bronze/`, `processed/dataset_tft/`) and rerun
Step 4. If the dataset fingerprint changes, the frozen cohort refuses to run
(`DatasetMismatchError`). A new revision with new sweeps is required.

## Troubleshooting

| Symptom | Likely cause | Resolution |
|---|---|---|
| `DuplicateKeyError … (bronze, candle)` in `materialize` | derived bronze from an earlier attempt | delete `bronze/` and `processed/dataset_tft/` only; rerun |
| `DatasetQualityError: Effective warmup exceeds …` | series starts before the fundamentals are effective | `materialize --start` at the first `reported_date` (Step 4) |
| `ValueError: No trading session after <day>` in `materialize` | code before the Stage 5.5 sentiment fix | update the branch; the calendar now has a tail pad |
| `CohortNotFrozenError` | `run`/`verify` on a draft | Steps 7–8 first |
| `CohortRunLockedError` naming a pid/host | another writer holds `data_root` | wait, or `--break-stale-lock` if that process is dead |
| `EnvironmentMismatchError: … uncommitted` | dirty `src/`, `uv.lock` or cohort file (including untracked files in `src/`) | commit or clean, then rerun |
| `EnvironmentMismatchError: environment differs …` | resume from another image, venv, CPU count or code | resume in the recorded environment, or open a new revision |
| `RuntimeError: repo_root … is not the repository root` | CLI run from a subdirectory | run from the worktree root (`-w /app`) |
| `PartialCohortUnitError` | a unit stopped mid-persist | new revision (Step 9) |
| `UnitOutputMismatchError` | a unit returned without persisting all runs | investigate the silver; new revision |
| `verify` prints `MISMATCH …`, exit 1 | missing run, count, target set or ledger mark | read the line; resume `run` or open a new revision |
| exit 2 with a traceback | unexpected error | read the traceback; nothing was marked for the failing unit |

## Related

- ADRs:
  - `docs/adr/5_5_0001-frozen-hashed-cohort-spec.md`
  - `docs/adr/5_5_0002-exploratory-sweep-on-fold-zero-geometry.md`
  - `docs/adr/5_5_0003-resumable-cohort-units-atomic-ledger.md`
  - `docs/adr/5_5_0004-single-training-grid-warmup-trim.md`
  - `docs/adr/5_4_0003-torch-core-dependency-cpu-index.md`
- Stage docs: `docs/stages/5.5-confirmatory-retrain/` (concept, technical §7 evidence)
- Code:
  - `src/financial_forecasting/cli.py`
  - `src/financial_forecasting/features/modeling/adapters/in/cli/`
  - `src/financial_forecasting/features/modeling/application/use_cases/run_confirmatory_cohort.py`
