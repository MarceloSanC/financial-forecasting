"""Serviço de domínio `H1Gate` — o gate H1 sobre contagens médias entre seeds (Stage 6.5).

stdlib-only (concept 6.5 §4, D6, I8, I11, C9; ADR `6_5_0006` itens 1-5). Por
horizonte, sobre a evidência do candidato em `model_full`, variante mascarada,
série inteira (`HorizonEvidence.gate`):

- c̄_l, c̄_u, n̄ = médias entre as seeds pré-registradas; degeneração = média das
  taxas por seed (a maior das duas caudas);
- `WilsonBand.evaluate(count=c̄, n=n̄, nominal, band_level=gate_band_level)` por
  cauda, nominais por `violation_rate_for` (dono da taxa nominal);
- **passa** ⇔ as duas bandas aplicáveis e contendo a nominal ∧ degeneração média
  ≤ `degeneracy_threshold` (limiar inclusivo, ADR 6.5.0006 item 3). Banda não
  aplicável (n̄ = 0, C9) reprova o gate e anula as sensibilidades.

Sensibilidades (perfil, **nunca** veredito — ADR 6.5.0006 item 4), sobre as
mesmas médias: LR_uc de 3 estados (`lr_uc_three_state` + `chi_square_sf(df=2)`,
rejeita se p < `sensitivity_alpha`); DGT para h > 1 (médias de cada sub-série,
banda a 1 - `sensitivity_alpha`/(2h), passa se as 2h bandas contêm a nominal;
h = 1 → `None`); o gate inteiro recomputado na amostra comum. Toda sensibilidade
cujo resultado difere do gate é listada em `divergences`, nos dois sentidos.

O poder (`H1GatePower`) é declarado por cenário em n = round(n̄) (vazio se
n̄ < 0,5); ignora a degeneração e, para h > 1, assume hits independentes
(`power_assumes_independence`, otimista — doc §4.4).

Nada é recomputado do gold (I8): só médias, os kernels de contagem e o poder. A
assinatura é a do concept (`evaluate(spec, evidence)`); quem confere
`rules.h1_gate.form` contra o catálogo é o `ConfirmatoryScorecard.decide`, que
recebe o plano inteiro. `tail_bands` é o método público que o perfil reusa para
os comparadores e para a banda a 95 % (Task 09) — sem segunda escrita da regra.
"""

from __future__ import annotations

from dataclasses import dataclass

from financial_forecasting.features.evaluation.domain.services.chi_square import chi_square_sf
from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    lr_uc_three_state,
)
from financial_forecasting.features.evaluation.domain.services.h1_gate_power import H1GatePower
from financial_forecasting.features.evaluation.domain.services.wilson_band import (
    WilsonBand,
    WilsonBandReport,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    is_multi_step,
)
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitKind,
    violation_rate_for,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    H1GateSpec,
    ScenarioRole,
)
from financial_forecasting.features.evaluation.domain.value_objects.scorecard_evidence import (
    CalibrationEvidence,
    HorizonEvidence,
    TailEvidence,
)

LR_UC_SENSITIVITY: str = "lr_uc_three_state"
DGT_SENSITIVITY: str = "dgt"
COMMON_SAMPLE_SENSITIVITY: str = "common_sample"
_LR_UC_DF = 2


@dataclass(frozen=True)
class GatePower:
    """Probabilidade de reprovar o gate sob um cenário, no n inteiro declarado."""

    label: str
    role: ScenarioRole
    n: int
    failure_probability: float


@dataclass(frozen=True)
class LrUcSensitivity:
    """LR_uc de 3 estados sobre as médias: estatística, p (χ²(2)) e rejeição."""

    statistic: float
    p_value: float
    rejected: bool


@dataclass(frozen=True)
class DgtSensitivity:
    """As 2h bandas DGT (inferior e superior por offset) e se todas contêm a nominal."""

    band_level: float
    bands: tuple[WilsonBandReport, ...]
    passed: bool


@dataclass(frozen=True, kw_only=True)
class H1Result:
    """Resultado do gate H1 de um horizonte (ADR 6.5.0006 itens 3-5)."""

    horizon: int
    passed: bool
    lower_band: WilsonBandReport
    upper_band: WilsonBandReport
    mean_observed: float
    common_points: int
    serial_dependence_warning: bool
    mean_degeneracy_rate: float
    degeneracy_above_threshold: bool
    mean_of_seed_rates: tuple[float | None, float | None]
    power: tuple[GatePower, ...]
    power_assumes_independence: bool
    lr_uc: LrUcSensitivity | None
    dgt: DgtSensitivity | None
    common_sample_passed: bool | None
    divergences: tuple[str, ...]


def _contains(band: WilsonBandReport) -> bool:
    return band.applicable and band.contains_nominal is True


