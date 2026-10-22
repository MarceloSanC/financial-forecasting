"""`resolve_judged_revision` — a revisão julgada de um plano, validada (Stage 8.1, A3).

Dono único da validação que até a 8.1 era privada do `BuildConfirmatoryScorecard`
(concept 8.1 §4, D2): o scorecard e o orquestrador da corrida confirmatória
(`RunConfirmatoryEvaluation`) resolvem a revisão pelo mesmo código. Passos, nesta ordem
(os de antes, movidos sem mudança — concept 6.5 I5):

1. lê as revisões 0..r do plano (`PreregistrationSource`) e monta cada
   `Preregistration` (C1/C2 propagam); **cadeia** — `name`/`revision` do payload iguais
   aos pedidos, r ≥ 1 com `amends` = a referência calculada da anterior
   (`PreregistrationChainError`);
2. **hash** — a referência da revisão julgada = `preregistration_ref`
   (`PreregistrationHashMismatchError`);
3. **âncora** — toda revisão da cadeia ancorada, com a tag
   `preregistration/<referência calculada da própria revisão>`
   (`PreregistrationNotAnchoredError`; ADR 6.5.0003 item 1).

Devolve **todos** os registros e planos da cadeia (a prontidão do scorecard precisa deles
para `AMENDED_AFTER_UNBLINDING`), a cadeia de referências e a âncora da julgada.
"""

from __future__ import annotations

from dataclasses import dataclass

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    PreregistrationChainError,
    PreregistrationHashMismatchError,
    PreregistrationNotAnchoredError,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    ANCHOR_TAG_PREFIX,
    PreregistrationAnchor,
    PreregistrationRecord,
    PreregistrationSource,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.shared.application.ports.out.hasher import Hasher
from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
    PreregistrationHash,
)


@dataclass(frozen=True)
class JudgedRevision:
    """A cadeia 0..r validada de um plano e a âncora da revisão julgada (a última).

    Campos:
        records: os registros lidos, revisão 0 primeiro.
        plans: os planos montados de cada registro, na mesma ordem.
        chain: a referência calculada de cada revisão, na mesma ordem.
        anchor: a âncora da revisão julgada.
    """

    records: tuple[PreregistrationRecord, ...]
    plans: tuple[Preregistration, ...]
    chain: tuple[str, ...]
    anchor: PreregistrationAnchor

    def __post_init__(self) -> None:
        sizes = {len(self.records), len(self.plans), len(self.chain)}
        if len(sizes) != 1 or not self.chain:
            raise ValueError(
                "records, plans and chain must be non-empty and of the same length, got "
                f"{len(self.records)}, {len(self.plans)}, {len(self.chain)}"
            )

    @property
    def plan(self) -> Preregistration:
        """O plano da revisão julgada."""
        return self.plans[-1]

    @property
    def reference(self) -> str:
        """A referência calculada da revisão julgada."""
        return self.chain[-1]


def resolve_judged_revision(
    *,
    source: PreregistrationSource,
    hasher: Hasher,
    name: str,
    revision: int,
    preregistration_ref: str,
) -> JudgedRevision:
    """A revisão `revision` do plano `name`, validada contra `preregistration_ref`.

    Raises:
        PreregistrationNotFoundError: revisão inexistente (C2).
        ValueError: plano malformado (C1).
        PreregistrationChainError / PreregistrationHashMismatchError /
            PreregistrationNotAnchoredError: nesta ordem (C3-C5).
    """
    records = [source.read(name=name, revision=index) for index in range(revision + 1)]
    plans = [Preregistration.from_mapping(record.payload) for record in records]
    chain = _chain(name, plans, hasher)
    if chain[-1] != preregistration_ref:
        raise PreregistrationHashMismatchError(
            f"revision {revision} of {name!r} hashes to {chain[-1]!r}, "
            f"the command expects {preregistration_ref!r}"
        )
    unanchored = [index for index, record in enumerate(records) if record.anchor is None]
    anchor = records[-1].anchor
    if unanchored or anchor is None:
        raise PreregistrationNotAnchoredError(f"revisions {unanchored} of {name!r} have no anchor")
    mismatched = [
        index
        for index, (record, reference) in enumerate(zip(records, chain, strict=True))
        if record.anchor is not None and record.anchor.tag != f"{ANCHOR_TAG_PREFIX}{reference}"
    ]
    if mismatched:
        raise PreregistrationNotAnchoredError(
            f"the anchors of revisions {mismatched} of {name!r} are not the tags "
            f"of their computed references (an anchor must match its revision)"
        )
    return JudgedRevision(
        records=tuple(records), plans=tuple(plans), chain=tuple(chain), anchor=anchor
    )


def _chain(name: str, plans: list[Preregistration], hasher: Hasher) -> list[str]:
    references: list[str] = []
    for revision, plan in enumerate(plans):
        if (plan.name, plan.revision) != (name, revision):
            raise PreregistrationChainError(
                f"the file of revision {revision} of {name!r} declares "
                f"name={plan.name!r}, revision={plan.revision}"
            )
        if revision > 0:
            amends = None if plan.amendment is None else plan.amendment.amends
            if amends != references[-1]:
                raise PreregistrationChainError(
                    f"revision {revision} amends {amends!r}, the previous "
                    f"revision is {references[-1]!r}"
                )
        digest = PreregistrationHash.compute(hasher=hasher, payload=plan.as_payload())
        references.append(plan.reference(digest))
    return references
