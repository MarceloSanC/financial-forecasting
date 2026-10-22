---
title: ADR 8.1.0001 — The confirmatory run is the evaluation use case `RunConfirmatoryEvaluation` (guards before effects, writer lock, three statuses, one judged generation per partition), with the 7.1 `infer` chained before it by the `evaluate` CLI subcommand
description: Architecture Decision Record
when-use: Reference before changing how the confirmatory run is sequenced, before adding a way to re-judge a revision, when a re-run of `evaluate` meets an existing judged generation or leftovers of an interrupted run, or when asking why the use case does not call the inference slice
keywords: [adr, evaluation, confirmatory-run, orchestration, orchestrator, guards, side-effects, replay, idempotency, status, blocked, anchor, preregistration, cli, infer, writer-lock, forking-paths]
status: accepted
created_at: 2026-10-22
updated_at: 2026-10-22
adr_id: 8.1.0001
decision: The confirmatory run is the application use case `RunConfirmatoryEvaluation` in the evaluation slice, which validates the judged revision (chain, expected hash, anchors) through a resolver extracted from `BuildConfirmatoryScorecard`, refuses dirty code, takes the data-root writer lock and checks for an existing judged generation before any effect, then runs `RefreshGold` (command from `refresh_command_from`), the scorecard and the preservation of ADR 8.1.0003; it reports `JUDGED`, `BLOCKED` or `ALREADY_JUDGED` (failures are exceptions), keeps exactly one judged generation per cohort partition (refusing a second revision) with no re-judge switch, re-runs fully when nothing was sealed, and does not know the inference slice — the `evaluate` CLI subcommand runs the 7.1 `infer` first and calls the use case only if it succeeded.
context_stage: 8.1-confirmatory-run
bounded_context: evaluation
---

# ADR 8.1.0001 — Confirmatory run orchestration: guards, status, replay

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — items 3 and 5 (G4, replay) amended by
[ADR 8.1.0004](./8_1_0004-single-judgment-attempt-log-committed-record-deviation.md)
(attempt log, live generation, committed record, deviation).

## Context

Every piece of the confirmatory evaluation exists and was proven on synthetic
silver, but nothing runs them in sequence on the real cohort
`aapl_confirmatory-r0-665f45d9169a`:

- `infer` (7.1) reproduces the test rows from the 60 checkpoints and completes
  the `calib` partition idempotently; `RunInference` takes a modeling
  `CohortSpec` and acquires the data-root writer lock itself (ADR 7.1.0004
  item 5).
- `RefreshGold` (6.4–7.3) regenerates the whole generation of a partition and
  publishes it as `current/`, replacing the previous one (ADR 6.4.0005 items
  4–5). It does **not** check any preregistration anchor; it has a
  single-writer **precondition** and no lock (item 6).
- `BuildConfirmatoryScorecard` (6.5) validates chain, hash and anchor of the
  revisions, then reads the live generation and decides the verdict. The
  validation is private to the use case.
- No CLI subcommand publishes gold today.
- The Step 8 domain gate requires the judged generation to be preserved
  before any other refresh (R-PRESERVA) and its identity, commit, environment
  and seeds to be recorded (domain doc reproduction §4.5).
- Blinding (evaluation §8.2, B-ORDEM): no confirmatory metric on the cohort
  before the judged revision is anchored. r3 is anchored
  (`aapl_confirmatory-r3-00fd83d9cd39`, 2026-10-21T17:41:23Z).

Forces: the run is the first and only confirmatory judgment, so its replay
semantics decide whether the study can be re-judged after seeing a result;
the slices stay independent (ADR 0.0.0053); the orchestrator holds no domain
rule (skill `orchestrator-design`).

## Decision

