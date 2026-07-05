"""Serviço de domínio: dedup operationally-latest por chave de alinhamento OOS.

Domínio puro (stdlib-only). Em folds walk-forward sobrepostos, um mesmo ponto OOS
realizado — identificado pela chave de alinhamento `(asset, split-scope, horizonte,
target_timestamp, quantile_level)` que espelha a PK LONG do `analytics_store`
(ADR 4.1.0002) — pode receber mais de uma predição (de decisões/folds distintos).
A métrica confirmatória exige **1 observação por unidade**, com alinhamento estrito
por `target_timestamp` (overview §OOS; ADR 0.0.0018 regra 5).

`deduplicate_operationally_latest` colapsa esses registros mantendo, por chave, o
**operacionalmente mais recente** — o de maior `operational_rank` (ex.: índice do
fold / da decisão mais recente). Empate exato (mesma chave, mesmo rank) **ergue**
`ValueError`: "operacionalmente mais recente" seria ambíguo e o projeto não
fabrica um desempate silencioso (concept §7 D5).

A função é **genérica** (recebe callables de chave e rank) porque as predições
concretas só existem a partir da Stage 5.2 — o harness fixa apenas a política.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Iterable


def deduplicate_operationally_latest[T](
    records: Iterable[T],
    *,
    alignment_key: Callable[[T], Hashable],
    operational_rank: Callable[[T], int],
) -> tuple[T, ...]:
    """Mantém, por chave de alinhamento, o registro de maior `operational_rank`.

    Args:
        records: registros a deduplicar (ordem define o desempate de saída).
        alignment_key: extrai a chave de alinhamento OOS (hashable) de um registro.
        operational_rank: extrai o rank operacional (int); maior = mais recente.

    Returns:
        Tupla com um registro por chave distinta (o de maior rank), na ordem da
        **primeira aparição** de cada chave na entrada.

    Raises:
        ValueError: dois registros compartilham chave e `operational_rank` (o
            "mais recente" seria ambíguo).
    """
    chosen: dict[Hashable, tuple[int, T]] = {}
    for record in records:
        key = alignment_key(record)
        rank = operational_rank(record)
        existing = chosen.get(key)
        if existing is None:
            chosen[key] = (rank, record)
            continue
        existing_rank, _ = existing
        if rank == existing_rank:
            raise ValueError(
                "ambiguous operationally-latest: two records share alignment key "
                f"{key!r} at the same operational_rank {rank}"
            )
        if rank > existing_rank:
            chosen[key] = (rank, record)
    return tuple(record for _, record in chosen.values())
