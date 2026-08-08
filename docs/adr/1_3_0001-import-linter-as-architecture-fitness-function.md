---
title: ADR 1.3.0001 — Encode the hexagonal boundary as an import-linter fitness function in a standalone .importlinter
description: Architecture Decision Record
when-use: Reference before changing where import-linter is configured, which contract types are used, or how the composition_root boundary is exempted
keywords: [adr, import-linter, fitness-function, layers, forbidden, ignore-imports, composition-root, dependency-rule]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "1.3.0001"
decision: The hexagonal dependency rule is encoded as import-linter contracts in a standalone .importlinter (INI), using layers + forbidden + ignore_imports, complementing check_layout.py and wired into make check / CI
context_stage: 1.3-architecture-contracts
bounded_context: shared
---

# ADR 1.3.0001 — Encode the hexagonal boundary as an import-linter fitness function in a standalone `.importlinter`

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

ADR [0.0.0019](./0_0_0019-hexagonal-enforced.md) already decided that the hexagonal dependency rule
is enforced **by tooling, not by review**, and explicitly staged the handoff: `scripts/check_layout.py`
in Stage 1.1, then **import-linter contracts mirroring `LAYOUT.md`** from Stage 1.3, with the
domain-purity rule (no `pandas`/`pyarrow`/`torch` in `domain`) becoming a build-breaking import
contract. This ADR records the concrete **how** of that handoff — it does not re-decide *whether* to
enforce.

Forces at play:

- **The prior codebase proved the failure mode is real, not hypothetical.** In the reference repo
  `/home/marcelo/Code/financial-time-series-forecasting`, **23 of 36** files under `src/domain/services/`
  imported `pandas`/`numpy`/`torch` (e.g. `dataset_quality_gate.py:1`, `holm_family_6.py:3`). The
  "domain" was domain in name only; the data layer had leaked all the way in. That repo had **no**
  import-linter, no `.importlinter`, no layer check — the only boundary "enforcement" was Ruff's isort
  `known-first-party` (`pyproject.toml:63`), which orders imports but says nothing about *direction*.
  Its CI (`ci.yml:27`) ran only ruff/mypy/pytest. The architectural debt that motivated the rebuild is
  exactly what an unenforced domain boundary produces.
- **A prior gate in this project was inert/myopic.** Lesson from Stage 1.2 (`0_0_0011` framing): a gate
  is worthless unless it *actually runs* in the pipeline and is *proven* by an intentional, reverted
  break. The import contract must be wired into the same target the CI invokes, and validated by making
  the build red on purpose.
- **`docs/LAYOUT.md` already exists and is the source of truth.** §3 fixes the dependency direction
  (`adapters → application → domain`, with `shared/application/ports` and `shared/infrastructure` as the
  inward base), §3/§7 forbid `domain` from importing `application`/`adapters`/`shared.infrastructure`
  and external libs, and §6 declares the one accepted boundary exception
  (`shared.infrastructure.http.app → composition_root → features.*.adapters`). The contract file must
  *mirror* LAYOUT, not invent a parallel rulebook; if they ever diverge, LAYOUT wins and the contract is
  what gets corrected.
- **The skeleton is mostly inert template surplus** (finding F2 from Stage 1.1): `shared.infrastructure`
  already carries `{clock,http,config,logging,uuid_generator}`, `shared.application.ports.out.*` exists,
  and `features/` contains only `__init__.py`. The contracts must reflect the *real* modular structure
  without failing the build because of empty/inert packages that no Stage has populated yet.
- **`check_layout.py` has a documented blind spot.** It cannot see the *indirect* composition_root
  boundary path (`check_layout.py:17`, mirrored in LAYOUT §6 line 228), leaving that to manual review.

## Decision

Encode the LAYOUT §3/§6 rules as **import-linter contracts** in a **standalone `.importlinter`
(INI format) at the repo root**, with `root_package = financial_forecasting`. Use three contract
families:

1. **`layers`** — fix the inward direction `adapters > application > domain`, modeled per real container
   (`shared` and each `features.<feature>` as it appears), with `shared.application.ports` and
   `shared.domain` as inward base layers. Containers are marked so that absent/inert layers in the
   current skeleton do not fail the build (finding F2).
2. **`forbidden`** — the build-breaking rules: `*.domain` (and `shared.domain`) may not import
   `pandas`/`pyarrow`/`torch` (the central DoD) **nor** `pydantic`/`sqlalchemy`/`fastapi` (LAYOUT line
   104); `application`/`shared.application` may not import `adapters`/`shared.infrastructure` (line 110);
   `shared.*` may not import `features.*` (line 244).
3. **`ignore_imports`** — declare the single accepted exception from LAYOUT §6: the indirect path
   `shared.infrastructure.http.app → composition_root` (verified verbatim at `app.py:22`) and
   `composition_root → features.*.adapters`. The contract must **not** flag this path.

