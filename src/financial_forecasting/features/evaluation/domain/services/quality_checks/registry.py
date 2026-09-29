"""`QualityCheckRegistry`, o contrato `QualityCheck` e o `QualityCheckContext` (6.4).

Serviço de domínio stdlib-only (concept 6.4 §4, D4; ADR `6_4_0002` item 1): o registry
guarda os checks numa ordem fixa, roda cada um sobre o mesmo contexto e concatena os
resultados; `is_blocking` é verdadeiro se e só se algum resultado é `ERROR` + `FAIL`.

O contexto é o que os checks leem — a montagem (`AssembledCohort`), a
`PairedLossSeries` por horizonte (quando montada), as estimativas b̂_sb por horizonte
(`BlockEstimate`, definidas ou com motivo), a tolerância de degeneração, o
`DatasetFingerprint` e o `RealizedReturns` consumido. Nenhum check lê estado de outro.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from financial_forecasting.features.evaluation.domain.value_objects._tolerance import (
    validate_tolerance,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    AssembledCohort,
)
from financial_forecasting.features.evaluation.domain.value_objects.block_estimate import (
    BlockEstimate,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
    models_suffice,
)
from financial_forecasting.features.evaluation.domain.value_objects.quality_check_result import (
    CheckOutcome,
    CheckSeverity,
    QualityCheckResult,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)
from financial_forecasting.shared.domain.value_objects.dataset_fingerprint import (
    DatasetFingerprint,
)


@dataclass(frozen=True)
class QualityCheckContext:
    """Entradas comuns dos checks de um refresh.

    Campos:
        assembled: a montagem (relatório e, sem achado, amostras por horizonte).
        paired: horizonte → `PairedLossSeries` da amostra comum (só os montados).
        block_estimates: horizonte → uma `BlockEstimate` por par de
            `paired[h].model_pairs()`, na mesma ordem.
        tolerance: tolerância absoluta de degeneração (finita, ≥ 0).
        dataset_fingerprint: impressão do dataset lido para o realizado.
        realized: o realizado consumido.

    Raises:
        ValueError: contêiner não-`Mapping`, tolerância inválida, horizonte fora da
            montagem, horizonte com k ≥ `MIN_MODELS` sem série pareada ou sem
            estimativas (ou com elas quando k < `MIN_MODELS`), série de outro horizonte
            ou estimativas que não batem com os pares da série, na construção.
    """

    assembled: AssembledCohort
    paired: Mapping[int, PairedLossSeries]
    block_estimates: Mapping[int, tuple[BlockEstimate, ...]]
    tolerance: float
    dataset_fingerprint: DatasetFingerprint
    realized: RealizedReturns

    def __post_init__(self) -> None:
        """Contêineres imutáveis, tolerância e estimativas coerentes com os pares."""
        for name in ("paired", "block_estimates"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise ValueError(f"{name} must be a Mapping, got {type(value).__name__}")
            object.__setattr__(self, name, MappingProxyType(dict(value)))
        validate_tolerance(self.tolerance, field="tolerance")
        self._check_horizon_keys()
        for horizon, estimates in self.block_estimates.items():
            series = self.paired.get(horizon)
            pairs = () if series is None else series.model_pairs()
            got = tuple(estimate.pair for estimate in estimates)
            if got != pairs:
                raise ValueError(
                    f"block_estimates[{horizon}] must cover the pairs {pairs} of the paired "
                    f"series in order, got {got}"
                )

    def _check_horizon_keys(self) -> None:
        """Sem achado: horizonte com k ≥ `MIN_MODELS` ⇔ tem série pareada e estimativas.

        Sem esta regra, um horizonte montado ausente de `paired`/`block_estimates` daria
        PASS falso no `statistical_preconditions` (Checkpoint C bloco 2, M-A).
        """
        assembled_horizons = {samples.horizon for samples in self.assembled.horizons}
        for name in ("paired", "block_estimates"):
            outside = sorted(set(getattr(self, name)) - assembled_horizons)
            if outside:
                raise ValueError(
                    f"{name} has horizons {outside} outside the assembled horizons "
                    f"{sorted(assembled_horizons)}"
                )
        for samples in self.assembled.horizons:
            horizon = samples.horizon
            expected = models_suffice(samples.models)
            for name in ("paired", "block_estimates"):
                if (horizon in getattr(self, name)) != expected:
                    raise ValueError(
                        f"{name} must {'' if expected else 'not '}hold horizon {horizon} "
                        f"(k={len(samples.models)} model(s))"
                    )
            series = self.paired.get(horizon)
            if series is not None and series.horizon != horizon:
                raise ValueError(f"paired[{horizon}] is a series of horizon {series.horizon}")


class QualityCheck(Protocol):
    """Um check: nome e severidade declarados, e os resultados sobre o contexto."""

    @property
    def name(self) -> str:
        """Nome único no registry (coluna `check` da tabela)."""
        ...

    @property
    def severity(self) -> CheckSeverity:
        """Severidade declarada (ADR `6_4_0002`)."""
        ...

    def run(self, context: QualityCheckContext) -> tuple[QualityCheckResult, ...]:
        """Resultados do check (cada um com `check == name` e `severity == severity`)."""
        ...


class QualityCheckRegistry:
    """Checks numa ordem fixa; roda todos e diz se o conjunto bloqueia."""

    def __init__(self, checks: Sequence[QualityCheck]) -> None:
        """Guarda os checks na ordem dada.

        Raises:
            ValueError: nome de check repetido.
        """
        names = [check.name for check in checks]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise ValueError(f"quality check names must be unique, repeated: {repeated}")
        self._checks = tuple(checks)

    @property
    def names(self) -> tuple[str, ...]:
        """Nomes dos checks, na ordem registrada."""
        return tuple(check.name for check in self._checks)

    def run(self, context: QualityCheckContext) -> tuple[QualityCheckResult, ...]:
        """Roda os checks na ordem registrada e concatena os resultados.

        Raises:
            ValueError: um check devolve resultado com outro nome ou outra severidade.
        """
        results: list[QualityCheckResult] = []
        for check in self._checks:
            for result in check.run(context):
                if (result.check, result.severity) != (check.name, check.severity):
                    raise ValueError(
                        f"check {check.name!r} ({check.severity.value}) returned a result "
                        f"of {result.check!r} ({result.severity.value})"
                    )
                results.append(result)
        return tuple(results)

    @staticmethod
    def is_blocking(results: Sequence[QualityCheckResult]) -> bool:
        """`True` se e só se algum resultado é `ERROR` + `FAIL`."""
        return any(result.is_blocking for result in results)


def result_of(  # noqa: PLR0913 — os campos do resultado, keyword-only
    check: QualityCheck,
    outcome: CheckOutcome,
    kind: str,
    *,
    detail: str,
    horizon: int | None = None,
    model: str | None = None,
    seed: int | None = None,
    occurrences: int = 1,
    value: float | None = None,
) -> QualityCheckResult:
    """Resultado de `check` (nome e severidade do próprio check — uma escrita só)."""
    return QualityCheckResult(
        check=check.name,
        severity=check.severity,
        outcome=outcome,
        kind=kind,
        horizon=horizon,
        model=model,
        seed=seed,
        occurrences=occurrences,
        value=value,
        detail=detail,
    )
