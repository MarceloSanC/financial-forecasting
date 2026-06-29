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
3. Guardar a invariante I4 (cada `__init__.py` de camada tem docstring de
   responsabilidade) — o ruff não seleciona pydocstyle (`D`), então sem este
   teste apagar a docstring de uma camada não quebraria nenhum gate.

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

# Camadas que precisam de docstring de responsabilidade (invariante I4 da Stage 1.1).
# Inclui os subpacotes do hexágono + os pacotes-raiz (`financial_forecasting`, `shared`).
# `shared` e o pacote-raiz não estão em HEXAGONAL_SKELETON porque o import deles é
# transitivamente exercido, mas a docstring deles também é exigida por I4/A5.
LAYERS_REQUIRING_DOCSTRING = [
    "financial_forecasting",
    "financial_forecasting.shared",
    *HEXAGONAL_SKELETON,
]


def test_package_imports() -> None:
    """Marcador: se a coleta do pytest chegou aqui, o import top-level passou."""


@pytest.mark.parametrize("module_name", HEXAGONAL_SKELETON)
def test_hexagonal_skeleton_imports(module_name: str) -> None:
    """Cada subpacote de camada do hexágono importa sem erro (I7)."""
    module = importlib.import_module(module_name)
    assert module is not None


@pytest.mark.parametrize("module_name", LAYERS_REQUIRING_DOCSTRING)
def test_layer_has_responsibility_docstring(module_name: str) -> None:
    """Cada `__init__.py` de camada tem docstring de responsabilidade (I4/A5).

    Guarda automatizada da invariante I4 da Stage 1.1: o ruff não seleciona o
    conjunto de regras `D` (pydocstyle), então sem este teste apagar a docstring
    de uma camada passaria por `make check`/`make test` sem nenhum gate falhar.
    """
    module = importlib.import_module(module_name)
    docstring = module.__doc__
    assert docstring is not None, f"camada sem docstring: {module_name}"
    assert docstring.strip(), f"docstring vazia na camada: {module_name}"
