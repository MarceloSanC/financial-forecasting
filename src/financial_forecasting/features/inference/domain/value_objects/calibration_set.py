"""`CalibrationSet` — calib dedicado de uma unidade conformal, com embargo (concept 7.2 §4, I7).

Uma unidade é (fold, seed, horizonte, par simétrico). Cada `CalibrationPoint` valida
os próprios campos (valor finito; timestamp ISO 8601 com fuso, nunca o `TypeError`
naive vs aware). O `CalibrationSet` valida as regras entre pontos e contra o teste:
calib vazio; `target_timestamp` não estritamente crescente; decisão de calib ≥
`test_start`; alvo de calib ≥ `test_start` (nenhum alvo do calib sobrepõe o teste,
o embargo); par não simétrico ou τ_lo fora de (0; 0,5). Toda recusa é `ValueError`
nomeando o campo.

`exact_level` mora aqui (o VO confere o par com ela; o calibrador importa o VO e a
reexporta): o nível vira o seu decimal mais curto, `Fraction(repr(level))` —
0,1 é 1/10 e 0,99 é 99/100, não o binário do float (ADR 7.2.0002 item 2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction

_HALF = Fraction(1, 2)


def exact_level(level: float) -> Fraction:
    """Decimal mais curto do nível, exato: `Fraction(repr(level))`; recusa bool e não finito."""
    if isinstance(level, bool) or not isinstance(level, int | float):
        raise ValueError(f"level must be a finite number, got {level!r}")
    if not math.isfinite(level):
        raise ValueError(f"level must be finite, got {level!r}")
    return Fraction(repr(level))


def _instant(value: str, field: str) -> datetime:
    """ISO 8601 com fuso; texto inválido ou sem fuso → `ValueError` nomeando o campo."""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field}: {value!r} is not an ISO 8601 timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field}: {value!r} has no time zone")
    return parsed


@dataclass(frozen=True)
class CalibrationPoint:
    """Um ponto do calib: decisão, alvo (decisão + h pregões), q̂ do par e o realizado."""

    decision_timestamp: str
    target_timestamp: str
    lower: float  # q̂_{τ_lo} do vetor rearranjado (`value_guardrail`, I2)
    upper: float  # q̂_{τ_hi} do vetor rearranjado
    realized: float  # y no `target_timestamp`

    def __post_init__(self) -> None:
        _instant(self.decision_timestamp, "decision_timestamp")
        _instant(self.target_timestamp, "target_timestamp")
        for field in ("lower", "upper", "realized"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError(f"{field}: {value!r} is not a number")
            if not math.isfinite(value):
                raise ValueError(f"{field}: {value!r} is not finite")


@dataclass(frozen=True)
class CalibrationSet:
    """Calib de uma unidade (fold, seed, horizonte, par), validado contra o teste (I7)."""

    fold_index: int
    seed: int
    horizon: int
    lower_level: float  # τ_lo; par simétrico τ_lo + τ_hi = 1
    upper_level: float
    points: tuple[CalibrationPoint, ...]  # ordem crescente de `target_timestamp`
    test_start: str  # timestamp da 1ª decisão de teste do fold

    def __post_init__(self) -> None:
        object.__setattr__(self, "points", tuple(self.points))
        self._check_pair()
        if not self.points:
            raise ValueError("points: the calibration set is empty")
        test_start = _instant(self.test_start, "test_start")
        previous: datetime | None = None
        for index, point in enumerate(self.points):
            name = f"points[{index}]"
            decision = _instant(point.decision_timestamp, f"{name}.decision_timestamp")
            target = _instant(point.target_timestamp, f"{name}.target_timestamp")
            if previous is not None and target <= previous:
                raise ValueError(
                    f"{name}.target_timestamp: {point.target_timestamp!r} is not strictly "
                    "after the previous target"
                )
            previous = target
            if decision >= test_start:
                raise ValueError(
                    f"{name}.decision_timestamp: {point.decision_timestamp!r} is not before "
                    f"test_start {self.test_start!r}"
                )
            if target >= test_start:
                raise ValueError(
                    f"{name}.target_timestamp: {point.target_timestamp!r} is not before "
                    f"test_start {self.test_start!r} (sem sobreposição com o teste; "
                    "o gap do embargo vem do FoldSplit)"
                )

    def _check_pair(self) -> None:
        low = exact_level(self.lower_level)
        high = exact_level(self.upper_level)
        if low + high != 1:
            raise ValueError(
                f"lower_level/upper_level: ({self.lower_level!r}, {self.upper_level!r}) "
                "is not a symmetric pair (lower + upper != 1 exactly)"
            )
        if not 0 < low < _HALF:
            raise ValueError(f"lower_level: {self.lower_level!r} is not in (0, 0.5)")
