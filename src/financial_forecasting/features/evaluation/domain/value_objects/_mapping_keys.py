"""Mensagens de chave desconhecida/ausente de um mapeamento do plano (dono único).

Consumidas pelo `Preregistration` (esquema recursivo) e pelo `ProfileParameters` (bloco
plano da Stage 6.6): mesmo texto nos dois, um redator só (Checkpoint C bloco 3, L4).
"""

from __future__ import annotations


def unknown_key_error(path: str) -> ValueError:
    """`preregistration has unknown key '<path>'`."""
    return ValueError(f"preregistration has unknown key '{path}'")


def missing_key_error(path: str) -> ValueError:
    """`preregistration misses the key '<path>'`."""
    return ValueError(f"preregistration misses the key '{path}'")
