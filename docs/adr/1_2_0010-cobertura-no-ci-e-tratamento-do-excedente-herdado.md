---
title: ADR 1.2.0010 — Make the coverage gate effective in CI and treat the inherited template surplus
description: Architecture Decision Record
when-use: Reference when wondering why the CI gate runs pytest --cov, why some inherited modules are omitted/pragma'd from coverage, or why import-linter contracts are not part of Stage 1.2
keywords: [adr, ci, coverage, fail_under, gate, template-surplus, omit, pragma, import-linter, layout-check, hexagonal]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "1.2.0010"
decision: Make `make check` (the CI path) run `pytest --cov` so `fail_under=90` actually fires, treat the inherited 33%-coverage surplus by scope-guided pruning + targeted omit/pragma over wiring, and keep import-linter contracts out of Stage 1.2 (deferred to 1.3, gated meanwhile by the existing check_layout.py)
context_stage: 1.2-ci-coverage
---

# ADR 1.2.0010 — Make the coverage gate effective in CI and treat the inherited template surplus

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 1.2 (`1.2-ci-coverage`) must turn the project's quality bar into a **real gate**: any PR that
violates ruff, mypy `--strict`, the hexagonal dependency direction, the test suite, or coverage
`< 90%` must fail CI before merge (overview §4 "Fronteiras enforçadas", §7 "enforcement-as-test";
roadmap Stage 1.2 DoD). Three forces collide:

1. **F3 — the coverage gate is inert.** `pyproject.toml` already declares `[tool.coverage.report]
   fail_under = 90`, but the path CI actually runs is `make check → … → make test`, and `make test`
   is `pytest tests/ -v` **without `--cov`**. `fail_under` is a `coverage report` setting; it only
   fires when coverage is being measured. Measured live, the project sits at **33.01%** (verified:
   `pytest --cov` → `FAIL Required test coverage of 90.0% not reached. Total coverage: 33.01%`). So
   the gate is "miopic": configured but never exercised on the CI path. The old repo
   (`financial-time-series-forecasting`) is a **negative precedent** here — its `make test` did pass
   `--cov` (`Makefile` L29-33) but it **never set `fail_under`**, so coverage was only ever a report,
   never a gate.

2. **The 33% is dominated by inherited template surplus, not by missing domain tests.** ADR 1.1.0001
   accepted the template's web/DB skeleton as inert, declared technical debt: `main.py`,
   `composition_root.py`, `shared/infrastructure/{http,database,logging,clock,uuid_generator,config}`,
   the stub out-ports `clock.py`/`id_generator.py`, and `pagination.py`. Per-module live numbers:
   `main.py` 0%, `http/*` 40-75%, `database/connection.py` 0%, `logging/config.py` 0%, stub ports 0%,
   `pagination.py` 0%, `composition_root.py` 71%. This is **wiring / deferred infra**, not
   domain/application logic. Flipping `fail_under=90` on without treating it would make a legitimate
   gate fail on code the Stage's own scope never touches.

3. **Scope tension on "contrato de import".** The roadmap's human prose for Stage 1.2 says
   "import-linter no CI", but (i) the formal Stage 1.2 YAML lists only `.github/workflows/ci.yml`,
   `pyproject.toml`, `README.md` — `.importlinter` and `tests/architecture/` belong to Stage 1.3;
   (ii) the Stage 1.2 `non_goals` literally include `import-linter contracts (1.3)`; (iii)
   import-linter is **not installed** in the project yet. Meanwhile a dependency-direction gate
   **already runs and already fails** in CI: `scripts/check_layout.py` via `make layout-check`, inside
   `make check`.

Constraints: the new project's toolchain is fixed (`uv sync --extra dev` + ruff + mypy + pytest); the
domain must stay pure (no pandas/pyarrow/torch — overview §6); persistence is Parquet+DuckDB, **no
Postgres** (overview §6); GitHub Free runner minutes are finite; "one branch in flight" governance.

## Decision

Three coupled decisions (D1, D2, D3).

### D1 — The coverage gate runs on the CI path

