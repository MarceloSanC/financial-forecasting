---
title: Runbook — Validate the CI gate per error class
description: Step-by-step procedure to prove that each error class is rejected by the local `make check` gate (which is exactly what the CI workflow runs)
when-use: After hardening the CI gate (a new tool joins the chain); when auditing that the existing CI gate still rejects each error class; after an incident where a regression slipped past the gate
keywords: [runbook, ci, gate, validation, make-check, lint, fmt-check, typecheck, layout-check, docs-check, test]
status: accepted
created_at: 2026-06-23
updated_at: 2026-06-23
runbook_id: validate-ci-gate
triggers:
  - Hardening of the CI gate (new tool joining the chain — e.g., bandit, import-linter)
  - Audit of the existing CI gate per error class
  - Incident — a PR was merged despite broken X; validate the gate still works
estimated_duration: ~20min
---

# Runbook — Validate the CI gate per error class

> Runbooks are written and consumed in **English**. They describe operational procedures executed by humans or agents.

> This file is a **worked-example instance** of [`docs/templates/runbook.md`](../templates/runbook.md). It ships in the project template so that a new project starts with one fully fleshed-out runbook. Replace `financial_forecasting` with your package name and adjust the placeholder Stage path (`docs/stages/N.M-<slug>/technical.md`) to a real Stage once you have one.

## Purpose

Prove, **class by class**, that each error class enforced by the local `make check` gate produces a non-zero exit code, so the CI step `Run gate completo (lint + typecheck + layout-check + tests)` in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) (which runs literally `make check`) rejects the broken state before merge.

The argument is transitive: if every class fails `make check` locally, every class fails `make check` on the runner. This runbook documents the local demonstration that closes that transitivity argument.

In this template, `make check` expands to the following target chain (see [`Makefile`](../../Makefile)):

```
check: lint typecheck layout-check docs-check test
```

and `make docs-check` itself expands to:

```
docs-check:
	uv run python scripts/check_technical_postexec.py
	uv run python scripts/check_stage_issue.py
```

## Triggers

When to execute this runbook:
- A new gate is added to `make check` (audit the addition).
- Periodically, after major dependency upgrades (ruff, mypy, pytest), to confirm fingerprints still match.
- After an incident where a regression slipped past the gate (validate that the class involved still fails — or extend the gate to cover it).

## Prerequisites

- [ ] Working tree clean (`git status` empty).
- [ ] `make check` green on the current branch **before** starting (baseline).
- [ ] `.venv` installed and current (`make setup`).
- [ ] On a POSIX shell (Linux native, macOS) or inside the Docker container on Windows (`make docker-shell`) — `make` is POSIX-only by project decision.

## Procedure

For each class below: apply the patch, run the command, capture the output, compare with the expected fingerprint, **revert the patch**, confirm `git status` is clean before moving to the next class.

> **Rule:** never commit a broken-on-purpose patch. Apply → exercise → revert → next.

### Class 1 — `lint` (ruff check)

**Patch** (apply to `src/financial_forecasting/__init__.py`):
```python
import os  # broken-on-purpose: F401 unused-import
```

**Command:**
```bash
uv run ruff check src/financial_forecasting/__init__.py
```

**Expected output (fingerprint):**
```
src/financial_forecasting/__init__.py:N:1: F401 [*] `os` imported but unused
Found 1 error.
```
Exit code: **1**.

**Revert:**
```bash
git restore src/financial_forecasting/__init__.py
```

---

### Class 2 — `fmt-check` (ruff format --check)

> **Note:** unlike `lint`/`typecheck`/etc., the formatter check is **not** a standalone target in this template's `make check` chain — the `fmt` target *applies* formatting (`ruff format` + `ruff check --fix`) rather than checking it. The class is kept here because `ruff format --check` is the canonical way to prove the formatter rejects unformatted code, and a project that promotes formatting to a blocking gate (adding `ruff format --check` to `check`) should validate it with exactly this patch. Exercise it directly via the command below.

**Patch** (apply to `src/financial_forecasting/__init__.py`):
```python
x=1  # broken-on-purpose: formatter wants `x = 1`
```

**Command:**
```bash
uv run ruff format --check src/financial_forecasting/__init__.py
```

**Expected output (fingerprint):**
```
Would reformat: src/financial_forecasting/__init__.py
1 file would be reformatted
```
Exit code: **1**.

**Revert:**
```bash
git restore src/financial_forecasting/__init__.py
```

---

### Class 3 — `typecheck` (mypy --strict)

**Patch** (apply to `src/financial_forecasting/__init__.py`):
```python
def add(a, b):  # broken-on-purpose: no type annotations under --strict
    return a + b
```

**Command:**
```bash
uv run mypy src/financial_forecasting/__init__.py
```

