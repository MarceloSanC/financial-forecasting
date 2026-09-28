"""Serviço de domínio `WilsonBand` — banda de Wilson da cobertura empírica (doc §4.4).

stdlib-only (concept 6.3 §4, I1, I4, I10, C3, C7, C9; ADR `6_3_0005`). Sob
calibração e independência dos hits, c ~ Binomial(n, p); a banda é o intervalo de
Wilson de Brown, Cai & DasGupta (2001, §3.1.1, Eq. (4)), com p̂ = c/n e
κ = z_{(1-nível)/2} tirado de `statistics.NormalDist` (sem scipy):

    centro = (c + κ²/2) / (n + κ²)
    meia-largura = κ·√n / (n + κ²) · √(p̂(1 - p̂) + κ²/(4n))

O veredito é "a banda **contém o nominal**" (convenção B-BANDAS, doc §4.4 e §10.1).

- `count`/`n` podem ser **reais**: a 6.5 passa a contagem média entre seeds e o
  número médio de pontos não-degenerados (ADR `6_3_0005`); n é o de **um** conjunto
  de pontos alinhados, nunca S·T (doc §4.4). A validação é a do validador único dos
  kernels de contagem (`count_input_validation`), sem cópia.
- n = 0 (série 100 % degenerada — baselines pontuais) → relatório "não aplicável"
  (C7), não erro.
- `horizon > 1` liga o aviso de dependência serial: a banda binomial pressupõe hits
  iid e é anti-conservadora para h > 1 (doc §4.4, §7.4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

from financial_forecasting.features.evaluation.domain.services.count_input_validation import (
    validate_rate,
    validate_real_count,
)
from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    validate_horizon,
)


def wilson_interval(*, count: float, n: float, band_level: float) -> tuple[float, float]:
    """Limites (inferior, superior) de Wilson, BCD 2001 Eq. (4), no nível da banda.

    Args:
        count: violações (ou acertos) c — real em [0, n] (média entre seeds é válida).
        n: pontos da proporção — real > 0.
        band_level: nível da banda, em (0, 1) (ex.: 0.95; 0.975 por cauda no gate H1).

    Raises:
        ValueError: contagem/n fora do contrato de `validate_real_count` ou
            `band_level` fora de (0, 1), não-finito ou `bool` (C3).
    """
    validate_real_count(count, n, count_field="count", n_field="n")
    validate_rate(band_level, field="band_level")
    # κ = -Φ⁻¹((1 - nível)/2): argumento exato em float (a forma 1 - (1 - nível)/2 vira
    # 1.0 para nível ≈ 1 e o `NormalDist` ergue sem nome de campo).
    kappa = -NormalDist().inv_cdf((1.0 - band_level) / 2.0)
    kappa_sq = kappa * kappa
    proportion = count / n
    center = (count + kappa_sq / 2.0) / (n + kappa_sq)
    half_width = (
        kappa
        * math.sqrt(n)
        / (n + kappa_sq)
        * math.sqrt(proportion * (1.0 - proportion) + kappa_sq / (4.0 * n))
    )
    # A Eq. (4) cai em [0, 1]; o recorte só remove o arredondamento das pontas (c = 0
    # dava -5.55e-17, c = n dava 1.0000000000000002) — a banda persistida é uma proporção.
    return max(0.0, center - half_width), min(1.0, center + half_width)


@dataclass(frozen=True)
class WilsonBandReport:
    """Banda de Wilson de uma série x horizonte e o veredito contém-o-nominal.

    Campos:
        horizon: horizonte da série de origem (≥ 1; I1).
        count: violações (real: pode ser média entre seeds — ADR 6.3.0005).
        n: pontos não-degenerados (nunca S·T); 0 ⇒ não aplicável.
        nominal: taxa nominal de violação, em (0, 1).
        band_level: nível da banda, em (0, 1).
        applicable: `False` ⇔ `n == 0` (série 100 % degenerada).
        estimate: `count / n`; `None` se não aplicável.
        lower / upper: limites de Wilson; `None` se não aplicável.
        contains_nominal: `lower ≤ nominal ≤ upper` — o veredito (doc §4.4); `None`
            se não aplicável.
        serial_dependence_warning: `horizon > 1` — banda anti-conservadora (doc §4.4,
            §7.4).

    Raises:
        ValueError: relatório incoerente (C9), um ramo por invariante.
    """

    horizon: int
    count: float
    n: float
    nominal: float
    band_level: float
    applicable: bool
    estimate: float | None
    lower: float | None
    upper: float | None
    contains_nominal: bool | None
    serial_dependence_warning: bool

    def __post_init__(self) -> None:
        """C9: horizonte, taxas, aplicabilidade, banda e aviso coerentes entre si."""
        validate_horizon(self.horizon, field="horizon")
        validate_rate(self.nominal, field="nominal")
        validate_rate(self.band_level, field="band_level")
        if self.serial_dependence_warning != (self.horizon > 1):
            raise ValueError(
                "serial_dependence_warning must be (horizon > 1), got "
                f"{self.serial_dependence_warning!r} for horizon={self.horizon}"
            )
        if self.applicable != (self.n > 0):
            raise ValueError(f"applicable must be (n > 0), got {self.applicable!r} with n={self.n}")
        band = (self.estimate, self.lower, self.upper, self.contains_nominal)
        if not self.applicable:
            is_zero = all(is_finite_number(v) and v == 0 for v in (self.n, self.count))
            if not is_zero:
                raise ValueError(
                    f"a non-applicable WilsonBandReport needs n == 0 and count == 0, got "
                    f"n={self.n!r}, count={self.count!r}"
                )
            if any(field is not None for field in band):
                raise ValueError(
                    "a non-applicable WilsonBandReport must have estimate, lower, upper and "
                    "contains_nominal set to None"
                )
            return
        self._check_applicable_band()

    def _check_applicable_band(self) -> None:
        validate_real_count(self.count, self.n, count_field="count", n_field="n")
        if self.estimate is None or self.lower is None or self.upper is None:
            raise ValueError("an applicable WilsonBandReport needs estimate, lower and upper")
        if self.contains_nominal is None:
            raise ValueError("an applicable WilsonBandReport needs contains_nominal")
        expected = self.count / self.n
        if self.estimate != expected:
            raise ValueError(f"estimate must be count / n = {expected}, got {self.estimate}")
        if not 0.0 <= self.lower <= self.upper <= 1.0:
            raise ValueError(
                f"the band must satisfy 0 <= lower <= upper <= 1, got ({self.lower}, {self.upper})"
            )
        verdict = self.lower <= self.nominal <= self.upper
        if self.contains_nominal != verdict:
            raise ValueError(
                f"contains_nominal must be (lower <= nominal <= upper) = {verdict}, got "
                f"{self.contains_nominal!r}"
            )


class WilsonBand:
    """Banda de Wilson + veredito contém-o-nominal, por série x horizonte (doc §4.4)."""

    @staticmethod
    def evaluate(
        *, horizon: int, count: float, n: float, nominal: float, band_level: float
    ) -> WilsonBandReport:
        """Relatório da banda; n = 0 (com count = 0) → "não aplicável" (C7).

        Raises:
            ValueError: `horizon` não-`int`, `bool` ou < 1; `nominal` ou `band_level`
                fora de (0, 1), não-finitos ou `bool`; contagem inválida (C3); n = 0
                com count ≠ 0.
        """
        validate_horizon(horizon, field="horizon")
        validate_rate(nominal, field="nominal")
        validate_rate(band_level, field="band_level")
        warning = horizon > 1
        if is_finite_number(n) and n == 0:
            if not (is_finite_number(count) and count == 0):
                raise ValueError(f"count must be 0 when n == 0, got {count!r}")
            return WilsonBandReport(
                horizon=horizon,
                count=count,
                n=n,
                nominal=nominal,
                band_level=band_level,
                applicable=False,
                estimate=None,
                lower=None,
                upper=None,
                contains_nominal=None,
                serial_dependence_warning=warning,
            )
        lower, upper = wilson_interval(count=count, n=n, band_level=band_level)
        return WilsonBandReport(
            horizon=horizon,
            count=count,
            n=n,
            nominal=nominal,
            band_level=band_level,
            applicable=True,
            estimate=count / n,
            lower=lower,
            upper=upper,
            contains_nominal=lower <= nominal <= upper,
            serial_dependence_warning=warning,
        )
