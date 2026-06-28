---
title: ADR 0.0.0000 — Adopt the documentation-driven development standard
description: Meta-ADR explaining why this project follows the docs-first standard with concept/technical phases per Stage
when-use: Reference when onboarding a new contributor, or when questioning whether a Stage justifies the upfront documentation cost
keywords: [adr, meta, documentation, process, planning]
status: accepted
created_at: 2026-05-08
updated_at: 2026-05-15
adr_id: "0.0.0000"
decision: Adopt the multi-phase documentation-driven flow (overview → roadmap → per-Stage concept → per-Stage technical → execution by Task) as the development standard for this project
context_stage: 1.1-bootstrap
---

# ADR 0.0.0000 — Adopt the documentation-driven development standard

> Numbered `0000` because this ADR governs the rule by which other ADRs (and other docs) exist. It is a meta-decision and is placed at the project's first Stage (`1.1-bootstrap`).

## Status

`accepted`

## Context

This project is built collaboratively with AI coding assistants (Claude.ai for planning, Claude Code and Codex for execution). We've observed in past work that two failure modes dominate:

1. **Context fragmentation across sessions.** AI assistants don't share memory between sessions. Each new conversation starts from zero unless we hand it the relevant artifacts. Without standardized artifacts, every session begins with a 10-minute re-explanation of the project, and details drift between sessions.

2. **Implementation drifting from intent.** When a coding session starts without a clear plan, the assistant fills the gap with plausible-looking choices. Some are fine; some create silent technical debt. By the time the issue surfaces in production or PR review, the original intent has been forgotten.

Additional forces:

- Small team (2 senior engineers, full-stack + ML). No room for process overhead that doesn't pay back within weeks.
- Multiple projects expected to follow the same standard (data intelligence multi-agent system, computer vision for MES, and others). A standard amortizes its own cost across projects.
- Documents must serve three audiences simultaneously: humans (reading, reviewing), Claude.ai (loaded as session context), and code assistants (consumed as execution plan).
- Some artifacts must be readable by non-technical stakeholders (HR, Legal in the CV/MES project).

## Decision

Adopt a documentation-driven development standard with the following structure:

1. **Project-level docs** (`docs/overview.md`, `docs/roadmap.md`): produced from Phase 1 (Overview) and Phase 2 (Roadmap); serve as base context for the project. The roadmap decomposes work into Steps (business deliverables) and Stages (atomic units of technical work).

2. **Per-Stage docs** (`docs/stages/N.M-<slug>/concept.md` and `technical.md`): produced in Phase 3A (Concept) and Phase 3B (Technical), one pair per Stage.
   - `concept.md` answers *what* and *why*, including relevant technical decisions.
   - `technical.md` is an executable plan broken into Tasks (`N.M/task-NN`) that Claude Code or Codex can consume task-by-task without inferring critical details.

3. **Auxiliary docs as needed**: ADRs (mandatory for non-obvious decisions, all stored together at `docs/adr/N_M_NNNN-<slug>.md` — the `N_M` filename prefix separates by Stage, no per-Stage subfolder), runbooks (for recurring operational procedures).

4. **Session protocol**: defined prompts and gates per phase (see `docs/PIPELINE.md` and the `RUNBOOK-*.md` family). New session per phase change. New session for back-tracking when a later phase reveals a problem in an earlier one.

5. **Versioning**: docs live in `docs/` of the project repo. Updates to docs travel in the same PR as the code changes they describe. Closing a Stage requires updating the roadmap (`last_reviewed_at` + Stage `status: done`) in the same PR.

The complete standard is defined in the `whaka-dev-project-template` repository, with templates, conventions (`docs/CONVENTIONS.md`), pipeline definition (`docs/PIPELINE.md`), and runbooks.

## Alternatives considered

### Alternative A — Lightweight READMEs only
- **Description:** Single README per project, ad-hoc notes per feature in PR descriptions.
- **Pros:** Minimal overhead; familiar to most developers.
- **Cons:** PR descriptions are not consumable as session context for a new Claude session. Decisions get buried in PR threads, unfindable months later. No structured way to plan multi-stage work.
- **Why rejected:** This is what we had before. The failure modes described in Context come precisely from this setup.

