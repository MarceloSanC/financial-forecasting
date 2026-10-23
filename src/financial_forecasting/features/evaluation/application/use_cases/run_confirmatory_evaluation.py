"""Use case `RunConfirmatoryEvaluation` — a corrida confirmatória com guardas e replay (8.1).

Orquestrador do slice `evaluation` (concept 8.1 §4, I1-I5, I8, I13, I14, D2, D3, D8,
D12; ADRs `8_1_0001` itens 3-5, `8_1_0003` item 6 e `8_1_0004` itens 1-2b). Sequencia o
`RefreshGold` e o `BuildConfirmatoryScorecard` (pelos Protocols locais `GoldRefresh` e
`ScorecardBuilder`, satisfeitos por duck typing — mesmo slice, fora de `ports/out/`),
confere igualdades de identidade e grava; **não calcula nenhum número** (I1). Ordem:

- **G1** `resolve_judged_revision` — cadeia, hash = `command.preregistration_ref`,
  âncora de toda revisão (erros da 6.5);
- **G2** foto do `EvaluationEnvironment` — `code_dirty` e `preregistration_dirty` têm de
  ser `"false"` (`DirtyCodeError`; sem id da imagem, `MissingImageIdError`);
- **G3** lock de escritor do `data_root`, liberado em `finally` (D8);
- **G4** (ADR 8.1.0004 item 2), nesta ordem: o `--deviation`, quando vem, cita um
  `[deviation]` (`InvalidDeviationError`); (a) registros `.judged.toml` commitados —
  de outra revisão → `JudgedGenerationExistsError`; desta sem cópia selada ou com outro
  digest → `JudgedGenerationTamperedError`; (b) cópias seladas — de outra revisão →
  `JudgedGenerationExistsError`; desta, conferida pelo `find` → **`ALREADY_JUDGED`**
  (sem refresh, scorecard nem escrita); (c) tentativas de outra revisão →
  `JudgedGenerationExistsError`; (d) geração viva — de outra revisão →
  `JudgedGenerationExistsError`; desta sem tentativa registrada →
  `JudgedGenerationTamperedError`; (e) sem `--deviation`, contra **o trecho desde o
  último desvio** (as tentativas desta revisão a partir da última `started` com
  `deviation`, ou todas se nenhuma tem): outro `code.*` → `PriorAttemptCodeChangedError`;
  outro `env.*` → `PriorAttemptEnvironmentChangedError`; uma divergência já registrada no
  trecho (`result_digest` diferentes entre si) → `PriorAttemptDivergenceError` — daí em
  diante só com `--deviation`;
- registro **write-ahead** da tentativa (`started`, com a foto e o `silver_content` da
  geração viva desta revisão, se houver) → **E1** `refresh_gold(refresh_command_from(plan,
  ref))` → registro `input_read` (a entrada lida e o `result_layer_digest` da geração
  publicada: tabelas por valor e manifesto sem `started_at`/`finished_at`) →
  conferências pós-E1, sem `--deviation` e contra **toda** tentativa do trecho: (i)
  entrada diferente → `PriorAttemptInputChangedError`; (ii) resultado diferente →
  `PriorAttemptDivergenceError` (falha do R-BIT; a linha `input_read` gravada antes da
  recusa deixa a divergência registrada). A geração viva em `current/` não é a referência
  da comparação (Checkpoint C 8.1 bloco 5, CC5-1..3);
- **E2** scorecard, só com refresh `COMPLETED`; `manifest_read` tem de ser o manifesto
  publicado (`JudgedGenerationMismatchError`, I8);
- **E3** `preserve(expected_manifest=result.manifest)` com o `run_record.json` e o JSON
  do scorecard → resultado com o corpo de atestação da cópia selada.

Falha em G1-G4 não publica gold nem escreve em `judged/`; falha depois do E1 deixa a
tentativa registrada e nada selado (I13). Uma linha `INFO` por etapa.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Protocol

from financial_forecasting.features.evaluation.application.dtos.confirmatory_run import (
    ConfirmatoryRunStatus,
    DirtyCodeError,
    PriorAttemptCodeChangedError,
    PriorAttemptDivergenceError,
    PriorAttemptEnvironmentChangedError,
    PriorAttemptInputChangedError,
    RunConfirmatoryEvaluationCommand,
    RunConfirmatoryEvaluationResult,
    check_deviation,
    run_record_document,
    sealed_status,
)
from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    BuildConfirmatoryScorecardCommand,
    ScorecardResult,
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    RUN_RECORD_DOCUMENT,
    SCORECARD_DOCUMENT,
    AttemptPhase,
    JudgedAttempt,
    JudgedGeneration,
    result_layer_digest,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldManifest,
    GoldManifestNotFoundError,
    GoldPartition,
    RefreshGoldCommand,
    RefreshGoldResult,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.ports.out.evaluation_environment import (
    CODE_DIRTY_KEY,
    CODE_PREFIX,
    COMMIT_KEY,
    ENV_PREFIX,
    FALSE,
    PREREGISTRATION_DIRTY_KEY,
    EvaluationEnvironment,
)
from financial_forecasting.features.evaluation.application.ports.out.evaluation_writer_lock import (
    EvaluationWriterLock,
)
from financial_forecasting.features.evaluation.application.ports.out.gold_generation_reader import (
    GoldGenerationReader,
)
from financial_forecasting.features.evaluation.application.ports.out.judged_generation_store import (  # noqa: E501
    JudgedGenerationExistsError,
    JudgedGenerationMismatchError,
    JudgedGenerationStore,
    JudgedGenerationTamperedError,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    PreregistrationSource,
)
from financial_forecasting.features.evaluation.application.use_cases.confirmatory_attestation import (  # noqa: E501
    attestation_body,
)
from financial_forecasting.features.evaluation.application.use_cases.judged_revision import (
    resolve_judged_revision,
)

if TYPE_CHECKING:
    from financial_forecasting.shared.application.ports.out.clock import Clock
    from financial_forecasting.shared.application.ports.out.hasher import Hasher

logger = logging.getLogger(__name__)


class GoldRefresh(Protocol):
    """O refresh do gold de um cohort (real: `RefreshGold`, Stage 6.4-7.3, 8.1)."""

    def __call__(self, command: RefreshGoldCommand) -> RefreshGoldResult:
        """Regenera e publica a geração da partição do comando."""
        ...


class ScorecardBuilder(Protocol):
    """O scorecard confirmatório de uma revisão (real: `BuildConfirmatoryScorecard`, 6.5)."""

    def __call__(self, command: BuildConfirmatoryScorecardCommand) -> ScorecardResult:
        """Lê a geração viva da partição do plano e monta o scorecard."""
        ...


def _prefixed(snapshot: Mapping[str, str], prefix: str) -> dict[str, str]:
    return {key: snapshot[key] for key in sorted(snapshot) if key.startswith(prefix)}


def _since_last_deviation(attempts: Sequence[JudgedAttempt]) -> tuple[JudgedAttempt, ...]:
    """As linhas a partir da última `started` com `deviation` (todas, se nenhuma tem)."""
    start = 0
    for index, attempt in enumerate(attempts):
        if attempt.phase is AttemptPhase.STARTED and attempt.deviation is not None:
            start = index
    return tuple(attempts[start:])


@dataclasses.dataclass(frozen=True)
class _Prior:
    """O que o G4 leu da partição antes de qualquer efeito.

    `segment` são as linhas desta revisão desde o último desvio — a referência das
    conferências sem `--deviation`.
    """

    segment: tuple[JudgedAttempt, ...]
    live: GoldGeneration | None


class RunConfirmatoryEvaluation:
    """Corrida confirmatória: guardas G1-G4, tentativa write-ahead, E1 → E2 → E3."""

    def __init__(  # noqa: PLR0913 — os colaboradores do concept §4 e o Clock (ADR 8.1.0004)
        self,
        *,
        source: PreregistrationSource,
        hasher: Hasher,
        refresh_gold: GoldRefresh,
        build_scorecard: ScorecardBuilder,
        judged_store: JudgedGenerationStore,
        gold_reader: GoldGenerationReader,
        environment: EvaluationEnvironment,
        writer_lock: EvaluationWriterLock,
        clock: Clock,
    ) -> None:
        """Guarda os colaboradores (só ports e Protocols)."""
        self._source = source
        self._hasher = hasher
        self._refresh_gold = refresh_gold
        self._build_scorecard = build_scorecard
        self._judged_store = judged_store
        self._gold_reader = gold_reader
        self._environment = environment
        self._writer_lock = writer_lock
        self._clock = clock

    def __call__(
        self, command: RunConfirmatoryEvaluationCommand
    ) -> RunConfirmatoryEvaluationResult:
        """Roda a corrida (ver docstring do módulo).

        Raises:
            PreregistrationNotFoundError / PreregistrationChainError /
                PreregistrationHashMismatchError / PreregistrationNotAnchoredError: G1.
            DirtyCodeError / MissingImageIdError: G2.
            ApplicationError: lock ocupado (G3, do dono do lock).
            InvalidDeviationError / JudgedGenerationExistsError /
                JudgedGenerationTamperedError / PriorAttemptCodeChangedError /
                PriorAttemptEnvironmentChangedError: G4.
            PriorAttemptInputChangedError / PriorAttemptDivergenceError: depois do E1.
            JudgedGenerationMismatchError: manifesto lido pelo scorecard ou copiado ≠
                publicado.
            Os erros do refresh, do scorecard e do store propagam sem tradução.
        """
        judged_revision = resolve_judged_revision(
            source=self._source,
            hasher=self._hasher,
            name=command.name,
            revision=command.revision,
            preregistration_ref=command.preregistration_ref,
        )
        logger.info(
            "step=G1 preregistration_ref=%s chain=%d",
            command.preregistration_ref,
            len(judged_revision.chain),
        )
        snapshot = dict(self._environment.snapshot())
        dirty = [
            key for key in (CODE_DIRTY_KEY, PREREGISTRATION_DIRTY_KEY) if snapshot.get(key) != FALSE
        ]
        if dirty:
            raise DirtyCodeError(
                "the run needs a clean tree: "
                + ", ".join(f"{key}={snapshot.get(key)!r}" for key in dirty)
            )
        logger.info("step=G2 commit=%s", snapshot.get(COMMIT_KEY))
        refresh_command = refresh_command_from(judged_revision.plan, judged_revision.reference)
        self._writer_lock.acquire_writer(break_stale=command.break_stale_lock)
        try:
            logger.info("step=G3 writer_lock=acquired")
            return self._locked(command, snapshot, refresh_command)
        finally:
            self._writer_lock.release_writer()

    # -- G4 e efeitos (com o lock) ---------------------------------------------------------

    def _locked(
        self,
        command: RunConfirmatoryEvaluationCommand,
        snapshot: Mapping[str, str],
        refresh_command: RefreshGoldCommand,
    ) -> RunConfirmatoryEvaluationResult:
        partition = refresh_command.partition
        ref = command.preregistration_ref
        check_deviation(command.deviation)
        sealed = self._check_judged(command, partition)
        if sealed is not None:
            logger.info("step=G4 status=ALREADY_JUDGED digest=%s", sealed.generation_digest)
            return RunConfirmatoryEvaluationResult(
                status=ConfirmatoryRunStatus.ALREADY_JUDGED,
                preregistration_ref=ref,
                partition=partition,
                generation_digest=sealed.generation_digest,
                refresh_status=sealed.refresh_status,
                scorecard=None,
                failed_checks=(),
                attestation_body=attestation_body(sealed),
            )
        prior = self._check_prior(command, partition, snapshot)
        logger.info("step=G4 segment=%d live=%s", len(prior.segment), prior.live is not None)

        started_at = self._clock.now()
        attempt_id = started_at.isoformat()
        self._judged_store.record_attempt(
            partition=partition,
            attempt=JudgedAttempt(
                phase=AttemptPhase.STARTED,
                attempt_id=attempt_id,
                preregistration_ref=ref,
                commit=snapshot.get(COMMIT_KEY),
                code=_prefixed(snapshot, CODE_PREFIX),
                environment=_prefixed(snapshot, ENV_PREFIX),
                started_at=started_at,
                deviation=command.deviation,
                prior_live_silver_content=(
                    None if prior.live is None else prior.live.manifest.silver_content
                ),
            ),
        )
        logger.info("step=attempt phase=started attempt_id=%s", attempt_id)
        result = self._refresh_gold(refresh_command)
        manifest = result.manifest
        read_back = self._judged_store_input(partition, attempt_id, ref, manifest)
        logger.info("step=E1 status=%s tables=%d", result.status.value, len(result.rows_by_table))
        self._check_after_refresh(command, prior, read_back)

        scorecard = None
        if result.status is RefreshStatus.COMPLETED:
            scorecard = self._build_scorecard(
                BuildConfirmatoryScorecardCommand(
                    name=command.name, revision=command.revision, preregistration_ref=ref
                )
            )
            if scorecard.manifest_read != manifest:
                raise JudgedGenerationMismatchError(
                    f"the scorecard read another manifest of {partition} than the refresh "
                    f"published (I8)"
                )
            logger.info("step=E2 academic_decision_ready=%s", scorecard.academic_decision_ready)
        documents: dict[str, Mapping[str, object]] = {
            RUN_RECORD_DOCUMENT: run_record_document(
                preregistration_ref=ref,
                partition=partition,
                environment=snapshot,
                inference_summary=command.inference_summary,
                deviation=command.deviation,
                attempts=self._judged_store.attempts(partition=partition),
                refresh_status=result.status,
                rows_by_table=result.rows_by_table,
                profile_error_units=result.profile_error_units,
                conformal_error_units=result.conformal_error_units,
                failed_checks=result.failed_checks,
            )
        }
        if scorecard is not None:
            documents[SCORECARD_DOCUMENT] = scorecard.as_mapping()
        judged = self._judged_store.preserve(
            partition=partition,
            preregistration_ref=ref,
            expected_manifest=manifest,
            documents=documents,
        )
        status = sealed_status(judged.refresh_status)
        logger.info("step=E3 status=%s digest=%s", status.value, judged.generation_digest)
        return RunConfirmatoryEvaluationResult(
            status=status,
            preregistration_ref=ref,
            partition=partition,
            generation_digest=judged.generation_digest,
            refresh_status=judged.refresh_status,
            scorecard=scorecard,
            failed_checks=result.failed_checks,
            attestation_body=attestation_body(judged),
        )

    def _check_judged(
        self, command: RunConfirmatoryEvaluationCommand, partition: GoldPartition
    ) -> JudgedGeneration | None:
        """G4 (a)-(b): registros commitados e cópias seladas; a selada íntegra desta revisão."""
        ref = command.preregistration_ref
        records = self._source.judged_records(name=command.name)
        others = sorted({r.preregistration_ref for r in records if r.preregistration_ref != ref})
        if others:
            raise JudgedGenerationExistsError(
                f"{command.name!r} already has committed judged records of {others}"
            )
        sealed = self._judged_store.find(partition=partition, preregistration_ref=ref)
        for record in records:
            if sealed is None or sealed.generation_digest != record.generation_digest:
                raise JudgedGenerationTamperedError(
                    f"the committed record of {ref} names digest {record.generation_digest}, "
                    f"the sealed copy has {None if sealed is None else sealed.generation_digest}"
                )
        other_sealed = [
            name for name in self._judged_store.judged_refs(partition=partition) if name != ref
        ]
        if other_sealed:
            raise JudgedGenerationExistsError(
                f"partition {partition} already has the judged generation of {other_sealed}"
            )
        return sealed

    def _check_prior(
        self,
        command: RunConfirmatoryEvaluationCommand,
        partition: GoldPartition,
        snapshot: Mapping[str, str],
    ) -> _Prior:
        """G4 (c)-(e): tentativas e geração viva; o trecho desde o último desvio."""
        ref = command.preregistration_ref
        attempts = self._judged_store.attempts(partition=partition)
        others = sorted({a.preregistration_ref for a in attempts if a.preregistration_ref != ref})
        if others:
            raise JudgedGenerationExistsError(
                f"partition {partition} already has attempts of {others}"
            )
        try:
            live: GoldGeneration | None = self._gold_reader.read_generation(partition=partition)
        except GoldManifestNotFoundError:
            live = None
        if live is not None:
            live_ref = live.manifest.parameters.preregistration_ref
            if live_ref != ref:
                raise JudgedGenerationExistsError(
                    f"the live generation of {partition} is of {live_ref!r}, not {ref!r}"
                )
            if not attempts:
                raise JudgedGenerationTamperedError(
                    f"the live generation of {partition} has no recorded attempt (an "
                    "unrecorded refresh)"
                )
        segment = _since_last_deviation(attempts)
        if command.deviation is None:
            started = [a for a in segment if a.phase is AttemptPhase.STARTED]
            code, environment = _prefixed(snapshot, CODE_PREFIX), _prefixed(snapshot, ENV_PREFIX)
            if any(dict(a.code or {}) != code for a in started):
                raise PriorAttemptCodeChangedError(
                    f"an earlier attempt of {ref} ran other code; re-running needs --deviation"
                )
            if any(dict(a.environment or {}) != environment for a in started):
                raise PriorAttemptEnvironmentChangedError(
                    f"an earlier attempt of {ref} ran in another environment; re-running "
                    "needs --deviation"
                )
            results = {a.result_digest for a in segment if a.phase is AttemptPhase.INPUT_READ}
            if len(results) > 1:
                raise PriorAttemptDivergenceError(
                    f"the attempts of {ref} already diverged in the result layer (R-BIT "
                    "failure recorded); re-running needs --deviation"
                )
        return _Prior(segment=segment, live=live)

    def _judged_store_input(
        self, partition: GoldPartition, attempt_id: str, ref: str, manifest: GoldManifest
    ) -> JudgedAttempt:
        """Grava a linha `input_read`: a entrada lida e o resultado publicado pelo E1."""
        line = JudgedAttempt(
            phase=AttemptPhase.INPUT_READ,
            attempt_id=attempt_id,
            preregistration_ref=ref,
            silver_content=manifest.silver_content,
            dataset_fingerprint=manifest.dataset_fingerprint.value,
            result_digest=result_layer_digest(
                self._gold_reader.read_generation(partition=partition)
            ),
        )
        self._judged_store.record_attempt(partition=partition, attempt=line)
        return line

    def _check_after_refresh(
        self,
        command: RunConfirmatoryEvaluationCommand,
        prior: _Prior,
        read_back: JudgedAttempt,
    ) -> None:
        """2b (i)-(ii): entrada e resultado contra toda tentativa do trecho, sem desvio."""
        if command.deviation is not None:
            return
        earlier = [a for a in prior.segment if a.phase is AttemptPhase.INPUT_READ]
        new_input = (read_back.silver_content, read_back.dataset_fingerprint)
        changed = [
            a.attempt_id for a in earlier if (a.silver_content, a.dataset_fingerprint) != new_input
        ]
        if changed:
            raise PriorAttemptInputChangedError(
                f"the refresh read another input than the attempts {changed} of "
                f"{command.preregistration_ref}; re-running needs --deviation"
            )
        diverged = [a.attempt_id for a in earlier if a.result_digest != read_back.result_digest]
        if diverged:
            raise PriorAttemptDivergenceError(
                f"the new generation of {command.preregistration_ref} differs in the result "
                f"layer from the attempts {diverged} with the same code, environment and input "
                "(R-BIT failure: stop for diagnosis)"
            )
