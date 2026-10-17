---
title: ADR 0.0.0058 — Architecture harness in three layers — deterministic gate, edit-time hook, read-only reviewer agent
description: Architecture Decision Record
when-use: Reference before adding an architecture rule to the harness (script, hook, skill or subagent), before adding a hook of type prompt/agent, or before copying gate logic into a skill or hook
keywords: [adr, harness, architecture, fitness-function, hook, posttooluse, subagent, skill, baseline, claude-code]
status: accepted
created_at: 2026-10-17
updated_at: 2026-10-17
adr_id: 0.0.0058
decision: Every architecture rule lives in exactly one of three layers — a deterministic gate in `scripts/` (the verdict, run by `make check`/CI), a command `PostToolUse` hook that re-runs those same gates on the edited file (feedback, never the verdict), or the read-only `architecture-reviewer` subagent for rules a script cannot express (judgment, cites rule + source) — and the skill `architecture-fitness` is the catalog that ties each rule to its source and its layer, with a thin runner that imports the gates instead of copying them.
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0058 — Architecture harness in three layers — deterministic gate, edit-time hook, read-only reviewer agent

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — issue #161.

## Context

Issue #61 shipped four AST gates (`check_use_case_deps`, `check_domain_determinism`, `check_schema_literals`, `check_vo_invariants`) on top of the import-linter contracts (ADR 1.3.0001) and the declared baseline of `scripts/arch_baseline.toml` (issue #62). They answer at `make check` time, which in a Stage is at the end of a Task (T1, ADR 0.0.0055). Two gaps remained:

- **Late feedback.** An agent that writes `datetime.now()` into a domain module learns about it only when it runs the gate, several edits later.
- **Rules no script expresses.** Issue #61 put two rules explicitly out of scope for scripts: vendor vocabulary in ports ("only expressible as a curated denylist of identifiers, high false-positive rate … ADR + code review, not script") and mutable state in adapters ("implementable, but noisy against lazy proxies and legitimate rate limiters"). Nothing reviews them today.
- **Uncited skills.** The architecture skills (`hex-arch-python`, `ddd-tactical-patterns`, `composition-root`, `pytest-with-fakes`, `import-linter-rules`) state rules without any primary source.

What the Claude Code mechanisms guarantee (official docs, read literally on 2026-10-17):

- **Hooks are the deterministic layer.** "Claude Code runs them at specific points in its lifecycle, which gives you deterministic control: certain actions always happen rather than relying on the LLM to choose to run them." (code.claude.com/docs/en/hooks-guide). On `PostToolUse`, exit code 2 "Shows stderr to Claude; the tool already ran" (code.claude.com/docs/en/hooks, §Exit code 2 behavior per event). "Agent hooks are experimental and may change." (same page).
- **Subagent `skills:` preloads the whole skill.** "The full skill content is injected, not only the description." (code.claude.com/docs/en/sub-agents, frontmatter table).
- **Skill layout.** "Keep SKILL.md body under 500 lines"; "Keep references one level deep from SKILL.md"; "For reference files longer than 100 lines, include a table of contents at the top"; utility scripts are "executed, not loaded" and "Only the script's output consumes tokens" (platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices).

## Decision

1. **Three layers, one home per rule.**
   - **Gate (verdict).** A script under `scripts/`, wired into `make check` and CI. It is the only layer whose result counts as evidence (ADR 0.0.0055 item 3). A rule that can be expressed as a script with an acceptable false-positive rate goes here, with a regression test in `tests/architecture/` that proves it fails on an injected violation.
   - **Hook (feedback).** A `command` hook only. No `prompt` or `agent` hook type: those are not deterministic, and the agent type is experimental. The hook re-runs the existing gates; it never decides anything a gate does not decide. A hook that crashes or meets an unexpected input exits 0 (fail open), because `make check` still holds the verdict.
   - **Reviewer agent (judgment).** A read-only subagent for rules that a script cannot express without an unacceptable false-positive rate. Each finding cites the rule and its source. Its output is input to a human or to an audit session; it never edits code and is not a gate.
