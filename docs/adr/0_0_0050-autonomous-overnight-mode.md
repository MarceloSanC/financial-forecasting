---
title: ADR 0.0.0050 — Autonomous overnight stage execution mode
description: Architecture Decision Record
when-use: Reference when auditing a stage executed in autonomous mode, or before changing the autonomous-run rules
keywords: [adr, process, autonomous, overnight, git, auto-merge, stage-audit]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: 0.0.0050
decision: Authorize an autonomous overnight run of stages 1.1→4.3 where the agent self-merges, with a clean-context audit substituting the human approval gate.
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0050 — Autonomous overnight stage execution mode

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

Scope-limited: applies to the autonomous overnight run of **Steps 1–4 (stages 1.1→4.3)** only. Step 5+ (statistical core: metrics, DM/MCS/Holm, calibration, conformal) is explicitly **out of scope** and requires a human in the loop.

## Context

Steps 1–4 are largely software-plumbing and well-specified domain modeling whose decisions are already taken or documented (roadmap, overview, the previous repo as reference). Marcelo authorized (2026-06-29) running these stages **overnight, unattended**, following `docs/PROMPT-stage-single-session.md` plus a `stage-audit` pass per stage.

Two written rules conflict with unattended self-merge:

- `docs/PROMPT-stage-single-session.md` §"REGRA DE FECHAMENTO E PR" forbids the agent from running `gh pr create` / `git push` / `gh pr merge` — the human closes each stage.
- `docs/GIT-WORKFLOW.md` §"Comportamento bloqueante" lists "merge without ≥ 1 approval" as an absolute stop.

Forces:
- The stage chain is **dependency-ordered**: stage N+1's real prerequisite is "N merged into `develop`" (per `stage-audit` skill). So merging per stage is load-bearing for the chain to advance overnight.
- **Branch protection is not actually enabled** (GitHub Free, private repo): `gh api .../branches/develop/protection` returns `404 Branch not protected`. The "1 approval" gate is documented-but-unenforced — there is no technical approval gate to bypass.
- An unattended run that papers over a real contradiction is worse than one that stops.

## Decision

For the 1.1→4.3 overnight run only:

1. **The agent self-merges** stage PRs into `develop` without waiting for a human approval. This overrides the prompt's "never PR/merge" rule and the GIT-WORKFLOW "merge needs approval" stop, **for this run only**.
2. The **human approval gate is substituted by a clean-context audit**: each stage is audited by a *fresh-context subagent* running the `stage-audit` skill, which never shares the implementer's context (impartiality per the skill's own Fase D-bis #9). Findings are triaged and fixed before the merge.
3. **All objective gates remain mandatory and unchanged**: `make check` green, coverage ≥ 90% on the stage diff, `check_technical_postexec.py`, the test-audit loop, issue-first, conventional commits with `Refs #`.
4. **Decisions taken outside the initial question round** follow the autonomous decision policy: enumerate options, research trade-offs against concrete references (no unfounded claims), weigh real gain vs real (not overestimated) implementation cost, prefer the simplest swappable solution that does not constrain growth — and record each non-trivial decision as an ADR.
5. **HALT-and-park** (stop the run, record why): contradiction with a higher-hierarchy source (Overview > Roadmap > Concept > Technical), an irreversible external contract that is ambiguous, or any gate that cannot go green.
6. **Git safety**: never force-push; never rewrite merged history of `develop`/`main`. Rebasing the agent's own in-flight branch onto `origin/develop` to drop unrelated commits (GIT-WORKFLOW Etapa 4) is allowed and is not "rewriting old history".
7. **Data**: ingestion stages (2.2/2.3/3.2) reuse existing data copied from the previous repo; API keys are configured only for connectivity smoke-tests, not to fetch new data.

## Alternatives considered

### Alternative A — Agent opens PR, human merges each stage
- **Description:** keep the written rule; agent stops at a green PR, human merges in the morning.
- **Pros:** honors the documented process literally; human eyes on every merge.
- **Cons:** the dependency chain advances ~1 stage/day — defeats the overnight goal entirely.
- **Why rejected:** incompatible with the stated objective (unattended chain through 17 stages).

### Alternative B — Same actor implements and audits
- **Description:** the implementing session also runs the audit.
- **Pros:** simpler, no subagent orchestration.
- **Cons:** context bias — the auditor inherits the implementer's blind spots; `stage-audit` explicitly warns against this.
- **Why rejected:** removes the impartiality that is the whole point of substituting human review.

### Alternative C — Do nothing / status quo (fully manual)
- **Description:** run every stage manually with the human gate.
- **Pros:** maximum control.
- **Cons:** does not deliver the requested autonomous throughput on well-specified plumbing stages.
- **Why rejected:** the human's time is better spent on Step 5+ where domain/statistical judgment is decisive.

## Consequences

### Positive
- The 1.1→4.3 chain can run unattended; the human reviews afterward and at Step 5+.
- A fresh-context audit per stage gives an independent check that is recorded.
- `stage-audit` and future sessions read this ADR and will **not** flag self-merge as a blocking violation for this run.

### Negative
- A silent bug merged in an early stage propagates down the chain until an audit or gate catches it. Mitigated by per-stage clean-context audit + objective gates, not eliminated.
- Deviates from two written rules; the deviation is scoped and recorded here, but it is still a deviation.

### Neutral / trade-offs accepted
- We accept that the run may HALT partway (contradiction, gate, or ambiguity) and wait for a human, rather than force progress.

## Implementation notes

- Per-stage loop: issue+branch+`docs/stages/N.M/` → implementer subagent (fresh) runs the autonomous prompt variant → auditor subagent (fresh) runs `stage-audit` → main session triages findings, fixes, records ADRs/issues → `stage N.M: complete` → PR → auto-merge → `git sync` → next stage.
- The autonomous prompt variant lives at `docs/PROMPT-stage-single-session-autonomous.md`.

## References

- Related: `docs/PROMPT-stage-single-session.md`, `docs/GIT-WORKFLOW.md` §Gates/§Comportamento bloqueante, `.claude/skills/stage-audit/SKILL.md` (Fase B prereq note + Fase D-bis #9).
- Memory: `autonomous-overnight-run`, `autonomous-decision-policy`.
- Conversation: planning session 2026-06-29.
