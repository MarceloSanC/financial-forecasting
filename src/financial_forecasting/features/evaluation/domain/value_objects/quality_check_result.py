"""VO `QualityCheckResult` e os enums de severidade e desfecho dos quality checks (6.4).

Value object de domínio **frozen, stdlib-only** (concept 6.4 §4, D4; ADR `6_4_0002`
item 2). Uma linha de `gold_quality_checks`: o check (`check`), a severidade declarada
(`severity`), o desfecho (`outcome`), o tipo do achado ou a grandeza medida (`kind`), o
escopo (`horizon`/`model`/`seed`, cada um opcional), o número de ocorrências
agregadas no escopo (`occurrences` ≥ 1), um valor opcional (`value`, finito) e o
detalhe da primeira ocorrência (`detail`).

Coerência severidade x desfecho (ADR `6_4_0002` itens 1, 5, 6): `ERROR` bloqueia e só
sai `PASS`/`FAIL`/`SKIPPED`; `WARN` nunca bloqueia e só sai `REPORTED`/`SKIPPED`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    validate_horizon,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    check_non_empty_str,
    check_optional_seed,
)


class CheckSeverity(StrEnum):
    """Severidade declarada de um check (ADR `6_4_0002`, fork C2a)."""

    ERROR = "error"  # bloqueia o refresh quando FAIL
    WARN = "warn"  # só reporta


class CheckOutcome(StrEnum):
    """Desfecho de um resultado de check."""

    PASS = "pass"
    FAIL = "fail"
    REPORTED = "reported"
    SKIPPED = "skipped"


_ALLOWED: dict[CheckSeverity, frozenset[CheckOutcome]] = {
    CheckSeverity.ERROR: frozenset({CheckOutcome.PASS, CheckOutcome.FAIL, CheckOutcome.SKIPPED}),
    CheckSeverity.WARN: frozenset({CheckOutcome.REPORTED, CheckOutcome.SKIPPED}),
}


@dataclass(frozen=True)
class QualityCheckResult:
    """Um resultado agregado de check, no grão (check, kind, horizon, model, seed).

    Raises:
        ValueError: campo fora da forma, `occurrences < 1`, `value` não-finito ou
            desfecho incompatível com a severidade, na construção.
    """

    check: str
    severity: CheckSeverity
    outcome: CheckOutcome
    kind: str
    horizon: int | None
    model: str | None
    seed: int | None
    occurrences: int
    value: float | None
    detail: str

    def __post_init__(self) -> None:
        """Forma de cada campo e coerência severidade x desfecho."""
        for field in ("check", "kind", "detail"):
            check_non_empty_str(getattr(self, field), field=field)
        if not isinstance(self.severity, CheckSeverity):
            raise ValueError(f"severity must be a CheckSeverity, got {self.severity!r}")
        if not isinstance(self.outcome, CheckOutcome):
            raise ValueError(f"outcome must be a CheckOutcome, got {self.outcome!r}")
        if self.outcome not in _ALLOWED[self.severity]:
            raise ValueError(
                f"outcome {self.outcome.value!r} is not allowed for severity "
                f"{self.severity.value!r}"
            )
        if self.horizon is not None:
            validate_horizon(self.horizon, field="horizon")
        if self.model is not None:
            check_non_empty_str(self.model, field="model")
        check_optional_seed(self.seed)
        occurrences = self.occurrences
        if isinstance(occurrences, bool) or not isinstance(occurrences, int) or occurrences < 1:
            raise ValueError(f"occurrences must be an int >= 1, got {occurrences!r}")
        if self.value is not None and not is_finite_number(self.value):
            raise ValueError(f"value must be a finite number or None, got {self.value!r}")

    @property
    def is_blocking(self) -> bool:
        """`ERROR` + `FAIL` — o único par que bloqueia o refresh."""
        return self.severity is CheckSeverity.ERROR and self.outcome is CheckOutcome.FAIL
