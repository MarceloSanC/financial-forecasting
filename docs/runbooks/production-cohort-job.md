---
title: Runbook — Production cohort job (scheduled round + serving switch)
description: How to run, schedule, resume, publish and roll back a production round of the AAPL cohort, and how to switch the inference API to the round the job published
when-use: When running or scheduling the production job (Stage 8.4), when a round stopped midway, when switching or rolling back the cohort served by the inference API, or when cleaning old rounds
keywords: [runbook, production-cohort, production-round, scheduler, cron, task-scheduler, serving-pointer, inference-api, resume, rollback]
status: accepted
created_at: 2026-10-25
updated_at: 2026-10-25
runbook_id: production-cohort-job
triggers:
  - A scheduled production round (weekly cadence suggested)
  - A round that stopped midway (crash, reboot, killed container)
  - Switching or rolling back the cohort served by the inference API
estimated_duration: ~1 h 45 min per round on 6 CPUs (FinBERT ~15 min, baselines and GBM minutes, three TFT seeds × ~27 min); API recreation in seconds
---

# Runbook — Production cohort job

> Runbooks are written and consumed in **English**. They describe operational procedures executed by humans or agents.

## Purpose

Keep a **production cohort** that the inference API (Stage 7.4) can serve, without
touching the confirmatory cohort. Each run of the job is a **round**:

1. copy the three raw inputs into `<production-root>/rounds/<round>/`;
2. materialize the dataset (FinBERT included);
3. derive the round's frozen spec from `config/cohorts/aapl_production.toml`
   (confirmatory r0 hyperparameters, one fold, seeds 1–3) and the round's data;
4. retrain the baselines, the GBM and the TFT seeds;
5. verify the round by counts;
6. only then replace `<production-root>/serving.env`, if the round is not older
   than the one it names.

The API reads `serving.env` once, at start-up. Switching cohorts is recreating its
container. Decisions: concept 8.4 and ADRs 8.4.0001 and 8.4.0002.

What a round serves: the test decisions of its last 252 sessions whose target is
already in the panel (h+1 up to `T − 1`, h+7 up to `T − 7`), per seed, with the
native quantiles only — the conformal and explainability blocks are
`unavailable` ("gold não publicado"). Forecasting the next session is issue #242.
Fetching the raw inputs from the providers is issue #241.

## Prerequisites

- [ ] Docker Desktop daemon up (`scripts/docker-start.ps1` on the Windows host).
- [ ] Image `financial_forecasting-app:dev` built.
- [ ] A **clean** checkout, run from its **root** (the environment probe reads the
      committed content of `src/`, `uv.lock` and the production model; a dirty tree
      is refused with `EnvironmentMismatchError`).
- [ ] A venv volume with the `sentiment` extra and a Hugging Face cache volume
      (the dev venv has no FinBERT). Create once:

      ```bash
      docker volume create ff-prod-venv-sentiment
      docker run --rm -v financial-forecasting_app-venv:/src:ro -v ff-prod-venv-sentiment:/dst \
        financial_forecasting-app:dev sh -c "cp -a /src/. /dst/"
      docker run --rm -v "$PWD:/app" -v ff-prod-venv-sentiment:/app/.venv -w /app \
        financial_forecasting-app:dev sh -c "uv sync --locked --extra dev --extra sentiment"
      docker volume create ff-prod-hf-cache
      ```

- [ ] A raw directory with the input layout of Stage 5.5, kept up to date outside
      the job (e.g. `data/raw-production/`):
      `raw/market/candles/AAPL/candles_AAPL_1d.parquet`,
      `raw/news/AAPL/news_AAPL.parquet`,
      `processed/fundamentals/AAPL/fundamentals_AAPL.parquet`.
- [ ] The production root **outside** `data/cohorts/` (the command refuses it
      otherwise). Default here: `data/production/aapl`.
- [ ] The job and the API mount the checkout at the **same container path**
      (`/app`): `serving.env` holds absolute container paths.

All commands below run from the checkout root on the host (Git Bash: prefix
`docker` with `MSYS_NO_PATHCONV=1`).

```bash
JOB="docker run --rm --cpus 6 --memory 8g \
  -v $PWD:/app -v ff-prod-venv-sentiment:/app/.venv -v ff-prod-hf-cache:/root/.cache/huggingface \
  -w /app financial_forecasting-app:dev"
CLI="uv run --no-sync python -m financial_forecasting.cli"
ROUND_ARGS="--production-root data/production/aapl --raw-root data/raw-production \
  --cohort config/cohorts/aapl_production.toml"
```

