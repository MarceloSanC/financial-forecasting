---
title: ADR 0.0.0055 — Tiered quality gates instead of the full make check on every commit
description: Architecture Decision Record
when-use: Reference when deciding which gate to run before a Task commit, at a Checkpoint C, or at stage exit; before re-introducing the full gate per commit; before marking a test `slow`
keywords: [adr, process, gates, make-check, check-task, check-block, pytest-xdist, slow, ci, tdd]
status: accepted
created_at: 2026-09-27
updated_at: 2026-09-27
adr_id: 0.0.0055
decision: Replace "make check green before every commit" with five tiers — T0 TDD loop, T1 per-Task `make check-task SLICE=…` (static gates + touched-slice tests, no coverage, no `slow`), T2 per-Checkpoint-C `make check-block` (full suite in parallel, no coverage), T3 stage exit and T4 CI both `make check` unchanged — and parallelize the suite with pytest-xdist.
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0055 — Tiered quality gates instead of the full make check on every commit

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — issue #110.

## Context

`PROMPT-stage-single-session.md` §Passo 5 required "`make check` green before every commit". `make check` is the full gate: ruff, mypy strict, check_layout, import-linter, fake-parity, port-coverage, docs-check and the whole pytest suite with coverage ≥ 90%.

Measured on 2026-09-27:

- **CI runner (Linux):** `make check` took ~5 min. pytest ran 2230 tests in 3m27s serially, and every other gate took under 1 min combined.
- **Local dev (Docker Desktop on Windows, source bind-mounted from NTFS):** ~30 min per run. A stage of 8–12 Tasks paid this cost 8–12 times.
- **Where the pytest time goes:** one module, `tests/integration/features/modeling/test_train_tft.py`, took ~58 s of the 207 s (three real TFT trainings). No other file took more than ~27 s, and that one spread over 129 tests.

Sources consulted agree on one model. Checks that are fast and scoped to the change run early and often. The full gate still exists and stays blocking, but it runs later:

- *Software Engineering at Google*, ch. 23: presubmit runs "only fast, reliable ones", limited to "the project where the change is happening". TAP then runs "all potentially affected tests, including larger and slower tests" after submission. <https://abseil.io/resources/swe-book/html/ch23.html>
- Fowler, *Continuous Integration*: a commit stage with localized unit tests and test doubles, and a secondary stage with the heavier suites. "99.9% green is still red." <https://martinfowler.com/articles/continuousIntegration.html>
- DORA, *Continuous integration*: when tests take longer than about 10 minutes, "developers won't want to run them frequently". The fix is to parallelize, or to split long-running tests into a separate stage. <https://dora.dev/capabilities/continuous-integration/>
- Shopify Engineering runs a selected subset per PR and "the full test suite every deploy". <https://shopify.engineering/spark-joy-by-running-fewer-tests>

## Decision

1. **Five tiers.** The operational table and its rules have a single source, `docs/RUNBOOK-STAGE-LIFECYCLE.md` §Gates em camadas:
   - **T0: TDD loop.** Run the single test being written.
   - **T1: before every Task commit.** `make check-task SLICE=<slices>` runs every static gate plus the tests of the touched slices, with no coverage and no `slow`. `tests/architecture/` is left out of T1 because it tests the gates themselves, which already run directly in T1. Those tests also cost minutes locally, since each one rebuilds the import graph without cache, and a Task that edits the gates escalates to T3 anyway.
   - **T2: at every Checkpoint C.** `make check-block` runs the static gates, docs-check and the whole suite including `slow`, in parallel and without coverage.
   - **T3: at stage/issue exit and before the push that opens the PR.** `make check`, unchanged.
   - **T4: CI.** `make check`, unchanged.
2. **Escalation rules.** Some Tasks cannot be judged by one slice's tests, so their T1 escalates:
   - A Task touching `shared/`, the composition root or another multi-slice module takes T2 as its T1.
   - A Task touching dependencies, tool config or a shared `conftest.py` takes T3.