2. **The skill `architecture-fitness` is the catalog.** For each rule, `SKILL.md` states the violation, the primary source (literal quote + locator), the layer and the gate that enforces it, and how to fix it. Only quotes checked against the raw source by the `evidence-verifier` enter; a source not read literally stays out (it is listed as a gap, not cited).
3. **No copied gate logic.** The skill's runner (`scripts/check_changed.py` inside the skill) imports each gate module, calls its `scan()`, reconciles with the baseline through `arch_baseline_lib`, and keeps only the keys of the files in question. It works because every AST gate key starts with `<relative file>::`. Copying the rules would be the duplication that `check_schema_literals` itself rejects ("Every piece of knowledge must have a single, unambiguous, authoritative representation within a system", Hunt & Thomas, Tip 15).
4. **`PostToolUse` hook `arch_feedback`** on `Edit|Write`. When the edited file is a `.py` under `src/`, it calls the runner on that file. If there are violations outside the baseline, or baseline entries of that file that no longer occur, it prints them to stderr and exits 2. The repo root is found from the edited file (the nearest ancestor holding `scripts/arch_baseline.toml`), not from `CLAUDE_PROJECT_DIR`, because sessions opened in the main checkout edit files in worktrees (`scripts/worktree-new.py`).
5. **Subagent `architecture-reviewer`.** `tools` restricted to reading (`Read, Grep, Glob, Bash` for `git diff`/`git show`), the skill preloaded through `skills: [architecture-fitness]`, and dispatchable by the `stage-audit`/`issue-audit` sessions.
6. **`scripts/check_harness.py` enforces the layout** the docs only recommend: `SKILL.md` ≤ 500 lines, `reference/` one level deep with a table of contents above 100 lines, scripts named by a skill exist, every `skills:` entry of a subagent exists, and every hook script named in `.claude/settings.json` exists.
7. **Conventions doc.** `docs/HARNESS.md` is the single home for the conventions of subagents and hooks (until now `docs/PIPELINE.md` §13 covered skills only).

## Alternatives considered

- **`prompt`/`agent` hook that reviews every edit.** Rejected. Non-deterministic, costs a model call per edit, and the agent type is experimental. The judgment layer runs on demand (audit), not on every keystroke.
- **Give each gate a `--paths` option and let the hook call the CLI.** Rejected. It changes four gate CLIs to serve a consumer, and the four would each re-implement the same path filter. Filtering on the key prefix in one runner keeps the gates untouched. A full scan of the four gates costs ~1 s, so filtering after the scan costs nothing that matters.
- **Turn the two non-scriptable rules into gates with a denylist.** Rejected for the reasons recorded in #61 (out of scope): a curated identifier denylist has a high false-positive rate and turns every PR into a naming argument.
- **Rewrite the existing architecture skills with citations.** Out of scope for #161; it can become its own issue now that the catalog exists.

## Consequences

- **Positive:** a domain/use-case/VO violation shows up on the edit that introduced it, with the rule and the fix, instead of at the next `make check`.
- **Positive:** the non-scriptable rules get a reviewer that cites sources, without pretending to be a gate.
- **Negative:** the hook runs the host `python`; the runner and the gates must stay stdlib-only (they already are — `tomllib`, `ast`).
- **Negative:** a new AST gate must be registered in the runner's gate list; a unit test compares that list with the `arch-ast` target of the `Makefile`, so forgetting it fails the build.
- **Neutral:** the hook only sees files edited through `Edit`/`Write`; edits made by shell commands are caught by `make check`, as before.

## References

- Issue #161; issue #61 (§Fora de escopo: the two non-scriptable rules); issue #62 (baseline).
- ADR 1.3.0001 (import-linter as fitness function); ADR 0.0.0055 (tiered gates; `make check` is the only verdict).
- Claude Code docs: <https://code.claude.com/docs/en/hooks>, <https://code.claude.com/docs/en/hooks-guide>, <https://code.claude.com/docs/en/sub-agents>, <https://code.claude.com/docs/en/skills>.
- Skill authoring best practices: <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices>.
