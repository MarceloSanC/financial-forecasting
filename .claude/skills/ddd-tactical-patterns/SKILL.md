---
name: ddd-tactical-patterns
description: DDD tactical patterns — Entity vs Value Object, aggregates, invariants, identity. Load on Stages whose target layer is domain (modeling entities, VOs, aggregates).
metadata:
  status: draft
  applies_when:
    camada_alvo: [domain]
---

# DDD tactical patterns in Python

## Entity vs Value Object

**Entity:** unique identity (ID), lifecycle, mutable. Equality by ID.
Examples: `User`, `Order`, `Subscription`.

**Value Object:** identity by value, immutable. Structural equality.
No own ID. Examples: `Money`, `Email`, `Address`, `DateRange`.

```python
@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        if "@" not in self.value:
            raise InvalidEmail(self.value)

@dataclass
class User:
    id: UserId          # identity
    email: Email        # value object as attribute
    name: str
```

## Aggregate

A grouping of entities + VOs with **one root** (aggregate root).
External access only via the root. Guarantees **transactional
consistency** invariants.

Rule: 1 transaction = 1 aggregate. If you need to update 2 aggregates
in the same operation, there is a modeling problem (the aggregate is
likely poorly defined) or use eventual consistency between them.

## Invariants

Rules that **always** hold for the entity. Enforced in the constructor
+ in methods that mutate state. Violation = exception, never invalid
transient state.

```python
class Order:
    def __init__(self, id: OrderId, items: list[OrderItem]) -> None:
        if not items:
            raise EmptyOrder()
        self.id = id
        self._items = items

    def add_item(self, item: OrderItem) -> None:
        if self.is_paid():
            raise CannotModifyPaidOrder(self.id)
        self._items.append(item)
```

## DO

- VO frozen (`@dataclass(frozen=True)`), validation in `__post_init__`.
- Entity never exposed in invalid state.
- Invariant inside a method, not via free access to `_items` from
  outside.
- Domain methods named after the **business** (`pay`, `cancel`,
  `add_item`), not generic CRUD.

## DON'T

- Don't model everything as Entity by habit — VO is cheaper and more
  expressive when it fits.
- Don't allow a constructor that creates an invalid entity.
- Don't leak the aggregate from inside: a getter for an internal list
  must return a copy or tuple.
- Don't mix two aggregates in a use case and commit everything together
  without thinking about consistency.
