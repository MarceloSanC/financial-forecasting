"""Use case `BuildConfirmatoryScorecard` — o scorecard confirmatório de uma revisão (Stage 6.5).

Concept 6.5 §4, I5, I6, I12, I13, C2-C5, C7, C10, C11; ADRs `6_5_0002` item 4,
`6_5_0003` item 3, `6_5_0007` item 8. `__call__(command)`, nesta ordem (I5) — os
passos 1-3 são o `resolve_judged_revision` (dono único desde a Stage 8.1, A3):

1. lê as revisões 0..r do plano (`PreregistrationSource`) e monta cada
   `Preregistration` (C1/C2 propagam); **cadeia** — `name`/`revision` do payload iguais
   aos pedidos, r ≥ 1 com `amends` = a referência calculada da anterior
   (`PreregistrationChainError`);
2. **hash** — a referência da revisão julgada = `command.preregistration_ref`
   (`PreregistrationHashMismatchError`);
3. **âncora** — toda revisão da cadeia ancorada, com a tag
   `preregistration/<referência calculada da própria revisão>` — âncora velha de um plano
   re-hasheado não serve (`PreregistrationNotAnchoredError`; ADR 6.5.0003 item 1);
4. só então lê o gold da partição **derivada do plano** (`refresh_command_from`);
5. `BLOCKED` → `GoldNotReadyError` com os checks `ERROR` + `FAIL`;
6. mapeia e confere o gold (`evidence_from_generation`, C6/C8);
7. veredito (`ConfirmatoryScorecard.decide`) — **antes** e sem o perfil (I12);
8. perfil (`build_profile`);
9. prontidão — razões `REQUIRED_CHECK_SKIPPED` (check exigido `SKIPPED`),
   `GOLD_BEFORE_ANCHOR` (`started_at` < âncora da revisão julgada; igualdade é pronta)
   e `AMENDED_AFTER_UNBLINDING` (alguma emenda `unblinded`); nunca o desfecho nem a
   declaração de cegamento (I13). Não há razão "check exigido falhou": `ERROR` + `FAIL`
   só existe em gold `BLOCKED` (passo 5) ou corrompido (passo 6).

Os erros moram em `dtos/confirmatory_scorecard.py` (importados daqui, sem
reexportação — technical 6.5 §7 `[deviation]` Task 08).

As células são lidas pelos acessores tipados de `refresh_gold` (F6): tipo divergente
do schema é corrupção nomeada (`GoldGenerationCorruptError`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    BuildConfirmatoryScorecardCommand,
    GoldNotReadyError,
    ReadinessReason,
    ScorecardResult,
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_QUALITY_CHECKS,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    FailedCheck,
    GoldGeneration,
    RefreshStatus,
    col_int,
    col_int_or_none,
    col_str,
    col_str_or_none,
)
from financial_forecasting.features.evaluation.application.ports.out.gold_generation_reader import (
    GoldGenerationReader,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    PreregistrationAnchor,
    PreregistrationSource,
)
from financial_forecasting.features.evaluation.application.use_cases.judged_revision import (
    resolve_judged_revision,
)
from financial_forecasting.features.evaluation.application.use_cases.scorecard_evidence import (
    evidence_from_generation,
)
from financial_forecasting.features.evaluation.application.use_cases.scorecard_profile import (
    build_profile,
)
from financial_forecasting.features.evaluation.domain.services.confirmatory_scorecard import (
    ConfirmatoryScorecard,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.alignment_check import (  # noqa: E501
    ALIGNMENT_CHECK,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.degeneracy_check import (  # noqa: E501
    DEGENERACY_CHECK,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.statistical_preconditions_check import (  # noqa: E501
    STATISTICAL_PRECONDITIONS,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    BlindStatus,
    Preregistration,
)
from financial_forecasting.features.evaluation.domain.value_objects.quality_check_result import (
    CheckOutcome,
    CheckSeverity,
)
from financial_forecasting.shared.application.ports.out.hasher import Hasher

REQUIRED_CHECKS: Final = frozenset({DEGENERACY_CHECK, ALIGNMENT_CHECK, STATISTICAL_PRECONDITIONS})
"""Os checks de que o veredito precisa (ADR 6.5.0007 item 8)."""


def _failed_checks(generation: GoldGeneration) -> tuple[FailedCheck, ...]:
    schema = GOLD_QUALITY_CHECKS
    return tuple(
        FailedCheck(
            check=col_str(row, schema, "check"),
            kind=col_str(row, schema, "kind"),
            horizon=col_int_or_none(row, schema, "horizon"),
            model=col_str_or_none(row, schema, "model"),
            seed=col_int_or_none(row, schema, "seed"),
            occurrences=col_int(row, schema, "occurrences"),
            detail=col_str(row, schema, "detail"),
        )
        for row in generation.table(schema).rows
        if col_str(row, schema, "severity") == CheckSeverity.ERROR.value
        and col_str(row, schema, "outcome") == CheckOutcome.FAIL.value
    )


def _required_check_skipped(generation: GoldGeneration) -> bool:
    schema = GOLD_QUALITY_CHECKS
    return any(
        col_str(row, schema, "check") in REQUIRED_CHECKS
        and col_str(row, schema, "outcome") == CheckOutcome.SKIPPED.value
        for row in generation.table(schema).rows
    )


class BuildConfirmatoryScorecard:
    """Valida a cadeia, o hash e a âncora; lê, confere e julga o gold (ver módulo)."""

    def __init__(
        self, *, source: PreregistrationSource, reader: GoldGenerationReader, hasher: Hasher
    ) -> None:
        """Os três colaboradores do concept 6.5 §4 (keyword-only)."""
        self._source = source
        self._reader = reader
        self._hasher = hasher

    def __call__(self, command: BuildConfirmatoryScorecardCommand) -> ScorecardResult:
        """O scorecard da revisão `command.revision` do plano `command.name`.

        Raises:
            PreregistrationNotFoundError: revisão inexistente (C2).
            ValueError: plano malformado (C1).
            PreregistrationChainError / PreregistrationHashMismatchError /
                PreregistrationNotAnchoredError: nesta ordem, antes de ler o gold (C3-C5).
            GoldManifestNotFoundError / GoldGenerationCorruptError: gold ausente ou
                corrompido (C6).
            GoldNotReadyError: gold `BLOCKED` (C7).
            PreregistrationMismatchError: gold de outro plano ou cohort (C8).
        """
        revision = resolve_judged_revision(
            source=self._source,
            hasher=self._hasher,
            name=command.name,
            revision=command.revision,
            preregistration_ref=command.preregistration_ref,
        )
        judged, chain, anchor = revision.plan, revision.chain, revision.anchor
        derived = refresh_command_from(judged, revision.reference)
        generation = self._reader.read_generation(partition=derived.partition)
        if generation.manifest.status is RefreshStatus.BLOCKED:
            raise GoldNotReadyError(_failed_checks(generation))
        evidence = evidence_from_generation(prereg=judged, command=derived, generation=generation)
        verdict = ConfirmatoryScorecard.decide(judged, evidence)
        profile = build_profile(
            prereg=judged, evidence=evidence, verdict=verdict, generation=generation
        )
        reasons = self._readiness(generation, anchor, revision.plans)
        return ScorecardResult(
            preregistration_ref=revision.reference,
            revision_chain=chain,
            anchor=anchor,
            blinding_statement=judged.blinding_statement,
            manifest_read=generation.manifest,
            verdict=verdict,
            profile=profile,
            academic_decision_ready=not reasons,
            readiness_reasons=reasons,
        )

    @staticmethod
    def _readiness(
        generation: GoldGeneration,
        anchor: PreregistrationAnchor,
        plans: Sequence[Preregistration],
    ) -> tuple[ReadinessReason, ...]:
        reasons: list[ReadinessReason] = []
        if _required_check_skipped(generation):
            reasons.append(ReadinessReason.REQUIRED_CHECK_SKIPPED)
        if generation.manifest.started_at < anchor.anchored_at:
            reasons.append(ReadinessReason.GOLD_BEFORE_ANCHOR)
        if any(
            plan.amendment is not None and plan.amendment.blind_status is BlindStatus.UNBLINDED
            for plan in plans
        ):
            reasons.append(ReadinessReason.AMENDED_AFTER_UNBLINDING)
        return tuple(reasons)