3. **`make check` stays the only verdict.** It is identical to CI (ADR 1.2.0010, I7). Only a green T3 counts as gate evidence in PRs, audits and exit checklists.
4. **pytest-xdist** is added. `make test` and every tier run with `-n auto --dist loadgroup`, and `tests/conftest.py` assigns the groups:
   - **One group per file**, which gives `loadfile` semantics. Module-scoped fixtures such as the real TFT training run once, not once per worker.
   - **One group for all of `tests/architecture/`.** `test_import_contracts.py` writes probe modules into the real `src/` tree, and the layout, port-coverage and fake-parity gates scan that same tree. The first parallel run, with default distribution, failed 7 of these tests because each worker saw the other workers' injections.

   pytest-cov combines worker coverage, so `fail_under = 90` still applies to the whole suite.
5. **`slow` marker.** It is applied only where measurement shows a cost in minutes; today that is `test_train_tft.py`. It excludes tests from T1 only, and T2, T3 and T4 run everything.
6. **Tool caches on named volumes** (`docker-compose.yml`). The mypy, pytest, ruff and import-linter caches get named volumes, so they stop crossing the Windows→WSL2 bind mount. Ad-hoc `docker run` worktrees do not share them, because the import-linter cache is not concurrency-safe.
7. **A drift pattern in `scripts/check_docs_pointers.py`** rejects paraphrases of the old per-commit rule in the live normative docs.

## Alternatives considered

- **Keep `make check` per commit and only speed it up (xdist, caches).** Rejected as the only measure. It helps, but the per-commit cost would still include coverage, docs-check and the real TFT training on every Task. The sources above say not to put the heaviest checks in the earliest stage.
- **Change-based test selection (pytest-testmon or pytest-picked) as T1.** Deferred. testmon does not track data or static files such as parquet fixtures or config, or environment changes. It has no official Windows support. It also conflicts with `-m` marker filters, although that caveat comes from a secondary source only. pytest-picked maps by filename only. Slice paths are a coarser selector, but they are predictable and cannot silently miss a changed fixture.
- **Drop per-commit gating entirely and rely on CI.** Rejected. T1 keeps every commit on a feature branch green for its slice, which the TDD inside-out ordering (skill `task-ordering-hex`) and `git bisect` depend on.
- **Move the repository to the WSL2 filesystem.** It helps, but it is not the main factor.
  - **Measured on 2026-09-27:** same container and venv, code bind-mounted from NTFS vs copied into a Linux volume, runs interleaved A/B/A. mypy without cache took 103/112 s on the bind mount vs 82 s in the Linux volume. `pytest tests/unit tests/contract -n auto` took 214/257 s vs 149 s. That is roughly 25–40% faster.
  - **Why the gain is small:** the venv (torch and the other heavy libraries) already lives on a Linux named volume.
  - **Out of scope here:** it is a per-machine decision about the developer's environment, not a project rule.

## Consequences

- **Positive:** T1 costs ~1–2 min instead of ~30 min, and the full suite is parallel in CI as well.
- **Positive:** T2 bounds the damage of a cross-slice break that T1 missed to at most 2–3 commits, which keeps bisecting cheap.
- **Negative:** a Task commit can be green on T1 but red on T2 when a slice it did not touch breaks. That failure surfaces at the next Checkpoint C and is fixed with a `task-NN-fix` commit.
- **Negative:** the escalation rules depend on the executor judging the blast radius. The rule is conservative (shared or composition root means T2), and T2 and T3 remain mandatory regardless.
- **Negative:** tests must stay safe under xdist, with no shared writable path across workers. A new test that touches the real repo tree must live under `tests/architecture/` or carry its own `xdist_group`. A test that fails only under `-n` is a test bug.
- **Neutral:** ADR 0.0.0050's "`make check` green" requirement was scoped to stage exit of a closed run (stages 1.1→4.3) and is not affected.

## References

- Issue #110.
- `docs/RUNBOOK-STAGE-LIFECYCLE.md` §Gates em camadas: operational single source.
- ADR 1.2.0010: `make check` == CI with coverage.
- ADR 0.0.0050: autonomous-mode gates.
- pytest-xdist distribution modes: <https://pytest-xdist.readthedocs.io/en/stable/distribution.html>
- import-linter caching (concurrency caveat): <https://import-linter.readthedocs.io/en/v2.8/caching/>
- Docker Desktop WSL best practices (bind-mount performance): <https://docs.docker.com/desktop/features/wsl/best-practices/>
