---
name: import-linter-rules
description: How to read, update, and add import-linter contracts that mirror LAYOUT.md. Load on Stage 1.1-bootstrap (initial contracts) and any Stage that changes dependency rules between layers/BCs.
metadata:
  status: accepted
  applies_when:
    camada_alvo: [any]
    fase: [any]
---

# import-linter — contracts mirroring LAYOUT.md

## Principle

import-linter is the **structural enforcement** of LAYOUT.md rules.
Every LAYOUT rule that translates into "module X cannot import Y"
becomes a contract. Without a contract, the rule is just prose — it
will be violated.

## `.importlinter` shape

```ini
[importlinter]
root_packages =
    myproject

[importlinter:contract:layered-architecture]
name = Hexagonal layers
type = layers
layers =
    myproject.adapters
    myproject.application
    myproject.domain
```

`type = layers` means: **upper** layers may import lower ones; lower
ones **cannot** import upper ones.

## Common contract types

- `type = layers` — dependency direction between layers.
- `type = forbidden` — forbid a specific import (e.g., `domain` may not
  import `pydantic`).
- `type = independence` — forbid BCs from importing each other (keeps
  vertical slicing).

## DO

- Every LAYOUT.md rule has a matching contract. If a rule has no
  contract, either the contract is missing or the rule isn't real.
- Run `lint-imports` in pre-commit + CI.
- When adding a new BC, update `independence` to include it.
- import-linter error messages in PRs are actionable: include them in
  the review guideline.

## DON'T

- Don't `# noqa` to silence import-linter — either the rule is wrong
  (revisit LAYOUT) or the code is wrong (refactor).
- Don't write a vague/generic contract that approves everything.
- Don't disable the linter in CI — blocking gate.

## Anti-example

```python
# ❌ domain importing pydantic — caught by the forbidden contract
from pydantic import BaseModel

class User(BaseModel):
    id: str
```

Fix: dataclass + manual validation in `__post_init__`, or Pydantic
only at the adapter boundary.
