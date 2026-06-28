"""Smoke test mínimo — garante que o pacote raiz importa sem erro.

Esse teste existe desde o bootstrap para:
1. Manter `make test` retornando exit 0 antes da primeira feature chegar
   (pytest retornaria exit 5 ['no tests collected'] sem nenhum teste, e make
   trataria isso como falha do gate).
2. Falhar imediatamente se o pacote ficar com import quebrado por mudança
   de estrutura ou ausência de `__init__.py`.

`import financial_forecasting` é substituído textualmente para `import <pkg_name>` pelo
`scripts/init-project.py` durante o bootstrap. Cada projeto fica importando
o seu próprio pacote.
"""

import financial_forecasting  # noqa: F401


def test_package_imports() -> None:
    """Marcador: se a coleta do pytest chegou aqui, o import top-level passou."""
