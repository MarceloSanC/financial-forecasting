"""Fake do port `ConformalCalibration` — regras do fornecedor, correções zero (Stage 7.2).

Reusa as funções donas do use case `CalibrateConformal` (`validate_command` e
`calibration_set_for`, o padrão do `merge_run_entry` da 7.1): erros de comando e
motivos de `undefined`/`error` são exatamente os do real. Não calibra: em toda unidade
`ok`, as duas correções são **zero** e os limites são os quantis nativos do par
(`grid[tau_lo]`, `grid[tau_hi]`). O posto é o do real: `split_conformal_rank(n,
alpha)` na variante sem pesos, `None` no NexCP (paridade, TA-3). Não define nem
importa o calibrador (guarda AST em `tests/architecture/test_stage_7_2_regression_guards.py`).

Configuração: `force_status[(fold, seed, horizon)] = (status, reason)` força o status de
uma unidade; `raises` faz a chamada erguer (a exceção do port que o `RefreshGold`
propaga); `calls` registra os comandos recebidos.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from financial_forecasting.features.inference.application.use_cases.calibrate_conformal import (
    CalibrateConformalCommand,
    CalibrateConformalResult,
    ConformalUnitInput,
    ConformalUnitResult,
    UnitStatus,
    calibration_set_for,
    validate_command,
)
from financial_forecasting.features.inference.domain.services.conformal_calibrator import (
    ConformalVariant,
    TailCorrection,
    exact_level,
    split_conformal_rank,
)

_NEXCP = ConformalVariant.NEXCP.value


def _zero_tail(tail: str, level: float, n: int, variant: str) -> TailCorrection:
    alpha = exact_level(level) if tail == "lower" else 1 - exact_level(level)
    return TailCorrection(
        tail=tail,  # type: ignore[arg-type]
        level=level,
        alpha=alpha,
        n=n,
        rank=None if variant == _NEXCP else split_conformal_rank(n, alpha),
        correction=0.0,
        infinite=False,
    )


@dataclass
class FakeConformalCalibration:
    """Satisfaz `ConformalCalibration` com correções zero e as regras do fornecedor."""

    force_status: Mapping[tuple[int, int, int], tuple[str, str]] = field(default_factory=dict)
    raises: Exception | None = None
    calls: list[CalibrateConformalCommand] = field(default_factory=list)

    def __call__(self, command: CalibrateConformalCommand) -> CalibrateConformalResult:
        self.calls.append(command)
        if self.raises is not None:
            raise self.raises
        validate_command(command)
        rows: list[ConformalUnitResult] = []
        for unit in sorted(command.units, key=lambda u: (u.fold_index, u.seed, u.horizon)):
            for pair in command.pairs:
                for variant in command.variants:
                    rho = command.nexcp_rho if variant == _NEXCP else None
                    rows.append(self._row(unit, pair, variant, rho))
        return CalibrateConformalResult(units=tuple(rows))

    def _row(
        self,
        unit: ConformalUnitInput,
        pair: tuple[float, float],
        variant: str,
        rho: float | None,
    ) -> ConformalUnitResult:
        forced = self.force_status.get((unit.fold_index, unit.seed, unit.horizon))
        if forced is not None:
            return _not_ok(unit, pair, variant, rho, UnitStatus(forced[0]), forced[1])
        try:
            calib = calibration_set_for(unit, pair)
        except (ValueError, ArithmeticError) as exc:
            return _not_ok(unit, pair, variant, rho, UnitStatus.ERROR, str(exc))
        if isinstance(calib, str):
            return _not_ok(unit, pair, variant, rho, UnitStatus.UNDEFINED, calib)
        n = len(calib.points)
        return ConformalUnitResult(
            fold_index=unit.fold_index,
            seed=unit.seed,
            horizon=unit.horizon,
            lower_level=pair[0],
            upper_level=pair[1],
            variant=variant,
            rho=rho,
            status=UnitStatus.OK,
            reason=None,
            lower=_zero_tail("lower", pair[0], n, variant),
            upper=_zero_tail("upper", pair[1], n, variant),
            lower_beta=None,
            upper_beta=None,
            test_lower=tuple(point.grid[pair[0]] for point in unit.test),
            test_upper=tuple(point.grid[pair[1]] for point in unit.test),
        )


def _not_ok(  # noqa: PLR0913 — a chave da linha, o status e o motivo
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
