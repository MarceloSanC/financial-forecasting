---
title: ADR 7.3.0006 — Stage 7.3 split between a Windows phase (code, synthetic tests, drafts) and a Linux phase (ROCm, pilot, seed decision, freeze, training, r3 anchor), with the handoff in the repository and the Stage PR closed on Linux
description: Architecture Decision Record
when-use: Reference when asking what Stage 7.3 delivers on each machine, what the Linux session must do and in which order, why the Stage PR is not merged after the Windows phase, or what blocks the start of the execution
keywords: [adr, handoff, windows, linux, rocm, gpu, pilot, seeds, freeze, anchor, r3, stage-lifecycle, pr, blinding]
status: accepted
created_at: 2026-10-18
updated_at: 2026-10-18
adr_id: 7.3.0006
decision: Stage 7.3 executes in two phases on one branch and one PR: the Windows phase delivers all code with synthetic tests, the unfrozen ablation spec, the r3 draft and, optionally, the unscored permuted predictions over the 60 real checkpoints, and ends with a [handoff] entry in the technical §7 plus a step-by-step comment on issue #186; the Linux phase installs the ROCm torch, runs the pilot, takes the human seed decision, freezes the ablation spec, trains the ~5 × 6 × S units, verifies, writes and anchors r3, then runs the Stage audit and merges; the Fase 4 starts only after Stage 7.2 is merged.
context_stage: 7.3-explainability
bounded_context: inference
---

