---
name: hex-arch-python
description: Hexagonal Architecture rules for Python — import direction (outside-in only), layer separation, Protocols as ports. Load on any Stage that touches Python code, especially domain, application, and adapters layers.
metadata:
  status: accepted
  applies_when:
    camada_alvo: [any]
---

# Hexagonal Architecture in Python

## Core principle

Dependency direction **only outside-in**:
`adapters/in → application → domain ← application ← adapters/out`.

`domain` does not import from **anything** inside the project except
other `domain` modules.

`application` imports only from `domain` (plus `typing`, `abc`, etc.
from stdlib). Defines ports as `typing.Protocol` or `abc.ABC`.

`adapters/*` import from `application` (and `domain` for types), but
**never the other way around**. Adapters are where Pydantic,
SQLAlchemy, FastAPI, boto3, etc. live.

## Ports

Ports are defined under `application/ports/`, never in `adapters/`.
Use `Protocol` (lighter, structural typing) unless `ABC` is explicitly
needed.

```python
# application/ports/user_repo.py
from typing import Protocol
from domain.user import User, UserId

class UserRepository(Protocol):
    def get(self, user_id: UserId) -> User | None: ...
    def save(self, user: User) -> None: ...
```

## DON'T

- Don't import Pydantic/SQLAlchemy in `domain/` or `application/`.
- Don't make a domain entity inherit from `BaseModel` (Pydantic).
- Don't call `Session.commit()` inside a use case — transaction is
  the persistence adapter's responsibility.
- Don't return a domain entity outside `application/` — use DTOs in
  the contract with `adapters/in/`.

## Anti-example

```python
# ❌ WRONG: domain importing from adapter
from adapters.out.postgres.user_table import UserTable

class User:
    @classmethod
    def from_db(cls, row: UserTable) -> "User": ...
```

```python
# ✓ RIGHT: pure domain
class User:
    def __init__(self, id: UserId, email: Email) -> None: ...
```