```
[decision:E] 8.1-F1 — order of guards and effects
Escolha: G1 resolve the judged revision (chain, hash = expected, every anchor) → G2 refuse dirty code → G3 writer lock → G4 find the judged generation → E1 RefreshGold → E2 scorecard (in memory) → E3 preserve; any guard failure = zero gold publish, zero judged write · Alternativas: refresh first and let the scorecard validate (today's order inside the scorecard); validate only in the runbook
Base: skill orchestrator-design "Side effects after gates … never write then validate"; evaluation §8.2 B-ORDEM (no confirmatory metric before the anchor); ADR 6.5.0003 items 1, 3 (the anchor is checked in code); RefreshGold has no anchor check (refresh_gold.py) — code fact read in this session
Verificado: não verificado (§4.2) — internal sources only
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] 8.1-F2 — where infer runs
Escolha: the `evaluate` CLI subcommand runs the 7.1 `infer` command in the same process and calls the use case only if it raised nothing; the use case receives an inference summary as plain data · Alternativas: consumer port in evaluation satisfied by RunInference; two runbook commands with no chaining · Degrau (C): 1 (cli.py already loads the cohort spec and dispatches commands of three slices; ADR 0.0.0053 consumer ports carry the supplier's DTOs) and 5
Base: ADR 0.0.0053; ADR 7.1.0004 item 5; cli.py `_dispatch_inference_command`
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] 8.1-F3 — status model and replay
Escolha: JUDGED | BLOCKED | ALREADY_JUDGED, failures as exceptions; sealed and intact judged generation → no-op; digest mismatch → refuse; nothing sealed → full re-run (leftovers removed); BLOCKED is sealed like JUDGED and never retried; no re-judge switch · Alternativas: re-run replaces the judged generation; "--force" to re-judge; retry BLOCKED; decide by timestamp · Degrau (C): 1 (ADR 6.4.0005 item 5 removes staging leftovers; ADR 7.1.0002 idempotent completion) and 4 (the most conservative for the confirmatory claim)
Base: evidence-resolution §1 (Gelman & Loken 2014 "garden of forking paths"; Nosek et al. 2018, via evaluation §8.3); domain doc reproduction §4.2 R-BIT (the chain is deterministic in the same environment, so a re-run before the seal reproduces the same result) and §4.6 (a correction after the hash is a deviation); issue #211 (GNU make decides by modification time — counterpart: decide by hash)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim (a re-judge path can be added later by a human decision; it cannot be removed after use)

[decision:C] 8.1-F4 — writer lock
Escolha: the use case holds the existing data-root writer lock (JsonCohortProgressLedger, through a consumer port) from G3 to the end, released in finally · Alternativas: no lock (ADR 6.4.0005 item 6 precondition only); a new gold-only lock · Degrau (C): 1 (ADR 7.1.0004 item 5, same ledger and same operator flag)
Base: ADR 6.4.0005 item 6; ADR 7.1.0004 item 5
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim
```

1. **Use case.** `RunConfirmatoryEvaluation` lives in
   `features/evaluation/application/use_cases/run_confirmatory_evaluation.py`.
   Its `__init__` annotates ports only: the preregistration source and the
   hasher (6.5), local Protocols satisfied by `RefreshGold` and
   `BuildConfirmatoryScorecard`, the `JudgedGenerationStore` (ADR 8.1.0003),
   the consumer port `EvaluationEnvironment` (ADR 8.1.0003) and the consumer
   port `EvaluationWriterLock` (real: `JsonCohortProgressLedger`, duck typing).
   It computes nothing: every judged number comes from `RefreshGold` and the
   scorecard, unchanged.
2. **Resolver extracted.** The chain/hash/anchor validation moves out of
   `BuildConfirmatoryScorecard` into one application function
   (`resolve_judged_revision`) used by both; same errors, same order. The
   orchestrator calls it **before** the refresh (G1); the scorecard keeps
   calling it, so its external behavior is unchanged.
