---
title: ADR 8.2.0001 — The reproduction of the judged generation runs in the judged commit (060537fc), from the input backup restored into a disposable data root, calling RefreshGold and BuildConfirmatoryScorecard directly — never RunConfirmatoryEvaluation, never the live partition
description: Architecture Decision Record
when-use: Reference before running or re-running the 8.2 reproduction, before proposing to reproduce at HEAD, or when asking why the reproduction does not go through the 8.1 orchestrator
keywords: [adr, evaluation, reproduction, r-bit, r-bit-commit, r-preserva, judged-generation, disposable-data-root, input-backup, ast, docstring]
status: accepted
created_at: 2026-10-23
updated_at: 2026-10-23
adr_id: 8.2.0001
decision: The 8.2 reproduction checks out 060537fc (the commit of the run record and the tag) in a detached worktree, restores the input backup recorded in the .judged.toml into a disposable data root outside data/cohorts/ (verified by sha256sum -c against the listing whose sha256 is recorded), and calls that commit's wire_dependencies with Settings(data_root=<disposable>) → resolve_judged_revision → RefreshGold(refresh_command_from(plan, ref)) → BuildConfirmatoryScorecard, in the run's image and CPU limits; it never calls RunConfirmatoryEvaluation, infer, the judged store's preserve or record_attempt, and never writes under the live partition; HEAD is only confirmed by a per-file AST comparison with docstrings removed.
context_stage: 8.2-equivalence-audit
bounded_context: evaluation
---

# ADR 8.2.0001 — Reproduction at the judged commit, in a disposable data root

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The domain doc (reproduction §4.1–§4.2, §4.6–§4.7) requires re-executing
silver → gold → scorecard from persisted artifacts, in a separate destination,
bit for bit in the registered environment and with the calculation path of the
judged generation; the TCC claim (a) "only holds for the reproduction done with
the calculation path of the judged generation (which may require re-executing at
its commit)" (R-BIT-COMMIT). Between `060537fc` and HEAD, `src/` changed in 15
files by formatting and one module-docstring passage, so `code.src` differs.

The 8.1 orchestrator `RunConfirmatoryEvaluation` adds guards and judgment
effects on top of `RefreshGold` and the scorecard: attempt log, seal, committed
record as cross truth (ADR 8.1.0004). ADR 6.5.0003 item 4 defines the 8.1 run as
*the* first confirmatory refresh. The live partition holds `current/`, the
sealed copy and `ATTEMPTS.jsonl`; ADR 8.1.0003 item 6b declares the pre-run
backup of the data root the frozen input of the 8.2.

## Decision

1. **Commit.** Run the reproduction in a detached worktree of `060537fc`. The
   probe there must give `code.src` `4d2b2540…`, `code.uv_lock` `0f36050a…`,
   clean tree, and no non-code difference against the `started` attempt line
   (same image `sha256:b69a7620…`, same `--cpus`).
2. **Input.** Copy `data/backups/aapl-pre-8.1-20261023-084758` into a disposable
   data root outside `data/cohorts/`; `sha256sum -c` against its listing, whose
   sha256 must equal `input_backup_sha256` of the `.judged.toml`.
3. **Calculation path only.** In that tree: `wire_dependencies(Settings(data_root=<disposable>))`,
   `resolve_judged_revision`, `refresh_gold(refresh_command_from(plan, ref))`,
   `build_confirmatory_scorecard(...)`. No `infer`, no `RunConfirmatoryEvaluation`,
   no `preserve`, no `record_attempt`, no tag, no comment.
4. **Identity before result.** The reproduced manifest must carry the judged
   `silver_content` digest and dataset fingerprint; otherwise it is another run
   and is not compared as a result.
5. **Live partition untouched.** sha256 of `current/MANIFEST.json`,
   `judged/ATTEMPTS.jsonl` and the copy's `CONTENTS.sha256` are recorded before
   and after.
6. **HEAD confirmation.** For each `src/` file in `060537fc..HEAD`, compare
   `ast.dump` of both versions with docstrings stripped (docstrings are
   `Expr(Constant)` nodes and are part of the AST). The result is recorded; it
   does not replace step 3.

## Alternatives considered

### Alternative A — Reproduce at HEAD
- **Pros:** uses the current code; no extra worktree.
- **Cons:** the claim would rest on an argument about the diff (R-BIT-COMMIT),
  not on the judged `code.src`.
- **Why rejected:** the domain doc prefers the judged calculation path for the
  citable claim; running at `060537fc` costs one worktree.

### Alternative B — `RunConfirmatoryEvaluation` over the disposable root
- **Pros:** one command, same stdout.
- **Cons:** at HEAD, G4 refuses (the committed `.judged.toml` names a sealed copy
  absent from the new root); at `060537fc` it would seal a second `judged/`
  — a second judgment of the same revision, against ADR 8.1.0004.
- **Why rejected:** the orchestrator is judgment, not calculation.

### Alternative C — Reproduce in the live partition / restore over `data/cohorts/aapl`
- **Cons:** the refresh replaces `current/` (ADR 6.4.0005 items 4–5); the live
  `ATTEMPTS.jsonl` and the sealed copy would be at risk.
- **Why rejected:** R-PRESERVA and doc §4.6.

### Alternative D — Do nothing (rely on the 8.1 replay)
- **Cons:** the 8.1 replays returned `ALREADY_JUDGED` without recomputing;
  nothing was re-executed.
- **Why rejected:** the roadmap DoD and claim (a) require a real re-execution.

## Consequences

### Positive
- The claim (a) uses literally the judged `code.src` and environment.
- No new orchestration code; the live partition is never written.

### Negative
- Needs the run image to stay available; a pruned image makes R-BIT impossible.
- The reproduction command is a runbook step, not a CLI subcommand (the
  subcommand would not exist at `060537fc`).

### Neutral / trade-offs accepted
- Between-environment reproduction (R-ENV, claim (c)) is not executed (single
  environment).

## Implementation notes

The exact commands, the disposable path and the probe line follow the 8.1
technical Etapa R (pre-flight, `$RES`, image id) and live in the 8.2
technical. The comparison runs from the 8.2 branch (ADR 8.2.0002).

## References

- Related ADRs: 6.4.0005, 6.5.0003, 7.1.0003, 8.1.0003, 8.1.0004, 8.2.0002
- Domain doc reproduction-equivalence-and-reporting §2.2, §4.1–§4.7
- Python 3.12 Glossary "docstring"; `ast` module docs
- Issue #232
