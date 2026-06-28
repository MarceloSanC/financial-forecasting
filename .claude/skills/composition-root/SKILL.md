---
name: composition-root
description: Where to inject dependencies, avoid global singletons, keep wiring centralized. Load on Stages that add wiring (composition root, DI, use case factories).
metadata:
  status: draft
  applies_when:
    camada_alvo: [shared/infrastructure]
    fase: [any]
---

# Composition Root

## Principle

**One single place** instantiates concrete implementations and wires
ports to adapters: `composition_root.py` (or `di.py`) at the root of
the bounded context. That's where every `new SqlAlchemyUserRepository(...)`
and `new BcryptHasher(...)` lives.

The rest of the code receives instances via constructor (manual DI) or
`Depends()` (FastAPI).

## Why

- Swapping an implementation (Postgres → in-memory for tests) changes 1 file.
- No `import` of an adapter inside a use case or domain.
- Lifecycle and configuration are visible in one place.

## Structure

```
src/myproject/<bc>/
├── domain/
├── application/
├── adapters/
└── composition_root.py    # only place with adapter imports
```

```python
# composition_root.py
from sqlalchemy.orm import Session

from .application.use_cases.create_user import CreateUserUseCase
from .adapters.out.postgres.user_repo import SqlAlchemyUserRepository
from .adapters.out.bcrypt.hasher import BcryptHasher

def build_create_user_use_case(session: Session) -> CreateUserUseCase:
    return CreateUserUseCase(
        repo=SqlAlchemyUserRepository(session),
        hasher=BcryptHasher(),
    )
```

## DO

- 1 composition root per BC; integration between BCs lives in
  `bootstrap/` at the project root.
- Simple factory functions: receive external dependencies (Session,
  config), return a ready use case.
- Use `Depends(build_create_user_use_case)` in a FastAPI endpoint.

## DON'T

- Don't import an adapter inside a use case or router.
- Don't use a global singleton Session or repository.
- Don't create a "magic" container (DI framework with auto-wiring) —
  manual DI in Python is simple and explicit.
- Don't make the composition root conditional inside a use case ("if
  prod, use X; if dev, use Y") — that's the composition root's
  responsibility.