3. **Order.** G1 → G2 (`code_dirty == "false"` and no uncommitted change
   under `config/preregistration/`, whose `.anchor.toml` files G1 reads and
   the 5.5 `code_dirty` does not cover — `DirtyCodeError`) → G3 (lock) → G4
   (`find` for this revision; and any judged generation of **another**
   revision in the partition → `JudgedGenerationExistsError`) → E1 (`RefreshGold(refresh_command_from(plan, ref))`)
   → E2 (scorecard, only if the refresh is `COMPLETED`) → E3 (`preserve`,
   ADR 8.1.0003). The lock is released in `finally`.
4. **Statuses.** `JUDGED` (completed refresh, scorecard produced — whatever
   `academic_decision_ready` says), `BLOCKED` (refresh `BLOCKED`, generation
   preserved with its failed checks, no scorecard), `ALREADY_JUDGED` (G4 found
   a sealed and intact judged generation: no refresh, no scorecard, no write).
   Errors are exceptions; there is no partial status.
5. **Replay.** One judged generation per partition, never overwritten or
   deleted by code. "Per revision" alone would not suffice: a new revision
   (r4) anchored after seeing the r3 verdict would pass G1–G3 and open a
   second judgment, and readiness only reads the `blind_status` the amendment
   declares about itself; so G4 refuses when the partition already holds a
   judged generation of another revision, and re-judging is a human-decided
   deviation outside this path. Tampered or incomplete sealed copy →
   `JudgedGenerationTamperedError` before any effect. Anything that failed
   before the seal leaves nothing judged; a re-run is a full run (staging
   leftovers removed), and because the chain is deterministic in the same
   environment it yields the same results — only provenance differs. A
   `BLOCKED` outcome is final for the revision: re-running until it passes
   would choose the result after seeing it. A correction after the seal is a
   deviation of the plan, decided by the human in its own issue (domain doc
   reproduction §4.6); this Stage adds no switch for it.
6. **`infer` before the use case.** The chaining lives in `cli.py` (the
   process root that already dispatches three slices), not in the evaluation
   CLI module, so `evaluation/adapters/in/cli/` never imports inference
   (Checkpoint A, CA-5). `cli.py` loads the cohort spec, runs the 7.1 `infer`
   through a new function `infer_with_summary` next to `infer` (same
   `RunInference`, which takes and releases its own lock; it returns the
   summary, and `infer` calls it and keeps returning the exit code, so the
   existing contract and its tests do not change — DT-8), and
   only if it raised nothing builds the command — with an inference
   summary as plain data (runs, strict/tolerance counts, max |Δ|, calib rows
   verified) — and calls the use case. No import edge from evaluation to
   inference is added.

## Alternatives considered

### Alternative A — Refresh first, let the scorecard validate (8.1-F1)
- **Description:** call `RefreshGold` and then `BuildConfirmatoryScorecard`,
  which validates chain/hash/anchor before reading the gold.
- **Pros:** no refactor of 6.5.
- **Cons:** the refresh computes every confirmatory metric before anything
  checks the anchor; an unanchored or re-hashed plan would produce (and
  publish) confirmatory numbers.
- **Why rejected:** violates B-ORDEM and "side effects after gates".

### Alternative B — Copy the validation into the orchestrator (8.1-F1)
- **Description:** re-implement chain/hash/anchor checks in the new use case.
- **Pros:** no change to the scorecard.
- **Cons:** two owners of the anchor rule; they drift.
- **Why rejected:** the extraction keeps one owner at the same cost.

### Alternative C — Consumer port for `infer` inside the use case (8.1-F2)
- **Description:** evaluation declares a port satisfied by `RunInference`.
- **Pros:** the use case covers "cohort → scorecard" literally.
- **Cons:** the command carries a modeling `CohortSpec`; `RunInference`
  takes the same writer lock (reentrancy); a new evaluation → inference data
  edge for no new guarantee.
- **Why rejected:** the CLI already holds the spec and sequences slices.

### Alternative D — Two separate runbook commands (8.1-F2)
- **Description:** the operator runs `infer`, then a separate `evaluate`.
- **Pros:** simplest code.
- **Cons:** nothing enforces that `infer` ran and passed right before the
  judgment.