Make the target that CI executes pass through `pytest --cov=src/financial_forecasting
--cov-report=term-missing`, with `fail_under=90` kept in `pyproject.toml`. Concretely: `make test`
(invoked by `make check`, invoked by the CI `lint-and-test` job) gains the `--cov` flags so the
existing `fail_under` fires on every CI run. A `make test-fast` stays **without** `--cov` for the
fast local loop; `make test-cov` keeps the HTML report. This mirrors the old repo's `--cov +
term-missing` (`Makefile` L29-33) while fixing its omission — we **add** the `fail_under` enforcement
the old repo never had. It is the smallest, most replaceable move: one flag on an existing target.

### D2 — Treat the inherited surplus by scope-guided pruning + targeted omit/pragma over wiring only

Make the measured percentage reflect **live, in-scope** code:

- **Prune** what overview §6 declares out of scope and ADR 1.1.0001 already flagged as removable:
  the SQLAlchemy/Postgres assumption (`database/connection.py`) — persistence is Parquet+DuckDB,
  there is no Postgres, and no Stage before Step 4 wires a DB engine. Pruning aligns with overview §3
  ("não reaproveitar implementações anteriores") and pays down template debt at the cheapest moment.
- **Omit / `exclude_lines`** the legitimate, not-yet-wired plumbing that *will* be consumed by a later
  Stage (composition root and `main.py` wiring — 1.5 and the API step; HTTP infra — API step): these
  are `__main__`/DI entry points, not logic. Add defensive `exclude_lines` precedented by the old
  repo (`pyproject` L68-83: `if __name__ == "__main__":`, `raise NotImplementedError`,
  `raise AssertionError`) plus `if TYPE_CHECKING:` and Protocol stub bodies (`...`).
- **`# pragma: no cover`** only pointwise, on genuinely unreachable defensive branches or Protocol
  method stubs.

**Hard constraint:** exclusions are restricted to wiring/DI/`__main__`/Protocol stubs/declared-deferred
infra. They are **never** used to inflate the number over domain or application logic. In particular
we do **not** replicate the old repo's `omit = ["src/adapters/*"]` blanket — in this hexagonal project
adapters carry contract tests and **must count** toward coverage (overview §7; ADR 0.0.0021).

### D3 — "Contrato de import" in Stage 1.2 = the existing layout-check; formal import-linter is Stage 1.3

Stage 1.2 satisfies its "import contract fails the PR" obligation through the **already-running**
`scripts/check_layout.py` (`make layout-check`, inside `make check`), which fails on a
dependency-direction violation. The **formal import-linter contracts** (`.importlinter`,
`tests/architecture/test_import_contracts.py`) are deferred to Stage 1.3, per the formal roadmap YAML
and the Stage 1.2 `non_goal`. Stage 1.2 guarantees the mechanism *reproves*; Stage 1.3 swaps/extends
it to import-linter. This is recorded here and as a `[decision]` in the technical §7.

## Alternatives considered

### Alternative A (for D1) — CI calls a separate `make test-cov`/`make ci-test` instead of adding `--cov` to `test`
- **Description:** Leave `make test` without coverage; point the CI step at `make test-cov` or a new
  `make ci-test` that runs `pytest --cov`.
- **Pros:** Keeps `make test` fast for local runs; explicit CI-only target.
- **Cons:** `make check` (the documented "full gate, used by CI") would still *not* include coverage,
  so a developer running `make check` locally would get a different verdict than CI — exactly the
  drift that produced F3. Two "test" entry points multiply the surface.
- **Why rejected:** Equivalent in mechanism but worse in honesty: the gate developers run locally
  (`make check`) must match CI. Adding `--cov` to the target inside `make check` keeps one source of
  truth. (`test-fast` covers the genuine fast-loop need.)

### Alternative B (for D2) — Replicate the old repo's `omit = ["src/adapters/*", "src/main.py"]`
- **Description:** Blanket-omit `adapters/*` and `main.py` from coverage, as the old `pyproject` did.
- **Pros:** One line; instantly lifts the percentage; zero pruning.
- **Cons:** Dishonest gate — it would let untested adapters (which in this project carry **contract
  tests** by design, ADR 0.0.0021/overview §7) escape the bar; it entrenches the very "report, not
  gate" posture that let the old project rot; it hides real risk behind a green number.
- **Why rejected:** Directly violates the Stage 1.2 invariant that the percentage must reflect live,
  in-scope code, and the project's whole premise (auditability). Adapters must count.