class H1Gate:
    """O gate H1 por horizonte e as suas sensibilidades (ver docstring do módulo)."""

    @staticmethod
    def tail_bands(
        spec: H1GateSpec,
        *,
        horizon: int,
        lower: TailEvidence,
        upper: TailEvidence,
        band_level: float,
    ) -> tuple[WilsonBandReport, WilsonBandReport]:
        """Bandas de Wilson das duas caudas sobre as médias entre seeds (c̄/n̄)."""
        lower_nominal = violation_rate_for(HitKind.LOWER_TAIL, (spec.lower_level,))
        upper_nominal = violation_rate_for(HitKind.UPPER_TAIL, (spec.upper_level,))
        return (
            WilsonBand.evaluate(
                horizon=horizon,
                count=lower.mean_violations,
                n=lower.mean_observed,
                nominal=lower_nominal,
                band_level=band_level,
            ),
            WilsonBand.evaluate(
                horizon=horizon,
                count=upper.mean_violations,
                n=upper.mean_observed,
                nominal=upper_nominal,
                band_level=band_level,
            ),
        )

    @staticmethod
    def _passes(spec: H1GateSpec, horizon: int, evidence: CalibrationEvidence) -> bool:
        lower, upper = H1Gate.tail_bands(
            spec,
            horizon=horizon,
            lower=evidence.lower,
            upper=evidence.upper,
            band_level=spec.gate_band_level,
        )
        within = evidence.mean_degeneracy <= spec.degeneracy_threshold
        return _contains(lower) and _contains(upper) and within

    @staticmethod
    def evaluate(spec: H1GateSpec, evidence: HorizonEvidence) -> H1Result:
        """O gate de um horizonte (ver docstring do módulo).

        Raises:
            ValueError: níveis de alguma cauda (gate, amostra comum ou sub-série DGT)
                diferentes do par pré-registrado (`spec.lower_level`, `spec.upper_level`).
        """
        H1Gate._check_levels(spec, evidence)
        horizon = evidence.horizon
        gate = evidence.gate
        lower_band, upper_band = H1Gate.tail_bands(
            spec,
            horizon=horizon,
            lower=gate.lower,
            upper=gate.upper,
            band_level=spec.gate_band_level,
        )
        mean_degeneracy = gate.mean_degeneracy
        above = mean_degeneracy > spec.degeneracy_threshold
        applicable = lower_band.applicable and upper_band.applicable
        passed = _contains(lower_band) and _contains(upper_band) and not above
        mean_observed = gate.lower.mean_observed
        n_power = round(mean_observed)
        power = tuple(
            GatePower(
                label=scenario.label,
                role=scenario.role,
                n=n_power,
                failure_probability=H1GatePower.failure_probability(
                    n=n_power, spec=spec, deviation=scenario
                ),
            )
            for scenario in spec.power_scenarios
            if n_power >= 1
        )
        lr_uc = H1Gate._lr_uc(spec, gate) if applicable else None
        dgt = H1Gate._dgt(spec, horizon, gate) if applicable else None
        common_passed = H1Gate._passes(spec, horizon, evidence.common) if applicable else None
        divergences: list[str] = []
        if lr_uc is not None and lr_uc.rejected == passed:
            divergences.append(LR_UC_SENSITIVITY)
        if dgt is not None and dgt.passed != passed:
            divergences.append(DGT_SENSITIVITY)
        if common_passed is not None and common_passed != passed:
            divergences.append(COMMON_SAMPLE_SENSITIVITY)
        return H1Result(
            horizon=horizon,
            passed=passed,
            lower_band=lower_band,
            upper_band=upper_band,
            mean_observed=mean_observed,
            common_points=evidence.common_points,
            serial_dependence_warning=lower_band.serial_dependence_warning,
            mean_degeneracy_rate=mean_degeneracy,
            degeneracy_above_threshold=above,
            mean_of_seed_rates=(gate.lower.mean_of_seed_rates, gate.upper.mean_of_seed_rates),
            power=power,
            power_assumes_independence=is_multi_step(horizon),
            lr_uc=lr_uc,
            dgt=dgt,
            common_sample_passed=common_passed,
            divergences=tuple(divergences),
        )

    @staticmethod
    def _check_levels(spec: H1GateSpec, evidence: HorizonEvidence) -> None:
        expected = (spec.lower_level, spec.upper_level)
        pairs = [
            (name, calibration.lower, calibration.upper)
            for name, calibration in (("gate", evidence.gate), ("common", evidence.common))
        ]
        pairs += [
            (f"{name}.dgt[{sub.offset}]", sub.lower, sub.upper)
            for name, calibration in (("gate", evidence.gate), ("common", evidence.common))
            for sub in calibration.dgt
        ]
        for where, lower, upper in pairs:
            if (lower.level, upper.level) != expected:
                raise ValueError(
                    f"{where} levels must be the preregistered pair {expected}, got "
                    f"({lower.level!r}, {upper.level!r})"
                )

    @staticmethod
    def _lr_uc(spec: H1GateSpec, gate: CalibrationEvidence) -> LrUcSensitivity:
        statistic = lr_uc_three_state(
            lower_count=gate.lower.mean_violations,
            upper_count=gate.upper.mean_violations,
            n=gate.lower.mean_observed,
            lower_rate=violation_rate_for(HitKind.LOWER_TAIL, (spec.lower_level,)),
            upper_rate=violation_rate_for(HitKind.UPPER_TAIL, (spec.upper_level,)),
        )
        p_value = chi_square_sf(statistic, df=_LR_UC_DF)
        return LrUcSensitivity(
            statistic=statistic, p_value=p_value, rejected=p_value < spec.sensitivity_alpha
        )

    @staticmethod
    def _dgt(spec: H1GateSpec, horizon: int, gate: CalibrationEvidence) -> DgtSensitivity | None:
        if not is_multi_step(horizon):
            return None
        band_level = 1.0 - spec.sensitivity_alpha / (2 * horizon)
        bands: list[WilsonBandReport] = []
        for sub in gate.dgt:
            bands.extend(
                H1Gate.tail_bands(
                    spec, horizon=horizon, lower=sub.lower, upper=sub.upper, band_level=band_level
                )
            )
        return DgtSensitivity(
            band_level=band_level,
            bands=tuple(bands),
            passed=all(_contains(band) for band in bands),
        )