- **Why rejected:** chaining in one subcommand costs a few lines and closes
  that gap.

### Alternative E — Re-run replaces the judged generation / `--force` / retry BLOCKED (8.1-F3)
- **Description:** let a later run overwrite the judged copy, or offer a
  switch to re-judge, or retry a blocked refresh.
- **Pros:** convenient after a defect.
- **Cons:** turns the single judgment into a choice among judgments — the
  forking-paths problem the preregistration exists to prevent; the copy the
  dossier cites could change.
- **Why rejected:** a defect after the seal is a reported deviation, not an
  overwrite.

### Alternative F — Decide replay by timestamps (8.1-F3)
- **Description:** compare modification times of silver and gold (make-like).
- **Cons:** timestamps are provenance, not identity (domain doc §2.2).
- **Why rejected:** replay decides by the seal and its digest.

### Alternative G — No lock (8.1-F4)
- **Description:** rely on the single-writer precondition of ADR 6.4.0005.
- **Pros:** one dependency less.
- **Cons:** nothing stops a concurrent `infer`/`attribute` writing silver, or a
  second `evaluate`, between refresh and copy.
- **Why rejected:** the lock exists and is already used the same way by
  `infer`.

### Alternative H — Do nothing
Running the pieces by hand leaves the anchor check after the metrics, no
preserved judged generation and no record of the environment — the Step 8
domain gate requirements (§4.5) would be unmet.

## Consequences

### Positive
- No confirmatory metric can be computed under an unanchored plan through this
  path, and nothing is published or preserved when a guard fails.
- The study is judged once per cohort partition; re-running is safe and auditable.
- Slice independence is unchanged (no new evaluation → inference edge).

### Negative
- A refactor of `BuildConfirmatoryScorecard` (extraction) and a new CLI
  subcommand.
- A `BLOCKED` real outcome produces no verdict, so the roadmap DoD ("veredito
  mecânico H1/H2/H3 produzido") is not met and cannot be met by re-running:
  the Stage stops with a `[finding]` for a human decision (deviation or DoD
  amendment).
- A real defect found after the seal has no code path; it needs a human
  decision and a deviation record.

### Neutral / trade-offs accepted
- Between `infer` releasing the lock and the use case taking it there is a
  short window; the run has one operator.
- `ALREADY_JUDGED` still runs `infer` first (the CLI chains it); it only
  verifies, writing nothing when calib is complete.

## Implementation notes

- Fakes for the three new ports in `tests/fakes/features/evaluation/`; the
  guard order is tested by counting calls on the fakes (zero `publish`, zero
  `preserve`).
- The real run is the last Task, on the main checkout's data root mounted into
  the worktree container; tests use synthetic silver only (blinding).

## References

- Related ADRs: [6.4.0005](./6_4_0005-gold-full-refresh-per-cohort-partition.md),
  [6.5.0003](./6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md),
  [7.1.0002](./7_1_0002-calib-predictions-in-fact-oos-predictions-idempotent-completion.md),
  [7.1.0004](./7_1_0004-checkpoint-resolution-before-load-and-write-ahead-inference-manifest.md),
  [0.0.0061](./0_0_0061-step-8-compares-own-run-reproduction-and-internal-prior-equivalence.md),
  [8.1.0002](./8_1_0002-silver-content-hash-exact-rows-consumed-by-refresh.md),
  [8.1.0003](./8_1_0003-judged-generation-preserved-copy-run-record-attestation.md)
- Domain: `docs/domain/evaluation/reproduction-equivalence-and-reporting.md` §3,
  §4.2, §4.5, §4.6; `docs/domain/evaluation/probabilistic-forecast-evaluation.md` §8.2
- External: Gelman & Loken 2014; Nosek et al. 2018 (via evaluation §8.3)
- Issue: #211; concept 8.1 D1–D3, D8