### Alternative C (for D2) — Lower `fail_under` to ~33% to match reality, raise later
- **Description:** Set the gate to the current number and ratchet up over time.
- **Pros:** Green immediately with no pruning/omit work.
- **Cons:** A 33% "gate" enforces nothing; it codifies the debt as acceptable and removes the pressure
  that Stage 1.2 exists to create. Overview §4 fixes the bar at ≥90%.
- **Why rejected:** Cosmetic; defeats the Stage's purpose.

### Alternative D (for D3) — Install and wire import-linter now, in Stage 1.2
- **Description:** Add `.importlinter` + `import-linter` dep + `tests/architecture/` and run it in CI
  this Stage.
- **Pros:** Literally matches the human prose "import-linter no CI".
- **Cons:** Contradicts the formal Stage 1.2 YAML (those files are 1.3's `arquivos_a_criar`) and the
  explicit `non_goal`; pulls 1.3 work forward; the dependency-direction gate already runs
  (`check_layout.py`), so the *enforcement* outcome is already met.
- **Why rejected:** Respect the formal YAML and the non-goal. The gate is already enforced today by
  `layout-check`; 1.3 owns the migration to formal contracts.

### Alternative E — Do nothing / status quo
- **Description:** Leave `make test` without `--cov`; ship the workflow as-is.
- **Why rejected:** The DoD ("a PR with coverage < 90% fails CI before merge") would be unmet — the
  gate stays inert (F3). Not acceptable.

## Consequences

### Positive
- CI becomes a real gate: ruff + mypy `--strict` + `check_layout.py` + pytest + coverage ≥ 90% all
  block merge. `make check` locally == CI verdict (no drift).
- The measured percentage is **honest**: it reflects live, in-scope code; adapters count.
- Inherited debt is paid down at the cheapest moment (pruning the Postgres assumption), consistent
  with ADR 1.1.0001's "remove-or-repurpose by the consuming Stage".
- D3 keeps Stage boundaries clean: 1.2 enforces, 1.3 formalizes import contracts.

### Negative
- Some wiring/`__main__` code is excluded from the measured base; a future regression in that code
  would not be caught by the coverage gate (it is caught by `make run`/the API step's own tests
  instead). Accepted: that code is DI/entry-point, not logic.
- Pruning `database/connection.py` now means the storage Step re-introduces a (Parquet/DuckDB) engine
  from scratch — but it was going to replace SQLAlchemy anyway (ADR 1.1.0001 / 0.0.0022).

### Neutral / trade-offs accepted
- We accept a documented `omit`/`exclude_lines`/`pragma` list as the contract of "what coverage does
  not measure"; it is auditable in `pyproject.toml` and must stay restricted to wiring/stubs.
- Import-linter enforcement is deferred one Stage; meanwhile `check_layout.py` holds the line.

## Implementation notes

- `Makefile`: add `--cov=src/financial_forecasting --cov-report=term-missing` to `test`; keep
  `test-fast` (no cov) and `test-cov` (HTML).
- `pyproject.toml`: `[tool.coverage.run] source = ["src/financial_forecasting"]`; extend
  `exclude_lines` with `if __name__ == "__main__":`, `raise NotImplementedError`,
  `raise AssertionError`, `if TYPE_CHECKING:`, `\.\.\.`; keep `fail_under = 90`; `omit` restricted to
  wiring/`main.py`/composition root — never `adapters/*`.
- `main.py` and the consuming Stages own the eventual wiring/removal of the remaining surplus.
- Validation is by intentional break, reverted (DoD), recorded in the technical §7.

## References

- Related ADRs: [1.1.0001](./1_1_0001-template-surplus-handling.md) (the surplus this treats),
  [0.0.0019](./0_0_0019-hexagonal-enforced.md) (the layout gate D3 relies on),
  [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md) (why adapters must count),
  [1.2.0011](./1_2_0011-coverage-gate-as-foundational-fitness-function.md) (foundational framing).
- Overview: §3 (não-reaproveitar), §4 (fronteiras enforçadas / ≥90%), §6 (sem Postgres; domínio puro),
  §7 (enforcement-as-test).
- Roadmap: Stage 1.2 (`arquivos_a_modificar`, `definition_of_done`, `non_goals`).
- Old repo (negative/positive precedent): `financial-time-series-forecasting/pyproject.toml` L68-83
  (`omit`/`exclude_lines`, no `fail_under`), `Makefile` L29-33 (`--cov` + term-missing).
</content>
</invoke>
