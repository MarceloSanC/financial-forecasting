"""Use case `CalibrateConformal` — calibração conformal por unidade, com status (concept 7.2 §4).

Puro: não lê nem grava nada e não chama port (o oráculo `ConformalBackend` nunca é
chamado por use case, I1). Recebe as unidades (fold, seed, horizonte) com o calib
dedicado e os pontos de teste já montados pelo consumidor, e devolve, por unidade,
par e variante, as duas correções de cauda, a referência Beta (só na variante sem
pesos) e os limites conformais alinhados aos pontos de teste (ADR 7.2.0003 item 2).

Status por unidade (I7):

- `undefined`: entrada incompleta — ponto de calib sem `realized`, grade sem um
  nível do par ou unidade sem ponto de teste (`test_start` não existe);
- `error`: `ValueError`/`ArithmeticError` do `CalibrationSet` ou do calibrador
  nesta unidade, com a mensagem em `reason`; as outras unidades seguem intactas;
- só erro de COMANDO ergue, antes de qualquer unidade (C3): unidade duplicada,
  variante desconhecida, rho inválido ou ausente para NEXCP, par não simétrico ou
  tau_lo fora de (0; 0,5).

Ordem do resultado (technical §1): unidades por (fold, seed, horizonte) crescentes;
dentro da unidade, pares e variantes na ordem do comando. `test_start` é a decisão do
primeiro ponto de teste; os q usados são `grid[tau_lo]` e `grid[tau_hi]` (o
`value_guardrail`, I2).

`validate_command` e `calibration_set_for` são as funções donas, usadas também pelo
`FakeConformalCalibration` do evaluation (o padrão do `merge_run_entry` da 7.1).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from financial_forecasting.features.inference.domain.services.conformal_calibrator import (
    BetaReference,
    ConformalCalibrator,
    ConformalVariant,
    PairCorrection,
    TailCorrection,
    beta_reference,
    exact_rho,
)
from financial_forecasting.features.inference.domain.value_objects.calibration_set import (
    CalibrationPoint,
    CalibrationSet,
    check_symmetric_pair,
)


@dataclass(frozen=True)
class ConformalPointInput:
    """Um ponto do calib ou do teste: a grade guardada e, no calib, o realizado."""

    decision_timestamp: str
    target_timestamp: str
    grid: Mapping[float, float]  # nível → value_guardrail
    realized: float | None  # obrigatório no calib, None no teste


@dataclass(frozen=True)
class ConformalUnitInput:
    """Uma unidade (fold, seed, horizonte) com o calib dedicado e os pontos de teste."""

    fold_index: int
    seed: int
    horizon: int
    calib: tuple[ConformalPointInput, ...]
    test: tuple[ConformalPointInput, ...]


@dataclass(frozen=True)
class CalibrateConformalCommand:
    """DTO de entrada — unidades, pares simétricos, variantes e o rho do NexCP."""

    units: tuple[ConformalUnitInput, ...]
    pairs: tuple[tuple[float, float], ...]
    variants: tuple[str, ...]  # valores de ConformalVariant
    nexcp_rho: float | None  # None só sem NEXCP em `variants`


class UnitStatus(StrEnum):
    """Status de uma (unidade, par, variante)."""

    OK = "ok"
    UNDEFINED = "undefined"
    ERROR = "error"


@dataclass(frozen=True)
class ConformalUnitResult:
    """Correções, Beta e limites de teste de uma (unidade, par, variante)."""

    fold_index: int
    seed: int
    horizon: int
    lower_level: float
    upper_level: float
    variant: str
    rho: float | None
    status: UnitStatus
    reason: str | None  # obrigatório quando status ≠ OK
    lower: TailCorrection | None  # None quando status ≠ OK
    upper: TailCorrection | None
    lower_beta: BetaReference | None  # None para NEXCP, para status ≠ OK e para l = 0
    upper_beta: BetaReference | None
    test_lower: tuple[float, ...] | None  # alinhados a `test`; None quando status ≠ OK
    test_upper: tuple[float, ...] | None


@dataclass(frozen=True)
class CalibrateConformalResult:
    """DTO de saída — ordem: fold, seed, horizonte, par, variante."""

    units: tuple[ConformalUnitResult, ...]


def _check_pair(pair: tuple[float, float]) -> None:
    try:
        check_symmetric_pair(pair[0], pair[1])
    except ValueError as exc:
        raise ValueError(f"pairs: {exc}") from None


def _check_rho(rho: float | None, *, required: bool) -> None:
    if rho is None:
        if required:
            raise ValueError(f"nexcp_rho: required for the {ConformalVariant.NEXCP.value} variant")
        return
    try:
        exact_rho(rho)
    except ValueError as exc:
        raise ValueError(f"nexcp_rho: {exc}") from None


def validate_command(command: CalibrateConformalCommand) -> None:
    """Erros de comando (C3), antes de qualquer unidade: ergue `ValueError`."""
    seen: set[tuple[int, int, int]] = set()
    for unit in command.units:
        key = (unit.fold_index, unit.seed, unit.horizon)
        if key in seen:
            raise ValueError(f"units: duplicate unit (fold, seed, horizon) = {key}")
        seen.add(key)
    known = {variant.value for variant in ConformalVariant}
    unknown = [variant for variant in command.variants if variant not in known]
    if unknown:
        raise ValueError(f"variants: unknown conformal variants {unknown}")
    _check_rho(command.nexcp_rho, required=ConformalVariant.NEXCP.value in command.variants)
    for pair in command.pairs:
        _check_pair(pair)


def _missing_level(point: ConformalPointInput, pair: tuple[float, float]) -> float | None:
    return next((level for level in pair if level not in point.grid), None)


def calibration_set_for(
    unit: ConformalUnitInput, pair: tuple[float, float]
) -> CalibrationSet | str:
    """O `CalibrationSet` do par, ou o motivo de `undefined` (entrada incompleta).

    `ValueError`/`ArithmeticError` do VO propagam: o chamador os captura como `error`.
    """
    if not unit.test:
        return "unit has no test point (test_start does not exist)"
    for name, points in (("calib", unit.calib), ("test", unit.test)):
        for point in points:
            level = _missing_level(point, pair)
            if level is not None:
                return f"{name} point {point.decision_timestamp} grid lacks level {level!r}"
    calib_points: list[CalibrationPoint] = []
    for point in unit.calib:
        if point.realized is None:
            return f"calib point {point.decision_timestamp} has no realized value"
        calib_points.append(
            CalibrationPoint(
                decision_timestamp=point.decision_timestamp,
                target_timestamp=point.target_timestamp,
                lower=point.grid[pair[0]],
                upper=point.grid[pair[1]],
                realized=point.realized,
            )
        )
    return CalibrationSet(
        fold_index=unit.fold_index,
        seed=unit.seed,
        horizon=unit.horizon,
        lower_level=pair[0],
        upper_level=pair[1],
        points=tuple(calib_points),
        test_start=unit.test[0].decision_timestamp,
    )


def _not_ok(  # noqa: PLR0913 — a chave da unidade, o status e o motivo
    unit: ConformalUnitInput,
    pair: tuple[float, float],
    variant: str,
    rho: float | None,
    status: UnitStatus,
    reason: str,
) -> ConformalUnitResult:
    return ConformalUnitResult(
        fold_index=unit.fold_index,
        seed=unit.seed,
        horizon=unit.horizon,
        lower_level=pair[0],
        upper_level=pair[1],
        variant=variant,
        rho=rho,
        status=status,
        reason=reason,
        lower=None,
        upper=None,
        lower_beta=None,
        upper_beta=None,
        test_lower=None,
        test_upper=None,
    )


def _ok(
    unit: ConformalUnitInput,
    pair: tuple[float, float],
    variant: ConformalVariant,
    correction: PairCorrection,
) -> ConformalUnitResult:
    limits = [
        correction.limits(lower=point.grid[pair[0]], upper=point.grid[pair[1]])
        for point in unit.test
    ]
    split = variant is ConformalVariant.SPLIT_CQR
    return ConformalUnitResult(
        fold_index=unit.fold_index,
        seed=unit.seed,
        horizon=unit.horizon,
        lower_level=pair[0],
        upper_level=pair[1],
        variant=variant.value,
        rho=correction.rho,
        status=UnitStatus.OK,
        reason=None,
        lower=correction.lower,
        upper=correction.upper,
        lower_beta=beta_reference(correction.lower.n, correction.lower.alpha) if split else None,
        upper_beta=beta_reference(correction.upper.n, correction.upper.alpha) if split else None,
        test_lower=tuple(low for low, _ in limits),
        test_upper=tuple(high for _, high in limits),
    )


class CalibrateConformal:
    """Calibra cada (unidade, par, variante) do comando; status por unidade."""

    def __call__(self, command: CalibrateConformalCommand) -> CalibrateConformalResult:
        validate_command(command)
        results: list[ConformalUnitResult] = []
        for unit in sorted(command.units, key=lambda u: (u.fold_index, u.seed, u.horizon)):
            for pair in command.pairs:
                results.extend(self._pair(command, unit, pair))
        return CalibrateConformalResult(units=tuple(results))

    @staticmethod
    def _pair(
        command: CalibrateConformalCommand,
        unit: ConformalUnitInput,
        pair: tuple[float, float],
    ) -> list[ConformalUnitResult]:
        variants = [ConformalVariant(value) for value in command.variants]

        def rho_of(variant: ConformalVariant) -> float | None:
            return command.nexcp_rho if variant is ConformalVariant.NEXCP else None

        try:
            calib = calibration_set_for(unit, pair)
        except (ValueError, ArithmeticError) as exc:
            return [
                _not_ok(unit, pair, v.value, rho_of(v), UnitStatus.ERROR, str(exc))
                for v in variants
            ]
        if isinstance(calib, str):
            return [
                _not_ok(unit, pair, v.value, rho_of(v), UnitStatus.UNDEFINED, calib)
                for v in variants
            ]
        results: list[ConformalUnitResult] = []
        for variant in variants:
            try:
                correction = ConformalCalibrator.calibrate(
                    calib, variant=variant, rho=rho_of(variant)
                )
            except (ValueError, ArithmeticError) as exc:
                results.append(
                    _not_ok(unit, pair, variant.value, rho_of(variant), UnitStatus.ERROR, str(exc))
                )
                continue
            results.append(_ok(unit, pair, variant, correction))
        return results
