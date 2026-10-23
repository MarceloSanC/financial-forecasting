"""Use case `AuditReproduction` — a geração reproduzida contra a cópia julgada (Stage 8.2).

Só leitura, por ports (technical 8.2 §1 "Use case `AuditReproduction`"; ADR `8_2_0002`
item 4). Passos, nesta ordem:

1. resolve a revisão julgada (`resolve_judged_revision`: cadeia, hash, âncora) e a partição
   pelo plano (`refresh_command_from(plan, ref).partition`) — nunca de um argumento;
2. exige o registro `.judged.toml` commitado da referência (ausente →
   `ReproductionAuditError`) com o `generation_digest` igual ao da cópia selada conferida
   pelo `find` (diferente → `JudgedGenerationTamperedError`; sem cópia →
   `JudgedGenerationNotFoundError`);
3. lê a cópia como geração (`read_judged_generation`) e o scorecard da cópia (ausente →
   `ReproductionAuditError`);
4. o `expected_result_digest` = `result_digest` da **última** linha `input_read` da
   referência no `ATTEMPTS.jsonl` da raiz julgada (nenhuma → `ReproductionAuditError`);
5. a geração reproduzida pelo `GoldGenerationReader` da raiz reproduzida (erros propagam);
6. `compare_reproduction`.

Nenhuma escrita: não chama `preserve`, `record_attempt` nem `publish`.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    SCORECARD_DOCUMENT,
    AttemptPhase,
    JudgedGeneration,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
)
from financial_forecasting.features.evaluation.application.dtos.reproduction_comparison import (
    AuditReproductionCommand,
    ReproductionComparison,
)
from financial_forecasting.features.evaluation.application.ports.out.gold_generation_reader import (
    GoldGenerationReader,
)
from financial_forecasting.features.evaluation.application.ports.out.judged_generation_store import (  # noqa: E501
    JudgedGenerationNotFoundError,
    JudgedGenerationStore,
    JudgedGenerationTamperedError,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    PreregistrationSource,
)
from financial_forecasting.features.evaluation.application.use_cases.judged_revision import (
    resolve_judged_revision,
)
from financial_forecasting.features.evaluation.application.use_cases.reproduction_comparison import (  # noqa: E501
    compare_reproduction,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.application.ports.out.hasher import Hasher


class ReproductionAuditError(ApplicationError):
    """Falta um insumo da auditoria: registro commitado, scorecard da cópia ou `input_read`."""


class EqualReproductionRootsError(ApplicationError):
    """A raiz julgada e a reproduzida são a mesma (concept 8.2 I2): recusa antes de ler."""


class AuditReproduction:
    """Compara a geração reproduzida com a cópia julgada da revisão (só leitura)."""

    def __init__(
        self,
        *,
        source: PreregistrationSource,
        hasher: Hasher,
        judged_store: JudgedGenerationStore,
        reproduced_reader: GoldGenerationReader,
    ) -> None:
        """`judged_store` lê a raiz julgada; `reproduced_reader`, a raiz reproduzida."""
        self._source = source
        self._hasher = hasher
        self._judged_store = judged_store
        self._reproduced_reader = reproduced_reader

    def __call__(self, command: AuditReproductionCommand) -> ReproductionComparison:
        """A comparação por classe da reprodução contra a cópia julgada.

        Raises:
            PreregistrationNotFoundError / PreregistrationChainError /
                PreregistrationHashMismatchError / PreregistrationNotAnchoredError: a
                revisão não se resolve.
            ReproductionAuditError: sem registro commitado da referência, sem scorecard na
                cópia ou sem linha `input_read` da referência.
            JudgedGenerationNotFoundError: sem cópia selada da referência.
            JudgedGenerationTamperedError: cópia adulterada ou digest ≠ o do registro.
            GoldManifestNotFoundError / GoldGenerationCorruptError: a raiz reproduzida não
                tem geração legível da partição.
            ValueError: coluna gravada sem classe declarada (`compare_reproduction`).
        """
        ref = command.preregistration_ref
        resolved = resolve_judged_revision(
            source=self._source,
            hasher=self._hasher,
            name=command.name,
            revision=command.revision,
            preregistration_ref=ref,
        )
        partition = refresh_command_from(resolved.plan, ref).partition
        sealed = self._sealed_matching_record(command, partition)
        judged = self._judged_store.read_judged_generation(
            partition=partition, preregistration_ref=ref
        )
        judged_scorecard = sealed.documents.get(SCORECARD_DOCUMENT)
        if judged_scorecard is None:
            raise ReproductionAuditError(f"the judged copy of {ref} has no {SCORECARD_DOCUMENT}")
        expected = self._expected_result_digest(partition, ref)
        reproduced = self._reproduced_reader.read_generation(partition=partition)
        return compare_reproduction(
            judged=judged,
            judged_scorecard=judged_scorecard,
            reproduced=reproduced,
            reproduced_scorecard=command.reproduced_scorecard,
            expected_result_digest=expected,
        )

    def _sealed_matching_record(
        self, command: AuditReproductionCommand, partition: GoldPartition
    ) -> JudgedGeneration:
        """A cópia selada, cujo digest o `.judged.toml` da referência nomeia."""
        ref = command.preregistration_ref
        records = [
            record
            for record in self._source.judged_records(name=command.name)
            if record.preregistration_ref == ref
        ]
        if not records:
            raise ReproductionAuditError(f"no committed judged record of {ref}")
        sealed = self._judged_store.find(partition=partition, preregistration_ref=ref)
        if sealed is None:
            raise JudgedGenerationNotFoundError(f"no judged copy of {ref} for {partition}")
        for record in records:
            if record.generation_digest != sealed.generation_digest:
                raise JudgedGenerationTamperedError(
                    f"the committed record of {ref} names digest {record.generation_digest}, "
                    f"the sealed copy has {sealed.generation_digest}"
                )
        return sealed

    def _expected_result_digest(self, partition: GoldPartition, ref: str) -> str:
        """O `result_digest` da última linha `input_read` da referência."""
        digests = [
            attempt.result_digest
            for attempt in self._judged_store.attempts(partition=partition)
            if attempt.phase is AttemptPhase.INPUT_READ
            and attempt.preregistration_ref == ref
            and attempt.result_digest is not None
        ]
        if not digests:
            raise ReproductionAuditError(f"no input_read attempt line of {ref}")
        return digests[-1]
