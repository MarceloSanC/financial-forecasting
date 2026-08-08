---
name: repository-pattern
description: Persistence adapter (repository) patterns — implementing an out port, domain↔ORM mappers, transaction boundaries. Load on Stages whose target layer is adapters/out (SQLAlchemy, MongoDB, etc.).
metadata:
  status: draft
  applies_when:
    camada_alvo: [adapters/out]
---

# Repository Pattern (out adapter for persistence)

## Principle

A repository is the concrete implementation of an **out port** declared
in `application/ports/`. The port states what `application/` needs; the
repository delivers it using the chosen technology (SQLAlchemy, etc.).

## Structure

```
adapters/out/postgres/
├── repositories/
│   └── user_repo.py       # implements application.ports.UserRepository
├── tables/
│   └── user_table.py      # SQLAlchemy Table/Model
└── mappers/
    └── user_mapper.py     # User (domain) ↔ UserTable (ORM)
```

## DO

- Implement the port interface exactly. Same method names, same type
  signatures.
- Mapper is a pure function: `to_domain(row) -> User`,
  `to_table(user) -> UserTable`. No business logic.
- Transaction is controlled by the **unit-of-work** or by the layer
  that orchestrates the call — never implicitly inside the repository.
- Infra errors (connection, integrity) become appropriate domain
  exceptions (`UserAlreadyExists`, etc.) before bubbling up to
  `application/`.

## DON'T

- Don't return `UserTable` (ORM) — always return `User` (domain).
- Don't `.commit()` inside the method. Whoever orchestrates commits.
- Don't use a module-global `Session` — receive it via constructor (DI).
- Don't duplicate validation logic that already lives in the domain.

## Example

```python
class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: UserId) -> User | None:
        row = self._session.get(UserTable, user_id.value)
        return user_mapper.to_domain(row) if row else None

    def save(self, user: User) -> None:
        row = user_mapper.to_table(user)
        self._session.merge(row)
        # commit is the caller's responsibility
```

## Testes que pulam em silêncio (regra de gatilho — não pular)

Parte dos contract/integration tests de adapter deste repo é **gated por
disponibilidade**, não por escolha: `pytest.mark.skipif` quando o extra `ml`
(`torch`/`transformers`) não está instalado, ou quando o oráculo/fixture de
dado não existe no ambiente. O `make check`/CI **não os executa** — eles
aparecem como `SKIPPED`, que lê como verde.

Consequência: mudança de assinatura ou de semântica num adapter (ou no port
dele) pode quebrar o teste gated e **ninguém vê** — ele apodrece em silêncio
até a próxima auditoria.

**Gatilho:** ao tocar adapter de persistência, port out correspondente, fake
espelho ou schema-espelho de teste, rodar ANTES do commit da Task o
subconjunto gated dirigido, num ambiente onde as dependências existam:

```bash
uv run --extra ml pytest tests/contract/features/<bc> \
  tests/integration/features/<bc> -q
```

Subconjunto **dirigido**, nunca `tests/` inteiro com todos os extras (a
suíte completa gated é lenta e tem interferências). Se o teste continuar
skipado por falta de fixture/oráculo, isso é a resposta — registre como
`[finding]` em vez de assumir cobertura.