**Expected output (fingerprint):**
```
src/financial_forecasting/__init__.py:N: error: Function is missing a type annotation  [no-untyped-def]
Found 1 error in 1 file (checked 1 source file)
```
Exit code: **1**.

**Revert:**
```bash
git restore src/financial_forecasting/__init__.py
```

---

### Class 4 — `layout-check` (`scripts/check_layout.py`)

The script enforces the dependency rules from [`LAYOUT.md`](../LAYOUT.md) §3: `domain/` may only import from stdlib and other `domain/` modules — never from `infrastructure/`.

**Patch** (create a new file):
```bash
cat > src/financial_forecasting/shared/domain/_temp_violation.py <<'EOF'
"""Broken-on-purpose: domain importing infrastructure (LAYOUT.md §3 violation)."""
from financial_forecasting.shared.infrastructure.config.settings import Settings  # noqa
EOF
```

**Command:**
```bash
uv run python scripts/check_layout.py
```

**Expected output (fingerprint):** an error from `check_layout.py` mentioning the offending file and the layer violation. In this template the message takes the form:
```
VIOLAÇÃO: financial_forecasting/shared/domain/_temp_violation.py importa 'financial_forecasting.shared.infrastructure.config.settings' (proibido para camada 'domain')
```
The exact wording is implementation-specific; the script must surface (a) the offending file and (b) the rule violated. Exit code: **1**.

**Revert:**
```bash
rm src/financial_forecasting/shared/domain/_temp_violation.py
```

---

### Class 5 — `docs-check` (`scripts/check_technical_postexec.py` + `scripts/check_stage_issue.py`)

`make docs-check` runs two scripts in sequence; the first to exit non-zero fails the gate.

1. **`check_technical_postexec.py`** enforces, on every `technical.md`:
   - **Structural (always):** exactly one `<!-- BEGIN: post-execution -->` marker and exactly one `<!-- END: post-execution -->` marker, with END after BEGIN.
   - **Diff vs baseline (only when `status: done` and the Stage has a reserved `stage N.M: technical approved` commit):** content outside the markers must match that approved baseline. If no approval commit exists in history (Stage still in 3A/3B, or no Stage yet), check 2 is skipped by design.
2. **`check_stage_issue.py`** requires every Stage `technical.md` to carry a valid `issue_id` that resolves via `gh issue view`. It is **best-effort**: if `gh` is not installed or not authenticated it prints WARN and returns 0, so it is not a reliable local trigger without `gh`.

The **structural check** of `check_technical_postexec.py` is the most direct, environment-independent trigger — break a marker and the script flags it regardless of file status and regardless of whether `gh` is available.

> **Note (template placeholder):** a fresh template has no `docs/stages/N.M-<slug>/technical.md` yet, so there is nothing to break until your first Stage exists. Substitute a real Stage path below once you have one (e.g. `docs/stages/1.1-bootstrap/technical.md`). If you want to confirm the script wiring before any Stage exists, run `uv run python scripts/check_technical_postexec.py` against a hand-made `technical.md` derived from [`docs/templates/`](../templates/) and break a marker in that.

**Patch:** comment out the `END: post-execution` marker in a Stage's `technical.md` (last marker line near the end of the file). Example: replace `<!-- END: post-execution -->` with `<!-- broken END -->` in `docs/stages/N.M-<slug>/technical.md`.

**Command:**
```bash
uv run python scripts/check_technical_postexec.py
```

**Expected output (fingerprint):**
```
docs/stages/N.M-<slug>/technical.md: marcadores de §7 inválidos — esperava 1 BEGIN e 1 END, encontrei 1 BEGIN e 0 END.
```
Exit code: **1**.

**Revert:**
```bash
git restore docs/stages/N.M-<slug>/technical.md
```

---

### Class 6 — `test` (pytest)

**Patch:** edit [`tests/test_smoke.py`](../../tests/test_smoke.py), changing the bootstrap smoke test so it fails. The shipped test only asserts that `import financial_forecasting` succeeds; force a failure by adding a failing assertion to its body, e.g.:
```python
def test_package_imports() -> None:
    """Marcador: se a coleta do pytest chegou aqui, o import top-level passou."""
    assert False  # broken-on-purpose
```

**Command:**
```bash
uv run pytest tests/test_smoke.py -v
```

**Expected output (fingerprint):**
```
FAILED tests/test_smoke.py::test_package_imports - assert False
```
Exit code: **1**.

**Revert:**
```bash
git restore tests/test_smoke.py
```

---

### Class 7 — `coverage` (pytest --cov-fail-under)

The coverage gate is configured in [`pyproject.toml`](../../pyproject.toml) `[tool.coverage.report] fail_under = 90`. A coverage drop below 90 % causes a non-zero exit, which fails the gate.

**Patch** (drop a tested branch — remove the smoke test temporarily so coverage falls):
```bash
git mv tests/test_smoke.py tests/test_smoke.py.bak
```

