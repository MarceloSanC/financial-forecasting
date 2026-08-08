---
title: ADR 1.1.0001 — Keep inherited template surplus as declared technical debt
description: Architecture Decision Record
when-use: Reference when wondering why FastAPI/SQLAlchemy scaffolding and unused infra modules exist in a bootstrap that the roadmap called an "empty structure", or before pruning them
keywords: [adr, bootstrap, template, technical-debt, surplus, fastapi, sqlalchemy, composition-root, scope]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "1.1.0001"
decision: Retain the template's surplus scaffolding (web/db infra, composition root, stub ports) as inert, declared technical debt rather than pruning it in Stage 1.1
context_stage: 1.1-bootstrap
bounded_context: transversal
---

# ADR 1.1.0001 — Keep inherited template surplus as declared technical debt

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 1.1 (`1.1-bootstrap`) was scaffolded from the `whaka-dev-project-template`. The template
ships more than the roadmap's `arquivos_a_criar` enumerated. The roadmap describes the target as a
hexagonal **empty structure** (`features/`, `shared/`), but the template delivered a working web/DB
skeleton. The **surplus** present in the repo and not requested by the Stage 1.1 roadmap entry is:

- `src/financial_forecasting/main.py` and `composition_root.py`;
- `shared/infrastructure/http/` (`app.py`, `middlewares.py`, `error_handlers.py`),
  `shared/infrastructure/database/connection.py`, `shared/infrastructure/logging/config.py`,
  `shared/infrastructure/clock/system_clock.py`, `shared/infrastructure/uuid_generator/uuid4_generator.py`,
  `shared/infrastructure/config/settings.py`;
- `shared/domain/value_objects/pagination.py`, `shared/domain/exceptions/base.py`;
- stub ports `shared/application/ports/out/clock.py` and `.../id_generator.py`;
- the matching dependencies in `pyproject.toml`: `fastapi`, `uvicorn`, `sqlalchemy`, `alembic`,
  `pydantic`, `pydantic-settings`.

Forces at play:

- The Stage's own non-goals exclude **business features** — but this surplus is *plumbing*, not a
  feature, so it does not violate that non-goal directly.
- The mandated stack in `CLAUDE.md` **requires** FastAPI, SQLAlchemy and Alembic, and later stages
  depend on parts of this surplus: Stage 1.5 (`1.5-config-and-tracking`) builds the typed config
  and the composition root; the inference API (Step covering FastAPI) needs `http/`.
- The Definition of Done is "`make setup && make check && make test` green on a clean machine."
  The surplus already passes the layout gate and the smoke test — it does **not** violate domain
  purity (`check_layout.py` is green) nor the import direction.
- Pruning now (removing FastAPI/SQLAlchemy/Alembic from `pyproject.toml`, deleting `http/` and
  `database/`) would have to be **undone** in Stages 1.5 and the API step, and would contradict the
  declared mandatory stack.

## Decision

**Keep the surplus as an inert, declared technical-debt skeleton; do not prune it in Stage 1.1.**

- The web/DB infrastructure modules (`http/`, `database/`, `logging/`, the stub ports
  `clock`/`id_generator`, `pagination.py`) are treated as **inherited scaffolding that is not yet
  wired into any business flow**. `composition_root.py` remains the single wiring point per ADR
  0.0.0001; nothing in the surplus is activated by a feature in this Stage.
- This debt is **declared here** and scheduled for removal-or-repurpose by the Stage that actually
  needs each module: typed config and composition root in **1.5**; `http/` when the inference API
  lands; `database/connection.py` is a candidate for removal/repurpose once the persistence engine
  (Parquet + DuckDB, ADR 0.0.0022) replaces the template's SQLAlchemy assumption (Step covering
  storage).
- The only Stage-1.1 obligation is the invariant already satisfied: the surplus must **not violate
  domain purity nor the import direction**. `check_layout.py` confirms it does not.

No surplus code is deleted and no dependency is removed in Stage 1.1. The change introduced by
this decision is this ADR plus its reference from the README/concept.

## Alternatives considered

### Alternative A — Prune the surplus now to match "empty structure"
- **Description:** Delete `http/`, `database/`, `main.py`, stub ports, `pagination.py`; remove
  `fastapi`/`uvicorn`/`sqlalchemy`/`alembic` from `pyproject.toml`.
- **Pros:** Literally matches the roadmap's "empty structure" wording; smaller surface; no unused
  code.
- **Cons:** Contradicts the mandatory stack declared in `CLAUDE.md` (FastAPI/SQLAlchemy/Alembic);
  must be reversed in Stage 1.5 and the API step (net rework); risks breaking `make setup`/imports
  if a removal is incomplete; spends effort now for a deletion that is partly undone soon.
- **Why rejected:** High real cost, low real gain. The wording "empty structure" describes intent,
  not a mandate to strip the template; the simple-and-replaceable move is to keep the skeleton and
  defer pruning to the Stage that touches each module.

### Alternative B — Wire the surplus now (activate http/db skeleton)
- **Description:** Hook `main.py`/`http/app.py` into a runnable server and `database/connection.py`
  into a real engine in Stage 1.1.
- **Pros:** Surplus becomes "used", not dead code.
- **Cons:** Pulls business/infra work into a bootstrap Stage (out of scope); pre-commits to
  SQLAlchemy before the Parquet+DuckDB engine decision (ADR 0.0.0022) is realized; violates the
  Stage's plumbing-only intent.
- **Why rejected:** Scope creep and premature commitment; the data engine is explicitly *not*
  SQLAlchemy-centric.

### Alternative C — Do nothing, leave it undocumented
- **Description:** Keep the surplus but write no ADR.
- **Why rejected:** The mismatch between the roadmap's "empty structure" and the actual repo would
  be an unexplained discrepancy in a project whose whole premise is auditability. The debt must be
  *declared* to be legitimate.

## Consequences

### Positive
- DoD stays green with zero risk of breaking imports/`make setup`.
- The mandatory stack (`CLAUDE.md`) is honored; Stages 1.5 and the API step inherit a ready
  skeleton instead of re-creating it.
- The discrepancy between roadmap wording and repo reality is explicitly recorded and auditable.

### Negative
- Dead/inert code lives in the tree until the consuming Stage prunes or wires it — a (small)
  cognitive cost and a temptation to import it prematurely.
- The "empty structure" wording in the roadmap is now slightly aspirational; readers must consult
  this ADR.

### Neutral / trade-offs accepted
- We accept carrying unused FastAPI/SQLAlchemy/Alembic dependencies and modules now, in exchange
  for avoiding rework and honoring the declared stack. Pruning is deferred, not cancelled.

## Implementation notes

- Tracking of the debt: this ADR is the record. Each consuming Stage (1.5 config/composition root;
  storage step for `database/`; API step for `http/`) is responsible for either wiring or removing
  the relevant module and noting it in its own technical.md.
- Stage-1.1 guard: only ensure `check_layout.py` stays green (no domain-purity / import-direction
  violation from the surplus) — already the case.

## References

- Related ADRs: [0.0.0001](./0_0_0001-hexagonal-from-day-one.md) (single composition root),
  [0.0.0019](./0_0_0019-hexagonal-enforced.md) (the gate confirming surplus does not break layering),
  [0.0.0022](./0_0_0022-data-engine-pandas-duckdb.md) (Parquet+DuckDB engine — to be authored —
  motivates eventual removal of the SQLAlchemy assumption).
- Roadmap: `docs/roadmap.md` Stage 1.1 (`arquivos_a_criar`, `non_goals`).
- `CLAUDE.md` — mandatory stack (FastAPI, SQLAlchemy, Alembic).
