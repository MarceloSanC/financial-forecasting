"""`gold_build_order` — ordem dos builders do gold pelas dependências declaradas (6.4).

Serviço de domínio stdlib-only (concept 6.4 §4, D7, I14, C1; ADR `6_4_0001`). Cada
builder declara o próprio nome e o conjunto de nomes de que depende; a ordem sai do
`graphlib.TopologicalSorter` da stdlib, alimentado **em ordem de nome** (nós e
dependências ordenados), para que qualquer ordem de registro dê a mesma sequência.

Validação própria antes da ordenação (`ValueError`, antes de qualquer leitura — C1):
nome repetido, auto-dependência, dependência de builder não registrado (a mensagem
nomeia os dois) e ciclo (`graphlib.CycleError` convertido, com o ciclo em
`args[1]` na mensagem).
"""

from __future__ import annotations

from collections.abc import Sequence
from graphlib import CycleError, TopologicalSorter


def gold_build_order(builders: Sequence[tuple[str, frozenset[str]]]) -> tuple[str, ...]:
    """Nomes dos builders em ordem de dependência (dependências primeiro).

    Args:
        builders: `(nome, dependências)` por builder, em qualquer ordem.

    Returns:
        Os nomes, cada um depois de todas as suas dependências; empates por nome.

    Raises:
        ValueError: nome vazio/não-`str`, dependências não-`frozenset`, nome repetido,
            auto-dependência, dependência não registrada ou ciclo.
    """
    names = [name for name, _ in builders]
    for name, depends_on in builders:
        if not isinstance(name, str) or not name:
            raise ValueError(f"builder name must be a non-empty str, got {name!r}")
        if not isinstance(depends_on, frozenset):
            raise ValueError(
                f"builder {name!r} dependencies must be a frozenset, got {depends_on!r}"
            )
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise ValueError(f"builder names must be unique, repeated: {repeated}")
    known = set(names)
    for name, depends_on in sorted(builders):
        if name in depends_on:
            raise ValueError(f"builder {name!r} depends on itself")
        unknown = sorted(depends_on - known)
        if unknown:
            raise ValueError(f"builder {name!r} depends on {unknown[0]!r}, which is not registered")
    sorter: TopologicalSorter[str] = TopologicalSorter()
    for name, depends_on in sorted(builders):
        sorter.add(name, *sorted(depends_on))
    try:
        return tuple(sorter.static_order())
    except CycleError as error:
        raise ValueError(f"builder dependency cycle: {error.args[1]}") from error
