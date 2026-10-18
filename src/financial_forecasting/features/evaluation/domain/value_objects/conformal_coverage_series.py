"""VO `ConformalCoverageSeries` — limites conformais sobre a série nativa embutida (ADR 7.2.0004).

Value object de domínio frozen, stdlib-only (concept 7.2 §4 "Evaluation — domain", I8).
Embute a `CoverageSeries` nativa de **uma** seed e **um** horizonte (o candidato,
`model_full`) e, por par simétrico da grade nativa, um limite conformal inferior e um
superior por ponto nativo. Os limites chegam como floats (sem import do `inference`,
ADR 7.2.0004 item 5): NaN é recusado, ±∞ é aceito (a correção infinita do C2 da
inferência). Um intervalo cruzado (L > U) é saída válida e nunca é trocado (I5).

A máscara de degeneração é a da série embutida (ADR 6.1.0004): não existe caminho para
medir a cobertura conformal com a máscara de outra série.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_real_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._integer import is_int
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    MEDIAN_LEVEL,
    CoverageSeries,
    is_symmetric_pair,
)


@dataclass(frozen=True)
class ConformalPairLimits:
    """Limites conformais de um par simétrico, um por ponto da série nativa."""

    lower_level: float
    upper_level: float
    lower: tuple[float, ...]  # 1 por ponto nativo; ±inf ok, NaN não
    upper: tuple[float, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "lower", tuple(self.lower))
        object.__setattr__(self, "upper", tuple(self.upper))
        pair = (self.lower_level, self.upper_level)
        if not all(is_real_number(level) for level in pair):
            raise ValueError(f"lower_level/upper_level must be numbers, got {pair}")
        if not 0.0 < self.lower_level < MEDIAN_LEVEL or not is_symmetric_pair(*pair):
            raise ValueError(f"lower_level/upper_level {pair} is not a symmetric pair")
        if len(self.lower) != len(self.upper):
            raise ValueError(
                f"lower and upper must align, got lengths {len(self.lower)} and {len(self.upper)}"
            )
        for name, values in (("lower", self.lower), ("upper", self.upper)):
            for index, value in enumerate(values):
                if not is_real_number(value) or math.isnan(value):
                    raise ValueError(f"{name}[{index}] must be a number (not NaN), got {value!r}")


@dataclass(frozen=True)
class ConformalCoverageSeries:
    """Série nativa embutida + limites conformais de uma variante, por par."""

    seed: int  # a seed da série nativa (vai ao ConformalCoverageReport)
    native: CoverageSeries  # candidato, uma seed, um horizonte (model_full)
    variant: str
    pairs: tuple[ConformalPairLimits, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "pairs", tuple(self.pairs))
        if not is_int(self.seed):
            raise ValueError(f"seed must be an int, got {self.seed!r}")
        if not isinstance(self.native, CoverageSeries):
            raise ValueError(f"native must be a CoverageSeries, got {type(self.native).__name__}")
        if not isinstance(self.variant, str) or not self.variant:
            raise ValueError(f"variant must be a non-empty string, got {self.variant!r}")
        if not self.pairs:
            raise ValueError("pairs must hold at least one ConformalPairLimits")
        seen: set[tuple[float, float]] = set()
        for index, limits in enumerate(self.pairs):
            pair = (limits.lower_level, limits.upper_level)
            if pair not in self.native.symmetric_pairs:
                raise ValueError(
                    f"pairs[{index}] {pair} is not a symmetric pair of the native grid "
                    f"{self.native.symmetric_pairs}"
                )
            if pair in seen:
                raise ValueError(f"pairs[{index}] {pair} is duplicated")
            seen.add(pair)
            if len(limits.lower) != self.native.n_points:
                raise ValueError(
                    f"pairs[{index}] has {len(limits.lower)} limits for "
                    f"{self.native.n_points} native points"
                )