import-linter **complements** `scripts/check_layout.py` (it does not replace it): the script keeps its
fast structural checks, import-linter adds direction/forbidden coverage and the layered model. Both run
under `make check`; a dedicated `lint-imports` Make target (`uv run lint-imports`) is added to `check`,
and because CI already invokes `make check`, the contract runs in CI by construction — made explicit in
`ci.yml` per the roadmap. The whole thing is validated by an intentional break (`import pandas` in a
`shared/domain` module) that turns the build red, then reverted.

## Alternatives considered

### Alternative A — Configure import-linter inside `pyproject.toml` (`[tool.importlinter]`)

- **Description:** Keep all tool config in the build manifest, as a `[tool.importlinter]` table.
- **Pros:** One fewer file; import-linter natively supports it.
- **Cons:** Buries the architecture contract among build/lint/test config; the roadmap (Stage 1.3 YAML,
  `arquivos_a_criar`) explicitly lists `.importlinter` as the artifact to create.
- **Why rejected:** The contract is the *headline deliverable* of this Stage and the visible mirror of
  LAYOUT; it deserves a dedicated, auditable file. The cost of moving it later is nil (one config block).

### Alternative B — Use only an `independence` contract (no `layers`)

- **Description:** Express the rule as mutual independence between layers instead of a directed stack.
- **Pros:** Slightly simpler to author for a flat model.
- **Cons:** `independence` forbids *all* cross-imports symmetrically; it cannot express that
  `adapters → application → domain` is allowed **one way** only. It would wrongly reject legitimate
  inward imports.
- **Why rejected:** Wrong shape — the hexagonal rule is fundamentally *directional*. `independence` is
  reserved for the day features must be isolated from each other (today unnecessary: `features/` is
  empty).

### Alternative C — Rely on `check_layout.py` alone (do nothing new)

- **Description:** Keep only the Stage 1.1 script; skip import-linter.
- **Pros:** No new dependency.
- **Cons:** Contradicts ADR 0.0.0019's staged plan and the roadmap DoD; the script has a documented
  blind spot (indirect composition_root path) and is bespoke rather than a standard, well-understood
  fitness-function tool. The `domain`-imports-`pandas` rule deserves the canonical tool the literature
  and the team's skill (`import-linter-rules`) assume.
- **Why rejected:** Reproduces a single-tool gap and leaves the central domain-purity rule on a custom
  script instead of the standard enforcement the project committed to.

## Consequences

### Positive

- The exact rot of the prior repo (23/36 domain files importing pandas/numpy/torch) becomes
  **mechanically impossible to merge**: `import pandas` in `domain` turns the build red.
- The dependency direction and the composition_root exception are encoded once, in a file that visibly
  mirrors LAYOUT §3/§6 — auditable evidence for the thesis, not an assertion.
- A regression test (`tests/architecture/test_import_contracts.py`) pins the gate itself: removing or
  loosening `.importlinter` fails the suite.

### Negative

- Two enforcement mechanisms coexist (`check_layout.py` + import-linter). The overlap is intentional
  (defense in depth) but means a rule lives in two places; both must stay aligned to LAYOUT.
- `layers`/`containers` modeling must track the real package tree as features are added; a new feature
  with populated layers may require touching `.importlinter` (a known, cheap maintenance cost).

### Neutral / trade-offs accepted

- We accept the small upfront cost of authoring the contracts and the intentional-break verification in
  exchange for permanent, standard-tool regression protection.
- We defer feature-vs-feature `independence` contracts until a second feature exists (no value today).

## Implementation notes

- Artifacts: `.importlinter` (root), `tests/architecture/test_import_contracts.py`,
  `tests/architecture/__init__.py`; `pyproject.toml` (`import-linter` in the `dev` extra);
  `Makefile` (`lint-imports` target added to `check`); `.github/workflows/ci.yml` (make the contract's
  presence explicit in CI).
- The intentional-break verification uses `shared/domain/value_objects/pagination.py` (an existing
  domain module), reverted with no production code left changed; evidence recorded in `technical.md` §7.
- If LAYOUT and `.importlinter` ever disagree, LAYOUT is the source of truth and the contract is
  corrected.

## References

- Related ADRs: [0.0.0019](./0_0_0019-hexagonal-enforced.md) (enforce by tooling, this Stage executes
  the import-linter handoff); [0.0.0001](./0_0_0001-hexagonal-from-day-one.md) (the structure protected);
  [0.0.0020](./0_0_0020-statistics-in-domain-over-value-objects.md) (what lives behind the boundary);
  [1.2.0011](./1_2_0011-coverage-gate-as-foundational-fitness-function.md) (gate-must-run-and-be-proven
  lesson).
- LAYOUT: `docs/LAYOUT.md` §3 (direction, lines 94/104/110), §6 (composition_root exception, lines
  222–229), §7 (line 244 "Shared não importa de features").
- Reference repo (negative example): `/home/marcelo/Code/financial-time-series-forecasting`
  (`src/domain/services/dataset_quality_gate.py:1`, `holm_family_6.py:3`; `ci.yml:27`; `pyproject.toml:63`).
- External: import-linter docs — contract types `layers`, `forbidden`, `independence`, and
  `ignore_imports`.
