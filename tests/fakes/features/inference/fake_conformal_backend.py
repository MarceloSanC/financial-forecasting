"""Fake do port `ConformalBackend` — Q pelo posto exato do domain (concept 7.2 §1, Fakes novos).

Sem fórmula própria: o posto vem de `split_conformal_rank` do domain, o alpha por
`exact_level`, e Q é o k-ésimo menor escore ordenado (+inf quando k > n). Não
reproduz os defeitos do MAPIE (o posto +1 em n divergentes e a recusa de n
pequeno): a suíte de contrato roda o fake só nos tamanhos de coincidência.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from financial_forecasting.features.inference.domain.services.conformal_calibrator import (
    exact_level,
    split_conformal_rank,
)


def _correction(scores: list[float], tail_alpha: float) -> float:
    rank = split_conformal_rank(len(scores), exact_level(tail_alpha))
    return math.inf if rank > len(scores) else sorted(scores)[rank - 1]


class FakeConformalBackend:
    """Satisfaz `ConformalBackend` com o posto exato do domain sobre os escores."""

    def split_cqr_corrections(
        self,
        *,
        calib_lower: Sequence[float],
        calib_upper: Sequence[float],
        calib_realized: Sequence[float],
        tail_alpha: float,
    ) -> tuple[float, float]:
        if not len(calib_lower) == len(calib_upper) == len(calib_realized):
            raise ValueError("calib_lower, calib_upper and calib_realized must align")
        lower = [q - y for q, y in zip(calib_lower, calib_realized, strict=True)]
        upper = [y - q for q, y in zip(calib_upper, calib_realized, strict=True)]
        return _correction(lower, tail_alpha), _correction(upper, tail_alpha)
