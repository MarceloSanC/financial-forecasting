"""Smoke test mínimo — garante que o pacote raiz e o esqueleto hexagonal importam sem erro.

Esse teste existe desde o bootstrap para:
1. Manter `make test` retornando exit 0 antes da primeira feature chegar
   (pytest retornaria exit 5 ['no tests collected'] sem nenhum teste, e make
   trataria isso como falha do gate).
2. Falhar imediatamente se o pacote ficar com import quebrado por mudança
   de estrutura ou ausência de `__init__.py` — agora cobrindo também os
   subpacotes de camada do hexágono (`shared.{domain,application,
   infrastructure}` e `features`), de modo que uma quebra de import no
   esqueleto não passe silenciosamente (invariante I7 da Stage 1.1).

`import financial_forecasting` é substituído textualmente para `import <pkg_name>` pelo
`scripts/init-project.py` durante o bootstrap. Cada projeto fica importando
o seu próprio pacote.
"""

import importlib

import pytest

import financial_forecasting  # noqa: F401

# Subpacotes de camada do esqueleto hexagonal que devem importar sempre.
# Só o pacote `features` (não submódulos de slice, que ainda não existem).
HEXAGONAL_SKELETON = [
    "financial_forecasting.shared.domain",
    "financial_forecasting.shared.application",
    "financial_forecasting.shared.infrastructure",
    "financial_forecasting.features",
]


def test_package_imports() -> None:
    """Marcador: se a coleta do pytest chegou aqui, o import top-level passou."""


@pytest.mark.parametrize("module_name", HEXAGONAL_SKELETON)
def test_hexagonal_skeleton_imports(module_name: str) -> None:
    """Cada subpacote de camada do hexágono importa sem erro (I7)."""
    importlib.import_module(module_name)
