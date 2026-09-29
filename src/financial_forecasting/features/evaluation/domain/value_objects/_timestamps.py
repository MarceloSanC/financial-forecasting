"""Regra única de "timestamps estritamente crescentes" dos VOs de série do slice (privado).

Uma observação por ponto, na ordem do tempo (antigo "gate F"; doc §6.7): cada
`target_timestamp` é estritamente maior que o anterior, pela comparação de string ISO
UTC — o formato único do silver, em que a ordem lexicográfica é a cronológica.

Consumidores hoje: a `PairedLossSeries` (6.2), a `HitSequence` (6.3) e o
`RealizedReturns` (6.4, com `field="timestamps"`). A `CoverageSeries` (6.1) ainda carrega a
cópia byte a byte desta regra; adotar o helper lá fica para depois do merge das Stages
6.2 e 6.3 (a 6.3 edita `coverage_series.py`) — `[finding]` no technical 6.2 §7.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise


def check_strictly_increasing(
    timestamps: Sequence[str], *, field: str = "target_timestamps"
) -> None:
    """Ergue `ValueError` no primeiro ponto que não é estritamente posterior ao anterior.

    `field` nomeia o campo na mensagem; o padrão (`target_timestamps`) é o das séries da
    6.2/6.3 — o `RealizedReturns` (6.4) passa `"timestamps"`.
    """
    for index, (previous, current) in enumerate(pairwise(timestamps), 1):
        if current <= previous:
            raise ValueError(
                f"{field} must be strictly increasing (unique and ordered): "
                f"point {index} has {current!r} after {previous!r}"
            )