### Alternative B — Issue tracker as source of truth (Linear, Jira, GitHub Issues)
- **Description:** Use issue tracker for planning; PR descriptions for execution; minimal repo-side docs.
- **Pros:** Strong status tracking; built-in collaboration; ticket → branch → PR linkage is automatic in many tools.
- **Cons:** Issues are optimized for status, not for context loading into AI sessions. Markdown in issue trackers is fragmented and hard to grep. Versioning of decisions is poor. AI assistants don't natively have access to issue trackers without extra tooling.
- **Why rejected:** Issue tracker is complementary, not a substitute. We may use one *in addition* to the docs standard for status tracking, but the canonical source of project context lives in `docs/`.

### Alternative C — Inline doc-as-code only (docstrings, type hints, ARCHITECTURE.md)
- **Description:** Document the codebase from within the code (docstrings, ARCHITECTURE.md), no planning docs.
- **Pros:** Documentation stays close to code; less duplication.
- **Cons:** Documents the *what is* but not the *why* or *what's planned*. AI assistants asked to extend the project must infer plans from code alone. Decisions invisible in code (rejected alternatives, deferred work) are lost.
- **Why rejected:** Code-as-doc is great for "how does this work today"; useless for "what are we going to build next month and why".

### Alternative D — Status quo (do nothing, ad-hoc)
- **Why rejected:** See Context section. The cost of doing nothing is the failure modes we're already living with.

## Consequences

### Positive

- **Reproducible session bootstrap.** Any new Claude.ai session about Stage `N.M` is identical: load `overview.md`, `roadmap.md`, this Stage's `concept.md`, relevant ADRs. No 10-minute warm-up.
- **Executable plans.** `technical.md` is structured so that Claude Code or Codex can pick up Task `N.M/task-NN`, execute, verify, commit, and move on — without midstream questions for the human.
- **Decisions outlive the people who made them.** ADRs survive turnover, context loss, and "I forget why we did it that way".
- **Status is visible.** Reading `roadmap.md` answers "where is the project" in 30 seconds.
- **Standard is reusable.** The same flow applies to every new project; we don't reinvent process per project.

### Negative

- **Upfront cost.** Setting up `overview` + `roadmap` + first Stage's concept takes a few sessions before any code lands. For genuinely throwaway prototypes, this is overkill.
- **Risk of bureaucracy.** If we treat the standard as ritual rather than tool, it will accumulate ceremony and lose value. We must aggressively cut anything that stops serving a real purpose.
- **Maintenance discipline required.** Roadmap that lies is worse than no roadmap. Closing a Stage *must* update the roadmap (hence the gate in the standard).
- **Documents can become stale despite gates.** A `technical.md` written before a step starts and not updated mid-execution is a known risk; mitigation is explicitly part of the standard but it can still fail.

### Neutral / trade-offs accepted

- We accept that the standard does not fit single-script utilities or one-off scripts. For those, README + script comments suffice; the standard is for projects expected to live > 1 month and grow.
- We accept that some redundancy will exist between `concept.md` and `technical.md` for a given Stage. The line between them is "executability," not "no overlap."
- We accept that documents in Portuguese (for human-facing artifacts) and English (for ADRs, runbooks, code) creates a bilingual repo. Worth it for the audience match.

## Implementation notes

- The standard pack lives in the `whaka-dev-project-template` repository (separate from this project's `docs/`). New projects bootstrap by following `RUNBOOK-INIT-PROJECT.md` in that template, which copies `boilerplate/layout-files/` (including this ADR) into the destination project.
- A reusable boilerplate exists at `whaka-dev-project-template/boilerplate/layout-files/` that materializes the destination project's structure (source layout, CI, docs, runbooks) and is the input to Stage `1.1-bootstrap`.
- The standard is not frozen. When a recurring pain point emerges, propose a change to the standard via PR on the template repo. Update affected projects opportunistically, not eagerly.

## References

- Standard pack: `whaka-dev-project-template/README.md`, `boilerplate/layout-files/docs/PIPELINE.md`, `boilerplate/layout-files/docs/CONVENTIONS.md`, `RUNBOOK-INIT-PROJECT.md`, `RUNBOOK-ADOPT-EXISTING.md`
- Cosmic Python (Percival & Gregory) — architectural reference
- "Documenting Architecture Decisions" (Michael Nygard, 2011) — origin of the ADR format