# ADR 7.3.0006 — Windows × Linux split and in-repo handoff

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 7.3 concept (issue #186), 2026-10-18. Closes item 10 of the
research findings of the issue. The split and the in-repo handoff were
requested by the human on 2026-10-06 (issue #186, alignment 1b items 2–4: GPU
training on Linux; the audit of 7.3 on the Linux session).

## Context

- The ablation needs GPU (ADR 7.3.0004); the GPU is on a Linux machine; the
  Windows session cannot see the Linux one, nor its memory — the handoff must
  live in the repository and on GitHub.
- The seed count is a human decision after the pilot (P-ABLACAO); the ablation
  hash, hence r3, exists only after it.
- r3 copies r2, which exists only after Stage 7.2 merges (ADR 7.3.0005).
- Blinding: no H3 metric before the r3 anchor; the first H3 metric is 8.1's.
- The roadmap DoD of 7.3 includes "cohort de ablação congelado e hasheado" and
  "pré-registro de H3 ancorado" — both Linux acts.

## Decision

`[decision:C] 7.3-SPLIT — where the Stage closes`
`Escolha: one branch and one PR; Windows phase ends at the handoff, PR open; Linux phase executes, audits and merges · Alternativas: merge the Windows code first and open a second PR on Linux; a separate Linux Stage · Degrau: 1 (roadmap DoD of 7.3 includes freeze and anchor; human request of 2026-10-06) e 5`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

1. **Precondition of the Fase 4:** Stage 7.2 merged into `develop` (r2
   anchored, `ConformalAssembly` and the public rule functions of
   `series_assembly.py` available) and the 7.3 branch rebased on it.
2. **Windows phase:** all Tasks of the technical (code + synthetic tests +
   gates), `config/cohorts/aapl_ablation.toml` as a draft (seeds empty,
   `torch_build` unset), the r3 draft in the Stage folder, and optionally
   Etapa W: `attribute` over the 60 real confirmatory checkpoints on the 7.1
   CPU environment (predictions and VSN weights only, never scored; identity
   strict). It ends with: a `[handoff]` entry in technical §7 and a comment on
   issue #186 with the Linux steps, the commit to check out and the exact
   commands; the PR stays open.
3. **Linux phase, in order:** (L1) environment: checkout of the branch, `uv
   sync --frozen`, ROCm torch over it, `uv run --no-sync` (ADR 7.3.0004); GPU
   smoke test; (L2) pilot `ablation-pilot` (full, seed 1, last fold) — time and
   epochs only; (L3) **P question to the human** on the seed count, in the
   "Anatomia da pergunta" format, anchored on the pilot output; decision
   recorded in an ADR; (L4) `ablation-freeze` (seeds, `torch_build`), commit,
   and **anchor the ablation cohort** (tag `cohort/<ablation cohort_id>` +
   comment on issue #186 with id and hash, ADR 5.5.0001), so the order check of
   ADR 6.5.0003 item 4 ("the anchor of the referenced cohort precedes the
   anchor of the preregistration") has a server timestamp before training;
   (L5) `ablation-run` (resumable) and `ablation-verify`; (L6) Etapa W if not
   done on Windows (on Linux CPU, identity in tolerance); (L7) r3 filled,
   committed and anchored (ADR 7.3.0005 item 3); (L8) Stage audit, findings,
   merge. No H3 metric at any step.
4. **What the Linux session may change in code:** only GPU adjustments found
   by the pilot (e.g. determinism of a ROCm kernel), each a `[decision]` in
   technical §7 and committed **before** L4; after L4 no change to `src/`
   until L5 ends (the runner refuses a different `code.src` on resume).
5. **Data transfers (data/ and artifacts/ are git-ignored)**, each with a
   check run at the destination before the next step (Checkpoint A, A-C5):
   - Windows → Linux, before L2: `data/cohorts/aapl/processed/dataset_tft`
     (the grid fingerprint read at the destination = the cohort's
     `dataset_fingerprint`; `check_cohort_declarations`, run by
     `ablation-pilot` before training, refuses a different one), the 60 confirmatory checkpoints (sha256 of each = the 7.1
     inference manifest) and the confirmatory silver (`dim_run`,
     `fact_oos_predictions`, and the attribution tables if the Etapa W ran;
     5.5 `verify` and the `attribute` re-verification green at the
     destination);
   - Linux → the machine where 8.1 runs: the ablation `dim_run` and
     `fact_oos_predictions` and, if L6 ran there, the attribution tables;
     `ablation-verify` and the `attribute` re-verification re-run at the
     destination. Which machine runs 8.1 is for the 8.1 concept; the checks are
     mandatory in both directions.
6. **Mechanical criteria per Linux step** (copied into the `[handoff]`):

   | Step | Command | Expected output | Stop |
   |---|---|---|---|
   | L1 | `uv run --no-sync python -c` probe snapshot | GPU available = true, GPU name, HIP version, torch version with `+rocm` | C12 |
   | L2 | `ablation-pilot` | report (seconds_per_epoch, max_epochs, ceiling and estimate per S) pasted in technical §7 | C12 |
   | L3 | — (P question) | ADR with S | — |
   | L4 | `ablation-freeze`, commit, tag `cohort/<id>`, comment | spec frozen; commit hash and tag published on #186 | C2, C13 |
   | L5 | `ablation-run`, `ablation-verify` | `verify` green with 5 · 6 · S runs (30 · S) | C3, C4 |
   | L6 | `attribute` (if not done) | CA15 counts; 60 `completed` | C5–C8 |
   | L7 | r3 fill + draft comparison test + anchor | only `[h3.ablation]` differs; tag, comment, `.anchor.toml` | C11, C13 |
   | L8 | Stage audit | verdict on the PR | — |

   A test runs `--help` of every subcommand the handoff cites, so a renamed
   command fails CI before the Linux session.

## Alternatives considered

### Alternative A — Merge the Windows code, second PR on Linux
- **Pros:** shorter-lived branch.
- **Cons:** `develop` would carry a Stage marked done without its DoD (no
  frozen cohort, no anchor), or an in-progress Stage in `develop` with the
  audit split in two.
- **Why rejected:** the Stage's DoD needs the Linux acts; nothing else waits on
  the Windows code (7.4 and 8.1 depend on 7.3 done).

### Alternative B — A separate Stage for the Linux run
- **Why rejected:** no scope boundary (the run is the same capability, as the
  real runs of 5.5 and 7.1 were inside their Stages).

## Consequences

### Positive
- The Linux session starts from a self-contained, versioned set of
  instructions; the human sees the seed decision with real cost numbers.

### Negative
- The PR stays open for the duration of the GPU run (days).

### Neutral / trade-offs accepted
- The Etapa W may run on either machine (ADR 7.3.0002 item 3).

## References

- Related ADRs: [0.0.0007](./0_0_0007-h3-family-contribution-across-horizons.md),
  [7.3.0002](./7_3_0002-permuted-predictions-and-vsn-via-modeling-port-persisted-in-silver.md),
  [7.3.0003](./7_3_0003-ablation-cohort-spec-by-reference-identity-per-configuration.md),
  [7.3.0004](./7_3_0004-device-per-trainer-instance-torch-build-declared.md),
  [7.3.0005](./7_3_0005-h3-preregistration-r3-details.md).
- Issue: [#186](https://github.com/MarceloSanC/financial-forecasting/issues/186).
