"""DTOs da corrida confirmatória e os erros das guardas (Stage 8.1).

DTOs de aplicação **frozen** do `RunConfirmatoryEvaluation` (concept 8.1 §4, D3, D12;
ADRs `8_1_0001` itens 3-4 e `8_1_0004` item 2):

- `ConfirmatoryRunStatus` — `JUDGED` | `BLOCKED` | `ALREADY_JUDGED`; falha é exceção,
  nunca status (D3). `sealed_status(refresh_status)` é o status que uma cópia selada
  carrega (`COMPLETED` → `JUDGED`, `BLOCKED` → `BLOCKED`): o corpo de atestação do
  `ALREADY_JUDGED` é o mesmo do `JUDGED`/`BLOCKED` que selou a cópia (A5, A15);
- `InferenceSummary` — o resumo do `infer` que a CLI acabou de rodar, como dado (sem
  tipo do `inference`, D1): `runs`, quantos `strict` e `tolerance`, o maior |Δ|, as
  linhas `calib` escritas e verificadas. `from_mapping` exige as chaves exatas;
- `RunConfirmatoryEvaluationCommand` / `RunConfirmatoryEvaluationResult` (concept §4);
- `DEVIATION_TAG` e `check_deviation` — o `--deviation` tem de citar um `[deviation]`
  (ADR 8.1.0004 item 2e);
- os erros das guardas e das conferências pós-E1 (`ApplicationError`);
- `run_record_document` — o `run_record.json` da cópia julgada (D6; ADR 8.1.0003 item 6,
  decisão 8.1-J3), dono único das chaves que o corpo de atestação lê (`RUN_RECORD_*`).

Nenhum número é calculado aqui (I1): o resumo do `infer` só é conferido na forma.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from enum import StrEnum
from typing import Final

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    ScorecardResult,
    to_jsonable,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    GENERATION_MANIFEST,
    JudgedAttempt,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    FailedCheck,
    GoldPartition,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._integer import (
    validate_int_at_least,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex

DEVIATION_TAG: Final = "[deviation]"
"""O marcador que todo `--deviation` cita (a entrada `[deviation]` do technical §7)."""


class ConfirmatoryRunStatus(StrEnum):
    """Desfecho de uma corrida confirmatória (D3)."""

    JUDGED = "JUDGED"
    BLOCKED = "BLOCKED"
    ALREADY_JUDGED = "ALREADY_JUDGED"


def sealed_status(refresh_status: RefreshStatus) -> ConfirmatoryRunStatus:
    """O status com que uma cópia foi selada, pelo status do seu refresh."""
    if refresh_status is RefreshStatus.COMPLETED:
        return ConfirmatoryRunStatus.JUDGED
    return ConfirmatoryRunStatus.BLOCKED


# --- erros ------------------------------------------------------------------------------


class DirtyCodeError(ApplicationError):
    """Código ou `config/preregistration/` com mudança não commitada (G2)."""


class InvalidDeviationError(ApplicationError):
    """O `--deviation` não cita um `[deviation]` (G4, ADR 8.1.0004 item 2e)."""


class PriorAttemptCodeChangedError(ApplicationError):
    """Tentativa sem selo desta revisão com outro `code.*`, sem `--deviation` (G4, I13)."""


class PriorAttemptEnvironmentChangedError(ApplicationError):
    """Tentativa sem selo desta revisão com outro ambiente `env.*`, sem `--deviation`."""


class PriorAttemptInputChangedError(ApplicationError):
    """A entrada lida pelo E1 ≠ a da tentativa anterior, sem `--deviation` (2b-i)."""


class PriorAttemptDivergenceError(ApplicationError):
    """Geração nova ≠ geração viva anterior com código, ambiente e entrada iguais (2b-ii).

    Falha do R-BIT (doc de domínio §4.2): parada para diagnóstico, nada selado.
    """


def check_deviation(deviation: str | None) -> None:
    """O `--deviation`, quando vem, cita um `[deviation]`.

    Raises:
        InvalidDeviationError: texto sem `DEVIATION_TAG`.
    """
    if deviation is not None and DEVIATION_TAG not in deviation:
        raise InvalidDeviationError(
            f"--deviation must cite a {DEVIATION_TAG} entry of the technical §7, got {deviation!r}"
        )


# --- resumo do infer --------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class InferenceSummary:
    """O resumo do `infer` que precede a corrida (D1; concept §4).

    Campos: `runs` (runs inferidos), `strict` e `tolerance` (quantos em cada modo de
    reprodução; somam `runs`), `max_abs_diff` (maior |Δ| entre os runs, finito ≥ 0),
    `calib_rows_written` e `calib_rows_verified`.

    Raises:
        ValueError: contagem não-`int` ou negativa, modos que não somam `runs` ou
            `max_abs_diff` não finito ou negativo.
    """

    runs: int
    strict: int
    tolerance: int
    max_abs_diff: float
    calib_rows_written: int
    calib_rows_verified: int

    def __post_init__(self) -> None:
        for name in ("runs", "strict", "tolerance", "calib_rows_written", "calib_rows_verified"):
            validate_int_at_least(getattr(self, name), minimum=0, field=f"inference {name}")
        if self.strict + self.tolerance != self.runs:
            raise ValueError(
                f"inference strict ({self.strict}) + tolerance ({self.tolerance}) "
                f"must equal runs ({self.runs})"
            )
        if not is_finite_number(self.max_abs_diff) or self.max_abs_diff < 0:
            raise ValueError(
                f"inference max_abs_diff must be a finite number >= 0, got {self.max_abs_diff!r}"
            )

    def as_mapping(self) -> dict[str, object]:
        """A forma JSON-safe (as mesmas chaves de `from_mapping`)."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> InferenceSummary:
        """O resumo devolvido pelo `infer_with_summary` (chaves exatas).

        Raises:
            ValueError: não-`Mapping`, chave a mais ou a menos, ou campo inválido.
        """
        if not isinstance(mapping, Mapping):
            raise ValueError(f"inference summary must be a Mapping, got {type(mapping).__name__}")
        expected = {f.name for f in fields(cls)}
        if set(mapping) != expected:
            raise ValueError(
                f"inference summary must have exactly the keys {sorted(expected)}, "
                f"got {sorted(str(key) for key in mapping)}"
            )
        return cls(**{name: mapping[name] for name in expected})  # type: ignore[arg-type]


