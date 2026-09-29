"""Regra única de "timestamps estritamente crescentes" dos VOs de série do slice (privado).

Uma observação por ponto, na ordem do tempo (antigo "gate F"; doc §6.7): cada
`target_timestamp` é estritamente maior que o anterior, pela comparação de string ISO
UTC — o formato único do silver, em que a ordem lexicográfica é a cronológica.

Consumidor hoje: a `PairedLossSeries` (6.2). A `CoverageSeries` (6.1) ainda carrega a
cópia byte a byte desta regra; adotar o helper lá fica para depois do merge das Stages
6.2 e 6.3 (a 6.3 edita `coverage_series.py`) — `[finding]` no technical 6.2 §7.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise


def check_strictly_increasing(timestamps: Sequence[str]) -> None:
    """Ergue `ValueError` no primeiro ponto que não é estritamente posterior ao anterior."""
    for index, (previous, current) in enumerate(pairwise(timestamps), 1):
        if current <= previous:
            raise ValueError(
                "target_timestamps must be strictly increasing (unique and ordered): "
                f"point {index} has {current!r} after {previous!r}"
            )