In a git worktree, also mount the main `.git` read-only and set `GIT_DIR`,
`GIT_WORK_TREE` and `GIT_OPTIONAL_LOCKS=0`, as in the confirmatory runbook.

## Procedure

### Step 1 — Run a round

```bash
$JOB sh -c "git config --global --add safe.directory '*'; $CLI production-round $ROUND_ARGS --round $(date +%F)"
```

**Expected** (one line per step; the last line names the published cohort):

```
materialized AAPL: … candles, … news, … fundamentals
dataset rows … (2010-04-21..<last session>), feature_set_hash 7df0e1b4…
round spec written: data/production/aapl/rounds/<round>/cohort.toml (dataset <12 hex>)
cohort aapl_production-r0-<hash12>
  baselines: ran (5 runs)
  gbm: ran (1 runs)
  tft:seed=1: ran (1 runs)
  tft:seed=2: ran (1 runs)
  tft:seed=3: ran (1 runs)
cohort aapl_production-r0-<hash12>: 9 models x 1 folds; rows expected …, observed …
OK
published aapl_production-r0-<hash12> → /app/data/production/aapl/serving.env
```

Exit codes: 0 = round verified (published, or `not published: … older than …`);
1 = `verify` diverged, nothing published; 2 = error (message on stderr).

### Step 2 — Switch the API to the published round

Recreate the API container with the pointer as its environment:

```bash
docker rm -f ff-inference-api 2>/dev/null
docker run -d --name ff-inference-api -p 8000:8000 \
  --env-file data/production/aapl/serving.env \
  -v "$PWD:/app" -v financial-forecasting_app-venv:/app/.venv -w /app \
  financial_forecasting-app:dev \
  uv run --no-sync uvicorn financial_forecasting.main:app --host 0.0.0.0 --port 8000
```

Check it serves the round:

```bash
curl -s -X POST localhost:8000/inference/run -H 'content-type: application/json' \
  -d '{"asset":"AAPL","decision_date":"<a test date of the round>","horizons":[1]}'
```

**Expected:** 200, `cohort_id` equal to the published one, three members
(seeds 1, 2, 3), conformal and explainability `unavailable`. A date outside the
round's test block answers 404 "não há dados para o pedido solicitado".

The API does not answer while the container is recreated (seconds; measured in
technical 8.4 §7). This gap is accepted (ADR 8.4.0002 item 3).

### Step 3 — Schedule it

The scheduled script runs Step 1 and, only if the output has a `published`
line, Step 2. Save as `scripts-local/production-round.sh` (not versioned) with
the variables above:

```bash
#!/bin/sh
# no `set -e`: exit 1 (verify diverged) and 2 (error) must reach the log, not abort it
cd /c/Users/<user>/Documents/Code/financial-forecasting || exit 2
export MSYS_NO_PATHCONV=1
rc=0
OUT=$(docker run --rm --cpus 6 --memory 8g \
  -v "$PWD:/app" -v ff-prod-venv-sentiment:/app/.venv -v ff-prod-hf-cache:/root/.cache/huggingface \
  -w /app financial_forecasting-app:dev sh -c "git config --global --add safe.directory '*'; \
  uv run --no-sync python -m financial_forecasting.cli production-round \
  --production-root data/production/aapl --raw-root data/raw-production \
  --cohort config/cohorts/aapl_production.toml --round $(date +%F)" 2>&1) || rc=$?
echo "$OUT"
echo "production-round exit $rc"
if [ "$rc" -eq 0 ] && echo "$OUT" | grep -q '^published '; then
  docker rm -f ff-inference-api 2>/dev/null
  docker run -d --name ff-inference-api -p 8000:8000 \
    --env-file data/production/aapl/serving.env \
    -v "$PWD:/app" -v financial-forecasting_app-venv:/app/.venv -w /app \
    financial_forecasting-app:dev \
    uv run --no-sync uvicorn financial_forecasting.main:app --host 0.0.0.0 --port 8000
fi
exit "$rc"
```

- **cron (Linux/WSL host):** `0 3 * * 6 /path/to/production-round.sh >> /var/log/ff-production.log 2>&1`
  (Saturdays 03:00).