# --- comando e resultado ----------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class RunConfirmatoryEvaluationCommand:
    """O pedido da corrida: a revisão julgada, a referência esperada e o contexto da CLI.

    Campos: `name` e `revision` do plano, `preregistration_ref` esperado (G1),
    `break_stale_lock` (decisão explícita do operador, G3), `deviation` (texto com
    `[deviation]` ou `None`; o marcador é conferido no G4) e `inference_summary`.

    Raises:
        ValueError: `name`/`preregistration_ref` vazios, `revision` não-`int` ou negativa,
            `break_stale_lock` não-`bool`, `deviation` nem `None` nem texto não vazio, ou
            `inference_summary` de outro tipo.
    """

    name: str
    revision: int
    preregistration_ref: str
    inference_summary: InferenceSummary
    break_stale_lock: bool = False
    deviation: str | None = None

    def __post_init__(self) -> None:
        for name in ("name", "preregistration_ref"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty str, got {value!r}")
        validate_int_at_least(self.revision, minimum=0, field="revision")
        if not isinstance(self.break_stale_lock, bool):
            raise ValueError(f"break_stale_lock must be a bool, got {self.break_stale_lock!r}")
        if self.deviation is not None and (
            not isinstance(self.deviation, str) or not self.deviation
        ):
            raise ValueError(f"deviation must be a non-empty str or None, got {self.deviation!r}")
        if not isinstance(self.inference_summary, InferenceSummary):
            raise ValueError(
                f"inference_summary must be an InferenceSummary, got {self.inference_summary!r}"
            )


@dataclass(frozen=True, kw_only=True)
class RunConfirmatoryEvaluationResult:
    """O desfecho da corrida (concept §4).

    Campos: `status`, `preregistration_ref`, `partition`, `generation_digest` (sha256 hex
    da cópia selada), `refresh_status` (o da cópia), `scorecard` (o `ScorecardResult`
    desta execução quando `JUDGED`; `None` com `BLOCKED` e com `ALREADY_JUDGED`, cujo
    scorecard é o JSON da cópia), `failed_checks` (os checks que bloquearam, quando
    `BLOCKED` nesta execução) e `attestation_body` (o texto do comentário, D7).

    Raises:
        ValueError: campo de tipo errado ou incoerente com o status.
    """

    status: ConfirmatoryRunStatus
    preregistration_ref: str
    partition: GoldPartition
    generation_digest: str
    refresh_status: RefreshStatus
    scorecard: ScorecardResult | None
    failed_checks: tuple[FailedCheck, ...]
    attestation_body: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, ConfirmatoryRunStatus):
            raise ValueError(f"status must be a ConfirmatoryRunStatus, got {self.status!r}")
        if not isinstance(self.refresh_status, RefreshStatus):
            raise ValueError(f"refresh_status must be a RefreshStatus, got {self.refresh_status!r}")
        if not isinstance(self.partition, GoldPartition):
            raise ValueError(f"partition must be a GoldPartition, got {self.partition!r}")
        validate_sha256_hex(self.generation_digest, field="generation_digest")
        for name in ("preregistration_ref", "attestation_body"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty str, got {value!r}")
        if self.status is not ConfirmatoryRunStatus.ALREADY_JUDGED and (
            sealed_status(self.refresh_status) is not self.status
        ):
            raise ValueError(
                f"status {self.status.value} does not match refresh {self.refresh_status.value}"
            )
        if (self.scorecard is not None) != (self.status is ConfirmatoryRunStatus.JUDGED):
            raise ValueError("a scorecard comes with JUDGED and only with JUDGED")
        if not isinstance(self.failed_checks, tuple):
            raise ValueError(f"failed_checks must be a tuple, got {self.failed_checks!r}")


# --- registro de execução ---------------------------------------------------------------

RUN_RECORD_REF: Final = "preregistration_ref"
RUN_RECORD_PARTITION: Final = "partition"
RUN_RECORD_ENVIRONMENT: Final = "environment"
RUN_RECORD_INFERENCE: Final = "inference_summary"
RUN_RECORD_DEVIATION: Final = "deviation"
RUN_RECORD_ATTEMPTS: Final = "attempts"
RUN_RECORD_REFRESH: Final = "refresh"
RUN_RECORD_FAILED_CHECKS: Final = "failed_checks"
RUN_RECORD_SEEDS: Final = "seeds"
SEEDS_REFERENCE: Final[Mapping[str, str]] = {
    "gold": f"{GENERATION_MANIFEST} parameters (MCS, Monte Carlo, H3)",
    "training": "cohort spec (code.cohort_file)",
}
"""As seeds por referência: já estão no manifesto e no spec do cohort (D6), sem cópia."""


def run_record_document(  # noqa: PLR0913 — as partes do registro (D6), uma por argumento
    *,
    preregistration_ref: str,
    partition: GoldPartition,
    environment: Mapping[str, str],
    inference_summary: InferenceSummary,
    deviation: str | None,
    attempts: Sequence[JudgedAttempt],
    refresh_status: RefreshStatus,
    rows_by_table: Mapping[str, int],
    profile_error_units: int,
    conformal_error_units: int,
    failed_checks: Sequence[FailedCheck],
) -> dict[str, object]:
    """O `run_record.json` (D6): foto do ambiente, resumo do `infer`, tentativas e refresh.

    `environment` é a foto do `EvaluationEnvironment` inteira (com `commit`, as chaves
    `code.*` e `env.*`); `attempts` são **todas** as linhas do log da partição (I13);
    `failed_checks` vem vazio com `COMPLETED`. Nenhum valor é calculado aqui.
    """
    return {
        RUN_RECORD_REF: preregistration_ref,
        RUN_RECORD_PARTITION: {
            "asset": partition.asset,
            "parent_sweep_id": partition.parent_sweep_id,
        },
        RUN_RECORD_ENVIRONMENT: {key: environment[key] for key in sorted(environment)},
        RUN_RECORD_INFERENCE: inference_summary.as_mapping(),
        RUN_RECORD_DEVIATION: deviation,
        RUN_RECORD_ATTEMPTS: [attempt.as_mapping() for attempt in attempts],
        RUN_RECORD_REFRESH: {
            "status": refresh_status.value,
            "rows_by_table": {table: rows_by_table[table] for table in sorted(rows_by_table)},
            "profile_error_units": profile_error_units,
            "conformal_error_units": conformal_error_units,
        },
        RUN_RECORD_FAILED_CHECKS: [to_jsonable(check) for check in failed_checks],
        RUN_RECORD_SEEDS: dict(SEEDS_REFERENCE),
    }
