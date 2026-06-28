---
title: ADR 0.0.0001 — Hexagonal architecture from day one
description: Architecture Decision Record
when-use: Reference when questioning the project structure or considering refactors to layering
keywords: [adr, hexagonal, architecture, ports-and-adapters]
status: accepted
created_at: 2026-05-03
updated_at: 2026-05-15
adr_id: "0.0.0001"
decision: Adopt hexagonal (ports-and-adapters) structure from project inception, before any business code is written
context_stage: 1.1-bootstrap
---

# ADR 0.0.0001 — Hexagonal architecture from day one

## Status

`accepted`

## Context

The project is a greenfield Python service expected to start as a monolith and fragment into microservices as load and team size grow. We need to decide on the internal structure of the codebase from the start.

Forces at play:
- The team is small (2 engineers) — overhead matters
- The project will outlive the initial scope; refactoring layering later is expensive
- We expect external integrations (DB, message brokers, third-party APIs) to evolve and be swapped
- We expect to extract microservices; clean module boundaries make extraction tractable
- We've experienced the pain of "everything imports everything" codebases before

## Decision

Structure the codebase in `src/<project>/` with **Vertical Slices over a hexagonal kernel** — each feature owns its own `domain/`, `application/`, and `adapters/` triple, alongside a `shared/` package for cross-feature kernel and infrastructure:

```
src/<project>/
├── features/
│   └── <feature>/
│       ├── domain/         # pure business logic, no I/O, no framework
│       ├── application/    # use cases / services orchestrating domain
│       └── adapters/
│           ├── in/         # inbound adapters (HTTP, CLI, queue consumers)
│           └── out/        # outbound adapters (DB, queue producers, 3rd-party)
├── shared/
│   ├── domain/             # cross-feature value objects, base exceptions
│   ├── application/        # cross-feature ports/contracts
│   └── infrastructure/     # framework wiring, config, HTTP app
└── composition_root.py     # single wiring point
```

The hexagonal contract is enforced **per feature**: `domain` imports nothing project-internal; `application` imports `domain` and shared ports; `adapters` import `application` and `domain` (never sideways into other features' adapters). `composition_root.py` is the only place allowed to instantiate adapters and inject them.

The first feature lands in `features/<name>/` from Stage 1.1-bootstrap onward — the Vertical Slice structure is created together with the hexagonal kernel, not as a later refactor.

See [`docs/LAYOUT.md`](../LAYOUT.md) for the full layer rules and `scripts/check_layout.py` for the import-direction enforcement.

## Alternatives considered

### Alternative A — Flat package, layer later
- **Description:** Start with `src/<project>/` and add layering only when pain emerges.
- **Pros:** Less ceremony upfront; small projects don't pay layering cost.
- **Cons:** Refactor to layers later requires touching every import; team tends to defer indefinitely.
- **Why rejected:** We've seen this fail in past projects. The "we'll do it later" rarely happens, and when it does, it's painful.

### Alternative B — Django/FastAPI-style organization (by feature/app)
- **Description:** Organize by feature module, each with its own models/views/services.
- **Pros:** Familiar to web devs; locality of related code.
- **Cons:** Couples business logic to framework conventions; harder to extract pure domain for reuse or testing.
- **Why rejected:** We want framework independence for the domain.

### Alternative C — Do nothing / status quo
- **Description:** No specific structure imposed; let it emerge.
- **Why rejected:** With 2 engineers working in parallel, divergent structures emerge fast. Better to align upfront.

## Consequences

### Positive
- New features have an obvious home from day 1
- Domain logic is testable without I/O
- Extracting a microservice means moving an adapter + its port, not untangling spaghetti
- Code assistants (Claude Code, Codex) place new files in the right layer when prompted

### Negative
- Empty packages on day 1 may feel like cargo cult
- Junior contributors (future) may need orientation on what goes where
- Some simple features end up touching 3 layers when 1 would suffice

### Neutral / trade-offs accepted
- We accept some upfront overhead in exchange for long-term maintainability
- We accept that for a small CLI script this would be overkill — but this project is not that

## Implementation notes

- Empty `__init__.py` in each package with a one-line docstring describing the layer's responsibility
- Import direction (per feature): `domain` → nothing project-internal; `application` → `domain` + `shared/application` ports; `adapters/in` and `adapters/out` → `application` + `domain`; `composition_root` wires everything
- No sideways imports between features' adapters — features communicate only through ports declared in `shared/application` or through composition root
- Enforcement: `scripts/check_layout.py` codifies the rules and is invoked by `make check`

## References

- Cosmic Python (Percival & Gregory), chapters on ports and adapters
- Hexagonal Architecture (Alistair Cockburn, 2005)
- Related ADRs: none yet
