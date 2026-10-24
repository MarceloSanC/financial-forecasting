"""Conferência "registro commitado ↔ cópia selada" e o `result_digest` (Stage 8.3).

Dono único (technical 8.3 §1 "Arquivos", CB-5) de duas regras que até a 8.2 eram privadas
do `AuditReproduction`; o `AuditReproduction` e o `GenerateReportArtifacts` chamam daqui,
cada um erguendo o **seu** erro quando a resposta é `None` (o `ReproductionAuditError` mora
no módulo que importa este — erguê-lo aqui seria import circular):

- `committed_records` — os `.judged.toml` commitados de uma referência;
- `sealed_matching_record` — a cópia selada cujo digest os registros nomeiam (`None` sem
  registro commitado; sem cópia → `JudgedGenerationNotFoundError`; digest diferente →
  `JudgedGenerationTamperedError`, erros do port);
- `last_input_read_digest` — o `result_digest` da **última** linha `input_read` da
  referência (`None` sem nenhuma).
"""

from __future__ import annotations

from collections.abc import Sequence

from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    AttemptPhase,
    JudgedAttempt,
    JudgedGeneration,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
)
from financial_forecasting.features.evaluation.application.ports.out.judged_generation_store import (  # noqa: E501
    JudgedGenerationNotFoundError,
    JudgedGenerationStore,
    JudgedGenerationTamperedError,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    JudgedRecord,
    PreregistrationSource,
)


def committed_records(
    source: PreregistrationSource, *, name: str, preregistration_ref: str
) -> tuple[JudgedRecord, ...]:
    """Os registros `.judged.toml` commitados da referência, na ordem do source."""
    return tuple(
        record
        for record in source.judged_records(name=name)
        if record.preregistration_ref == preregistration_ref
    )


def sealed_matching_record(
    *,
    source: PreregistrationSource,
    judged_store: JudgedGenerationStore,
    name: str,
    preregistration_ref: str,
    partition: GoldPartition,
) -> JudgedGeneration | None:
    """A cópia selada cujo digest o `.judged.toml` da referência nomeia.

    Returns:
        `None` sem registro commitado da referência (o chamador ergue o seu erro).

    Raises:
        JudgedGenerationNotFoundError: há registro e não há cópia selada.
        JudgedGenerationTamperedError: cópia adulterada (pelo `find`) ou digest ≠ o do
            registro.
    """
    records = committed_records(source, name=name, preregistration_ref=preregistration_ref)
    if not records:
        return None
    sealed = judged_store.find(partition=partition, preregistration_ref=preregistration_ref)
    if sealed is None:
        raise JudgedGenerationNotFoundError(
            f"no judged copy of {preregistration_ref} for {partition}"
        )
    for record in records:
        if record.generation_digest != sealed.generation_digest:
            raise JudgedGenerationTamperedError(
                f"the committed record of {preregistration_ref} names digest "
                f"{record.generation_digest}, the sealed copy has {sealed.generation_digest}"
            )
    return sealed


def last_input_read_digest(attempts: Sequence[JudgedAttempt], ref: str) -> str | None:
    """O `result_digest` da última linha `input_read` da referência (`None` sem nenhuma)."""
    digests = [
        attempt.result_digest
        for attempt in attempts
        if attempt.phase is AttemptPhase.INPUT_READ
        and attempt.preregistration_ref == ref
        and attempt.result_digest is not None
    ]
    return digests[-1] if digests else None
