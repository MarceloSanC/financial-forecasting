---
name: fastapi-thin-adapter
description: Thin FastAPI adapter patterns — router, Pydantic schemas only at the adapter boundary, mapping domain exceptions to HTTP. Load on Stages whose target layer is adapters/in/http (FastAPI REST endpoints).
metadata:
  status: draft
  applies_when:
    camada_alvo: [adapters/in/http]
---

# FastAPI as a thin adapter

## Principle

FastAPI router is a **transport adapter**. It has no business logic,
does not access the database directly, does not orchestrate use cases —
it only:
1. Validates input via Pydantic schema.
2. Calls a use case from `application/`.
3. Maps the result/exception to HTTP.

## Structure

```
adapters/in/http/
├── routers/
│   └── users.py          # APIRouter, endpoints
├── schemas/
│   └── user.py           # Pydantic models (request/response)
├── exception_handlers.py # maps domain exceptions → HTTPException
└── dependencies.py       # Depends() — injects use cases via composition_root
```

## DO

- Pydantic schemas live **only** under `adapters/in/http/schemas/`.
- Endpoint converts schema → application DTO before calling the use case.
- Response is built from the DTO returned by the use case.
- Domain exceptions (`UserNotFound`, `InvalidEmail`) become
  `HTTPException` in `exception_handlers.py`, not inside the router.

## DON'T

- Don't import `domain/` directly in a Pydantic schema.
- Don't use Pydantic as a domain entity.
- Don't run SQL queries inside the router — call a use case.
- Don't catch exceptions and return JSON manually — register a handler.

## Example

```python
# routers/users.py
@router.post("/users", response_model=UserResponse)
def create_user(
    body: CreateUserRequest,
    use_case: CreateUserUseCase = Depends(get_create_user_use_case),
) -> UserResponse:
    dto = body.to_dto()
    result = use_case.execute(dto)
    return UserResponse.from_dto(result)
```
