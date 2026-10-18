---
title: ADR 0.0.0058 — A planned budget of 1–3 full gates per Stage instead of a gate on every Task
description: Architecture Decision Record
when-use: Reference when writing the gate plan of a technical.md (Fase 3B), deciding what to run before a Task commit, adding a fourth full-gate point to a Stage, or before re-introducing a mandatory per-Task or per-Checkpoint gate
keywords: [adr, process, gates, make-check, check-task, check-block, gate-plan, budget, tdd]
status: accepted
created_at: 2026-10-17
updated_at: 2026-10-17
adr_id: 0.0.0058
decision: Each Task runs only the tests it wrote or changed (plus the pre-commit hooks); the full `make check` runs only at the 1–3 points per Stage/issue that the technical.md gate plan names, the exit gate included, and any point beyond 3 needs an explicit written justification. `check-task` and `check-block` stop being mandatory.
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0058 — A planned budget of 1–3 full gates per Stage instead of a gate on every Task

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — issue #185. Amends [ADR 0.0.0055](./0_0_0055-tiered-quality-gates.md): its Decision items 1 (T1 and T2) and 2 (escalation rules) are replaced by the gate plan below. Items 3–7 (`make check` as the only verdict, pytest-xdist, `slow`, cache volumes, the drift guard) still hold.

## Context

ADR 0.0.0055 removed the full `make check` from every commit, but it still put a heavy gate on every Task:

- **T1 on every commit.** `make check-task SLICE=…` runs all the static gates over the whole repo (mypy strict, import-linter, check_layout, fake-parity, port-coverage, arch-ast) plus the whole test suite of the touched slices. In a big slice such as `evaluation` that is most of the suite.
- **T2 at every Checkpoint C.** `make check-block` runs the whole suite every 2–3 Tasks.
- **Escalations.** Any Task that touched `shared/`, the composition root, a dependency, tool config or a shared `conftest.py` escalated to T2 or T3.

Stage 6.6 shows the cost. Its technical.md runs `check-task` at the end of all 22 Tasks and `check-block` at the end of each of its 6 Checkpoint C blocks, plus the exit `make check`. Locally (Docker Desktop on Windows, NTFS bind mount) each of these runs takes many minutes, so execution time went mostly to repeating checks that had not found anything new.

A fixed rule (gate on every Task, every N Tasks, every Task of kind X) cannot tell a risky Task from a routine one. The executor can, when it writes the plan: it knows which Tasks change contracts read by other slices, which ones edit gate config, and which ones only add a pure function and its unit tests.

## Decision

1. **Per Task: only the Task's own tests.** Before each Task commit the executor runs the test files that the Task wrote or changed (`pytest <files> -q --no-cov`). The pre-commit hooks (ruff, ruff-format, mypy) run on the commit as usual. A red test blocks the commit.
2. **A gate plan in the technical.md.** In Fase 3B the executor writes a gate plan in §1 of the technical.md. The plan lists the Tasks after which the full `make check` runs and gives the reason for each one.
3. **Budget: 1–3 full gates per Stage or issue, the exit gate included.** The exit gate (RUNBOOK Passo 10) is always one of them. A 4th or later point is allowed only with an explicit justification in the plan, stating what concrete risk that point catches which the next planned point would catch too late. "To be safe" is not a justification. When the need comes up during execution, the extra point is recorded as a `[deviation]` in §7 with the same justification.
4. **Where to place a mid-Stage point.** A mid-Stage point goes right after the last Task of a group whose break would invalidate the Tasks that follow. Typical cases are a change to a port or contract read by another slice, a change to `shared/` or the composition root, and a change to dependencies, tool config, gate scripts or a shared `conftest.py`. The executor orders the Tasks so that these changes cluster, so that one point covers them all. A Stage with none of these needs only the exit gate.
5. **`check-task` and `check-block` become optional tools.** The targets stay in the Makefile. The executor may run `check-task` when it has a concrete reason, for example a new import across layers that it wants import-linter to confirm before building on it. It does not run it as a routine step. `check-block` costs nearly as much as `make check` and counts against the budget.
6. **Checkpoint C stays and no longer carries a gate.** The independent subagent review per block of Tasks continues. It does not run `check-block` any more.
7. **A red full gate** is fixed with a `fix(<scope>): ... [N.M/task-NN-fix]` commit before the next Task, as before.
8. **`make check` stays the only verdict**, identical to CI (ADR 0.0.0055 item 3, ADR 1.2.0010).

The operational rules have a single source, `docs/RUNBOOK-STAGE-LIFECYCLE.md` §Gates em camadas.

## Alternatives considered

- **Keep ADR 0.0.0055 as is.** Rejected. The per-Task T1 and per-block T2 make most of the Stage's time go to gates that rarely find anything new, as Stage 6.6 shows.
- **A fixed cadence, such as `make check` every N Tasks.** Rejected. It spends the same budget on a Stage of pure functions as on a Stage that rewires the composition root. Placing the points by judgement, written down in the plan, spends it where the risk is.
- **Drop mid-Stage gates and keep only the exit gate.** Rejected as the rule, kept as the default for low-risk Stages. When a Task changes a contract that later Tasks build on, finding the break only at the exit means several Tasks to redo.
- **Change-based test selection (pytest-testmon) per Task.** Still deferred, for the reasons in ADR 0.0.0055.

## Consequences

- **Positive:** a Stage pays 1–3 full gates instead of one heavy gate per Task plus one suite per block.
- **Positive:** the plan makes the risk assessment visible and reviewable. Checkpoint B reviews it together with the rest of the technical.md.
- **Negative:** a commit between two gate points can be red outside its own tests, for example a mypy error in a module that imports the changed one, or a test in a slice it did not touch. The next planned point catches it, and the fix may need a bisect over more commits than under ADR 0.0.0055. That trade is accepted on purpose.
- **Negative:** commit-level green now means only "the Task's own tests and the pre-commit hooks passed". `git bisect` on a feature branch may hit commits that are red elsewhere. Gate points and CI still guarantee green at the points that matter: each planned point, the exit gate and the merge.
- **Negative:** the quality of the plan depends on the executor's judgement. The budget cap and the justification rule make a bad plan visible, but they do not prevent one.

## References

- Issue #185.
- [ADR 0.0.0055](./0_0_0055-tiered-quality-gates.md): tiered gates, amended here.
- ADR 1.2.0010: `make check` == CI with coverage.
- `docs/RUNBOOK-STAGE-LIFECYCLE.md` §Gates em camadas: the operational single source.
- `docs/stages/6.6-scorecard-profiles/technical.md`: per-Task `check-task` and per-block `check-block`, the cost measured in Context.