- **Windows Task Scheduler:** a weekly task running
  `"C:\Program Files\Git\bin\bash.exe" -lc "/c/.../production-round.sh >> /c/.../ff-production.log 2>&1"`,
  with "Run whether user is logged on or not" and the Docker Desktop autostart on.

The command holds `<production-root>/.writer.lock` for the whole round, so two
scheduled runs never overlap: the second exits 2 with `CohortRunLockedError`.

## Resume, redo and rollback

- **Resume:** rerun Step 1 with the same `--round`. A marked materialization is
  skipped, an equal round spec is kept, completed units are `skipped_completed`,
  `verify` runs again and the pointer is rewritten only if the round is still the
  newest.
- **Orphan lock** (a killed job left `.writer.lock` in the production root or in
  the round): the run exits 2 naming the owner. After confirming that process is
  dead, rerun with `--break-stale-lock`. Never put `--break-stale-lock` in the
  scheduled line.
- **Round that cannot resume** (`EnvironmentMismatchError` after a merge changed
  `src/` or `uv.lock`; `PartialCohortUnitError`, `CompletedUnitCorruptedError`,
  `UnitOutputMismatchError`): start a **new round** of the same day,
  `--round <date>.1` (then `.2`, …). Do not raise the `revision` of the production
  model: that changes the `cohort_id` of every future round.
- **Rollback:** edit `serving.env` by hand to point at an older round
  (`DATA_ROOT` and `SERVING_COHORT_FILE`), then Step 2. The next scheduled round
  (newer by date) publishes again.
- **Cleanup:** delete `data/production/aapl/rounds/<old round>/` for rounds that
  are not the one in `serving.env`. Every TFT training also copies its checkpoint
  into the MLflow artifact store `./mlruns/` of the working directory (the checkout;
  git-ignored), ~80 MB per round with three seeds (measured in technical 8.4 §7):
  the round's runs are listed in its own `rounds/<round>/mlruns.db`, so after
  deleting old rounds also delete `./mlruns/` entries no remaining round uses, or the
  whole `./mlruns/` if only the served round matters. There is no automatic
  retention.

## Verification

```bash
cat data/production/aapl/serving.env          # two lines, the newest verified round
$JOB sh -c "$CLI verify --data-root data/production/aapl/rounds/<round> --cohort data/production/aapl/rounds/<round>/cohort.toml"
```

Expected: `OK` and exit 0.

## Troubleshooting

| Symptom | Likely cause | Resolution |
|---|---|---|
| `MissingSentimentExtraError` | job run with the dev venv | use the `ff-prod-venv-sentiment` volume |
| `ProductionRoundError: … overlaps …/data/cohorts` | production root inside `data/cohorts/` | use `data/production/<asset>` |
| `ProductionRoundError: raw input not found` | raw directory incomplete | fix the raw directory |
| `ValueError: round name must be YYYY-MM-DD…` | bad `--round` | use the date, or `<date>.N` |
| `warning: --raw-root differs from the round's copy` | inputs changed after the round materialized | expected on a rerun; start a new round to use them |
| `ProductionRoundError: … derived, never edited` | the round's `cohort.toml` was edited, or the model changed | start a new round |
| `EnvironmentMismatchError: … uncommitted` | dirty checkout | commit or clean, then rerun |
| `EnvironmentMismatchError: environment differs …` | resume after a code/venv change | new round `<date>.1` |
| `CohortRunLockedError` | another round running, or an orphan lock | wait, or `--break-stale-lock` after confirming the owner is dead |
| `not published: round … is older than …` | a rerun of an old round | expected; the pointer stays |
| exit 1 with `MISMATCH …` | `verify` diverged | read the lines; rerun to resume, or a new round |
| API answers 500 "serviço de inferência sem cohort configurado" | container started without `--env-file` | Step 2 |
| API answers 404 for today's date | the round serves only decisions with a realized target | expected (issue #242) |

## Related

- Concept and technical: `docs/stages/8.4-production-cohort-job/`
- ADRs: `docs/adr/8_4_0001-production-round-own-frozen-cohort-retrained-without-gold.md`,
  `docs/adr/8_4_0002-immutable-round-roots-and-atomic-serving-pointer.md`
- Confirmatory cohort runbook (environment, resume, lock): `docs/runbooks/confirmatory-cohort-aapl.md`
- Code: `src/financial_forecasting/cli.py` (`production-round`),
  `src/financial_forecasting/features/modeling/adapters/in/cli/production_commands.py`
