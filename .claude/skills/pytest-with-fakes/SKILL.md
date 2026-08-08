---
name: pytest-with-fakes
description: Test domain and application with in-memory fakes of out ports; validate real adapters with contract tests. Load on Stages whose target layer is domain or application, or stages adding a new out adapter that needs a contract test.
metadata:
  status: draft
  applies_when:
    camada_alvo: [domain, application, adapters/out]
---

# Tests with fakes (not mocks)

## Principle

Use cases and domain are tested with **fakes** — in-memory
implementations of out ports, not mocks. Mocks couple to call detail
(`assert_called_with`); fakes couple to behavior (observable state).

Real adapters (SQLAlchemy, boto3) are validated by **contract tests** —
the same test suite that runs against the fake also runs against the
real implementation, ensuring both satisfy the port contract.

## Structure (canonical — see `docs/LAYOUT.md` §2)

```
tests/
├── unit/                    # pure domain + use cases with fake
│   └── features/<name>/
│       ├── domain/
│       └── application/
├── integration/             # real adapters with test infra
├── contract/                # 1 suite per port; runs against fake + real
├── e2e/                     # full flow over HTTP
└── fakes/                   # in-memory implementations of out ports
    └── features/<name>/
        └── in_memory_<port>.py
```

Fakes live at **`tests/fakes/features/<name>/`** (single canonical location);
unit and contract suites import from there. Never duplicate fakes inside
`tests/unit/`.

## DO

- Fake implements the port `Protocol`; stores state in a `dict` or
  `list` in memory.
- For a use case, instantiate with fakes: `UseCase(repo=FakeUserRepo())`.
- Contract test receives a `repo` fixture that parametrizes fake and
  real implementations.
- Use `pytest.mark.unit`, `integration`, `contract`, `e2e` for filtering.

## DON'T

- Don't use `unittest.mock` for something that has a fake.
- Don't duplicate contract tests inside unit (defeats the point: the
  contract is single).
- Don't write a test that depends on real time/IO inside `unit/`.
- Don't let a hand-rolled double of a port violate the port's
  **invariants** (e.g., serve a state the contract forbids). Every
  double — canonical fake or ergonomic per-test stub — inherits the
  contract's invariants even when the contract itself is proven
  elsewhere; an assert built on top of a violated invariant is
  **vacuous** (it can never fail for the reason it claims to test).

## Example

```python
# tests/unit/application/test_create_user.py
def test_create_user_persists_with_hashed_password() -> None:
    repo = FakeUserRepository()
    use_case = CreateUserUseCase(repo=repo, hasher=BcryptHasher())

    result = use_case.execute(CreateUserDTO(email="x@y.com", password="abc"))

    saved = repo.get(result.id)
    assert saved is not None
    assert saved.password_hash != "abc"
```