**Command:**
```bash
uv run pytest tests/ --cov=src/financial_forecasting --cov-fail-under=90
```

**Expected output (fingerprint):**
```
FAIL Required test coverage of 90% not reached. Total coverage: N%
```
Exit code: **2** (pytest coverage failure).

**Revert:**
```bash
git mv tests/test_smoke.py.bak tests/test_smoke.py
```

> The `90` threshold here must match `fail_under` in `pyproject.toml`. If the project raises or lowers the coverage gate, update both the command and the fingerprint in this class.

---

## Verification (cumulative)

After exercising all seven classes individually, run the full gate **without any patch** to confirm baseline is green:

```bash
git status              # must be clean
make check              # must exit 0
```

If `make check` is green and each class individually produced a non-zero exit code, the transitivity argument is closed: the CI step `Run gate completo (lint + typecheck + layout-check + tests)` runs exactly `make check`, so every class fails on the runner as well.

## Rollback

If a patch was committed by accident:

1. **Inspect the diff:**
   ```bash
   git show HEAD
   ```
2. **Revert the commit (preferable; preserves history):**
   ```bash
   git revert HEAD
   ```
3. **If the commit was the most recent and not yet pushed**, alternative: drop it:
   ```bash
   git reset --soft HEAD~1   # keep changes staged
   git restore --staged .    # unstage
   git restore .             # discard
   ```

## Troubleshooting

| Symptom | Likely cause | Resolution |
|---|---|---|
| The patch triggers an error in a *different* class than expected (e.g., the type-error patch is also flagged by lint). | Patch is too broad; multiple linters react. | Use the minimal patch listed in this runbook; do not improvise broader patches. |
| `make check` fails on baseline (before any patch). | Working tree drift, or a previous patch was not reverted. | `git status` first; `git restore .` to discard any leftover changes; re-run `make check`. |
| `check_technical_postexec.py` does not flag an edit **outside** the markers in a `status: done` file. | Expected when the Stage has no reserved `stage N.M: technical approved` commit in history: check 2 is scoped to the execution window, so without that baseline only the structural check runs. | Exercise Class 5 via the **structural** check (break a marker — see §Procedure Class 5 above), which fires regardless of status. |
| `check_stage_issue.py` prints `WARN — gh não disponível` and returns 0. | `gh` is not installed or not authenticated. | Expected locally without `gh`. To exercise this sub-check, install `gh` and run `gh auth login`; otherwise rely on the `check_technical_postexec.py` structural break as the Class 5 trigger. |
| Class 6 patch flagged by `ruff` (lint) before reaching `pytest`. | If `make check` runs `lint` first and exits on it, you won't see `pytest` fail. | Run `uv run pytest tests/test_smoke.py -v` directly (as listed in this runbook) instead of the full `make check`. |
| Fingerprint differs from the runbook (different line number, slightly different wording). | Tool was upgraded; line numbers shift as files evolve. | Match on **rule code** (`F401`, `[no-untyped-def]`, etc.) and **exit code**, not on the exact line number. Update the runbook if a fingerprint drifts materially. |

## Maintenance

When a future Stage **hardens** the CI gate, this runbook MUST be extended in the same Stage. Examples:

- **New tool joins `make check`** (e.g., `bandit`, `safety`, `pip-audit`): add a new §Class N section in §Procedure, in the order in which `make check` runs it, with the four-part shape (patch / command / expected output / revert).
- **`scripts/check_layout.py` replaced by `import-linter`**: rewrite §Class 4 with the new tool's fingerprint; keep the same domain-violation patch.
- **`fmt-check` promoted to a blocking target** (adding `ruff format --check` to `check`): upgrade the note in §Class 2 and add the target to the chain documented in §Purpose.
- **Coverage gate** (`fail_under` in `pyproject.toml`): if the threshold or coverage tool changes, update §Class 7's command and fingerprint accordingly.

Update `updated_at` in the frontmatter and reference the hardening Stage in the body of the new subsection.

## Related

- CI workflow: [`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
- Local gate definition: [`../../Makefile`](../../Makefile) (target `check`)
- Coverage gate config: [`../../pyproject.toml`](../../pyproject.toml) (`[tool.coverage.report]`)
- Layer rules: [`../LAYOUT.md`](../LAYOUT.md) §3
- PR gates: [`../GIT-WORKFLOW.md`](../GIT-WORKFLOW.md) §Gates
- Runbook template: [`../templates/runbook.md`](../templates/runbook.md)
- Validators: [`../../scripts/check_layout.py`](../../scripts/check_layout.py), [`../../scripts/check_technical_postexec.py`](../../scripts/check_technical_postexec.py), [`../../scripts/check_stage_issue.py`](../../scripts/check_stage_issue.py)
